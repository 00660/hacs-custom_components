from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlencode

import voluptuous as vol

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    ATTR_ENTRY_ID,
    CONF_CAMERA_ENTITY_ID,
    CONF_COOLDOWN_SECONDS,
    CONF_DOORBELL_ENTITY_ID,
    CONF_NOTIFICATION_MESSAGE,
    CONF_OPEN_ACTION_TITLE,
    CONF_OPEN_URI,
    CONF_NOTIFICATION_TAG,
    CONF_NOTIFICATION_TIMEOUT,
    CONF_NOTIFICATION_TITLE,
    CONF_NOTIFY_TARGETS,
    CONF_TRIGGER_STATE,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_NOTIFICATION_MESSAGE,
    DEFAULT_OPEN_ACTION_TITLE,
    DEFAULT_NOTIFICATION_TAG,
    DEFAULT_NOTIFICATION_TIMEOUT,
    DEFAULT_NOTIFICATION_TITLE,
    DEFAULT_TRIGGER_STATE,
    DOMAIN,
    EVENT_HANGUP_PRESSED,
    FRONTEND_CARD_JS_URL,
    FRONTEND_CARD_TAG,
    FRONTEND_PANEL_JS_URL,
    FRONTEND_PANEL_TAG,
    FRONTEND_PANEL_URL_PATH,
    FRONTEND_STATIC_BASE,
    SERVICE_CLEAR_NOTIFICATION,
    SERVICE_SEND_NOTIFICATION,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RuntimeConfig:
    name: str
    doorbell_entity_id: str
    camera_entity_id: str
    notify_targets: list[str]
    notification_title: str
    notification_message: str
    open_action_title: str
    open_uri: str
    notification_tag: str
    notification_timeout: int
    cooldown_seconds: int
    trigger_state: str


