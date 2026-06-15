"""小红书内容提取器 — 正文 + 图片下载 + API拦截多级嵌套评论 + 主动展开二级回复"""
import json
import logging
import time
import re
import random
import requests
from pathlib import Path
from dataclasses import dataclass, field
from playwright.sync_api import Page

from config import (
    PAGE_TIMEOUT, COMMENT_API_TIMEOUT,
    MAX_COMMENTS, MAX_SUB_COMMENTS, OUTPUT_DIR,
)
from scraper.browser import human_scroll, human_delay

logger = logging.getLogger("xhs_extractor")


@dataclass
class Comment:
    id: str
    user: str
    content: str
    likes: int = 0
    time_str: str = ""
    replies: list["Comment"] = field(default_factory=list)
    sub_count: int = 0       # 二级回复总数（API 返回，可能 > len(replies)）


@dataclass
class XhsNote:
    platform: str = "xhs"
    url: str = ""
    note_id: str = ""
    title: str = ""
    author: str = ""
    content: str = ""
    images: list[str] = field(default_factory=list)      # 原始 URL
    local_images: list[str] = field(default_factory=list) # 本地路径
    likes: int = 0
    collects: int = 0
    comments: list[Comment] = field(default_factory=list)
    comment_count: int = 0


def extract(page: Page, url: str, note_id: str = "", save_dir: Path = None) -> XhsNote:
    """提取小红书笔记正文 + 全部多级评论 + 下载图片"""
    result = XhsNote(url=url, note_id=note_id)
    logger.info(f"开始提取小红书: {url}")

    # ---- 预置评论 API 监听（必须在 page.goto 之前） ----
    raw_comments: list[dict] = []
    sub_raw: dict[str, list[dict]] = {}
    xsec_token = ""

    def _on_resp(resp):
        nonlocal xsec_token
        try:
            rurl = resp.url
            if "/api/sns/web/v2/comment/sub/page" in rurl:
                root_id = _extract_param(rurl, "root_comment_id")
                data = resp.json()
                slist = data.get("data", {}).get("comments", [])
                logger.info(f"sub/page: root={root_id[:8] if root_id else '?'} +{len(slist)}条")
                if root_id not in sub_raw:
                    sub_raw[root_id] = []
                sub_raw[root_id].extend(slist)
            elif "/api/sns/web/v2/comment/page" in rurl and "sub/page" not in rurl:
                token = _extract_param(rurl, "xsec_token")
                if token:
                    xsec_token = token
                data = resp.json()
                clist = data.get("data", {}).get("comments", [])
                logger.info(f"comment/page: +{len(clist)}条 token={'有' if xsec_token else '无'}")
                raw_comments.extend(clist)
        except Exception as e:
            logger.debug(f"on_resp error: {e}")

    page.on("response", _on_resp)

    # ---- 1. 打开页面（加随机参数绕过缓存） ----
    import random as _rand
    sep = "&" if "?" in url else "?"
    cache_bust = f"{sep}_nocache={_rand.randint(10000,99999)}"
    page.goto(url + cache_bust, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
    try:
        page.wait_for_selector("#detail-desc", timeout=15_000)
    except Exception:
        logger.warning("正文加载慢，继续尝试...")
        human_delay(2, 3)
    human_delay(1.5, 2.5)

    # 如果 note_id 为空，从最终 URL 或页面数据提取
    if not result.note_id:
        result.note_id = _extract_note_id_from_url(page.url)
    # 双重确认：尝试从页面 JS 变量提取
    if not result.note_id:
        try:
            result.note_id = page.evaluate("""
                () => {
                    const m = location.href.match(/explore\\/([a-f0-9]+)/) || location.href.match(/item\\/([a-f0-9]+)/);
                    return m ? m[1] : '';
                }
            """)
        except Exception:
            pass
    logger.info(f"note_id: {result.note_id}")

    # ---- 2. 提取正文 ----
    _extract_body(page, result)

    # ---- 3. 下载图片到本地 ----
    if save_dir:
        _download_images(result, save_dir)

    # ---- 4. 评论：极速模式（跳过，专注正文+图片） ----
    comments: list[Comment] = []
    try:
        _trigger_comment_load(page)
        _wait_and_paginate(page, raw_comments, "", max_wait=2)
        for c in raw_comments[:MAX_COMMENTS]:
            comment = _parse_comment(c)
            comment.sub_count = int(c.get("sub_comment_count", 0) or 0)
            comments.append(comment)
        if raw_comments:
            _click_expand_buttons(page, comments, result.note_id, xsec_token)
    except Exception:
        pass
    try:
        page.remove_listener("response", _on_resp)
    except Exception:
        pass

    result.comments = comments
    result.comment_count = len(comments) + sum(len(c.replies) for c in comments)

    logger.info(f"提取完成: {result.title[:40]} | {len(result.content)}字 "
                f"| {result.likes}赞 | {len(result.local_images)}图 | "
                f"评论{result.comment_count}条({len(result.comments)}条一级)")

    return result


def _extract_body(page: Page, result: XhsNote):
    """提取正文元数据"""
    try:
        result.title = page.locator("#detail-title").inner_text().strip()
    except Exception:
        result.title = page.title()

    try:
        el = page.locator(".username").first
        result.author = el.inner_text().strip() if el else ""
    except Exception:
        pass

    try:
        el = page.locator("#detail-desc .note-text").first
        result.content = el.inner_text().strip() if el else ""
    except Exception:
        pass

    try:
        result.likes = _parse_count(page.locator(".like-wrapper .count").first.inner_text())
    except Exception:
        pass
    try:
        result.collects = _parse_count(page.locator(".collect-wrapper .count").first.inner_text())
    except Exception:
        pass

    # 图片 URL
    try:
        imgs = page.locator(".swiper-slide img, .note-image img, img[src*='xhscdn']").all()
        seen = set()
        for img in imgs:
            src = img.get_attribute("src") or ""
            if src and "avatar" not in src and "icon" not in src and src not in seen:
                seen.add(src)
                result.images.append(src)
    except Exception:
        pass

    logger.info(f"正文: {result.title[:40]} | {len(result.content)}字 "
                f"| {result.likes}赞 | {len(result.images)}图")


def _download_images(result: XhsNote, save_dir: Path):
    """下载图片到本地 output 目录"""
    img_dir = save_dir / "images"
    img_dir.mkdir(exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.xiaohongshu.com/",
    }

    for i, url in enumerate(result.images):
        try:
            # 修复协议缺失的 URL（// → https://）
            if url.startswith("//"):
                url = "https:" + url
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                ext = ".webp" if "webp" in url else ".jpg"
                fname = f"img_{i+1:02d}{ext}"
                fpath = img_dir / fname
                with open(fpath, "wb") as f:
                    f.write(resp.content)
                result.local_images.append(str(fpath))
                logger.info(f"图片下载: {fname} ({len(resp.content)} bytes)")
        except Exception as e:
            logger.warning(f"图片下载失败 {i}: {e}")

    # 同时修正原始 URL
    result.images = [("https:" + u if u.startswith("//") else u) for u in result.images]


# ======================================================================
# 登录检测
# ======================================================================

def check_logged_in(page: Page) -> bool:
    """检查是否已登录小红书（多重检测）"""
    # 方法1: 检查 session cookie
    cookies = page.context.cookies()
    for c in cookies:
        if c.get("name") in ("web_session", "a1") and c.get("value"):
            logger.info("小红书登录态有效 (cookie)")
            return True

    # 方法2: 调用户 API
    try:
        result = page.evaluate("""
            async () => {
                try {
                    const resp = await fetch('/api/sns/web/v1/user/selfinfo', {credentials:'include'});
                    const data = await resp.json();
                    return data?.success === true;
                } catch(e) { return false; }
            }
        """)
        if result:
            logger.info("小红书登录态有效 (API)")
            return True
    except Exception:
        pass

    return False


# ======================================================================
# 评论抓取 — 一级 API 拦截 + 二级主动展开
# ======================================================================

def _fetch_all_comments(page: Page, note_id: str) -> list[Comment]:
    """抓取全部评论：监听页面自然触发的API + 滚动触发 + 翻页"""
    raw_comments: list[dict] = []
    sub_raw: dict[str, list[dict]] = {}

    def _on_resp(resp):
        url = resp.url
        try:
            if "/api/sns/web/v2/comment/sub/page" in url:
                root_id = _extract_param(url, "root_comment_id")
                data = resp.json()
                slist = data.get("data", {}).get("comments", [])
                if root_id not in sub_raw:
                    sub_raw[root_id] = []
                sub_raw[root_id].extend(slist)
            elif "/api/sns/web/v2/comment/page" in url:
                data = resp.json()
                clist = data.get("data", {}).get("comments", [])
                raw_comments.extend(clist)
        except Exception:
            pass

    page.on("response", _on_resp)

    # 触发评论加载 —— 滚动 + 点击评论
    _trigger_comment_load(page)
    _wait_and_paginate(page, raw_comments, "一级评论", max_wait=25)

    try:
        page.remove_listener("response", _on_resp)
    except Exception:
        pass

    # 解析
    comments: list[Comment] = []
    for c in raw_comments[:MAX_COMMENTS]:
        comment = _parse_comment(c)
        comment.sub_count = int(c.get("sub_comment_count", 0) or 0)
        # 合并拦截到的子评论
        root_id = comment.id
        if root_id in sub_raw:
            for s in sub_raw[root_id]:
                if len(comment.replies) < MAX_SUB_COMMENTS:
                    comment.replies.append(_parse_comment(s))
        comments.append(comment)

    logger.info(f"一级评论: {len(comments)}条, 二级回复: {sum(len(c.replies) for c in comments)}条")
    return comments


def _trigger_comment_load(page: Page):
    """滚动触发评论加载，切换到评论 tab"""
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.35)")
        human_delay(1, 1.5)
        # 评论 tab
        tab = page.locator('[class*="comment"]').first
        if tab:
            try:
                tab.click()
                human_delay(0.5, 1)
            except Exception:
                pass
    except Exception:
        pass


