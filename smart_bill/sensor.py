import logging
import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import (
    UnitOfPower,
    UnitOfEnergy,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.core import callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """UI 配置入口"""
    power_entity = config_entry.options.get("power_entity", config_entry.data.get("power_entity"))
    energy_offset = config_entry.options.get("energy_offset", 0.0)
    initial_balance = config_entry.options.get("initial_balance", 0.0)
    name = config_entry.data.get("name")

    manager = SmartBillManager(hass, name, power_entity, config_entry.entry_id, energy_offset, initial_balance)
    
    async_add_entities([
        manager.sensor_power,
        manager.sensor_price,
        manager.sensor_balance,
        manager.sensor_total_energy,
        manager.sensor_energy_peak,    # [新增] 峰电
        manager.sensor_energy_valley,  # [新增] 谷电
        manager.sensor_energy_today,
        manager.sensor_cost_today,
        manager.sensor_energy_yesterday,
        manager.sensor_cost_yesterday,
        manager.sensor_energy_month,
        manager.sensor_cost_month,
        manager.sensor_energy_year,
        manager.sensor_cost_year,
    ])

class SmartBillManager:
    def __init__(self, hass, name, power_entity, entry_id, energy_offset, initial_balance):
        self.hass = hass
        self.power_entity = power_entity
        self.energy_offset = energy_offset
        self.initial_balance = initial_balance
        self.last_update = dt_util.now()
        self.last_power = 0.0
        
        self.common_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=name,
            manufacturer="DIY",
            model="智能电费计算器",
        )
        
        # 1. 实时功率
        self.sensor_power = BillSensor(
            name + " ⚡ 实时功率", 
            UnitOfPower.WATT, 
            "mdi:flash-outline", 
            SensorDeviceClass.POWER, 
            SensorStateClass.MEASUREMENT, 
            self.common_device_info, 
            f"{entry_id}_power"
        )

        # 2. 当前电价
        self.sensor_price = BillSensor(
            name + " 💰 当前电价", 
            "CNY/kWh", 
            "mdi:cash-multiple", 
            None, 
            None, 
            self.common_device_info, 
            f"{entry_id}_price"
        )
        
        # 3. 电费余额
        self.sensor_balance = BalanceSensor(
            name + " 💳 电费余额", 
            "CNY", 
            "mdi:wallet-outline", 
            SensorDeviceClass.MONETARY, 
            SensorStateClass.TOTAL, 
            self.common_device_info, 
            f"{entry_id}_balance", 
            initial_balance
        )
        
        # 4. 电表总读数
        self.sensor_total_energy = BillSensor(
            name + " 📟 电表总读数", 
            UnitOfEnergy.KILO_WATT_HOUR, 
            "mdi:counter", 
            SensorDeviceClass.ENERGY, 
            SensorStateClass.TOTAL, 
            self.common_device_info, 
            f"{entry_id}_total_reading"
        )
        self.sensor_total_energy.set_initial_offset(energy_offset)

        # --- [新增] 峰谷电量统计 (按月重置) ---
        self.sensor_energy_peak = BillSensor(
            name + " ☀️ 本月峰电", 
            UnitOfEnergy.KILO_WATT_HOUR, 
            "mdi:weather-sunny", 
            SensorDeviceClass.ENERGY, 
            SensorStateClass.TOTAL, 
            self.common_device_info, 
            f"{entry_id}_e_peak"
        )
        self.sensor_energy_valley = BillSensor(
            name + " 🌙 本月谷电", 
            UnitOfEnergy.KILO_WATT_HOUR, 
            "mdi:weather-night", 
            SensorDeviceClass.ENERGY, 
            SensorStateClass.TOTAL, 
            self.common_device_info, 
            f"{entry_id}_e_valley"
        )

        # 7-12. 常规统计数据
        self.sensor_energy_today = BillSensor(name + " 📅 今日电量", UnitOfEnergy.KILO_WATT_HOUR, "mdi:battery-clock-outline", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, self.common_device_info, f"{entry_id}_e_today")
        self.sensor_cost_today = BillSensor(name + " 💸 今日电费", "CNY", "mdi:currency-cny", SensorDeviceClass.MONETARY, SensorStateClass.TOTAL, self.common_device_info, f"{entry_id}_c_today")
        self.sensor_energy_yesterday = BillSensor(name + " ⏮️ 昨日电量", UnitOfEnergy.KILO_WATT_HOUR, "mdi:history", SensorDeviceClass.ENERGY, None, self.common_device_info, f"{entry_id}_e_yest")
        self.sensor_cost_yesterday = BillSensor(name + " 📉 昨日电费", "CNY", "mdi:currency-cny", SensorDeviceClass.MONETARY, None, self.common_device_info, f"{entry_id}_c_yest")
        self.sensor_energy_month = BillSensor(name + " 🗓️ 本月电量", UnitOfEnergy.KILO_WATT_HOUR, "mdi:calendar-month", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, self.common_device_info, f"{entry_id}_e_month")
        self.sensor_cost_month = BillSensor(name + " 💴 本月电费", "CNY", "mdi:currency-cny", SensorDeviceClass.MONETARY, SensorStateClass.TOTAL, self.common_device_info, f"{entry_id}_c_month")
        self.sensor_energy_year = BillSensor(name + " 📆 本年电量", UnitOfEnergy.KILO_WATT_HOUR, "mdi:calendar-today", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, self.common_device_info, f"{entry_id}_e_year")
        self.sensor_cost_year = BillSensor(name + " 🏦 本年电费", "CNY", "mdi:currency-cny", SensorDeviceClass.MONETARY, SensorStateClass.TOTAL, self.common_device_info, f"{entry_id}_c_year")

        async_track_state_change_event(hass, power_entity, self._on_power_change)

    @callback
    def _on_power_change(self, event):
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ["unknown", "unavailable"]:
            self.sensor_power.set_value(0.0)
            return

        try:
            current_power = float(new_state.state)
            unit = new_state.attributes.get("unit_of_measurement")
            if unit == UnitOfPower.KILO_WATT:
                current_power *= 1000.0
        except ValueError:
            return

        self.sensor_power.set_value(current_power)
        now = dt_util.now()
        self._check_reset(now)

        time_diff = (now - self.last_update).total_seconds()
        if time_diff > 0:
            energy_increment = ((self.last_power + current_power) / 2) * (time_diff / 3600.0) / 1000.0
            
            # --- [核心逻辑] 判断峰谷并分流 ---
            hour = now.hour
            is_peak = 7 <= hour < 23
            
            # 峰谷电量累加
            if is_peak:
                self.sensor_energy_peak.add_value(energy_increment)
            else:
                self.sensor_energy_valley.add_value(energy_increment)
            # -------------------------------

            current_price = self._calculate_price(now, self.sensor_energy_month.native_value)
            self.sensor_price.set_value(current_price)

            cost_increment = energy_increment * current_price

            self.sensor_balance.deduct(cost_increment)
            self.sensor_total_energy.add_value(energy_increment)

            self.sensor_energy_today.add_value(energy_increment)
            self.sensor_cost_today.add_value(cost_increment)
            self.sensor_energy_month.add_value(energy_increment)
            self.sensor_cost_month.add_value(cost_increment)
            self.sensor_energy_year.add_value(energy_increment)
            self.sensor_cost_year.add_value(cost_increment)

        self.last_update = now
        self.last_power = current_power

    def _check_reset(self, now):
        last = self.last_update
        
        if now.date() > last.date():
            self.sensor_energy_yesterday.set_value(self.sensor_energy_today.native_value)
            self.sensor_cost_yesterday.set_value(self.sensor_cost_today.native_value)
            self.sensor_energy_today.set_value(0.0)
            self.sensor_cost_today.set_value(0.0)

        if now.month != last.month or now.year != last.year:
            self.sensor_energy_month.set_value(0.0)
            self.sensor_cost_month.set_value(0.0)
            # [新增] 跨月时清零峰谷统计
            self.sensor_energy_peak.set_value(0.0)
            self.sensor_energy_valley.set_value(0.0)

        if now.year != last.year:
            self.sensor_energy_year.set_value(0.0)
            self.sensor_cost_year.set_value(0.0)

    def _calculate_price(self, now, month_usage):
        hour = now.hour
        month = now.month
        
        is_peak = 7 <= hour < 23
        is_summer = 6 <= month <= 10

        base_p = 0.5224
        valley_p = 0.175 if is_summer else 0.2535
        
        tier_adder = 0.0
        if 180 < month_usage <= 280:
            tier_adder = 0.1
        elif month_usage > 280:
            tier_adder = 0.3
            
        final_price = (base_p if is_peak else valley_p) + tier_adder
        return round(final_price, 4)


