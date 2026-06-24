"""iFinD 数据适配器 — 基于同花顺官方 skill 的 call.py
统一数据源: 全市场筛选 + K线 + 实时行情 全部走 iFinD MCP
"""
from __future__ import annotations

import json, logging, re, sys
from pathlib import Path
from typing import Optional

import pandas as pd

# 确保能找到 ifind_call
sys.path.insert(0, str(Path(__file__).parent))

from ifind_call import call as _ifind_call

logger = logging.getLogger("ifind")

# ══════════════════════════════════════════════════════════════
# 1. K线数据 → DataFrame
# ══════════════════════════════════════════════════════════════

def fetch_kline(symbol: str, days: int = 250) -> pd.DataFrame:
    """获取日K线 — iFinD MCP → DataFrame

    使用 get_stock_info 接口（支持日频行情+技术指标）
    """
    try:
        r = _ifind_call("stock", "get_stock_info", {
            "query": f"{symbol}最近{days}个交易日的开盘价,收盘价,最高价,最低价,成交量,涨跌幅"
        })
    except Exception as e:
        logger.warning(f"iFinD K-line call failed for {symbol}: {e}")
        return _fallback_kline(symbol, days)

    if not r.get("ok"):
        logger.warning(f"iFinD K-line error for {symbol}: {r.get('error')}")
        return _fallback_kline(symbol, days)

    # 解析返回数据
    text = _extract_text(r)
    table = _parse_inner_json(text)
    return _parse_markdown_table(table, symbol)


def _extract_text(r: dict) -> str:
    """从 MCP 响应中提取文本内容"""
    # MCP返回: data.result.content[0].text = 内层JSON字符串
    data = r.get("data", {})
    result = data.get("result", {})
    content = result.get("content", [])
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            return item.get("text", "")
    return str(data)


def _parse_inner_json(text: str) -> str:
    """解析 iFinD 返回的内层JSON, 提取 markdown 表格

    search_stocks → data.result
    get_stock_info → data.answer
    """
    try:
        inner = json.loads(text)
    except Exception:
        return text  # 可能已经是纯表格

    data = inner.get("data", {})
    # 优先 answer, 其次 result
    table = data.get("answer") or data.get("result") or ""
    return table


def _parse_markdown_table(text: str, symbol: str) -> pd.DataFrame:
    """解析 iFinD 返回的 markdown 表格 → DataFrame"""
    lines = [l for l in text.strip().split("\n") if l and "|---" not in l]

    if len(lines) < 2:
        return pd.DataFrame()

    # Parse pipe-delimited, but iFinD column order varies by query.
    # Strategy: try keyword mapping first, then fall back to all columns as-is.
    header = [h.strip() for h in lines[0].split("|") if h.strip()]
    col_map = {}
    for i, h in enumerate(header):
        hc = h.replace("(元)", "").replace("(%)", "").replace("(股)", "").replace("（元）", "").replace("（万股）", "")
        if "日期" in hc: col_map["date"] = i
        elif "最高" in hc or ("高" in hc and "价" in hc and "最" not in hc): col_map["high"] = i
        elif "最低" in hc: col_map["low"] = i
        elif "成交" in hc and "量" in hc and "额" not in hc: col_map["volume"] = i
        elif "成交额" in hc: col_map["amount"] = i

    # open/close are ambiguous in garbled text — use positional:
    # iFinD standard OHLCV order puts close before high, open at end
    # Fallback: keep ALL numeric columns as named columns
    price_cols = [i for i, h in enumerate(header)
                  if any(kw in h for kw in ["价", "盘"]) and "日期" not in h]

    # If we found exactly 4 price columns, they're: close, high, low, open (in order)
    if "open" not in col_map and "close" not in col_map and len(price_cols) >= 4:
        col_map["close"] = price_cols[0]
        col_map["high"] = price_cols[1]
        col_map["low"] = price_cols[2]
        col_map["open"] = price_cols[3]
    elif "open" not in col_map and len(price_cols) >= 2:
        # Partial: try to fill missing
        for idx in price_cols:
            h = header[idx]
            if "收" in h: col_map["close"] = idx
            elif "开" in h: col_map["open"] = idx
            elif "最" in h and "高" in h: col_map["high"] = idx
            elif "最" in h and "低" in h: col_map["low"] = idx

    rows = []
    for line in lines[1:]:
        cols = [c.strip() for c in line.split("|")]
        cols = [c for c in cols if c]
        if len(cols) < 5: continue

        # 跳过非数据行（日期必须是8位数字）
        date_idx = col_map.get("date", -1)
        if date_idx >= len(cols): continue
        dv = cols[date_idx]
        if not dv.isdigit() or len(dv) != 8: continue

        row = {}
        for k, idx in col_map.items():
            if idx < len(cols): row[k] = cols[idx]
        if row.get("date"): rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    # Drop rows missing key columns, but be tolerant
    required = [c for c in ["open", "close"] if c in df.columns]
    if required:
        df = df.dropna(subset=required)
    if "date" in df.columns:
        df = df.sort_values("date")

    if len(df) >= 20:
        logger.info(f"iFinD K-line: {symbol} {len(df)} bars")
    return df


