"""PA信号系统运行器 — 早/中/晚三时段

用法:
    python pa_runner.py                     # 默认晚间全量扫描
    python pa_runner.py --session morning   # 盘前精选（基于昨日数据）
    python pa_runner.py --session noon      # 午间扫描
    python pa_runner.py --session evening   # 收盘复盘（全量+深度）

流程:
    1. pa_screener: 全市场 → 硬过滤 → PA评分 → Top 200-300
    2. pa_analyzer: 逐只拉K线 → PA结构分析
    3. pa_signal:   生成信号 + 支撑阻力 + 挂单价格
    4. pa_feishu:   飞书卡片推送
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime

# 项目内模块
from src.pa_screener import screen_pa_friendly
from src.pa_analyzer import analyze
from src.pa_signal import generate
from src.pa_feishu import render_signal_card, render_summary_card
from src.feishu import send_card
from src.fetcher import http_push2_kline
from config import PA_SIGNAL_MIN_SCORE

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("pa_runner")


def setup_logging():
    """确保所有子模块的 logger 也被捕获"""
    for name in ["a-share.pa_screener", "a-share.pa_analyzer",
                 "a-share.pa_signal", "a-share.pa_feishu", "a-share.feishu"]:
        logging.getLogger(name).setLevel(logging.INFO)


def _run_analysis_on_pool(pool, session_label: str, top_n_push: int = 15,
                          min_score: int = PA_SIGNAL_MIN_SCORE,
                          max_stocks: int = None) -> list:
    """对筛选池中的股票逐只做 PA 分析并生成信号

    Args:
        pool: screen_pa_friendly 的结果 (DataFrame)
        session_label: 用于日志
        top_n_push: 最多推送数量
        min_score: 最低评分门槛
        max_stocks: 最多分析多少只（None=全部）

    Returns:
        按评分降序排列的信号列表
    """
    total = len(pool)
    limit = min(total, max_stocks) if max_stocks else total
    logger.info(f"PA分析 ({limit}/{total}只)...")

    t0 = time.time()
    signals = []

    for i, row in pool.iterrows():
        if i >= limit:
            break

        code = row["code"]
        name = row["name"]

        try:
            # 拉K线
            df = http_push2_kline(code, days=250)
            if df.empty or len(df) < 50:
                logger.debug(f"  {name}({code}) 跳过: K线不足")
                continue

            # PA 分析
            pa_result = analyze(df)
            pa_result["current_price"] = float(row.get("price", 0))

            # 生成信号
            signal = generate(pa_result, code, name)

            if signal.ok:
                signals.append(signal)
                logger.info(f"  ✅ {name}({code}) 评分{signal.technical_score} "
                           f"方向:{signal.direction} 置信:{signal.confidence} "
                           f"入场:{signal.suggested_entry} RR:{signal.rr_ratio}")
            else:
                logger.debug(f"  - {name}({code}) {signal.error}")

        except Exception as e:
            logger.warning(f"  ❌ {name}({code}) 分析失败: {e}")
            continue

        # 进度
        if (i + 1) % 25 == 0:
            elapsed = time.time() - t0
            logger.info(f"  进度: {i+1}/{limit} ({elapsed:.0f}s, 已发现{len(signals)}个)")

    elapsed = time.time() - t0
    logger.info(f"分析完成: {len(signals)} 个信号 (耗时{elapsed:.0f}s, "
               f"平均{elapsed/max(1,limit):.1f}s/只)")

    # 排序
    signals.sort(key=lambda s: -s.technical_score)
    return signals[:top_n_push]


def _push_to_feishu(signals: list, session_label: str) -> int:
    """推送到飞书"""
    if not signals:
        logger.warning("无信号可推送")
        return 0

    logger.info(f"飞书推送 ({len(signals)}个信号)...")

    # 1. 汇总卡片
    summary = render_summary_card(signals, session_label)
    if summary:
        ok = send_card(summary)
        logger.info(f"  汇总卡片: {'✅' if ok else '❌'}")

    # 2. 逐个详情卡片
    pushed = 0
    for s in signals:
        card = render_signal_card(s)
        ok = send_card(card)
        if ok:
            pushed += 1
            logger.info(f"  📨 {s.name}({s.code})")
        else:
            logger.warning(f"  ❌ {s.name}({s.code}) 推送失败")
        time.sleep(0.3)

    return pushed


# ═══════════════════════════════════════════════
# 三时段
# ═══════════════════════════════════════════════

def run_evening(top_n_screen: int = 250, top_n_push: int = 15):
    """晚间收盘复盘：全量扫描 + 深度PA分析 + 推送明日候选"""
    logger.info("=" * 60)
    logger.info("🌙 晚间收盘复盘 — PA信号扫描")
    logger.info("=" * 60)

    t0 = time.time()

    # Phase 1: 筛选
    pool = screen_pa_friendly(top_n=top_n_screen)
    if pool.empty:
        logger.warning("未筛选出任何PA友好标的")
        return
    logger.info(f"Phase 1 筛选完成: {len(pool)} 只")

    # Phase 2: 全量分析
    signals = _run_analysis_on_pool(pool, "收盘复盘", top_n_push=top_n_push)

    # Phase 3: 推送
    pushed = _push_to_feishu(signals, "收盘复盘")

    total_time = time.time() - t0
    logger.info(f"\n{'='*50}")
    logger.info(f"晚间复盘完成: 筛选{len(pool)}只 → 信号{len(signals)}个 → 推送{pushed}条")
    logger.info(f"总耗时: {total_time:.0f}s ({total_time/60:.1f}min)")
    logger.info(f"{'='*50}")


def run_morning():
    """盘前精选：基于昨日收盘K线，推送今日可关注的高质量标的"""
    logger.info("=" * 60)
    logger.info("🌅 盘前精选 — 基于昨日收盘的PA候选")
    logger.info("=" * 60)

    t0 = time.time()

    # 少一些标的，提高门槛
    pool = screen_pa_friendly(top_n=150)
    if pool.empty:
        logger.warning("未筛选出PA友好标的")
        return
    logger.info(f"筛选: {len(pool)} 只")

    # 只分析前80只，门槛提高到70
    signals = _run_analysis_on_pool(pool, "盘前精选", top_n_push=8,
                                    min_score=70, max_stocks=80)

    pushed = _push_to_feishu(signals, "盘前精选")

    logger.info(f"盘前完成: 信号{len(signals)}个 → 推送{pushed}条, "
               f"耗时{time.time()-t0:.0f}s")


def run_noon():
    """午间扫描：快速扫描，发现上午走出的PA结构"""
    logger.info("=" * 60)
    logger.info("☀️ 午间扫描 — 盘中PA信号捕捉")
    logger.info("=" * 60)

    t0 = time.time()

    pool = screen_pa_friendly(top_n=100)
    if pool.empty:
        logger.warning("未筛选出标的")
        return
    logger.info(f"筛选: {len(pool)} 只")

    # 快速分析前50只
    signals = _run_analysis_on_pool(pool, "午间扫描", top_n_push=8,
                                    max_stocks=50)

    pushed = _push_to_feishu(signals, "午间扫描")

    logger.info(f"午间完成: 信号{len(signals)}个 → 推送{pushed}条, "
               f"耗时{time.time()-t0:.0f}s")


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="A股PA信号系统")
    parser.add_argument("--session", "-s", choices=["morning", "noon", "evening"],
                       default="evening", help="运行时段 (默认: evening)")
    parser.add_argument("--top-screen", type=int, default=250,
                       help="筛选保留数量 (默认: 250)")
    parser.add_argument("--top-push", type=int, default=15,
                       help="最多推送数量 (默认: 15)")
    args = parser.parse_args()

    setup_logging()

    logger.info(f"PA Runner 启动 — session={args.session}")

    if args.session == "morning":
        run_morning()
    elif args.session == "noon":
        run_noon()
    else:
        run_evening(top_n_screen=args.top_screen, top_n_push=args.top_push)


if __name__ == "__main__":
    main()
