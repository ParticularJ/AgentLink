#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATR止损参数计算模块
提供精确ATR计算、板块速查表、快速估算三种精度
"""
import os
import sys
import pandas as pd
import numpy as np
from typing import Optional, Tuple

# 清除代理
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try:
            del os.environ[k]
        except:
            pass


# ── 板块速查表（ATR%范围）────────────────────────────────
SECTOR_ATR_CONFIG = {
    # 板块: (ATR%下限, ATR%上限, 清仓止损N=2.0, 减半止损N=2.0)
    "AI芯片": (5.0, 6.0, 0.13, 0.10),
    "存储": (5.0, 6.0, 0.13, 0.10),
    "科创板次新": (5.0, 6.0, 0.13, 0.10),
    "半导体设备": (4.0, 5.0, 0.11, 0.08),
    "半导体材料": (4.0, 5.0, 0.11, 0.08),
    "创业板": (4.0, 5.0, 0.11, 0.08),
    "主板半导体": (3.0, 4.0, 0.08, 0.06),
    "封测": (3.0, 4.0, 0.08, 0.06),
    "主板蓝筹": (2.0, 3.0, 0.07, 0.05),
    "白马股": (2.0, 3.0, 0.07, 0.05),
    "default": (3.0, 4.0, 0.08, 0.06),
}


def calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    计算ATR(14)
    df需要包含 high, low, close 列
    """
    if df is None or len(df) < period + 1:
        return 0.0

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    # TR = max(H-L, |H-PC|, |L-PC|)
    tr_list = []
    for i in range(1, len(close)):
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )
        tr_list.append(tr)

    if len(tr_list) < period:
        return 0.0

    atr = float(np.mean(tr_list[-period:]))
    return atr


def calc_atr_pct(atrs: float, current_price: float) -> float:
    """ATR占买入价的百分比"""
    if current_price <= 0:
        return 0.0
    return atrs / current_price


def calc_volatility_estimate(df: pd.DataFrame, periods: int = 10) -> float:
    """
    快速估算波动率：近N日平均振幅 / 前日收盘
    振幅 = (H-L) / 前日收盘
    """
    if df is None or len(df) < periods + 2:
        return 0.0

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    amplitudes = []
    for i in range(2, len(closes)):
        prev_close = closes[i - 1]
        if prev_close <= 0:
            continue
        amplitude = (highs[i] - lows[i]) / prev_close
        amplitudes.append(amplitude)

    if len(amplitudes) < periods:
        return 0.0

    avg_amplitude = float(np.mean(amplitudes[-periods:]))
    return avg_amplitude


def calc_stop_levels(
    atr: float,
    entry_price: float,
    sector: str = "default",
    n_multiplier: float = 2.0
) -> dict:
    """
    计算止损参数

    Returns:
        {
            "atr_pct": ATR占买入价百分比,
            "atr_abs": ATR绝对值,
            "clear_stop_pct": 清仓止损比例,
            "clear_stop_price": 清仓止损价格,
            "half_stop_pct": 减半止损比例,
            "half_stop_price": 减半止损价格,
            "method": "精确ATR" / "板块速查" / "快速估算"
        }
    """
    # ATR精确计算
    atr_pct = calc_atr_pct(atr, entry_price)
    clear_stop_pct = n_multiplier * atr_pct
    half_stop_pct = clear_stop_pct * 0.65

    clear_stop_price = round(entry_price * (1 - clear_stop_pct), 2)
    half_stop_price = round(entry_price * (1 - half_stop_pct), 2)

    return {
        "atr_pct": round(atr_pct, 4),
        "atr_abs": round(atr, 4),
        "clear_stop_pct": round(clear_stop_pct, 4),
        "clear_stop_price": clear_stop_price,
        "half_stop_pct": round(half_stop_pct, 4),
        "half_stop_price": half_stop_price,
        "method": "精确ATR",
        "sector": sector,
    }