def _wait_and_paginate(page: Page, raw_list: list, label: str, max_wait: int = 25):
    """等待 API 响应，滚动翻页获取更多"""
    start = time.time()
    last_count = 0
    stall = 0

    while time.time() - start < max_wait:
        time.sleep(1.0)
        current = len(raw_list)
        if current > last_count:
            last_count = current
            stall = 0
            human_scroll(page, distance=random.randint(400, 700))
            human_delay(0.5, 1)
        else:
            stall += 1

        if stall >= 4 and current > 0:
            break
        if current >= MAX_COMMENTS:
            break

    logger.debug(f"{label}: {len(raw_list)}条")


# ======================================================================
# 二级回复 — 主动调用 API
# ======================================================================

def _click_expand_buttons(page: Page, comments: list[Comment], note_id: str, xsec_token: str = ""):
    """获取二级回复：直接调API（带xsec_token鉴权）"""
    total_subs = 0

    for parent in comments:
        if parent.sub_count <= 0:
            continue
        if not note_id or not parent.id:
            continue

        try:
            sub_comments = page.evaluate("""
                async ([nid, rid, token]) => {
                    const params = new URLSearchParams({
                        note_id: nid, root_comment_id: rid, num: '10'
                    });
                    if (token) params.append('xsec_token', token);
                    const u = 'https://edith.xiaohongshu.com/api/sns/web/v2/comment/sub/page?' + params.toString();
                    const resp = await fetch(u, {credentials:'include'});
                    const data = await resp.json();
                    return data?.data?.comments || [];
                }
            """, [note_id, parent.id, xsec_token])

            for s in sub_comments or []:
                if len(parent.replies) >= MAX_SUB_COMMENTS:
                    break
                parent.replies.append(_parse_comment(s))
                total_subs += 1

            time.sleep(0.2)
        except Exception as e:
            pass

        if total_subs >= 100:
            break

    logger.info(f"二级回复: {total_subs}条")


