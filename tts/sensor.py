import base64, json, logging
from datetime import datetime, timezone
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, CONF_TOKEN, CONF_ENGINE, ENGINE_ZAI

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    if entry.data.get(CONF_ENGINE, ENGINE_ZAI) == ENGINE_ZAI: async_add_entities([ZaiTokenSensor(entry)])

class ZaiTokenSensor(SensorEntity):
    _attr_has_entity_name, _attr_name, _attr_native_unit_of_measurement, _attr_state_class = True, "Token Remaining", "d", SensorStateClass.MEASUREMENT
    def __init__(self, entry):
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_token_days_left"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": "Z.ai TTS"}
    @property
    def native_value(self):
        try:
            token = self._entry.data.get(CONF_TOKEN, "")
            p = token.split(".")[1]
            p += "=" * ((4 - len(p) % 4) % 4)
            d = json.loads(base64.b64decode(p).decode("utf-8"))
            if "exp" in d: return max(0, int((d["exp"] - datetime.now(timezone.utc).timestamp()) / 86400))
        except: pass
        return None