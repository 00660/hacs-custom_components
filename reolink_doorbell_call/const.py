from __future__ import annotations

DOMAIN = "reolink_doorbell_call"
FRONTEND_CARD_TAG = "reolink-doorbell-call-card"
FRONTEND_PANEL_TAG = "reolink-doorbell-call-panel"
FRONTEND_PANEL_URL_PATH = "reolink-doorbell-call"
FRONTEND_STATIC_BASE = f"/api/{DOMAIN}"
FRONTEND_CARD_JS_URL = f"{FRONTEND_STATIC_BASE}/{FRONTEND_CARD_TAG}.js"
FRONTEND_PANEL_JS_URL = f"{FRONTEND_STATIC_BASE}/{FRONTEND_PANEL_TAG}.js"

CONF_CAMERA_ENTITY_ID = "camera_entity_id"
CONF_COOLDOWN_SECONDS = "cooldown_seconds"
CONF_DOORBELL_ENTITY_ID = "doorbell_entity_id"
CONF_NOTIFICATION_MESSAGE = "notification_message"
CONF_OPEN_ACTION_TITLE = "open_action_title"
CONF_OPEN_URI = "open_uri"
CONF_NOTIFICATION_TAG = "notification_tag"
CONF_NOTIFICATION_TIMEOUT = "notification_timeout"
CONF_NOTIFICATION_TITLE = "notification_title"
CONF_NOTIFY_TARGETS = "notify_targets"
CONF_TRIGGER_STATE = "trigger_state"

DEFAULT_COOLDOWN_SECONDS = 10
DEFAULT_NOTIFICATION_MESSAGE = "有人按门铃"
DEFAULT_OPEN_ACTION_TITLE = "接听"
DEFAULT_NOTIFICATION_TAG = "reolink-doorbell-call"
DEFAULT_NOTIFICATION_TIMEOUT = 30
DEFAULT_NOTIFICATION_TITLE = "门铃"
DEFAULT_TRIGGER_STATE = "on"

EVENT_HANGUP_PRESSED = f"{DOMAIN}_hangup_pressed"

SERVICE_CLEAR_NOTIFICATION = "clear_notification"
SERVICE_SEND_NOTIFICATION = "send_notification"

ATTR_ENTRY_ID = "entry_id"
