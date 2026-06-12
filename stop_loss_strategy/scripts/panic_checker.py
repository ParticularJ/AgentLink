#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
恐慌区自查清单模块
当恐慌区触发、你想清仓时，强制按此清单逐项检查
"""

import pandas as pd
from typing import Dict, List, Tuple
from dataclasses import dataclass
from scripts.atr_calculator import is_below_ma, days_below_ma


@dataclass
class CheckItem:
    """检查项"""
    name: str
    description: str
    condition: str
    action_if_true: str


class PanicZoneChecker:
    """恐慌区自查清单"""
    
    def __init__(self):
        self.checklist = [
            CheckItem(
                name="持续抛压检查",
                description="往回数5天，是否有4天收跌？",
                condition="5天内至少4天收跌",
                action_if_true="说明抛压持续，可减至5成"
            ),
            CheckItem(
                name="仓位检查",
                description="当前仓位是否 >5成？",
                condition="当前仓位 > 50%",
                action_if_true="最多减到5成，保留底仓"
            ),
            CheckItem(
                name="个股相对强度",
                description="个股是否跌破20日线？",
                condition="股价 >= 20日线",
                action_if_true="说明个股相对强势，不该清仓"
            ),
            CheckItem(
                name="技术形态",
                description="个股是否放量破10日线？",
                condition="未放量破10日线",
                action_if_true="技术形态未走坏，不该清仓"
            ),
            CheckItem(
                name="历史经验",
                description="前两次清仓后次日都大涨了？",
                condition="前两次清仓后次日大涨",
                action_if_true="这次只减一半，留一半防踏空"
            ),
        ]
    
    def check_continuous_decline(self, df: pd.DataFrame, days: int = 5, threshold: int = 4) -> Tuple[bool, str]:
        """
        检查持续抛压：往回数N天，是否有M天收跌
        
        Args:
            df: DataFrame with 'close' column
            days: 检查天数
            threshold: 收跌天数阈值
        
        Returns:
            (是否触发, 描述)
        """
        if len(df) < days + 1:
            return False, "数据不足"
        
        recent = df.iloc[-days:].copy()
        recent['prev_close'] = recent['close'].shift(1)
        recent['decline'] = recent['close'] < recent['prev_close']
        
        decline_days = recent['decline'].sum()
        
        if decline_days >= threshold:
            return True, f"最近{days}天有{decline_days}天收跌（≥{threshold}天）"
        
        return False, f"最近{days}天仅{decline_days}天收跌（<{threshold}天）"
    
    def check_position_ratio(self, current_position: float, threshold: float = 0.5) -> Tuple[bool, str]:
        """
        检查仓位是否超过阈值
        
        Args:
            current_position: 当前仓位比例 (0-1)
            threshold: 阈值
        
        Returns:
            (是否超过, 描述)
        """
        if current_position > threshold:
            return True, f"当前仓位{current_position*100:.0f}% > {threshold*100:.0f}%"
        return False, f"当前仓位{current_position*100:.0f}% ≤ {threshold*100:.0f}%"
    
    def check_above_ma20(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        检查个股是否在20日线上方（相对强势）
        
        Returns:
            (是否在上方, 描述)
        """
        if is_below_ma(df, 20):
            return False, "股价跌破20日线"
        return True, "股价在20日均线上方（相对强势）"
    
    def check_volume_breakdown(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        检查是否放量破10日线
        
        Returns:
            (是否放量破线, 描述)
        """
        if len(df) < 2:
            return False, "数据不足"
        
        # 检查是否跌破10日线
        if not is_below_ma(df, 10):
            return False, "未跌破10日线"
        
        # 检查是否放量
        if 'volume' not in df.columns:
            return False, "无成交量数据"
        
        current_volume = df['volume'].iloc[-1]
        volume_ma5 = df['volume'].iloc[-5:].mean()
        
        if volume_ma5 > 0 and current_volume > volume_ma5 * 1.5:
            return True, f"放量{current_volume/volume_ma5:.1f}倍跌破10日线"
        
        return False, f"缩量跌破10日线（{current_volume/volume_ma5:.1f}倍）"
    
    def check_previous_clear_history(
        self, 
        clear_history: List[dict]
    ) -> Tuple[bool, str]:
        """
        检查前两次清仓后次日是否大涨
        
        Args:
            clear_history: 清仓历史记录列表
                [{date: str, next_day_change: float}, ...]
        
        Returns:
            (是否大涨, 描述)
        """
        if len(clear_history) < 2:
            return False, "清仓历史不足2次"
        
        # 取最近两次
        recent_two = clear_history[-2:]
        big_rise_count = sum(1 for h in recent_two if h.get('next_day_change', 0) > 0.03)
        
        if big_rise_count >= 2:
            return True, f"前两次清仓后次日均大涨（>{big_rise_count}次涨幅>3%）"
        
        return False, f"前两次清仓后次日未都大涨"
    
    def run_checklist(
        self,
        df: pd.DataFrame,
        current_position: float,
        clear_history: List[dict] = None
    ) -> Dict:
        """
        运行完整的恐慌区自查清单
        
        Returns:
            {
                'can_clear': bool,           # 是否可以清仓
                'max_reduce_ratio': float,   # 最大减仓比例
                'recommendation': str,       # 建议操作
                'details': List[dict],       # 每项检查结果
            }
        """
        if clear_history is None:
            clear_history = []
        
        results = {
            'can_clear': True,
            'max_reduce_ratio': 1.0,  # 默认可以全部减仓
            'recommendation': '可以清仓',
            'details': [],
        }
        
        # 检查1：持续抛压
        has_pressure, pressure_desc = self.check_continuous_decline(df)
        results['details'].append({
            'item': '持续抛压检查',
            'passed': not has_pressure,  # 通过 = 没有持续抛压
            'description': pressure_desc,
            'suggestion': '抛压持续，可减至5成' if has_pressure else '无持续抛压',
        })
        
        if has_pressure:
            results['max_reduce_ratio'] = min(results['max_reduce_ratio'], 0.5)
        
        # 检查2：仓位检查
        over_position, position_desc = self.check_position_ratio(current_position)
        results['details'].append({
            'item': '仓位检查',
            'passed': not over_position,
            'description': position_desc,
            'suggestion': '最多减到5成，保留底仓' if over_position else '仓位适中',
        })
        
        if over_position:
            results['max_reduce_ratio'] = min(results['max_reduce_ratio'], 0.5)
        
        # 检查3：个股相对强度
        above_ma20, ma20_desc = self.check_above_ma20(df)
        results['details'].append({
            'item': '个股相对强度',
            'passed': above_ma20,
            'description': ma20_desc,
            'suggestion': '个股相对强势，不该清仓' if above_ma20 else '个股跌破20日线',
        })
        
        if above_ma20:
            results['can_clear'] = False
            results['recommendation'] = '个股相对强势，建议持有'
        
        # 检查4：技术形态
        volume_breakdown, volume_desc = self.check_volume_breakdown(df)
        results['details'].append({
            'item': '技术形态',
            'passed': not volume_breakdown,
            'description': volume_desc,
            'suggestion': '技术形态未走坏，不该清仓' if not volume_breakdown else '放量破线，注意风险',
        })
        
        if not volume_breakdown and not above_ma20:
            results['can_clear'] = False
            results['recommendation'] = '技术形态未走坏，建议持有'
        
        # 检查5：历史经验
        history_rise, history_desc = self.check_previous_clear_history(clear_history)
        results['details'].append({
            'item': '历史经验',
            'passed': not history_rise,
            'description': history_desc,
            'suggestion': '这次只减一半，留一半防踏空' if history_rise else '无历史踏空记录',
        })
        
        if history_rise:
            results['max_reduce_ratio'] = min(results['max_reduce_ratio'], 0.5)
        
        # 最终建议
        if not results['can_clear']:
            results['recommendation'] = '恐慌区自查未通过，禁止清仓，建议持有'
        elif results['max_reduce_ratio'] < 1.0:
            results['recommendation'] = f"恐慌区限制：最多减仓{results['max_reduce_ratio']*100:.0f}%"
        
        return results
    
    def format_report(self, results: Dict) -> str:
        """格式化恐慌区自查报告"""
        lines = []
        lines.append("=" * 60)
        lines.append("📋 恐慌区自查清单")
        lines.append("=" * 60)
        lines.append(f"是否可以清仓: {'✅ 是' if results['can_clear'] else '❌ 否'}")
        lines.append(f"最大减仓比例: {results['max_reduce_ratio']*100:.0f}%")
        lines.append(f"建议操作: {results['recommendation']}")
        lines.append("-" * 60)
        
        for detail in results['details']:
            status = "✅" if detail['passed'] else "⚠️"
            lines.append(f"{status} {detail['item']}")
            lines.append(f"   结果: {detail['description']}")
            lines.append(f"   建议: {detail['suggestion']}")
            lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)
