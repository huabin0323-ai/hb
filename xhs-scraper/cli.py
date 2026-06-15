#!/usr/bin/env python
"""xhs-scraper CLI — 多平台内容爬取入口

用法:
  python cli.py <url>
  python cli.py <url> --no-summary    # 只爬取，不触发AI总结
  python cli.py <url> --force         # 强制重新爬取（忽略缓存）
"""

import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper.platform import detect_platform, extract_note_id, get_platform_name, detect_profile_url
from scraper.browser import create_browser, cleanup_browser, save_cookies, human_delay
from scraper.storage import save, save_summary
from config import OUTPUT_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("cli")


def scrape(url: str) -> dict:
    """主流程：识别平台 → 爬取 → 保存"""
    platform = detect_platform(url)
    platform_name = get_platform_name(platform)

    logger.info(f"平台: {platform_name} | URL: {url[:60]}")

    # 启动浏览器
    pw, browser, context, page = create_browser()
    note_id = ""

    try:
        # 按平台分发
        if platform == "xhs":
            from scraper.extractor_xhs import extract

            # 短链接跳转 → 用最终URL，避免二次导航走缓存
            final_url = url
            if "xhslink.com" in url:
                page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                final_url = page.url
                note_id = extract_note_id(final_url, platform)
                logger.info(f"短链跳转: {url[:40]}... -> {final_url[:60]}...")

            from datetime import datetime
            date_str = datetime.now().strftime("%Y%m%d")
            tmp_dir = OUTPUT_DIR / f"{date_str}_tmp"
            tmp_dir.mkdir(exist_ok=True, parents=True)

            data = extract(page, final_url, note_id=note_id, save_dir=tmp_dir)
        elif platform == "wechat":
            from scraper.extractor_wechat import extract
            data = extract(page, url)
        else:
            raise ValueError(f"不支持的平台: {platform}")

        # 保存
        save_dir = save(data, platform)

        return {
            "ok": True,
            "platform": platform,
            "platform_name": platform_name,
            "title": getattr(data, "title", ""),
            "content_length": len(getattr(data, "content", "")),
            "comment_count": getattr(data, "comment_count", 0),
            "save_dir": str(save_dir),
        }

    finally:
        cleanup_browser(pw, browser, context)


def main():
    p = argparse.ArgumentParser(description="xhs-scraper: 小红书/公众号内容爬取")
    p.add_argument("url", help="目标页面URL", nargs="?")
    p.add_argument("--author", "-a", action="store_true",
                   help="作者模式：抓取该用户全部笔记")
    p.add_argument("--max-notes", type=int, default=None,
                   help="作者模式下最多抓取笔记数 (默认50)")
    p.add_argument("--no-summary", action="store_true",
                   help="只爬取，不触发AI总结")
    p.add_argument("--force", action="store_true",
                   help="强制重新爬取（忽略缓存）")
    args = p.parse_args()

    if not args.url:
        p.print_help()
        return

    print(f"\n{'='*60}")
    label = "xhs-scraper [作者模式]" if args.author else "xhs-scraper"
    print(label)
    print(f"{'='*60}")

    if args.author:
        result = _scrape_author(args.url, max_notes=args.max_notes)
        print(f"\n{'='*60}")
        if result["ok"]:
            print(f"[OK] 作者爬取完成")
            print(f"   作者:   {result.get('author_name', '')}")
            print(f"   已抓取: {result.get('scraped', 0)} 篇")
            print(f"   已跳过: {result.get('skipped', 0)} 篇（已存在）")
            print(f"   目录:   {result.get('save_root', '')}")
            print(f"\n>> 索引: {result['save_root']}\\index.md")
        else:
            print(f"[FAIL] {result.get('error', '未知错误')}")
        print(f"{'='*60}\n")
    else:
        result = scrape(args.url)

        print(f"\n{'='*60}")
        if result["ok"]:
            print(f"[OK] 爬取成功")
            print(f"   平台:   {result['platform_name']}")
            print(f"   标题:   {result['title'][:60]}")
            print(f"   正文:   {result['content_length']}字")
            print(f"   评论:   {result['comment_count']}条")
            print(f"   目录:   {result['save_dir']}")
            print(f"\n>> 内容文件: {result['save_dir']}\\content.md")
            if not args.no_summary:
                print(f">> 在 Claude Code 中输入以生成 AI 总结")
        else:
            print(f"[FAIL] {result.get('error', '未知错误')}")

        print(f"{'='*60}\n")
        return result


def _scrape_author(url: str, max_notes: int = None) -> dict:
    """作者模式：解析user_id → 批量抓取全部笔记"""
    from scraper.extractor_xhs import extract_user_id
    from scraper.extractor_xhs_author import scrape_author as do_scrape_author
    from urllib.parse import urlparse, parse_qs

    # 提取 xsec_token（如果URL中有的话）
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    xsec_token = qs.get("xsec_token", [""])[0]

    # Step 1: 获取 user_id
    user_id = detect_profile_url(url)
    if user_id:
        logger.info(f"直接识别为作者主页: user_id={user_id} token={'有' if xsec_token else '无'}")
    else:
        logger.info("从笔记页面提取作者 user_id...")
        pw, browser, context, page = create_browser()
        try:
            if "xhslink.com" in url:
                page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                url = page.url
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_selector("#detail-desc", timeout=12_000)
            except Exception:
                human_delay(2, 3)
            user_id = extract_user_id(page)
        finally:
            cleanup_browser(pw, browser, context)

        if not user_id:
            return {"ok": False, "error": "无法从页面提取作者 user_id"}

    # Step 2: 启动浏览器，批量抓取
    pw, browser, context, page = create_browser()
    try:
        result = do_scrape_author(page, user_id, max_notes, xsec_token=xsec_token)
        return result
    finally:
        cleanup_browser(pw, browser, context)


if __name__ == "__main__":
    main()
