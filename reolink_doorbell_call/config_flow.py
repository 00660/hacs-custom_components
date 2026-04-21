from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
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
)


def _normalize_notify_targets(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("\n", ",").split(",")

    targets = []
    for item in raw_items:
        candidate = str(item or "").strip()
        if not candidate:
            continue
        if candidate.startswith("notify."):
            candidate = candidate.split(".", 1)[1]
        targets.append(candidate)
    return targets


def _build_notify_selector_options(hass: HomeAssistant, current_targets: list[str]) -> list[selector.SelectOptionDict]:
    options: dict[str, selector.SelectOptionDict] = {}
    notify_services = hass.services.async_services().get("notify", {})

    for service_name in notify_services:
        if not service_name.startswith("mobile_app_"):
            continue
        label = service_name.removeprefix("mobile_app_").replace("_", " ").strip() or service_name
        options[service_name] = selector.SelectOptionDict(
            value=service_name,
            label=f"{label} ({service_name})",
        )

    for service_name in current_targets:
        if service_name not in options:
            options[service_name] = selector.SelectOptionDict(
                value=service_name,
                label=service_name,
            )

    return list(options.values())


def _build_schema(hass: HomeAssistant, user_input: dict[str, Any] | None = None) -> vol.Schema:
    data = user_input or {}
    notify_targets = _normalize_notify_targets(data.get(CONF_NOTIFY_TARGETS, ""))
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=data.get(CONF_NAME, "Reolink Doorbell Call")): selector.TextSelector(),
            vol.Required(CONF_DOORBELL_ENTITY_ID, default=data.get(CONF_DOORBELL_ENTITY_ID, "")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Required(CONF_CAMERA_ENTITY_ID, default=data.get(CONF_CAMERA_ENTITY_ID, "")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="camera")
            ),
            vol.Required(
                CONF_NOTIFY_TARGETS,
                default=notify_targets,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_build_notify_selector_options(hass, notify_targets),
                    multiple=True,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    sort=True,
                )
            ),
            vol.Optional(
                CONF_NOTIFICATION_TITLE,
                default=data.get(CONF_NOTIFICATION_TITLE, DEFAULT_NOTIFICATION_TITLE),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_NOTIFICATION_MESSAGE,
                default=data.get(CONF_NOTIFICATION_MESSAGE, DEFAULT_NOTIFICATION_MESSAGE),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_OPEN_ACTION_TITLE,
                default=data.get(CONF_OPEN_ACTION_TITLE, DEFAULT_OPEN_ACTION_TITLE),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_OPEN_URI,
                default=data.get(CONF_OPEN_URI, ""),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_NOTIFICATION_TAG,
                default=data.get(CONF_NOTIFICATION_TAG, DEFAULT_NOTIFICATION_TAG),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_NOTIFICATION_TIMEOUT,
                default=data.get(CONF_NOTIFICATION_TIMEOUT, DEFAULT_NOTIFICATION_TIMEOUT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=300, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(
                CONF_COOLDOWN_SECONDS,
                default=data.get(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=600, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(
                CONF_TRIGGER_STATE,
                default=data.get(CONF_TRIGGER_STATE, DEFAULT_TRIGGER_STATE),
            ): selector.TextSelector(),
        }
    )


def _normalize_form_data(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_NOTIFY_TARGETS] = _normalize_notify_targets(data.get(CONF_NOTIFY_TARGETS, ""))
    data[CONF_OPEN_ACTION_TITLE] = str(data.get(CONF_OPEN_ACTION_TITLE, DEFAULT_OPEN_ACTION_TITLE)).strip()
    data[CONF_OPEN_URI] = str(data.get(CONF_OPEN_URI, "")).strip()
    data[CONF_NOTIFICATION_TIMEOUT] = int(data.get(CONF_NOTIFICATION_TIMEOUT, DEFAULT_NOTIFICATION_TIMEOUT))
    data[CONF_COOLDOWN_SECONDS] = int(data.get(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS))
    return data


class ReolinkDoorbellCallConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            if not _normalize_notify_targets(user_input.get(CONF_NOTIFY_TARGETS, "")):
                errors[CONF_NOTIFY_TARGETS] = "notify_targets_required"

            if not errors:
                normalized = _normalize_form_data(user_input)
                await self.async_set_unique_id(str(normalized[CONF_DOORBELL_ENTITY_ID]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=str(normalized.get(CONF_NAME) or normalized[CONF_DOORBELL_ENTITY_ID]),
                    data=normalized,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(self.hass, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ReolinkDoorbellCallOptionsFlow(config_entry)


class ReolinkDoorbellCallOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    def __init__(self, config_entry) -> None:
        super().__init__(config_entry)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            if not _normalize_notify_targets(user_input.get(CONF_NOTIFY_TARGETS, "")):
                errors[CONF_NOTIFY_TARGETS] = "notify_targets_required"

            if not errors:
                return self.async_create_entry(title="", data=_normalize_form_data(user_input))

        current = dict(self.config_entry.data)
        current.update(self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(self.hass, current),
            errors=errors,
        )