def _fallback_kline(symbol: str, days: int) -> pd.DataFrame:
    """push2 备用"""
    try:
        from src.a_share.fetcher import http_push2_kline
        df = http_push2_kline(symbol, days=days)
        if not df.empty and len(df) >= 20:
            logger.info(f"push2 fallback: {symbol} {len(df)} bars")
            return df
    except Exception:
        pass
    return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# 2. 智能选股
# ══════════════════════════════════════════════════════════════

def search_stocks(query: str) -> list[str]:
    """iFinD 智能选股 → 代码列表"""
    try:
        r = _ifind_call("stock", "search_stocks", {"query": query})
    except Exception as e:
        logger.error(f"iFinD search_stocks failed: {e}")
        return []

    if not r.get("ok"):
        logger.error(f"search_stocks error: {r.get('error')}")
        return []

    text = _extract_text(r)
    table = _parse_inner_json(text)
    codes = re.findall(r'\b(\d{6})\b', table)
    # iFinD返回的代码可能是纯6位数字或带后缀(000021.SZ)
    if not codes:
        codes = re.findall(r'\b(\d{6})\.(?:SZ|SH|BJ)\b', table)
    return list(dict.fromkeys(codes))


# ══════════════════════════════════════════════════════════════
# 3. 全市场筛选
# ══════════════════════════════════════════════════════════════

def screen_market_akshare(min_price=5, max_price=60, min_amount_yi=1.5,
                           min_amp=4.0) -> list[dict]:
    """全市场行情列表 — AKShare Sina源 (HTTP, 不需要SSL)

    iFinD search_stocks 对宽泛条件不稳定，用 AKShare 拉全市场，
    iFinD 专注K线等结构化数据
    """
    try:
        import akshare as ak
        df_all = ak.stock_zh_a_spot()
        candidates = []
        for _, r in df_all.iterrows():
            code = str(r.get("代码", "")); name = str(r.get("名称", ""))
            if not code or "ST" in name: continue
            price = float(r.get("最新价", 0))
            if price < min_price or price > max_price: continue
            pct = float(r.get("涨跌幅", 0))
            if abs(pct) >= 9.8: continue
            amount = float(r.get("成交额", 0))
            if amount < min_amount_yi * 1e8: continue
            high = float(r.get("最高", 0)); low = float(r.get("最低", 0))
            prev_close = float(r.get("昨收", 0))
            amplitude = (high - low) / prev_close * 100 if prev_close > 0 else 0
            if amplitude < min_amp: continue
            candidates.append({
                "code": code, "name": name, "price": price, "pct": pct,
                "amount": amount, "amplitude": amplitude,
                "turnover": 0, "total_mv": 0,
            })
        return candidates
    except Exception as e:
        logger.error(f"screen_market failed: {e}")
        return []
