#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻情绪分析模块
使用 Tavily API 获取相关新闻并进行情绪打分
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False


# 负面关键词（利空）
NEGATIVE_KEYWORDS = [
    '减持', '解禁', '业绩预亏', '业绩下滑', '暴雷', 'ST', '退市',
    '诉讼', '处罚', '监管', '问询函', '立案调查', '产品召回',
    '安全事故', '债务违约', '商誉减值', '应收账款坏账',
    '高管离职', '核心技术人员离职', '大客户流失',
]

# 正面关键词（利好）
POSITIVE_KEYWORDS = [
    '业绩预增', '业绩增长', '扭亏为盈', '净利润增长', '订单大增',
    '新产品发布', '战略合作', '中标', '获批', '创新药获批',
    '产能扩张', '市占率提升', '技术突破', '独家授权',
]

# 利好出尽关键词（需结合股价判断）
BULLISH_EXHAUST_KEYWORDS = [
    '利好兑现', '利好出尽', '不及预期', '业绩增速放缓',
]


def get_tavily_client() -> 'TavilyClient':
    """获取 Tavily 客户端"""
    api_key = os.environ.get('TAVILY_API_KEY')
    if not api_key:
        # 尝试从配置文件读取
        config_path = os.path.expanduser('~/.openclaw/config.json')
        if os.path.exists(config_path):
            import json
            with open(config_path) as f:
                config = json.load(f)
                api_key = config.get('tavily_api_key')
    if not api_key:
        raise RuntimeError('TAVILY_API_KEY 未设置，请配置 Tavily API Key')
    return TavilyClient(api_key=api_key)


def fetch_news_sentiment(stock_code: str, stock_name: str) -> Tuple[str, List[Dict]]:
    """
    获取股票相关新闻并分析情绪
    返回: (sentiment, articles)
    sentiment: 'positive' / 'neutral' / 'negative' / '利好出尽' / 'unknown'
    """
    if not TAVILY_AVAILABLE:
        return sentiment_fallback(stock_code, stock_name)

    try:
        client = get_tavily_client()

        # 搜索最近2小时内新闻
        time_range = 'd'  # day
        query = f"{stock_name} {stock_code} 最新公告 新闻"
        results = client.search(
            query=query,
            search_depth='basic',
            max_results=8,
            time_range=time_range,
        )

        articles = results.get('results', [])
        if not articles:
            return 'unknown', []

        return analyze_sentiment(articles)

    except Exception as e:
        print(f"[WARN] Tavily新闻获取失败 ({stock_code}): {e}")
        return 'unknown', []


def analyze_sentiment(articles: List[Dict]) -> Tuple[str, List[Dict]]:
    """
    分析新闻情绪
    """
    if not articles:
        return 'unknown', []

    scores = []
    reasons = []

    for article in articles:
        title = article.get('title', '')
        content = article.get('content', '')
        text = (title + ' ' + content).lower()

        # 计分
        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        exhaust_count = sum(1 for kw in BULLISH_EXHAUST_KEYWORDS if kw in text)

        if neg_count > pos_count:
            scores.append(-neg_count)
            reasons.append(f"负面: {title[:30]}")
        elif exhaust_count > 0:
            scores.append(-1)  # 利好出尽按轻微负面处理
            reasons.append(f"利好出尽: {title[:30]}")
        elif pos_count > 0:
            scores.append(pos_count)
            reasons.append(f"正面: {title[:30]}")
        else:
            scores.append(0)

    avg_score = sum(scores) / len(scores) if scores else 0

    if avg_score < -0.5:
        sentiment = 'negative'
    elif avg_score > 0.5:
        sentiment = 'positive'
    else:
        sentiment = 'neutral'

    enriched = []
    for i, article in enumerate(articles):
        article['sentiment_score'] = scores[i] if i < len(scores) else 0
        enriched.append(article)

    return sentiment, enriched


def sentiment_fallback(stock_code: str, stock_name: str) -> Tuple[str, List]:
    """
    当 Tavily 不可用时的降级方案
    通过网络爬取东方财富等平台的新闻
    """
    try:
        import akshare as ak
        news = ak.stock_news_em(symbol=stock_code)
        if news is None or news.empty:
            return 'unknown', []

        articles = []
        for _, row in news.head(5).iterrows():
            articles.append({
                'title': str(row.get('新闻标题', '')),
                'url': str(row.get('新闻链接', '')),
                'content': '',
            })

        return analyze_sentiment(articles)

    except Exception as e:
        return 'unknown', []
