"""小红书配图生成器"""

from dataclasses import dataclass, field
from typing import Optional

# 画布规格
SIZE_FEED = (1080, 1440)     # 标准图文 3:4
SIZE_COVER = (1080, 1080)    # 封面 1:1
SIZE_STORY = (1080, 1920)    # 故事/长图 9:16

# 默认配色
THEMES = {
    "dark_pro": {   # 专业暗色
        "bg": "#1a1a2e",
        "title": "#e94560",
        "text": "#f0f0f0",
        "accent": "#16213e",
        "highlight": "#0f3460",
    },
    "light_clean": {  # 简洁白
        "bg": "#ffffff",
        "title": "#2d3436",
        "text": "#636e72",
        "accent": "#dfe6e9",
        "highlight": "#0984e3",
    },
    "warm": {         # 暖色调
        "bg": "#fff5e6",
        "title": "#c0392b",
        "text": "#2c3e50",
        "accent": "#f39c12",
        "highlight": "#e74c3c",
    },
    "trading": {      # 交易主题
        "bg": "#0d1117",
        "title": "#58a6ff",
        "text": "#c9d1d9",
        "accent": "#21262d",
        "highlight": "#3fb950",
        "red": "#f85149",
        "green": "#3fb950",
    },
}

# 字体路径（用户放入 fonts/ 目录）
FONT_DIR = "fonts"
