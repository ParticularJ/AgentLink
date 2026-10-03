#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纯计算型技术指标（无网络、无副作用，便于单元测试）。

注意：项目里另外还有两处 calc_atr 实现（atr_calculator.py 用于止损位，
market_phase_detector.py 用于行情判定），二者口径不同、各自被大量调用，
因此**没有**合并到这里，避免无谓的口径变更风险。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(closes: pd.Series, period: int = 14) -> float:
    """Wilder 平滑的 RSI(period)，返回最后一个值。

    修正记录：position_monitor.py 里曾有一个同名实现误写成
    `avg_gain / loss.replace(0, nan)`（用了原始 loss 而非 avg_loss），
    该函数当时没有任何调用点，已随重构删除。
    """
    closes = pd.Series(closes).astype(float)
    if len(closes) < 2:
        return 50.0
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    last = float(value.iloc[-1])
    if np.isnan(last):
        # 全程无下跌 -> avg_loss 为 0 -> RSI 定义为 100；全程无上涨则相反
        return 100.0 if float(avg_gain.iloc[-1]) > 0 else 50.0
    return last


def ma(series: pd.Series, window: int) -> pd.Series:
    """简单移动平均。"""
    return pd.Series(series).astype(float).rolling(window).mean()


def pct_change(from_price: float, to_price: float) -> float:
    """涨跌幅（%）；基准价非法时返回 0.0。"""
    if not from_price or from_price <= 0:
        return 0.0
    return (to_price - from_price) / from_price * 100


def upward_shadow_ratio(row: dict) -> float:
    """上影线占比 = (最高 - 收盘) / (最高 - 最低)。"""
    high = float(row.get("high", 0) or 0)
    low = float(row.get("low", 0) or 0)
    close = float(row.get("close", 0) or 0)
    span = high - low
    if span <= 0:
        return 0.0
    return (high - close) / span
