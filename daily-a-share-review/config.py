"""每日A股复盘 — 配置"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── 飞书 ──
FEISHU_WEBHOOK_AM = os.getenv("FEISHU_WEBHOOK_AM", "") or os.getenv("FEISHU_WEBHOOK", "")
FEISHU_WEBHOOK_PM = os.getenv("FEISHU_WEBHOOK_PM", "") or os.getenv("FEISHU_WEBHOOK", "")

# ── 主要指数 ──
INDEX_CODES = {
    "上证指数": "000001",
    "深证成指": "399001",
    "创业板指": "399006",
    "科创50":  "000688",
}

# ── 全球指数（AKShare symbol） ──
GLOBAL_INDEX_CODES = {
    "道琼斯":    "DJIA",
    "纳斯达克":  "IXIC",
    "标普500":   "SPX",
    "恒生指数":  "HSI",
    "富时A50":   "XIN9",
}

# ── 商品/汇率 ──
COMMODITY_CODES = {
    "离岸人民币": "USDCNH",
    "NYMEX原油":  "CL00Y",
    "COMEX黄金":  "GC00Y",
}

# ── 涨停分析阈值 ──
ZT_MIN_BOARDS_FOR_TIER = 2       # 连板≥2才进入梯队
SECTOR_STRONG_THRESHOLD = 3       # 涨停数≥3 = 主线题材
SECTOR_WEAK_THRESHOLD = 1         # 涨停数=1-2 = 支线/一日游

# ── 行业板块数量 ──
SECTOR_TOP_N = 8                  # 涨幅榜Top N
SECTOR_BOTTOM_N = 5               # 跌幅榜Top N

# ── 输出目录 ──
OUTPUT_BASE = "output"

# ── 长图配色（深色金融风）──
COLORS = {
    "bg":           "#0d1117",
    "card_bg":      "#161b22",
    "border":       "#21262d",
    "text_primary": "#e6edf3",
    "text_secondary": "#8b949e",
    "green":        "#3fb950",
    "red":          "#f85149",
    "accent":       "#58a6ff",
    "accent_warn":  "#d29922",
    "accent_purple": "#a371f7",
}

# ═══════════════════════════════════════════════
# PA（价格行为学）筛选 & 信号阈值
# ═══════════════════════════════════════════════

# ── 硬过滤 ──
PA_MIN_AVG_AMOUNT = 50_000_000         # 近20日均成交额 ≥ 5000万
PA_MIN_LISTING_DAYS = 250              # 上市天数 ≥ 250 交易日
PA_MAX_LIMIT_HITS_20D = 1              # 近20日碰板次数 ≤ 1
PA_MIN_DISTANCE_FROM_LIMIT = 3.0       # 距涨跌停板 ≥ 3%

# ── PA 适合度评分权重 ──
PA_WEIGHT_LIQUIDITY = 25               # 流动性质量
PA_WEIGHT_VOLATILITY = 20              # 波动稳定性
PA_WEIGHT_TREND = 25                   # 趋势持续性
PA_WEIGHT_STRUCTURE = 20               # 结构清晰度
PA_WEIGHT_AWAY_LIMIT = 10              # 远离涨跌停

# ── 筛选/信号门槛 ──
PA_SCREEN_TOP_N = 250                  # 筛选后保留标的数量
PA_SIGNAL_MIN_SCORE = 60               # 最低推送技术评分
PA_SIGNAL_TOP_N = 15                   # 每时段最多推送数量
PA_MIN_RR_RATIO = 2.0                  # 最低盈亏比

# ── 运行时段 ──
PA_SESSIONS = {
    "morning": {"hour": 9, "minute": 0, "label": "盘前精选"},
    "noon":    {"hour": 11, "minute": 30, "label": "午间扫描"},
    "evening": {"hour": 15, "minute": 30, "label": "收盘复盘"},
}
