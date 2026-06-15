#!/usr/bin/env python
"""hb-trading 统一入口 — PA 投研一体化平台

子命令:
  pa-pipeline  全市场PA扫描 + TOP5委员会 + 回顾
  scrape       小红书/公众号单篇抓取
  scrape-author 小红书作者级批量抓取
  gen-image    生成小红书图片卡片
  dashboard    启动 Streamlit 面板
  runner       期货实时信号监控
  futures      期货数据采集 / 回测
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import LOG_FORMAT, LOG_LEVEL

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger("main")


# ======================================================================
# PA Pipeline (from src.a_share)
# ======================================================================

def cmd_pa_pipeline(args):
    from src.a_share.pipeline import run_full_pipeline, run_review_and_push, run_backtest
    from src.a_share.market_overview import analyze_market
    from src.a_share.stock_scanner import run_scan, save_scan_result
    from src.a_share.report import generate_daily_report, generate_feishu_doc, save_reports
    from src.a_share.feishu_pusher import push_market_overview, push_daily_report_doc
    from src.a_share.review import run_review

    mode = args.mode
    push = not args.no_push
    scan_date = args.date or date.today().isoformat()

    if mode == "full":
        prev = args.prev_date
        result = run_full_pipeline(push=push, prev_review_date=prev)
        print(f"\nPipeline: {result.get('buy_count','?')} buy signals")
        if result.get("doc_url"):
            print(f"Feishu: {result['doc_url']}")

    elif mode == "market":
        market = analyze_market()
        print(f"\nPA env: {market.pa_environment.total}/100")
        print(f"Verdict: {market.pa_environment.verdict}")

    elif mode == "decide":
        scan = run_scan()
        save_scan_result(scan)
        print(f"\nScanned: {scan.total_scanned} -> {scan.phase1_passed} -> {scan.summary['买入']} buy")
        print(f"TOP5: {[(s.name, s.total_score) for s in scan.top5]}")

    elif mode == "review":
        review_data = run_review_and_push(scan_date, push=True) if push else run_review(scan_date)
        m = review_data.get("matrix", {})
        print(f"\nConfusion: TP={m.get('tp','?')} FP={m.get('fp','?')}")
        print(f"Win rate: {review_data.get('metrics', {}).get('win_rate', 'N/A')}")

    elif mode == "backtest":
        result = run_backtest(args.from_date, args.to_date)
        print(result)

    elif mode == "stats":
        tracker = Path("output/performance_tracker.json")
        if tracker.exists():
            import json
            print(json.dumps(json.loads(tracker.read_text(encoding="utf-8")), ensure_ascii=False, indent=2))
        else:
            print("No stats yet")

    elif mode == "report":
        report_path = Path(f"output/daily/{scan_date}/daily_report.md")
        if report_path.exists() and push:
            doc_url = push_daily_report_doc(report_path.read_text(encoding="utf-8"), scan_date)
            print(f"Pushed: {doc_url}")
        elif not report_path.exists():
            print(f"No report for {scan_date}")


# ======================================================================
# Scraper
# ======================================================================

def cmd_scrape(args):
    url = args.url
    from src.scraper.platform import detect_platform, extract_note_id, get_platform_name

    platform = detect_platform(url)
    logger.info(f"Platform: {get_platform_name(platform)} | {url[:60]}")

    if platform == "xhs":
        from src.scraper.browser import create_browser, cleanup_browser
        from src.scraper.extractor_xhs import extract
        from src.scraper.storage import save

        pw, browser, context, page = create_browser()
        try:
            final_url = url
            if "xhslink.com" in url:
                page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                final_url = page.url

            from datetime import datetime
            date_str = datetime.now().strftime("%Y%m%d")
            tmp_dir = Path("output/scraper") / f"{date_str}_tmp"
            tmp_dir.mkdir(exist_ok=True, parents=True)

            nid = "" if "xhslink.com" in url else extract_note_id(final_url, platform)
            data = extract(page, final_url, note_id=nid, save_dir=tmp_dir)
            save_dir = save(data, platform)
            print(f"[OK] {data.title[:50]} | {len(data.content)} chars | {save_dir}")
        finally:
            cleanup_browser(pw, browser, context)

    elif platform == "wechat":
        from src.scraper.browser import create_browser, cleanup_browser
        from src.scraper.extractor_wechat import extract
        from src.scraper.storage import save

        pw, browser, context, page = create_browser()
        try:
            data = extract(page, url)
            save_dir = save(data, platform)
            print(f"[OK] {data.title[:50]} | {save_dir}")
        finally:
            cleanup_browser(pw, browser, context)


def cmd_scrape_author(args):
    url = args.url
    max_notes = args.max_notes or 50

    from src.scraper.platform import detect_profile_url
    from src.scraper.browser import create_browser, cleanup_browser, human_delay

    user_id = detect_profile_url(url)
    if not user_id:
        from src.scraper.extractor_xhs import extract_user_id
        pw, browser, context, page = create_browser()
        try:
            if "xhslink.com" in url:
                page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                url = page.url
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            user_id = extract_user_id(page)
        finally:
            cleanup_browser(pw, browser, context)
        if not user_id:
            print("[FAIL] Cannot extract user_id")
            return

    from src.scraper.extractor_xhs_author import scrape_author as do_scrape
    pw, browser, context, page = create_browser()
    try:
        result = do_scrape(page, user_id, max_notes)
        print(f"[OK] {result.get('author_name', '')}: "
              f"new={result.get('scraped', 0)} skip={result.get('skipped', 0)} "
              f"total={result.get('total_notes', 0)}")
        print(f"Dir: {result.get('save_root', '')}")
    finally:
        cleanup_browser(pw, browser, context)


# ======================================================================
# Image Gen
# ======================================================================

def cmd_gen_image(args):
    from src.image_gen.generator import (
        generate_knowledge_card, generate_quote_card,
        generate_list_card, generate_comparison_card,
    )
    template = args.template or "knowledge"
    title = args.title or "Title"
    body = args.body or ""
    tag = args.tag or "#PA"
    output = args.output or "output/images/card.png"

    Path(output).parent.mkdir(exist_ok=True, parents=True)

    if template == "knowledge":
        generate_knowledge_card(title, body, tag, output)
    elif template == "quote":
        generate_quote_card(body, title, output)
    elif template == "list":
        items = [l.strip() for l in body.split("\n") if l.strip()]
        generate_list_card(title, items, output)
    elif template == "comparison":
        parts = body.split("|") if "|" in body else ("Left", "Right")
        generate_comparison_card(title, parts[0].strip(), parts[-1].strip(), output)
    print(f"[OK] {output}")


# ======================================================================
# Dashboard / Runner / Futures
# ======================================================================

def cmd_dashboard(args):
    import subprocess
    subprocess.run(["streamlit", "run", "dashboard.py"])


def cmd_runner(args):
    from runner import main as runner_main
    runner_main()


def cmd_futures(args):
    if args.futures_action == "collect":
        from src.collector import fill_all
        fill_all()
        print("[OK] Data collected")
    elif args.futures_action == "backtest":
        from src.backtest import run_backtest
        symbols = args.symbols.split(",") if args.symbols else None
        run_backtest(symbols)


# ======================================================================
# Main
# ======================================================================

def main():
    p = argparse.ArgumentParser(description="hb-trading — PA Research Platform")
    sub = p.add_subparsers(dest="command", help="Subcommand")

    # pa-pipeline
    pp = sub.add_parser("pa-pipeline", help="A-share PA scan pipeline")
    pp.add_argument("--mode", choices=["full","market","decide","report","review","backtest","stats","repush"],
                    default="full")
    pp.add_argument("--date", help="Target date")
    pp.add_argument("--prev-date", help="Previous date for review")
    pp.add_argument("--from-date", help="Backtest start")
    pp.add_argument("--to-date", help="Backtest end")
    pp.add_argument("--push", action="store_true", default=True)
    pp.add_argument("--no-push", action="store_true")
    pp.set_defaults(func=cmd_pa_pipeline)

    # scrape
    ps = sub.add_parser("scrape", help="Scrape single post")
    ps.add_argument("url")
    ps.set_defaults(func=cmd_scrape)

    # scrape-author
    psa = sub.add_parser("scrape-author", help="Scrape all author posts")
    psa.add_argument("url")
    psa.add_argument("--max-notes", "-n", type=int, default=50)
    psa.set_defaults(func=cmd_scrape_author)

    # gen-image
    pgi = sub.add_parser("gen-image", help="Generate XHS card image")
    pgi.add_argument("--template", "-t", choices=["knowledge","quote","list","comparison"], default="knowledge")
    pgi.add_argument("--title")
    pgi.add_argument("--body")
    pgi.add_argument("--tag")
    pgi.add_argument("--output", "-o")
    pgi.set_defaults(func=cmd_gen_image)

    # dashboard
    pd_ = sub.add_parser("dashboard", help="Launch Streamlit dashboard")
    pd_.set_defaults(func=cmd_dashboard)

    # runner
    pr = sub.add_parser("runner", help="Futures live monitor")
    pr.set_defaults(func=cmd_runner)

    # futures
    pf = sub.add_parser("futures", help="Futures data/backtest")
    pf.add_argument("action", choices=["collect","backtest"])
    pf.add_argument("--symbols", "-s")
    pf.set_defaults(func=cmd_futures)

    args = p.parse_args()
    if not args.command:
        p.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
