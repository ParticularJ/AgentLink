#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
止损参数配置模块
定义各板块的清仓止损比例和减半止损比例
"""

from typing import Dict, Tuple

# ATR 乘数 N（推荐值 2.0，保守型可提至 2.5）
ATR_MULTIPLIER = 2.0

# 近期平均振幅天数
AMPLITUDE_DAYS = 10

# 板块止损参数表
# 格式: {板块名称: (清仓止损比例, 减半止损比例)}
SECTOR_STOP_LOSS_CONFIG: Dict[str, Tuple[float, float]] = {
    # 高波动板块
    '科创板': (0.13, 0.08),
    '创业板': (0.13, 0.08),
    '北交所': (0.15, 0.10),
    'ST板块': (0.10, 0.06),
    
    # 中波动板块
    '科技成长': (0.12, 0.07),
    '新能源': (0.12, 0.07),
    '半导体': (0.12, 0.07),
    '医药生物': (0.11, 0.065),
    '消费电子': (0.11, 0.065),
    
    # 低波动板块
    '银行': (0.08, 0.05),
    '保险': (0.08, 0.05),
    '公用事业': (0.09, 0.055),
    '食品饮料': (0.10, 0.06),
    '家用电器': (0.10, 0.06),
    '交通运输': (0.09, 0.055),
    
    # 默认
    'default': (0.10, 0.06),
}

# 快速判断法 - 基于近期平均振幅
# 格式: (振幅阈值下限, 振幅阈值上限): (清仓止损比例, 减半止损比例)
QUICK_JUDGMENT_CONFIG: Dict[Tuple[float, float], Tuple[float, float]] = {
    (0.00, 0.02): (0.08, 0.05),   # 低波动: 振幅<2%
    (0.02, 0.04): (0.10, 0.06),   # 中波动: 振幅2-4%
    (0.04, 0.06): (0.12, 0.07),   # 高波动: 振幅4-6%
    (0.06, 1.00): (0.15, 0.10),   # 极高波动: 振幅>6%
}

# 利润保护模式 - 回撤阈值表
# 格式: (最高浮盈下限, 最高浮盈上限): 允许最大回撤比例
PROFIT_DRAWBACK_CONFIG: Dict[Tuple[float, float], float] = {
    (0.10, 0.15): 0.45,   # 10%-15%浮盈: 允许回撤45%
    (0.15, 0.25): 0.55,   # 15%-25%浮盈: 允许回撤55%
    (0.25, 0.40): 0.70,   # 25%-40%浮盈: 允许回撤70%
    (0.40, 10.0): 0.80,   # >40%浮盈: 允许回撤80%
}

# 大盘状态配置
MARKET_STATUS_CONFIG = {
    'normal': {'name': '正常', 'description': '收盘价在5日均线上方'},
    'weak': {'name': '偏弱', 'description': '收盘价在5日线下方，未达恐慌区'},
    'panic': {'name': '恐慌区', 'description': '5日线下且连续3天至少2天跌幅≥1.5%'},
    'extreme_panic': {'name': '极端恐慌', 'description': '恐慌区且当日跌幅≥2%'},
}

# 个人专属参数
PERSONAL_CONFIG = {
    'total_capital': 1000000,        # 总资金 100万
    'min_position': 50000,           # 单笔最小仓位 5万(5%)
    'max_position': 150000,          # 单笔最大仓位 15万(15%)
    'atr_multiplier': 2.0,           # ATR乘数 N
    'max_monthly_correction': 2,     # 每月纠错买入最多2次
    'correction_position_limit': 0.03,  # 纠错仓位上限 3%
    'panic_min_position': 0.30,      # 恐慌区最低保留仓位 3成
}

# 时间止损参数
TIME_STOP_CONFIG = {
    'min_hold_days': 10,             # 最少持仓天数
    'min_profit_for_time_stop': 0.05, # 浮盈低于5%才考虑时间止损
    'loss_ratio_for_time_stop': 0.8,  # 亏损≥原止损×0.8
}

# 假跌破例外参数
FALSE_BREAKOUT_CONFIG = {
    'check_time': '14:50',           # 复查时间
    'recovery_condition': '收回均线之上且当日收阳线',
    'max_daily_usage': 1,            # 每只个股每日仅限一次
}

# 纠错买入参数
CORRECTION_BUY_CONFIG = {
    'buy_ratio': 1/3,                # 买入原仓位的1/3
    'stop_loss_1': 0.05,             # 较买入价下跌5%清仓
    'stop_loss_2': '跌破20日线',      # 跌破20日线清仓
    'time_limit': 3,                 # 3日内未收复清仓前价位减半
    'max_monthly': 2,                # 每月最多2次
    'max_capital_ratio': 0.03,       # 最多占总资金3%
}


def get_sector_stop_loss(sector: str) -> Tuple[float, float]:
    """
    获取板块止损参数
    返回: (清仓止损比例, 减半止损比例)
    """
    return SECTOR_STOP_LOSS_CONFIG.get(sector, SECTOR_STOP_LOSS_CONFIG['default'])


def get_quick_judgment_stop_loss(amplitude: float) -> Tuple[float, float]:
    """
    根据近期平均振幅快速判断止损参数
    返回: (清仓止损比例, 减半止损比例)
    """
    for (low, high), (clear_ratio, half_ratio) in QUICK_JUDGMENT_CONFIG.items():
        if low <= amplitude < high:
            return (clear_ratio, half_ratio)
    return QUICK_JUDGMENT_CONFIG[(0.04, 1.00)]  # 默认高波动


def get_profit_drawback_threshold(max_profit: float, market_panic: bool = False) -> float:
    """
    获取利润保护模式的回撤阈值
    
    Args:
        max_profit: 最高浮盈比例（如 0.25 表示 25%）
        market_panic: 是否处于恐慌区
    
    Returns:
        允许的最大回撤比例
    """
    threshold = 0.45  # 默认最低阈值
    
    for (low, high), drawback in PROFIT_DRAWBACK_CONFIG.items():
        if low <= max_profit < high:
            threshold = drawback
            break
    
    # 恐慌区阈值放宽10个百分点
    if market_panic:
        threshold = min(0.90, threshold + 0.10)
    
    return threshold


def calculate_atr_stop_loss(atr: float, multiplier: float = None) -> float:
    """
    基于ATR计算止损比例
    
    Args:
        atr: ATR值（如 0.05 表示 5%）
        multiplier: ATR乘数，默认使用配置值
    
    Returns:
        止损比例
    """
    if multiplier is None:
        multiplier = PERSONAL_CONFIG['atr_multiplier']
    return atr * multiplier
