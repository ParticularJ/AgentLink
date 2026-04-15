# skills/scripts/performance_analyzer.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
性能分析器 - 分析策略回测数据
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
import os
import yaml


class PerformanceAnalyzer:
    """策略性能分析器"""
    
    def __init__(self, config: Dict):
        self.config = config
        
    def analyze(self, backtest_data: pd.DataFrame) -> Dict:
        """分析策略表现"""
        if backtest_data.empty:
            return self._empty_analysis()
        
        # 基础指标
        total_trades = len(backtest_data)
        win_trades = len(backtest_data[backtest_data.get('is_win', backtest_data['profit_pct'] > 0)])
        loss_trades = total_trades - win_trades
        
        win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
        
        # 收益指标
        profits = backtest_data['profit_pct'] if 'profit_pct' in backtest_data else backtest_data.get('returns', pd.Series([0]))
        total_return = profits.sum()
        avg_profit = profits.mean()
        
        # 风险指标
        max_drawdown = self._calculate_max_drawdown(profits.cumsum())
        
        # 夏普比率
        sharpe_ratio = self._calculate_sharpe_ratio(profits)
        
        # 盈亏比
        if loss_trades > 0:
            avg_win = profits[profits > 0].mean() if len(profits[profits > 0]) > 0 else 0
            avg_loss = abs(profits[profits < 0].mean()) if len(profits[profits < 0]) > 0 else 1
            profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        else:
            profit_loss_ratio = 0
        
        # 综合评分
        composite_score = self._calculate_composite_score({
            'win_rate': win_rate,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'profit_loss_ratio': profit_loss_ratio,
            'total_return': total_return
        })
        
        return {
            'total_trades': total_trades,
            'win_trades': win_trades,
            'loss_trades': loss_trades,
            'win_rate': round(win_rate, 2),
            'total_return': round(total_return, 2),
            'avg_profit': round(avg_profit, 2),
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'profit_loss_ratio': round(profit_loss_ratio, 2),
            'composite_score': round(composite_score, 2),
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def compare_performances(self, 
                             current: Dict, 
                             optimized: Dict) -> Dict:
        """比较优化前后的表现"""
        improvements = {}
        
        for key in ['win_rate', 'sharpe_ratio', 'profit_loss_ratio']:
            current_val = current.get(key, 0)
            optimized_val = optimized.get(key, 0)
            improvements[key] = round(optimized_val - current_val, 2)
        
        improvements['max_drawdown'] = round(
            current.get('max_drawdown', 0) - optimized.get('max_drawdown', 0), 2
        )
        
        # 判断优化是否有效
        is_improved = (
            improvements['win_rate'] > 0 or
            improvements['sharpe_ratio'] > 0 or
            improvements['max_drawdown'] > 0
        )
        
        return {
            'improvements': improvements,
            'is_improved': is_improved,
            'grade': self._get_improvement_grade(improvements)
        }
    
    def _calculate_max_drawdown(self, equity_curve: pd.Series) -> float:
        """计算最大回撤"""
        if len(equity_curve) == 0:
            return 0
        
        peak = equity_curve.expanding().max()
        drawdown = (equity_curve - peak) / peak * 100
        return abs(drawdown.min())
    
    def _calculate_sharpe_ratio(self, returns: pd.Series) -> float:
        """计算夏普比率"""
        if len(returns) == 0 or returns.std() == 0:
            return 0
        
        return (returns.mean() / returns.std()) * np.sqrt(252)
    
    def _calculate_composite_score(self, metrics: Dict) -> float:
        """计算综合评分"""
        # 加载评估配置
        import yaml
        import os
        
        eval_config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'config', 'evaluation_config.yaml'
        )
        
        if os.path.exists(eval_config_path):
            with open(eval_config_path, 'r', encoding='utf-8') as f:
                eval_config = yaml.safe_load(f)
            weights = eval_config.get('evaluation', {}).get('metrics', {})
        else:
            # 默认权重
            weights = {
                'win_rate': 0.30,
                'sharpe_ratio': 0.25,
                'max_drawdown': 0.20,
                'profit_loss_ratio': 0.15,
                'total_return': 0.10
            }
        
        score = 0
        for name, weight in weights.items():
            value = metrics.get(name, 0)
            
            # 归一化处理
            if name == 'win_rate':
                normalized = min(100, max(0, value)) / 100
            elif name == 'max_drawdown':
                normalized = max(0, 1 - value / 100)
            elif name == 'sharpe_ratio':
                normalized = min(3, max(0, value)) / 3
            elif name == 'profit_loss_ratio':
                normalized = min(3, max(0, value)) / 3
            else:
                normalized = min(100, max(0, value)) / 100
            
            score += normalized * weight * 100
        
        return score
    
    def _get_improvement_grade(self, improvements: Dict) -> str:
        """获取改善等级"""
        total_improvement = (
            improvements.get('win_rate', 0) +
            improvements.get('sharpe_ratio', 0) * 10 +
            improvements.get('max_drawdown', 0)
        )
        
        if total_improvement > 15:
            return "A - 显著改善"
        elif total_improvement > 8:
            return "B - 良好改善"
        elif total_improvement > 0:
            return "C - 轻微改善"
        else:
            return "D - 无改善或恶化"
    
    def _empty_analysis(self) -> Dict:
        """空分析结果"""
        return {
            'total_trades': 0,
            'win_trades': 0,
            'loss_trades': 0,
            'win_rate': 0,
            'total_return': 0,
            'avg_profit': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
            'profit_loss_ratio': 0,
            'composite_score': 0,
            'error': '无回测数据'
        }