import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import DOMAIN

class SmartBillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """处理初始添加"""
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartBillOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title=user_input["name"], data=user_input)

        return self.async_show_form(
            step_id="user", 
            data_schema=vol.Schema({
                vol.Required("name", default="My Home"): str,
                vol.Required("power_entity"): EntitySelector(
                    EntitySelectorConfig(domain="sensor")
                ),
            }), 
            errors=errors
        )

class SmartBillOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """管理选项：重新配置实体 + 校准功能"""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # 获取当前值
        current_power = self.config_entry.options.get(
            "power_entity", self.config_entry.data.get("power_entity")
        )
        current_offset = self.config_entry.options.get("energy_offset", 0.0)
        current_balance_init = self.config_entry.options.get("initial_balance", 0.0)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("power_entity", default=current_power): EntitySelector(
                    EntitySelectorConfig(domain="sensor")
                ),
                # [新增] 电量校准
                vol.Optional("energy_offset", default=current_offset): NumberSelector(
                    NumberSelectorConfig(mode=NumberSelectorMode.BOX, step=0.01, unit_of_measurement="kWh")
                ),
                # [新增] 初始余额设定 (注意：只会生效一次，后续通过服务充值)
                vol.Optional("initial_balance", default=current_balance_init): NumberSelector(
                    NumberSelectorConfig(mode=NumberSelectorMode.BOX, step=0.1, unit_of_measurement="CNY")
                ),
            })
        )