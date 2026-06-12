#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二阶段评分配置
V4.0 - 财报评分 + 护城河评分
"""

from typing import Dict, Tuple

# 差异化及格线 (V4.0修正)
DIFFERENTIAL_PASSING_SCORE = {
    'first_grade': 35,   # 第一档 >=35分（放松）- 产业逻辑强，基本面可适度放宽
    'second_grade': 40,  # 第二档 >=40分（严格）- 产业逻辑弱，需更严基本面补偿
}

# 仓位上限 (V4.0下调)
POSITION_LIMITS = {
    'first_grade': 0.08,   # 第一档 8% (V4.0从10%下调)
    'second_grade': 0.05,  # 第二档 5% (V4.0从8%下调)
}

# 护城河评分卡 (V4.0新增定量评分，满分20分)
MOAT_SCORING_CARD = {
    'pricing_power': {
        'name': '定价权/差异化壁垒',
        'max_score': 10,  # 6+4
        'gross_margin_premium': {
            'max_score': 6,
            'above_industry_5pct': 6,   # 高于行业均值5个百分点
            'above_industry_3_5pct': 4, # 高3-5个百分点
            'above_industry_0_3pct': 2, # 高0-3个百分点
            'below_industry': 0,        # 低于均值
        },
        'rd_expense_ratio': {
            'max_score': 4,
            'tech_growth': {  # 科技类
                'above_10pct': 4,
                '8_10pct': 3,
                '5_8pct': 2,
                'below_5pct': 0,
            },
            'consumer_value': {  # 消费类 - 改为销售费用率
                'sales_expense_above_15pct': 4,
            },
            'manufacturing': {  # 制造类
                'above_5pct': 4,
            },
        },
    },
    'customer_stickiness': {
        'name': '客户粘性',
        'max_score': 7,  # 4+3
        'top5_customer_concentration': {
            'max_score': 4,
            'below_40pct': 4,
            '40_60pct': 3,
            '60_80pct': 1,
            'above_80pct': 0,
        },
        'renewal_rate': {
            'max_score': 3,
            'above_80pct_or_3years': 3,  # 续约率>80%或平均合作>3年
            'otherwise': 0,
        },
    },
    'profit_quality': {
        'name': '利润含金量',
        'max_score': 3,
        'net_profit_cash_content': {
            'above_100pct': 3,
            '80_100pct': 2,
            '60_80pct': 1,
            'below_60pct': 0,
        },
    },
}

# 护城河等级判定
MOAT_GRADE_THRESHOLDS = {
    'strong': {'min_score': 14, 'position_adjustment': 1.0},      # >=14分 仓位100%
    'medium': {'min_score': 9, 'position_adjustment': 0.6},       # 9-13分 仓位60%
    'weak': {'min_score': 0, 'position_adjustment': 0.4},         # <9分 仓位40%或剔除
}

# 一票否决配置 (第二阶段6项动态项)
VETO_ITEMS = {
    'management_violation': {
        'name': '管理层违规记录',
        'source': '巨潮资讯网',
        'threshold': {'years': 2, 'existence': True},  # 近2年内存在即否决
    },
    'audit_opinion': {
        'name': '审计意见非标',
        'source': '财报审计意见章节',
        'veto_types': ['保留意见', '无法表示意见', '否定意见'],
    },
    'north_bound_outflow': {
        'name': '北向资金持续流出',
        'source': '东方财富数据中心',
        'threshold': {'consecutive_days': 5, 'cumulative_outflow': 3e7},  # V4.0从5000万下调到3000万
    },
    'major_shareholder_pledge': {
        'name': '大股东高比例质押',
        'source': '同花顺F10',
        'threshold': 0.50,  # >50%
    },
    'upcoming_unlock': {
        'name': '近期大额解禁',
        'source': '同花顺F10',
        'threshold': {'days': 30, 'market_cap_ratio': 0.08},  # V4.0从10%下调到8%
    },
    'pre_earnings_gain': {
        'name': '财报前涨幅过大',
        'source': '前复权K线',
        'threshold': {
            'bull': 0.20,      # 牛市>20%
            'volatile': 0.12,  # 震荡>12%
            'bear': 0.08,      # 熊市>8%
        },
    },
}

# 财报核心指标评分 (V4.0重构，满分60分)
FINANCIAL_SCORING = {
    'absolute_performance': {
        'revenue_growth': {
            'max_score': 8,
            'above_30pct': 8,
            '15_30pct': 5,
            'below_15pct': 2,
        },
        'profit_growth': {
            'max_score': 8,
            'above_40pct': 8,
            '20_40pct': 5,
            'below_20pct': 2,
        },
    },
    'earnings_trend': {
        'max_score': 8,
        'acceleration_positive': 8,           # 加速且绝对值>0%
        'deceleration_below_10pct': 4,        # 减速但幅度<10个百分点
        'deceleration_above_10pct_or_negative': 0,  # 减速>=10个百分点或负增长
    },
    'profit_quality': {
        'cash_content': {
            'max_score': 8,
            'above_100pct': 8,
            '80_100pct': 5,
            'below_80pct': 2,
        },
    },
    'profitability': {
        'roe': {
            'max_score': 8,
            'above_20pct': 8,
            '15_20pct': 5,
            'below_15pct': 2,
        },
    },
    'earnings_surprise': {  # V4.0新增，满分10分
        'max_score': 10,
        'above_30pct': 10,      # 超预期>=30%
        '15_30pct': 8,          # 15%-30%
        '5_15pct': 6,           # 5%-15%
        'negative_5_to_5pct': 3,  # -5%~+5% 符合预期
        'below_negative_5pct': 0,  # <-5% 不及预期
    },
    'institution_attitude': {  # V4.0新增，满分10分
        'max_score': 10,
        'upgrade_2plus': 10,    # 近1月>=2家上调
        'maintain': 5,          # 维持
        'downgrade': 0,         # 下调
        'no_coverage': 3,       # 无覆盖
    },
}

# 行业适配调整规则
INDUSTRY_ADAPTATION = {
    'tech_growth': {
        'revenue_growth_threshold': 0.25,  # >25%满分
        'profit_growth_threshold': 0.35,   # >35%满分
        'roe_threshold': 0.15,             # >15%满分
        'surprise_weight': 1.0,            # 标准权重
    },
    'consumer_value': {
        'revenue_growth_threshold': 0.20,
        'profit_growth_threshold': 0.25,
        'roe_threshold': 0.25,             # 消费类ROE要求更高
        'surprise_weight': 0.8,            # 权重x0.8
    },
    'cyclical_resource': {
        'revenue_growth_threshold': 0.50,  # 周期类增速阈值更高
        'profit_growth_threshold': 0.60,
        'roe_threshold': 0.12,
        'surprise_weight': 1.2,            # 权重x1.2（更关键）
    },
    'manufacturing': {
        'revenue_growth_threshold': 0.20,
        'profit_growth_threshold': 0.25,
        'roe_threshold': 0.15,
        'surprise_weight': 1.0,
    },
}

# 业绩趋势评分细则
EARNINGS_TREND_SCORING = {
    'above_20pct': {
        'acceleration': 8,
        'deceleration_below_10pct': 4,
        'deceleration_above_10pct': 1,
    },
    '0_20pct': {
        'any': 2,
    },
    'below_0pct': {
        'any': 0,
    },
}
