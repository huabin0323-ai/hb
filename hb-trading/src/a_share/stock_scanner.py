"""Phase 1-3: A股全量粗筛 → PA结构 → 信号扫描+决策

Phase 1: 全市场粗筛 (5000→~200)
Phase 2: PA结构判定 (日线, 全部~200只)
Phase 3: 信号扫描 + 决策 (每只: 买入/不动, TOP5)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional, Literal

import akshare as ak
import numpy as np
import pandas as pd

logger = logging.getLogger("pa_pipeline.scanner")

# ======================================================================
# Config
# ======================================================================

OUTPUT_DIR = Path("D:/hb/output")

# Phase 1 粗筛条件
MIN_DAYS_LISTED = 60
MIN_AVG_AMOUNT_YI = 1.0         # 近20日日均成交额（亿）
MIN_AVG_AMPLITUDE_PCT = 3.0     # 近20日日均振幅（%）
MIN_PRICE = 5.0                  # 最低股价
EXCLUDE_ST = True
EXCLUDE_LIMIT_LOCKED = True      # 排除涨跌停封死

# Phase 3 评分权重
SCORE_SIGNAL_MAX = 50
SCORE_CONFIRM_RANGE = (-30, 30)
SCORE_VOLUME_RANGE = (-20, 20)
SCORE_RR_RANGE = (-10, 10)

DecisionType = Literal["买入", "不动"]
DirectionType = Literal["多", "空", None]
SignalType = Literal[
    "H2回调", "L2回调", "窄通道突破", "旗形突破", "20EMA弹跳",
    "楔形反转", "失败突破", "双顶双底", "高潮反转", "Pin Bar反转",
    "平台突破", "回踩不破", "炸板回封", "跌停翘板",
    None,
]


# ======================================================================
# Data structures
# ======================================================================

@dataclass
class StockSnapshot:
    """个股快照（Phase 1输出）"""
    code: str
    name: str
    close: float
    pct_change: float
    volume: float           # 成交量（手）
    amount: float            # 成交额（元）
    amplitude: float         # 振幅（%）
    turnover_rate: float     # 换手率（%）
    total_market_cap: float  # 总市值（亿）
    circ_market_cap: float   # 流通市值（亿）


@dataclass
class PAStructure:
    """PA结构判定（Phase 2输出）"""
    code: str
    name: str
    trend: str               # "上升趋势"|"下降趋势"|"交易区间"|"无法判定"
    stage: int                # 1-4 (Spike/窄通道/宽通道/区间)
    channel: str              # "窄通道"|"宽通道"|"—"
    swing_structure: str      # "HH+HL"|"LH+LL"|"无序列"|"混乱"
    structure_score: int      # 0-100
    key_levels: dict          # {support, resistance, ema20, ema50, high20, low20}
    ema20_direction: str


@dataclass
class PASignal:
    """PA信号（Phase 3输出）"""
    code: str
    name: str
    signal_type: SignalType
    direction: DirectionType
    base_score: int           # 信号基础分 0-50
    confirm_score: int        # 60min确认分 -30~+30
    volume_score: int         # 量能分 -20~+20
    rr_score: int             # R:R分 -10~+10
    risk_penalty: int         # A股风险扣分
    total_score: int          # 总分 0-110
    decision: DecisionType
    decision_reason: str      # 决策原因
    # 交易计划（仅买入信号有值）
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    rr_ratio: Optional[float] = None
    max_loss_pct: Optional[float] = None
    # 详细信息
    pa_reason: str = ""
    risk_flags: list[str] = field(default_factory=list)
    structure: Optional[PAStructure] = None


@dataclass
class ScanResult:
    """完整扫描结果"""
    date: str
    total_scanned: int
    phase1_passed: int
    phase1_candidates: list[StockSnapshot]
    phase2_structures: list[PAStructure]
    phase3_signals: list[PASignal]
    top5: list[PASignal]
    summary: dict  # {买入: X, 不动_信号不够强: X, ...}


# ======================================================================
# Phase 1: 全市场粗筛
# ======================================================================

def _fetch_all_stocks() -> pd.DataFrame:
    """获取全A股实时行情（新浪数据源）"""
    logger.info("获取全A股实时行情...")
    try:
        df = ak.stock_zh_a_spot()
        # Sina columns: ['代码', '名称', '最新价', '涨跌额', '涨跌幅', '买入', '卖出', '昨收', '今开', '最高', '最低', '成交量', '成交额']
        # Rename to standard names for internal use
        df = df.rename(columns={
            '代码': '代码_raw', '名称': '名称_raw',
        })
        # Keep original Sina column names but add aliases
        df['代码'] = df['代码_raw']
        df['名称'] = df['名称_raw']
        df['最新价'] = df['最新价']
        df['涨跌幅'] = df['涨跌幅']
        df['成交量'] = df['成交量']
        df['成交额'] = df['成交额']
        df['振幅'] = df['振幅'] if '振幅' in df.columns else 0
        df['换手率'] = df['换手率'] if '换手率' in df.columns else 0
        df['流通市值'] = df['流通市值'] if '流通市值' in df.columns else 0
        df['总市值'] = df['总市值'] if '总市值' in df.columns else 0
    except Exception:
        # Fallback to East Money
        df = ak.stock_zh_a_spot_em()
    logger.info(f"获取到 {len(df)} 只股票")
    return df


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """统一列名：中文(Sina) → 英文"""
    col_map = {
        '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low',
        '收盘': 'close', '成交量': 'volume', '成交额': 'amount',
        '代码': 'code', '名称': 'name', '最新价': 'close',
        '涨跌幅': 'pct_change', '振幅': 'amplitude',
        '换手率': 'turnover_rate', '流通市值': 'circ_market_cap',
        '总市值': 'total_market_cap',
    }
    df = df.copy()
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    return df


def coarse_filter(df: pd.DataFrame) -> tuple[list[StockSnapshot], dict]:
    """Phase 1: 粗筛，5000+ → ~200

    Returns:
        (候选股票列表, 排除统计)
    """
    excluded = {
        "ST": 0, "新股": 0, "成交额不足": 0,
        "振幅不足": 0, "涨跌停": 0, "低价": 0, "其他": 0,
    }
    candidates = []

    # Detect column naming style
    has_cn = '代码' in df.columns
    code_col = '代码' if has_cn else '代码'
    name_col = '名称' if has_cn else '名称'
    close_col = '最新价' if has_cn else '最新价'
    pct_col = '涨跌幅' if has_cn else '涨跌幅'
    amp_col = '振幅' if has_cn else ('振幅' if '振幅' in df.columns else 'amplitude')
    amount_col = '成交额' if has_cn else ('成交额' if '成交额' in df.columns else 'amount')
    vol_col = '成交量' if has_cn else 'volume'
    to_col = '换手率' if has_cn and '换手率' in df.columns else ('turnover_rate' if 'turnover_rate' in df.columns else None)
    circ_col = '流通市值' if has_cn and '流通市值' in df.columns else ('circ_market_cap' if 'circ_market_cap' in df.columns else None)
    total_col = '总市值' if has_cn and '总市值' in df.columns else ('total_market_cap' if 'total_market_cap' in df.columns else None)

    for _, row in df.iterrows():
        code = str(row.get(code_col, ""))
        name = str(row.get(name_col, ""))

        # ST过滤
        if EXCLUDE_ST and ("ST" in name or "*ST" in name):
            excluded["ST"] += 1
            continue

        # 价格过滤
        close = float(row.get(close_col, 0))
        if close < MIN_PRICE:
            excluded["低价"] += 1
            continue

        # 涨跌停过滤
        pct = float(row.get(pct_col, 0))
        if EXCLUDE_LIMIT_LOCKED and (pct >= 9.9 or pct <= -9.9):
            excluded["涨跌停"] += 1
            continue

        # 振幅过滤
        amp_val = row.get(amp_col, 0)
        amplitude = float(amp_val) if amp_val and amp_val == amp_val else 0
        if amplitude < 1.0:
            excluded["振幅不足"] += 1
            continue

        # 成交额过滤
        amount = float(row.get(amount_col, 0))
        if amount < MIN_AVG_AMOUNT_YI * 1e8:
            excluded["成交额不足"] += 1
            continue

        # 市值
        circ_cap = float(row.get(circ_col, 0)) / 1e8 if circ_col and row.get(circ_col, 0) else 0
        total_cap = float(row.get(total_col, 0)) / 1e8 if total_col and row.get(total_col, 0) else 0
        # 换手率
        turnover = float(row.get(to_col, 0)) if to_col and row.get(to_col, 0) else 0

        candidates.append(StockSnapshot(
            code=code,
            name=name,
            close=close,
            pct_change=pct,
            volume=float(row.get("成交量", 0)),
            amount=amount,
            amplitude=amplitude,
            turnover_rate=float(row.get("换手率", 0)),
            total_market_cap=total_cap,
            circ_market_cap=circ_cap,
        ))

    logger.info(f"粗筛结果: {len(candidates)}/{len(df)} 通过")
    return candidates, excluded


# ======================================================================
# Phase 2: PA结构判定
# ======================================================================

def _fetch_daily_kline(code: str, days: int = 100) -> pd.DataFrame:
    """获取个股日线K线（腾讯数据源）"""
    try:
        # Tencent source - most reliable from this network
        prefix = "sh" if code.startswith("6") else "sz"
        df = ak.stock_zh_a_hist_tx(symbol=f"{prefix}{code}", start_date="20260101", end_date="20260612", adjust="qfq")
        if df is not None and len(df) >= 20:
            # Tencent columns: ['date', 'open', 'close', 'high', 'low', 'volume']
            return df.tail(days)
    except Exception:
        pass
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df is not None and len(df) >= 20:
            return df.tail(days)
    except Exception:
        pass
    return pd.DataFrame()


def _ema(series: pd.Series, period: int = 20) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _find_swing_points(high: np.ndarray, low: np.ndarray, window: int = 5):
    """找摆动点"""
    n = len(high)
    sh_idx, sh_val = [], []
    sl_idx, sl_val = [], []
    for i in range(window, n - window):
        if high[i] == np.max(high[i - window:i + window + 1]):
            sh_idx.append(i)
            sh_val.append(float(high[i]))
        if low[i] == np.min(low[i - window:i + window + 1]):
            sl_idx.append(i)
            sl_val.append(float(low[i]))
    return sh_idx, sh_val, sl_idx, sl_val


def analyze_structure(snapshot: StockSnapshot) -> PAStructure:
    """Phase 2: 对单只股票做PA结构判定"""
    code = snapshot.code
    name = snapshot.name

    df = _fetch_daily_kline(code)
    if df.empty or len(df) < 20:
        return PAStructure(
            code=code, name=name, trend="数据不足", stage=0, channel="—",
            swing_structure="—", structure_score=0,
            key_levels={}, ema20_direction="—",
        )

    # Normalize columns (Tencent: English, others may use Chinese)
    df = _normalize_columns(df)

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    ema20 = _ema(pd.Series(close), 20).values
    ema50 = _ema(pd.Series(close), 50).values

    # EMA方向
    ema20_slope = (ema20[-1] - ema20[-6]) / ema20[-6] * 100 if ema20[-6] != 0 else 0
    if ema20_slope > 0.5:
        ema_dir = "上升"
    elif ema20_slope < -0.5:
        ema_dir = "下降"
    else:
        ema_dir = "走平"

    # 摆动结构
    sh_idx, sh_vals, sl_idx, sl_vals = _find_swing_points(high, low, window=5)

    has_hh_hl = False
    has_lh_ll = False
    if len(sh_vals) >= 2 and len(sl_vals) >= 2:
        recent_n = min(3, len(sh_vals))
        r_sh = sh_vals[-recent_n:]
        r_sl = sl_vals[-recent_n:]
        hh = all(r_sh[i] > r_sh[i-1] for i in range(1, len(r_sh)))
        hl = all(r_sl[i] > r_sl[i-1] for i in range(1, len(r_sl)))
        lh = all(r_sh[i] < r_sh[i-1] for i in range(1, len(r_sh)))
        ll = all(r_sl[i] < r_sl[i-1] for i in range(1, len(r_sl)))
        has_hh_hl = hh and hl
        has_lh_ll = lh and ll

    # 趋势判定
    if has_hh_hl and ema_dir == "上升":
        trend = "上升趋势"
        swing = "HH+HL"
    elif has_lh_ll and ema_dir == "下降":
        trend = "下降趋势"
        swing = "LH+LL"
    elif has_hh_hl:
        trend = "上升趋势"  # 结构优先
        swing = "HH+HL"
    elif has_lh_ll:
        trend = "下降趋势"
        swing = "LH+LL"
    elif ema_dir == "走平":
        trend = "交易区间"
        swing = "无序列"
    else:
        trend = "交易区间"
        swing = "混乱"

    # 阶段+通道
    if trend in ("上升趋势", "下降趋势"):
        recent = df.iloc[-20:].copy()
        recent = _normalize_columns(recent)
        ema_recent = _ema(recent["close"], 20)
        if ema_dir == "上升":
            touches = (recent["low"] < ema_recent).sum()
        else:
            touches = (recent["high"] > ema_recent).sum()

        rng = (float(high[-20:].max()) - float(low[-20:].min())) / float(close[-1]) * 100

        if touches <= 2 and rng > 15:
            stage, channel = 1, "—"
        elif touches <= 4:
            stage, channel = 2, "窄通道"
        elif touches <= 12:
            stage, channel = 3, "宽通道"
        else:
            stage, channel = 4, "—"
    else:
        stage, channel = 4, "—"

    # 结构评分
    # 趋势清晰度
    if trend in ("上升趋势", "下降趋势"):
        if stage in (1, 2):
            trend_score = 38
        elif stage == 3:
            trend_score = 28
        else:
            trend_score = 15
    elif trend == "交易区间":
        trend_score = 10
    else:
        trend_score = 5

    # 摆动结构完整性
    sw_count = len(sh_vals)
    if sw_count >= 4:
        swing_score = 28
    elif sw_count >= 3:
        swing_score = 22
    elif sw_count >= 2:
        swing_score = 15
    else:
        swing_score = 5

    # 关键价位明确度
    key_count = 0
    key_levels = {}
    if len(sh_vals) >= 1:
        key_levels["resistance"] = float(sh_vals[-1])
        key_count += 1
    if len(sl_vals) >= 1:
        key_levels["support"] = float(sl_vals[-1])
        key_count += 1
    key_levels["ema20"] = float(ema20[-1])
    key_levels["ema50"] = float(ema50[-1]) if len(ema50) > 0 else float(ema20[-1])
    key_levels["high20"] = float(high[-20:].max())
    key_levels["low20"] = float(low[-20:].min())
    key_count += 2  # ema20 + ema50

    key_score = min(key_count * 7, 30)

    structure_score = min(trend_score + swing_score + key_score, 100)

    return PAStructure(
        code=code, name=name, trend=trend, stage=stage, channel=channel,
        swing_structure=swing, structure_score=structure_score,
        key_levels=key_levels, ema20_direction=ema_dir,
    )


# ======================================================================
# Phase 3: 信号扫描+评分+决策
# ======================================================================

def _detect_signal(
    df: pd.DataFrame, structure: PAStructure
) -> tuple[Optional[SignalType], Optional[DirectionType], int, str]:
    """在日线上检测PA信号，返回(信号类型, 方向, 基础分, 原因)"""
    if df.empty or len(df) < 20:
        return None, None, 0, "数据不足"

    df = _normalize_columns(df)
    close = df["close"].values
    open_ = df["open"].values
    high = df["high"].values
    low = df["low"].values
    vol = df["volume"].values

    n = len(close)
    latest = slice(n-1, n)
    recent_5 = slice(n-6, n-1)
    recent_10 = slice(max(0, n-11), n-1)
    recent_20 = slice(max(0, n-21), n-1)

    body = abs(close[-1] - open_[-1])
    total_range = high[-1] - low[-1]
    body_pct = body / total_range * 100 if total_range > 0 else 0
    upper_wick = high[-1] - max(close[-1], open_[-1])
    lower_wick = min(close[-1], open_[-1]) - low[-1]
    avg_range_3 = np.mean(high[-4:-1] - low[-4:-1])
    range_ratio = total_range / avg_range_3 if avg_range_3 > 0 else 1

    is_bullish = close[-1] > open_[-1]
    close_position = (close[-1] - low[-1]) / total_range * 100 if total_range > 0 else 50

    # 均量
    avg_vol_5 = np.mean(vol[-6:-1]) if len(vol) >= 6 else vol[-1]
    vol_ratio = vol[-1] / avg_vol_5 if avg_vol_5 > 0 else 1

    reasons = []

    # ============ A. 趋势延续信号 ============
    if structure.trend in ("上升趋势", "下降趋势") and structure.stage in (2, 3):
        # H2/L2回调入场
        ema20_val = structure.key_levels.get("ema20", 0)
        dist_from_ema = abs(close[-1] - ema20_val) / ema20_val * 100 if ema20_val > 0 else 99

        if dist_from_ema < 3 and body_pct > 50:
            if structure.trend == "上升趋势" and is_bullish and close_position > 60:
                reasons.append(f"H2回调至20EMA附近(距{dist_from_ema:.1f}%)，强阳线确认")
                return "H2回调", "多", 50, "; ".join(reasons)
            elif structure.trend == "下降趋势" and not is_bullish and close_position < 40:
                reasons.append(f"L2反弹至20EMA附近(距{dist_from_ema:.1f}%)，强阴线确认")
                return "L2回调", "空", 50, "; ".join(reasons)

        # 20EMA弹跳（接触但强度略低）
        if dist_from_ema < 5 and body_pct > 40:
            if structure.trend == "上升趋势" and is_bullish:
                reasons.append(f"触碰20EMA后弹跳(距{dist_from_ema:.1f}%)")
                return "20EMA弹跳", "多", 40, "; ".join(reasons)
            elif structure.trend == "下降趋势" and not is_bullish:
                reasons.append(f"触碰20EMA后弹跳(距{dist_from_ema:.1f}%)")
                return "20EMA弹跳", "空", 40, "; ".join(reasons)

    # ============ B. 反转信号 ============
    # 楔形反转（简化检测：看20日价格走势是否收敛）
    if len(close) >= 20:
        first_10_range = np.max(high[-20:-10]) - np.min(low[-20:-10])
        last_10_range = np.max(high[-10:]) - np.min(low[-10:])
        range_shrink = first_10_range > 0 and (last_10_range / first_10_range) < 0.7

        if range_shrink and body_pct > 50 and range_ratio > 1.3:
            if structure.trend == "上升趋势" and not is_bullish and close_position < 40:
                reasons.append("上升楔形收敛+强阴线反转，H3看跌")
                return "楔形反转", "空", 50, "; ".join(reasons)
            elif structure.trend == "下降趋势" and is_bullish and close_position > 60:
                reasons.append("下降楔形收敛+强阳线反转，L3看涨")
                return "楔形反转", "多", 50, "; ".join(reasons)

    # Pin Bar 反转
    if structure.trend == "上升趋势" and close[-1] >= np.max(high[-20:-1]):
        if upper_wick > total_range * 0.33 and close_position < 50:
            reasons.append("趋势高位Pin Bar，长上影+收盘反方向")
            return "Pin Bar反转", "空", 40, "; ".join(reasons)
    elif structure.trend == "下降趋势" and close[-1] <= np.min(low[-20:-1]):
        if lower_wick > total_range * 0.33 and close_position > 50:
            reasons.append("趋势低位Pin Bar，长下影+收盘反方向")
            return "Pin Bar反转", "多", 40, "; ".join(reasons)

    # 失败突破（80%规则）— 简化检测
    high20 = structure.key_levels.get("high20", 0)
    low20 = structure.key_levels.get("low20", 0)
    if high20 > 0:
        prev_close = close[-2] if n >= 2 else close[-1]
        if prev_close > high20 * 1.005 and close[-1] < high20 * 1.002:
            reasons.append(f"突破20日高{high20:.2f}后收盘回到下方，80%规则看跌")
            return "失败突破", "空", 50, "; ".join(reasons)
    if low20 > 0:
        prev_close = close[-2] if n >= 2 else close[-1]
        if prev_close < low20 * 0.995 and close[-1] > low20 * 0.998:
            reasons.append(f"跌破20日低{low20:.2f}后收盘回到上方，80%规则看涨")
            return "失败突破", "多", 50, "; ".join(reasons)

    # 高潮反转
    if len(close) >= 5:
        recent_closes = close[-5:]
        consecutive_up = all(recent_closes[i] > recent_closes[i-1] for i in range(1, 5))
        consecutive_down = all(recent_closes[i] < recent_closes[i-1] for i in range(1, 5))
        if consecutive_up and body_pct > 60 and vol_ratio > 1.5 and not is_bullish:
            reasons.append("连续5阳后巨量阴线，高潮反转")
            return "高潮反转", "空", 45, "; ".join(reasons)
        if consecutive_down and body_pct > 60 and vol_ratio > 1.5 and is_bullish:
            reasons.append("连续5阴后巨量阳线，高潮反转")
            return "高潮反转", "多", 45, "; ".join(reasons)

    # ============ C. A股特有信号 ============
    # 平台突破
    if structure.trend in ("交易区间", "上升趋势") and structure.stage == 4:
        range_20d = (np.max(high[-20:]) - np.min(low[-20:])) / np.mean(close[-20:]) * 100
        if range_20d < 15 and vol_ratio > 2.0 and is_bullish and close_position > 70:
            reasons.append(f"横盘振幅{range_20d:.1f}%，放量{vol_ratio:.1f}x突破平台")
            return "平台突破", "多", 50, "; ".join(reasons)

    # 回踩不破
    if structure.trend == "上升趋势":
        prev_swing_high = 0
        for k, v in structure.key_levels.items():
            if "resistance" in k and v > prev_swing_high:
                prev_swing_high = v
        if prev_swing_high > 0 and abs(close[-1] - prev_swing_high) / prev_swing_high < 0.02:
            if vol_ratio < 0.7 and is_bullish:
                reasons.append(f"回踩前高{prev_swing_high:.2f}不破，缩量确认")
                return "回踩不破", "多", 45, "; ".join(reasons)

    # 未识别到有效信号
    if body_pct > 50 and range_ratio > 1.3:
        if is_bullish:
            return None, "多", 25, "强阳线但缺乏明确PA形态"
        else:
            return None, "空", 25, "强阴线但缺乏明确PA形态"

    return None, None, 0, "无有效PA信号"


def _calc_rr(
    direction: Optional[DirectionType],
    close: float, structure: PAStructure, signal_type: Optional[SignalType],
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """计算R:R、止损、止盈"""
    if direction is None or close <= 0:
        return None, None, None, None

    key = structure.key_levels
    support = key.get("support", close * 0.95)
    resistance = key.get("resistance", close * 1.05)

    if direction == "多":
        stop_loss = min(key.get("low20", close * 0.97), support) * 0.995
        target_1 = resistance
        target_2 = key.get("high20", close * 1.1)
    else:
        stop_loss = max(key.get("high20", close * 1.03), resistance) * 1.005
        target_1 = support
        target_2 = key.get("low20", close * 0.9)

    rr = abs(target_1 - close) / abs(stop_loss - close) if abs(stop_loss - close) > 0 else 0
    max_loss = abs(stop_loss - close) / close * 100

    return round(rr, 2), round(stop_loss, 2), round(target_1, 2), round(target_2, 2)


def _a_share_risk_penalty(snapshot: StockSnapshot) -> tuple[int, list[str]]:
    """A股特有风险扣分"""
    penalty = 0
    flags = []

    if snapshot.pct_change > 0:
        # 估算5日涨幅（用当日涨幅近似，精确需要历史数据）
        # 简化：如果当日涨>5%，标记追高风险
        if snapshot.pct_change > 5:
            penalty += 10
            flags.append(f"当日涨幅{snapshot.pct_change:.1f}%偏高")

    if snapshot.circ_market_cap < 20:
        penalty += 10
        flags.append(f"流通市值{snapshot.circ_market_cap:.1f}亿偏小")

    if snapshot.turnover_rate > 15:
        penalty += 10
        flags.append(f"换手率{snapshot.turnover_rate:.1f}%异常")

    return penalty, flags


def scan_signals(
    structures: list[PAStructure],
    snapshots: list[StockSnapshot],
) -> list[PASignal]:
    """Phase 3: 对所有股票做信号扫描+评分+决策

    Returns:
        信号列表，按总分降序
    """
    snap_map = {s.code: s for s in snapshots}
    signals = []

    for struct in structures:
        code = struct.code
        snap = snap_map.get(code)
        if snap is None:
            continue

        df = _fetch_daily_kline(code)
        if df.empty:
            signals.append(PASignal(
                code=code, name=struct.name,
                signal_type=None, direction=None,
                base_score=0, confirm_score=0, volume_score=0,
                rr_score=0, risk_penalty=0, total_score=0,
                decision="不动", decision_reason="数据获取失败",
                structure=struct,
            ))
            continue

        # 信号检测
        sig_type, direction, base, reason = _detect_signal(df, struct)

        # 60min确认（简化：无60min数据时中立）
        confirm_score = 0

        # 量能验证
        vol_score = 0
        if snap.amount > 3e8:
            vol_score += 5
        # 量比估算（用当日成交额/流通市值近似换手率变化）
        if snap.turnover_rate > 3 and snap.turnover_rate < 15:
            vol_score += 5
        elif snap.turnover_rate < 1:
            vol_score -= 10

        # R:R评估
        rr, stop_loss, target_1, target_2 = _calc_rr(direction, snap.close, struct, sig_type)
        rr_score = 0
        if rr is not None:
            if rr >= 3:
                rr_score = 10
            elif rr >= 2:
                rr_score = 5
            elif rr < 1.5:
                rr_score = -10

        # A股风险
        risk_penalty, risk_flags = _a_share_risk_penalty(snap)

        # 总分
        total = base + confirm_score + vol_score + rr_score - risk_penalty
        total = max(0, min(110, total))

        # 决策
        if sig_type is None and base < 25:
            decision = "不动"
            decision_reason = "无有效PA信号" if base == 0 else f"信号太弱({reason})"
        elif total >= 60 and (rr is None or rr >= 2.0):
            decision = "买入"
            decision_reason = f"评分{total}达标，{reason}"
        elif total >= 40:
            decision = "不动"
            decision_reason = f"信号不够强(评分{total}，{reason})"
        elif rr is not None and rr < 1.5:
            decision = "不动"
            decision_reason = f"空间不足(R:R={rr:.1f})"
        elif risk_penalty > 30:
            decision = "不动"
            decision_reason = f"风险过大({'; '.join(risk_flags)})"
        else:
            decision = "不动"
            decision_reason = f"评分不足(总分{total})"

        max_loss_pct = abs(stop_loss - snap.close) / snap.close * 100 if stop_loss else None

        signals.append(PASignal(
            code=code, name=struct.name,
            signal_type=sig_type, direction=direction,
            base_score=base, confirm_score=confirm_score,
            volume_score=vol_score, rr_score=rr_score,
            risk_penalty=risk_penalty, total_score=total,
            decision=decision, decision_reason=decision_reason,
            pa_reason=reason,
            entry_price=snap.close if decision == "买入" else None,
            stop_loss=stop_loss if decision == "买入" else None,
            target_1=target_1 if decision == "买入" else None,
            target_2=target_2 if decision == "买入" else None,
            rr_ratio=rr if decision == "买入" else None,
            max_loss_pct=round(max_loss_pct, 2) if max_loss_pct else None,
            risk_flags=risk_flags,
            structure=struct,
        ))

    # 按总分降序
    signals.sort(key=lambda x: x.total_score, reverse=True)
    return signals


# ======================================================================
# 主入口
# ======================================================================

def run_scan(progress_callback=None) -> ScanResult:
    """运行 Phase 1-3 完整扫描

    Args:
        progress_callback: 可选，进度回调 fn(phase, current, total)

    Returns:
        ScanResult with all data
    """
    today = date.today().isoformat()

    # Phase 1
    if progress_callback:
        progress_callback("phase1", 0, 3)
    df_all = _fetch_all_stocks()
    candidates, excluded = coarse_filter(df_all)

    # Phase 2
    if progress_callback:
        progress_callback("phase2", 0, len(candidates))
    structures = []
    for i, snap in enumerate(candidates):
        struct = analyze_structure(snap)
        structures.append(struct)
        if progress_callback and i % 20 == 0:
            progress_callback("phase2", i, len(candidates))
    if progress_callback:
        progress_callback("phase2", len(candidates), len(candidates))

    # Phase 3
    if progress_callback:
        progress_callback("phase3", 0, 1)
    signals = scan_signals(structures, candidates)
    if progress_callback:
        progress_callback("phase3", 1, 1)

    # TOP5
    buy_signals = [s for s in signals if s.decision == "买入"]
    buy_signals.sort(key=lambda x: x.total_score, reverse=True)
    top5 = buy_signals[:5]

    # Summary
    summary = {
        "买入": len([s for s in signals if s.decision == "买入"]),
        "不动_信号不够强": len([s for s in signals if "信号不够强" in s.decision_reason]),
        "不动_无有效信号": len([s for s in signals if "无有效PA信号" in s.decision_reason or "信号太弱" in s.decision_reason]),
        "不动_空间不足": len([s for s in signals if "空间不足" in s.decision_reason]),
        "不动_风险过大": len([s for s in signals if "风险过大" in s.decision_reason]),
        "不动_其他": len([s for s in signals if s.decision == "不动" and s.decision_reason not in [
            x for x in ["信号不够强", "无有效PA信号", "信号太弱", "空间不足", "风险过大"]
            if any(x in s.decision_reason for _ in [s])
        ]]),  # 简化
    }
    # Fix: 用实际分类重算
    summary = {"买入": 0, "不动_信号不够强": 0, "不动_无有效信号": 0, "不动_空间不足": 0, "不动_风险过大": 0, "不动_无信号": 0}
    for s in signals:
        if s.decision == "买入":
            summary["买入"] += 1
        elif "信号不够强" in s.decision_reason:
            summary["不动_信号不够强"] += 1
        elif "无有效PA信号" in s.decision_reason or "信号太弱" in s.decision_reason:
            summary["不动_无有效信号"] += 1
        elif "空间不足" in s.decision_reason:
            summary["不动_空间不足"] += 1
        elif "风险过大" in s.decision_reason:
            summary["不动_风险过大"] += 1
        else:
            summary["不动_无信号"] += 1

    return ScanResult(
        date=today,
        total_scanned=len(df_all),
        phase1_passed=len(candidates),
        phase1_candidates=candidates,
        phase2_structures=structures,
        phase3_signals=signals,
        top5=top5,
        summary=summary,
    )


def save_scan_result(result: ScanResult) -> Path:
    """保存扫描结果到JSON"""
    out_dir = OUTPUT_DIR / result.date
    out_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1
    with open(out_dir / "phase1_candidates.json", "w", encoding="utf-8") as f:
        json.dump({
            "date": result.date,
            "total_scanned": result.total_scanned,
            "passed": result.phase1_passed,
            "candidates": [asdict(c) for c in result.phase1_candidates],
        }, f, ensure_ascii=False, indent=2, default=str)

    # Phase 2
    with open(out_dir / "phase2_structures.json", "w", encoding="utf-8") as f:
        json.dump({
            "date": result.date,
            "total": len(result.phase2_structures),
            "structures": [asdict(s) for s in result.phase2_structures],
        }, f, ensure_ascii=False, indent=2, default=str)

    # Phase 3
    with open(out_dir / "phase3_decisions.json", "w", encoding="utf-8") as f:
        json.dump({
            "date": result.date,
            "summary": result.summary,
            "top5": [asdict(s) for s in result.top5],
            "all_decisions": [asdict(s) for s in result.phase3_signals],
        }, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"扫描结果已保存至 {out_dir}")
    return out_dir


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    result = run_scan()
    save_scan_result(result)
    print(f"\n扫描完成: {result.phase1_passed}只候选 → {result.summary['买入']}只买入信号 → TOP5: {[(s.name, s.total_score) for s in result.top5]}")
