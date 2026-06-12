#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优先级决策引擎
按优先级1→9顺序检查，一旦某个条件满足并执行操作，立即结束当天决策
"""

import pandas as pd
from datetime import datetime
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass

from scripts.market_status import MarketStatus, get_market_status_for_trading
from scripts.atr_calculator import (
    calculate_current_profit,
    get_stop_loss_by_atr,
    calculate_recent_amplitude
)
from scripts.profit_protect import ProfitProtectMode
from scripts.principal_protect import PrincipalProtectMode
from scripts.time_stop import TimeStopLoss
from scripts.panic_checker import PanicZoneChecker
from config.stop_loss_config import (
    get_sector_stop_loss,
    get_quick_judgment_stop_loss,
    SECTOR_STOP_LOSS_CONFIG
)
from config.sector_config import get_stock_sector


@dataclass
class DecisionResult:
    """决策结果"""
    priority: int                    # 优先级
    check_item: str                  # 检查项名称
    triggered: bool                  # 是否触发
    action: str                      # 操作（清仓/减半/持有）
    reduce_ratio: float              # 减仓比例
    reason: str                      # 原因
    market_blocked: bool = False     # 是否被大盘状态拦截


class StopLossDecisionEngine:
    """止损决策引擎"""
    
    def __init__(self):
        self.profit_protect = ProfitProtectMode()
        self.principal_protect = PrincipalProtectMode()
        self.time_stop = TimeStopLoss()
        self.panic_checker = PanicZoneChecker()
    
    def get_stop_loss_params(
        self,
        stock_code: str,
        stock_name: str,
        df: pd.DataFrame,
        use_atr: bool = False  # 默认不使用ATR，使用板块配置
    ) -> Tuple[float, float]:
        """
        获取止损参数
        优先级：① ATR精确计算 > ② 板块速查表 > ③ 快速判断法
        
        Args:
            use_atr: 是否使用ATR计算，默认False（使用板块配置更稳定）
        
        Returns:
            (清仓止损比例, 减半止损比例)
        """
        # ① 尝试ATR精确计算（仅当启用且数据充足时）
        if use_atr and len(df) >= 20:
            try:
                atr_clear, atr_half = get_stop_loss_by_atr(df, multiplier=2.0, period=14)
                # ATR止损通常在5%-15%之间，超出范围则使用板块配置
                if 0.05 <= atr_clear <= 0.20:
                    return (atr_clear, atr_half)
            except Exception as e:
                pass
        
        # ② 板块速查表
        sector = get_stock_sector(stock_code, stock_name)
        if sector in SECTOR_STOP_LOSS_CONFIG:
            return get_sector_stop_loss(sector)
        
        # ③ 快速判断法（基于近期平均振幅）
        amplitude = calculate_recent_amplitude(df, days=10)
        return get_quick_judgment_stop_loss(amplitude)
    
    def check_priority_1_absolute_loss_clear(
        self,
        current_profit: float,
        clear_stop_loss: float
    ) -> DecisionResult:
        """
        优先级1：绝对亏损清仓
        条件：亏损≥清仓止损比例
        操作：无条件清仓
        大盘影响：不受任何影响
        """
        if current_profit <= -clear_stop_loss:
            return DecisionResult(
                priority=1,
                check_item="绝对亏损清仓",
                triggered=True,
                action="清仓",
                reduce_ratio=1.0,
                reason=f"亏损{abs(current_profit)*100:.1f}% ≥ 清仓止损线{clear_stop_loss*100:.1f}%",
                market_blocked=False
            )
        
        return DecisionResult(
            priority=1,
            check_item="绝对亏损清仓",
            triggered=False,
            action="持有",
            reduce_ratio=0.0,
            reason=f"亏损{abs(current_profit)*100:.1f}% < 清仓止损线{clear_stop_loss*100:.1f}%"
        )
    
    def check_priority_2_absolute_loss_half(
        self,
        current_profit: float,
        clear_stop_loss: float,
        half_stop_loss: float
    ) -> DecisionResult:
        """
        优先级2：绝对亏损减半
        条件：亏损≥减半止损比例（未达清仓线）
        操作：减半
        大盘影响：不受任何影响
        """
        # 确保未达清仓线
        if current_profit <= -clear_stop_loss:
            return DecisionResult(
                priority=2,
                check_item="绝对亏损减半",
                triggered=False,
                action="持有",
                reduce_ratio=0.0,
                reason="已达到清仓线，优先执行清仓"
            )
        
        if current_profit <= -half_stop_loss:
            return DecisionResult(
                priority=2,
                check_item="绝对亏损减半",
                triggered=True,
                action="减半",
                reduce_ratio=0.5,
                reason=f"亏损{abs(current_profit)*100:.1f}% ≥ 减半止损线{half_stop_loss*100:.1f}%",
                market_blocked=False
            )
        
        return DecisionResult(
            priority=2,
            check_item="绝对亏损减半",
            triggered=False,
            action="持有",
            reduce_ratio=0.0,
            reason=f"亏损{abs(current_profit)*100:.1f}% < 减半止损线{half_stop_loss*100:.1f}%"
        )
    
    def check_priority_3_extreme_panic(
        self,
        market_status: MarketStatus
    ) -> DecisionResult:
        """
        优先级3：极端恐慌
        条件：大盘处于极端恐慌状态
        操作：禁止卖出
        """
        if market_status == MarketStatus.EXTREME_PANIC:
            return DecisionResult(
                priority=3,
                check_item="极端恐慌",
                triggered=True,
                action="禁止卖出",
                reduce_ratio=0.0,
                reason="大盘处于极端恐慌状态，禁止任何卖出操作",
                market_blocked=True
            )
        
        return DecisionResult(
            priority=3,
            check_item="极端恐慌",
            triggered=False,
            action="继续检查",
            reduce_ratio=0.0,
            reason="大盘未处于极端恐慌状态"
        )
    
    def check_priority_4_panic_zone(
        self,
        market_status: MarketStatus,
        df: pd.DataFrame,
        current_position: float,
        clear_history: List[dict]
    ) -> DecisionResult:
        """
        优先级4：恐慌区
        条件：大盘处于恐慌区状态
        操作：禁止清仓（最多3成）
        """
        if market_status != MarketStatus.PANIC:
            return DecisionResult(
                priority=4,
                check_item="恐慌区",
                triggered=False,
                action="继续检查",
                reduce_ratio=0.0,
                reason="大盘未处于恐慌区"
            )
        
        # 运行恐慌区自查清单
        checklist_result = self.panic_checker.run_checklist(
            df, current_position, clear_history
        )
        
        if not checklist_result['can_clear']:
            return DecisionResult(
                priority=4,
                check_item="恐慌区",
                triggered=True,
                action="禁止清仓",
                reduce_ratio=0.0,
                reason=f"恐慌区且自查未通过：{checklist_result['recommendation']}",
                market_blocked=True
            )
        
        # 可以减仓，但有限制
        max_reduce = checklist_result['max_reduce_ratio']
        return DecisionResult(
            priority=4,
            check_item="恐慌区",
            triggered=True,
            action=f"限制减仓（最多{max_reduce*100:.0f}%）",
            reduce_ratio=max_reduce,
            reason=f"恐慌区：{checklist_result['recommendation']}",
            market_blocked=False
        )
    
    def make_decision(
        self,
        stock_code: str,
        stock_name: str,
        buy_price: float,
        current_price: float,
        buy_date: str,
        current_date: str,
        df: pd.DataFrame,
        market_status: MarketStatus,
        current_position: float = 1.0,
        clear_history: List[dict] = None,
        historical_max_profit: float = None
    ) -> Dict:
        """
        执行完整的决策流程
        
        Returns:
            {
                'final_decision': DecisionResult,      # 最终决策
                'all_checks': List[DecisionResult],    # 所有检查项
                'stop_loss_params': Tuple[float, float], # 止损参数
            }
        """
        if clear_history is None:
            clear_history = []
        
        # 获取止损参数
        clear_stop_loss, half_stop_loss = self.get_stop_loss_params(
            stock_code, stock_name, df
        )
        
        # 计算当前浮盈
        current_profit = calculate_current_profit(current_price, buy_price)
        
        all_checks = []
        final_decision = None
        
        # 优先级1：绝对亏损清仓
        result = self.check_priority_1_absolute_loss_clear(
            current_profit, clear_stop_loss
        )
        all_checks.append(result)
        if result.triggered:
            final_decision = result
        
        # 优先级2：绝对亏损减半
        if final_decision is None:
            result = self.check_priority_2_absolute_loss_half(
                current_profit, clear_stop_loss, half_stop_loss
            )
            all_checks.append(result)
            if result.triggered:
                final_decision = result
        
        # 优先级3：极端恐慌
        if final_decision is None:
            result = self.check_priority_3_extreme_panic(market_status)
            all_checks.append(result)
            if result.triggered and result.market_blocked:
                final_decision = result
        
        # 优先级4：恐慌区
        if final_decision is None:
            result = self.check_priority_4_panic_zone(
                market_status, df, current_position, clear_history
            )
            all_checks.append(result)
            if result.triggered and result.market_blocked:
                final_decision = result
        
        # 优先级5-6：利润保护模式
        if final_decision is None and current_profit >= 0.10:
            profit_result = self.profit_protect.analyze(
                current_price, buy_price, df, market_status, historical_max_profit
            )
            
            if profit_result['clear_triggered']:
                final_decision = DecisionResult(
                    priority=5,
                    check_item="利润模式清仓",
                    triggered=True,
                    action="清仓",
                    reduce_ratio=1.0,
                    reason=profit_result['reason']
                )
                all_checks.append(final_decision)
            elif profit_result['half_triggered']:
                final_decision = DecisionResult(
                    priority=6,
                    check_item="利润模式减半",
                    triggered=True,
                    action="减半",
                    reduce_ratio=0.5,
                    reason=profit_result['reason']
                )
                all_checks.append(final_decision)
        
        # 优先级7-8：本金保护模式
        if final_decision is None and current_profit < 0.10:
            principal_result = self.principal_protect.analyze(
                current_price, buy_price, df, market_status
            )
            
            if principal_result['ma5_half_triggered']:
                final_decision = DecisionResult(
                    priority=7,
                    check_item="本金模式5日线",
                    triggered=True,
                    action="减半",
                    reduce_ratio=principal_result['reduce_ratio'],
                    reason=principal_result['reason']
                )
                all_checks.append(final_decision)
            elif principal_result['ma10_clear_triggered']:
                final_decision = DecisionResult(
                    priority=8,
                    check_item="本金模式10日线",
                    triggered=True,
                    action="清仓",
                    reduce_ratio=1.0,
                    reason=principal_result['reason']
                )
                all_checks.append(final_decision)
        
        # 优先级9：时间止损
        if final_decision is None:
            time_result = self.time_stop.analyze(
                buy_date, current_date, current_profit, 
                clear_stop_loss, market_status
            )
            
            if time_result['time_stop_triggered']:
                final_decision = DecisionResult(
                    priority=9,
                    check_item="时间止损",
                    triggered=True,
                    action="清仓",
                    reduce_ratio=1.0,
                    reason=time_result['reason']
                )
                all_checks.append(final_decision)
        
        # 默认：持有
        if final_decision is None:
            final_decision = DecisionResult(
                priority=0,
                check_item="持有",
                triggered=False,
                action="持有",
                reduce_ratio=0.0,
                reason="以上条件均不满足，继续持有"
            )
            all_checks.append(final_decision)
        
        return {
            'final_decision': final_decision,
            'all_checks': all_checks,
            'stop_loss_params': (clear_stop_loss, half_stop_loss),
            'current_profit': current_profit,
        }
    
    def format_full_report(self, result: Dict, stock_code: str, stock_name: str) -> str:
        """格式化完整决策报告"""
        lines = []
        lines.append("=" * 70)
        lines.append(f"📊 止损决策报告 - {stock_name}({stock_code})")
        lines.append("=" * 70)
        
        # 止损参数
        clear_sl, half_sl = result['stop_loss_params']
        lines.append(f"\n止损参数:")
        lines.append(f"  清仓止损线: {clear_sl*100:.1f}%")
        lines.append(f"  减半止损线: {half_sl*100:.1f}%")
        lines.append(f"  当前浮盈: {result['current_profit']*100:.1f}%")
        
        # 所有检查项
        lines.append(f"\n决策流程（按优先级1→9检查）:")
        lines.append("-" * 70)
        for check in result['all_checks']:
            status = "✅ 触发" if check.triggered else "⏭️ 跳过"
            lines.append(f"优先级{check.priority}: {check.check_item} - {status}")
            lines.append(f"  操作: {check.action}")
            if check.reduce_ratio > 0:
                lines.append(f"  减仓: {check.reduce_ratio*100:.0f}%")
            lines.append(f"  原因: {check.reason}")
            lines.append("")
        
        # 最终决策
        final = result['final_decision']
        lines.append("=" * 70)
        lines.append(f"🎯 最终决策: {final.action}")
        if final.reduce_ratio > 0:
            lines.append(f"   减仓比例: {final.reduce_ratio*100:.0f}%")
        lines.append(f"   触发条件: 优先级{final.priority} - {final.check_item}")
        lines.append(f"   原因: {final.reason}")
        lines.append("=" * 70)
        
        return "\n".join(lines)
