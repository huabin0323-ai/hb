"""Phase 5: 次日全量回顾 — 验证前日决策，生成混淆矩阵，判定策略修正"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import akshare as ak
import numpy as np
import pandas as pd

from .stock_scanner import OUTPUT_DIR, PASignal

logger = logging.getLogger("pa_pipeline.review")


# ======================================================================
# Data structures
# ======================================================================

@dataclass
class ReviewResult:
    """回顾结果（单只股票）"""
    code: str
    name: str
    decision: str           # 前日决策: "买入" | "不动"
    signal_type: str
    direction: str

    # 前日计划
    entry: Optional[float]
    stop_loss: Optional[float]
    target_1: Optional[float]
    target_2: Optional[float]

    # 今日实际
    today_open: float
    today_high: float
    today_low: float
    today_close: float
    today_pnl_pct: float    # 以开盘价为基准的盈亏%

    # 验证结果
    hit_entry: bool         # 是否触发入场
    hit_stop: bool          # 是否触发止损
    hit_target_1: bool      # 是否触及止盈1
    hit_target_2: bool      # 是否触及止盈2
    result: str             # "止盈1" | "止盈2" | "盈利" | "止损" | "未触发" | "N/A"


@dataclass
class ReviewMatrix:
    """混淆矩阵"""
    true_positive: int   # 买入+盈利
    false_positive: int  # 买入+亏损
    false_negative: int  # 不动+盈利（漏判）
    true_negative: int   # 不动+亏损（正确不动）

    @property
    def total_buy(self) -> int:
        return self.true_positive + self.false_positive

    @property
    def total_wait(self) -> int:
        return self.false_negative + self.true_negative

    @property
    def win_rate(self) -> float:
        """胜率 = TP / (TP+FP)"""
        total = self.total_buy
        return self.true_positive / total * 100 if total > 0 else 0

    @property
    def miss_rate(self) -> float:
        """漏判率 = FN / (FN+TN)"""
        total = self.total_wait
        return self.false_negative / total * 100 if total > 0 else 0

    @property
    def accuracy(self) -> float:
        """准确率 = (TP+TN) / 全部"""
        total = self.total_buy + self.total_wait
        return (self.true_positive + self.true_negative) / total * 100 if total > 0 else 0


# ======================================================================
# 获取今日K线
# ======================================================================

def _fetch_today_kline(code: str) -> Optional[dict]:
    """获取个股今日日线数据"""
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df is not None and len(df) >= 1:
            last = df.iloc[-1]
            return {
                "open": float(last["开盘"]),
                "high": float(last["最高"]),
                "low": float(last["最低"]),
                "close": float(last["收盘"]),
            }
    except Exception as e:
        logger.debug(f"获取 {code} 今日K线失败: {e}")
    return None


# ======================================================================
# 逐只验证
# ======================================================================

def _evaluate_one(decision: dict, today: Optional[dict]) -> ReviewResult:
    """验证单只股票的决策"""
    code = decision.get("code", "")
    name = decision.get("name", "")
    dec = decision.get("decision", "不动")
    sig = decision.get("signal_type") or "—"
    direction = decision.get("direction") or "—"
    entry = decision.get("entry_price")
    stop_loss = decision.get("stop_loss")
    target_1 = decision.get("target_1")
    target_2 = decision.get("target_2")

    if today is None:
        return ReviewResult(
            code=code, name=name, decision=dec, signal_type=sig,
            direction=direction, entry=entry, stop_loss=stop_loss,
            target_1=target_1, target_2=target_2,
            today_open=0, today_high=0, today_low=0, today_close=0,
            today_pnl_pct=0, hit_entry=False, hit_stop=False,
            hit_target_1=False, hit_target_2=False, result="N/A",
        )

    open_p = today["open"]
    high = today["high"]
    low = today["low"]
    close = today["close"]

    # 盈亏（以开盘价为基准）
    if open_p > 0:
        pnl_pct = (close - open_p) / open_p * 100
    else:
        pnl_pct = 0

    # 验证
    hit_entry = True  # 假设开盘即可入场
    hit_stop = False
    hit_target_1 = False
    hit_target_2 = False
    result = "N/A"

    if dec == "买入" and entry and stop_loss:
        # 以开盘价作为实际入场价
        # 止损检查
        if direction == "多":
            hit_stop = low <= stop_loss
            hit_target_1 = high >= target_1 if target_1 else False
            hit_target_2 = high >= target_2 if target_2 else False
        else:
            hit_stop = high >= stop_loss
            hit_target_1 = low <= target_1 if target_1 else False
            hit_target_2 = low <= target_2 if target_2 else False

        if hit_stop:
            result = "止损"
        elif hit_target_2:
            result = "止盈2"
        elif hit_target_1:
            result = "止盈1"
        elif pnl_pct > 0:
            result = "盈利"
        else:
            result = "亏损"
    else:
        # 不动信号：假设开盘价买入，看是否盈利
        hit_entry = False
        if pnl_pct > 0:
            result = "漏判(盈利)"  # 不动但实际涨了
        else:
            result = "正确(不动)"

    return ReviewResult(
        code=code, name=name, decision=dec, signal_type=sig,
        direction=direction, entry=entry, stop_loss=stop_loss,
        target_1=target_1, target_2=target_2,
        today_open=open_p, today_high=high, today_low=low, today_close=close,
        today_pnl_pct=round(pnl_pct, 2),
        hit_entry=hit_entry, hit_stop=hit_stop,
        hit_target_1=hit_target_1, hit_target_2=hit_target_2,
        result=result,
    )


# ======================================================================
# 混淆矩阵构建
# ======================================================================

def _build_matrix(results: list[ReviewResult]) -> ReviewMatrix:
    """从回顾结果构建混淆矩阵"""
    tp = fp = fn = tn = 0

    for r in results:
        if r.decision == "买入":
            if r.result in ("止盈1", "止盈2", "盈利"):
                tp += 1
            else:  # 止损, 亏损
                fp += 1
        else:  # 不动
            if "漏判" in r.result:
                fn += 1
            else:
                tn += 1

    return ReviewMatrix(
        true_positive=tp, false_positive=fp,
        false_negative=fn, true_negative=tn,
    )


# ======================================================================
# 信号类型拆解
# ======================================================================

def _by_signal_type(results: list[ReviewResult]) -> dict:
    """按信号类型统计"""
    stats = {}
    for r in results:
        if r.decision != "买入":
            continue
        st = r.signal_type or "无信号"
        if st not in stats:
            stats[st] = {"total": 0, "win": 0, "pnls": []}
        stats[st]["total"] += 1
        if r.result in ("止盈1", "止盈2", "盈利"):
            stats[st]["win"] += 1
        stats[st]["pnls"].append(r.today_pnl_pct)

    output = {}
    for st, s in stats.items():
        output[st] = {
            "买入数": s["total"],
            "胜率": f"{s['win']/s['total']*100:.1f}%" if s["total"] > 0 else "N/A",
            "平均盈亏": f"{np.mean(s['pnls']):+.2f}%" if s["pnls"] else "N/A",
        }
    return output


# ======================================================================
# 策略修正判定
# ======================================================================

def _assess_strategy(matrix: ReviewMatrix, by_signal: dict) -> dict:
    """判定是否需要策略修正"""
    fixes = []
    level = "🟢 正常"

    if matrix.total_buy >= 10:  # 样本足够才下结论
        if matrix.win_rate < 40:
            level = "🔴 策略无效，暂停并深入分析"
            fixes.append("胜率<40%，检查失败案例共性")
        elif matrix.win_rate < 50:
            level = "🟡 需要优化"
            fixes.append("胜率40-50%，提高信号门槛或检查失败信号类型")
        else:
            level = "🟢 策略有效"

    if matrix.miss_rate > 25:
        fixes.append("漏判率>25%，考虑降低买入阈值")

    # 检查信号类型
    for st, s in by_signal.items():
        try:
            wr = float(s["胜率"].replace("%", ""))
        except (ValueError, KeyError):
            continue
        count = s["买入数"]
        if count >= 5 and wr < 35:
            fixes.append(f"信号类型'{st}'近5日胜率仅{wr:.0f}%，建议暂停或提高门槛")

    return {
        "level": level,
        "fixes": fixes,
        "needs_fix": len(fixes) > 0,
    }


# ======================================================================
# 主入口
# ======================================================================

def run_review(scan_date: str) -> dict:
    """Phase 5: 运行次日全量回顾

    Args:
        scan_date: 要回顾的扫描日期 (YYYY-MM-DD)

    Returns:
        完整回顾数据 dict
    """
    decisions_path = OUTPUT_DIR / scan_date / "phase3_decisions.json"
    if not decisions_path.exists():
        logger.error(f"决策文件不存在: {decisions_path}")
        return {"error": f"决策文件不存在: {decisions_path}"}

    # 加载前日决策
    with open(decisions_path, "r", encoding="utf-8") as f:
        decisions_data = json.load(f)

    all_decisions = decisions_data.get("all_decisions", [])
    top5 = decisions_data.get("top5", [])

    # 逐只验证
    results = []
    for i, dec in enumerate(all_decisions):
        today_kline = _fetch_today_kline(dec["code"])
        result = _evaluate_one(dec, today_kline)
        results.append(result)
        if i % 50 == 0:
            logger.info(f"回顾进度: {i}/{len(all_decisions)}")

    # 构建混淆矩阵
    matrix = _build_matrix(results)

    # 信号类型拆解
    by_signal = _by_signal_type(results)

    # TOP5回顾
    top5_review = []
    for i, t5 in enumerate(top5, 1):
        code = t5["code"]
        today = _fetch_today_kline(code)
        open_p = today["open"] if today else 0
        close_p = today["close"] if today else 0
        pnl = (close_p - open_p) / open_p * 100 if open_p > 0 else 0
        result = "N/A"
        if today:
            entry = t5.get("entry_price", 0)
            stop = t5.get("stop_loss", 0)
            target = t5.get("target_1", 0)
            if entry and stop:
                if t5.get("direction") == "多":
                    if today["low"] <= stop:
                        result = "loss"
                    elif today["high"] >= target:
                        result = "win"
                    elif close_p > open_p:
                        result = "win"
                    else:
                        result = "loss"
                else:
                    if today["high"] >= stop:
                        result = "loss"
                    elif today["low"] <= target:
                        result = "win"
                    elif close_p < open_p:
                        result = "win"
                    else:
                        result = "loss"

        top5_review.append({
            "rank": i,
            "name": t5.get("name", "?"),
            "code": code,
            "signal": t5.get("signal_type", "?"),
            "pnl": f"{pnl:+.2f}%",
            "result": result,
        })

    # 策略修正评估
    strategy = _assess_strategy(matrix, by_signal)

    # 汇总
    buy_count = matrix.total_buy
    buylist = [r for r in results if r.decision == "买入"]
    avg_pnl = np.mean([r.today_pnl_pct for r in buylist]) if buylist else 0
    wins = [r.today_pnl_pct for r in buylist if r.result in ("止盈1", "止盈2", "盈利")]
    losses = [abs(r.today_pnl_pct) for r in buylist if r.result in ("止损", "亏损")]
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    profit_factor = (avg_win / avg_loss) if avg_loss > 0 else 99

    review_data = {
        "date": scan_date,
        "total_stocks": len(results),
        "buy_count": buy_count,
        "matrix": {
            "tp": matrix.true_positive,
            "fp": matrix.false_positive,
            "fn": matrix.false_negative,
            "tn": matrix.true_negative,
        },
        "metrics": {
            "win_rate": f"{matrix.win_rate:.1f}%",
            "miss_rate": f"{matrix.miss_rate:.1f}%",
            "accuracy": f"{matrix.accuracy:.1f}%",
            "avg_pnl": f"{avg_pnl:+.2f}%",
            "profit_factor": f"{profit_factor:.1f}:1",
            "avg_win": f"{avg_win:+.2f}%",
            "avg_loss": f"{-avg_loss:.2f}%",
        },
        "by_signal_type": by_signal,
        "top5_review": top5_review,
        "strategy": strategy,
        "results": [asdict(r) for r in results],
    }

    # 保存
    out_dir = OUTPUT_DIR / scan_date
    out_dir.mkdir(parents=True, exist_ok=True)
    review_path = out_dir / f"review_{scan_date}.json"
    with open(review_path, "w", encoding="utf-8") as f:
        json.dump(review_data, f, ensure_ascii=False, indent=2, default=str)

    # Markdown报告
    _save_review_md(review_data, out_dir)

    logger.info(f"回顾完成: 胜率{matrix.win_rate:.1f}% | 盈亏比{profit_factor:.1f}:1 | {strategy['level']}")
    return review_data


def _save_review_md(review_data: dict, out_dir: Path):
    """保存回顾Markdown报告"""
    lines = [
        f"# PA回顾报告 · {review_data['date']}",
        "",
        "## 混淆矩阵",
        "",
        "|  | 实际盈利 | 实际亏损 |",
        "|------|:---:|:---:|",
    ]
    m = review_data["matrix"]
    bc = m["tp"] + m["fp"]
    wc = m["fn"] + m["tn"]
    lines.append(f"| 🟢 买入信号({bc}) | {m['tp']} ✅ | {m['fp']} ❌ |")
    lines.append(f"| ⚪ 不动信号({wc}) | {m['fn']} ⚠️ | {m['tn']} ✅ |")
    lines.append("")

    lines.append("## 核心指标")
    lines.append("")
    met = review_data["metrics"]
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|:----:|")
    for k, v in met.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    if review_data.get("by_signal_type"):
        lines.append("## 按信号类型拆解")
        lines.append("")
        lines.append("| 信号类型 | 买入数 | 胜率 | 平均盈亏 |")
        lines.append("|----------|:---:|:---:|:---:|")
        for st, s in review_data["by_signal_type"].items():
            lines.append(f"| {st} | {s['买入数']} | {s['胜率']} | {s['平均盈亏']} |")
        lines.append("")

    if review_data.get("top5_review"):
        lines.append("## TOP5 回顾")
        lines.append("")
        lines.append("| # | 股票 | 信号 | 盈亏 | 结果 |")
        lines.append("|---|------|------|:---:|:---:|")
        for r in review_data["top5_review"]:
            emoji = "✅" if r["result"] == "win" else "❌" if r["result"] == "loss" else "⚠️"
            lines.append(f"| {r['rank']} | {r['name']}({r['code']}) | {r['signal']} | {r['pnl']} | {emoji} |")
        lines.append("")

    strat = review_data.get("strategy", {})
    lines.append(f"## 策略状态: {strat.get('level', 'N/A')}")
    lines.append("")
    if strat.get("fixes"):
        for fix in strat["fixes"]:
            lines.append(f"- {fix}")
    lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"review_{review_data['date']}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else (date.today() - timedelta(days=1)).isoformat()
    print(f"回顾日期: {target}")
    result = run_review(target)
    m = result["matrix"]
    print(f"\n混淆矩阵: TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}")
    print(f"胜率: {result['metrics']['win_rate']}")
    print(f"策略: {result['strategy']['level']}")
