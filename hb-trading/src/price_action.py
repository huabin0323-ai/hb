"""价格行为引擎 — Al Brooks 裸K结构识别与信号检测

实现：
  1. 摆动点识别 (swing highs/lows)
  2. 市场状态判定 (趋势/区间/通道)
  3. 信号K线检测 (强趋势K/Pin Bar/Inside Bar/Outside Bar)
  4. 入场信号 (H1/H2/H3 序列)
  5. 楔形检测 (3推+收敛)
  6. 失败突破检测 (80%规则)
  7. 0-100 技术面评分

参考：Al Brooks "Reading Price Charts Bar by Bar" 方法论。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np
import pandas as pd

from config import OHLCV_COLUMNS

logger = logging.getLogger("price_action")

# ======================================================================
# Data structures
# ======================================================================

SwingType = Literal["high", "low"]
TrendType = Literal["uptrend", "downtrend", "trading_range", "narrow_channel", "wide_channel"]
BarType = Literal[
    "strong_bullish", "strong_bearish",
    "pin_bar_bullish", "pin_bar_bearish",
    "inside_bar", "outside_bar_bullish", "outside_bar_bearish",
]
EntryType = Literal["H1", "H2", "H3", "wedge_break", "failed_breakout",
                        "bear_bar_long", "support_betrayal_long", "climax_warning",
                        "double_bottom", "ema_interaction", "final_flag_reversal",
                        "vacuum_effect", "horizontal_sr", "measuring_gap",
                        "spike_channel", "trend_resumption_day"]
Direction = Literal["long", "short"]


@dataclass
class SwingPoint:
    """摆动点"""
    index: int
    timestamp: pd.Timestamp
    price: float
    type: SwingType
    major: bool = False  # 是否是主要摆动点（窗口更大）


@dataclass
class MarketState:
    """市场状态判定结果"""
    trend: TrendType
    strength: float          # 0.0 ~ 1.0，趋势强度
    bias: Direction | None   # 方向倾向
    description: str
    swing_highs: list[SwingPoint] = field(default_factory=list)
    swing_lows: list[SwingPoint] = field(default_factory=list)
    channel_top: Optional[float] = None
    channel_bottom: Optional[float] = None


@dataclass
class SignalBar:
    """单根信号K线"""
    index: int
    timestamp: pd.Timestamp
    type: BarType
    strength: float          # 0.0 ~ 1.0
    description: str


@dataclass
class EntrySignal:
    """入场信号"""
    type: EntryType
    direction: Direction
    confidence: float        # 0.0 ~ 1.0
    entry_price: float
    stop_loss: float
    target: float
    description: str
    bar_index: int
    timestamp: pd.Timestamp


@dataclass
class TechnicalScore:
    """技术面综合评分"""
    score: int               # 0-100
    direction: Direction | None
    breakdown: dict          # 各因子得分拆解
    summary: str             # 一句话总结


# ======================================================================
# Helpers
# ======================================================================

def _validate_df(df: pd.DataFrame) -> pd.DataFrame:
    """确保 DataFrame 包含所需列，返回副本"""
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame 缺少列: {missing}")
    if len(df) == 0:
        raise ValueError("DataFrame 为空")
    return df.copy()


def _body_size(o: float, c: float) -> float:
    return abs(c - o)


def _upper_wick(o: float, c: float, h: float) -> float:
    return h - max(o, c)


def _lower_wick(o: float, c: float, l: float) -> float:
    return min(o, c) - l


def _total_range(h: float, l: float) -> float:
    return h - l


# ======================================================================
# 1. 摆动点识别
# ======================================================================

def find_swing_points(
    df: pd.DataFrame,
    window: int = 5,
    major_window: int = 10,
) -> tuple[list[SwingPoint], list[SwingPoint]]:
    """识别主要和次要摆动点。

    Args:
        df: OHLCV DataFrame
        window: 次要摆动点窗口（左右各 N 根 bar）
        major_window: 主要摆动点窗口

    Returns:
        (minor_swings, major_swings) — minor 包含所有，major 是子集
    """
    df = _validate_df(df)
    n = len(df)
    if n < 2 * window + 1:
        logger.warning(f"数据量({n})不足以检测摆动点(需要{2*window+1})")
        return [], []

    high = df["high"].values
    low = df["low"].values
    idx = df.index

    # 找所有次要摆动点
    minor_swings: list[SwingPoint] = []

    for i in range(window, n - window):
        h = high[i]
        l = low[i]

        # 局部高点
        if h >= np.max(high[i - window: i + window + 1]):
            # 确保不是平顶（至少有一侧严格大于）
            left_max = np.max(high[i - window: i])
            right_max = np.max(high[i + 1: i + window + 1])
            if h > left_max or h > right_max:
                minor_swings.append(SwingPoint(
                    index=i, timestamp=idx[i], price=h,
                    type="high", major=False,
                ))

        # 局部低点
        if l <= np.min(low[i - window: i + window + 1]):
            left_min = np.min(low[i - window: i])
            right_min = np.min(low[i + 1: i + window + 1])
            if l < left_min or l < right_min:
                minor_swings.append(SwingPoint(
                    index=i, timestamp=idx[i], price=l,
                    type="low", major=False,
                ))

    # 用 major_window 标记主要摆动点
    major_swings: list[SwingPoint] = []
    for i in range(major_window, n - major_window):
        h = high[i]
        l = low[i]

        if h >= np.max(high[i - major_window: i + major_window + 1]):
            left_max = np.max(high[i - major_window: i])
            right_max = np.max(high[i + 1: i + major_window + 1])
            if h > left_max or h > right_max:
                sp = SwingPoint(
                    index=i, timestamp=idx[i], price=h,
                    type="high", major=True,
                )
                major_swings.append(sp)
                # 也标记对应的 minor
                for ms in minor_swings:
                    if ms.index == i and ms.type == "high":
                        ms.major = True

        if l <= np.min(low[i - major_window: i + major_window + 1]):
            left_min = np.min(low[i - major_window: i])
            right_min = np.min(low[i + 1: i + major_window + 1])
            if l < left_min or l < right_min:
                sp = SwingPoint(
                    index=i, timestamp=idx[i], price=l,
                    type="low", major=True,
                )
                major_swings.append(sp)
                for ms in minor_swings:
                    if ms.index == i and ms.type == "low":
                        ms.major = True

    logger.debug(f"摆动点: minor={len(minor_swings)}, major={len(major_swings)}")
    return minor_swings, major_swings


# ======================================================================
# 2. 市场状态判定
# ======================================================================

def analyze_structure(df: pd.DataFrame) -> MarketState:
    """分析市场结构，判定当前状态。

    基于最近的主要摆动点序列判断趋势方向和通道类型。
    """
    df = _validate_df(df)
    n = len(df)

    # 默认返回值
    _empty = MarketState(
        trend="trading_range", strength=0.0, bias=None,
        description="数据不足，无法判定市场状态",
    )

    if n < 50:
        return _empty

    _, major = find_swing_points(df, window=5, major_window=10)

    high_points = [sp for sp in major if sp.type == "high"]
    low_points = [sp for sp in major if sp.type == "low"]

    if len(high_points) < 2 or len(low_points) < 2:
        return MarketState(
            trend="trading_range", strength=0.3, bias=None,
            description="摆动点不足，暂按区间处理",
            swing_highs=high_points, swing_lows=low_points,
        )

    # 取最近 5 个主要摆动点分析趋势
    recent_highs = sorted(high_points, key=lambda s: s.index)[-5:]
    recent_lows = sorted(low_points, key=lambda s: s.index)[-5:]

    hh_prices = [s.price for s in recent_highs]
    ll_prices = [s.price for s in recent_lows]

    # 判定更高高点 / 更低低点
    higher_highs = all(
        hh_prices[i] > hh_prices[i - 1]
        for i in range(1, len(hh_prices))
    )
    lower_highs = all(
        hh_prices[i] < hh_prices[i - 1]
        for i in range(1, len(hh_prices))
    )
    higher_lows = all(
        ll_prices[i] > ll_prices[i - 1]
        for i in range(1, len(ll_prices))
    )
    lower_lows = all(
        ll_prices[i] < ll_prices[i - 1]
        for i in range(1, len(ll_prices))
    )

    # 计算最近 N 根 bar 的价格区间
    recent = df.iloc[-50:]
    range_high = recent["high"].max()
    range_low = recent["low"].min()
    range_pct = (range_high - range_low) / range_low * 100

    # 计算价格运动斜率（用线性回归近似）
    x = np.arange(len(recent))
    y = recent["close"].values
    slope, _ = np.polyfit(x, y, 1)
    avg_price = y.mean()
    slope_pct = (slope * len(recent)) / avg_price * 100  # 50根bar期间的趋势幅度%

    # 判定
    trend: TrendType
    strength: float
    bias: Direction | None
    description: str

    if higher_highs and higher_lows:
        # 上升趋势
        if range_pct < 2:
            trend = "narrow_channel"
            strength = min(abs(slope_pct) / 3, 1.0)
            bias = "long"
            description = f"窄上升通道，区间{range_pct:.1f}%"
        elif range_pct < 5:
            trend = "wide_channel"
            strength = min(abs(slope_pct) / 5, 1.0)
            bias = "long"
            description = f"宽上升通道，区间{range_pct:.1f}%"
        else:
            trend = "uptrend"
            strength = min(abs(slope_pct) / 5, 1.0)
            bias = "long"
            description = f"上升趋势，斜率{slope_pct:.1f}%"

    elif lower_highs and lower_lows:
        # 下降趋势
        if range_pct < 2:
            trend = "narrow_channel"
            strength = min(abs(slope_pct) / 3, 1.0)
            bias = "short"
            description = f"窄下降通道，区间{range_pct:.1f}%"
        elif range_pct < 5:
            trend = "wide_channel"
            strength = min(abs(slope_pct) / 5, 1.0)
            bias = "short"
            description = f"宽下降通道，区间{range_pct:.1f}%"
        else:
            trend = "downtrend"
            strength = min(abs(slope_pct) / 5, 1.0)
            bias = "short"
            description = f"下降趋势，斜率{slope_pct:.1f}%"

    else:
        # 无明确趋势 → 交易区间
        trend = "trading_range"
        strength = 0.3
        bias = None
        description = f"交易区间，区间{range_pct:.1f}%"

    # 计算通道边界（用于后续入场参考）
    channel_top = None
    channel_bottom = None
    if trend in ("narrow_channel", "wide_channel", "trading_range"):
        if high_points:
            channel_top = np.mean([s.price for s in high_points[-3:]])
        if low_points:
            channel_bottom = np.mean([s.price for s in low_points[-3:]])

    return MarketState(
        trend=trend,
        strength=round(strength, 2),
        bias=bias,
        description=description,
        swing_highs=high_points,
        swing_lows=low_points,
        channel_top=channel_top,
        channel_bottom=channel_bottom,
    )


# ======================================================================
# 3. 信号K线检测
# ======================================================================

def detect_signal_bars(df: pd.DataFrame) -> list[SignalBar]:
    """检测每根K线是否为信号K线。

    检测类型：
    - strong_bullish / strong_bearish：强趋势K线
    - pin_bar_bullish / pin_bar_bearish：Pin Bar（锤子线/流星线）
    - inside_bar：内包线
    - outside_bar_bullish / outside_bar_bearish：外包线
    """
    df = _validate_df(df)
    n = len(df)
    if n < 2:
        return []

    signals: list[SignalBar] = []
    idx = df.index

    for i in range(1, n):  # 从第2根开始（inside/outside需要前一根）
        o, h, l, c = (
            df["open"].iloc[i], df["high"].iloc[i],
            df["low"].iloc[i], df["close"].iloc[i],
        )
        prev_o, prev_h, prev_l, prev_c = (
            df["open"].iloc[i - 1], df["high"].iloc[i - 1],
            df["low"].iloc[i - 1], df["close"].iloc[i - 1],
        )

        body = _body_size(o, c)
        total = _total_range(h, l)
        upper_w = _upper_wick(o, c, h)
        lower_w = _lower_wick(o, c, l)

        if total == 0:
            continue  # 无波动K线，跳过

        body_ratio = body / total
        upper_ratio = upper_w / total
        lower_ratio = lower_w / total
        bullish = c > o

        # --- 强趋势K线 ---
        # 实体 > 70%，收盘在极端附近（小影线）
        if body_ratio >= 0.7:
            if bullish and upper_ratio < 0.1:
                strength = min(body_ratio + (1 - upper_ratio), 1.0) / 2 + 0.5
                signals.append(SignalBar(
                    index=i, timestamp=idx[i], type="strong_bullish",
                    strength=round(strength, 2),
                    description=f"强多头K线 实体{body_ratio:.0%}",
                ))
            elif not bullish and lower_ratio < 0.1:
                strength = min(body_ratio + (1 - lower_ratio), 1.0) / 2 + 0.5
                signals.append(SignalBar(
                    index=i, timestamp=idx[i], type="strong_bearish",
                    strength=round(strength, 2),
                    description=f"强空头K线 实体{body_ratio:.0%}",
                ))

        # --- Pin Bar ---
        # 小实体 + 长影线（一头长一头短）
        if body_ratio <= 0.35:
            # 多头 Pin Bar（锤子线）：长下影线 + 短上影线 + 实体在顶部
            if lower_ratio >= 0.6 and upper_ratio <= 0.15:
                strength = lower_ratio * 0.8 + (1 - body_ratio) * 0.2
                signals.append(SignalBar(
                    index=i, timestamp=idx[i], type="pin_bar_bullish",
                    strength=round(strength, 2),
                    description=f"多头Pin Bar 下影线{lower_ratio:.0%}",
                ))
            # 空头 Pin Bar（流星线）：长上影线 + 短下影线 + 实体在底部
            elif upper_ratio >= 0.6 and lower_ratio <= 0.15:
                strength = upper_ratio * 0.8 + (1 - body_ratio) * 0.2
                signals.append(SignalBar(
                    index=i, timestamp=idx[i], type="pin_bar_bearish",
                    strength=round(strength, 2),
                    description=f"空头Pin Bar 上影线{upper_ratio:.0%}",
                ))

        # --- Inside Bar ---
        if h <= prev_h and l >= prev_l:
            # 内包在强趋势K线之后更有意义（整理形态）
            # 趋势尾部孕线 = 衰竭信号（来自Mr.西土瓦案例9/22）
            exhaustion = ""
            if i >= 4:
                prev_bars = df.iloc[i - 4:i]
                bull_run = all(
                    prev_bars.iloc[j]["close"] > prev_bars.iloc[j]["open"]
                    for j in range(len(prev_bars))
                )
                bear_run = all(
                    prev_bars.iloc[j]["close"] < prev_bars.iloc[j]["open"]
                    for j in range(len(prev_bars))
                )
                if bull_run:
                    exhaustion = "（多头衰竭）"
                elif bear_run:
                    exhaustion = "（空头衰竭）"
            signals.append(SignalBar(
                index=i, timestamp=idx[i], type="inside_bar",
                strength=0.65 if exhaustion else 0.5,
                description=f"Inside Bar{exhaustion}",
            ))

        # --- Outside Bar（外包/吞没） ---
        if h > prev_h and l < prev_l:
            if bullish and c > prev_c:
                signals.append(SignalBar(
                    index=i, timestamp=idx[i], type="outside_bar_bullish",
                    strength=min(body_ratio + 0.3, 1.0),
                    description="多头吞没",
                ))
            elif not bullish and c < prev_c:
                signals.append(SignalBar(
                    index=i, timestamp=idx[i], type="outside_bar_bearish",
                    strength=min(body_ratio + 0.3, 1.0),
                    description="空头吞没",
                ))

    return signals


# ======================================================================
# 4. 入场信号 (H1/H2/H3)
# ======================================================================

def detect_entry_signals(
    df: pd.DataFrame,
    state: MarketState,
    signal_bars: list[SignalBar],
    swings: list[SwingPoint],
) -> list[EntrySignal]:
    """检测 H1/H2/H3 入场序列。

    Al Brooks 二次入场逻辑：
    - H1: 趋势中的第一次回调入场（风险较高）
    - H2: 第二次回调入场（高概率）
    - H3: 第三次回调入场（楔形，最高概率）

    在上升趋势中寻找做多信号，下降趋势中寻找做空信号。
    """
    df = _validate_df(df)
    n = len(df)
    entries: list[EntrySignal] = []

    if state.bias is None or state.strength < 0.3:
        return entries  # 无明显方向或趋势太弱

    # 找到最近的信号K线（只保留近期的）
    recent_signals = [s for s in signal_bars if s.index >= n - 50]
    if not recent_signals:
        return entries

    # 根据 bias 筛选相关信号
    if state.bias == "long":
        relevant_types = {"strong_bullish", "pin_bar_bullish", "outside_bar_bullish"}
    else:
        relevant_types = {"strong_bearish", "pin_bar_bearish", "outside_bar_bearish"}

    filtered = [s for s in recent_signals if s.type in relevant_types]

    # 按摆动点分组，看信号K线出现在哪个回调位置
    bias_swings = [sp for sp in swings
                   if (state.bias == "long" and sp.type == "low") or
                      (state.bias == "short" and sp.type == "high")]

    # 找最近的摆动点
    recent_swings = sorted(bias_swings, key=lambda s: s.index)
    if len(recent_swings) < 1:
        return entries

    # 对每个摆动点后的信号判定是 H1/H2/H3
    # H1: 趋势启动后的第一次回调
    # H2: 第二次回调
    # H3: 第三次回调（楔形）

    for rank, sw in enumerate(recent_swings[-3:], start=len(recent_swings) - 2):
        # 该摆动点之后的信号K线
        after_swing = [s for s in filtered if s.index > sw.index and s.index >= n - 20]
        if not after_swing:
            continue

        best_signal = max(after_swing, key=lambda s: s.strength)
        bar = df.iloc[best_signal.index]
        atr = _calc_atr(df, 14)
        if atr is None or atr == 0:
            continue

        if rank == 1:
            entry_type: EntryType = "H1"
            confidence = min(state.strength * 0.6 + best_signal.strength * 0.4, 1.0)
        elif rank == 2:
            entry_type = "H2"
            confidence = min(state.strength * 0.6 + best_signal.strength * 0.4 + 0.1, 1.0)
        else:
            entry_type = "H3"
            confidence = min(state.strength * 0.6 + best_signal.strength * 0.4 + 0.2, 1.0)

        if state.bias == "long":
            entry_price = bar["high"] + atr * 0.1  # 突破入场
            stop_loss = sw.price - atr * 0.5
            target = entry_price + atr * 2.0
        else:
            entry_price = bar["low"] - atr * 0.1
            stop_loss = sw.price + atr * 0.5
            target = entry_price - atr * 2.0

        entries.append(EntrySignal(
            type=entry_type,
            direction=state.bias,
            confidence=round(confidence, 2),
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target=round(target, 2),
            description=f"{entry_type}入场 ({'多' if state.bias == 'long' else '空'})",
            bar_index=best_signal.index,
            timestamp=df.index[best_signal.index],
        ))

    return entries


# ======================================================================
# 5. 楔形检测
# ======================================================================

def detect_wedges(
    df: pd.DataFrame,
    swings: list[SwingPoint],
) -> list[EntrySignal]:
    """检测楔形形态（3推+收敛）。

    楔形（Wedge）的特征：
    - 同一方向的 3 次推动
    - 每次推动幅度收敛（斜率递减）
    - 价格创新高/低但动能衰减
    - 第3推破趋势线时反向入场
    """
    df = _validate_df(df)
    n = len(df)
    entries: list[EntrySignal] = []

    # 分离高点和低点
    highs = sorted([s for s in swings if s.type == "high"], key=lambda s: s.index)
    lows = sorted([s for s in swings if s.type == "low"], key=lambda s: s.index)

    # 上升楔形（顶部收敛 → 看跌）
    _detect_wedge_direction(df, highs, "high", "short", entries)

    # 下降楔形（底部收敛 → 看涨）
    _detect_wedge_direction(df, lows, "low", "long", entries)

    return entries


def _detect_wedge_direction(
    df: pd.DataFrame,
    points: list[SwingPoint],
    point_type: str,
    breakout_dir: Direction,
    entries: list[EntrySignal],
) -> None:
    """辅助：检测单方向楔形"""
    if len(points) < 3:
        return

    # 取最近 3 个同向摆动点
    recent = points[-3:]
    if len(recent) < 3:
        return

    p1, p2, p3 = recent
    n = len(df)

    # 确保它们在同侧（都在推高或都在推低）
    if point_type == "high":
        # 上升楔形：三个高点，价格越来越高但幅度递减
        if not (p3.price > p2.price > p1.price):
            return
    else:
        # 下降楔形：三个低点，价格越来越低但幅度递减
        if not (p3.price < p2.price < p1.price):
            return

    # 计算推动幅度
    move1 = abs(p2.price - p1.price)
    move2 = abs(p3.price - p2.price)

    if move1 == 0:
        return

    # 检查是否收敛（第3推动幅度小于第2推动）
    convergence = move2 < move1 * 0.85

    # 检查时间上的收敛（间隔变短）
    bars_1_2 = p2.index - p1.index
    bars_2_3 = p3.index - p2.index
    time_convergence = bars_1_2 > 0 and bars_2_3 < bars_1_2 * 0.9

    # 需要幅度收敛或时间收敛
    if not (convergence or time_convergence):
        return

    # 找突破确认：最近一根K线是否破了楔形趋势线
    # 用 p1-p3 连线作为趋势线
    x_vals = np.array([p1.index, p3.index])
    y_vals = np.array([p1.price, p3.price])
    trendline_slope, trendline_intercept = np.polyfit(x_vals, y_vals, 1)

    # 最新 K 线
    latest_idx = n - 1
    trendline_val = trendline_slope * latest_idx + trendline_intercept
    latest_close = df["close"].iloc[-1]

    # 突破判断
    breakout = False
    if point_type == "high" and latest_close < trendline_val:
        breakout = True  # 上升楔形向下突破
    elif point_type == "low" and latest_close > trendline_val:
        breakout = True  # 下降楔形向上突破

    if not breakout:
        return

    # 计算置信度
    conf = 0.6
    if convergence:
        conf += 0.15
    if time_convergence:
        conf += 0.1
    if abs(move2 / move1) < 0.5:
        conf += 0.15  # 强收敛

    atr = _calc_atr(df, 14)
    if atr is None:
        return

    latest = df.iloc[-1]
    if breakout_dir == "long":
        entry_price = latest["high"] + atr * 0.1
        stop_loss = p3.price - atr * 0.5
        target = entry_price + atr * 2.5
    else:
        entry_price = latest["low"] - atr * 0.1
        stop_loss = p3.price + atr * 0.5
        target = entry_price - atr * 2.5

    entries.append(EntrySignal(
        type="wedge_break",
        direction=breakout_dir,
        confidence=round(min(conf, 1.0), 2),
        entry_price=round(entry_price, 2),
        stop_loss=round(stop_loss, 2),
        target=round(target, 2),
        description=f"{'上升' if point_type == 'high' else '下降'}楔形突破 ({'多' if breakout_dir == 'long' else '空'})",
        bar_index=latest_idx,
        timestamp=df.index[latest_idx],
    ))


# ======================================================================
# 5b. 双底牛旗检测（来自Mr.西土瓦 案例1/9/10/11/22/24/25）
# ======================================================================

def detect_double_bottom(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    state: MarketState,
) -> list[EntrySignal]:
    """检测双底牛旗：两个相近低点 + 中间更高低点 + 上涨趋势背景。"""
    entries: list[EntrySignal] = []
    if len(df) < 15 or state.trend not in ("uptrend", "narrow_channel", "wide_channel", "trading_range"):
        return entries

    atr = _calc_atr(df, 14)
    if atr is None:
        return entries

    lows = sorted([s for s in swings if s.type == "low"], key=lambda s: s.index)
    if len(lows) < 3:
        return entries

    n = len(df)
    recent_lows = [s for s in lows if s.index >= n - 50]
    for i in range(len(recent_lows) - 1):
        l1 = recent_lows[i]
        l2 = recent_lows[-1]
        if l2.index - l1.index < 5:
            continue
        price_diff = abs(l1.price - l2.price)
        if price_diff > atr * 0.3:
            continue
        middle_lows = [s for s in recent_lows
                       if l1.index < s.index < l2.index and s.price > max(l1.price, l2.price)]
        if not middle_lows:
            continue

        latest = df.iloc[-1]
        entry_price = l2.price + atr * 0.3
        stop_loss = min(l1.price, l2.price) - atr * 0.3
        target = entry_price + (entry_price - stop_loss) * 2.5

        entries.append(EntrySignal(
            type="double_bottom",
            direction="long",
            confidence=round(min(0.55 + state.strength * 0.25, 0.85), 2),
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target=round(target, 2),
            description=f"双底牛旗: {l1.price:.1f}≈{l2.price:.1f} 间隔{l2.index - l1.index}根",
            bar_index=n - 1,
            timestamp=df.index[-1],
        ))
        break

    return entries


# ======================================================================
# 5c. EMA20 互动系统（来自Mr.西土瓦 案例6/7/8/10/26, 高胜率7/9）
# ======================================================================

def detect_ema_interaction(
    df: pd.DataFrame,
    state: MarketState,
) -> list[EntrySignal]:
    """检测价格与 EMA20 的互动：缺口K线 / 回踩反弹 / 假跌破 / 两次测试失败。"""
    entries: list[EntrySignal] = []
    n = len(df)
    if n < 30:
        return entries

    atr = _calc_atr(df, 14)
    if atr is None:
        return entries

    ema20 = df["close"].ewm(span=20, adjust=False).mean()
    latest_close = df["close"].iloc[-1]
    latest_ema = ema20.iloc[-1]
    latest_low = df["low"].iloc[-1]
    latest_high = df["high"].iloc[-1]

    strong_trend = state.strength >= 0.4 and state.trend in ("uptrend", "narrow_channel")
    if not strong_trend:
        return entries

    # a) EMA20 缺口K线：最近有 bar 高点低于 EMA20，当前 bar 突破其高点
    for i in range(n - 2, max(n - 12, 0), -1):
        if df["high"].iloc[i] < ema20.iloc[i]:
            gap_high = df["high"].iloc[i]
            gap_low = df["low"].iloc[i]
            if latest_close > gap_high:
                entries.append(EntrySignal(
                    type="ema_interaction",
                    direction="long",
                    confidence=round(min(0.60 + state.strength * 0.2, 0.80), 2),
                    entry_price=round(gap_high, 2),
                    stop_loss=round(gap_low, 2),
                    target=round(gap_high + (gap_high - gap_low) * 2.5, 2),
                    description=f"EMA20缺口K线: 突破#{i}高点{gap_high:.1f}",
                    bar_index=n - 1, timestamp=df.index[-1],
                ))
            break

    # b) 回踩 EMA20 反弹
    dist_pct = abs(latest_low - latest_ema) / latest_ema
    if dist_pct < 0.02 and latest_close > df["open"].iloc[-1] and latest_close > latest_ema:
        entries.append(EntrySignal(
            type="ema_interaction",
            direction="long",
            confidence=round(0.55 + state.strength * 0.2, 2),
            entry_price=round(latest_high + atr * 0.1, 2),
            stop_loss=round(latest_low - atr * 0.3, 2),
            target=round(latest_high + atr * 2.5, 2),
            description=f"回踩EMA20反弹: 距EMA{dist_pct:.1%}",
            bar_index=n - 1, timestamp=df.index[-1],
        ))

    # c) EMA20 假跌破：近5根有bar刺破EMA20但收阳收回
    for i in range(n - 2, max(n - 7, 0), -1):
        bar = df.iloc[i]
        if bar["low"] < ema20.iloc[i] and bar["close"] > ema20.iloc[i] and bar["close"] > bar["open"]:
            if latest_close > bar["high"]:
                entries.append(EntrySignal(
                    type="ema_interaction",
                    direction="long",
                    confidence=0.70,
                    entry_price=round(bar["high"] + atr * 0.05, 2),
                    stop_loss=round(bar["low"] - atr * 0.3, 2),
                    target=round(bar["high"] + atr * 3.0, 2),
                    description=f"EMA20假跌破收回: #{i}收阳",
                    bar_index=n - 1, timestamp=df.index[-1],
                ))
            break

    # d) 两次测试 EMA20 失败 → 反转预警
    touches = sum(1 for j in range(n - 3, max(n - 18, 0), -1)
                  if df["high"].iloc[j] > ema20.iloc[j] > df["low"].iloc[j])
    if touches >= 2 and latest_close < latest_ema:
        entries.append(EntrySignal(
            type="ema_interaction",
            direction="short",
            confidence=0.55,
            entry_price=0, stop_loss=0, target=0,
            description=f"EMA20两次测试失败预警: {touches}次穿透",
            bar_index=n - 1, timestamp=df.index[-1],
        ))

    return entries


# ======================================================================
# 5d. 最终旗形反转（来自Mr.西土瓦 案例10, 高胜率16, 2月战绩）
# ======================================================================

def detect_final_flag_reversal(
    df: pd.DataFrame,
    swings: list[SwingPoint],
) -> list[EntrySignal]:
    """检测最终旗形反转：趋势末期→横盘旗形→假突破旗形→反转。"""
    entries: list[EntrySignal] = []
    n = len(df)
    if n < 30:
        return entries

    atr = _calc_atr(df, 14)
    if atr is None:
        return entries

    lows = sorted([s for s in swings if s.type == "low"], key=lambda s: s.index)
    if len(lows) < 2:
        return entries

    recent_low = lows[-1]
    if recent_low.index < n - 20:
        return entries

    flag_start = recent_low.index
    flag_bars = df.iloc[flag_start:n]
    if len(flag_bars) < 3 or len(flag_bars) > 10:
        return entries

    flag_high = flag_bars["high"].max()
    flag_low = flag_bars["low"].min()
    flag_range = flag_high - flag_low
    if flag_range > atr * 1.5:
        return entries

    for i in range(flag_start + len(flag_bars), n):
        bar = df.iloc[i]
        if bar["low"] < flag_low and bar["close"] > flag_low:
            latest = df.iloc[-1]
            if latest["close"] > bar["high"]:
                entries.append(EntrySignal(
                    type="final_flag_reversal",
                    direction="long",
                    confidence=0.70,
                    entry_price=round(bar["high"], 2),
                    stop_loss=round(bar["low"], 2),
                    target=round(bar["high"] + (bar["high"] - bar["low"]) * 3.0, 2),
                    description=f"最终旗形反转: 旗形{len(flag_bars)}根 假破后收",
                    bar_index=n - 1, timestamp=df.index[-1],
                ))
            break

    return entries


# ======================================================================
# 5e. 真空效应检测（来自Mr.西土瓦 案例24, 被套篇, 卖飞篇）
# ======================================================================

def detect_vacuum_effect(
    df: pd.DataFrame,
    state: MarketState,
) -> list[EntrySignal]:
    """检测真空效应：大阴/阳线急速运动到S/R位 → 强势反转。"""
    entries: list[EntrySignal] = []
    n = len(df)
    if n < 20:
        return entries

    atr = _calc_atr(df, 14)
    if atr is None:
        return entries

    recent = df.iloc[-10:]
    latest = df.iloc[-1]

    for i in range(len(recent) - 2, max(len(recent) - 6, 0), -1):
        bar = recent.iloc[i]
        body = abs(bar["close"] - bar["open"])
        total = bar["high"] - bar["low"]
        if total == 0:
            continue
        if bar["close"] < bar["open"] and body / total > 0.6:
            near_support = False
            support_desc = ""
            if state.channel_bottom and abs(bar["low"] - state.channel_bottom) / state.channel_bottom < 0.02:
                near_support = True
                support_desc = f"通道底{state.channel_bottom:.1f}"
            if not near_support and state.swing_lows:
                for sl in state.swing_lows:
                    if sl.index >= n - 30 and abs(bar["low"] - sl.price) / sl.price < 0.02:
                        near_support = True
                        support_desc = f"前低{sl.price:.1f}"
                        break
            if near_support and latest["close"] > latest["open"]:
                entries.append(EntrySignal(
                    type="vacuum_effect",
                    direction="long",
                    confidence=0.65,
                    entry_price=round(latest["high"] + atr * 0.05, 2),
                    stop_loss=round(bar["low"] - atr * 0.3, 2),
                    target=round(latest["high"] + atr * 2.5, 2),
                    description=f"真空效应反转: 急跌至{support_desc}收回",
                    bar_index=n - 1, timestamp=df.index[-1],
                ))
            break

    return entries


# ======================================================================
# 5f. 水平压力/支撑位（来自Mr.西土瓦 案例10/22, 卖飞篇, 高胜率12）
# ======================================================================

def detect_horizontal_sr(
    df: pd.DataFrame,
    state: MarketState,
) -> list[EntrySignal]:
    """检测水平S/R位：多根影线聚集在同一价位 → 压力/支撑。"""
    entries: list[EntrySignal] = []
    n = len(df)
    if n < 20:
        return entries

    atr = _calc_atr(df, 14)
    if atr is None:
        return entries

    recent = df.iloc[-30:]
    upper_wicks = []
    lower_wicks = []

    for i in range(len(recent)):
        bar = recent.iloc[i]
        body_high = max(bar["open"], bar["close"])
        body_low = min(bar["open"], bar["close"])
        upper_w = bar["high"] - body_high
        lower_w = body_low - bar["low"]
        total_r = bar["high"] - bar["low"]
        if total_r == 0:
            continue
        if upper_w / total_r > 0.4:
            upper_wicks.append(bar["high"])
        if lower_w / total_r > 0.4:
            lower_wicks.append(bar["low"])

    latest = df.iloc[-1]

    if len(upper_wicks) >= 3:
        cluster = np.mean(upper_wicks)
        if abs(latest["high"] - cluster) / cluster < 0.01 and latest["close"] < latest["open"]:
            entries.append(EntrySignal(
                type="horizontal_sr",
                direction="short",
                confidence=0.55,
                entry_price=0, stop_loss=0, target=0,
                description=f"水平压力位{cluster:.2f}({len(upper_wicks)}影线)",
                bar_index=n - 1, timestamp=df.index[-1],
            ))

    if len(lower_wicks) >= 3:
        cluster = np.mean(lower_wicks)
        if abs(latest["low"] - cluster) / cluster < 0.01 and latest["close"] > latest["open"]:
            entries.append(EntrySignal(
                type="horizontal_sr",
                direction="long",
                confidence=0.60,
                entry_price=round(latest["high"] + atr * 0.05, 2),
                stop_loss=round(cluster - atr * 0.3, 2),
                target=round(latest["high"] + atr * 2.0, 2),
                description=f"水平支撑位{cluster:.2f}({len(lower_wicks)}影线)",
                bar_index=n - 1, timestamp=df.index[-1],
            ))

    return entries


# ======================================================================
# 5g. 测量缺口（来自Mr.西土瓦 高胜率6）
# ======================================================================

def detect_measuring_gap(
    df: pd.DataFrame,
    state: MarketState,
) -> list[EntrySignal]:
    """检测测量缺口：上涨趋势回调缺口 → 缺口上沿做多。"""
    entries: list[EntrySignal] = []
    n = len(df)
    if n < 5:
        return entries

    if state.trend not in ("uptrend", "narrow_channel") or state.strength < 0.3:
        return entries

    atr = _calc_atr(df, 14)
    if atr is None:
        return entries

    for i in range(n - 4, max(n - 12, 0), -1):
        if i < 2:
            continue
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        next_bar = df.iloc[i + 1] if i + 1 < n else None
        if next_bar is None:
            continue
        if curr["close"] <= curr["open"] or curr["high"] <= prev["high"]:
            continue
        gap = next_bar["low"] - prev["high"]
        if gap < atr * 0.05:
            continue

        latest = df.iloc[-1]
        gap_top = prev["high"]
        if abs(latest["close"] - gap_top) / gap_top < 0.02:
            entries.append(EntrySignal(
                type="measuring_gap",
                direction="long",
                confidence=0.60,
                entry_price=round(gap_top + atr * 0.1, 2),
                stop_loss=round(next_bar["low"] - atr * 0.3, 2),
                target=round(gap_top + (curr["high"] - prev["low"]) * 2, 2),
                description=f"测量缺口: {gap_top:.2f} 宽{gap/atr:.1f}ATR",
                bar_index=n - 1, timestamp=df.index[-1],
            ))
            break

    return entries


# ======================================================================
# 5h. 急速与通道（来自Mr.西土瓦 高胜率10, 案例1/9/11, 多篇战绩）
# ======================================================================

def _spike_bars_strong(df: pd.DataFrame, start: int, end: int) -> bool:
    """验证急速段：所有 bar 必须阳线 + 实体 ≥ 50% 振幅。"""
    seg = df.iloc[start:end + 1]
    for _, bar in seg.iterrows():
        if bar["close"] <= bar["open"]:
            return False
        rng = bar["high"] - bar["low"]
        if rng > 0 and (bar["close"] - bar["open"]) / rng < 0.5:
            return False
    return True


def detect_spike_channel(
    df: pd.DataFrame,
    state: MarketState,
    swings: list[SwingPoint],
) -> list[EntrySignal]:
    """检测急速与通道模型：急速上涨→回调→等距通道上涨（3推）→双底回测。

    阿布经典高胜率模型。两种入场：
    A: 通道内回调买入（知道目标位）
    B: 通道完成后回测通道起点=双底牛旗买入（更安全）
    """
    entries: list[EntrySignal] = []
    if len(df) < 30 or state.bias != "long":
        return entries

    atr = _calc_atr(df, 14)
    if atr is None:
        return entries

    highs = sorted([s for s in swings if s.type == "high"], key=lambda s: s.index)
    lows = sorted([s for s in swings if s.type == "low"], key=lambda s: s.index)
    if len(highs) < 4 or len(lows) < 3:
        return entries

    n = len(df)
    # 扫描最近的 swing low → swing high 对作为候选 spike
    for i in range(len(lows) - 1):
        spike_low = lows[i]
        if spike_low.index > n - 40:
            continue
        # 找该 low 之后的第一个 swing high
        later_highs = [h for h in highs if h.index > spike_low.index]
        if not later_highs:
            continue
        spike_high = later_highs[0]
        spike_height = spike_high.price - spike_low.price
        spike_bars = spike_high.index - spike_low.index

        if spike_height < atr * 1.5 or spike_bars > 8:
            continue
        if not _spike_bars_strong(df, spike_low.index, spike_high.index):
            continue

        # 找 spike high 之后的第一个 swing low（回调）
        later_lows = [l for l in lows if l.index > spike_high.index]
        if not later_lows:
            continue
        pullback = later_lows[0]
        retrace = (spike_high.price - pullback.price) / spike_height
        if not (0.15 <= retrace <= 0.80):
            continue

        # 找回调后的 3 个 swing high（通道三推）
        ch_highs = [h for h in highs if h.index > pullback.index][:3]
        if len(ch_highs) < 3:
            continue
        h1, h2, h3 = ch_highs[0], ch_highs[1], ch_highs[2]
        if not (h3.price > h2.price > h1.price > pullback.price):
            continue

        channel_height = h3.price - pullback.price
        ratio = channel_height / spike_height
        if not (0.70 <= ratio <= 1.40):
            continue

        latest = df.iloc[-1]
        latest_close = latest["close"]

        # Entry A: 在通道内（未到顶）→ 通道内买入
        if latest_close < h3.price and latest_close > pullback.price:
            entries.append(EntrySignal(
                type="spike_channel",
                direction="long",
                confidence=0.55,
                entry_price=round(latest["high"] + atr * 0.1, 2),
                stop_loss=round(pullback.price - atr * 0.3, 2),
                target=round(pullback.price + spike_height, 2),
                description=f"急速与通道(A): spike{spike_height/atr:.1f}ATR 等距{ratio:.0%}",
                bar_index=n - 1, timestamp=df.index[-1],
            ))

        # Entry B: 价格回落到通道起点附近 → 双底买入
        dist_from_start = abs(latest_close - pullback.price) / pullback.price
        if dist_from_start < 0.03:
            entries.append(EntrySignal(
                type="spike_channel",
                direction="long",
                confidence=0.70,
                entry_price=round(latest["high"] + atr * 0.1, 2),
                stop_loss=round(pullback.price - atr * 0.5, 2),
                target=round(pullback.price + spike_height, 2),
                description=f"急速与通道(B): 回测通道起点{pullback.price:.1f}双底",
                bar_index=n - 1, timestamp=df.index[-1],
            ))
        break

    return entries


# ======================================================================
# 5i. 趋势恢复交易日（来自Mr.西土瓦 案例21, 胜率依旧篇）
# ======================================================================

def detect_trend_resumption_day(
    df: pd.DataFrame,
    state: MarketState,
    swings: list[SwingPoint],
) -> list[EntrySignal]:
    """检测趋势恢复日模型：强势上涨→弱回调→突破前高恢复趋势。

    隔夜/波段交易利器。特征：
    - 前期强势上涨（impulse leg）
    - 回调浅而有序（小实体、重叠、不破EMA20太远）
    - 当前 bar 突破前一根 bar 高点 → 趋势恢复
    """
    entries: list[EntrySignal] = []
    n = len(df)
    if n < 40 or state.bias != "long" or state.strength < 0.4:
        return entries

    atr = _calc_atr(df, 14)
    if atr is None:
        return entries

    # Step 1: 找前期强势上涨（impulse）
    recent_range = df.iloc[-30:]
    impulse_peak_idx = recent_range["high"].idxmax()
    impulse_peak_pos = df.index.get_loc(impulse_peak_idx)

    prior_lows = [s for s in swings if s.type == "low" and s.index < impulse_peak_pos]
    if not prior_lows:
        return entries
    impulse_trough = prior_lows[-1]
    impulse_height = df.iloc[impulse_peak_pos]["high"] - impulse_trough.price
    if impulse_height <= 0 or impulse_height < atr * 1.5:
        return entries

    # Step 2: 验证弱回调
    pullback_bars = df.iloc[impulse_peak_pos:n]
    pb_len = len(pullback_bars)
    if pb_len < 3 or pb_len > 30:
        return entries

    pb_low = pullback_bars["low"].min()
    retrace_pct = (df.iloc[impulse_peak_pos]["high"] - pb_low) / impulse_height
    if retrace_pct > 0.38:
        return entries  # 回调太深

    # 回调的 bar 是否"弱"（小实体）
    body_ratios = []
    for i in range(len(pullback_bars)):
        bar = pullback_bars.iloc[i]
        body = abs(bar["close"] - bar["open"])
        rng = bar["high"] - bar["low"]
        if rng > 0:
            body_ratios.append(body / rng)
    avg_body = np.mean(body_ratios) if body_ratios else 1.0
    if avg_body > 0.5:
        return entries  # bar 太大，不是"弱"回调

    # Step 3: 检测恢复信号 → 当前 bar 突破前 bar 高点
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    if curr["high"] <= prev["high"]:
        return entries  # 未突破

    # 开盘价不能低太多（显示 urgency）
    open_vs_prev = (curr["open"] - prev["high"]) / prev["high"]
    if open_vs_prev < -0.03:
        return entries

    # Step 4: 构建信号
    confidence = min(0.55 + state.strength * 0.15 + (1.0 - retrace_pct) * 0.2, 0.90)

    entries.append(EntrySignal(
        type="trend_resumption_day",
        direction="long",
        confidence=round(confidence, 2),
        entry_price=round(prev["high"] + atr * 0.05, 2),
        stop_loss=round(prev["low"] - atr * 0.5, 2),
        target=round(prev["high"] + impulse_height * 0.8, 2),
        description=f"趋势恢复日: 涨幅{impulse_height/atr:.1f}ATR 回调{retrace_pct:.0%}",
        bar_index=n - 1,
        timestamp=df.index[-1],
    ))

    return entries


# ======================================================================
# 6. 失败突破检测 (80% 规则)
# ======================================================================

def detect_failed_breakouts(df: pd.DataFrame) -> list[EntrySignal]:
    """检测失败突破（80% 规则）。

    当价格突破区间边界后，回撤超过突破幅度的 80%，
    则判定为失败突破，应向反方向交易。
    """
    df = _validate_df(df)
    n = len(df)
    entries: list[EntrySignal] = []

    if n < 40:
        return entries

    # 用滚动窗口找区间
    window = min(30, n // 2)
    lookback = df.iloc[-window * 2: -window] if n > window * 2 else df.iloc[:window]
    recent = df.iloc[-window:]

    range_high = lookback["high"].max()
    range_low = lookback["low"].min()
    range_size = range_high - range_low

    if range_size == 0 or range_size / range_low < 0.005:  # 区间太小忽略
        return entries

    # 检查向上突破失败
    breakout_high = recent["high"].max()
    if breakout_high > range_high:
        # 有向上突破
        breakout_idx = recent["high"].idxmax()
        breakout_pos = recent.index.get_loc(breakout_idx)
        breakout_value = breakout_high
        breakout_size = breakout_value - range_high

        # 突破后的最低点
        if breakout_pos < len(recent) - 1:
            after_breakout = recent.iloc[breakout_pos:]
            pullback_low = after_breakout["low"].min()
            retrace = (breakout_value - pullback_low) / breakout_size * 100

            if retrace >= 80:
                atr_val = _calc_atr(df, 14)
                if atr_val:
                    latest = df.iloc[-1]
                    entries.append(EntrySignal(
                        type="failed_breakout",
                        direction="short",
                        confidence=min(retrace / 100, 1.0),
                        entry_price=round(latest["low"] - atr_val * 0.1, 2),
                        stop_loss=round(breakout_value + atr_val * 0.3, 2),
                        target=round(range_low, 2),
                        description=f"向上假突破 {retrace:.0f}%回撤 → 做空",
                        bar_index=n - 1,
                        timestamp=df.index[-1],
                    ))

    # 检查向下突破失败
    breakout_low = recent["low"].min()
    if breakout_low < range_low:
        breakout_idx = recent["low"].idxmin()
        breakout_pos = recent.index.get_loc(breakout_idx)
        breakout_value = breakout_low
        breakout_size = range_low - breakout_value

        if breakout_pos < len(recent) - 1:
            after_breakout = recent.iloc[breakout_pos:]
            pullback_high = after_breakout["high"].max()
            retrace = (pullback_high - breakout_value) / breakout_size * 100

            if retrace >= 80:
                atr_val = _calc_atr(df, 14)
                if atr_val:
                    latest = df.iloc[-1]
                    entries.append(EntrySignal(
                        type="failed_breakout",
                        direction="long",
                        confidence=min(retrace / 100, 1.0),
                        entry_price=round(latest["high"] + atr_val * 0.1, 2),
                        stop_loss=round(breakout_value - atr_val * 0.3, 2),
                        target=round(range_high, 2),
                        description=f"向下假突破 {retrace:.0f}%回撤 → 做多",
                        bar_index=n - 1,
                        timestamp=df.index[-1],
                    ))

    return entries


# ======================================================================
# 8. #23 阴线高点做多（bear_bar_long）
# 阿布理论23: 强上涨趋势中连续阳线后出现阴线→突破阴线高点做多
# ======================================================================

def detect_bear_bar_long(
    df: pd.DataFrame, state: MarketState, signal_bars: list[SignalBar]
) -> list[EntrySignal]:
    """检测「阴线高点做多」信号。

    条件:
      1. 市场处于上涨趋势（strength >= 0.4）
      2. 最近出现一根阴线（收盘 < 开盘）
      3. 当前K线收盘突破该阴线高点
      4. 不能是交易区间（80%规则不适用）
    """
    entries: list[EntrySignal] = []
    if len(df) < 5 or state.trend not in ("uptrend", "narrow_channel"):
        return entries

    n = len(df)
    atr_val = _calc_atr(df, 14)

    # 找最近2-5根K线内的阴线
    for lookback in range(2, min(6, n)):
        bear_idx = n - lookback
        bear_bar = df.iloc[bear_idx]
        if bear_bar["close"] >= bear_bar["open"]:
            continue  # 不是阴线

        # 确认之前是阳线主导（上涨趋势特征）
        prev_bars = df.iloc[bear_idx - 3:bear_idx]
        bull_count = sum(1 for i in range(len(prev_bars)) if prev_bars.iloc[i]["close"] > prev_bars.iloc[i]["open"])
        if bull_count < 2:
            continue

        # 当前K线突破阴线高点
        latest = df.iloc[-1]
        if latest["close"] > bear_bar["high"]:
            confidence = 0.55 + state.strength * 0.15  # 0.55-0.70
            entry_price = bear_bar["high"]
            stop_loss = bear_bar["low"]
            target = entry_price + (entry_price - stop_loss) * 2  # 2:1 R:R

            entries.append(EntrySignal(
                type="bear_bar_long",
                direction="long",
                confidence=round(min(confidence, 1.0), 2),
                entry_price=round(entry_price, 2),
                stop_loss=round(stop_loss, 2),
                target=round(target, 2),
                description=f"#23 阴线高点做多: 强趋势中突破阴线高点 {entry_price:.1f}",
                bar_index=n - 1,
                timestamp=df.index[-1],
            ))
            break  # 只取最近一个

    return entries


# ======================================================================
# 9. #19 最强盈利工具 — 支撑背叛反转（support_betrayal_long）
# 阿布理论19: 先跌破重要支撑→迅速反转向上，套住多空双方
# ======================================================================

def detect_support_betrayal(
    df: pd.DataFrame, state: MarketState, swings: list[SwingPoint]
) -> list[EntrySignal]:
    """检测「支撑背叛反转」信号 — 阿布称为最强的盈利工具。

    模式:
      1. 存在一个明显的支撑位（近期摆动低点或区间底部）
      2. 价格向下跌破支撑
      3. 在1-3根K线内迅速反转回到支撑上方
      4. 形成「陷阱」— 空头被套，多头被洗
    """
    entries: list[EntrySignal] = []
    if len(df) < 15:
        return entries

    # 只做多方向（下跌趋势中不做这个模式）
    if state.trend == "downtrend":
        return entries

    n = len(df)
    atr_val = _calc_atr(df, 14)

    # 找最近的支撑位：近期摆动低点或通道底部
    support_candidates: list[tuple[float, str]] = []
    if state.channel_bottom:
        support_candidates.append((state.channel_bottom, "通道底部"))
    if state.swing_lows:
        recent_lows = [s for s in state.swing_lows if s.index >= n - 30]
        if recent_lows:
            avg_low = np.mean([s.price for s in recent_lows])
            support_candidates.append((avg_low, "近期摆动低点均值"))

    if not support_candidates:
        return entries

    # 检查最近5根K线是否有「跌破→反转」模式
    for support_val, support_name in support_candidates:
        for i in range(n - 5, n):
            bar = df.iloc[i]
            # 跌破支撑
            if bar["low"] < support_val:
                # 检查后续是否反转回到支撑上方
                recovery_bars = df.iloc[i + 1:n]
                if len(recovery_bars) == 0:
                    continue

                for j in range(len(recovery_bars)):
                    rec = recovery_bars.iloc[j]
                    if rec["close"] > support_val:
                        # 确认反转！在1-3根K线内完成 = 高确信度
                        bars_to_recover = j + 1
                        urgency = 1.0 if bars_to_recover <= 2 else 0.8

                        # 计算入场: 突破翻转K线高点
                        latest = df.iloc[-1]
                        entry_price = rec["high"]
                        stop_loss = bar["low"]  # 止损在假突破最低点
                        target = support_val + (support_val - stop_loss) * 2

                        entries.append(EntrySignal(
                            type="support_betrayal_long",
                            direction="long",
                            confidence=round(0.60 * urgency, 2),
                            entry_price=round(entry_price, 2),
                            stop_loss=round(stop_loss, 2),
                            target=round(target, 2),
                            description=f"#19 支撑背叛反转: 假破{support_name}{support_val:.0f}→{bars_to_recover}根内收回",
                            bar_index=n - 1,
                            timestamp=df.index[-1],
                        ))
                        break
                break  # 找到第一个就停

    return entries


# ======================================================================
# 10. #21 高潮预警 + #32 区间中点
# ======================================================================

def detect_climax(df: pd.DataFrame) -> list[EntrySignal]:
    """检测交易高潮 — 连续大阳/大阴加速 = 风险信号。

    阿布理论21: 加速=弱势交易者最后入场+弱势对手认输→风险来临
    """
    entries: list[EntrySignal] = []
    if len(df) < 10:
        return entries

    n = len(df)
    recent = df.iloc[-10:]

    # 连续大阳线计数
    bull_bars = 0
    bear_bars = 0
    for i in range(len(recent)):
        bar = recent.iloc[i]
        body = abs(bar["close"] - bar["open"])
        range_val = bar["high"] - bar["low"]
        if range_val == 0:
            continue
        # 实体占比 > 60%，且几乎无重叠
        if bar["close"] > bar["open"] and body / range_val > 0.6:
            if i > 0 and recent.iloc[i - 1]["high"] < bar["high"]:
                bull_bars += 1
        elif bar["close"] < bar["open"] and body / range_val > 0.6:
            if i > 0 and recent.iloc[i - 1]["low"] > bar["low"]:
                bear_bars += 1

    # 5根以上连续同向强势K线 = 高潮
    if bull_bars >= 5:
        entries.append(EntrySignal(
            type="climax_warning",
            direction="long",
            confidence=0.75,
            entry_price=0, stop_loss=0, target=0,
            description=f"#21 高潮预警: {bull_bars}根连续强阳线加速，注意回调风险",
            bar_index=n - 1, timestamp=df.index[-1],
        ))
    elif bear_bars >= 5:
        entries.append(EntrySignal(
            type="climax_warning",
            direction="short",
            confidence=0.75,
            entry_price=0, stop_loss=0, target=0,
            description=f"#21 高潮预警: {bear_bars}根连续强阴线加速，注意反弹风险",
            bar_index=n - 1, timestamp=df.index[-1],
        ))

    return entries


def compute_range_midpoint(df: pd.DataFrame, state: MarketState) -> Optional[float]:
    """计算区间中点 — 阿布理论32: 磁力位，止盈参考"""
    if state.trend != "trading_range" or len(df) < 20:
        return None
    recent = df.iloc[-50:]
    high = recent["high"].max()
    low = recent["low"].min()
    return round((high + low) / 2, 2)

def compute_technical_score(
    df: pd.DataFrame,
    state: MarketState,
    signal_bars: list[SignalBar],
    entry_signals: list[EntrySignal],
) -> TechnicalScore:
    """综合所有技术分析结果，输出 0-100 评分。

    评分构成：
    - 趋势清晰度 (30 分): 趋势越明确分越高
    - 信号K线质量 (25 分): 近期有高质量信号K线
    - 入场形态质量 (25 分): 有明确的入场形态（H2/H3/楔形 > H1）
    - 高级信号加分 (10 分): #19支撑背叛 / #23阴线做多
    - 高潮预警 (扣10 分): 连续加速K线=风险
    - 市场背景 (20 分): 价格位置是否有利（非极端位）
    """
    df = _validate_df(df)
    n = len(df)

    # --- 趋势清晰度 (0-30) ---
    trend_score = state.strength * 30

    # --- 信号K线质量 (0-25) ---
    if n >= 20:
        recent_signals = [s for s in signal_bars if s.index >= n - 20]
    else:
        recent_signals = signal_bars

    if recent_signals:
        # 信号K线数量 + 平均强度
        count_score = min(len(recent_signals) / 3, 1.0)
        avg_strength = np.mean([s.strength for s in recent_signals])
        # 方向一致性加分
        if state.bias == "long":
            bullish_signals = [s for s in recent_signals
                               if s.type in ("strong_bullish", "pin_bar_bullish", "outside_bar_bullish")]
            consistency = len(bullish_signals) / len(recent_signals) if recent_signals else 0
        elif state.bias == "short":
            bearish_signals = [s for s in recent_signals
                               if s.type in ("strong_bearish", "pin_bar_bearish", "outside_bar_bearish")]
            consistency = len(bearish_signals) / len(recent_signals) if recent_signals else 0
        else:
            consistency = 0.5
        signal_score = (count_score * 0.4 + avg_strength * 0.3 + consistency * 0.3) * 25
    else:
        signal_score = 0

    # --- 入场形态质量 (0-25) ---
    if entry_signals:
        best_entry = max(entry_signals, key=lambda e: e.confidence)
        entry_type_bonus = {
            "H1": 0.5,
            "H2": 0.7,
            "H3": 0.85,
            "wedge_break": 0.9,
            "failed_breakout": 0.85,
            "bear_bar_long": 0.75,
            "support_betrayal_long": 0.95,
            "climax_warning": 0.0,
            "double_bottom": 0.80,
            "ema_interaction": 0.75,
            "final_flag_reversal": 0.85,
            "vacuum_effect": 0.70,
            "horizontal_sr": 0.65,
            "measuring_gap": 0.70,
            "spike_channel": 0.85,
            "trend_resumption_day": 0.85,
        }.get(best_entry.type, 0.5)
        entry_score = best_entry.confidence * entry_type_bonus * 25
    else:
        entry_score = 0

    # --- 高级信号加分 0-10 (#19, #23) ---
    advanced_bonus = 0.0
    has_bear_bar = any(e.type == "bear_bar_long" for e in entry_signals)
    has_betrayal = any(e.type == "support_betrayal_long" for e in entry_signals)
    if has_betrayal:
        advanced_bonus += 8  # #19 最强盈利工具
    elif has_bear_bar:
        advanced_bonus += 5  # #23 阴线高点做多

    # --- 高潮预警扣分 0-10 (#21) ---
    climax_penalty = 0.0
    climax_signals = [e for e in entry_signals if e.type == "climax_warning"]
    if climax_signals:
        climax_penalty = min(10, len(climax_signals) * 5)

    # --- 市场背景 (0-20) ---
    context_score = 10.0

    if state.trend == "trading_range":
        # 区间内：价格在边缘比在中间好
        if state.channel_top and state.channel_bottom:
            latest_close = df["close"].iloc[-1]
            range_mid = (state.channel_top + state.channel_bottom) / 2
            dist_from_mid = abs(latest_close - range_mid)
            half_range = abs(state.channel_top - state.channel_bottom) / 2
            if half_range > 0:
                edge_ratio = dist_from_mid / half_range
                context_score += edge_ratio * 10  # 越靠边缘分越高
    else:
        # 趋势中：回调位置好（不过度延伸）
        if n >= 20:
            ma20 = df["close"].iloc[-20:].mean()
            latest_close = df["close"].iloc[-1]
            deviation = abs(latest_close - ma20) / ma20 * 100
            if deviation < 2:
                context_score += 8  # 接近均线，好位置
            elif deviation < 5:
                context_score += 4
            else:
                context_score -= 2  # 过度延伸

    context_score = max(0, min(20, context_score))

    # --- 汇总 ---
    total = int(round(trend_score + signal_score + entry_score +
                      advanced_bonus - climax_penalty + context_score))
    total = max(0, min(100, total))

    # 方向判定
    direction: Direction | None = state.bias
    if direction is None and entry_signals:
        direction = entry_signals[-1].direction

    # 一句话总结
    if total >= 70:
        dir_str = f"偏{'多' if direction == 'long' else '空' if direction == 'short' else '中性'}"
        summary = f"技术面偏强({total}分)，{dir_str}，{state.description}"
    elif total >= 40:
        summary = f"技术面中性({total}分)，{state.description}"
    else:
        summary = f"技术面偏弱({total}分)，建议观望，{state.description}"

    return TechnicalScore(
        score=total,
        direction=direction,
        breakdown={
            "趋势清晰度": round(trend_score, 1),
            "信号K线质量": round(signal_score, 1),
            "入场形态质量": round(entry_score, 1),
            "高级信号(#19/#23)": round(advanced_bonus, 1),
            "高潮预警扣分": round(-climax_penalty, 1),
            "市场背景": round(context_score, 1),
        },
        summary=summary,
    )


# ======================================================================
# 组合入口
# ======================================================================

def analyze(df: pd.DataFrame) -> dict:
    """一键分析：市场结构 + 信号K线 + 入场信号 + 技术评分。

    Args:
        df: OHLCV DataFrame（来自 collector.get_klines 或 fetch_historical）

    Returns:
        dict with keys: state, signal_bars, entry_signals, wedges,
                        failed_breakouts, technical_score, swings
    """
    df = _validate_df(df)

    if len(df) < 20:
        return {
            "state": MarketState(
                trend="trading_range", strength=0.0, bias=None,
                description="数据不足（需要至少20根K线）",
            ),
            "signal_bars": [],
            "entry_signals": [],
            "wedges": [],
            "failed_breakouts": [],
            "technical_score": TechnicalScore(
                score=0, direction=None,
                breakdown={"趋势清晰度": 0, "信号K线质量": 0,
                          "入场形态质量": 0, "市场背景": 0},
                summary="数据不足",
            ),
            "swings": {"minor": [], "major": []},
        }

    minor_swings, major_swings = find_swing_points(df)
    all_swings = sorted(minor_swings, key=lambda s: s.index)

    state = analyze_structure(df)
    signal_bars = detect_signal_bars(df)
    entry_signals = detect_entry_signals(df, state, signal_bars, all_swings)
    wedges = detect_wedges(df, all_swings)
    failed_breakouts = detect_failed_breakouts(df)
    bear_bar_longs = detect_bear_bar_long(df, state, signal_bars)
    support_betrayals = detect_support_betrayal(df, state, all_swings)
    climax_warnings = detect_climax(df)
    # 新增: Mr.西土瓦 策略合入
    double_bottoms = detect_double_bottom(df, all_swings, state)
    ema_signals = detect_ema_interaction(df, state)
    final_flags = detect_final_flag_reversal(df, all_swings)
    vacuum_effects = detect_vacuum_effect(df, state)
    horizontal_srs = detect_horizontal_sr(df, state)
    measuring_gaps = detect_measuring_gap(df, state)
    spike_channels = detect_spike_channel(df, state, all_swings)
    trend_resumptions = detect_trend_resumption_day(df, state, all_swings)

    all_entries = (entry_signals + wedges + failed_breakouts +
                   bear_bar_longs + support_betrayals + climax_warnings +
                   double_bottoms + ema_signals + final_flags +
                   vacuum_effects + horizontal_srs + measuring_gaps +
                   spike_channels + trend_resumptions)
    tech_score = compute_technical_score(df, state, signal_bars, all_entries)

    # 区间中点
    range_mid = compute_range_midpoint(df, state)

    logger.info(f"分析完成: {state.description} | 评分={tech_score.score} | "
                f"信号K线={len(signal_bars)} 入场={len(all_entries)}")

    return {
        "state": state,
        "signal_bars": signal_bars,
        "entry_signals": entry_signals,
        "wedges": wedges,
        "failed_breakouts": failed_breakouts,
        "bear_bar_longs": bear_bar_longs,
        "support_betrayals": support_betrayals,
        "climax_warnings": climax_warnings,
        "double_bottoms": double_bottoms,
        "ema_signals": ema_signals,
        "final_flags": final_flags,
        "vacuum_effects": vacuum_effects,
        "horizontal_srs": horizontal_srs,
        "measuring_gaps": measuring_gaps,
        "spike_channels": spike_channels,
        "trend_resumptions": trend_resumptions,
        "range_midpoint": range_mid,
        "technical_score": tech_score,
        "swings": {"minor": minor_swings, "major": major_swings},
    }


# ======================================================================
# 工具函数
# ======================================================================

def _calc_atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """计算 ATR (Average True Range) 最新值"""
    if len(df) < period + 1:
        return None
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    tr_list = []
    for i in range(1, len(df)):
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
        tr_list.append(tr)

    if len(tr_list) < period:
        return None

    # Wilder's smoothed ATR
    atr = np.mean(tr_list[:period])
    for i in range(period, len(tr_list)):
        atr = (atr * (period - 1) + tr_list[i]) / period

    return float(atr)
