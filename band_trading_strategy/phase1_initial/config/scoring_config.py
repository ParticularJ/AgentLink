#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
评分配置
V5.0 - 三因子评分模型
"""

from typing import Dict, Tuple

# 三因子评分权重
THREE_FACTOR_WEIGHTS = {
    'industry_momentum': 0.35,    # 产业动量 35% (V5.0从40%下调)
    'individual_elasticity': 0.35, # 个股弹性 35%
    'safety_margin': 0.30,         # 安全边际 30% (V5.0从25%上调)
}

# 产业动量子项评分 (满分35分)
INDUSTRY_MOMENTUM_SCORING = {
    'sector_rating': {
        'max_score': 15,  # V5.0从20分下调
        'S_grade': 15,
        'A_grade': 11,
        'B_grade': 7,
    },
    'industry_position': {
        'max_score': 12,  # V5.0从20分下调
        'core_beneficiary': (10, 12),      # 核心受益 + 景气传导早期
        'important_beneficiary': (7, 9),   # 重要受益 + 景气传导中期
        'general_beneficiary': (4, 6),     # 一般受益 + 景气传导后期
        'marginal_beneficiary': (1, 3),    # 边缘受益
    },
    'catalyst_calendar': {
        'max_score': 8,  # V5.0新增
        'two_or_more_events': 8,   # 未来30天>=2个催化事件
        'one_event': 4,            # 1个催化事件
        'no_event': 0,             # 无事件
    },
}

# 个股弹性子项评分 (满分35分)
INDIVIDUAL_ELASTICITY_SCORING = {
    'market_cap': {
        'max_score': 12,
        'optimal': (10e9, 80e9),      # 100-800亿：12分 (V5.0上限从1000亿下调)
        'large': (80e9, 300e9),        # 800-3000亿：9分
        'mega': (300e9, 800e9),        # 3000-8000亿：5分
        'giant': (800e9, float('inf')), # >8000亿：2分
    },
    'historical_performance': {  # V5.0新增，替代"券商目标价空间"
        'max_score': 12,
        'excellent': {'avg_gain': 0.40, 'win_rate': 0.60, 'score': 12},  # 涨幅>40%且胜率>60%
        'good': {'avg_gain': 0.30, 'win_rate': 0.50, 'score': 8},       # 涨幅30-40%
        'average': {'avg_gain': 0.20, 'win_rate': 0.40, 'score': 5},    # 涨幅20-30%
        'poor': {'avg_gain': 0.20, 'win_rate': 0.00, 'score': 2},       # 涨幅<20%
    },
    'volatility_elasticity': {  # V5.0新增
        'max_score': 11,
        'optimal': (0.35, 0.60),   # 年化波动率35%-60%：11分
        'moderate_high': (0.25, 0.35),  # 25%-35%：7分
        'high': (0.60, 0.80),      # 60%-80%：5分
        'extreme': (0.00, 0.25),   # <25%或>80%：2分
    },
}

# 安全边际子项评分 (满分30分)
SAFETY_MARGIN_SCORING = {
    'earnings_trend': {
        'max_score': 12,  # V5.0从15分下调
        'double_acceleration': 12,   # 近两季度营收+利润双加速
        'single_improvement': 7,     # 单季度改善
        'stable': 4,                  # 平稳
        'decline': 0,                 # 下滑
    },
    'reduction_unlock_risk': {
        'max_score': 9,  # V5.0从10分下调
        'no_risk': 9,        # 未来3个月无大额解禁且无实控人减持
        'single_risk': 4,    # 仅有其一
        'double_risk': 0,    # 两者皆有
    },
    'beta_control': {  # V5.0新增
        'max_score': 9,
        'low_beta': (0, 1.0, 9),       # Beta < 1.0：9分
        'moderate_beta': (1.0, 1.3, 5), # 1.0-1.3：5分
        'high_beta': (1.3, 1.5, 3),     # 1.3-1.5：3分
        'extreme_beta': (1.5, float('inf'), 1),  # >1.5：1分
    },
}

# 及格线
PASSING_SCORE = 70  # 总分 >=70分才能进入档位判定

# 档位判定标准
GRADE_CLASSIFICATION = {
    'first_grade': {
        'name': '第一档',
        'description': '核心受益 + 业绩验证 + 弹性明确 + Beta可控',
        'requirements': [
            {'item': '产业链卡位', 'threshold': 'core_beneficiary'},
            {'item': '第一阶段总分', 'threshold': 80},  # V5.0新增总分要求
            {'item': '近60日涨幅', 'threshold': {'bull': 1.20, 'volatile': 1.00, 'bear': 0.80}},  # 动态化
            {'item': '流通市值', 'threshold': 50e9},  # V5.0从1万亿下调到5000亿
            {'item': '业绩趋势', 'threshold': 'continuous_acceleration'},
            {'item': 'Beta', 'threshold': 1.2},  # V5.0新增
            {'item': '催化日历', 'threshold': 1},  # V5.0新增
        ],
        'min_requirements': 4,  # 需满足至少4项
        'second_stage_score': 35,  # 第二阶段及格线（V4.0修正）
        'position_limit': 0.08,    # 仓位上限8%（V4.0从10%下调）
        'target_ratio': (0.30, 0.40),  # 占初筛池30%-40%
    },
    'second_grade': {
        'name': '第二档',
        'description': '明确受益 + 等待业绩验证 或 弹性一般',
        'requirements': [
            {'item': '产业链卡位', 'threshold': 'core_or_important'},
            {'item': '第一阶段总分', 'threshold': (70, 79)},
            {'item': '近60日涨幅', 'threshold': {'bull': (1.20, 2.00), 'volatile': (1.00, 1.50), 'bear': (0.80, 1.00)}},
            {'item': '流通市值', 'threshold': 80e9},  # V5.0从1.5万亿下调
            {'item': '业绩趋势', 'threshold': 'single_improvement_or_stable'},
            {'item': 'Beta', 'threshold': 1.5},  # V5.0新增
        ],
        'min_requirements': 3,  # 需满足至少3项
        'second_stage_score': 40,  # 第二阶段及格线（V4.0修正）
        'position_limit': 0.05,    # 仓位上限5%（V4.0从8%下调）
        'target_ratio': (0.60, 0.70),  # 占初筛池60%-70%
    },
    'third_grade': {
        'name': '第三档',
        'description': '边缘受益、弹性不足或存在瑕疵',
        'second_stage': '仅作参考，不进入第二阶段',
        'position_limit': 0,
    },
}

# 强制过滤阈值 (V5.0动态化)
FORCED_FILTER_THRESHOLDS = {
    'financial': {
        'operating_cash_flow': {'consecutive_negative_quarters': 2},  # 连续两季为负
        'receivables_to_revenue': {'threshold': 0.50},  # 应收账款/营收 > 50%
        'goodwill_to_assets': {'threshold': 0.30},      # 商誉/总资产 > 30%
        'consecutive_net_loss': {'quarters': 2},        # 连续两季亏损
        'interest_bearing_debt': {'threshold': 0.60, 'require_negative_cash_flow': True},  # V5.0新增
    },
    'price_gain': {
        'bull_market': {'days_60': 2.00, 'days_20': 1.00},      # 牛市阈值
        'volatile_market': {'days_60': 1.50, 'days_20': 0.80},  # 震荡市阈值
        'bear_market': {'days_60': 1.00, 'days_20': 0.50},      # 熊市阈值
    },
    'liquidity': {
        'min_price': 5.0,                    # 股价 < 5元
        'min_market_cap': 3e9,               # 流通市值 < 30亿
        'bull_min_daily_volume': 3e7,        # 牛市日均成交额 < 3000万
        'volatile_min_daily_volume': 5e7,    # 震荡市日均成交额 < 5000万
    },
}

# 持仓周期与景气阶段匹配
HOLDING_PERIOD_MATCHING = {
    'short_band': {  # 4-6周
        'optimal_stages': ['startup_end', 'acceleration'],
        'acceptable_stages': ['climax_early'],
        'avoid_stages': ['decline'],
    },
    'standard_band': {  # 8-12周
        'optimal_stages': ['startup', 'acceleration'],
        'acceptable_stages': ['climax'],
        'avoid_stages': ['decline'],
    },
    'long_band': {  # 12周+
        'optimal_stages': ['startup'],
        'acceptable_stages': ['startup', 'acceleration'],
        'avoid_stages': ['climax', 'decline'],
    },
}
