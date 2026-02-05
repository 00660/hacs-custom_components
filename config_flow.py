import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import *

def get_zai_schema(defaults):
    v_opt = [{"value": k, "label": v} for k, v in VOICE_MAP.items()]
    return vol.Schema({
        vol.Required(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): str,
        # 核心改动：把 Required 改成 Optional
        vol.Optional(CONF_USER_ID, default=defaults.get(CONF_USER_ID, "")): str,
        vol.Optional(CONF_VOICE_ID, default=defaults.get(CONF_VOICE_ID, DEFAULT_VOICE)): selector.SelectSelector(selector.SelectSelectorConfig(options=v_opt, mode="dropdown")),
        vol.Optional(CONF_SPEED, default=float(defaults.get(CONF_SPEED, DEFAULT_SPEED))): selector.NumberSelector(selector.NumberSelectorConfig(min=0.5, max=2.0, step=0.1, mode="slider")),
        vol.Optional(CONF_SMOOTHING, default=int(defaults.get(CONF_SMOOTHING, DEFAULT_SMOOTHING))): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=50, step=1, mode="slider")),
        vol.Optional(CONF_CONCURRENT, default=defaults.get(CONF_CONCURRENT, False)): selector.BooleanSelector(),
        vol.Optional(CONF_MAX_CONCURRENCY, default=int(defaults.get(CONF_MAX_CONCURRENCY, 3))): selector.NumberSelector(selector.NumberSelectorConfig(min=2, max=5, step=1, mode="box")),
    })

class ZaiTTSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=[ENGINE_ZAI, ENGINE_QWEN])

    async def async_step_zai(self, user_input=None):
        if user_input is not None:
            user_input[CONF_ENGINE] = ENGINE_ZAI
            return self.async_create_entry(title="Z.ai TTS", data=user_input)
        return self.async_show_form(step_id="zai", data_schema=get_zai_schema({}))

    async def async_step_qwen(self, user_input=None):
        if user_input is not None:
            user_input[CONF_ENGINE] = ENGINE_QWEN
            return self.async_create_entry(title="Qwen TTS", data=user_input)
        return self.async_show_form(step_id="qwen", data_schema=vol.Schema({
            vol.Required(CONF_QWEN_URL, default=DEFAULT_QWEN_URL): str,
            vol.Optional(CONF_QWEN_VOICE, default=DEFAULT_QWEN_VOICE): selector.SelectSelector(selector.SelectSelectorConfig(options=[{"value": v, "label": v} for v in QWEN_VOICES], mode="dropdown")),
        }))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry): return ZaiTTSOptionsFlowHandler(config_entry)

class ZaiTTSOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry): self._entry, self._temp_id = entry, None
    async def async_step_init(self, user_input=None):
        engine = self._entry.data.get(CONF_ENGINE)
        if engine == ENGINE_QWEN: return await self.async_step_modify_base()
        return self.async_show_menu(step_id="init", menu_options=["modify_base", "add_voice_id", "clear_voices"])

    async def async_step_modify_base(self, user_input=None):
        if user_input is not None:
            new_data = {**self._entry.data, **user_input}
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            return self.async_create_entry(title="", data={})
        current = {**self._entry.data, **self._entry.options}
        if self._entry.data.get(CONF_ENGINE) == ENGINE_QWEN:
            schema = vol.Schema({vol.Required(CONF_QWEN_URL, default=current.get(CONF_QWEN_URL)): str, vol.Optional(CONF_QWEN_VOICE, default=current.get(CONF_QWEN_VOICE)): selector.SelectSelector(selector.SelectSelectorConfig(options=[{"value": v, "label": v} for v in QWEN_VOICES], mode="dropdown"))})
        else: schema = get_zai_schema(current)
        return self.async_show_form(step_id="modify_base", data_schema=schema)

    async def async_step_add_voice_id(self, user_input=None):
        if user_input is not None: self._temp_id = user_input["v_id"]; return await self.async_step_add_voice_name()
        return self.async_show_form(step_id="add_voice_id", data_schema=vol.Schema({vol.Required("v_id"): str}))

    async def async_step_add_voice_name(self, user_input=None):
        if user_input is not None:
            customs = dict(self._entry.data.get(CONF_CUSTOM_VOICES_DICT, {}))
            customs[self._temp_id] = user_input["v_name"]
            new_data = {**self._entry.data, CONF_CUSTOM_VOICES_DICT: customs}
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(step_id="add_voice_name", description_placeholders={"v_id": self._temp_id}, data_schema=vol.Schema({vol.Required("v_name"): str}))

    async def async_step_clear_voices(self, _=None):
        new_data = {**self._entry.data, CONF_CUSTOM_VOICES_DICT: {}}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
        return self.async_create_entry(title="", data={})