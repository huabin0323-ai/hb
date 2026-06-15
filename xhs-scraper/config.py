"""xhs-scraper 配置"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ======================================================================
# 浏览器配置
# ======================================================================

# 专用 Playwright profile（不和正在运行的 Edge 冲突）
EDGE_USER_DATA = os.path.expandvars(
    r"%LOCALAPPDATA%\xhs-scraper-browser-profile"
)
# 备用：尝试复用主 Edge profile 的 cookies
EDGE_MAIN_PROFILE = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\Edge\User Data"
)
BROWSER_CHANNEL = "msedge"            # 使用本机 Edge
HEADLESS = False                       # 小红书反headless，暂用可见模式
VIEWPORT_WIDTH = 1400
VIEWPORT_HEIGHT = 900

# ======================================================================
# 反爬参数
# ======================================================================
SCROLL_DELAY_MIN = 1.0                 # 最小滚动间隔(秒)
SCROLL_DELAY_MAX = 3.0                 # 最大滚动间隔
SCROLL_DISTANCE_MIN = 200              # 最小滚动距离(px)
SCROLL_DISTANCE_MAX = 600              # 最大滚动距离
PAGE_TIMEOUT = 30_000                  # 页面加载超时(ms)
COMMENT_API_TIMEOUT = 15_000           # 评论API超时(ms)

# ======================================================================
# 评论爬取
# ======================================================================
MAX_COMMENTS = 500                     # 最多拉取评论数
MAX_SUB_COMMENTS = 100                 # 每条评论最多拉取二级回复

# ======================================================================
# 输出
# ======================================================================
CONTENT_FILENAME = "content.md"
RAW_FILENAME = "raw.json"
SUMMARY_FILENAME = "summary.md"

# ======================================================================
# 作者级爬取
# ======================================================================
MAX_AUTHOR_NOTES = 50                   # 每位作者最多抓取笔记数
AUTHOR_DELAY_MIN = 4.0                  # 笔记间最小延迟(秒)
AUTHOR_DELAY_MAX = 8.0                  # 笔记间最大延迟(秒)
AUTHOR_SCROLL_PAGES = 15                # 作者主页最大翻页轮次
USER_POSTED_PAGE_SIZE = 30              # 每页笔记数
