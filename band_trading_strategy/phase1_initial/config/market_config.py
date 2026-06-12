#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大盘环境配置
V5.0 - 三级评估体系
"""

from typing import Dict, Tuple

# 大盘环境三级评估权重
MARKET_ENVIRONMENT_WEIGHTS = {
    'index_trend': 0.40,      # 指数趋势 40%
    'market_liquidity': 0.30,  # 市场流动性 30%
    'market_sentiment': 0.20,  # 市场情绪 20%
    'north_bound': 0.10,       # 北向资金 10%
}

# 指数趋势评分标准
INDEX_TREND_SCORING = {
    'bullish_arrangement': (30, 40),    # 多头排列(20>60>120)且指数在两线之上
    'volatile': (15, 29),                # 震荡(20与60纠缠)
    'bearish_arrangement': (0, 14),      # 空头排列
}

# 市场流动性评分标准
LIQUIDITY_SCORING = {
    'high': (1.5e12, float('inf'), 25, 30),      # >1.5万亿
    'medium': (8e11, 1.5e12, 15, 24),             # 8000亿-1.5万亿
    'low': (0, 8e11, 0, 14),                       # <8000亿
}

# 市场情绪评分标准
SENTIMENT_SCORING = {
    'strong': (3.0, 80, 15, 20),      # 涨跌比>3:1且涨停>80家
    'moderate': (1.0, None, 8, 14),   # 涨跌比1:1-3:1
    'weak': (0, 1.0, 0, 7),            # 涨跌比<1:1
}

# 北向资金评分标准
NORTH_BOUND_SCORING = {
    'inflow_strong': (2e9, float('inf'), 8, 10),   # 近20日净流入>200亿
    'inflow_weak': (0, 2e9, 4, 7),                  # 净流入0-200亿
    'outflow': (float('-inf'), 0, 0, 3),            # 净流出
}

# 大盘环境等级阈值
MARKET_ENVIRONMENT_LEVELS = {
    'green': 60,    # 绿灯 >=60分
    'yellow': 40,   # 黄灯 40-59分
    'red': 0,       # 红灯 <40分
}

# 大盘环境对初筛流程的影响
MARKET_ENVIRONMENT_IMPACT = {
    'green': {
        'description': '正常执行全部流程',
        'sector_filter': 'all',           # 筛选全部赛道
        'gain_threshold_60d': 1.5,        # 60日涨幅阈值 150%
        'gain_threshold_20d': 0.8,        # 20日涨幅阈值 80%
        'position_limit': 1.0,            # 仓位系数上限 100%
        'min_position_ratio': 0.0,        # 最低保留仓位
    },
    'yellow': {
        'description': '降级处理',
        'sector_filter': 'S_only',        # 仅筛选S级赛道
        'gain_threshold_60d': 1.0,        # 60日涨幅阈值收紧到100%
        'gain_threshold_20d': 0.5,        # 20日涨幅阈值收紧到50%
        'position_limit': 0.5,            # 仓位系数上限降至50%
        'min_position_ratio': 0.3,        # 最低保留仓位30%
    },
    'red': {
        'description': '暂停初筛',
        'sector_filter': 'none',          # 不筛选任何赛道
        'gain_threshold_60d': 0.5,        # 不适用
        'gain_threshold_20d': 0.3,        # 不适用
        'position_limit': 0.0,            # 仓位系数上限0%
        'min_position_ratio': 0.3,        # 最低保留仓位30%
    },
}

# 沪深300 RPS阈值
HS300_RPS_THRESHOLDS = {
    'rps50_weak': 40,      # RPS50 < 40 视为弱势
    'rps120_weak': 40,     # RPS120 < 40 视为弱势
}

# 全市场成交额阈值
TOTAL_VOLUME_THRESHOLDS = {
    'liquidity_dry': 7e11,  # <7000亿视为流动性枯竭
}

# 均线空头排列判定
MA_BEARISH_THRESHOLDS = {
    'ma20_below_ma60': True,  # 20日<60日
    'index_below_both': True, # 指数位于两线之下
}
