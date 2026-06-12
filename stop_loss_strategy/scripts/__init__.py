#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本模块
"""

from .market_status import (
    MarketStatus,
    MarketStatusChecker,
    get_market_status_for_trading,
)

from .atr_calculator import (
    calculate_tr,
    calculate_atr,
    calculate_atr_ratio,
    calculate_recent_amplitude,
    get_stop_loss_by_atr,
    calculate_ma,
    calculate_volume_ma,
    is_above_ma,
    is_below_ma,
    days_below_ma,
    calculate_max_profit,
    calculate_current_profit,
    calculate_drawback,
)

from .profit_protect import ProfitProtectMode
from .principal_protect import PrincipalProtectMode
from .time_stop import TimeStopLoss
from .panic_checker import PanicZoneChecker
from .decision_engine import StopLossDecisionEngine, DecisionResult

__all__ = [
    # 大盘状态
    'MarketStatus',
    'MarketStatusChecker',
    'get_market_status_for_trading',
    # ATR计算
    'calculate_tr',
    'calculate_atr',
    'calculate_atr_ratio',
    'calculate_recent_amplitude',
    'get_stop_loss_by_atr',
    'calculate_ma',
    'calculate_volume_ma',
    'is_above_ma',
    'is_below_ma',
    'days_below_ma',
    'calculate_max_profit',
    'calculate_current_profit',
    'calculate_drawback',
    # 保护模式
    'ProfitProtectMode',
    'PrincipalProtectMode',
    'TimeStopLoss',
    'PanicZoneChecker',
    # 决策引擎
    'StopLossDecisionEngine',
    'DecisionResult',
]