# ======================================================================
# 解析工具
# ======================================================================

def _parse_comment(c: dict) -> Comment:
    return Comment(
        id=str(c.get("id", "")),
        user=c.get("user_info", {}).get("nickname", "匿名"),
        content=c.get("content", ""),
        likes=int(c.get("like_count", 0)),
        time_str=c.get("create_time", ""),
        sub_count=c.get("sub_comment_count", 0),
    )


def _parse_count(text: str) -> int:
    text = text.strip()
    if not text:
        return 0
    try:
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        return int(text)
    except ValueError:
        return 0


def _extract_note_id_from_url(url: str) -> str:
    m = re.search(r'/explore/([a-f0-9]+)', url)
    if m: return m.group(1)
    m = re.search(r'/discovery/item/([a-f0-9]+)', url)
    if m: return m.group(1)
    m = re.search(r'/a/([a-f0-9]+)', url)
    if m: return m.group(1)
    return ""


def _extract_param(url: str, key: str) -> str:
    """从URL中提取单个查询参数"""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    return qs.get(key, [""])[0]


def extract_user_id(page: Page) -> str:
    """从笔记页面提取作者 user_id（24位hex字符串）"""
    # 策略1: HTML regex（覆盖绝大多数情况）
    html = page.content()
    for pattern in [
        r'"authorId"\s*:\s*"([a-f0-9]{24})"',
        r'"userId"\s*:\s*"([a-f0-9]{24})"',
        r'"user_id"\s*:\s*"([a-f0-9]{24})"',
        r'/user/profile/([a-f0-9]{24})',
    ]:
        m = re.search(pattern, html)
        if m:
            logger.info(f"从HTML提取user_id: {m.group(1)}")
            return m.group(1)

    # 策略2: JS evaluate
    try:
        user_id = page.evaluate("""
            () => {
                const s = document.body.innerHTML;
                const m = s.match(/"authorId":"([a-f0-9]{24})"/);
                return m ? m[1] : '';
            }
        """)
        if user_id:
            logger.info(f"从JS提取user_id: {user_id}")
            return user_id
    except Exception:
        pass

    logger.warning("无法提取user_id")
    return ""
