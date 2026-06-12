#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
利润保护模式模块
浮盈≥10%时的回撤保护逻辑
"""

import pandas as pd
from typing import Tuple, Optional
from scripts.atr_calculator import (
    calculate_max_profit, 
    calculate_current_profit,
    calculate_drawback,
    is_below_ma
)
from config.stop_loss_config import get_profit_drawback_threshold
from scripts.market_status import MarketStatus


class ProfitProtectMode:
    """利润保护模式"""
    
    def __init__(self):
        self.min_profit_threshold = 0.10  # 进入利润保护模式的最低浮盈 10%
    
    def is_profit_mode(self, current_profit: float) -> bool:
        """
        判断是否处于利润保护模式
        
        Args:
            current_profit: 当前浮盈比例
        
        Returns:
            True if 浮盈≥10%
        """
        return current_profit >= self.min_profit_threshold
    
    def check_profit_clear(
        self, 
        current_profit: float,
        max_profit: float,
        df: pd.DataFrame,
        market_status: MarketStatus
    ) -> Tuple[bool, str, float]:
        """
        检查利润模式清仓条件（优先级5）
        
        条件：浮盈≥10%且回撤100%（回到成本）且股价<20日线且非恐慌区
        
        Args:
            current_profit: 当前浮盈
            max_profit: 最高浮盈
            df: 价格数据
            market_status: 大盘状态
        
        Returns:
            (是否触发, 原因, 减仓比例)
        """
        # 检查大盘状态
        if market_status == MarketStatus.PANIC or market_status == MarketStatus.EXTREME_PANIC:
            return False, "恐慌区禁止利润模式清仓", 0.0
        
        # 检查回撤100%（回到成本或以下）
        if current_profit > 0:
            return False, f"当前浮盈{current_profit*100:.1f}% > 0，未回到成本", 0.0
        
        # 检查股价<20日线
        if not is_below_ma(df, 20):
            return False, "股价未跌破20日线", 0.0
        
        return True, "浮盈回撤100%（回到成本）且股价<20日线，清仓", 1.0
    
    def check_profit_half(
        self,
        current_profit: float,
        max_profit: float,
        market_status: MarketStatus
    ) -> Tuple[bool, str, float]:
        """
        检查利润模式减半条件（优先级6）
        
        条件：浮盈≥10%且回撤≥阈值
        
        Args:
            current_profit: 当前浮盈
            max_profit: 最高浮盈
            market_status: 大盘状态
        
        Returns:
            (是否触发, 原因, 减仓比例)
        """
        # 计算回撤
        drawback = calculate_drawback(current_profit, max_profit)
        
        # 获取回撤阈值
        is_panic = (market_status == MarketStatus.PANIC)
        threshold = get_profit_drawback_threshold(max_profit, is_panic)
        
        # 检查是否触发
        if drawback >= threshold:
            return True, (
                f"最高浮盈{max_profit*100:.1f}%，当前回撤{drawback*100:.1f}% "
                f"≥ 阈值{threshold*100:.1f}%，减半"
            ), 0.5
        
        return False, (
            f"最高浮盈{max_profit*100:.1f}%，当前回撤{drawback*100:.1f}% "
            f"< 阈值{threshold*100:.1f}%，继续持有"
        ), 0.0
    
    def analyze(
        self,
        current_price: float,
        buy_price: float,
        df: pd.DataFrame,
        market_status: MarketStatus,
        historical_max_profit: float = None
    ) -> dict:
        """
        利润保护模式综合分析
        
        Args:
            current_price: 当前价格
            buy_price: 买入价格
            df: 价格数据（从买入日至今）
            market_status: 大盘状态
            historical_max_profit: 历史最高浮盈（用于减半后重置）
        
        Returns:
            {
                'in_profit_mode': bool,          # 是否处于利润保护模式
                'current_profit': float,          # 当前浮盈
                'max_profit': float,              # 最高浮盈
                'drawback': float,                # 当前回撤
                'clear_triggered': bool,          # 是否触发清仓
                'half_triggered': bool,           # 是否触发减半
                'action': str,                    # 操作建议
                'reduce_ratio': float,            # 减仓比例
                'reason': str,                    # 原因
            }
        """
        result = {
            'in_profit_mode': False,
            'current_profit': 0.0,
            'max_profit': 0.0,
            'drawback': 0.0,
            'clear_triggered': False,
            'half_triggered': False,
            'action': '持有',
            'reduce_ratio': 0.0,
            'reason': '',
        }
        
        # 计算当前浮盈
        current_profit = calculate_current_profit(current_price, buy_price)
        result['current_profit'] = current_profit
        
        # 检查是否进入利润保护模式
        if not self.is_profit_mode(current_profit):
            result['reason'] = f"浮盈{current_profit*100:.1f}% < 10%，不进入利润保护模式"
            return result
        
        result['in_profit_mode'] = True
        
        # 计算最高浮盈
        if historical_max_profit is not None:
            # 使用历史最高值（减半后重置的情况）
            max_profit_from_data = calculate_max_profit(df, buy_price)
            max_profit = max(historical_max_profit, max_profit_from_data)
        else:
            max_profit = calculate_max_profit(df, buy_price)
        
        result['max_profit'] = max_profit
        
        # 计算回撤
        drawback = calculate_drawback(current_profit, max_profit)
        result['drawback'] = drawback
        
        # 优先级5：检查利润模式清仓
        clear_triggered, clear_reason, clear_ratio = self.check_profit_clear(
            current_profit, max_profit, df, market_status
        )
        
        if clear_triggered:
            result['clear_triggered'] = True
            result['action'] = '清仓'
            result['reduce_ratio'] = clear_ratio
            result['reason'] = clear_reason
            return result
        
        # 优先级6：检查利润模式减半
        half_triggered, half_reason, half_ratio = self.check_profit_half(
            current_profit, max_profit, market_status
        )
        
        if half_triggered:
            result['half_triggered'] = True
            result['action'] = '减半'
            result['reduce_ratio'] = half_ratio
            result['reason'] = half_reason
            return result
        
        # 未触发任何条件
        result['reason'] = (
            f"利润保护模式：最高浮盈{max_profit*100:.1f}%，"
            f"当前回撤{drawback*100:.1f}%，未达到操作阈值"
        )
        
        return result
    
    def format_report(self, result: dict) -> str:
        """格式化利润保护模式报告"""
        lines = []
        lines.append("-" * 50)
        lines.append("💰 利润保护模式分析")
        lines.append("-" * 50)
        lines.append(f"当前浮盈: {result['current_profit']*100:.1f}%")
        
        if result['in_profit_mode']:
            lines.append(f"最高浮盈: {result['max_profit']*100:.1f}%")
            lines.append(f"当前回撤: {result['drawback']*100:.1f}%")
            lines.append(f"操作建议: {result['action']}")
            if result['reduce_ratio'] > 0:
                lines.append(f"减仓比例: {result['reduce_ratio']*100:.0f}%")
            lines.append(f"原因: {result['reason']}")
        else:
            lines.append(f"状态: 未进入利润保护模式（需浮盈≥10%）")
            lines.append(f"原因: {result['reason']}")
        
        lines.append("-" * 50)
        return "\n".join(lines)
