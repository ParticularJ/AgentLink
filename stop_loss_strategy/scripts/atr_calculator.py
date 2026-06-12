#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATR计算模块
计算个股的真实波动幅度均值(ATR)和近期平均振幅
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple


def calculate_tr(high: float, low: float, close: float, prev_close: float) -> float:
    """
    计算真实波幅(True Range)
    TR = max(|high-low|, |high-prev_close|, |low-prev_close|)
    """
    tr1 = abs(high - low)
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    return max(tr1, tr2, tr3)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    计算ATR（真实波动幅度均值）
    
    Args:
        df: DataFrame，包含 'high', 'low', 'close' 列
        period: ATR计算周期，默认14日
    
    Returns:
        ATR值（以价格为单位）
    """
    if len(df) < period + 1:
        return 0.0
    
    df = df.copy()
    df['prev_close'] = df['close'].shift(1)
    
    # 计算TR
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['prev_close'])
    df['tr3'] = abs(df['low'] - df['prev_close'])
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    # 计算ATR（使用 Wilder 平滑法）
    atr = df['tr'].iloc[1:].ewm(alpha=1/period, min_periods=period).mean().iloc[-1]
    
    return atr


def calculate_atr_ratio(df: pd.DataFrame, period: int = 14) -> float:
    """
    计算ATR比例（ATR / 收盘价）
    
    Returns:
        ATR比例（如 0.05 表示 5%）
    """
    if len(df) == 0 or df['close'].iloc[-1] == 0:
        return 0.0
    
    atr = calculate_atr(df, period)
    current_price = df['close'].iloc[-1]
    
    return atr / current_price if current_price > 0 else 0.0


def calculate_recent_amplitude(df: pd.DataFrame, days: int = 10) -> float:
    """
    计算近期平均振幅
    振幅 = (当日最高 - 当日最低) / 前日收盘
    
    Args:
        df: DataFrame，包含 'high', 'low', 'close' 列
        days: 计算天数，默认10日
    
    Returns:
        平均振幅比例（如 0.035 表示 3.5%）
    """
    if len(df) < days + 1:
        days = len(df) - 1
    
    if days < 1:
        return 0.0
    
    df = df.copy()
    df['prev_close'] = df['close'].shift(1)
    
    # 计算每日振幅
    df['amplitude'] = (df['high'] - df['low']) / df['prev_close']
    
    # 取最近days天的平均振幅
    recent_amplitude = df['amplitude'].iloc[-days:].mean()
    
    return recent_amplitude if not np.isnan(recent_amplitude) else 0.0


def get_stop_loss_by_atr(df: pd.DataFrame, multiplier: float = 2.0, 
                         period: int = 14) -> Tuple[float, float]:
    """
    基于ATR计算止损比例
    
    Args:
        df: DataFrame，包含 'high', 'low', 'close' 列
        multiplier: ATR乘数
        period: ATR计算周期
    
    Returns:
        (清仓止损比例, 减半止损比例)
        清仓止损 = ATR × multiplier
        减半止损 = 清仓止损 × 0.6
    """
    atr_ratio = calculate_atr_ratio(df, period)
    
    clear_stop_loss = atr_ratio * multiplier
    half_stop_loss = clear_stop_loss * 0.6
    
    return (clear_stop_loss, half_stop_loss)


def calculate_ma(df: pd.DataFrame, period: int) -> float:
    """
    计算移动平均线
    
    Returns:
        最新MA值
    """
    if len(df) < period:
        return df['close'].mean() if len(df) > 0 else 0.0
    
    return df['close'].iloc[-period:].mean()


def calculate_volume_ma(df: pd.DataFrame, period: int = 5) -> float:
    """
    计算成交量均线
    
    Returns:
        最新成交量MA值
    """
    if len(df) < period or 'volume' not in df.columns:
        return 0.0
    
    return df['volume'].iloc[-period:].mean()


def is_above_ma(df: pd.DataFrame, period: int) -> bool:
    """
    判断当前价格是否在均线上方
    
    Returns:
        True if 收盘价 > MA
    """
    if len(df) == 0:
        return False
    
    ma = calculate_ma(df, period)
    current_price = df['close'].iloc[-1]
    
    return current_price > ma


def is_below_ma(df: pd.DataFrame, period: int) -> bool:
    """
    判断当前价格是否在均线下方
    """
    return not is_above_ma(df, period)


def days_below_ma(df: pd.DataFrame, period: int) -> int:
    """
    计算连续在均线下方运行的天数
    
    Returns:
        连续天数
    """
    if len(df) < 2:
        return 0
    
    df = df.copy()
    df['ma'] = df['close'].rolling(window=period).mean()
    df['below_ma'] = df['close'] < df['ma']
    
    # 从后往前数连续为True的天数
    consecutive_days = 0
    for i in range(len(df) - 1, -1, -1):
        if df['below_ma'].iloc[i]:
            consecutive_days += 1
        else:
            break
    
    return consecutive_days


def calculate_max_profit(df: pd.DataFrame, buy_price: float) -> float:
    """
    计算持仓期间最高浮盈
    
    Args:
        df: DataFrame，包含 'high' 列（从买入日至今的数据）
        buy_price: 买入价格
    
    Returns:
        最高浮盈比例（如 0.25 表示 25%）
    """
    if len(df) == 0 or buy_price <= 0:
        return 0.0
    
    highest_price = df['high'].max()
    max_profit = (highest_price - buy_price) / buy_price
    
    return max_profit


def calculate_current_profit(current_price: float, buy_price: float) -> float:
    """
    计算当前浮盈/浮亏
    
    Returns:
        浮盈比例（正数表示盈利，负数表示亏损）
    """
    if buy_price <= 0:
        return 0.0
    
    return (current_price - buy_price) / buy_price


def calculate_drawback(current_profit: float, max_profit: float) -> float:
    """
    计算当前回撤比例
    
    回撤 = (最高浮盈 - 当前浮盈) / 最高浮盈 × 100%
    
    Args:
        current_profit: 当前浮盈比例
        max_profit: 最高浮盈比例
    
    Returns:
        回撤比例（如 0.45 表示 45%）
    """
    if max_profit <= 0:
        return 0.0
    
    drawback = (max_profit - current_profit) / max_profit
    
    return max(0.0, drawback)
