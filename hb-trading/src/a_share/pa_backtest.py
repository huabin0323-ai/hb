"""PA策略回测引擎 v2 — Al Brooks 全套13+信号 + ATR动态止损 + 滑动窗口

信号清单（来自 price_action.py 完整方法论）:
  H1/H2/H3 回调入场   楔形(3推收敛)    双底牛旗
  EMA20互动系统(缺口K线/回踩/假跌破)  最终旗形反转
  真空效应反转        水平S/R位       失败突破(80%规则)
  #23 阴线做多        #19 支撑背叛     #21 高潮预警
  平台突破(A股补充)    回踩不破(A股补充)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from src.a_share.ifind_adapter import fetch_kline

logger = logging.getLogger("pa_backtest")


# ══════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════

def _ema(s: np.ndarray, period: int) -> np.ndarray:
    alpha = 2 / (period + 1)
    result = np.zeros_like(s)
    result[0] = s[0]
    for i in range(1, len(s)): result[i] = alpha * s[i] + (1-alpha) * result[i-1]
    return result

def _sma(s: np.ndarray, period: int) -> np.ndarray:
    result = np.zeros_like(s)
    for i in range(len(s)):
        start = max(0, i-period+1)
        result[i] = np.mean(s[start:i+1])
    return result

def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
    tr[0] = high[0] - low[0]
    return _sma(tr, period)

def _rolling_max(a: np.ndarray, w: int) -> np.ndarray:
    r = np.zeros_like(a)
    for i in range(len(a)): r[i] = np.max(a[max(0,i-w+1):i+1])
    return r

def _rolling_min(a: np.ndarray, w: int) -> np.ndarray:
    r = np.zeros_like(a)
    for i in range(len(a)): r[i] = np.min(a[max(0,i-w+1):i+1])
    return r

def _swing_points(high: np.ndarray, low: np.ndarray, w: int = 5):
    n = len(high)
    sh_idx, sh_val, sl_idx, sl_val = [], [], [], []
    for i in range(w, n-w):
        if high[i] == np.max(high[i-w:i+w+1]): sh_idx.append(i); sh_val.append(float(high[i]))
        if low[i] == np.min(low[i-w:i+w+1]): sl_idx.append(i); sl_val.append(float(low[i]))
    return sh_idx, sh_val, sl_idx, sl_val


# ══════════════════════════════════════════════════════════════
# 结构判定
# ══════════════════════════════════════════════════════════════

def analyze_structure(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> dict:
    n = len(close)
    if n < 30: return {"trend": "数据不足", "stage": 0, "strength": 0}

    ema20 = _ema(close, 20)
    ema50 = _ema(close, min(50, n))
    sh_idx, sh_vals, sl_idx, sl_vals = _swing_points(high, low, 5)
    atr14 = _atr(high, low, close, 14)

    # 摆动结构
    has_hh_hl = has_lh_ll = False
    if len(sh_vals) >= 3 and len(sl_vals) >= 3:
        rsh, rsl = sh_vals[-3:], sl_vals[-3:]
        has_hh_hl = all(rsh[i] > rsh[i-1] for i in range(1,3)) and all(rsl[i] > rsl[i-1] for i in range(1,3))
        has_lh_ll = all(rsh[i] < rsh[i-1] for i in range(1,3)) and all(rsl[i] < rsl[i-1] for i in range(1,3))

    ema_slope = (ema20[-1]-ema20[-6])/ema20[-6]*100 if ema20[-6] > 0 else 0
    ema_dir = "上升" if ema_slope > 0.5 else "下降" if ema_slope < -0.5 else "走平"

    # 趋势
    if has_hh_hl and ema_dir in ("上升","走平"): trend = "上升趋势"
    elif has_lh_ll and ema_dir in ("下降","走平"): trend = "下降趋势"
    elif ema_dir == "走平": trend = "交易区间"
    else: trend = "交易区间"

    # 强度: EMA斜率归一化 + 结构完整性
    strength = min(1.0, abs(ema_slope)/5.0 + (0.3 if (has_hh_hl or has_lh_ll) else 0))

    # 通道阶段
    touches = np.sum(low[-20:] < ema20[-20:]) if ema_dir == "上升" else np.sum(high[-20:] > ema20[-20:]) if ema_dir == "下降" else 5
    rng = (float(np.max(high[-20:]))-float(np.min(low[-20:])))/float(close[-1])*100
    if touches <= 2 and rng > 15: stage, channel = 1, "扩张"
    elif touches <= 4: stage, channel = 2, "窄通道"
    elif touches <= 12: stage, channel = 3, "宽通道"
    else: stage, channel = 4, "区间"

    # 通道边界 (用20日高低)
    chan_top = float(np.max(high[-20:])) if ema_dir != "下降" else float(np.max(high[-20:]))
    chan_bot = float(np.min(low[-20:])) if ema_dir != "上升" else float(np.min(low[-20:]))

    return {
        "trend": trend, "stage": stage, "channel": channel, "strength": round(strength,2),
        "ema20_dir": ema_dir, "ema20": float(ema20[-1]), "ema50": float(ema50[-1]),
        "support": float(np.min(low[-20:])), "resistance": float(np.max(high[-20:])),
        "swing_highs": sh_vals, "swing_lows": sl_vals,
        "swing_high_idx": sh_idx, "swing_low_idx": sl_idx,
        "high20": float(np.max(high[-20:])), "low20": float(np.min(low[-20:])),
        "atr14": float(atr14[-1]) if len(atr14) > 0 else 0,
        "channel_top": chan_top, "channel_bottom": chan_bot,
    }


# ══════════════════════════════════════════════════════════════
# 信号数据类
# ══════════════════════════════════════════════════════════════

@dataclass
class PASignal:
    idx: int; date: str; signal_type: str; direction: str
    entry_price: float; stop_loss: float; take_profit: float
    score: int; reason: str; rr_ratio: float = 0.0; confidence: float = 0.5


# ══════════════════════════════════════════════════════════════
# 全信号检测（14种）
# ══════════════════════════════════════════════════════════════

def detect_all_signals(
    open_: np.ndarray, high: np.ndarray, low: np.ndarray,
    close: np.ndarray, vol: np.ndarray, dates: list, struct: dict,
    atr_arr: np.ndarray = None,
) -> list[PASignal]:
    n = len(close)
    if n < 25: return []

    i = n - 1
    o, h, l, c = open_[i], high[i], low[i], close[i]
    v = vol[i]
    body = abs(c - o)
    total_r = h - l
    if total_r == 0: return []
    body_pct = body / total_r * 100
    is_bull = c > o
    close_pos = (c - l) / total_r * 100
    upper_w = h - max(c, o)
    lower_w = min(c, o) - l

    avg_v5 = np.mean(vol[max(0,i-6):i]) if i >= 5 else v
    vol_ratio = v / avg_v5 if avg_v5 > 0 else 1
    atr_val = atr_arr[i] if atr_arr is not None and len(atr_arr) > i else (h-l)

    trend = struct.get("trend",""); stage = struct.get("stage",0)
    strength = struct.get("strength",0); ema20 = struct.get("ema20",c)
    dist_ema = abs(c-ema20)/ema20*100 if ema20 > 0 else 99
    high20 = struct.get("high20",c*1.1); low20 = struct.get("low20",c*0.9)
    support = struct.get("support",low20); resistance = struct.get("resistance",high20)
    chan_top = struct.get("channel_top",high20); chan_bot = struct.get("channel_bottom",low20)
    sh_idx = struct.get("swing_high_idx",[]); sl_idx = struct.get("swing_low_idx",[])
    sh_vals = struct.get("swing_highs",[]); sl_vals = struct.get("swing_lows",[])

    signals = []
    bias = "long" if trend == "上升趋势" else "short" if trend == "下降趋势" else None
    strong_trend = trend in ("上升趋势","下降趋势") and strength >= 0.4
    in_channel = stage in (2,3)

    # 止损至少留 1.5x ATR 空间
    min_stop_distance = atr_val * 1.5

    # ── 1. H2回调 ──
    if bias == "long" and dist_ema < 5 and body_pct > 40 and is_bull and close_pos > 55:
        sl = min(l, support) - min_stop_distance; tp = resistance
        rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
        if rr >= 1.5:
            signals.append(PASignal(i, str(dates[i])[:10], "H2回调","多",
                float(c), round(sl,2), round(tp,2), 50,
                f"H2回调至20EMA(距{dist_ema:.1f}%)，强阳线确认，R:R={rr:.1f}", round(rr,2), min(0.85, strength+0.3)))

    # ── 2. L2回调(做空) ──
    if bias == "short" and in_channel and dist_ema < 3 and body_pct > 50 and not is_bull and close_pos < 40:
        sl = max(h, resistance) + min_stop_distance; tp = support
        rr = abs(c-tp)/abs(sl-c) if abs(sl-c) > 0 else 0
        if rr >= 1.5:
            signals.append(PASignal(i, str(dates[i])[:10], "L2回调","空",
                float(c), round(sl,2), round(tp,2), 50,
                f"L2反弹至20EMA(距{dist_ema:.1f}%)，强阴线确认", round(rr,2), min(0.85, strength+0.3)))

    # ── 3. 20EMA弹跳 ──
    if bias == "long" and dist_ema < 5 and body_pct > 40 and is_bull and not signals:
        sl = min(l, support) - min_stop_distance; tp = resistance
        rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
        if rr >= 1.5:
            signals.append(PASignal(i, str(dates[i])[:10], "20EMA弹跳","多",
                float(c), round(sl,2), round(tp,2), 40,
                f"触碰20EMA弹跳(距{dist_ema:.1f}%)，R:R={rr:.1f}", round(rr,2), 0.55))

    # ── 4. EMA20缺口K线 ──
    if not signals and strong_trend and bias == "long":
        for j in range(n-2, max(n-12,0), -1):
            if high[j] < _ema(close,20)[j]:
                gap_h, gap_l = high[j], low[j]
                if c > gap_h:
                    sl = gap_l - min_stop_distance; tp = gap_h + (gap_h-gap_l) * 2.5
                    rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
                    if rr >= 1.5:
                        signals.append(PASignal(i, str(dates[i])[:10], "EMA缺口K线","多",
                            float(gap_h), round(sl,2), round(tp,2), 45,
                            f"突破EMA20缺口K线#{j}高点{gap_h:.1f}", round(rr,2), 0.65))
                break

    # ── 5. EMA20假跌破 ──
    if not signals and bias == "long":
        ema20_arr = _ema(close, 20)
        for j in range(n-2, max(n-7,0), -1):
            if low[j] < ema20_arr[j] and close[j] > ema20_arr[j] and close[j] > open_[j]:
                if c > high[j]:
                    sl = low[j] - min_stop_distance; tp = high[j] + atr_val * 3.0
                    rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
                    if rr >= 1.5:
                        signals.append(PASignal(i, str(dates[i])[:10], "EMA假跌破","多",
                            float(high[j]), round(sl,2), round(tp,2), 48,
                            f"EMA20假跌破收回: #{j}收阳", round(rr,2), 0.70))
                break

    # ── 6. 楔形反转 ──
    if not signals:
        if bias == "short" and len(sh_vals) >= 3:  # 上升楔形→看跌
            r = sh_vals[-3:]
            if r[2] > r[1] > r[0]:
                m1, m2 = abs(r[1]-r[0]), abs(r[2]-r[1])
                if (m1 > 0 and m2 < m1*0.85) or (len(sh_idx)>=3 and (sh_idx[2]-sh_idx[1]) < (sh_idx[1]-sh_idx[0])*0.9):
                    if not is_bull and close_pos < 40:
                        sl = max(h, resistance) + min_stop_distance; tp = support
                        rr = abs(c-tp)/abs(sl-c) if abs(sl-c) > 0 else 0
                        signals.append(PASignal(i, str(dates[i])[:10], "楔形反转","空",
                            float(c), round(sl,2), round(tp,2), 50,
                            f"上升楔形收敛+强阴线，R:R={rr:.1f}", round(rr,2), 0.75))
        elif bias == "long" and len(sl_vals) >= 3:  # 下降楔形→看涨
            r = sl_vals[-3:]
            if r[2] < r[1] < r[0]:
                m1, m2 = abs(r[1]-r[0]), abs(r[2]-r[1])
                if (m1 > 0 and m2 < m1*0.85) or (len(sl_idx)>=3 and (sl_idx[2]-sl_idx[1]) < (sl_idx[1]-sl_idx[0])*0.9):
                    if is_bull and close_pos > 60:
                        sl = min(l, support) - min_stop_distance; tp = resistance
                        rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
                        signals.append(PASignal(i, str(dates[i])[:10], "楔形反转","多",
                            float(c), round(sl,2), round(tp,2), 50,
                            f"下降楔形收敛+强阳线，R:R={rr:.1f}", round(rr,2), 0.75))

    # ── 7. 双底牛旗 ──
    if not signals and bias == "long" and len(sl_vals) >= 2:
        for a in range(len(sl_vals)):
            for b in range(a+1, len(sl_vals)):
                l1, l2 = sl_vals[a], sl_vals[b]
                if sl_idx[b] - sl_idx[a] < 5: continue
                if abs(l1-l2) > atr_val * 0.3: continue
                middle_lows = [sl_vals[k] for k in range(a+1,b) if sl_vals[k] > max(l1,l2)]
                if middle_lows:
                    sl = min(l1,l2) - min_stop_distance; tp = l2 + atr_val*3.0
                    rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
                    if rr >= 1.5:
                        signals.append(PASignal(i, str(dates[i])[:10], "双底牛旗","多",
                            float(l2+atr_val*0.3), round(sl,2), round(tp,2), 42,
                        f"双底: {l1:.1f}≈{l2:.1f} 间隔{sl_idx[b]-sl_idx[a]}根", round(rr,2), 0.60))
                break
        if any(s.signal_type == "双底牛旗" for s in signals): pass  # keep

    # ── 8. 最终旗形反转 ──
    if not signals and len(sl_vals) >= 2 and sl_idx[-1] >= n-20:
        flag_start = sl_idx[-1]
        flag_len = n - flag_start
        if 3 <= flag_len <= 10:
            flag_h = float(np.max(high[flag_start:])); flag_l = float(np.min(low[flag_start:]))
            if (flag_h-flag_l) < atr_val * 1.5:
                for j in range(flag_start+flag_len, n):
                    if low[j] < flag_l and close[j] > flag_l and c > high[j]:
                        sl = low[j] - min_stop_distance; tp = high[j] + (high[j]-low[j])*3.0
                        rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
                        if rr >= 1.5:
                            signals.append(PASignal(i, str(dates[i])[:10], "最终旗形","多",
                                float(high[j]), round(sl,2), round(tp,2), 46,
                            f"最终旗形反转: {flag_len}根旗形假破后收", round(rr,2), 0.70))
                        break

    # ── 9. 真空效应 ──
    if not signals and bias == "long" and n >= 10:
        for j in range(min(6, n-1), 2, -1):
            idx = n - j
            bar_b = abs(close[idx]-open_[idx]); bar_t = high[idx]-low[idx]
            if bar_t > 0 and not (close[idx] > open_[idx]) and bar_b/bar_t > 0.6:
                near_sup = (abs(low[idx]-chan_bot)/chan_bot < 0.02) if chan_bot > 0 else False
                for slv in sl_vals[-3:]:
                    if abs(low[idx]-slv)/slv < 0.02: near_sup = True; break
                if near_sup and is_bull:
                    sl = low[idx] - min_stop_distance; tp = h + atr_val*2.5
                    rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
                    if rr >= 1.5:
                        signals.append(PASignal(i, str(dates[i])[:10], "真空效应","多",
                            float(h+atr_val*0.05), round(sl,2), round(tp,2), 43,
                            f"真空效应: 急跌至支撑收回", round(rr,2), 0.65))
                break

    # ── 10. 水平S/R ──
    if not signals and bias == "long" and n >= 20:
        uw_vals = []; lw_vals = []
        for k in range(max(0,n-30), n):
            bh = max(open_[k],close[k]); bl = min(open_[k],close[k])
            tr_k = high[k]-low[k]
            if tr_k > 0:
                if (high[k]-bh)/tr_k > 0.5: uw_vals.append(high[k])
                if (bl-low[k])/tr_k > 0.5: lw_vals.append(low[k])
        if len(lw_vals) >= 5 and is_bull:  # 至少5根下影线
            cluster = np.mean(lw_vals)
            if abs(c-cluster)/cluster < 0.02:
                sl = cluster - min_stop_distance; tp = c + atr_val * 3.0
                rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
                if rr >= 2.0:  # 弱信号要求更高RR
                    signals.append(PASignal(i, str(dates[i])[:10], "水平支撑","多",
                        float(c), round(sl,2), round(tp,2), 35,
                        f"水平支撑: {len(lw_vals)}根下影线聚集{cluster:.1f}", round(rr,2), 0.50))

    # ── 11. 失败突破(80%规则) ──
    if not signals and n >= 40:
        win = min(30, n//2)
        lookback_high = float(np.max(high[-win*2:-win])); lookback_low = float(np.min(low[-win*2:-win]))
        rng_size = lookback_high - lookback_low
        if rng_size > 0 and rng_size/lookback_low >= 0.005:
            recent_h = float(np.max(high[-win:])); recent_l = float(np.min(low[-win:]))
            # 向上假突破→做空
            if recent_h > lookback_high:
                brk_size = recent_h - lookback_high
                after = low[np.argmax(high[-win:]):]
                pullback = float(np.min(after)) if len(after) > 0 else recent_h
                retrace = (recent_h-pullback)/brk_size*100 if brk_size > 0 else 0
                if retrace >= 80 and bias != "long":
                    sl = recent_h + min_stop_distance; tp = lookback_low
                    rr = abs(c-tp)/abs(sl-c) if abs(sl-c) > 0 else 0
                    if rr >= 1.5:
                        signals.append(PASignal(i, str(dates[i])[:10], "80%假突破","空",
                            float(l-atr_val*0.1), round(sl,2), round(tp,2), 50,
                            f"向上假突破{retrace:.0f}%回撤→做空", round(rr,2), min(retrace/100,1.0)))
            # 向下假突破→做多
            if recent_l < lookback_low and not signals:
                brk_size = lookback_low - recent_l
                after = high[np.argmin(low[-win:]):]
                pullback = float(np.max(after)) if len(after) > 0 else recent_l
                retrace = (pullback-recent_l)/brk_size*100 if brk_size > 0 else 0
                if retrace >= 80:
                    sl = recent_l - min_stop_distance; tp = lookback_high
                    rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
                    if rr >= 1.5:
                        signals.append(PASignal(i, str(dates[i])[:10], "80%假突破","多",
                            float(h+atr_val*0.1), round(sl,2), round(tp,2), 50,
                            f"向下假突破{retrace:.0f}%回撤→做多", round(rr,2), min(retrace/100,1.0)))

    # ── 12. #23 阴线做多 ──
    if not signals and bias == "long" and strength >= 0.3:
        for lb in range(2, min(6, n)):
            bi = n - lb
            if close[bi] < open_[bi]:
                prev_bull = sum(1 for k in range(bi-3, bi) if k >= 0 and close[k] > open_[k])
                if prev_bull >= 2 and c > high[bi]:
                    sl = low[bi] - min_stop_distance; tp = high[bi] + (high[bi]-low[bi])*2.0
                    rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
                    if rr >= 1.5:
                        signals.append(PASignal(i, str(dates[i])[:10], "#23阴线做多","多",
                            float(high[bi]), round(sl,2), round(tp,2), 48,
                            f"#23 阴线做多: 突破阴线高点{high[bi]:.1f}", round(rr,2), min(0.70, 0.55+strength*0.15)))
                break

    # ── 13. #19 支撑背叛 ──
    if not signals and bias == "long":
        candidates = [(chan_bot, "通道底")] if chan_bot > 0 else []
        for slv in sl_vals[-3:]: candidates.append((slv, f"前低{slv:.1f}"))
        for sup_val, sup_name in candidates:
            for j in range(max(0,n-5), n):
                if low[j] < sup_val:
                    for k in range(j+1, min(n, j+4)):
                        if close[k] > sup_val:
                            bars = k - j
                            urgency = 1.0 if bars <= 2 else 0.8
                            sl = low[j] - min_stop_distance; tp = sup_val + (sup_val-low[j])*2
                            rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
                            if rr >= 1.5:
                                signals.append(PASignal(i, str(dates[i])[:10], "#19支撑背叛","多",
                                    float(high[k]), round(sl,2), round(tp,2), 55,
                                    f"#19 支撑背叛: 假破{sup_name}→{bars}根内收回", round(rr,2), 0.60*urgency))
                            break
                    break
            if signals: break

    # ── 14. 平台突破(A股补充) ──
    if not signals and trend in ("交易区间","上升趋势"):
        rng_20d = (float(np.max(high[-20:]))-float(np.min(low[-20:])))/float(np.mean(close[-20:]))*100
        if rng_20d < 15 and vol_ratio > 1.5 and is_bull and close_pos > 70:
            sl = float(np.mean(low[-10:])) - min_stop_distance; tp = c*(1+rng_20d/100)
            rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
            if rr >= 1.5:
                signals.append(PASignal(i, str(dates[i])[:10], "平台突破","多",
                    float(c), round(sl,2), round(tp,2), 50,
                    f"横盘振幅{rng_20d:.1f}%突破，放量{vol_ratio:.1f}x", round(rr,2), 0.65))

    # ── 15. 回踩不破(A股补充) ──
    if not signals and bias == "long" and strong_trend:
        if abs(c-support)/support < 0.02 and vol_ratio < 0.8 and is_bull:
            sl = support*0.985; tp = resistance
            rr = abs(tp-c)/abs(sl-c) if abs(sl-c) > 0 else 0
            if rr >= 1.8:  # 弱信号要求更高RR
                signals.append(PASignal(i, str(dates[i])[:10], "回踩不破","多",
                    float(c), round(sl,2), round(tp,2), 42,
                    f"回踩支撑{support:.2f}不破，缩量确认", round(rr,2), 0.55))

    # ── #21 高潮预警(不产生交易信号，附加到已有信号中或忽略) ──
    # 作为风险提示，降低在加速行情中对信号的要求

    # 按置信度排序
    signals.sort(key=lambda x: -x.confidence)
    return signals


# ══════════════════════════════════════════════════════════════
# 交易/回测结果数据类
# ══════════════════════════════════════════════════════════════

@dataclass
class Trade:
    code: str; name: str; signal_type: str; direction: str
    entry_date: str; entry_idx: int; entry_price: float
    stop_loss: float; take_profit: float
    exit_date: str = ""; exit_idx: int = -1; exit_price: float = 0.0
    exit_reason: str = ""; pnl_pct: float = 0.0; bars_held: int = 0
    entry_reason: str = ""; exit_detail: str = ""


@dataclass
class BacktestResult:
    code: str; name: str; total_bars: int
    signal_count: int; trade_count: int; win_trades: int; lose_trades: int
    win_rate: float; total_return_pct: float; max_drawdown_pct: float
    profit_factor: float; avg_win_pct: float; avg_loss_pct: float; avg_bars_held: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)
    buy_markers: list[dict] = field(default_factory=list)
    sell_markers: list[dict] = field(default_factory=list)
    daily_klines: list[dict] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# 回测主函数
# ══════════════════════════════════════════════════════════════

def run_pa_backtest(
    code: str, name: str = "",
    window: int = 100, min_score: int = 35,
    min_rr: float = 1.3, max_hold: int = 20,
    use_long_only: bool = True,
) -> BacktestResult:
    try:
        df = fetch_kline(code, days=500)
    except Exception as e:
        logger.error(f"K线获取失败 {code}: {e}")
        return BacktestResult(code=code, name=name, total_bars=0, signal_count=0,
                            trade_count=0, win_trades=0, lose_trades=0, win_rate=0,
                            total_return_pct=0, max_drawdown_pct=0, profit_factor=0,
                            avg_win_pct=0, avg_loss_pct=0, avg_bars_held=0)

    if df.empty or len(df) < window + 20:
        return BacktestResult(code=code, name=name, total_bars=len(df), signal_count=0,
                            trade_count=0, win_trades=0, lose_trades=0, win_rate=0,
                            total_return_pct=0, max_drawdown_pct=0, profit_factor=0,
                            avg_win_pct=0, avg_loss_pct=0, avg_bars_held=0)

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    open_ = df["open"].values.astype(float); high = df["high"].values.astype(float)
    low = df["low"].values.astype(float); close = df["close"].values.astype(float)
    vol = df["volume"].values.astype(float); dates = df["date"].values
    n = len(close)

    atr_arr = _atr(high, low, close, 14)

    trades: list[Trade] = []
    eq = 100.0; equity_curve = [{"idx":0,"equity":100.0,"date":str(dates[window])[:10]}]
    peak = eq; max_dd = 0.0
    in_position = False; pos: Optional[Trade] = None
    signal_count = 0

    for i in range(window, n):
        if not in_position:
            equity_curve.append({"idx":i,"equity":round(eq,2),"date":str(dates[i])[:10]})

        w_start = max(0, i-window)
        struct = analyze_structure(high[w_start:i+1], low[w_start:i+1], close[w_start:i+1])

        # 出场检查
        if in_position and pos is not None:
            cur_h, cur_l, cur_c = high[i], low[i], close[i]
            exit_triggered = False
            if pos.direction == "多":
                if cur_l <= pos.stop_loss: pos.exit_price = pos.stop_loss*0.995; pos.exit_reason = "止损"; exit_triggered = True
                elif cur_h >= pos.take_profit: pos.exit_price = pos.take_profit; pos.exit_reason = "止盈"; exit_triggered = True
                elif i - pos.entry_idx >= max_hold: pos.exit_price = cur_c; pos.exit_reason = "到期"; exit_triggered = True
            else:
                if cur_h >= pos.stop_loss: pos.exit_price = pos.stop_loss*1.005; pos.exit_reason = "止损"; exit_triggered = True
                elif cur_l <= pos.take_profit: pos.exit_price = pos.take_profit; pos.exit_reason = "止盈"; exit_triggered = True
                elif i - pos.entry_idx >= max_hold: pos.exit_price = cur_c; pos.exit_reason = "到期"; exit_triggered = True

            if exit_triggered:
                pos.exit_date = str(dates[i])[:10]; pos.exit_idx = i; pos.bars_held = i - pos.entry_idx
                pos.pnl_pct = round((pos.exit_price/pos.entry_price-1)*100,2) if pos.direction=="多" else round((pos.entry_price/pos.exit_price-1)*100,2)
                pos.exit_detail = f"出场日{pos.exit_date} | {pos.exit_reason} | 持{pos.bars_held}天"
                trades.append(pos); eq *= (1+pos.pnl_pct/100)
                peak = max(peak,eq); dd = (peak-eq)/peak*100 if peak > 0 else 0; max_dd = max(max_dd,dd)
                equity_curve.append({"idx":i,"equity":round(eq,2),"date":str(dates[i])[:10]})
                in_position = False; pos = None

        # 入场
        if not in_position:
            signals = detect_all_signals(open_[w_start:i+1], high[w_start:i+1], low[w_start:i+1],
                                        close[w_start:i+1], vol[w_start:i+1], dates[w_start:i+1],
                                        struct, atr_arr[w_start:i+1] if atr_arr is not None else None)
            signal_count += len(signals)
            for sig in signals:
                if use_long_only and sig.direction != "多": continue
                if sig.score < min_score: continue
                if sig.rr_ratio < min_rr: continue
                next_i = i + 1
                if next_i >= n: continue
                pos = Trade(code=code, name=name, signal_type=sig.signal_type,
                           direction=sig.direction, entry_date=str(dates[next_i])[:10],
                           entry_idx=next_i, entry_price=float(open_[next_i]),
                           stop_loss=sig.stop_loss, take_profit=sig.take_profit,
                           entry_reason=sig.reason)
                in_position = True
                # 开盘跳空止损
                if open_[next_i] <= sig.stop_loss and sig.direction == "多":
                    pos.exit_date = str(dates[next_i])[:10]; pos.exit_idx = next_i
                    pos.exit_price = sig.stop_loss*0.995; pos.exit_reason = "止损(跳空)"
                    pos.bars_held = 0; pos.pnl_pct = round((pos.exit_price/pos.entry_price-1)*100,2)
                    pos.exit_detail = "开盘跳空跌破止损"
                    trades.append(pos); eq *= (1+pos.pnl_pct/100)
                    peak = max(peak,eq); dd = (peak-eq)/peak*100 if peak>0 else 0; max_dd = max(max_dd,dd)
                    in_position = False; pos = None
                break

    # 末笔强制平仓
    if in_position and pos is not None:
        pos.exit_date = str(dates[-1])[:10]; pos.exit_idx = n-1; pos.exit_price = float(close[-1])
        pos.exit_reason = "回测结束"; pos.bars_held = n-1-pos.entry_idx
        pos.pnl_pct = round((pos.exit_price/pos.entry_price-1)*100,2) if pos.direction=="多" else round((pos.entry_price/pos.exit_price-1)*100,2)
        pos.exit_detail = "回测结束强制平仓"
        trades.append(pos); eq *= (1+pos.pnl_pct/100)
        equity_curve.append({"idx":n-1,"equity":round(eq,2),"date":str(dates[-1])[:10]})

    # 统计
    completed = trades
    wins = [t for t in completed if t.pnl_pct > 0]; losses = [t for t in completed if t.pnl_pct <= 0]
    nt, nw, nl = len(completed), len(wins), len(losses)
    wr = nw/nt*100 if nt > 0 else 0
    avg_win = np.mean([t.pnl_pct for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl_pct for t in losses]) if losses else 0
    total_ret = round(eq-100,2); avg_bars = np.mean([t.bars_held for t in completed]) if completed else 0
    gp = sum(t.pnl_pct for t in wins); gl = abs(sum(t.pnl_pct for t in losses))
    pf = gp/gl if gl > 0 else (999 if gp > 0 else 0)

    buy_markers = [{"idx":t.entry_idx,"date":t.entry_date,"price":t.entry_price,
                    "signal":t.signal_type,"reason":t.entry_reason} for t in completed]
    sell_markers = [{"idx":t.exit_idx,"date":t.exit_date,"price":t.exit_price,
                     "reason":t.exit_reason,"pnl_pct":t.pnl_pct} for t in completed if t.exit_idx >= 0]

    daily = [{"date":str(dates[i])[:10],"open":float(open_[i]),"high":float(high[i]),
             "low":float(low[i]),"close":float(close[i]),"volume":int(vol[i])}
             for i in range(0, n, max(1, n//300))]

    return BacktestResult(code=code, name=name, total_bars=n, signal_count=signal_count,
                        trade_count=nt, win_trades=nw, lose_trades=nl, win_rate=round(wr,1),
                        total_return_pct=total_ret, max_drawdown_pct=round(max_dd,2),
                        profit_factor=round(pf,2), avg_win_pct=round(avg_win,2),
                        avg_loss_pct=round(avg_loss,2), avg_bars_held=round(avg_bars,1),
                        trades=completed, equity_curve=equity_curve,
                        buy_markers=buy_markers, sell_markers=sell_markers, daily_klines=daily)
