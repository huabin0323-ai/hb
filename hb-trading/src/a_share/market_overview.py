"""Phase 0: 大盘行情概览 — A股主要指数PA状态 + 板块轮动 + 环境评分"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import akshare as ak
import pandas as pd
import numpy as np

logger = logging.getLogger("pa_pipeline.market")

# ======================================================================
# 指数配置
# ======================================================================

MAJOR_INDICES = {
    "sh000001": {"name": "上证指数", "code": "000001"},
    "sz399001": {"name": "深证成指", "code": "399001"},
    "sz399006": {"name": "创业板指", "code": "399006"},
    "sh000688": {"name": "科创50", "code": "000688"},
}

BROAD_INDICES = {
    "sh000300": {"name": "沪深300", "code": "000300"},
    "sh000905": {"name": "中证500", "code": "000905"},
    "sh000852": {"name": "中证1000", "code": "000852"},
}


# ======================================================================
# Data structures
# ======================================================================

@dataclass
class IndexPAState:
    """单个指数的PA状态"""
    name: str
    code: str
    close: float
    pct_change: float
    trend: str           # "上升趋势" | "下降趋势" | "交易区间"
    stage: int            # 1-4 (Al Brooks四阶段)
    channel: str          # "窄通道" | "宽通道" | "—"
    ema20_direction: str  # "上升" | "走平" | "下降"
    ema20_value: float


@dataclass
class SectorPerformance:
    """板块表现"""
    name: str
    pct_change: float
    leading_stocks: list[str] = field(default_factory=list)


@dataclass
class MarketBreadth:
    """市场宽度"""
    up_count: int
    down_count: int
    flat_count: int
    limit_up_count: int
    limit_down_count: int
    total_volume_yi: float   # 成交额（亿）
    avg_volume_5d_yi: float  # 5日均成交额


@dataclass
class PAEnvironmentScore:
    """PA环境评分"""
    trend_score: float       # 趋势性 0-40 (多指数同向程度)
    activity_score: float    # 活跃度 0-30 (成交额+涨跌比)
    structure_score: float   # 结构性 0-30 (板块分化程度)
    total: int               # 总分 0-100
    verdict: str             # 🟢适合顺势 | 🟡适合区间 | 🔴建议观望
    description: str


@dataclass
class MarketOverview:
    """大盘行情概览汇总"""
    date: str
    indices: list[IndexPAState]
    breadth: MarketBreadth
    top_sectors: list[SectorPerformance]   # 领涨
    bottom_sectors: list[SectorPerformance] # 领跌
    pa_environment: PAEnvironmentScore


# ======================================================================
# 数据获取
# ======================================================================

def _fetch_index_hist(symbol: str, name: str, days: int = 100) -> pd.DataFrame:
    """获取指数日线历史"""
    try:
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is not None and len(df) >= 20:
            return df.tail(days)
    except Exception as e:
        logger.warning(f"获取指数 {name}({symbol}) 数据失败: {e}")
    return pd.DataFrame()


def _calc_ema(series: pd.Series, period: int = 20) -> pd.Series:
    """计算EMA"""
    return series.ewm(span=period, adjust=False).mean()


def _find_swings(high: np.ndarray, low: np.ndarray, window: int = 5):
    """找摆动高低点"""
    n = len(high)
    sh_idx, sh_val = [], []
    sl_idx, sl_val = [], []

    for i in range(window, n - window):
        if high[i] == np.max(high[i - window:i + window + 1]):
            sh_idx.append(i)
            sh_val.append(high[i])
        if low[i] == np.min(low[i - window:i + window + 1]):
            sl_idx.append(i)
            sl_val.append(low[i])

    return sh_idx, sh_val, sl_idx, sl_val


# ======================================================================
# 指数PA状态判定
# ======================================================================

def _classify_index_pa(df: pd.DataFrame, name: str, code: str) -> IndexPAState:
    """对单个指数做PA状态分类"""
    if len(df) < 20:
        return IndexPAState(
            name=name, code=code, close=0, pct_change=0,
            trend="数据不足", stage=0, channel="—",
            ema20_direction="—", ema20_value=0,
        )

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    ema20 = _calc_ema(df["close"], 20).values

    latest_close = float(close[-1])
    latest_ema20 = float(ema20[-1])
    pct_change = float((close[-1] - close[-2]) / close[-2] * 100) if len(close) >= 2 else 0

    # EMA20 方向
    ema20_slope = (ema20[-1] - ema20[-6]) / ema20[-6] * 100 if ema20[-6] != 0 else 0
    if ema20_slope > 0.3:
        ema_dir = "上升"
    elif ema20_slope < -0.3:
        ema_dir = "下降"
    else:
        ema_dir = "走平"

    # 找摆动点
    sh_idx, sh_vals, sl_idx, sl_vals = _find_swings(high, low, window=5)

    # 判定HH+HL还是LH+LL
    has_hh_hl = False
    has_lh_ll = False
    if len(sh_vals) >= 2 and len(sl_vals) >= 2:
        recent_sh = sh_vals[-3:] if len(sh_vals) >= 3 else sh_vals
        recent_sl = sl_vals[-3:] if len(sl_vals) >= 3 else sl_vals
        hh = all(recent_sh[i] > recent_sh[i-1] for i in range(1, len(recent_sh)))
        hl = all(recent_sl[i] > recent_sl[i-1] for i in range(1, len(recent_sl)))
        lh = all(recent_sh[i] < recent_sh[i-1] for i in range(1, len(recent_sh)))
        ll = all(recent_sl[i] < recent_sl[i-1] for i in range(1, len(recent_sl)))
        has_hh_hl = hh and hl
        has_lh_ll = lh and ll

    # 趋势判定
    if has_hh_hl and ema_dir == "上升":
        trend = "上升趋势"
    elif has_lh_ll and ema_dir == "下降":
        trend = "下降趋势"
    elif ema_dir == "走平":
        trend = "交易区间"
    elif has_hh_hl:
        trend = "上升趋势"
    elif has_lh_ll:
        trend = "下降趋势"
    else:
        trend = "交易区间"

    # 阶段判定
    if trend in ("上升趋势", "下降趋势"):
        # 检查回调特征
        recent = df.iloc[-20:]
        if ema_dir == "上升":
            below_ema = (recent["low"] < recent["close"].ewm(span=20, adjust=False).mean()).sum()
        else:
            below_ema = (recent["high"] > recent["close"].ewm(span=20, adjust=False).mean()).sum()

        recent_range = (recent["high"].max() - recent["low"].min()) / recent["close"].mean() * 100

        if below_ema <= 2 and recent_range > 8:
            stage = 1  # Spike
            channel = "—"
        elif below_ema <= 4:
            stage = 2  # 窄通道
            channel = "窄通道"
        elif below_ema <= 10:
            stage = 3  # 宽通道
            channel = "宽通道"
        else:
            stage = 4  # 交易区间
            channel = "—"
    else:
        stage = 4
        channel = "—"

    return IndexPAState(
        name=name, code=code, close=latest_close, pct_change=pct_change,
        trend=trend, stage=stage, channel=channel,
        ema20_direction=ema_dir, ema20_value=latest_ema20,
    )


# ======================================================================
# 全市场数据
# ======================================================================

def _fetch_market_breadth() -> MarketBreadth:
    """获取全市场涨跌家数、成交额（新浪数据源）"""
    try:
        # Use Sina-based spot data which works more reliably
        df = ak.stock_zh_a_spot()
        # Sina columns: ['代码', '名称', '最新价', '涨跌额', '涨跌幅', '买入', '卖出', '昨收', '今开', '最高', '最低', '成交量', '成交额']
        pct_col = '涨跌幅'
        vol_col = '成交额'

        up = int((df[pct_col] > 0).sum())
        down = int((df[pct_col] < 0).sum())
        flat = int((df[pct_col] == 0).sum())
        # 涨停≈涨幅>=9.9%
        limit_up = int((df[pct_col] >= 9.9).sum())
        limit_down = int((df[pct_col] <= -9.9).sum())
        total_vol = float(df[vol_col].sum() / 1e8)  # 转为亿

        return MarketBreadth(
            up_count=up, down_count=down, flat_count=flat,
            limit_up_count=limit_up, limit_down_count=limit_down,
            total_volume_yi=total_vol, avg_volume_5d_yi=total_vol,
        )
    except Exception as e:
        logger.warning(f"获取全市场宽度失败: {e}")
        return MarketBreadth(0, 0, 0, 0, 0, 0, 0)


def _fetch_sector_performance() -> tuple[list[SectorPerformance], list[SectorPerformance]]:
    """获取行业涨跌幅排名（新浪数据源）"""
    try:
        # Try Sina industry boards
        df = ak.stock_board_industry_summary_ths()
        if df is not None and len(df) > 0:
            # THS columns: ['板块', '涨幅', ...]
            df = df.sort_values("涨幅", ascending=False)
            sectors = []
            for _, row in df.iterrows():
                sectors.append(SectorPerformance(
                    name=str(row["板块"]),
                    pct_change=float(row["涨幅"]),
                ))
            return sectors[:5], sectors[-5:][::-1]
    except Exception:
        pass

    try:
        # Fallback: use East Money if available
        df = ak.stock_board_industry_name_em()
        if df is not None and len(df) > 0:
            df = df.sort_values("涨跌幅", ascending=False)
            sectors = []
            for _, row in df.iterrows():
                sectors.append(SectorPerformance(
                    name=str(row["板块名称"]),
                    pct_change=float(row["涨跌幅"]),
                ))
            return sectors[:5], sectors[-5:][::-1]
    except Exception as e:
        logger.warning(f"获取板块数据失败: {e}")

    return [], []


# ======================================================================
# PA环境评分
# ======================================================================

def _score_environment(
    indices: list[IndexPAState],
    breadth: MarketBreadth,
) -> PAEnvironmentScore:
    """计算PA环境评分 0-100"""

    # 趋势性: 多指数同向程度 (0-40)
    trends = [i.trend for i in indices if i.trend != "数据不足"]
    if not trends:
        trend_score = 10
    else:
        up_count = sum(1 for t in trends if t == "上升趋势")
        down_count = sum(1 for t in trends if t == "下降趋势")
        max_align = max(up_count, down_count)
        trend_score = (max_align / len(trends)) * 40

    # 活跃度: 成交额+涨跌比 (0-30)
    vol_score = min(breadth.total_volume_yi / 15000, 1.0) * 15 if breadth.total_volume_yi > 0 else 7
    total_stocks = breadth.up_count + breadth.down_count + breadth.flat_count
    if total_stocks > 0:
        breadth_ratio = max(breadth.up_count, breadth.down_count) / total_stocks
    else:
        breadth_ratio = 0.5
    breadth_score = (1 - abs(breadth_ratio - 0.5) * 1.5) * 15 if breadth_ratio > 0.55 else breadth_ratio * 15
    activity_score = vol_score + breadth_score

    # 结构性: 板块分化程度 (0-30)
    # 有领涨领跌板块说明有结构，不是普涨普跌
    structure_score = 16  # 默认中等

    total = int(trend_score + activity_score + structure_score)

    if total >= 65:
        verdict = "🟢 适合顺势交易，优先阶段1/2个股"
        desc = "多指数共振+成交充沛+板块有主线"
    elif total >= 45:
        verdict = "🟡 适合交易区间策略，顺势仓位减半"
        desc = "趋势分化或震荡，精选结构清晰的个股"
    else:
        verdict = "🔴 建议观望，减少买入信号"
        desc = "市场混乱，PA信号可靠性下降"

    return PAEnvironmentScore(
        trend_score=trend_score,
        activity_score=activity_score,
        structure_score=structure_score,
        total=total,
        verdict=verdict,
        description=desc,
    )


# ======================================================================
# 主入口
# ======================================================================

def analyze_market() -> MarketOverview:
    """Phase 0: 分析大盘PA环境

    Returns:
        MarketOverview with all market analysis data
    """
    from datetime import date
    today = date.today().isoformat()

    # 获取主要指数日线 + PA状态
    indices = []
    for symbol, info in MAJOR_INDICES.items():
        try:
            df = _fetch_index_hist(symbol, info["name"])
            if df is not None and len(df) >= 20:
                state = _classify_index_pa(df, info["name"], info["code"])
            else:
                state = IndexPAState(
                    name=info["name"], code=info["code"], close=0, pct_change=0,
                    trend="获取失败", stage=0, channel="—",
                    ema20_direction="—", ema20_value=0,
                )
            indices.append(state)
        except Exception as e:
            logger.error(f"分析指数 {info['name']} 失败: {e}")
            indices.append(IndexPAState(
                name=info["name"], code=info["code"], close=0, pct_change=0,
                trend="错误", stage=0, channel="—",
                ema20_direction="—", ema20_value=0,
            ))

    # 全市场宽度
    breadth = _fetch_market_breadth()

    # 板块轮动
    top_sectors, bottom_sectors = _fetch_sector_performance()

    # PA环境评分
    pa_env = _score_environment(indices, breadth)

    return MarketOverview(
        date=today,
        indices=indices,
        breadth=breadth,
        top_sectors=top_sectors,
        bottom_sectors=bottom_sectors,
        pa_environment=pa_env,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    overview = analyze_market()
    print(f"\n大盘PA环境评分: {overview.pa_environment.total}/100")
    print(f"结论: {overview.pa_environment.verdict}")
    for idx in overview.indices:
        print(f"  {idx.name}: {idx.trend} 阶段{idx.stage} {idx.channel} 20EMA{idx.ema20_direction}")
    print(f"  上涨{overview.breadth.up_count}/下跌{overview.breadth.down_count} 成交{overview.breadth.total_volume_yi:.0f}亿")
