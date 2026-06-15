"""小红书作者级爬取 — 抓取作者全部笔记列表 + 逐篇提取正文+图片"""
import json
import logging
import time
import random
from pathlib import Path
from dataclasses import dataclass, field
from playwright.sync_api import Page

from .config import (
    MAX_AUTHOR_NOTES, AUTHOR_DELAY_MIN, AUTHOR_DELAY_MAX,
    AUTHOR_SCROLL_PAGES, OUTPUT_DIR,
)
from .browser import human_delay, human_scroll

logger = logging.getLogger("xhs_author")


@dataclass
class AuthorNoteMeta:
    """作者笔记列表中的单条元数据"""
    note_id: str
    xsec_token: str = ""
    title: str = ""
    url: str = ""
    like_count: int = 0
    comment_count: int = 0


@dataclass
class AuthorIndex:
    """作者全部笔记索引"""
    user_id: str
    author_name: str = ""
    notes: list[AuthorNoteMeta] = field(default_factory=list)


def intercept_author_notes(page: Page, user_id: str, max_notes: int = None,
                           xsec_token: str = "") -> AuthorIndex:
    """访问作者主页，拦截 user_posted API，滚动翻页收集全部笔记元数据"""
    if max_notes is None:
        max_notes = MAX_AUTHOR_NOTES

    result = AuthorIndex(user_id=user_id)
    collected: dict[str, AuthorNoteMeta] = {}
    stop_scrolling = False

    def _on_user_posted(resp):
        nonlocal stop_scrolling
        try:
            if "user_posted" not in resp.url:
                return
            data = resp.json()
            if not data.get("success"):
                return
            notes_data = data.get("data", {}).get("notes", [])
            has_more = data.get("data", {}).get("has_more", False)

            for item in notes_data:
                nid = item.get("note_id", "")
                if nid and nid not in collected:
                    xsec = item.get("xsec_token", "")
                    display_title = (
                        item.get("display_title", "")
                        or item.get("title", "")
                        or ""
                    )
                    collected[nid] = AuthorNoteMeta(
                        note_id=nid,
                        xsec_token=xsec,
                        title=display_title,
                        url=f"https://www.xiaohongshu.com/explore/{nid}",
                        like_count=int(item.get("liked_count", 0) or 0),
                        comment_count=int(item.get("comments_count", 0) or 0),
                    )
                    logger.info(
                        f"[{len(collected)}/{max_notes}] {display_title[:50]} "
                        f"| {nid[:8]}..."
                    )

            if not has_more:
                stop_scrolling = True
                logger.info("user_posted: has_more=false, 翻页结束")
            if len(collected) >= max_notes:
                stop_scrolling = True
                logger.info(f"已收集 {max_notes} 条, 停止翻页")

        except Exception as e:
            logger.debug(f"user_posted resp error: {e}")

    page.on("response", _on_user_posted)

    try:
        profile_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
        logger.info(f"访问作者主页: {profile_url}")
        page.goto(profile_url, wait_until="domcontentloaded", timeout=20_000)
        human_delay(2, 3)
    except Exception as e:
        logger.error(f"作者主页加载失败: {e}")
        try:
            page.remove_listener("response", _on_user_posted)
        except Exception:
            pass
        return result

    # 提取作者名
    try:
        name_el = page.locator('[class*="username"], [class*="nickname"], [class*="user-name"]').first
        result.author_name = name_el.inner_text().strip() if name_el else ""
        logger.info(f"作者: {result.author_name}")
    except Exception:
        pass

    # 滚动翻页
    for scroll_round in range(AUTHOR_SCROLL_PAGES):
        if stop_scrolling or len(collected) >= max_notes:
            break
        # 每轮滚动3次（更像人类行为）
        for _ in range(3):
            human_scroll(page, distance=random.randint(300, 600))
            human_delay(0.6, 1.2)
        human_delay(1, 2)
        logger.debug(f"翻页 {scroll_round + 1}/{AUTHOR_SCROLL_PAGES} | 已收集 {len(collected)}")

    human_delay(1, 2)

    try:
        page.remove_listener("response", _on_user_posted)
    except Exception:
        pass

    result.notes = list(collected.values())[:max_notes]
    logger.info(f"作者笔记收集完成: {len(result.notes)} 条")
    return result


