DOMAIN = "zai_tts"

# 引擎选择
CONF_ENGINE = "engine"
ENGINE_ZAI = "zai"
ENGINE_QWEN = "qwen"

# Z.ai 专用设置键
CONF_TOKEN = "token"
CONF_USER_ID = "user_id"
CONF_VOICE_ID = "voice_id"
CONF_SPEED = "speed"
CONF_SMOOTHING = "smoothing"
CONF_CONCURRENT = "concurrent"
CONF_MAX_CONCURRENCY = "max_concurrency"
CONF_CUSTOM_VOICES_DICT = "custom_voices_dict"

# Qwen 专用设置键
CONF_QWEN_URL = "qwen_url"
CONF_QWEN_VOICE = "qwen_voice"

# 默认值
DEFAULT_VOICE = "system_001"
DEFAULT_SPEED = 1.0
DEFAULT_SMOOTHING = 15
DEFAULT_QWEN_URL = "https://qwen-qwen3-tts-demo.ms.show"
DEFAULT_QWEN_VOICE = "Vivian / 十三"

# Z.ai 官方内置角色表
VOICE_MAP = {
    "system_001": "活泼女声",
    "system_003": "通用男声",
    "system_002": "温柔女声",
}

# Qwen 角色列表
QWEN_VOICES = [
    "Serena / 苏瑶",
    "Ethan / 晨煦",
    "Chelsie / 千雪",
    "Momo / 茉兔",
    "Vivian / 十三",
    "Moon / 月白",
    "Maia / 四月",
    "Kai / 凯",
    "Nofish / 不吃鱼",
    "Bella / 萌宝",
    "Jennifer / 詹妮弗",
    "Ryan / 甜茶",
    "Katerina / 卡捷琳娜",
    "Aiden / 艾登",
    "Bodega / 西班牙语-博德加",
    "Alek / 俄语-阿列克",
    "Dolce / 意大利语-多尔切",
    "Sohee / 韩语-素熙"
]