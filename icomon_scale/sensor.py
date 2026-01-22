import logging
import asyncio
from bleak import BleakClient
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.components.bluetooth import (
    async_register_callback,
    async_ble_device_from_address,
    BluetoothServiceInfoBleak,
    BluetoothScanningMode,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import UnitOfMass, EntityCategory, PERCENTAGE
from .const import DOMAIN, CONF_MAC, CONF_HEIGHT, CONF_AGE, CONF_GENDER

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    conf = config_entry.data
    mac = conf[CONF_MAC]
    
    # 实例化全套实体
    weight = WeightSensor(mac)
    impedance = ImpedanceSensor(mac)
    body_fat = BodyFatSensor(mac)
    physique = PhysiqueSensor(mac)
    status = StatusSensor(mac)
    
    async_add_entities([weight, impedance, body_fat, physique, status], False)
    
    # 启动管理器
    manager = IcomonManager(hass, mac, weight, impedance, body_fat, physique, status, conf)
    await manager.start_listening()

class IcomonManager:
    def __init__(self, hass, mac, weight, impedance, body_fat, physique, status, conf):
        self.hass = hass
        self.mac = mac
        self.weight = weight
        self.impedance = impedance
        self.body_fat = body_fat
        self.physique = physique
        self.status = status
        self.conf = conf
        self.is_connecting = False
        self._lock_event = asyncio.Event()
        self._stable_buffer = []

    async def start_listening(self):
        self.status.update_val("待机 (监听中)")
        async_register_callback(
            self.hass, self._handle_event,
            {"address": self.mac, "connectable": False},
            BluetoothScanningMode.ACTIVE 
        )

    def _handle_event(self, service_info, change):
        if not self.is_connecting:
            self.hass.async_create_task(self._connect())

    async def _connect(self):
        self.is_connecting = True
        self._lock_event.clear()
        self._stable_buffer = []
        client = None
        try:
            ble_device = async_ble_device_from_address(self.hass, self.mac, connectable=True)
            if not ble_device: self.is_connecting = False; return
            
            client = BleakClient(ble_device)
            await client.connect(timeout=15.0)
            if client.is_connected:
                # 寻找通道
                target_char = None
                write_char = None
                for s in client.services:
                    for c in s.characteristics:
                        if "notify" in c.properties: target_char = c.uuid
                        if "write" in c.properties: write_char = c.uuid
                
                if target_char:
                    await client.start_notify(target_char, self._handler)
                    if write_char:
                        await client.write_gatt_char(write_char, bytes.fromhex("FD37000000000000"), response=False)
                    
                    # 等待锁定或超时 (25秒)
                    try:
                        await asyncio.wait_for(self._lock_event.wait(), timeout=25.0)
                    except: pass
        except Exception as e:
            _LOGGER.error(f"连接错: {e}")
        finally:
            if client and client.is_connected: await client.disconnect()
            self.status.update_val("💤 冷却中")
            await asyncio.sleep(7)
            self.is_connecting = False
            self.status.update_val("等待上秤")

    def _handler(self, sender, data):
        if len(data) >= 6 and data[0] == 0xAC:
            # === 24位大整数克数算法 ===
            val_int = (data[3] << 16) | (data[4] << 8) | data[5]
            weight_kg = (val_int - 9175040) / 1000.0
            
            # 阻抗解析 (Byte 4-5 如果不溢出则是阻抗)
            raw_imp = (data[4] << 8) | data[5]
            impedance = raw_imp / 10.0 if raw_imp < 8000 else 0

            if weight_kg > 2.0:
                # 实时更新数值 (跳动效果)
                self.weight.update_val(weight_kg)
                self.status.update_val(f"称重中: {weight_kg}kg")
                
                # 稳定性判定
                self._stable_buffer.append(weight_kg)
                if len(self._stable_buffer) > 5: self._stable_buffer.pop(0)
                if len(self._stable_buffer) == 5 and max(self._stable_buffer) - min(self._stable_buffer) < 0.01:
                    # 锁定，执行体脂计算
                    self._calculate(weight_kg, impedance)
                    self._lock_event.set()

    def _calculate(self, weight, impedance):
        h = self.conf["height"]
        age = self.conf["age"]
        gender = 1 if self.conf["gender"] == "male" else 0
        
        bmi = weight / ((h/100)**2)
        # Deurenberg公式
        fat = (1.20 * bmi) + (0.23 * age) - (10.8 * gender) - 5.4
        
        state = "未知"
        if bmi < 18.5: state = "偏瘦"
        elif 18.5 <= bmi < 24: state = "标准"
        elif 24 <= bmi < 28: state = "超重"
        else: state = "肥胖"

        self.body_fat.update_val(max(0, round(fat, 1)))
        self.physique.update_val(state)
        self.impedance.update_val(impedance)
        self.status.update_val(f"✅ 已锁定: {weight}kg")

# ================= 实体定义 =================

class BaseSensor(SensorEntity):
    def __init__(self, mac):
        self._mac = mac
        self._state = None
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name="Icomon 智能体脂秤",
            manufacturer="Icomon",
            model="Smart Scale (Full Logic)",
        )
    @property
    def native_value(self): return self._state
    def update_val(self, val):
        self._state = val
        if self.hass and self.entity_id: self.schedule_update_ha_state()

class WeightSensor(BaseSensor):
    def __init__(self, mac):
        super().__init__(mac)
        self._attr_name = "体重"
        self._attr_unique_id = f"{mac}_weight"
        self._attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
        self._attr_device_class = SensorDeviceClass.WEIGHT
        self._attr_state_class = SensorStateClass.MEASUREMENT

class ImpedanceSensor(BaseSensor):
    def __init__(self, mac):
        super().__init__(mac)
        self._attr_name = "阻抗"
        self._attr_unique_id = f"{mac}_impedance"
        self._attr_native_unit_of_measurement = "Ω"

class BodyFatSensor(BaseSensor):
    def __init__(self, mac):
        super().__init__(mac)
        self._attr_name = "体脂率"
        self._attr_unique_id = f"{mac}_fat"
        self._attr_native_unit_of_measurement = PERCENTAGE

class PhysiqueSensor(BaseSensor):
    def __init__(self, mac):
        super().__init__(mac)
        self._attr_name = "身材评价"
        self._attr_unique_id = f"{mac}_physique"

class StatusSensor(BaseSensor):
    def __init__(self, mac):
        super().__init__(mac)
        self._attr_name = "连接状态"
        self._attr_unique_id = f"{mac}_status"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC