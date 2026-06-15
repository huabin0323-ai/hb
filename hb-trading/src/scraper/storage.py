"""存储 — 保存原始数据 + 格式化 Markdown"""
import json
import logging
import re
from pathlib import Path
from datetime import datetime

from .config import OUTPUT_DIR, CONTENT_FILENAME, RAW_FILENAME, SUMMARY_FILENAME
from .platform import get_platform_name

logger = logging.getLogger("storage")


def safe_filename(title: str, max_len: int = 40) -> str:
    """标题 → 安全文件名"""
    name = re.sub(r'[\\/:*?"<>|]', '', title)
    name = name.strip()[:max_len].strip()
    return name or "untitled"


def save(data, platform: str) -> Path:
    """保存爬取结果到 output/{date}_{title}/ 目录"""
    date_str = datetime.now().strftime("%Y%m%d")
    title_safe = safe_filename(getattr(data, "title", ""))
    dir_name = f"{date_str}_{title_safe}" if title_safe else f"{date_str}_{platform}"
    save_dir = OUTPUT_DIR / dir_name
    save_dir.mkdir(exist_ok=True, parents=True)

    # 1. 原始 JSON
    raw_path = save_dir / RAW_FILENAME
    raw_data = _to_dict(data)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"原始数据: {raw_path}")

    # 2. 格式化 Markdown
    md_path = save_dir / CONTENT_FILENAME
    markdown = _to_markdown(data, platform)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    logger.info(f"Markdown: {md_path}")

    return save_dir


def _to_dict(data) -> dict:
    """提取器 dataclass → dict"""
    d = {}
    for field_name in data.__dataclass_fields__:
        val = getattr(data, field_name)
        if hasattr(val, '__dataclass_fields__'):
            d[field_name] = _to_dict(val)
        elif isinstance(val, list):
            d[field_name] = [
                _to_dict(item) if hasattr(item, '__dataclass_fields__') else item
                for item in val
            ]
        else:
            d[field_name] = val
    return d


def _to_markdown(data, platform: str) -> str:
    """格式化正文+评论为 Markdown"""
    platform_name = get_platform_name(platform)
    lines = [
        f"# {getattr(data, 'title', '无标题')}",
        f"",
        f"> 来源: {platform_name} | 作者: {getattr(data, 'author', '未知')}",
        f"> URL: {getattr(data, 'url', '')}",
    ]

    # 互动数据（小红书）
    if platform == "xhs":
        likes = getattr(data, "likes", 0)
        collects = getattr(data, "collects", 0)
        lines.append(f"> 点赞: {likes} | 收藏: {collects}")

    lines.extend(["", "---", "", "## 正文", ""])
    content = getattr(data, "content", "")
    lines.append(content if content else "(无正文)")

    # 图片
    images = getattr(data, "images", [])
    local_images = getattr(data, "local_images", [])
    if images:
        lines.extend(["", "## 图片", ""])
        for i, src in enumerate(images[:10]):
            lines.append(f"![图{i+1}]({src})")
        # 如果有本地图片也引用
        if local_images:
            lines.append("")
            for i, lp in enumerate(local_images[:10]):
                # 使用相对路径
                rel = Path(lp).name
                lines.append(f"*本地: images/{rel}*")

    # 评论
    comments = getattr(data, "comments", [])
    total_comment_count = getattr(data, "comment_count", len(comments))
    if comments:
        lines.extend(["", "---", "",
                      f"## 评论 ({len(comments)}条一级, 共{total_comment_count}条)", ""])
        for i, c in enumerate(comments, 1):
            likes_str = f" 👍{c.likes}" if c.likes else ""
            sub_hint = f" [+{c.sub_count}回复]" if c.sub_count else ""
            lines.append(f"### {i}. {c.user}{likes_str}{sub_hint}")
            lines.append(f"")
            lines.append(c.content)
            lines.append(f"")

            # 二级回复
            for r in c.replies:
                r_likes = f" 👍{r.likes}" if r.likes else ""
                lines.append(f"> **{r.user}**{r_likes}: {r.content}")
                lines.append(f"> ")

            lines.append(f"")

    return "\n".join(lines)


def save_summary(save_dir: Path, summary_md: str):
    """保存 AI 总结"""
    summary_path = save_dir / SUMMARY_FILENAME
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_md)
    logger.info(f"AI总结: {summary_path}")
    return summary_path
