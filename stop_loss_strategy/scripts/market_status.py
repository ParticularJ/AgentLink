#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大盘状态判定模块
以沪深300指数为基准，每日14:40判定大盘状态
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
from enum import Enum


class MarketStatus(Enum):
    """大盘状态枚举"""
    NORMAL = "normal"           # 正常
    WEAK = "weak"               # 偏弱
    PANIC = "panic"             # 恐慌区
    EXTREME_PANIC = "extreme_panic"  # 极端恐慌


class MarketStatusChecker:
    """大盘状态检查器"""
    
    def __init__(self, index_code: str = "000300"):
        """
        初始化
        
        Args:
            index_code: 指数代码，默认沪深300 (000300)
        """
        self.index_code = index_code
        self.status_names = {
            MarketStatus.NORMAL: "正常",
            MarketStatus.WEAK: "偏弱",
            MarketStatus.PANIC: "恐慌区",
            MarketStatus.EXTREME_PANIC: "极端恐慌",
        }
    
    def calculate_ma(self, df: pd.DataFrame, period: int = 5) -> pd.Series:
        """计算移动平均线"""
        return df['close'].rolling(window=period).mean()
    
    def check_panic_zone(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        检查是否处于恐慌区
        
        条件：5日线下且连续3天内至少2天跌幅≥1.5%
        
        Returns:
            (是否恐慌区, 原因)
        """
        if len(df) < 5:
            return False, "数据不足"
        
        # 计算5日均线
        df['ma5'] = self.calculate_ma(df, 5)
        
        # 最新收盘价在5日线下方
        latest_close = df['close'].iloc[-1]
        latest_ma5 = df['ma5'].iloc[-1]
        
        if latest_close >= latest_ma5:
            return False, "收盘价在5日均线上方"
        
        # 检查最近3天是否有至少2天跌幅≥1.5%
        recent_3_days = df.iloc[-3:].copy()
        recent_3_days['change_pct'] = recent_3_days['close'].pct_change() * 100
        
        # 排除第一行（NaN）
        drop_days = recent_3_days['change_pct'].iloc[1:]
        big_drop_days = (drop_days <= -1.5).sum()
        
        if big_drop_days >= 2:
            return True, f"连续3天内{big_drop_days}天跌幅≥1.5%"
        
        return False, "未达到恐慌区条件（连续3天至少2天跌幅≥1.5%）"
    
    def check_extreme_panic(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        检查是否处于极端恐慌
        
        条件：恐慌区且当日跌幅≥2%
        
        Returns:
            (是否极端恐慌, 原因)
        """
        is_panic, panic_reason = self.check_panic_zone(df)
        
        if not is_panic:
            return False, "未处于恐慌区"
        
        # 检查当日跌幅
        latest_close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-2]
        today_drop = (latest_close - prev_close) / prev_close * 100
        
        if today_drop <= -2.0:
            return True, f"恐慌区且当日跌幅{today_drop:.2f}%≥2%"
        
        return False, f"恐慌区但当日跌幅{today_drop:.2f}%<2%"
    
    def determine_status(self, df: pd.DataFrame) -> Tuple[MarketStatus, str]:
        """
        判定大盘状态
        
        Returns:
            (状态枚举, 描述)
        """
        if len(df) < 5:
            return MarketStatus.NORMAL, "数据不足，默认正常"
        
        # 首先检查极端恐慌
        is_extreme, extreme_reason = self.check_extreme_panic(df)
        if is_extreme:
            return MarketStatus.EXTREME_PANIC, extreme_reason
        
        # 检查恐慌区
        is_panic, panic_reason = self.check_panic_zone(df)
        if is_panic:
            return MarketStatus.PANIC, panic_reason
        
        # 检查偏弱（5日线下方但未达恐慌区）
        df['ma5'] = self.calculate_ma(df, 5)
        latest_close = df['close'].iloc[-1]
        latest_ma5 = df['ma5'].iloc[-1]
        
        if latest_close < latest_ma5:
            return MarketStatus.WEAK, "收盘价在5日线下方，未达恐慌区"
        
        # 正常状态
        return MarketStatus.NORMAL, "收盘价在5日均线上方"
    
    def can_sell(self, status: MarketStatus, sell_type: str = "clear") -> Tuple[bool, str]:
        """
        检查是否可以卖出
        
        Args:
            status: 大盘状态
            sell_type: 卖出类型 ("clear"清仓 / "half"减半)
        
        Returns:
            (是否可以卖出, 原因)
        """
        if status == MarketStatus.EXTREME_PANIC:
            return False, "极端恐慌状态：禁止任何卖出"
        
        if status == MarketStatus.PANIC and sell_type == "clear":
            return False, "恐慌区状态：禁止清仓，最多减半至3成"
        
        return True, "允许卖出"
    
    def get_status_name(self, status: MarketStatus) -> str:
        """获取状态中文名称"""
        return self.status_names.get(status, "未知")
    
    def format_status_report(self, status: MarketStatus, reason: str) -> str:
        """格式化状态报告"""
        lines = []
        lines.append("=" * 50)
        lines.append(f"📊 大盘状态判定")
        lines.append("=" * 50)
        lines.append(f"指数: 沪深300 ({self.index_code})")
        lines.append(f"状态: {self.get_status_name(status)}")
        lines.append(f"原因: {reason}")
        lines.append("-" * 50)
        
        # 交易限制说明
        if status == MarketStatus.EXTREME_PANIC:
            lines.append("⚠️ 交易限制: 禁止任何卖出操作（绝对亏损规则除外）")
        elif status == MarketStatus.PANIC:
            lines.append("⚠️ 交易限制: 禁止清仓，最多减半至3成")
        elif status == MarketStatus.WEAK:
            lines.append("⚠️ 提示: 提高警惕，所有规则正常执行")
        else:
            lines.append("✅ 交易限制: 无")
        
        lines.append("=" * 50)
        return "\n".join(lines)


def get_market_status_for_trading(df: pd.DataFrame) -> Dict:
    """
    获取用于交易决策的大盘状态信息
    
    Returns:
        {
            'status': MarketStatus,
            'status_name': str,
            'reason': str,
            'can_clear': bool,      # 是否可以清仓
            'can_half': bool,       # 是否可以减半
            'max_reduce': float,    # 最大减仓比例（恐慌区限制）
        }
    """
    checker = MarketStatusChecker()
    status, reason = checker.determine_status(df)
    
    can_clear, _ = checker.can_sell(status, "clear")
    can_half, _ = checker.can_sell(status, "half")
    
    # 恐慌区最大减仓限制
    max_reduce = 1.0  # 默认可以全部减仓
    if status == MarketStatus.PANIC:
        max_reduce = 0.7  # 恐慌区最多减70%（保留30%）
    elif status == MarketStatus.EXTREME_PANIC:
        max_reduce = 0.0  # 极端恐慌不能减仓
    
    return {
        'status': status,
        'status_name': checker.get_status_name(status),
        'reason': reason,
        'can_clear': can_clear,
        'can_half': can_half,
        'max_reduce': max_reduce,
    }
