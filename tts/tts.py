import logging
import json
import io
import wave
import aiohttp
import asyncio
import re
import os
import struct
from base64 import b64decode
from gradio_client import Client

from homeassistant.components.tts import TextToSpeechEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import *

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    engine = entry.data.get(CONF_ENGINE, ENGINE_ZAI)
    if engine == ENGINE_QWEN:
        async_add_entities([QwenTTSEntity(hass, entry)])
    else:
        async_add_entities([ZaiTTSEntity(hass, entry)])

class ZaiTTSEntity(TextToSpeechEntity):
    _attr_has_entity_name = True
    _attr_name = "TTS Service"
    _attr_supported_languages = ["zh", "en"]
    _attr_default_language = "zh"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self._hass, self._entry = hass, entry
        self._attr_unique_id = f"{entry.entry_id}_zai_tts_service"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Z.ai TTS",
            "manufacturer": "Z.ai",
            "model": "Zai TTS Service"
        }

    @property
    def default_voice(self) -> str: return self._entry.data.get(CONF_VOICE_ID, DEFAULT_VOICE)
    @property
    def supported_voices(self) -> list[str]:
        customs = self._entry.data.get(CONF_CUSTOM_VOICES_DICT, {})
        return list(VOICE_MAP.keys()) + list(customs.keys())

    def _apply_fade(self, pcm_data, fade_ms, sample_rate=24000):
        if fade_ms <= 0 or not pcm_data: return pcm_data
        try:
            samples = list(struct.unpack(f"<{len(pcm_data)//2}h", pcm_data))
            fade_len = int(sample_rate * (fade_ms / 1000))
            fade_len = min(fade_len, len(samples) // 2)
            for i in range(fade_len):
                samples[i] = int(samples[i] * (i / fade_len))
                idx = len(samples) - 1 - i
                samples[idx] = int(samples[idx] * (i / fade_len))
            return struct.pack(f"<{len(samples)}h", *samples)
        except Exception: return pcm_data

    async def _show_error(self, msg):
        await self._hass.services.async_call("persistent_notification", "create", {"title": "Z.ai TTS 报警", "message": msg, "notification_id": "zai_tts_alert"})

    async def _get_event_stream(self, res):
        buffer = b""
        async for chunk in res.content.iter_any():
            buffer += chunk
            if b"\n" not in chunk: continue
            lines = buffer.split(b"\n")
            buffer = lines.pop()
            for line_bytes in lines:
                if line_bytes: yield line_bytes.decode().strip()
        if buffer: yield buffer.decode().strip()

    async def _raw_fetch_logic(self, session, payload, headers):
        try:
            async with session.post("https://audio.z.ai/api/v1/z-audio/tts/create", json=payload, headers=headers, timeout=60) as res:
                if res.status != 200:
                    err_text = await res.text()
                    if res.status == 404: await self._show_error("样本被清空了！请检查 Voice ID。")
                    elif res.status == 401: await self._show_error("Token 过期了，请重新配置。")
                    return None, None
                combined_audio, wav_params = bytearray(), None
                async for line in self._get_event_stream(res):
                    if not line.startswith("data:"): continue
                    text = line[5:].strip()
                    if text == "[DONE]": break
                    try:
                        data_json = json.loads(text)
                        if b64_audio := data_json.get("audio"):
                            chunk_bytes = b64decode(b64_audio)
                            if chunk_bytes.startswith(b"RIFF"):
                                with io.BytesIO(chunk_bytes) as f, wave.open(f, 'rb') as w:
                                    if wav_params is None: wav_params = w.getparams()
                                    chunk_bytes = w.readframes(w.getnframes())
                            combined_audio.extend(chunk_bytes)
                    except Exception: continue
                return wav_params, combined_audio
        except Exception as e:
            _LOGGER.error("ZaiTTS 通信失败: %s", e)
            return None, None

    async def async_get_tts_audio(self, message: str, language: str, options: dict | None = None):
        data = self._entry.data
        token, user_id, speed = data.get(CONF_TOKEN), data.get(CONF_USER_ID) or "0", data.get(CONF_SPEED, 1.0)
        smoothing, concurrent, max_con = int(data.get(CONF_SMOOTHING, DEFAULT_SMOOTHING)), data.get(CONF_CONCURRENT, False), int(data.get(CONF_MAX_CONCURRENCY, 3))
        voice_id = (options or {}).get("voice") or self.default_voice
        voice_name = VOICE_MAP.get(voice_id) or data.get(CONF_CUSTOM_VOICES_DICT, {}).get(voice_id, "活泼女声")
        headers = {"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0", "Referer": "https://audio.z.ai/", "Origin": "https://audio.z.ai", "Accept": "text/event-stream", "Accept-Encoding": "gzip, deflate"}
        session = async_get_clientsession(self._hass)
        if concurrent and len(message) > 15:
            raw_parts = re.split(r'([。！？!?.])', message)
            sentences = [raw_parts[i] + raw_parts[i+1] for i in range(0, len(raw_parts)-1, 2)]
            if len(raw_parts) % 2 == 1: sentences.append(raw_parts[-1])
            sentences = [s.strip() for s in sentences if s.strip()]
            num_tasks = min(max_con, len(sentences))
            chunks = []
            if num_tasks <= 1: chunks = [message]
            else:
                k, m = divmod(len(sentences), num_tasks)
                idx = 0
                for i in range(num_tasks):
                    size = k + (1 if i < m else 0)
                    chunks.append("".join(sentences[idx:idx+size])); idx += size
            tasks = [self._raw_fetch_logic(session, {"voice_name": voice_name, "voice_id": voice_id, "user_id": user_id, "input_text": c, "speed": int(float(speed) * 10) / 10, "volume": 1}, headers) for c in chunks if c]
            results = await asyncio.gather(*tasks)
            all_pcm, final_params = bytearray(), None
            for p_params, p_pcm in results:
                if p_pcm:
                    if final_params is None: final_params = p_params
                    all_pcm.extend(self._apply_fade(p_pcm, smoothing, final_params.framerate if final_params else 24000))
            if not all_pcm: return None, None
            output = io.BytesIO()
            with wave.open(output, 'wb') as out_w:
                if final_params: out_w.setparams(final_params)
                else: out_w.setnchannels(1); out_w.setsampwidth(2); out_w.setframerate(24000)
                out_w.writeframes(all_pcm)
            return ("wav", output.getvalue())
        else:
            payload = {"voice_name": voice_name, "voice_id": voice_id, "user_id": user_id, "input_text": message, "speed": int(float(speed) * 10) / 10, "volume": 1}
            res_params, res_pcm = await self._raw_fetch_logic(session, payload, headers)
            if not res_pcm: return (None, None)
            output = io.BytesIO()
            with wave.open(output, 'wb') as out_w:
                if res_params: out_w.setparams(res_params)
                else: out_w.setnchannels(1); out_w.setsampwidth(2); out_w.setframerate(24000)
                out_w.writeframes(res_pcm)
            return ("wav", output.getvalue())

class QwenTTSEntity(TextToSpeechEntity):
    _attr_has_entity_name, _attr_name = True, "Qwen TTS Service"
    _attr_supported_languages, _attr_default_language = ["zh", "en", "auto"], "zh"
    def __init__(self, hass, entry):
        self._hass, self._entry = hass, entry
        self._attr_unique_id = f"{entry.entry_id}_qwen_tts"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": "Qwen TTS", "manufacturer": "Alibaba", "model": "Qwen2-Audio"}
    @property
    def supported_voices(self) -> list[str]: return QWEN_VOICES
    async def async_get_tts_audio(self, message, language, options=None):
        url, voice = self._entry.data.get(CONF_QWEN_URL), (options or {}).get("voice") or self._entry.data.get(CONF_QWEN_VOICE)
        audio = await self._hass.async_add_executor_job(self._p, url, message, voice)
        return ("wav", audio) if audio else (None, None)
    def _p(self, url, t, v):
        try:
            p = Client(url).predict(text=t, voice_display=v, api_name="/tts_interface")
            if p and os.path.exists(p):
                with open(p, "rb") as f: d = f.read()
                os.remove(p); return d
        except: return None