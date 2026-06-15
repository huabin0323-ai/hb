"""微信公众号文章提取器 — 静态 HTML，无评论"""
import logging
import time
from dataclasses import dataclass, field
from playwright.sync_api import Page

from .config import PAGE_TIMEOUT

logger = logging.getLogger("wechat_extractor")


@dataclass
class WechatArticle:
    platform: str = "wechat"
    url: str = ""
    title: str = ""
    author: str = ""
    publish_time: str = ""
    content: str = ""
    images: list[str] = field(default_factory=list)
    comment_count: int = 0


def extract(page: Page, url: str) -> WechatArticle:
    """提取微信公众号文章正文"""
    result = WechatArticle(url=url)
    logger.info(f"开始提取公众号文章: {url}")

    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)

    # 等正文出现
    try:
        page.wait_for_selector("#js_content", timeout=10_000)
    except Exception:
        logger.warning("正文加载超时，尝试提取当前DOM")

    # 标题
    try:
        result.title = page.locator("#activity-name").inner_text().strip()
    except Exception:
        result.title = page.title()

    # 作者
    try:
        result.author = page.locator("#js_name").inner_text().strip()
    except Exception:
        pass

    # 发布时间
    try:
        result.publish_time = page.locator("#publish_time").inner_text().strip()
    except Exception:
        pass

    # 正文（处理 emoji、图片、段落）
    try:
        content_el = page.locator("#js_content")
        # 移除隐藏元素
        page.evaluate("""
            document.querySelectorAll('#js_content [style*="visibility: hidden"]')
                .forEach(el => el.remove());
        """)
        result.content = content_el.inner_text().strip()
    except Exception:
        result.content = ""

    # 图片
    try:
        img_els = page.locator("#js_content img").all()
        for img in img_els:
            src = img.get_attribute("data-src") or img.get_attribute("src")
            if src and "avatar" not in src:
                result.images.append(src)
    except Exception:
        pass

    logger.info(f"公众号提取完成: {result.title[:50]} ({len(result.content)}字)")
    return result
