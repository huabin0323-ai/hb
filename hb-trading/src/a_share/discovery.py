"""标的发现层 — 合并 serenity-alpha 事件驱动 + 数据驱动热门股"""
from __future__ import annotations

import logging
from collections import defaultdict

from src.a_share.fetcher import fetch_limit_up_pool, fetch_dragon_tiger, fetch_market_news, fetch_sector_spot
from src.a_share.hot_stocks import identify_hot_stocks

logger = logging.getLogger("a-share.discovery")


def discover_candidates(date_str: str, top_n: int = 5) -> list[dict]:
    """Phase 1: 发现候选标的池

    两条路径互补：
    1. 数据驱动：涨停板+龙虎榜→热度评分
    2. 事件驱动：盘后要闻→产业链受益标的识别

    Returns:
        [{code, name, source, heat_score, discovery_reason, boards, theme, ...}, ...]
    """
    candidates = {}

    # ── 路径1: 数据驱动（涨停板龙头+龙虎榜明星）──
    logger.info("路径1: 数据驱动热门股识别...")
    try:
        zt_df = fetch_limit_up_pool(date_str)
    except Exception as e:
        logger.warning(f"涨停板数据获取失败: {e}")
        zt_df = None

    try:
        dt_df = fetch_dragon_tiger(date_str)
    except Exception as e:
        logger.warning(f"龙虎榜数据获取失败: {e}")
        dt_df = None

    try:
        news = fetch_market_news()
    except Exception:
        news = None

    if zt_df is not None or dt_df is not None:
        hot = identify_hot_stocks(date_str, zt_df, dt_df, news=news, top_n=top_n)
        for s in hot:
            key = s["code"]
            candidates[key] = {
                "code": s["code"],
                "name": s["name"],
                "source": "data-driven",
                "heat_score": s["heat_score"],
                "boards": s.get("boards", 0),
                "theme": s.get("theme", ""),
                "net_buy": s.get("net_buy", 0),
                "discovery_reasons": s.get("reasons", []),
            }
        logger.info(f"数据驱动发现 {len(hot)} 只候选")

    # ── 路径2: 事件驱动（新闻→产业链受益标的）──
    logger.info("路径2: 事件驱动产业链线索挖掘...")
    event_candidates = _news_to_candidates(news, date_str)
    for s in event_candidates:
        key = s["code"]
        if key not in candidates:
            candidates[key] = s
            logger.info(f"事件驱动发现: {s['name']}({s['code']}) — {s['discovery_reasons'][0][:50] if s['discovery_reasons'] else ''}")

    # ── 合并排序 ──
    result = sorted(candidates.values(), key=lambda x: -x.get("heat_score", 5))
    logger.info(f"候选池总计 {len(result)} 只（数据驱动+事件驱动去重后）")
    return result[:top_n]


