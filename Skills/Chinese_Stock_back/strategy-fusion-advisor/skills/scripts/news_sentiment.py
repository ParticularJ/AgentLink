#!/usr/bin/env python3
"""
涨停板新闻情绪检测模块
通过搜索近期新闻/公告/研报，判断个股是否存在重大利空或利多
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ——————————————————————————
# 利空 / 利多 关键词库
# ——————————————————————————

NEGATIVE_KEYWORDS = [
    # 监管 & 风险
    "问询函", "监管函", "关注函", "警示函", "立案调查", "涉嫌违规", "涉嫌信息披露",
    "行政处罚", "纪律处分", "市场禁入", "风险提示", "退市风险", "ST", "*ST",
    "暂停上市", "终止上市", "强制退市", "业绩变脸", "大幅下调", "业绩修正",
    "商誉减值", "资产减值", "大幅亏损", "债务危机", "资金紧张", "流动性风险",
    "诉讼仲裁", "仲裁事项", "法律诉讼", "股份冻结", "轮候冻结", "司法冻结",
    "减持", "清仓式减持", "大幅减持", "高比例质押", "质押触及平仓", "强制平仓",
    "澄清公告", "澄清说明", "未发现", "不存在", "未触及", "郑重澄清",
    "虚假信息", "谣言", "不实传闻", "蹭热点", "投机炒作",
]

POSITIVE_KEYWORDS = [
    # 政策 & 行业
    "政策利好", "政策支持", "行业景气", "市场需求旺盛", "订单饱满", "产能扩张",
    "业绩增长", "净利润增长", "营收增长", "超预期增长", "大幅增长", "扭亏为盈",
    "回购", "增持", "员工持股", "股权激励", "战略合作", "中标", "重大合同",
    "技术突破", "研发成功", "新产品", "新业务", "市场份额提升", "进口替代",
    "国产替代", "产业链升级", "降本增效", "毛利率提升", "ROE提升",
]


def search_stock_news(code: str, name: str, days: int = 7) -> Dict:
    """
    使用 Tavily 搜索个股近期新闻，返回情绪分析结果

    Returns:
        {
            "has_news": bool,
            "sentiment": "negative" | "neutral" | "positive",
            "sentiment_score": float,   # -100 ~ +100
            "negative_count": int,
            "positive_count": int,
            "highlights": List[str],     # 关键信息片段
            "risk_warnings": List[str],  # 利空预警
            "news_summary": str,
        }
    """
    try:
        from tavily import TavilyClient
    except ImportError:
        return _search_stock_news_fallback(code, name, days)

    api_key = "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"

    print("11111111111111111111111111111111")
    if not api_key:
        # 尝试从配置读取
        cfg_path = os.path.expanduser("~/.openclaw/config.json")
        if os.path.exists(cfg_path):
            try:
                import json
                with open(cfg_path) as f:
                    cfg = json.load(f)
                api_key = cfg.get("tavily_api_key") or os.getenv("TAVILY_API_KEY")
            except:
                pass
        if not api_key:
            return _search_stock_news_fallback(code, name, days)

    try:
        client = TavilyClient(api_key=api_key)
        # 搜索 query：股票名称 + 代码 + 近7日
        query = f"{name}（{code}）股票 最新公告 新闻 {days}日内"
        results = client.search(
            query=query,
            search_depth="basic",
            max_results=10,
            time_range="week" if days <= 7 else "month",
        )

        articles = results.get("results", [])

        print("articles: ", articles)
        return _analyze_sentiment(code, name, articles)

    except Exception as e:
        print(f"[WARN] Tavily搜索失败 {code}: {e}", file=sys.stderr)
        return _search_stock_news_fallback(code, name, days)


def _search_stock_news_fallback(code: str, name: str, days: int = 7) -> Dict:
    """
    当 Tavily 不可用时的降级方案：使用 requests 直接搜索东方财富快讯
    """
    import requests
    import re

    result = {
        "has_news": False,
        "sentiment": "neutral",
        "sentiment_score": 0.0,
        "negative_count": 0,
        "positive_count": 0,
        "highlights": [],
        "risk_warnings": [],
        "news_summary": "（数据获取失败，无法分析新闻情绪）",
    }

    # 东方财富个股快讯接口
    url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    params = {
        "sr": -1,
        "page_size": 10,
        "page_index": 1,
        "ann_type": "A,ARC,CT",
        "client_source": "web",
        "stock_list": code,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://data.eastmoney.com/announcement/{code}.html",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        data = resp.json()
        notices = data.get("data", {}).get("list", [])
        if not notices:
            return result
    except Exception:
        return result

    highlights = []
    risk_warnings = []
    neg_cnt, pos_cnt = 0, 0

    for n in notices:
        title = str(n.get("notice_title", ""))
        # 过滤时间
        try:
            pub_date = n.get("publish_date", "")
            if pub_date:
                pub_dt = datetime.strptime(pub_date[:10], "%Y-%m-%d")
                if (datetime.now() - pub_dt).days > days:
                    continue
        except:
            pass

        title_lower = title.lower()
        full_text = str(n.get("art_content", ""))[:500]

        # 检查利空
        for kw in NEGATIVE_KEYWORDS:
            if kw in title or kw in full_text:
                neg_cnt += 1
                risk_warnings.append(f"[{kw}] {title[:40]}")
                break

        # 检查利多
        for kw in POSITIVE_KEYWORDS:
            if kw in title:
                pos_cnt += 1
                highlights.append(f"[{kw}] {title[:40]}")
                break

        if len(highlights) + len(risk_warnings) >= 8:
            break

    if neg_cnt == 0 and pos_cnt == 0:
        result["has_news"] = False
        result["news_summary"] = f"近{days}日无重大公告"
        return result

    result["has_news"] = True
    result["negative_count"] = neg_cnt
    result["positive_count"] = pos_cnt
    result["highlights"] = highlights[:5]
    result["risk_warnings"] = risk_warnings[:5]

    # 情绪打分：利空权重更高（亏损的影响不对称）
    net = pos_cnt - neg_cnt * 1.5
    score = max(-100, min(100, net * 25))
    result["sentiment_score"] = score

    if score <= -30:
        result["sentiment"] = "negative"
        result["news_summary"] = f"⚠️ 检测到{neg_cnt}条利空公告，建议回避"
    elif score >= 30:
        result["sentiment"] = "positive"
        result["news_summary"] = f"✅ 检测到{pos_cnt}条利好公告，短线情绪偏多"
    else:
        result["sentiment"] = "neutral"
        result["news_summary"] = f"中性（利好{pos_cnt}条 / 利空{neg_cnt}条），无重大风险"

    return result


def _analyze_sentiment(code: str, name: str, articles: List[Dict]) -> Dict:
    """对 Tavily 搜索结果进行情绪分析"""
    result = {
        "has_news": len(articles) > 0,
        "sentiment": "neutral",
        "sentiment_score": 0.0,
        "negative_count": 0,
        "positive_count": 0,
        "highlights": [],
        "risk_warnings": [],
        "news_summary": "",
    }

    if not articles:
        return result

    neg_cnt, pos_cnt = 0, 0
    highlights = []
    risk_warnings = []

    for art in articles:
        title = str(art.get("title", ""))
        snippet = str(art.get("snippet", ""))[:300]

        for kw in NEGATIVE_KEYWORDS:
            if kw in title or kw in snippet:
                neg_cnt += 1
                risk_warnings.append(f"[{kw}] {title[:50]}")
                break

        for kw in POSITIVE_KEYWORDS:
            if kw in title:
                pos_cnt += 1
                highlights.append(f"[{kw}] {title[:50]}")
                break

    result["negative_count"] = neg_cnt
    result["positive_count"] = pos_cnt
    result["highlights"] = highlights[:5]
    result["risk_warnings"] = risk_warnings[:5]

    net = pos_cnt - neg_cnt * 1.5
    score = max(-100, min(100, net * 25))
    result["sentiment_score"] = score

    if score <= -30:
        result["sentiment"] = "negative"
        result["news_summary"] = f"⚠️ 检测到{neg_cnt}条利空新闻，建议回避"
    elif score >= 30:
        result["sentiment"] = "positive"
        result["news_summary"] = f"✅ 检测到{pos_cnt}条利好新闻，短线情绪偏多"
    else:
        result["sentiment"] = "neutral"
        result["news_summary"] = f"中性（利好{pos_cnt}条 / 利空{neg_cnt}条），无重大风险"

    return result


def calc_news_penalty(sentiment: str, sentiment_score: float, limit_up_days: int) -> float:
    """
    根据新闻情绪计算机器惩罚分（可正可负）
    返回加/扣分：-20 ~ +5
    """
    if sentiment == "negative":
        # 利空：扣分，上板越多跌得越惨
        base_penalty = -15
        escalation = -min(limit_up_days - 1, 3) * 1.5  # 3板比1板多扣4.5分
        return round(base_penalty + escalation, 1)
    elif sentiment == "positive":
        return 5.0  # 利好小加分
    else:
        return 0.0
