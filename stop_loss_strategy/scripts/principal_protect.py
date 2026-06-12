#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本金保护模式模块
浮盈<10%时的均线和ATR止损逻辑
"""

import pandas as pd
from typing import Tuple
from scripts.atr_calculator import (
    calculate_current_profit,
    is_below_ma,
    days_below_ma,
    calculate_ma,
    calculate_volume_ma,
    calculate_atr_ratio
)
from scripts.market_status import MarketStatus


class PrincipalProtectMode:
    """本金保护模式"""
    
    def __init__(self):
        self.profit_threshold = 0.10  # 利润保护模式阈值 10%
    
    def is_principal_mode(self, current_profit: float) -> bool:
        """
        判断是否处于本金保护模式
        
        Args:
            current_profit: 当前浮盈比例
        
        Returns:
            True if 浮盈<10%
        """
        return current_profit < self.profit_threshold
    
    def check_ma5_half(
        self,
        df: pd.DataFrame,
        current_profit: float,
        market_status: MarketStatus
    ) -> Tuple[bool, str, float]:
        """
        检查本金模式5日线减半条件（优先级7）
        
        条件：浮盈<10%且收盘价<5日线且跌破>1×ATR(5)且（量>5日均量×1.2或连续2天<5日线）
        
        Args:
            df: 价格数据
            current_profit: 当前浮盈
            market_status: 大盘状态
        
        Returns:
            (是否触发, 原因, 减仓比例)
        """
        # 检查收盘价<5日线
        if not is_below_ma(df, 5):
            return False, "收盘价在5日均线上方", 0.0
        
        # 计算ATR(5)
        atr_ratio = calculate_atr_ratio(df, 5)
        ma5 = calculate_ma(df, 5)
        current_price = df['close'].iloc[-1]
        
        # 检查跌破幅度 > 1×ATR(5)
        drop_below_ma = (ma5 - current_price) / ma5
        if drop_below_ma <= atr_ratio:
            return False, f"跌破5日线幅度{drop_below_ma*100:.2f}% ≤ ATR(5){atr_ratio*100:.2f}%", 0.0
        
        # 检查量能条件：量>5日均量×1.2 或 连续2天<5日线
        volume_condition = False
        volume_reason = ""
        
        if 'volume' in df.columns:
            current_volume = df['volume'].iloc[-1]
            volume_ma5 = calculate_volume_ma(df, 5)
            
            if volume_ma5 > 0 and current_volume > volume_ma5 * 1.2:
                volume_condition = True
                volume_reason = f"放量{current_volume/volume_ma5:.1f}倍"
            elif days_below_ma(df, 5) >= 2:
                volume_condition = True
                volume_reason = f"连续{days_below_ma(df, 5)}天低于5日线"
        else:
            # 无成交量数据时，仅检查连续天数
            if days_below_ma(df, 5) >= 2:
                volume_condition = True
                volume_reason = f"连续{days_below_ma(df, 5)}天低于5日线"
        
        if not volume_condition:
            return False, "未满足量能条件（放量破线或连续2天<5日线）", 0.0
        
        # 检查大盘限制
        if market_status == MarketStatus.PANIC or market_status == MarketStatus.EXTREME_PANIC:
            # 恐慌区最多减至3成（即减仓不超过70%）
            return True, f"跌破5日线且{volume_reason}，恐慌区最多减至3成", 0.7
        
        return True, f"跌破5日线且{volume_reason}，减半", 0.5
    
    def check_ma10_clear(
        self,
        df: pd.DataFrame,
        current_profit: float,
        market_status: MarketStatus
    ) -> Tuple[bool, str, float]:
        """
        检查本金模式10日线清仓条件（优先级8）
        
        条件：浮盈<10%且收盘价<10日线且（量>5日均量×1.5或连续3天<10日线）
        
        Args:
            df: 价格数据
            current_profit: 当前浮盈
            market_status: 大盘状态
        
        Returns:
            (是否触发, 原因, 减仓比例)
        """
        # 检查大盘状态
        if market_status == MarketStatus.PANIC or market_status == MarketStatus.EXTREME_PANIC:
            return False, "恐慌区禁止本金模式清仓", 0.0
        
        # 检查收盘价<10日线
        if not is_below_ma(df, 10):
            return False, "收盘价在10日均线上方", 0.0
        
        # 检查量能条件：量>5日均量×1.5 或 连续3天<10日线
        volume_condition = False
        volume_reason = ""
        
        if 'volume' in df.columns:
            current_volume = df['volume'].iloc[-1]
            volume_ma5 = calculate_volume_ma(df, 5)
            
            if volume_ma5 > 0 and current_volume > volume_ma5 * 1.5:
                volume_condition = True
                volume_reason = f"放量{current_volume/volume_ma5:.1f}倍"
            elif days_below_ma(df, 10) >= 3:
                volume_condition = True
                volume_reason = f"连续{days_below_ma(df, 10)}天低于10日线"
        else:
            # 无成交量数据时，仅检查连续天数
            if days_below_ma(df, 10) >= 3:
                volume_condition = True
                volume_reason = f"连续{days_below_ma(df, 10)}天低于10日线"
        
        if not volume_condition:
            return False, "未满足量能条件（放量破线或连续3天<10日线）", 0.0
        
        return True, f"跌破10日线且{volume_reason}，清仓", 1.0
    
    def analyze(
        self,
        current_price: float,
        buy_price: float,
        df: pd.DataFrame,
        market_status: MarketStatus
    ) -> dict:
        """
        本金保护模式综合分析
        
        Args:
            current_price: 当前价格
            buy_price: 买入价格
            df: 价格数据
            market_status: 大盘状态
        
        Returns:
            {
                'in_principal_mode': bool,       # 是否处于本金保护模式
                'current_profit': float,          # 当前浮盈
                'ma5_half_triggered': bool,       # 是否触发5日线减半
                'ma10_clear_triggered': bool,     # 是否触发10日线清仓
                'action': str,                    # 操作建议
                'reduce_ratio': float,            # 减仓比例
                'reason': str,                    # 原因
            }
        """
        result = {
            'in_principal_mode': False,
            'current_profit': 0.0,
            'ma5_half_triggered': False,
            'ma10_clear_triggered': False,
            'action': '持有',
            'reduce_ratio': 0.0,
            'reason': '',
        }
        
        # 计算当前浮盈
        current_profit = calculate_current_profit(current_price, buy_price)
        result['current_profit'] = current_profit
        
        # 检查是否处于本金保护模式
        if not self.is_principal_mode(current_profit):
            result['reason'] = f"浮盈{current_profit*100:.1f}% ≥ 10%，进入利润保护模式"
            return result
        
        result['in_principal_mode'] = True
        
        # 优先级7：检查5日线减半
        ma5_triggered, ma5_reason, ma5_ratio = self.check_ma5_half(
            df, current_profit, market_status
        )
        
        if ma5_triggered:
            result['ma5_half_triggered'] = True
            result['action'] = '减半'
            result['reduce_ratio'] = ma5_ratio
            result['reason'] = ma5_reason
            return result
        
        # 优先级8：检查10日线清仓
        ma10_triggered, ma10_reason, ma10_ratio = self.check_ma10_clear(
            df, current_profit, market_status
        )
        
        if ma10_triggered:
            result['ma10_clear_triggered'] = True
            result['action'] = '清仓'
            result['reduce_ratio'] = ma10_ratio
            result['reason'] = ma10_reason
            return result
        
        # 未触发任何条件
        result['reason'] = "本金保护模式：未达到均线操作条件"
        
        return result
    
    def format_report(self, result: dict) -> str:
        """格式化本金保护模式报告"""
        lines = []
        lines.append("-" * 50)
        lines.append("🛡️ 本金保护模式分析")
        lines.append("-" * 50)
        lines.append(f"当前浮盈: {result['current_profit']*100:.1f}%")
        
        if result['in_principal_mode']:
            lines.append(f"操作建议: {result['action']}")
            if result['reduce_ratio'] > 0:
                lines.append(f"减仓比例: {result['reduce_ratio']*100:.0f}%")
            lines.append(f"原因: {result['reason']}")
        else:
            lines.append(f"状态: 进入利润保护模式（浮盈≥10%）")
            lines.append(f"原因: {result['reason']}")
        
        lines.append("-" * 50)
        return "\n".join(lines)