def _news_to_candidates(news: list[dict] | None, date_str: str) -> list[dict]:
    """事件驱动路径：从盘后要闻中识别产业链受益标的

    应用 serenity-alpha 核心逻辑：
    新闻 → 真实需求 → 财务传导 → 小市值弹性
    """
    if not news:
        return []

    candidates = []

    # 关键词→行业→标的映射表
    KEYWORD_STOCK_MAP = {
        "光模块": [("中际旭创", "300308"), ("新易盛", "300502"), ("天孚通信", "300394")],
        "CPO": [("中际旭创", "300308"), ("天孚通信", "300394")],
        "磷化铟": [("云南锗业", "002428"), ("鼎泰芯源", "待上市")],
        "钼": [("金钼股份", "601958"), ("洛阳钼业", "603993")],
        "半导体": [("北方华创", "002371"), ("中芯国际", "688981"), ("中微公司", "688012")],
        "AI芯片": [("寒武纪", "688256"), ("海光信息", "688041")],
        "数据中心": [("润泽科技", "300442"), ("奥飞数据", "300738"), ("光环新网", "300383")],
        "液冷": [("英维克", "002837"), ("高澜股份", "300499"), ("同飞股份", "300990")],
        "储能": [("宁德时代", "300750"), ("阳光电源", "300274"), ("亿纬锂能", "300014")],
        "固态电池": [("宁德时代", "300750"), ("国轩高科", "002074"), ("赣锋锂业", "002460")],
        "钠电池": [("宁德时代", "300750"), ("传艺科技", "002866"), ("维科技术", "600152")],
        "光伏": [("隆基绿能", "601012"), ("通威股份", "600438"), ("晶澳科技", "002459")],
        "风电": [("金风科技", "002202"), ("明阳智能", "601615"), ("运达股份", "300772")],
        "机器人": [("绿的谐波", "688017"), ("埃斯顿", "002747"), ("拓斯达", "300607")],
        "低空": [("万丰奥威", "002085"), ("中信海直", "000099"), ("亿航智能", "EH")],
        "有色": [("紫金矿业", "601899"), ("洛阳钼业", "603993"), ("铜陵有色", "000630")],
        "军工": [("中航西飞", "000768"), ("航天发展", "003547"), ("航发科技", "600391")],
        "创新药": [("恒瑞医药", "600276"), ("百济神州", "688235"), ("信达生物", "01801")],
        "稀土": [("北方稀土", "600111"), ("中国稀土", "000831")],
        "碳酸锂": [("赣锋锂业", "002460"), ("天齐锂业", "002466"), ("盐湖股份", "000792")],
        "PCB": [("沪电股份", "002463"), ("深南电路", "002916"), ("鹏鼎控股", "002938")],
        "HBM": [("通富微电", "002156"), ("长电科技", "600584")],
        "先进封装": [("通富微电", "002156"), ("长电科技", "600584"), ("华天科技", "002185")],
    }

    # 解析每条新闻
    for n in news[:10]:
        title = n.get("title", "")
        for keyword, stocks in KEYWORD_STOCK_MAP.items():
            if keyword in title:
                for stock_name, stock_code in stocks:
                    # 只加A股（排除待上市和美股/港股）
                    if stock_code in ("待上市", "EH") or stock_code.startswith("0"):
                        if stock_code.isdigit() and len(stock_code) <= 5:
                            continue  # 港股代码跳过
                    candidates.append({
                        "code": stock_code,
                        "name": stock_name,
                        "source": "event-driven",
                        "heat_score": 8,  # 事件驱动基础分
                        "boards": 0,
                        "theme": keyword,
                        "net_buy": 0,
                        "discovery_reasons": [
                            f"新闻提及「{keyword}」→ {title[:60]}"
                        ],
                    })

    # 去重
    seen = {}
    unique = []
    for c in candidates:
        if c["code"] not in seen:
            seen[c["code"]] = c
            unique.append(c)
        else:
            # 合并理由
            seen[c["code"]]["discovery_reasons"].extend(c["discovery_reasons"])

    return unique


