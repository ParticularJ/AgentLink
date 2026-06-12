#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时间止损模块
持仓时间过长且未达预期收益时的止损逻辑
"""

from datetime import datetime, timedelta
from typing import Tuple, Optional
from scripts.market_status import MarketStatus
from config.stop_loss_config import TIME_STOP_CONFIG


class TimeStopLoss:
    """时间止损"""
    
    def __init__(self):
        self.min_hold_days = TIME_STOP_CONFIG['min_hold_days']
        self.min_profit = TIME_STOP_CONFIG['min_profit_for_time_stop']
        self.loss_ratio = TIME_STOP_CONFIG['loss_ratio_for_time_stop']
    
    def calculate_hold_days(self, buy_date: str, current_date: str = None) -> int:
        """
        计算持仓天数
        
        Args:
            buy_date: 买入日期 (格式: YYYY-MM-DD)
            current_date: 当前日期，默认今天
        
        Returns:
            持仓天数
        """
        if current_date is None:
            current_date = datetime.now().strftime('%Y-%m-%d')
        
        try:
            buy = datetime.strptime(buy_date, '%Y-%m-%d')
            current = datetime.strptime(current_date, '%Y-%m-%d')
            return (current - buy).days
        except:
            return 0
    
    def check_time_stop(
        self,
        hold_days: int,
        current_profit: float,
        clear_stop_loss: float,
        market_status: MarketStatus
    ) -> Tuple[bool, str, float]:
        """
        检查时间止损条件（优先级9）
        
        条件：持仓>10日且浮盈<5%且亏损≥原止损×0.8
        
        Args:
            hold_days: 持仓天数
            current_profit: 当前浮盈（负数表示亏损）
            clear_stop_loss: 清仓止损比例（正数，如0.10）
            market_status: 大盘状态
        
        Returns:
            (是否触发, 原因, 减仓比例)
        """
        # 检查大盘状态
        if market_status == MarketStatus.PANIC or market_status == MarketStatus.EXTREME_PANIC:
            return False, "恐慌区禁止时间止损清仓", 0.0
        
        # 检查持仓天数
        if hold_days <= self.min_hold_days:
            return False, f"持仓{hold_days}天 ≤ {self.min_hold_days}天", 0.0
        
        # 检查浮盈条件（需<5%）
        if current_profit >= self.min_profit:
            return False, f"浮盈{current_profit*100:.1f}% ≥ {self.min_profit*100}%", 0.0
        
        # 检查亏损条件（亏损≥原止损×0.8）
        # current_profit为负数表示亏损
        loss_threshold = clear_stop_loss * self.loss_ratio  # 如 10% * 0.8 = 8%
        
        if current_profit > -loss_threshold:
            return False, f"亏损{abs(current_profit)*100:.1f}% < 阈值{loss_threshold*100:.1f}%", 0.0
        
        return True, (
            f"持仓{hold_days}天，浮盈{current_profit*100:.1f}% < 5%，"
            f"亏损{abs(current_profit)*100:.1f}% ≥ 原止损{clear_stop_loss*100:.1f}%×0.8，"
            f"时间止损清仓"
        ), 1.0
    
    def analyze(
        self,
        buy_date: str,
        current_date: str,
        current_profit: float,
        clear_stop_loss: float,
        market_status: MarketStatus
    ) -> dict:
        """
        时间止损综合分析
        
        Args:
            buy_date: 买入日期
            current_date: 当前日期
            current_profit: 当前浮盈
            clear_stop_loss: 清仓止损比例
            market_status: 大盘状态
        
        Returns:
            {
                'hold_days': int,                 # 持仓天数
                'time_stop_triggered': bool,      # 是否触发时间止损
                'action': str,                    # 操作建议
                'reduce_ratio': float,            # 减仓比例
                'reason': str,                    # 原因
            }
        """
        result = {
            'hold_days': 0,
            'time_stop_triggered': False,
            'action': '持有',
            'reduce_ratio': 0.0,
            'reason': '',
        }
        
        # 计算持仓天数
        hold_days = self.calculate_hold_days(buy_date, current_date)
        result['hold_days'] = hold_days
        
        # 检查时间止损
        triggered, reason, ratio = self.check_time_stop(
            hold_days, current_profit, clear_stop_loss, market_status
        )
        
        if triggered:
            result['time_stop_triggered'] = True
            result['action'] = '清仓'
            result['reduce_ratio'] = ratio
            result['reason'] = reason
        else:
            result['reason'] = f"持仓{hold_days}天，{reason}"
        
        return result
    
    def format_report(self, result: dict) -> str:
        """格式化时间止损报告"""
        lines = []
        lines.append("-" * 50)
        lines.append("⏰ 时间止损分析")
        lines.append("-" * 50)
        lines.append(f"持仓天数: {result['hold_days']}天")
        
        if result['time_stop_triggered']:
            lines.append(f"⚠️ 触发时间止损")
            lines.append(f"操作建议: {result['action']}")
            lines.append(f"减仓比例: {result['reduce_ratio']*100:.0f}%")
        
        lines.append(f"原因: {result['reason']}")
        lines.append("-" * 50)
        return "\n".join(lines)