class DoorbellCallRuntime:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config = _build_runtime_config(entry)
        self._last_triggered = 0.0
        self._unsub_state = None
        self._unsub_action = None

    @property
    def hangup_action(self) -> str:
        return f"{DOMAIN}_hangup_{self.entry.entry_id}"

    @property
    def open_uri(self) -> str:
        if self.config.open_uri:
            return self.config.open_uri
        if self.config.camera_entity_id:
            return _build_panel_uri(self.config.camera_entity_id, self.config.name, self.entry.entry_id)
        return ""

    async def async_setup(self) -> None:
        self._unsub_state = async_track_state_change_event(
            self.hass,
            [self.config.doorbell_entity_id],
            self._handle_doorbell_state_change,
        )
        self._unsub_action = self.hass.bus.async_listen(
            "mobile_app_notification_action",
            self._handle_mobile_action,
        )

    async def async_unload(self) -> None:
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_action:
            self._unsub_action()
            self._unsub_action = None

    @callback
    def _handle_doorbell_state_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return
        if str(new_state.state) != self.config.trigger_state:
            return
        if old_state is not None and str(old_state.state) == str(new_state.state):
            return

        now = monotonic()
        if self.config.cooldown_seconds > 0 and now - self._last_triggered < self.config.cooldown_seconds:
            _LOGGER.debug(
                "门铃触发被冷却忽略 | entry_id=%s entity=%s cooldown=%ss",
                self.entry.entry_id,
                self.config.doorbell_entity_id,
                self.config.cooldown_seconds,
            )
            return
        self._last_triggered = now
        self.hass.async_create_task(self.async_send_notification())

    @callback
    def _handle_mobile_action(self, event: Event) -> None:
        action = str((event.data or {}).get("action") or "").strip()
        if not action:
            return

        if action == self.hangup_action:
            self.hass.async_create_task(self._async_handle_hangup_action(event))

    async def _async_handle_hangup_action(self, event: Event) -> None:
        self.hass.bus.async_fire(
            EVENT_HANGUP_PRESSED,
            self._build_event_payload(event),
        )
        await self.async_clear_notification()

    def _build_event_payload(self, event: Event | None = None) -> dict[str, Any]:
        return {
            ATTR_ENTRY_ID: self.entry.entry_id,
            "name": self.config.name,
            "doorbell_entity_id": self.config.doorbell_entity_id,
            "camera_entity_id": self.config.camera_entity_id,
            "notification_tag": self.config.notification_tag,
            "mobile_event": dict(event.data or {}) if event is not None else {},
        }

    async def async_send_notification(self) -> None:
        data = {
            "tag": self.config.notification_tag,
            "group": self.config.notification_tag,
            "sticky": True,
            "timeout": self.config.notification_timeout,
            "entity_id": self.config.camera_entity_id,
            "actions": self._build_notification_actions(),
        }
        if self.open_uri:
            data["url"] = self.open_uri
            data["clickAction"] = self.open_uri
        for notify_target in self.config.notify_targets:
            await _async_send_notify_message(
                self.hass,
                notify_target,
                self.config.notification_title,
                self.config.notification_message,
                data,
            )

    async def async_clear_notification(self) -> None:
        data = {"tag": self.config.notification_tag}
        for notify_target in self.config.notify_targets:
            await _async_send_notify_message(
                self.hass,
                notify_target,
                "",
                "clear_notification",
                data,
            )

    def _build_notification_actions(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if self.open_uri:
            actions.append(
                {
                    "action": "URI",
                    "title": self.config.open_action_title,
                    "uri": self.open_uri,
                }
            )
        actions.append(
            {
                "action": self.hangup_action,
                "title": "关闭",
                "destructive": True,
            }
        )
        return actions


DomainData = dict[str, DoorbellCallRuntime]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await _async_register_frontend(hass)
    await _async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await _async_register_frontend(hass)
    await _async_register_services(hass)
    runtime = DoorbellCallRuntime(hass, entry)
    await runtime.async_setup()
    domain_data: DomainData = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = runtime
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data: DomainData = hass.data.setdefault(DOMAIN, {})
    runtime = domain_data.pop(entry.entry_id, None)
    if runtime is not None:
        await runtime.async_unload()
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _build_runtime_config(entry: ConfigEntry) -> RuntimeConfig:
    raw = dict(entry.data)
    raw.update(entry.options)
    return RuntimeConfig(
        name=str(raw.get(CONF_NAME) or entry.title or "Reolink Doorbell Call").strip(),
        doorbell_entity_id=str(raw.get(CONF_DOORBELL_ENTITY_ID) or "").strip(),
        camera_entity_id=str(raw.get(CONF_CAMERA_ENTITY_ID) or "").strip(),
        notify_targets=_normalize_notify_targets(raw.get(CONF_NOTIFY_TARGETS)),
        notification_title=str(raw.get(CONF_NOTIFICATION_TITLE) or DEFAULT_NOTIFICATION_TITLE).strip(),
        notification_message=str(raw.get(CONF_NOTIFICATION_MESSAGE) or DEFAULT_NOTIFICATION_MESSAGE).strip(),
        open_action_title=str(raw.get(CONF_OPEN_ACTION_TITLE) or DEFAULT_OPEN_ACTION_TITLE).strip()
        or DEFAULT_OPEN_ACTION_TITLE,
        open_uri=str(raw.get(CONF_OPEN_URI) or "").strip(),
        notification_tag=str(raw.get(CONF_NOTIFICATION_TAG) or DEFAULT_NOTIFICATION_TAG).strip(),
        notification_timeout=max(1, int(raw.get(CONF_NOTIFICATION_TIMEOUT, DEFAULT_NOTIFICATION_TIMEOUT))),
        cooldown_seconds=max(0, int(raw.get(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS))),
        trigger_state=str(raw.get(CONF_TRIGGER_STATE) or DEFAULT_TRIGGER_STATE).strip() or DEFAULT_TRIGGER_STATE,
    )


def _normalize_notify_targets(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("\n", ",").split(",")

    targets: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if not text:
            continue
        if text.startswith("notify."):
            text = text.split(".", 1)[1]
        targets.append(text)
    return targets


def _build_panel_uri(camera_entity_id: str, title: str, entry_id: str) -> str:
    query = urlencode(
        {
            "camera_entity_id": camera_entity_id,
            "title": title,
            "entry_id": entry_id,
        }
    )
    return f"/{FRONTEND_PANEL_URL_PATH}?{query}"


async def _async_register_frontend(hass: HomeAssistant) -> None:
    if hass.data.setdefault(f"{DOMAIN}_frontend", False):
        return

    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_CARD_JS_URL,
                str(frontend_dir / f"{FRONTEND_CARD_TAG}.js"),
                cache_headers=False,
            ),
            StaticPathConfig(
                FRONTEND_PANEL_JS_URL,
                str(frontend_dir / f"{FRONTEND_PANEL_TAG}.js"),
                cache_headers=False,
            ),
        ]
    )
    frontend.add_extra_js_url(hass, FRONTEND_CARD_JS_URL)
    existing_panels = hass.data.setdefault(frontend.DATA_PANELS, {})
    if FRONTEND_PANEL_URL_PATH not in existing_panels:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=FRONTEND_PANEL_URL_PATH,
            webcomponent_name=FRONTEND_PANEL_TAG,
            sidebar_title="门铃接听",
            sidebar_icon="mdi:doorbell-video",
            module_url=FRONTEND_PANEL_JS_URL,
            config={
                "domain": DOMAIN,
                "default_panel_path": f"/{FRONTEND_PANEL_URL_PATH}",
                "static_base": FRONTEND_STATIC_BASE,
            },
        )
    hass.data[f"{DOMAIN}_frontend"] = True


async def _async_send_notify_message(
    hass: HomeAssistant,
    notify_target: str,
    title: str,
    message: str,
    data: dict[str, Any],
) -> None:
    service = str(notify_target or "").strip()
    if not service:
        return
    await hass.services.async_call(
        "notify",
        service,
        {
            "title": title,
            "message": message,
            "data": data,
        },
        blocking=True,
    )


async def _async_register_services(hass: HomeAssistant) -> None:
    if hass.data.setdefault(f"{DOMAIN}_services", False):
        return

    async def async_send_notification_service(call: ServiceCall) -> None:
        runtime = _get_runtime_from_service_call(hass, call)
        if runtime is None:
            return
        await runtime.async_send_notification()

    async def async_clear_notification_service(call: ServiceCall) -> None:
        runtime = _get_runtime_from_service_call(hass, call)
        if runtime is None:
            return
        await runtime.async_clear_notification()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_NOTIFICATION,
        async_send_notification_service,
        schema=vol.Schema({vol.Required(ATTR_ENTRY_ID): str}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_NOTIFICATION,
        async_clear_notification_service,
        schema=vol.Schema({vol.Required(ATTR_ENTRY_ID): str}),
    )
    hass.data[f"{DOMAIN}_services"] = True


def _get_runtime_from_service_call(hass: HomeAssistant, call: ServiceCall) -> DoorbellCallRuntime | None:
    entry_id = str(call.data.get(ATTR_ENTRY_ID) or "").strip()
    if not entry_id:
        return None
    domain_data: DomainData = hass.data.setdefault(DOMAIN, {})
    runtime = domain_data.get(entry_id)
    if runtime is None:
        _LOGGER.warning("未找到门铃通知运行时 | entry_id=%s", entry_id)
    return runtime
