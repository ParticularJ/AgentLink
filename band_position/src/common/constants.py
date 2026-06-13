"""
波段交易系统 - 常量配置
"""

# ========== 大盘环境评分阈值 ==========
MARKET_ENVIRONMENT_THRESHOLDS = {
    "green": 60,    # 绿灯 >= 60分
    "yellow": 40,   # 黄灯 40-59分
}

# 市场状态判定标准
MARKET_STATUS_RPS_THRESHOLDS = {
    "bull": {"rps50": 70, "rps120": 60},
    "bear": {"rps50": 40, "rps120": 40},
}

# 市场流动性阈值（亿元）
MARKET_LIQUIDITY_THRESHOLDS = {
    "high": 15000,      # > 1.5万亿
    "medium": 8000,     # 8000亿-1.5万亿
}

# ========== 赛道评分阈值 ==========
TRACK_SCORE_THRESHOLDS = {
    "s_level": 85,      # S级 >= 85分
    "a_level": 70,      # A级 70-84分
    "b_level": 60,      # B级 60-69分
    "pass": 70,         # 进入第三层 >= 70分
}

# 赛道数量控制
TRACK_COUNT_LIMITS = {
    "s_max": 4,         # S级最多4个
    "a_max": 6,         # A级最多6个
    "b_max": 3,         # B级最多3个
    "total_max": 12,    # 总计最多12个
    "total_min": 8,     # 总计最少8个
}

# ========== 强制过滤阈值 ==========
# 涨幅过滤阈值（按市场状态）
RISE_FILTER_THRESHOLDS = {
    "60d": {
        "牛市": 200,
        "震荡市": 150,
        "熊市": 100,
    },
    "20d": {
        "牛市": 100,
        "震荡市": 80,
        "熊市": 50,
    },
}

# 流动性过滤阈值
LIQUIDITY_FILTER_THRESHOLDS = {
    "min_price": 5.0,           # 股价 < 5元剔除
    "min_float_market_cap": 30,  # 流通市值 < 30亿剔除
    "min_daily_volume_bear": 5000,  # 熊市日均成交额 < 5000万剔除
    "min_daily_volume_bull": 3000,  # 牛市日均成交额 < 3000万剔除
}

# 财务雷区阈值
FINANCIAL_FILTER_THRESHOLDS = {
    "max_receivables_revenue_ratio": 0.5,  # 应收账款/营收 > 50%
    "max_goodwill_total_assets_ratio": 0.3,  # 商誉/总资产 > 30%
    "max_interest_bearing_debt_ratio": 0.6,  # 有息负债率 > 60%
}

# ========== 三因子评分阈值 ==========
# 产业动量
INDUSTRY_MOMENTUM_WEIGHTS = {
    "track_rating": 15,
    "chain_position": 12,
    "catalyst": 8,
}

# 个股弹性
FLEXIBILITY_WEIGHTS = {
    "market_cap": 12,
    "historical_performance": 12,
    "volatility": 11,
}

# 安全边际
SAFETY_MARGIN_WEIGHTS = {
    "earnings_trend": 12,
    "reduction_risk": 9,
    "beta_control": 9,
}

# 总分及格线
PHASE1_PASS_SCORE = 70

# 档位判定标准
GRADE_THRESHOLDS = {
    "first": {
        "min_score": 80,
        "max_rise_60d_bull": 120,
        "max_rise_60d_oscillation": 100,
        "max_rise_60d_bear": 80,
        "max_float_market_cap": 5000,
        "max_beta": 1.2,
        "min_catalyst": 1,
    },
    "second": {
        "min_score": 70,
        "max_score": 79,
        "max_rise_60d_bull": 200,
        "max_rise_60d_oscillation": 150,
        "max_rise_60d_bear": 100,
        "max_float_market_cap": 8000,
        "max_beta": 1.5,
    },
}

# 第一档占比目标
FIRST_GRADE_RATIO = {
    "min": 0.3,
    "max": 0.4,
}

# ========== 第二阶段常量 ==========
# 差异化及格线
PHASE2_PASS_SCORES = {
    "一档": 35,    # 第一档 >= 35分
    "二档": 40,   # 第二档 >= 40分
}

# 仓位上限
MAX_POSITION = {
    "一档": 8,     # 第一档最大8%
    "二档": 5,    # 第二档最大5%
}

# 行业最大仓位
MAX_INDUSTRY_POSITION = 20  # 同行业内个股总仓位不超过20%

# 护城河评分阈值
MOAT_THRESHOLDS = {
    "strong": 14,       # >= 14分 强
    "medium": 9,        # >= 9分 中
}

# 一票否决阈值
VETO_THRESHOLDS = {
    "northbound_outflow_days": 5,       # 连续5日净卖出
    "northbound_outflow_amount": 3000,  # 累计 > 3000万
    "major_shareholder_pledge_ratio": 0.5,  # 大股东质押 > 50%
    "unlock_market_cap_ratio": 0.08,    # 解禁市值 > 流通市值8%
    "pre_report_rise_bull": 20,         # 牛市财报前20日涨幅 > 20%
    "pre_report_rise_oscillation": 12,  # 震荡市 > 12%
    "pre_report_rise_bear": 8,          # 熊市 > 8%
}

# 财报评分满分
FINANCIAL_SCORE_MAX = 60

# 估值判断标准
VALUATION_PEG_THRESHOLDS = {
    "severely_undervalued": 0.6,
    "undervalued": 0.9,
    "fairly_low": 1.2,
    "fair": 1.5,
    "overvalued": 2.0,
}

VALUATION_PB_ROE_THRESHOLDS = {
    "severely_undervalued": -0.4,
    "undervalued": -0.2,
    "fairly_low": 0.0,
    "fair": 0.2,
    "overvalued": 0.4,
}

VALUATION_PS_THRESHOLDS = {
    "severely_undervalued": 0.5,
    "undervalued": 0.8,
    "fairly_low": 1.2,
    "fair": 2.0,
}

# 历史分位点阈值
HISTORICAL_PERCENTILE_THRESHOLDS = {
    "extremely_low": 10,
    "low": 30,
    "medium": 50,
    "high": 70,
    "extremely_high": 90,
}

# 止损位设定
STOP_LOSS_THRESHOLDS = {
    "beta_lt_1": -7,
    "beta_1_to_1_3": -6,
    "beta_1_3_to_1_5": -5,
    "beta_gt_1_5": -4,
}

TIME_STOP_THRESHOLDS = {
    "beta_lt_1": 12,
    "beta_1_to_1_3": 10,
    "beta_1_3_to_1_5": 8,
    "beta_gt_1_5": 6,
}

# 行业系数（PB-ROE法）
INDUSTRY_PB_ROE_COEFFICIENTS = {
    "科技成长型": 0.9,
    "消费价值型": 1.1,
    "周期资源型": 0.6,
    "制造工业型": 0.7,
}

# PS估值系数
PS_COEFFICIENTS = {
    "科技成长型": 0.3,
    "消费价值型": 0.5,
}
