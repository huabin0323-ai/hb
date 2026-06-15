"""PA Pipeline 编排器 — 串联所有Phase，提供统一入口"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from .market_overview import analyze_market, MarketOverview
from .stock_scanner import run_scan, save_scan_result, ScanResult
from .committee import run_committee, save_committee_result, CommitteeReport
from .report import generate_daily_report, generate_feishu_doc, save_reports
from .feishu_pusher import (
    push_market_overview, push_daily_report_doc, push_review,
)
from .review import run_review

logger = logging.getLogger("pa_pipeline")


def run_full_pipeline(
    push: bool = True,
    prev_review_date: Optional[str] = None,
) -> dict:
    """运行完整五阶段流水线

    Args:
        push: 是否推送飞书
        prev_review_date: 前一个交易日日期（用于昨日回顾，None=自动）

    Returns:
        {status, scan_date, buy_count, top5, doc_url, ...}
    """
    today = date.today().isoformat()
    logger.info(f"========== PA Pipeline 启动 · {today} ==========")

    # ===== Phase 0: 大盘概览 =====
    logger.info("Phase 0: 大盘行情概览...")
    market = analyze_market()
    logger.info(f"  PA环境评分: {market.pa_environment.total}/100 — {market.pa_environment.verdict}")

    # ===== Phase 1-3: 扫描+决策 =====
    logger.info("Phase 1-3: 全市场扫描...")
    scan = run_scan()
    save_scan_result(scan)
    buy_count = scan.summary.get("买入", 0)
    logger.info(f"  粗筛: {scan.phase1_passed}只 → 买入: {buy_count}只 → TOP5: {len(scan.top5)}只")

    # ===== Phase 4: 五角色委员会评审TOP5 =====
    logger.info("Phase 4: 五角色委员会评审TOP5...")
    if scan.top5:
        committee = run_committee(scan.top5, scan.phase1_candidates)
        save_committee_result(committee, today)
    else:
        committee = []
        logger.warning("  TOP5为空，跳过委员会评审")

    # ===== 生成报告 =====
    logger.info("生成日报...")
    prev_review = None
    if prev_review_date:
        review_path = Path(f"D:/hb/output/{prev_review_date}/review_{prev_review_date}.json")
        if review_path.exists():
            prev_review = json.loads(review_path.read_text(encoding="utf-8"))

    report_md = generate_daily_report(market, scan, committee, prev_review)
    feishu_doc = generate_feishu_doc(report_md)
    save_reports(report_md, feishu_doc, today)

    # ===== 飞书推送 =====
    doc_url = None
    if push:
        logger.info("飞书推送...")

        # 推送 #1: 大盘+TOP5速览
        push_market_overview(market, scan)

        # 推送 #2: 飞书文档
        doc_url = push_daily_report_doc(report_md, today)

    result = {
        "status": "success",
        "scan_date": today,
        "market_score": market.pa_environment.total,
        "market_verdict": market.pa_environment.verdict,
        "total_scanned": scan.total_scanned,
        "phase1_passed": scan.phase1_passed,
        "buy_count": buy_count,
        "top5": [
            {"code": s.code, "name": s.name, "score": s.total_score, "signal": s.signal_type}
            for s in scan.top5
        ],
        "committee_count": len(committee),
        "doc_url": doc_url,
    }

    logger.info(f"========== PA Pipeline 完成 ==========")
    logger.info(f"  买入: {buy_count}只 | TOP5评审: {len(committee)}只 | 推送: {'是' if push else '否'}")
    return result


def run_review_and_push(
    scan_date: str,
    push: bool = True,
) -> dict:
    """运行 Phase 5 回顾 + 飞书推送 #3

    Args:
        scan_date: 要回顾的日期
        push: 是否推送

    Returns:
        回顾数据
    """
    logger.info(f"Phase 5: 回顾 {scan_date}...")
    review_data = run_review(scan_date)

    if push:
        push_review(review_data)

    return review_data


def run_backtest(from_date: str, to_date: str) -> dict:
    """多日回测模式

    Args:
        from_date: 起始日期
        to_date: 结束日期

    Returns:
        累计统计
    """
    # TODO: 实现完整回测循环
    logger.info(f"回测模式: {from_date} → {to_date}")
    return {"status": "not_implemented", "mode": "backtest"}
