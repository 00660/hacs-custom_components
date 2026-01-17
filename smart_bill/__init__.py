import logging
import os
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

# 目标图标 URL (偷网上国网的图)
ICON_URL = "https://brands.home-assistant.io/state_grid/icon.png"

async def async_setup(hass: HomeAssistant, config: dict):
    """YAML 配置入口 (兼顾初始化任务)"""
    # 启动后台任务：自动检查并下载图标
    hass.async_create_task(auto_download_icon(hass))
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """UI 配置入口"""
    entry.async_on_unload(entry.add_update_listener(update_listener))
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # 注册充值服务
    async def handle_recharge(call: ServiceCall):
        entity_id = call.data.get("entity_id")
        amount = call.data.get("amount")
        component = hass.data.get("entity_components", {}).get("sensor")
        if component:
            entity = component.get_entity(entity_id)
            if entity and hasattr(entity, "recharge"):
                await entity.recharge(amount)

    hass.services.async_register(DOMAIN, "recharge", handle_recharge)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """卸载集成"""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """重载集成"""
    await hass.config_entries.async_reload(entry.entry_id)

async def auto_download_icon(hass: HomeAssistant):
    """down www """
    target_dir = hass.config.path("www", "brands", DOMAIN)
    target_file = os.path.join(target_dir, "icon.png")

    if os.path.exists(target_file):
        return

    _LOGGER.info(f"正在自动下载集成图标到: {target_file}")

    try:
        if not os.path.exists(target_dir):
            await hass.async_add_executor_job(os.makedirs, target_dir)

        # 4. 开始下载
        session = async_get_clientsession(hass)
        async with session.get(ICON_URL) as response:
            if response.status == 200:
                data = await response.read()
                # 5. 写入文件 (使用 executor 防止阻塞主线程)
                def write_file():
                    with open(target_file, "wb") as f:
                        f.write(data)
                await hass.async_add_executor_job(write_file)
                _LOGGER.info("图标下载成功！请强制刷新浏览器查看。")
            else:
                _LOGGER.warning(f"图标下载失败，HTTP状态码: {response.status}")
    except Exception as e:
        _LOGGER.error(f"自动下载图标时出错: {e}")