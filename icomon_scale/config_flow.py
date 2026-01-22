import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_MAC, CONF_HEIGHT, CONF_AGE, CONF_GENDER

class IcomonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            user_input[CONF_MAC] = user_input[CONF_MAC].upper()
            return self.async_create_entry(title=f"体脂秤 ({user_input[CONF_MAC]})", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_MAC, default="FF:FF:10:CB:33:08"): str,
                vol.Required(CONF_HEIGHT, default=175): int,
                vol.Required(CONF_AGE, default=30): int,
                vol.Required(CONF_GENDER, default="male"): vol.In({"male": "男", "female": "女"}),
            })
        )