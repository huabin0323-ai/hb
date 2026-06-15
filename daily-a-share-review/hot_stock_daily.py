"""收盘后热门股识别 + 飞书预览推送

用法：
  python hot_stock_daily.py                         # 识别今日热门股，推预览到飞书
  python hot_stock_daily.py --date 20260612         # 指定日期
  python hot_stock_daily.py --no-push               # 仅保存，不推飞书
  python hot_stock_daily.py --top 5                 # 取前5只
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_BASE
from src.fetcher import fetch_limit_up_pool, fetch_limit_down_pool, fetch_dragon_tiger, fetch_market_news
from src.hot_stocks import identify_hot_stocks, format_hot_stocks_text
from src.feishu import send_afternoon_card

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("hot-stock-daily")


def main():
    parser = argparse.ArgumentParser(description="收盘后热门股识别")
    parser.add_argument("--date", default=None, help="日期 YYYYMMDD，默认今天")
    parser.add_argument("--top", type=int, default=3, help="取前N只热门股（默认3）")
    parser.add_argument("--no-push", action="store_true", help="跳过飞书推送")
    args = parser.parse_args()

    target_date = args.date or date.today().strftime("%Y%m%d")
    date_display = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]}"

    logger.info(f"🔍 识别 {date_display} 热门个股（Top {args.top}）")

    # 1. 抓取数据
    logger.info("📡 获取涨停板数据...")
    try:
        zt_df = fetch_limit_up_pool(target_date)
    except Exception as e:
        logger.warning(f"涨停板数据获取失败: {e}")
        zt_df = None

    logger.info("📡 获取龙虎榜数据...")
    try:
        dt_df = fetch_dragon_tiger(target_date)
    except Exception as e:
        logger.warning(f"龙虎榜数据获取失败: {e}")
        dt_df = None

    logger.info("📡 获取市场要闻...")
    try:
        news = fetch_market_news()
    except Exception as e:
        logger.warning(f"新闻获取失败: {e}")
        news = None

    # 2. 识别热门股
    hot_stocks = identify_hot_stocks(target_date, zt_df, dt_df, news=news, top_n=args.top)

    if not hot_stocks:
        logger.warning("⚠️ 今日未识别到热门个股（可能非交易日或数据延迟）")
        return

    logger.info(f"✅ 识别到 {len(hot_stocks)} 只热门股：")
    for s in hot_stocks:
        logger.info(f"  #{s['name']} — 热度分:{s['heat_score']} — {' · '.join(s['reasons'][:3])}")

    # 3. 保存到 output
    out_dir = Path(OUTPUT_BASE) / date_display
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "date": date_display,
        "generated_at": datetime.now().strftime("%H:%M:%S"),
        "hot_stocks": hot_stocks,
    }
    snapshot_path = out_dir / "hot_stocks.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"📸 热门股快照 → {snapshot_path}")

    # 4. 飞书预览卡
    if not args.no_push:
        card = _build_preview_card(date_display, hot_stocks)
        ok = send_afternoon_card(card)
        if ok:
            logger.info("✅ 热门股预览已推送到飞书")
        else:
            logger.warning("⚠️ 飞书推送失败")
    else:
        logger.info("⏭️ 跳过飞书推送 (--no-push)")

    # 5. 输出路径供 Claude 后续使用
    logger.info(f"\n📌 Claude 深度解读入口：")
    logger.info(f"   读取 {snapshot_path}")
    logger.info(f"   对每只热门股调用 /investment-committee")
    logger.info(f"   或执行: python hot_stock_daily.py --date {target_date} 查看结果")


def _build_preview_card(date_display: str, hot_stocks: list[dict]) -> dict:
    """构建飞书预览卡片"""
    lines = [f"**🔥 {date_display} 收盘热门股识别**\n"]

    for i, s in enumerate(hot_stocks, 1):
        reasons_text = " · ".join(s["reasons"][:4])
        board_info = f" {s['boards']}连板 |" if s["boards"] else ""
        theme_info = f" {s['theme']} |" if s["theme"] else ""

        lines.append(f"**#{i} {s['name']}**（{s['code']}）")
        lines.append(f"{board_info}{theme_info} {reasons_text}")
        if s["net_buy"]:
            lines.append(f"龙虎榜净买：{s['net_buy']:+.1f}亿")
        lines.append("")

    lines.append("---")
    lines.append("💡 深度分析进行中，稍后推送每只个股的投委会纪要...")

    return {
        "header": {
            "title": {"tag": "plain_text", "content": f"🔥 收盘热门股速览 · {date_display}"},
            "template": "red",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}},
            {"tag": "note", "elements": [{"tag": "plain_text",
                "content": f"数据：新浪+东财 · AI热度评分 · {datetime.now().strftime('%H:%M')} · 深度分析稍后推送"}]},
        ],
    }


if __name__ == "__main__":
    main()
