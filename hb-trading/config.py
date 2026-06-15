"""项目配置 — 国内商品期货"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 路径
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ======================================================================
# 交易品种（国内期货 — 20品种，分5大类）
# ======================================================================

SYMBOLS = {
    # ---- 农产品 ----
    "m":  {"name": "豆粕",    "exchange": "DCE",  "lot_size": 10, "margin_per_lot": 2500},
    "RM": {"name": "菜粕",    "exchange": "CZCE", "lot_size": 10, "margin_per_lot": 2200},
    "c":  {"name": "玉米",    "exchange": "DCE",  "lot_size": 10, "margin_per_lot": 1500},
    "jd": {"name": "鸡蛋",    "exchange": "DCE",  "lot_size": 10, "margin_per_lot": 3500},
    "SR": {"name": "白糖",    "exchange": "CZCE", "lot_size": 10, "margin_per_lot": 4500},
    # ---- 化工 ----
    "MA": {"name": "甲醇",    "exchange": "CZCE", "lot_size": 10, "margin_per_lot": 1800},
    "PF": {"name": "短纤",    "exchange": "CZCE", "lot_size": 5,  "margin_per_lot": 2500},
    "TA": {"name": "PTA",     "exchange": "CZCE", "lot_size": 5,  "margin_per_lot": 2500},
    "EG": {"name": "乙二醇",  "exchange": "DCE",  "lot_size": 10, "margin_per_lot": 3500},
    "LU": {"name": "低硫燃油","exchange": "INE",  "lot_size": 10, "margin_per_lot": 5000},
    "EB": {"name": "苯乙烯",  "exchange": "DCE",  "lot_size": 5,  "margin_per_lot": 4000},
    # ---- 黑色 ----
    "RB": {"name": "螺纹钢",  "exchange": "SHFE", "lot_size": 10, "margin_per_lot": 3500},
    "HC": {"name": "热卷",    "exchange": "SHFE", "lot_size": 10, "margin_per_lot": 3500},
    "SS": {"name": "不锈钢",  "exchange": "SHFE", "lot_size": 5,  "margin_per_lot": 6000},
    # ---- 有色 ----
    "pb": {"name": "沪铅",    "exchange": "SHFE", "lot_size": 5,  "margin_per_lot": 6000},
    # ---- 其他 ----
    "SP": {"name": "纸浆",    "exchange": "SHFE", "lot_size": 10, "margin_per_lot": 4500},
    "FG": {"name": "玻璃",    "exchange": "CZCE", "lot_size": 20, "margin_per_lot": 3500},
    "CJ": {"name": "红枣",    "exchange": "CZCE", "lot_size": 5,  "margin_per_lot": 6000},
    "PK": {"name": "花生",    "exchange": "CZCE", "lot_size": 5,  "margin_per_lot": 4000},
}

CATEGORIES = {
    "农产品": ["m", "RM", "c", "jd", "SR"],
    "化工":   ["MA", "PF", "TA", "EG", "LU", "EB"],
    "黑色":   ["RB", "HC", "SS"],
    "有色":   ["pb"],
    "其他":   ["SP", "FG", "CJ", "PK"],
}

ALL_SYMBOLS = [s for g in CATEGORIES.values() for s in g]  # 保持分类顺序
PRIMARY_SYMBOL = "RB"          # 默认主做品种
BACKUP_SYMBOLS = [s for s in ALL_SYMBOLS if s != PRIMARY_SYMBOL]

# 主合约代码（AKShare 格式：上期所/大商所小写，郑商所/能源中心大写 + "0"）
MAIN_CONTRACT = {
    # 农产品
    "m": "m0", "RM": "RM0", "c": "c0", "jd": "jd0", "SR": "SR0",
    # 化工
    "MA": "MA0", "PF": "PF0", "TA": "TA0", "EG": "eg0", "LU": "LU0", "EB": "eb0",
    # 黑色
    "RB": "rb0", "HC": "hc0", "SS": "ss0",
    # 有色
    "pb": "pb0",
    # 其他
    "SP": "sp0", "FG": "FG0", "CJ": "CJ0", "PK": "PK0",
}

# ======================================================================
# 时间框架
# ======================================================================

TIMEFRAME_MAIN = "5m"             # 主交易时间框架（阿布推荐5分钟）
TIMEFRAMES = {"1m": "1分钟", "5m": "5分钟", "30m": "30分钟", "daily": "日线", "weekly": "周线"}
TIMEFRAME_CONTEXT = "daily"       # 更高时间框架（判断大方向）

# ======================================================================
# K线采集
# ======================================================================

LOOKBACK_DAYS = 7000            # 历史数据拉取天数（17年）
POLL_INTERVAL_MINUTES = 30     # 轮询间隔（分钟）

# ======================================================================
# 数据质量
# ======================================================================

PRICE_CHANGE_WARN_PCT = 5.0    # 单日涨跌幅超过此值告警
VOLUME_SPIKE_MULTIPLIER = 3.0  # 成交量超过均值的倍数告警
DATA_FRESHNESS_HOURS = 24      # 超过此时间无新数据视为延迟
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

# ======================================================================
# 国内期货特有情绪指标
# ======================================================================

# 基差阈值（现货-期货 / 现货 %）
BASIS_POSITIVE_THRESHOLD = 3.0    # 正基差超过3% = 现货紧张 = 偏多
BASIS_NEGATIVE_THRESHOLD = -3.0   # 负基差超过3% = 现货宽松 = 偏空

# 仓单变化阈值
WAREHOUSE_INCREASE_THRESHOLD = 10  # 仓单增加超过10% = 库存压力 = 偏空
WAREHOUSE_DECREASE_THRESHOLD = -10 # 仓单减少超过10% = 库存去化 = 偏多

# ======================================================================
# 信号
# ======================================================================

SIGNAL_THRESHOLD_BUY = 70
SIGNAL_THRESHOLD_SELL = 30

# ======================================================================
# 风险管理（逐仓模式）
# ======================================================================

INITIAL_CAPITAL = 10000         # 初始资金
MAX_LEVERAGE = 3                # 最大杠杆
MAX_SINGLE_LOSS_PCT = 2.0       # 单笔最大亏损占资金比例%
DEFAULT_POSITION_PCT = 20.0     # 单笔投入资金比例%

# ======================================================================
# 通知
# ======================================================================

SERVERCHAN_KEY = "SCT362455TAW1JnZODnSX5lHkPH06sQUyY"
NOTIFY_ENABLED = True
NOTIFY_MIN_INTERVAL_MINUTES = 30  # 同品种最小通知间隔

# ======================================================================
# 手续费（螺纹钢为例，万分之1）
# ======================================================================

COMMISSION_RATE = 0.0001         # 手续费率（万分之1）
MIN_COMMISSION = 3.0             # 最低手续费（元）

# ======================================================================
# 模拟交易 (Paper Trading)
# ======================================================================

PAPER_INITIAL_BALANCE = 100000.0  # 模拟交易初始资金
PAPER_SLIPPAGE_PCT = 0.0002      # 模拟滑点 0.02%

# ======================================================================
# 日志
# ======================================================================

LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_LEVEL = "INFO"

# ======================================================================
# A股扫描管线
# ======================================================================

A_SHARE_SCAN_MIN_PRICE = 3.0
A_SHARE_SCAN_MAX_PRICE = 200.0
A_SHARE_TOP_N = 200
A_SHARE_COMMITTEE_TOP = 5
A_SHARE_SCAN_TIMEFRAME = "daily"
A_SHARE_POOL_WATCHLIST = []
A_SHARE_OUTPUT_DIR = PROJECT_ROOT / "output" / "daily"
OUTPUT_BASE = A_SHARE_OUTPUT_DIR  # compat alias

# A-share index codes for market overview
INDEX_CODES = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
    "科创50": "sh000688",
}

# Afternoon report thresholds
ZT_MIN_BOARDS_FOR_TIER = 3
SECTOR_STRONG_THRESHOLD = 2.0
SECTOR_TOP_N = 5
SECTOR_BOTTOM_N = 5

# Theme colors for reports
COLORS = {
    "buy": "#00C853",
    "sell": "#FF1744",
    "hold": "#FFD600",
    "bg_dark": "#1a1a2e",
    "card": "#16213e",
    "text": "#e0e0e0",
    "accent": "#0f3460",
}

# ======================================================================
# 飞书
# ======================================================================

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_WEBHOOK_MORNING = os.getenv("FEISHU_WEBHOOK_MORNING", "")
FEISHU_WEBHOOK_AFTERNOON = os.getenv("FEISHU_WEBHOOK_AFTERNOON", "")
FEISHU_WEBHOOK_REVIEW = os.getenv("FEISHU_WEBHOOK_REVIEW", "")
FEISHU_DOC_FOLDER = os.getenv("FEISHU_DOC_FOLDER", "")
FEISHU_WEBHOOK_AM = FEISHU_WEBHOOK_MORNING   # compat
FEISHU_WEBHOOK_PM = FEISHU_WEBHOOK_AFTERNOON  # compat

# ======================================================================
# 小红书抓取
# ======================================================================

XHS_BROWSER_CHANNEL = "chromium"
XHS_HEADLESS = False
XHS_VIEWPORT_WIDTH = 1400
XHS_VIEWPORT_HEIGHT = 900
XHS_SCROLL_DELAY_MIN = 1.0
XHS_SCROLL_DELAY_MAX = 3.0
XHS_PAGE_TIMEOUT = 30_000
XHS_COMMENT_API_TIMEOUT = 15_000
XHS_MAX_COMMENTS = 500
XHS_MAX_SUB_COMMENTS = 100
XHS_MAX_AUTHOR_NOTES = 50
XHS_AUTHOR_DELAY_MIN = 4.0
XHS_AUTHOR_DELAY_MAX = 8.0
XHS_AUTHOR_SCROLL_PAGES = 15
XHS_SCRAPER_OUTPUT_DIR = PROJECT_ROOT / "output" / "scraper"

# ======================================================================
# 图片生成
# ======================================================================

IMAGE_CANVAS_SIZES = {
    "portrait": (1080, 1440),
    "square": (1080, 1080),
    "full": (1080, 1920),
}
IMAGE_OUTPUT_DIR = PROJECT_ROOT / "output" / "images"

# image_gen compat
SIZE_FEED = (1080, 1440)
SIZE_COVER = (1080, 1080)
SIZE_STORY = (1080, 1920)
FONT_DIR = "fonts"

THEMES = {
    "dark_pro": {
        "bg": "#1a1a2e", "title": "#e94560", "text": "#f0f0f0",
        "accent": "#16213e", "highlight": "#0f3460",
    },
    "light_clean": {
        "bg": "#ffffff", "title": "#2d3436", "text": "#636e72",
        "accent": "#dfe6e9", "highlight": "#0984e3",
    },
    "warm": {
        "bg": "#fff5e6", "title": "#c0392b", "text": "#2c3e50",
        "accent": "#f39c12", "highlight": "#e74c3c",
    },
    "trading": {
        "bg": "#0d1117", "title": "#58a6ff", "text": "#c9d1d9",
        "accent": "#21262d", "highlight": "#3fb950",
        "red": "#f85149", "green": "#3fb950",
    },
}
