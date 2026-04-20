#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术指标计算模块
"""

import numpy as np
import pandas as pd


def calculate_rsi(closes: np.ndarray, period: int = 14) -> float:
    """计算RSI指标"""
    if len(closes) < period + 1:
        return 50.0

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # 使用指数移动平均
    alpha = 2.0 / (period + 1)
    avg_gain = gains[-period:].mean()
    avg_loss = losses[-period:].mean()

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def calculate_macd(
    closes: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> dict:
    """
    计算MACD指标
    返回 DIF, DEA, HIST
    """
    if len(closes) < slow + signal:
        return {'dif': 0.0, 'dea': 0.0, 'hist': 0.0, 'signal': 'unknown'}

    # EMA
    ema_fast = pd.Series(closes).ewm(span=fast, adjust=False).mean().values
    ema_slow = pd.Series(closes).ewm(span=slow, adjust=False).mean().values

    dif = ema_fast - ema_slow
    dea = pd.Series(dif).ewm(span=signal, adjust=False).mean().values
    hist = (dif - dea) * 2  # 柱状线

    dif_val = float(dif[-1])
    dea_val = float(dea[-1])
    hist_val = float(hist[-1])

    # 信号判断
    if dif_val > dea_val and dif_val > 0:
        sig = 'golden_cross'  # 零轴上方金叉（多头）
    elif dif_val < dea_val and dif_val > 0:
        sig = 'high_dead_cross'  # 高位死叉（看空）
    elif dif_val > dea_val and dif_val < 0:
        sig = 'recovering'  # 零轴下方金叉（反弹）
    elif dif_val < dea_val and dif_val < 0:
        sig = 'below_zero'  # 持续在零轴下方（弱势）
    else:
        sig = 'neutral'

    return {
        'dif': round(dif_val, 4),
        'dea': round(dea_val, 4),
        'hist': round(hist_val, 4),
        'signal': sig,
        'dif_arr': dif.tolist(),
        'dea_arr': dea.tolist(),
    }


def check_macd_bearish_divergence(
    prices: np.ndarray,
    macd_dif: np.ndarray,
    lookback: int = 20
) -> bool:
    """
    检测MACD顶背离
    价格创新高但MACD未创新高 → 顶背离
    """
    if len(prices) < lookback:
        return False

    recent_prices = prices[-lookback:]
    recent_macd = macd_dif[-lookback:]

    price_max_idx = np.argmax(recent_prices)
    macd_max_idx = np.argmax(recent_macd)

    # 价格创新高（在窗口内）
    price_new_high = (price_max_idx == len(recent_prices) - 1) or \
                     (recent_prices[-1] >= recent_prices.max() * 0.98)

    # MACD未创新高（dif低于前期高点）
    macd_not_high = recent_macd[-1] < recent_macd.max() * 0.95

    return price_new_high and macd_not_high


def check_volume_anomaly(df: pd.DataFrame) -> str:
    """
    检测成交量异常
    返回：
    - 'high_volume_top': 高位巨量（警惕）
    - 'price_up_volume_down': 价涨量缩（背离）
    - 'normal': 正常
    """
    if len(df) < 20:
        return 'normal'

    closes = df['收盘'].astype(float).values
    volumes = df['成交量'].astype(float).values

    vol_ma20 = volumes[-20:].mean()
    current_vol = volumes[-1]
    vol_ratio = current_vol / vol_ma20 if vol_ma20 > 0 else 1

    price_change = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] != 0 else 0

    # 高位巨量：涨幅>3% 且 成交量>均量2倍
    if price_change > 3 and vol_ratio > 2.0:
        return 'high_volume_top'

    # 价涨量缩：价格上涨但成交量萎缩
    if price_change > 1 and vol_ratio < 0.7:
        return 'price_up_volume_down'

    # 底部放量大涨（可能启动）
    if price_change > 5 and vol_ratio > 2.5:
        return 'bottom_volume_up'

    return 'normal'


def check_ma_death_cross(ma5: float, ma10: float, ma20: float) -> bool:
    """检查均线死叉（短期跌破中期）"""
    return ma5 < ma10 and ma10 < ma20


def check_ma_golden_cross(ma5: float, ma10: float, ma20: float) -> bool:
    """检查均线金叉（短期突破中期）"""
    return ma5 > ma10 and ma10 > ma20
