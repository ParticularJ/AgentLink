#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置文件 - Medium-termHoldingStrategy
提供所有策略配置
"""

# ── 仓位配置 ────────────────────────────────────────────
POSITION_CONFIG = {
    "强势主升": {
        "base_position": 0.80,
        "max_position": 0.95,
        "trend_coef": 1.0
    },
    "震荡偏多": {
        "base_position": 0.60,
        "max_position": 0.80,
        "trend_coef": 0.8
    },
    "弱势震荡": {
        "base_position": 0.40,
        "max_position": 0.50,
        "trend_coef": 0.5
    },
    "下跌趋势": {
        "base_position": 0.05,
        "max_position": 0.30,
        "trend_coef": 0.3
    },
    "系统性风险": {
        "base_position": 0.0,
        "max_position": 0.10,
        "trend_coef": 0.1
    }
}

# ── 数据源配置 ─────────────────────────────────────────
DATA_CONFIG = {
    "default_days": 250,
    "min_history_days": 60
}

# ── 评分权重配置 ────────────────────────────────────────
SCORE_WEIGHTS = {
    "technical": 0.25,       # 技术评分
    "money_flow": 0.25,       # 资金流评分
    "sector": 0.20,           # 板块评分
    "fundamental": 0.05,      # 基本面评分
    "volume": 0.15,            # 成交量评分
    "sentiment": 0.10         # 市场情绪评分
}

# 买入阈值
BUY_THRESHOLD = 65.0

# ── 均线配置 ───────────────────────────────────────────
MA_CONFIG = {
    "score": {
        "days": 1,
        "message": "score综合评分过低",
        "action": "减仓50%"  # 第一防线，立刻减一半
    },
    "ma5": {
        "days": 5,
        "message": "5日均线跌破",
        "action": "减仓50%"  # 第一防线，立刻减一半
    },
    "ma10": {
        "days": 10,
        "message": "10日均线跌破",
        "action": "清仓"     # 第二防线，直接跑
    }
}

# ── 再平衡阈值 ─────────────────────────────────────────
REBALANCE_THRESHOLD = 0.15  # 仓位偏离15%时触发再平衡

# ── 飞书 Webhook 配置 ──────────────────────────────────
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-url"

WEBHOOK_CONFIG = {
    "feishu_webhook": FEISHU_WEBHOOK,
    "default_bot_name": "StockBot"
}