def calc_stop_levels_by_sector(
    sector: str,
    entry_price: float,
    atr_pct_override: float = None
) -> dict:
    """
    板块速查表方式计算止损
    sector: 板块名称
    """
    # 匹配板块（模糊匹配关键字）
    key = "default"
    for k in SECTOR_ATR_CONFIG:
        if k != "default" and k in sector:
            key = k
            break

    atr_low, atr_high, clear_pct, half_pct = SECTOR_ATR_CONFIG[key]

    if atr_pct_override is not None:
        atr_pct = atr_pct_override
        clear_pct = 2.0 * atr_pct
        half_pct = clear_pct * 0.65
    else:
        # 取中值
        atr_pct = (atr_low + atr_high) / 2 / 100
        clear_pct = 2.0 * atr_pct
        half_pct = clear_pct * 0.65

    clear_stop_price = round(entry_price * (1 - clear_pct), 2)
    half_stop_price = round(entry_price * (1 - half_pct), 2)

    return {
        "atr_pct": round(atr_pct, 4),
        "atr_abs": 0.0,
        "clear_stop_pct": round(clear_pct, 4),
        "clear_stop_price": clear_stop_price,
        "half_stop_pct": round(half_pct, 4),
        "half_stop_price": half_stop_price,
        "method": "板块速查",
        "sector": key,
        "atr_range": f"{atr_low}%~{atr_high}%",
    }


def calc_stop_levels_fast(df: pd.DataFrame, entry_price: float, is_growth_board: bool) -> dict:
    """
    快速判断法（无ATR数据时应急估算）
    """
    avg_amplitude = calc_volatility_estimate(df, 10)

    if is_growth_board:
        if avg_amplitude > 0.08:
            clear_pct, half_pct = 0.13, 0.10
            method = "快速估算(科创/创业,高振幅)"
        else:
            clear_pct, half_pct = 0.11, 0.08
            method = "快速估算(科创/创业,正常)"
    else:
        if avg_amplitude > 0.05:
            clear_pct, half_pct = 0.09, 0.07
            method = "快速估算(主板,高振幅)"
        else:
            clear_pct, half_pct = 0.07, 0.05
            method = "快速估算(主板,正常)"

    clear_stop_price = round(entry_price * (1 - clear_pct), 2)
    half_stop_price = round(entry_price * (1 - half_pct), 2)

    return {
        "atr_pct": round(avg_amplitude, 4),
        "atr_abs": 0.0,
        "clear_stop_pct": round(clear_pct, 4),
        "clear_stop_price": clear_stop_price,
        "half_stop_pct": round(half_pct, 4),
        "half_stop_price": half_stop_price,
        "method": method,
        "sector": "快速估算",
    }


def is_growth_board(code: str) -> bool:
    """判断是否属于科创板/创业板（高波动板块）"""
    code = code.strip()
    # 科创板：688开头
    if code.startswith("688"):
        return True
    # 创业板：300开头
    if code.startswith("300"):
        return True
    return False


def get_lot_size(code: str) -> int:
    """
    返回交易单位（每手股数）
    - 科创板（688开头）：200股/手
    - 其他（创业板300/主板等）：100股/手
    """
    if code.startswith("688"):
        return 200
    return 100


def auto_calc_stop_levels(
    df: pd.DataFrame,
    code: str,
    entry_price: float,
    sector: str = "default",
    n_multiplier: float = 2.0
) -> dict:
    """
    自动选择最佳精度计算止损
    优先级：精确ATR > 板块速查 > 快速估算
    """
    # 方法1：精确ATR
    atr = calc_atr(df, 14)
    if atr > 0 and entry_price > 0:
        result = calc_stop_levels(atr, entry_price, sector, n_multiplier)
        if result["atr_pct"] > 0.01:  # ATR% 至少 > 1%
            return result

    # 方法2：板块速查
    is_growth = is_growth_board(code)
    if is_growth:
        lookup_sector = "创业板" if code.startswith("300") else "科创板次新"
    else:
        lookup_sector = "主板半导体"

    result = calc_stop_levels_by_sector(lookup_sector, entry_price)
    if result["atr_pct"] > 0:
        return result

    # 方法3：快速估算
    return calc_stop_levels_fast(df, entry_price, is_growth)