"""浏览器管理 — 独立窗口 + cookie 持久化，不影响你正在用的 Edge"""
import random
import logging
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from .config import (
    BROWSER_CHANNEL, HEADLESS,
    VIEWPORT_WIDTH, VIEWPORT_HEIGHT,
)

logger = logging.getLogger("browser")

COOKIE_FILE = Path(__file__).parent.parent / "output" / ".xhs_cookies.json"

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {
    get: () => { const arr = [1,2,3,4,5]; arr.item = i => arr[i]; arr.namedItem = () => null; arr.refresh = () => {}; return arr; }
});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
window.chrome = { runtime:{}, loadTimes:function(){}, csi:function(){}, app:{} };
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) => (
    p.name === 'notifications' ? Promise.resolve({state:Notification.permission}) : origQuery(p)
);
"""


def create_browser():
    """启动独立 Playwright 浏览器，加载已保存 cookie，不影响你正在用的 Edge"""
    pw = sync_playwright().start()

    storage_state = None
    if COOKIE_FILE.exists():
        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                storage_state = json.load(f)
            logger.info(f"已加载cookie: {len(storage_state.get('cookies',[]))}条")
        except Exception:
            pass

    w = VIEWPORT_WIDTH + random.randint(-50, 50)
    h = VIEWPORT_HEIGHT + random.randint(-30, 30)

    browser = pw.chromium.launch(
        channel=BROWSER_CHANNEL,
        headless=HEADLESS,
    )

    context = browser.new_context(
        viewport={"width": w, "height": h},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        storage_state=storage_state,
    )

    page = context.new_page()
    page.add_init_script(STEALTH_SCRIPT)

    logger.info(f"浏览器已启动: viewport={w}x{h} cookie={'有' if storage_state else '无'}")
    return pw, browser, context, page


def save_cookies(context: BrowserContext):
    if context is None:
        return
    state = context.storage_state()
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    logger.info(f"Cookie已保存: {len(state.get('cookies',[]))}条")


def cleanup_browser(pw, browser, context):
    try:
        if context:
            context.close()
        if browser:
            browser.close()
        pw.stop()
    except Exception:
        pass


def human_delay(min_s: float = None, max_s: float = None):
    from config import SCROLL_DELAY_MIN, SCROLL_DELAY_MAX
    lo = min_s if min_s is not None else SCROLL_DELAY_MIN
    hi = max_s if max_s is not None else SCROLL_DELAY_MAX
    return random.uniform(lo, hi) * 1000


def human_scroll(page: Page, distance: int = None):
    from config import SCROLL_DISTANCE_MIN, SCROLL_DISTANCE_MAX
    if distance is None:
        distance = random.randint(SCROLL_DISTANCE_MIN, SCROLL_DISTANCE_MAX)
    x_offset = random.randint(-5, 5)
    page.mouse.wheel(x_offset, distance)