class BillSensor(RestoreEntity, SensorEntity):
    def __init__(self, name, unit, icon, device_class, state_class, device_info, unique_id):
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_device_info = device_info
        self._attr_unique_id = unique_id
        self._attr_native_value = 0.0
        self._initial_offset_applied = False

    def set_initial_offset(self, offset):
        self._initial_offset = offset

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = float(state.state)
                self._initial_offset_applied = True
            except ValueError:
                pass
        
        if not self._initial_offset_applied and hasattr(self, '_initial_offset') and self._initial_offset > 0:
             self._attr_native_value = self._initial_offset
             self._initial_offset_applied = True

    def add_value(self, value):
        self._attr_native_value += value
        self.async_write_ha_state()

    def set_value(self, value):
        self._attr_native_value = value
        self.async_write_ha_state()


class BalanceSensor(BillSensor):
    def __init__(self, name, unit, icon, device_class, state_class, device_info, unique_id, initial_balance):
        super().__init__(name, unit, icon, device_class, state_class, device_info, unique_id)
        self._initial_balance_config = initial_balance
    
    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self._attr_native_value == 0.0 and self._initial_balance_config > 0:
             self._attr_native_value = self._initial_balance_config

    def deduct(self, amount):
        self._attr_native_value -= amount
        self.async_write_ha_state()

    async def recharge(self, amount):
        self._attr_native_value += float(amount)
        self.async_write_ha_state()