def save_note(data, note_dir: Path) -> Path:
    """保存单篇笔记的 content.md + raw.json 到指定目录（不含日期前缀）"""
    from .storage import _to_dict, _to_markdown

    note_dir.mkdir(exist_ok=True, parents=True)

    # raw.json
    raw_data = _to_dict(data)
    with open(note_dir / "raw.json", "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2, default=str)

    # content.md
    markdown = _to_markdown(data, "xhs")
    with open(note_dir / "content.md", "w", encoding="utf-8") as f:
        f.write(markdown)

    logger.info(f"已保存: {note_dir.name}")
    return note_dir


def scrape_author(page: Page, user_id: str, max_notes: int = None,
                  skip_existing: bool = True, xsec_token: str = "") -> dict:
    """完整作者抓取流程:
    1. 拦截user_posted API收集全部笔记元数据
    2. 逐篇导航到详情页，调用 extract() 提取正文+图片
    3. 保存到 output/{author_name}/{title}/
    """
    from .extractor_xhs import extract
    from .storage import safe_filename

    if max_notes is None:
        max_notes = MAX_AUTHOR_NOTES

    # Step 1: 收集笔记列表
    index = intercept_author_notes(page, user_id, max_notes, xsec_token=xsec_token)
    if not index.notes:
        return {
            "ok": False,
            "error": "未找到任何笔记（作者可能设置了隐私，或账号不存在）",
            "author_name": index.author_name,
            "total_notes": 0,
        }

    # Step 2: 准备输出目录
    author_safe = safe_filename(index.author_name) if index.author_name else user_id[:8]
    save_root = OUTPUT_DIR / author_safe
    save_root.mkdir(exist_ok=True, parents=True)

    # Step 3: 逐篇抓取
    total = len(index.notes)
    scraped = 0
    skipped = 0

    for i, meta in enumerate(index.notes, 1):
        detail_url = f"{meta.url}?xsec_token={meta.xsec_token}" if meta.xsec_token else meta.url
        meta_safe = safe_filename(meta.title or meta.note_id)
        note_dir = save_root / meta_safe

        if skip_existing and (note_dir / "content.md").exists():
            logger.info(f"[{i}/{total}] 跳过(已存在): {meta.title[:40]}")
            skipped += 1
            continue

        logger.info(f"[{i}/{total}] 抓取: {meta.title[:50] or meta.note_id[:8]}")
        try:
            page.goto(detail_url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_selector("#detail-desc", timeout=12_000)
            except Exception:
                logger.warning("正文加载慢, 继续尝试...")
                human_delay(2, 3)

            note_dir.mkdir(exist_ok=True, parents=True)
            data = extract(page, detail_url, note_id=meta.note_id, save_dir=note_dir)
            save_note(data, note_dir)
            scraped += 1
        except Exception as e:
            logger.error(f"[{i}/{total}] 抓取失败: {meta.note_id[:8]} | {e}")
            continue

        delay = random.uniform(AUTHOR_DELAY_MIN, AUTHOR_DELAY_MAX)
        logger.debug(f"休息 {delay:.1f}s...")
        time.sleep(delay)

    # Step 4: 生成 index.md
    _generate_index_md(save_root, index)

    return {
        "ok": True,
        "author_name": index.author_name,
        "total_notes": total,
        "scraped": scraped,
        "skipped": skipped,
        "save_root": str(save_root),
    }


def _generate_index_md(save_root: Path, index: AuthorIndex) -> Path:
    """生成笔记索引表 index.md"""
    from .storage import safe_filename

    lines = [
        f"# {index.author_name or '未知作者'} 的笔记索引",
        "",
        f"- User ID: `{index.user_id}`",
        f"- 总计笔记: {len(index.notes)} 条",
        f"- 爬取时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
        "| # | 标题 | 点赞 | 评论 | 目录 |",
        "|:--:|------|:----:|:----:|------|",
    ]

    for i, meta in enumerate(index.notes, 1):
        title = (meta.title or meta.note_id[:12])[:40]
        like_str = str(meta.like_count) if meta.like_count else "-"
        comment_str = str(meta.comment_count) if meta.comment_count else "-"
        meta_safe = safe_filename(meta.title or meta.note_id)
        note_dir = save_root / meta_safe
        dir_link = f"[📁](./{meta_safe}/)" if (note_dir / "content.md").exists() else "⏳"

        lines.append(
            f"| {i} | {title} | {like_str} | {comment_str} | {dir_link} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 流水线提示",
        "",
        "将此索引交给 Claude，可批量生成 AI 总结并入库到 hb-trading 案例库：",
        "",
        "```",
        f"读取 {save_root}/index.md，为每篇已抓取的笔记生成 summary.md，",
        "然后将高质量案例入库到 D:/hb/hb-trading/data/cases/",
        "```",
    ])

    index_path = save_root / "index.md"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"索引已生成: {index_path}")
    return index_path
