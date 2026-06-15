"""情绪聚合器 — 国内期货版：基差 + 持仓变化 → 综合 0-100 情绪分

替代之前的 Fear & Greed（仅适用于加密）。
v2: 5分钟缓存 + 超时保护 + 减少 API 重复调用
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from config import (
    SYMBOLS, MAIN_CONTRACT, PRIMARY_SYMBOL,
    BASIS_POSITIVE_THRESHOLD, BASIS_NEGATIVE_THRESHOLD,
)

logger = logging.getLogger("sentiment")

REQUEST_TIMEOUT = 8        # 单次 HTTP 超时(秒)
MAX_RETRIES = 1            # 重试次数
RETRY_DELAY = 0.5          # 重试间隔(秒)
SENTIMENT_CACHE_TTL = 300  # 情绪缓存 5 分钟
API_TIMEOUT = 8            # AKShare 调用超时(秒)


# ======================================================================
# Data structures
# ======================================================================

@dataclass
class BasisData:
    """基差数据"""
    spot_price: float
    futures_price: float
    basis_pct: float
    signal: str              # "偏多" / "偏空" / "中性"


@dataclass
class PositionData:
    """持仓量数据"""
    current: float
    change_5d: float
    change_20d: float
    signal: str


@dataclass
class SentimentResult:
    """综合情绪结果"""
    score: int               # 0-100
    basis: Optional[BasisData] = None
    position: Optional[PositionData] = None
    summary: str = ""
    fear_greed: Optional[object] = None


# ======================================================================
# 缓存
# ======================================================================

_sentiment_cache: dict[str, tuple[float, SentimentResult]] = {}
_main_sina_cache: dict[str, tuple[float, object]] = {}  # AKShare futures_main_sina 结果缓存


def _call_with_timeout(fn, *args, timeout=API_TIMEOUT):
    """在线程中执行函数，超时返回 None"""
    result = [None]

    def _target():
        try:
            result[0] = fn(*args)
        except Exception:
            result[0] = None

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return None if t.is_alive() else result[0]


def _get_main_sina(symbol: str):
    """获取 futures_main_sina 数据（带缓存，两个子函数共用）"""
    contract = MAIN_CONTRACT.get(symbol, "")
    if not contract:
        return None

    now = time.time()
    if contract in _main_sina_cache:
        ts, data = _main_sina_cache[contract]
        if now - ts < SENTIMENT_CACHE_TTL:
            return data

    try:
        import akshare as ak
        df = _call_with_timeout(ak.futures_main_sina, symbol=contract)
        if df is not None and not df.empty:
            _main_sina_cache[contract] = (now, df)
            return df
    except Exception:
        logger.debug(f"futures_main_sina 失败: {symbol}")
    return None


# ======================================================================
# 基差计算
# ======================================================================

def get_basis(symbol: str) -> Optional[BasisData]:
    """获取基差数据（带超时保护）。基差 = 现货 - 期货。"""
    info = SYMBOLS.get(symbol, {})
    if not info:
        return None

    try:
        import akshare as ak

        # 现货价（目前仅螺纹钢有良好支持，其他品种返回 None）
        spot = None
        if symbol == "RB":
            df_spot = _call_with_timeout(ak.futures_spot_price, symbol="螺纹钢")
            if df_spot is not None and not df_spot.empty:
                spot = float(df_spot.iloc[-1]["price"]) if "price" in df_spot.columns else float(df_spot.iloc[-1, 1])

        if spot is None:
            return None

        # 期货价（复用缓存）
        df_futures = _get_main_sina(symbol)
        if df_futures is None:
            return None
        futures = float(df_futures.iloc[-1]["收盘价"])

        basis_pct = (spot - futures) / spot * 100
        if basis_pct > BASIS_POSITIVE_THRESHOLD:
            signal = "偏多"
        elif basis_pct < BASIS_NEGATIVE_THRESHOLD:
            signal = "偏空"
        else:
            signal = "中性"

        return BasisData(spot_price=spot, futures_price=futures,
                         basis_pct=basis_pct, signal=signal)
    except Exception:
        logger.debug(f"基差获取失败 {symbol}")
        return None


def get_position_sentiment(symbol: str) -> Optional[PositionData]:
    """从持仓量变化推断市场情绪（带超时保护，复用 main_sina 缓存）"""
    try:
        df = _get_main_sina(symbol)
        if df is None:
            return None

        oi_col = "持仓量" if "持仓量" in df.columns else None
        if not oi_col:
            return None

        oi = df[oi_col].astype(float)
        current = float(oi.iloc[-1])
        avg_5d = float(oi.iloc[-6:-1].mean()) if len(oi) >= 6 else current
        avg_20d = float(oi.iloc[-21:-1].mean()) if len(oi) >= 21 else current

        chg_5d = (current / avg_5d - 1) * 100
        chg_20d = (current / avg_20d - 1) * 100

        if chg_20d > 10 and chg_5d > 0:
            signal = "偏多"
        elif chg_20d < -10 and chg_5d < 0:
            signal = "偏空"
        else:
            signal = "中性"

        return PositionData(current=current, change_5d=round(chg_5d, 1),
                            change_20d=round(chg_20d, 1), signal=signal)
    except Exception:
        logger.debug(f"持仓分析失败 {symbol}")
        return None


# ======================================================================
# 聚合（带缓存）
# ======================================================================

def aggregate(symbol: str = None) -> SentimentResult:
    """综合情绪评分 — 5分钟缓存 + 超时保护"""
    sym = symbol or PRIMARY_SYMBOL

    # 查缓存
    now = time.time()
    if sym in _sentiment_cache:
        ts, cached = _sentiment_cache[sym]
        if now - ts < SENTIMENT_CACHE_TTL:
            return cached

    # 并行获取基差和持仓（利用线程减少总时间）
    basis_result = [None]
    position_result = [None]

    def _fetch_basis():
        basis_result[0] = get_basis(sym)

    def _fetch_position():
        position_result[0] = get_position_sentiment(sym)

    t1 = threading.Thread(target=_fetch_basis, daemon=True)
    t2 = threading.Thread(target=_fetch_position, daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=API_TIMEOUT)
    t2.join(timeout=API_TIMEOUT)

    basis = basis_result[0]
    position = position_result[0]

    # 评分
    score = 50
    if basis:
        if basis.signal == "偏多":
            score += 18
        elif basis.signal == "偏空":
            score -= 18
    if position:
        if position.signal == "偏多":
            score += 12
        elif position.signal == "偏空":
            score -= 12

    score = max(0, min(100, int(score)))

    parts = []
    if basis:
        parts.append(f"基差{basis.basis_pct:+.1f}%({basis.signal})")
    if position:
        parts.append(f"持仓{position.change_5d:+.1f}%({position.signal})")
    summary = " | ".join(parts) if parts else "数据不足"

    result = SentimentResult(score=score, basis=basis, position=position, summary=summary)
    _sentiment_cache[sym] = (now, result)
    return result


def get_full_sentiment(symbol: str = None) -> SentimentResult:
    return aggregate(symbol)


def get_fear_greed():
    """兼容旧接口"""
    return None
