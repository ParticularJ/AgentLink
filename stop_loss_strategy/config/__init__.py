#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置模块
"""

from .stop_loss_config import (
    ATR_MULTIPLIER,
    AMPLITUDE_DAYS,
    SECTOR_STOP_LOSS_CONFIG,
    QUICK_JUDGMENT_CONFIG,
    PROFIT_DRAWBACK_CONFIG,
    MARKET_STATUS_CONFIG,
    PERSONAL_CONFIG,
    TIME_STOP_CONFIG,
    FALSE_BREAKOUT_CONFIG,
    CORRECTION_BUY_CONFIG,
    get_sector_stop_loss,
    get_quick_judgment_stop_loss,
    get_profit_drawback_threshold,
    calculate_atr_stop_loss,
)

from .sector_config import (
    SECTOR_STOCK_POOLS,
    get_stock_sector,
    get_sector_by_code_prefix,
)

__all__ = [
    'ATR_MULTIPLIER',
    'AMPLITUDE_DAYS',
    'SECTOR_STOP_LOSS_CONFIG',
    'QUICK_JUDGMENT_CONFIG',
    'PROFIT_DRAWBACK_CONFIG',
    'MARKET_STATUS_CONFIG',
    'PERSONAL_CONFIG',
    'TIME_STOP_CONFIG',
    'FALSE_BREAKOUT_CONFIG',
    'CORRECTION_BUY_CONFIG',
    'get_sector_stop_loss',
    'get_quick_judgment_stop_loss',
    'get_profit_drawback_threshold',
    'calculate_atr_stop_loss',
    'SECTOR_STOCK_POOLS',
    'get_stock_sector',
    'get_sector_by_code_prefix',
]
