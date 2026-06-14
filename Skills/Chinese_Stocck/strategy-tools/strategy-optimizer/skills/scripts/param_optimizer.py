# skills/scripts/param_optimizer.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
参数优化器 - 网格搜索优化策略参数
"""

import os
import sys
import itertools
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime


class ParamOptimizer:
    """参数优化器"""
    
    def __init__(self, config: Dict, optimization_params: Dict):
        self.config = config
        self.optimization_params = optimization_params
        
    def optimize(self, strategy_name: str, 
                 backtest_data: pd.DataFrame,
                 current_performance: Dict) -> Dict:
        """执行参数优化"""
        print(f"\n执行{strategy_name}参数优化...")
        
        # 获取可优化参数
        params_config = self._get_params_config(strategy_name)
        
        if not params_config:
            print(f"  未找到{strategy_name}的优化参数配置")
            return {}
        
        # 生成参数组合
        param_combinations = self._generate_param_combinations(params_config)
        
        print(f"  生成{len(param_combinations)}个参数组合")
        
        # 评估每个参数组合
        best_params = None
        best_score = -float('inf')
        results = []
        
        for i, params in enumerate(param_combinations):
            # 模拟使用该参数的表现
            score = self._evaluate_params(
                strategy_name, params, backtest_data
            )
            
            results.append({
                'params': params,
                'score': score
            })
            
            if score > best_score:
                best_score = score
                best_params = params
            
            if (i + 1) % 10 == 0:
                print(f"  进度: {i+1}/{len(param_combinations)}")
        
        print(f"  最佳得分: {best_score:.2f}")
        
        return best_params
    
    def optimize_weights(self, strategy_name: str,
                         backtest_data: pd.DataFrame) -> Dict:
        """优化评分权重"""
        print(f"\n优化{strategy_name}的评分权重...")
        
        # 获取权重配置
        weights_config = self.optimization_params.get('scoring_weights', {})
        strategy_weights = weights_config.get('strategies', {}).get(strategy_name, {})
        
        if not strategy_weights:
            print(f"  未找到{strategy_name}的权重配置")
            return {}
        
        # 生成权重组合
        weight_combinations = self._generate_weight_combinations(strategy_weights)
        
        print(f"  生成{len(weight_combinations)}个权重组合")
        
        # 评估每个权重组合
        best_weights = None
        best_score = -float('inf')
        
        for weights in weight_combinations:
            score = self._evaluate_weights(
                strategy_name, weights, backtest_data
            )
            
            if score > best_score:
                best_score = score
                best_weights = weights
        
        print(f"  最佳权重得分: {best_score:.2f}")
        
        return best_weights
    
    def validate(self, strategy_name: str,
                 optimized_params: Dict,
                 backtest_data: pd.DataFrame) -> Dict:
        """验证优化效果"""
        print(f"\n验证{strategy_name}优化效果...")
        
        # 获取当前参数配置
        current_params = self._get_current_params(strategy_name)
        
        if not current_params:
            return {
                'win_rate_improvement': 0,
                'sharpe_improvement': 0,
                'drawdown_reduction': 0,
                'suggestions': ['无法验证，缺少当前参数配置']
            }
        
        # 计算改善幅度
        current_score = self._evaluate_params(
            strategy_name, current_params, backtest_data
        )
        optimized_score = self._evaluate_params(
            strategy_name, optimized_params, backtest_data
        )
        
        improvement = optimized_score - current_score
        
        # 生成建议
        suggestions = []
        
        if improvement > 10:
            suggestions.append("优化效果显著，建议立即应用新参数")
        elif improvement > 5:
            suggestions.append("优化效果良好，建议在模拟盘验证后应用")
        elif improvement > 0:
            suggestions.append("优化效果有限，建议继续优化或保持原参数")
        else:
            suggestions.append("优化效果不佳，建议检查参数范围或增加数据量")
        
        return {
            'win_rate_improvement': round(improvement * 0.5, 2),  # 模拟值
            'sharpe_improvement': round(improvement * 0.05, 2),
            'drawdown_reduction': round(improvement * 0.3, 2),
            'suggestions': suggestions
        }
    
    def _get_params_config(self, strategy_name: str) -> Dict:
        """获取策略的参数配置"""
        strategies = self.optimization_params.get('strategies', {})
        return strategies.get(strategy_name, {}).get('parameters', {})
    
    def _get_current_params(self, strategy_name: str) -> Dict:
        """获取当前参数配置"""
        params_config = self._get_params_config(strategy_name)
        
        current_params = {}
        for param_name, param_config in params_config.items():
            current_params[param_name] = param_config.get('default')
        
        return current_params
    
    def _generate_param_combinations(self, params_config: Dict) -> List[Dict]:
        """生成参数组合"""
        param_names = []
        param_values = []
        
        for name, config in params_config.items():
            param_names.append(name)
            param_values.append(config.get('range', []))
        
        # 限制组合数量
        max_combinations = self.config['optimizer']['algorithm']['max_iterations']
        
        combinations = []
        for values in itertools.product(*param_values):
            combination = dict(zip(param_names, values))
            combinations.append(combination)
            
            if len(combinations) >= max_combinations:
                break
        
        return combinations
    
    def _generate_weight_combinations(self, weights_config: Dict) -> List[Dict]:
        """生成权重组合"""
        weight_names = []
        weight_ranges = []
        
        for name, config in weights_config.items():
            weight_names.append(name)
            weight_ranges.append(config.get('range', []))
        
        combinations = []
        for values in itertools.product(*weight_ranges):
            # 确保权重和为1
            total = sum(values)
            if abs(total - 1.0) < 0.01:
                combination = dict(zip(weight_names, values))
                combinations.append(combination)
        
        return combinations
    
    def _evaluate_params(self, strategy_name: str,
                         params: Dict,
                         backtest_data: pd.DataFrame) -> float:
        """评估参数组合的表现"""
        # 模拟策略表现
        # 实际应用中应使用真实回测引擎
        
        base_score = 50
        
        # 根据参数合理性加分
        for param_name, param_value in params.items():
            if 'ratio' in param_name and 0.4 <= param_value <= 0.7:
                base_score += 5
            elif 'threshold' in param_name and 20 <= param_value <= 40:
                base_score += 5
        
        # 根据回测数据调整
        if len(backtest_data) > 0:
            win_rate = backtest_data['is_win'].mean() * 100 if 'is_win' in backtest_data else 50
            base_score += (win_rate - 50) * 0.5
        
        return min(100, max(0, base_score))
    
    def _evaluate_weights(self, strategy_name: str,
                          weights: Dict,
                          backtest_data: pd.DataFrame) -> float:
        """评估权重组合的表现"""
        # 模拟权重效果
        base_score = 50
        
        # 检查权重合理性
        for weight_name, weight_value in weights.items():
            if 0.1 <= weight_value <= 0.4:
                base_score += 3
        
        return min(100, base_score)