#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
估值配置
V4.0 - PEG/PB-ROE/PS三轨体系 + 历史分位点
"""

from typing import Dict, Tuple

# 估值轨道选择
VALUATION_TRACKS = {
    'peg': {
        'name': 'PEG估值法',
        'applicable_industries': ['tech_growth', 'consumer_value'],
        'formula': 'PEG = PE(TTM) / 净利润增速(TTM)',
    },
    'pb_roe': {
        'name': 'PB-ROE估值法',
        'applicable_industries': ['cyclical_resource', 'manufacturing'],
        'formula': '合理PB = ROE x 100 x 行业系数',
    },
    'ps': {
        'name': 'PS估值法',
        'applicable_industries': ['loss_making_tech', 'innovation_drug'],
        'formula': '合理PS = 营收增速 x 系数',
    },
}

# PEG判断标准
PEG_THRESHOLDS = {
    'severely_undervalued': {'max': 0.6, 'position_coefficient': 1.0, 'action': '可建仓'},
    'undervalued': {'min': 0.6, 'max': 0.9, 'position_coefficient': 0.9, 'action': '积极建仓'},
    'reasonable_low': {'min': 0.9, 'max': 1.2, 'position_coefficient': 0.8, 'action': '分批建仓'},
    'reasonable': {'min': 1.2, 'max': 1.5, 'position_coefficient': 0.6, 'action': '小仓位试探'},
    'expensive': {'min': 1.5, 'max': 2.0, 'position_coefficient': 0.2, 'action': '观察不买'},
    'overvalued': {'min': 2.0, 'position_coefficient': 0.0, 'action': '放弃'},
}

# PEG负增长处理方案 (V4.0新增)
PEG_NEGATIVE_HANDLING = {
    'negative_growth': {  # 净利润增速为负
        'action': 'PEG失效，切换至PB-ROE或PS',
        'alternative_track': ['pb_roe', 'ps'],
    },
    'negative_profit': {  # 净利润为负（亏损）
        'action': 'PEG完全失效，强制切换至PS',
        'alternative_track': ['ps'],
    },
    'low_growth': {  # 增速0-10%
        'action': 'PEG可能失真，交叉验证',
        'alternative_track': ['pb_roe'],  # 同时计算，取更保守结论
    },
}

# PB-ROE行业系数
PB_ROE_INDUSTRY_COEFFICIENTS = {
    'tech_growth': (0.8, 1.0),
    'consumer_value': (1.0, 1.2),
    'cyclical_resource': (0.5, 0.7),
    'manufacturing': (0.6, 0.8),
}

# PB-ROE判断标准
PB_ROE_THRESHOLDS = {
    'severely_undervalued': {'max_premium': -0.40, 'position_coefficient': 1.0},
    'undervalued': {'min_premium': -0.40, 'max_premium': -0.20, 'position_coefficient': 0.9},
    'reasonable_low': {'min_premium': -0.20, 'max_premium': 0.00, 'position_coefficient': 0.8},
    'reasonable': {'min_premium': 0.00, 'max_premium': 0.20, 'position_coefficient': 0.6},
    'expensive': {'min_premium': 0.20, 'max_premium': 0.40, 'position_coefficient': 0.2},
    'overvalued': {'min_premium': 0.40, 'position_coefficient': 0.0},
}

# PS估值系数
PS_COEFFICIENTS = {
    'tech': 0.3,      # 科技类
    'consumer': 0.5,  # 消费类
}

# PS判断标准
PS_THRESHOLDS = {
    'severely_undervalued': {'max_ratio': 0.5, 'position_coefficient': 1.0},
    'undervalued': {'min_ratio': 0.5, 'max_ratio': 0.8, 'position_coefficient': 0.8},
    'reasonable': {'min_ratio': 0.8, 'max_ratio': 1.2, 'position_coefficient': 0.6},
    'expensive': {'min_ratio': 1.2, 'max_ratio': 2.0, 'position_coefficient': 0.2},
    'overvalued': {'min_ratio': 2.0, 'position_coefficient': 0.0},
}

# 历史估值分位点体系 (V4.0核心新增)
HISTORICAL_PERCENTILE = {
    'calculation': {
        'period': '3年',  # 或上市以来
        'formula': '分位点 = (历史估值中低于当前估值的天数 / 总交易日数) x 100%',
    },
    'thresholds': {
        'extremely_low': {'max': 10, 'meaning': '历史极低', 'adjustment': 0.10},      # 系数+10%
        'low': {'min': 10, 'max': 30, 'meaning': '历史较低', 'adjustment': 0.00},      # 不变
        'medium': {'min': 30, 'max': 50, 'meaning': '历史中位', 'adjustment': 0.00},   # 不变
        'high': {'min': 50, 'max': 70, 'meaning': '历史较高', 'adjustment': -0.10},    # 系数-10%
        'very_high': {'min': 70, 'max': 90, 'meaning': '历史很高', 'adjustment': -0.20}, # 系数-20%
        'extremely_high': {'min': 90, 'meaning': '历史极高', 'adjustment': -0.20, 'limit': 0.20},  # 系数-20%，即使PEG合理也限仓20%
    },
    'application_rules': {
        'consistent_with_valuation': '强化估值结论',
        'contradictory_to_valuation': '以分位点为准，下调仓位系数',
        'new_stock_less_than_1year': '分位点数据不可靠，以PEG/PB-ROE为主',
    },
}

# 机构持仓变化跟踪 (V4.0新增)
INSTITUTION_HOLDING_TRACKING = {
    'data_sources': ['基金季报', '沪深港通持股'],
    'update_frequency': {'fund_report': '季度', 'stock_connect': '每日'},
    'thresholds': {
        'strong_bullish': {'change': 0.30, 'tolerance_adjustment': 0.10},      # 持仓增加>30%
        'bullish': {'min_change': 0.10, 'max_change': 0.30, 'tolerance_adjustment': 0.05},  # 增加10-30%
        'neutral': {'min_change': -0.10, 'max_change': 0.10, 'tolerance_adjustment': 0.00},  # -10%~+10%
        'bearish': {'min_change': -0.30, 'max_change': -0.10, 'tolerance_adjustment': -0.10},  # 减少10-30%
        'strong_bearish': {'change': -0.30, 'tolerance_adjustment': -0.20},     # 减少>30%
    },
}

# 仓位计算公式 (V4.0简化)
POSITION_CALCULATION = {
    'formula': '最终仓位 = 建议基准仓位 x 估值仓位系数 x 护城河调整系数',
    'components': {
        'base_position': {'first_grade': 0.08, 'second_grade': 0.05},  # 建议基准仓位
        'valuation_coefficient': '来自估值判断 (0%-100%)',
        'moat_coefficient': {'strong': 1.0, 'medium': 0.6, 'weak': 0.4},  # 护城河调整系数
    },
    'constraints': {
        'max_single_stock': 0.08,       # 单个股票最大仓位8%
        'max_industry_total': 0.20,     # 同行业内个股总仓位不超过20%
        'round_to': 0.01,               # 向下取整至最接近的1%整数倍
    },
}

# 止损位设定 (V4.0新增)
STOP_LOSS_CONFIG = {
    'methods': {
        'technical': {
            'name': '技术止损',
            'applicable': '所有标的',
            'formula': '买入价下方 6%-8%',
        },
        'volatility': {
            'name': '波动率止损',
            'applicable': '高波动标的（波动率>50%）',
            'formula': '买入价下方 1.5 x ATR(14)',
        },
        'support': {
            'name': '支撑位止损',
            'applicable': '有明确技术支撑位的标的',
            'formula': '最近重要支撑位下方 3%',
        },
        'time': {
            'name': '时间止损',
            'applicable': '所有标的',
            'formula': '买入后8周（标准波段）或12周（长波段）无盈利',
        },
    },
    'recommended': '技术止损(-7%) + 时间止损(12周) 结合',
    'beta_adjustment': {
        'below_1.0': {'stop_loss': -0.07, 'time_stop': 12},   # Beta<1.0: -7%, 12周
        '1.0_1.3': {'stop_loss': -0.06, 'time_stop': 10},     # 1.0-1.3: -6%, 10周
        '1.3_1.5': {'stop_loss': -0.05, 'time_stop': 8},      # 1.3-1.5: -5%, 8周
        'above_1.5': {'stop_loss': -0.04, 'time_stop': None}, # >1.5: -4%或回避
    },
}