def compute_quick_filter(candidate: dict, limit_up_df=None) -> dict:
    """Phase 2: 快速筛选 — tam-adj-peg 近似 + gf-dma-health-index（真实DMA数据）

    用新浪K线计算均线结构，补连板+龙虎榜信息，做综合判断
    """
    import logging
    _log = logging.getLogger("a-share.filter")

    warnings = []
    score = 10
    code = candidate.get("code", "")
    name = candidate.get("name", "")
    boards = candidate.get("boards", 0)

    # ── DMA 数据（新浪K线，真实均线）──
    dma = {}
    try:
        from src.a_share.fetcher import compute_dma_metrics
        dma = compute_dma_metrics(code)
        if "error" not in dma:
            _log.info(f"{name}({code}) DMA: price={dma.get('price')}, "
                      f"MA5/20/50={dma.get('ma30')}/{dma.get('ma20')}/{dma.get('ma50')}, "
                      f"ranking={dma.get('ma_ranking')}, "
                      f"dma20_pct={dma.get('dma20_pct')}%, escape={dma.get('escape_ratio')}")
    except Exception as e:
        _log.warning(f"DMA计算失败({code}): {e}")
        dma = {"error": str(e)}

    # ── PE 估值数据（AKShare stock_value_em，可用）──
    val = {}
    try:
        from src.a_share.fetcher import fetch_valuation
        val = fetch_valuation(code)
        if val:
            _log.info(f"{name}({code}) PE={val.get('pe_ttm')} PB={val.get('pb')} PEG={val.get('peg')}")
    except Exception as e:
        _log.warning(f"估值获取失败({code}): {e}")

    # ── tam-adj-peg（真实PE版）──
    boards = candidate.get("boards", 0)
    pe = val.get("pe_ttm")
    peg = val.get("peg")

    # 有真实PE数据时做精确判断
    if pe is not None and pe != 0:
        if pe < 0:
            warnings.append(f"PE为负(亏损)→不纳入深度分析候选")
            score -= 5
            tam_ok = False
        elif pe > 200:
            warnings.append(f"PE={pe:.0f}→极端估值，仅做事件驱动")
            score -= 4
            tam_ok = boards <= 2  # 只有低位连板+极端PE才放行
        elif pe > 100:
            warnings.append(f"PE={pe:.0f}→极高估值")
            score -= 3
            tam_ok = boards <= 3
        elif pe > 50:
            warnings.append(f"PE={pe:.0f}→偏高")
            score -= 1
            tam_ok = True
        elif pe > 0:
            warnings.append(f"PE={pe:.0f}→合理区间")
            score += 2
            tam_ok = True

        if peg is not None and peg != 0:
            if peg < 0:
                warnings.append(f"PEG为负(利润下滑)→基本面恶化")
                score -= 3
            elif peg > 3:
                warnings.append(f"PEG={peg:.1f}→增长严重透支")
                score -= 2
            elif peg > 1.5:
                warnings.append(f"PEG={peg:.1f}→偏贵")
                score -= 1
            elif 0 < peg < 1.0:
                warnings.append(f"PEG={peg:.2f}→增长未被充分定价")
                score += 3
    else:
        # 无PE数据时用连板数近似
        if boards >= 5:
            warnings.append(f"连板{boards}板→PE不可靠")
            tam_ok = True
        elif boards >= 3:
            warnings.append(f"连板{boards}板→估值偏高概率大")
            score -= 2
            tam_ok = True
        else:
            tam_ok = True
            score += 2

    # ── gf-dma-health-index（真实DMA数据版）──
    if dma and "error" not in dma:
        ma_ranking = dma.get("ma_ranking", "")
        dma20_pct = dma.get("dma20_pct")
        escape = dma.get("escape_ratio")

        # 均线排列评分
        if ma_ranking == "bullish":
            score += 3
            warnings.append("均线多头排列→趋势健康")
        elif ma_ranking == "bearish":
            score -= 3
            warnings.append("均线空头排列→趋势偏弱")
        elif ma_ranking == "mixed":
            warnings.append("均线交织→方向待选择")

        # 乖离率评分
        if dma20_pct is not None:
            if 0 <= dma20_pct <= 10:
                score += 2
                warnings.append(f"乖离+{dma20_pct}%→健康区间")
            elif 10 < dma20_pct <= 20:
                score -= 1
                warnings.append(f"乖离+{dma20_pct}%→偏热")
            elif dma20_pct > 20:
                score -= 3
                warnings.append(f"乖离+{dma20_pct}%→严重过热，均值回归压力大")
            elif -5 <= dma20_pct < 0:
                score += 1
                warnings.append(f"乖离{dma20_pct}%→温和回调，可能是机会")
            elif dma20_pct < -10:
                score -= 2
                warnings.append(f"乖离{dma20_pct}%→深度回调，趋势可能破坏")

        # Escape Ratio
        if escape is not None:
            if escape > 2.5:
                score -= 3
                warnings.append(f"EscapeRatio={escape}→FOMO逃逸！")
            elif escape > 1.8:
                score -= 1
                warnings.append(f"EscapeRatio={escape}→短线过热")

    # 连板FOMO扣分（叠加DMA判断后更精准）
    if boards >= 4:
        warnings.append(f"连板{boards}板→FOMO逃逸风险极高")
        score -= 3
        health_ok = boards <= 5  # 4-5板仍可观察
        if health_ok:
            warnings.append("需关注换手率和炸板次数：如果换手<1%且0炸板→锁筹健康；如果换手骤增→开板风险")
        else:
            warnings.append("连板>5板→FOMO极高，不纳入深度分析候选")
    elif boards >= 2:
        warnings.append(f"2连板→短线偏热，关注是否为换手板→一字板加速（健康）还是连续一字板（锁筹风险）")
        score -= 1
        health_ok = True
    else:
        health_ok = True
        score += 1

    # 龙虎榜辅助判断
    net_buy = candidate.get("net_buy", 0)
    if net_buy > 5:
        score += 2
    elif net_buy < -3:
        score -= 2
    elif net_buy > 0:
        score += 1

    # 打分门槛：>=8 通过（健康标的），5-7 标记高风险但可观察，<5 直接淘汰
    if score >= 8:
        passed = True
    elif score >= 5 and boards <= 3:
        passed = True  # 低评分但非极端连板，给机会
        warnings.append("⚠️ 低评分通过——深度分析中需重点审视风险")
    else:
        passed = False
        warnings.append("❌ 评分不足或风险过高，建议仅观察不入深研")

    return {
        "passed": passed,
        "tam_adj_peg_ok": tam_ok,
        "health_ok": health_ok,
        "warnings": warnings,
        "score": score,
        "dma": dma if dma and "error" not in dma else {},
    }
