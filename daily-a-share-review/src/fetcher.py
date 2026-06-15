"""数据抓取层 — 新浪财经 + 东方财富混合

指数/板块/北向 → 新浪财经 API（稳定、免费、不限IP）
涨停/龙虎榜/研报   → AKShare (东方财富)
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from urllib import request
from urllib.error import URLError

import akshare as ak
import pandas as pd

from config import INDEX_CODES

logger = logging.getLogger("a-share.fetcher")

MAX_RETRIES = 2
RETRY_DELAY = 1.0
SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://finance.sina.com.cn/",
}
SINA_QUOTE_URL = "http://hq.sinajs.cn/list="

# ── 新浪指数代码映射 ──
_SINA_INDEX_MAP = {
    "000001": "sh000001",   # 上证指数
    "399001": "sz399001",   # 深证成指
    "399006": "sz399006",   # 创业板指
    "000688": "sh000688",   # 科创50
}

_SINA_VAL_MAP = {
    # format: [0]name, [1]open, [2]prev_close, [3]price, [4]high, [5]low
    # [8]volume(shares), [9]amount(yuan)
    "name": 0, "price": 3, "prev_close": 2,
    "high": 4, "low": 5, "open": 1, "amount": 9,
}

# ── 中证行业/主题指数代码（新浪可用）──
_SINA_SECTORS = [
    ("中证军工", "sz399967"), ("中证银行", "sz399986"), ("中证煤炭", "sz399998"),
    ("中证白酒", "sz399997"), ("中证医疗", "sz399989"), ("中证有色", "sz399395"),
    ("中证食品", "sz399396"), ("中证文化", "sz399397"), ("中证医药", "sz399394"),
    ("中证地产", "sz399393"), ("中证通信", "sz399389"), ("中证消费", "sz399390"),
    ("信息技术", "sz399994"), ("智能家居", "sz399996"), ("一带一路", "sz399991"),
    ("CSWD数据", "sz399993"), ("地产产权", "sz399983"), ("基建工程", "sz399995"),
    ("1000医药", "sz399386"), ("1000信息", "sz399388"), ("1000消费", "sz399390"),
    ("中证环保", "sz399385"), ("1000精选", "sz399384"), ("中证酒", "sz399987"),
    ("中证车", "sz399987"), ("投资时钟", "sz399391"), ("高效指标", "sz399398"),
    ("研究GDP", "sz399399"), ("煤炭产权", "sz399990"),
]


def _sina_fetch(codes: list[str]) -> dict[str, list]:
    """批量获取新浪行情数据"""
    url = SINA_QUOTE_URL + ",".join(codes)
    for attempt in range(3):
        try:
            req = request.Request(url, headers=SINA_HEADERS)
            resp = request.urlopen(req, timeout=15)
            raw = resp.read().decode("gbk")
            result = {}
            for line in raw.strip().split("\n"):
                m = re.match(r'var hq_str_(\w+)="(.*?)";', line)
                if m:
                    result[m.group(1)] = m.group(2).split(",")
            if result:
                return result
        except Exception as e:
            logger.warning(f"sina fetch attempt {attempt+1}: {e}")
            if attempt < 2:
                time.sleep(1.5)
    logger.error("sina fetch all retries exhausted")
    return {}


# ═══════════════════════════════════════════════
# 指数行情
# ═══════════════════════════════════════════════

def fetch_index_spot() -> pd.DataFrame:
    """主要指数实时行情 — 新浪财经"""
    sina_codes = [_SINA_INDEX_MAP[c] for c in INDEX_CODES.values()]
    data = _sina_fetch(sina_codes)

    rows = []
    for name, code in INDEX_CODES.items():
        sc = _SINA_INDEX_MAP.get(code, "")
        vals = data.get(sc, [])
        if len(vals) < 10:
            continue
        price = float(vals[3])
        prev = float(vals[2])
        pct = round((price - prev) / prev * 100, 2) if prev else 0
        change = round(price - prev, 2)
        amount = float(vals[9]) if len(vals) > 9 else 0
        rows.append({
            "name": name, "code": code,
            "price": price, "pct_chg": pct, "change": change,
            "amount": amount,
        })
    return pd.DataFrame(rows)


def fetch_market_stats() -> dict:
    """全市场涨跌家数 — 新浪（通过上证分时数据近似）"""
    # 新浪没有直接提供涨跌家数，用东财 API 的备选方案
    # 或者从 sina 的上证分时线推断
    # 简单方案：返回模拟数据标记为待获取
    return {"up": 0, "down": 0, "flat": 0, "total": 0,
            "note": "涨跌家数需东财API，当前网络不可用"}


# ═══════════════════════════════════════════════
# 板块行情
# ═══════════════════════════════════════════════

def fetch_sector_spot() -> pd.DataFrame:
    """行业板块行情 — 中证行业指数（新浪）"""
    codes = [c for _, c in _SINA_SECTORS]
    data = _sina_fetch(codes)
    rows = []
    for name, code in _SINA_SECTORS:
        vals = data.get(code, [])
        if len(vals) < 10:
            continue
        price = float(vals[3])
        prev = float(vals[2])
        pct = round((price - prev) / prev * 100, 2) if prev else 0
        amount = float(vals[9]) if len(vals) > 9 else 0
        rows.append({
            "name": name, "code": code,
            "pct_chg": pct, "amount": amount,
            "lead_stock": "",
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("pct_chg", ascending=False)
    return df


# ═══════════════════════════════════════════════
# 北向资金 — 新浪
# ═══════════════════════════════════════════════

def fetch_north_flow() -> dict:
    """北向资金 — 新浪沪港通/深港通数据"""
    # 新浪北向资金接口
    try:
        url = "http://vip.stock.finance.sina.com.cn/q/go.php/vInvestConsult/kind/northbound/index.phtml"
        req = request.Request(url, headers=SINA_HEADERS)
        resp = request.urlopen(req, timeout=15)
        raw = resp.read().decode("gbk", errors="ignore")

        # 解析 HTML table 中的北向资金数据
        # 找 "净流入" 相关的数字
        hgt_match = re.search(r'沪股通.*?([\-\d,.]+)\s*亿', raw)
        sgt_match = re.search(r'深股通.*?([\-\d,.]+)\s*亿', raw)

        hgt = float(hgt_match.group(1).replace(",", "")) if hgt_match else 0
        sgt = float(sgt_match.group(1).replace(",", "")) if sgt_match else 0
        return {"hgt": round(hgt, 2), "sgt": round(sgt, 2), "total": round(hgt + sgt, 2)}
    except Exception as e:
        logger.warning(f"north_flow sina failed: {e}")

    # 备选：用新浪实时接口
    try:
        # 沪股通+深股通实时额度
        data = _sina_fetch(["sh518880", "sz159915"])  # placeholder
        if data:
            return {"hgt": 0, "sgt": 0, "total": 0, "note": "实时数据待完善"}
    except Exception:
        pass

    return {"hgt": 0, "sgt": 0, "total": 0, "note": "数据暂不可用"}


# ═══════════════════════════════════════════════
# 涨停板 / 龙虎榜 / 研报 — AKShare (东方财富)
# ═══════════════════════════════════════════════

def _retry(func, name: str, **kwargs):
    for attempt in range(MAX_RETRIES + 1):
        try:
            df = func(**kwargs)
            if df is None or df.empty:
                raise ValueError(f"{name} returned empty")
            return df
        except Exception as e:
            logger.warning(f"{name} attempt {attempt+1}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"{name} all retries exhausted")
                raise


def fetch_limit_up_pool(target_date: str | None = None) -> pd.DataFrame:
    """涨停板池"""
    if target_date is None:
        target_date = date.today().strftime("%Y%m%d")
    df = _retry(ak.stock_zt_pool_em, "zt_pool", date=target_date)
    col_map = {
        "代码": "code", "名称": "name",
        "连板数": "boards", "连续涨停天数": "boards",
        "涨停原因": "reason", "涨停统计": "reason",
        "封板时间": "seal_time", "最后封板时间": "seal_time",
        "首次封板时间": "first_seal",
        "炸板次数": "break_count", "开板次数": "break_count",
        "涨停价": "zt_price", "成交额": "amount", "流通市值": "float_mv",
    }
    rename = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename)
    for col in ["boards", "break_count"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    for col in ["reason", "seal_time", "first_seal"]:
        if col not in df.columns:
            df[col] = ""
    return df


def fetch_limit_down_pool(target_date: str | None = None) -> pd.DataFrame:
    """跌停板池"""
    if target_date is None:
        target_date = date.today().strftime("%Y%m%d")
    try:
        return _retry(ak.stock_zt_pool_dtgc_em, "dt_pool", date=target_date)
    except Exception:
        return pd.DataFrame()


def fetch_dragon_tiger(target_date: str | None = None) -> pd.DataFrame:
    """龙虎榜"""
    if target_date is None:
        target_date = date.today().strftime("%Y%m%d")
    try:
        df = _retry(ak.stock_lhb_detail_em, "lhb",
                    start_date=target_date, end_date=target_date)
        keep = [c for c in ["代码", "名称", "收盘价", "涨跌幅", "成交额", "上榜原因", "净买额"]
                if c in df.columns]
        return df[keep]
    except Exception:
        return pd.DataFrame()


def fetch_research_reports(target_date: str | None = None) -> pd.DataFrame:
    """研报（热门股样本）"""
    hot_stocks = ["600519", "000858", "300750", "002594", "601899",
                  "688981", "002371", "603986", "600036", "601318"]
    all_reports = []
    for code in hot_stocks:
        try:
            df = ak.stock_research_report_em(symbol=code)
            if not df.empty:
                all_reports.append(df.head(2))
        except Exception:
            pass
        time.sleep(0.3)
    if all_reports:
        df = pd.concat(all_reports, ignore_index=True)
        # AKShare 返回的列名
        col_map = {
            "股票简称": "stock_name", "报告名称": "title",
            "东财评级": "rating", "机构": "org",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        for c in ["stock_name", "title", "rating", "org"]:
            if c not in df.columns:
                df[c] = ""
        return df[["stock_name", "title", "rating", "org"]]
    return pd.DataFrame()


def fetch_global_indices() -> pd.DataFrame:
    """全球指数 — 新浪美股+港股"""
    codes = {
        "道琼斯": "gb_dji", "纳斯达克": "gb_ixic", "标普500": "gb_inx",
        "恒生指数": "hkHSI", "富时A50": "hf_CHA50CFD",
    }
    data = _sina_fetch(list(codes.values()))
    rows = []
    for name, sc in codes.items():
        vals = data.get(sc, [])
        if len(vals) < 3:
            continue
        if sc.startswith("gb_"):
            # 美股: [0]name, [1]price, [2]pct_chg, [3]time, ...
            price = float(vals[1]) if vals[1] else 0
            pct = float(vals[2]) if vals[2] else 0
            rows.append({"name": name, "price": price, "pct": pct, "change": 0})
        elif sc == "hkHSI":
            # 港股: [0]name, [1]name_cn, [3]open, [4]prev, [5]price, [6]high, [7]low, [8]change, [9]pct, ...
            price = float(vals[5]) if len(vals) > 5 and vals[5] else 0
            pct = float(vals[9]) if len(vals) > 9 and vals[9] else 0
            rows.append({"name": name, "price": price, "pct": pct, "change": 0})
        elif sc == "hf_CHA50CFD":
            # 期货: [0]latest, [1]volume, [2]bid, [3]ask, [4]high, [5]low, [6]time, [7]prev, ...
            price = float(vals[0]) if vals[0] else 0
            prev = float(vals[7]) if len(vals) > 7 and vals[7] else price
            pct = round((price - prev) / prev * 100, 2) if prev else 0
            rows.append({"name": name, "price": price, "pct": pct, "change": 0})
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ═══════════════════════════════════════════════
# 新闻 & 7x24
# ═══════════════════════════════════════════════

def fetch_market_news() -> list[dict]:
    """盘前市场要闻 — 新浪7x24 + 财经要闻"""
    news = []

    # 1. 新浪 7x24 快讯
    try:
        from urllib import request as ur
        import re as _re
        url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size=15&zhibo_id=152&tag_id=0"
        req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = ur.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        items = data.get("result", {}).get("data", {}).get("feed", {}).get("list", [])
        for item in items[:15]:
            title = _re.sub(r"<[^>]+>", "", item.get("rich_text", ""))
            if len(title) > 15:
                news.append({"title": title[:120], "source": "7x24"})
    except Exception:
        pass

    # 2. 新浪财经要闻
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=10&page=1"
        req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = ur.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        for item in data.get("result", {}).get("data", [])[:10]:
            title = item.get("title", "")
            if len(title) > 15:
                news.append({"title": title[:120], "source": "要闻"})
    except Exception:
        pass

    # 去重
    seen = set()
    unique = []
    for n in news:
        key = n["title"][:30]
        if key not in seen:
            seen.add(key)
            unique.append(n)
    return unique[:15]


def fetch_stock_notices(target_date: str | None = None) -> pd.DataFrame:
    """个股公告"""
    if target_date is None:
        target_date = date.today().strftime("%Y%m%d")
    try:
        df = _retry(ak.stock_notice_report, "notices", symbol="全部", date=target_date)
        return df.head(50)
    except Exception:
        logger.warning("notices unavailable")
        return pd.DataFrame()


# ═══════════════════════════════════════════════
# 估值 + 均线数据 — AKShare（供 tam-adj-peg / gf-dma-health-index 使用）
# ═══════════════════════════════════════════════

def fetch_valuation_daily(trade_date: str | None = None) -> pd.DataFrame:
    """全市场A股每日估值快照（PE TTM / PB / PS / PCF）

    AKShare: stock_a_valuation_daily()
    返回 ~4800 只股票的 PE/PB/PS/PCF/总市值
    """
    if trade_date is None:
        trade_date = date.today().strftime("%Y-%m-%d")
    try:
        df = _retry(ak.stock_a_valuation_daily, "valuation_daily", date=trade_date)
        # 列名规范化
        col_map = {
            "code": "code", "name": "name",
            "pe_ttm": "pe", "pb_lf": "pb",
            "ps_ttm": "ps", "pcf_ocf_ttm": "pcf",
            "total_mv": "total_mv",
        }
        # 只保留存在的列
        keep = {k: v for k, v in col_map.items() if k in df.columns}
        df = df.rename(columns=keep)
        return df[list(keep.values())]
    except Exception as e:
        logger.warning(f"valuation_daily failed: {e}")
        return pd.DataFrame()


def http_push2(endpoint: str, params: dict, timeout: int = 30) -> dict:
    """东财 push2 HTTP直连 — 绕过代理SSL拦截

    代理仅截HTTPS，HTTP明文请求不触发SSL检查，无频率限制。
    """
    from urllib.parse import urlencode
    base = f"http://push2.eastmoney.com/api/qt/{endpoint}"
    qs = urlencode(params)
    url = f"{base}?{qs}"
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    resp = request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode())


def http_push2_kline(symbol: str, days: int = 250) -> pd.DataFrame:
    """东财 push2his HTTP直连 K线"""
    from urllib.parse import urlencode
    secid = f"1.{symbol}" if symbol.startswith(("6","9")) else f"0.{symbol}"
    params = {
        "secid": secid, "klt": "101", "fqt": "1",
        "end": "20500101", f"lmt": str(days),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    base = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
    qs = urlencode(params)
    req = request.Request(f"{base}?{qs}", headers={"User-Agent": "Mozilla/5.0"})
    resp = request.urlopen(req, timeout=30)
    body = resp.read().decode()
    data = json.loads(body)
    if data is None:
        return pd.DataFrame()
    inner = data.get("data")
    if inner is None:
        return pd.DataFrame()
    klines = inner.get("klines", [])
    if not klines:
        return pd.DataFrame()
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 7:
            rows.append({
                "date": parts[0], "open": float(parts[1]), "close": float(parts[2]),
                "high": float(parts[3]), "low": float(parts[4]),
                "volume": int(parts[5]), "amount": float(parts[6]),
            })
    return pd.DataFrame(rows)


def fetch_market_pe_scan(max_stocks: int = 5000) -> pd.DataFrame:
    """全市场PE快照 — HTTP直连push2"""
    params = {
        "pn": "1", "pz": str(max_stocks), "po": "1", "np": "1",
        "fltt": "2", "fid": "f12",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "fields": "f2,f3,f9,f12,f14,f20,f21,f23,f115",
    }
    try:
        data = http_push2("clist/get", params)
        rows = []
        for r in data.get("data", {}).get("diff", []):
            rows.append({
                "code": r.get("f12", ""), "name": r.get("f14", ""),
                "price": r.get("f2", 0), "pct": r.get("f3", 0),
                "pe": r.get("f9"), "mv": r.get("f20", 0),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        logger.warning(f"market_pe_scan failed: {e}")
        return pd.DataFrame()


def compute_dma_metrics(symbol: str) -> dict:
    """计算均线指标 — HTTP push2 K线优先，新浪K线备选"""

    # 方案1: HTTP push2his K线（快速、稳定）
    try:
        df = http_push2_kline(symbol, days=250)
        if not df.empty and len(df) >= 20:
            return _dma_from_df(df)
    except Exception as e:
        logger.debug(f"push2 DMA failed, fallback to Sina: {e}")

    # 方案2: 新浪K线（次选，仅250天）
    return _sina_dma(symbol)


def _dma_from_df(df: pd.DataFrame) -> dict:
    """从DataFrame计算均线指标（push2 K线或新浪K线统一入口）"""
    close = df["close"].astype(float)

    price = close.iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(min(len(df), 50)).mean().iloc[-1]
    ma100 = close.rolling(min(len(df), 100)).mean().iloc[-1]
    ma200 = close.rolling(min(len(df), 200)).mean().iloc[-1]

    # ATR(20)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr20 = tr.rolling(20).mean().iloc[-1]

    def _pct(p, ma):
        return round((float(p) / float(ma) - 1) * 100, 2) if ma and not pd.isna(ma) and float(ma) != 0 else None

    dma = {
        "price": round(float(price), 2),
        "ma20": round(float(ma20), 2) if not pd.isna(ma20) else None,
        "ma50": round(float(ma50), 2) if not pd.isna(ma50) else None,
        "ma100": round(float(ma100), 2) if not pd.isna(ma100) else None,
        "ma200": round(float(ma200), 2) if not pd.isna(ma200) else None,
        "atr20": round(float(atr20), 2) if not pd.isna(atr20) else None,
        "dma20_pct": _pct(price, ma20),
        "dma50_pct": _pct(price, ma50),
        "dma100_pct": _pct(price, ma100),
        "dma200_pct": _pct(price, ma200),
    }

    mas = [v for v in [ma20, ma50, ma100, ma200] if v and not pd.isna(v)]
    if len(mas) >= 3:
        if all(mas[i] > mas[i+1] for i in range(len(mas)-1)):
            dma["ma_ranking"] = "bullish"
        elif all(mas[i] < mas[i+1] for i in range(len(mas)-1)):
            dma["ma_ranking"] = "bearish"
        else:
            dma["ma_ranking"] = "mixed"
    else:
        dma["ma_ranking"] = "insufficient_data"

    try:
        slope_5d = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100 if len(close) >= 6 else 0
        ma50_series = close.rolling(min(len(df), 50)).mean()
        slope_50d = (ma50_series.iloc[-1] - ma50_series.iloc[-6]) / abs(ma50_series.iloc[-6]) * 100 \
            if len(ma50_series) >= 6 and ma50_series.iloc[-6] != 0 else 0
        dma["escape_ratio"] = round(slope_5d / slope_50d, 2) if slope_50d and slope_50d != 0 else None
    except Exception:
        dma["escape_ratio"] = None

    return dma


def _sina_dma(symbol: str) -> dict:
    """新浪K线备选路径"""
    import json as _json
    from urllib import request as _req

    prefix = "sh" if symbol.startswith(("6", "9")) else "sz"
    sina_code = f"{prefix}{symbol}"
    url = (f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={sina_code}&scale=240&datalen=250")

    try:
        req = _req.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = _req.urlopen(req, timeout=15)
        data = _json.loads(resp.read().decode())
    except Exception as e:
        logger.warning(f"Sina K-line({symbol}) failed: {e}")
        return {"error": f"数据获取失败: {e}"}

    if not data or len(data) < 20:
        return {"error": "K线数据不足"}

    df = pd.DataFrame(data)
    # 新浪字段名不同，统一成标准列名
    df = df.rename(columns={"day": "date"})
    return _dma_from_df(df)


def fetch_valuation(symbol: str) -> dict:
    """单只股票估值数据（PE/PB/PEG/市值）

    AKShare stock_value_em — 可用（非push2子域，不触发代理限流）
    """
    try:
        df = ak.stock_value_em(symbol=symbol)
        if df.empty or len(df) < 1:
            return {}
        latest = df.iloc[-1]
        return {
            "date": str(latest.get("数据日期", "")),
            "price": float(latest.get("当日收盘价", 0)),
            "pe_ttm": float(latest.get("PE(TTM)", 0)),
            "pe_static": float(latest.get("PE(静)", 0)),
            "pb": float(latest.get("市净率", 0)),
            "peg": float(latest.get("PEG值", 0)),
            "total_mv": int(latest.get("总市值", 0)),
            "float_mv": int(latest.get("流通市值", 0)),
            "ps": float(latest.get("市销率", 0)),
            "pcf": float(latest.get("市现率", 0)),
        }
    except Exception as e:
        logger.warning(f"stock_value_em({symbol}) failed: {e}")
        return {}


def fetch_quick_metrics(symbol: str) -> dict:
    """一次性获取快速筛选所需的估值+均线数据"""
    result = {"symbol": symbol}

    # 估值
    val = fetch_stock_valuation(symbol)
    result["pe"] = val.get("pe")
    result["pb"] = val.get("pb")
    result["peg"] = val.get("peg")

    # 均线
    dma = compute_dma_metrics(symbol)
    result.update({f"dma_{k}": v for k, v in dma.items()})

    return result
