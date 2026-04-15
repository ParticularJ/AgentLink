#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略分类配置 - 不同买入策略对应不同的止盈/止损参数
所有盈利/止损比例均使用小数形式（0.10 = 10%）
"""

from typing import Dict


# 策略分类：激进 / 稳健 / 保守
STRATEGY_CLASS = {
    # ── 激进（主升浪，让利润奔跑）────────────────────────────
    'limit_up':          {'class': 'aggressive',   'note': '涨停连板，主升浪'},
    'breakout_high':     {'class': 'aggressive',   'note': '突破新高，趋势确认'},

    # ── 稳健（正常趋势交易）────────────────────────────────
    'gap_fill':          {'class': 'moderate',    'note': '缺口填充，趋势确认'},
    'ma_bullish':       {'class': 'moderate',    'note': '均线多头，稳定趋势'},

    # ── 保守（反弹/修复行情）───────────────────────────────
    'macd_divergence':  {'class': 'conservative', 'note': 'MACD背离，超跌反弹'},
    'rsi_oversold':     {'class': 'conservative', 'note': 'RSI超卖，超跌反弹'},
    'morning_star':      {'class': 'conservative', 'note': '早晨之星，底部反转'},
    'volume_extreme':    {'class': 'conservative', 'note': '地量见底，反弹修复'},

    # ── 超短（不过夜）────────────────────────────────────
    'a_stock_1430':      {'class': 'intraday',     'note': '尾盘超短，次日开盘走'},

    # ── 默认（未标记的持仓）────────────────────────────────
    'default':           {'class': 'moderate',    'note': '默认稳健策略'},
}


# ── 单只仓位上限配置（小数形式）──────────────────────────────
POSITION_SIZE_CONFIG: Dict[str, float] = {
    'aggressive':   0.20,   # 激进策略：单只上限20%
    'moderate':     0.15,   # 稳健策略：单只上限15%
    'conservative': 0.10,   # 保守策略：单只上限10%
    'intraday':     0.05,   # 超短策略：单只上限5%
}


# ── 大盘环境与总仓位配置（小数形式）──────────────────────────────
MARKET_STATUS_CONFIG: Dict[str, float] = {
    'strong':     0.80,   # 强势：总仓位80%
    'bullish':    0.60,   # 震荡偏多：总仓位60%
    'neutral':    0.50,   # 震荡：总仓位50%
    'bearish':    0.30,   # 震荡偏空：总仓位30%
    'weak':       0.10,   # 弱势：总仓位10%
}


# ── 止损配置（小数形式，如 0.05 = 5%）──────────────────────────────
STOP_LOSS_CONFIG: Dict[str, float] = {
    'aggressive':   0.07,   # -7% 止损
    'moderate':     0.05,   # -5% 止损
    'conservative': 0.03,   # -3% 止损
    'intraday':     0.02,   # -2% 止损
}


# ── 止盈配置（小数形式，key=盈利阈值，value=(减仓比例, 描述)）─────────────────
# 盈利幅度 thresholds 也用小数，如 0.10 = 10%
PROFIT_TAKE_CONFIG: Dict[str, dict] = {
    # ── 激进：让利润奔跑 ────────────────────────────────
    'aggressive': {
        0.10: (0.00, '盈利10%，持有观望'),
        0.15: (0.00, '盈利15%，继续持有'),
        0.20: (0.00, '盈利20%，让利润奔跑'),
        0.30: (0.30, '盈利30%，减仓30%留70%持仓'),
        0.40: (0.50, '盈利40%，减仓50%'),
        0.50: (0.70, '盈利50%，减仓70%'),
        0.80: (1.00, '盈利80%，高位清仓守住利润'),
    },

    # ── 稳健：正常止盈 ──────────────────────────────────
    'moderate': {
        0.05: (0.00, '盈利5%，继续持有'),
        0.10: (0.30, '盈利10%，减仓30%锁定收益'),
        0.15: (0.50, '盈利15%，减仓50%'),
        0.20: (0.50, '盈利20%，减仓50%'),
        0.30: (0.70, '盈利30%，减仓70%留30%持仓'),
        0.40: (1.00, '盈利40%，清仓'),
    },

    # ── 保守：尽早落袋 ───────────────────────────────────
    'conservative': {
        0.05: (0.20, '盈利5%，减仓20%锁定收益'),
        0.08: (0.30, '盈利8%，减仓30%'),
        0.10: (0.50, '盈利10%，减仓50%过半仓落袋'),
        0.15: (0.70, '盈利15%，减仓70%'),
        0.20: (1.00, '盈利20%，清仓'),
    },

    # ── 超短：次日开盘必走 ───────────────────────────────
    'intraday': {
        0.02: (0.50, '盈利2%，减半仓'),
        0.05: (1.00, '盈利5%+，清仓不过夜'),
    },
}


# ── RSI 过买阈值（超过则加重减仓）─────────────────────────────
RSI_OVERBOUGHT_THRESHOLD: Dict[str, float] = {
    'aggressive':   90.0,   # RSI>90 才干预
    'moderate':     85.0,   # RSI>85 适当加码
    'conservative': 80.0,   # RSI>80 就要注意
    'intraday':     75.0,   # 超短 RSI>75就走
}


# ──────────────────────────────────────────────────────────
def get_strategy_class(buy_reason: str) -> str:
    return STRATEGY_CLASS.get(buy_reason, STRATEGY_CLASS['default'])['class']


def get_stop_loss(buy_reason: str) -> float:
    cls = get_strategy_class(buy_reason)
    return STOP_LOSS_CONFIG.get(cls, 0.05)


def get_position_size_limit(buy_reason: str) -> float:
    cls = get_strategy_class(buy_reason)
    return POSITION_SIZE_CONFIG.get(cls, 0.15)


def get_profit_take_stages(buy_reason: str) -> dict:
    cls = get_strategy_class(buy_reason)
    return PROFIT_TAKE_CONFIG.get(cls, PROFIT_TAKE_CONFIG['moderate'])


def get_rsi_threshold(buy_reason: str) -> float:
    cls = get_strategy_class(buy_reason)
    return RSI_OVERBOUGHT_THRESHOLD.get(cls, 80.0)


def calculate_profit_take(profit_pct: float, buy_reason: str, rsi: float) -> tuple:
    """
    根据盈利幅度（百分比，如 10.0 表示 10%）、策略类型、RSI 计算止盈建议
    返回: (减仓比例, 描述)
    """
    cls = get_strategy_class(buy_reason)
    stages = get_profit_take_stages(buy_reason)
    rsi_threshold = get_rsi_threshold(buy_reason)

    # 盈利幅度转小数（10.0% -> 0.10）
    profit_decimal = profit_pct / 100.0

    # 按盈利阶段从小到大匹配，找到最高的达标阶段
    profit_levels = sorted(stages.keys())   # 升序
    matched_level = None
    for level in profit_levels:
        if profit_decimal >= level:
            matched_level = level

    if matched_level is None:
        return 0.0, '盈利未达目标，继续持有'

    sell_pct, desc = stages[matched_level]

    # RSI 辅助判断：是否需要加码减仓
    if rsi >= rsi_threshold:
        sell_pct = max(sell_pct, 0.30)
        desc += f'（RSI>{rsi_threshold:.0f}，加重减仓）'

    return sell_pct, desc


def calculate_stop_loss_action(
    loss_pct: float,
    buy_reason: str,
    current_price: float,
    buy_price: float
) -> tuple:
    """
    根据亏损幅度（正数表示亏损比例）和策略类型计算止损操作
    返回: (止损比例, 描述) 或 (None, None) 如果未触发
    """
    cls = get_strategy_class(buy_reason)
    stop_loss = get_stop_loss(buy_reason)

    if loss_pct >= stop_loss:
        return 1.0, f'触及止损线（-{stop_loss*100:.0f}%，{cls}策略），强制清仓'
    elif loss_pct >= stop_loss * 0.6:
        return 0.50, f'亏损{loss_pct:.1f}%，接近止损线，警告'

    return None, None
