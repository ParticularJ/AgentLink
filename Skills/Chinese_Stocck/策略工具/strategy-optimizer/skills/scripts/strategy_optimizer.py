# skills/scripts/strategy_optimizer.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略优化器 - 主模块
分析回测数据并优化策略参数
"""

import os
import sys
import json
import yaml
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# 添加模块路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from param_optimizer import ParamOptimizer
from performance_analyzer import PerformanceAnalyzer
from model_updater import ModelUpdater


class StrategyOptimizer:
    """策略优化器主类"""
    
    def __init__(self):
        self.name = "策略优化器"
        
        # 加载配置
        self.config = self._load_config()
        self.optimization_params = self._load_optimization_params()
        
        # 初始化子模块
        self.param_optimizer = ParamOptimizer(self.config, self.optimization_params)
        self.performance_analyzer = PerformanceAnalyzer(self.config)
        self.model_updater = ModelUpdater(self.config)
        
        # 策略列表
        self.strategies = self.config['optimizer']['strategies']
        
    def _load_config(self) -> Dict:
        """加载配置文件"""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'config', 'optimizer_config.yaml'
        )
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _load_optimization_params(self) -> Dict:
        """加载优化参数配置"""
        params_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'config', 'optimization_params.yaml'
        )
        with open(params_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def optimize_strategy(self, strategy_name: str) -> Dict:
        """优化单个策略"""
        print(f"\n开始优化策略: {strategy_name}")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)
        
        # 1. 获取策略回测数据
        backtest_data = self._get_backtest_data(strategy_name)
        
        if backtest_data is None or backtest_data.empty:
            return {'error': f'未找到{strategy_name}的回测数据'}
        
        # 2. 分析当前表现
        current_performance = self.performance_analyzer.analyze(backtest_data)
        
        print(f"\n当前策略表现:")
        print(f"  胜率: {current_performance.get('win_rate', 0):.2f}%")
        print(f"  夏普比率: {current_performance.get('sharpe_ratio', 0):.2f}")
        print(f"  最大回撤: {current_performance.get('max_drawdown', 0):.2f}%")
        
        # 3. 执行参数优化
        optimized_params = self.param_optimizer.optimize(
            strategy_name, 
            backtest_data,
            current_performance
        )
        
        if not optimized_params:
            return {'error': f'{strategy_name}参数优化失败'}
        
        # 4. 验证优化效果
        validation_result = self.param_optimizer.validate(
            strategy_name,
            optimized_params,
            backtest_data
        )
        
        # 5. 生成优化报告
        report = self._generate_optimization_report(
            strategy_name,
            current_performance,
            optimized_params,
            validation_result
        )
        
        # 6. 保存优化结果
        self._save_optimization_result(strategy_name, {
            'optimized_params': optimized_params,
            'validation': validation_result,
            'report': report,
            'timestamp': datetime.now().isoformat()
        })
        
        return {
            'strategy': strategy_name,
            'current_performance': current_performance,
            'optimized_params': optimized_params,
            'validation': validation_result,
            'report': report
        }
    
    def optimize_all_strategies(self) -> List[Dict]:
        """优化所有策略"""
        results = []
        
        for strategy in self.strategies:
            if not strategy.get('enabled', True):
                continue
            
            result = self.optimize_strategy(strategy['name'])
            results.append(result)
            
            # 输出优化建议
            self._output_optimization_suggestion(result)
        
        # 生成综合报告
        self._generate_comprehensive_report(results)
        
        return results
    
    def optimize_scoring_weights(self, strategy_name: str) -> Dict:
        """优化评分权重"""
        print(f"\n优化{strategy_name}的评分权重")
        
        # 获取回测数据
        backtest_data = self._get_backtest_data(strategy_name)
        
        if not backtest_data:
            return {'error': '未找到回测数据'}
        
        # 优化权重
        optimized_weights = self.param_optimizer.optimize_weights(
            strategy_name, backtest_data
        )
        
        return {
            'strategy': strategy_name,
            'original_weights': self._get_current_weights(strategy_name),
            'optimized_weights': optimized_weights
        }
    
    def _get_backtest_data(self, strategy_name: str) -> Optional[pd.DataFrame]:
        """获取策略回测数据"""
        data_path = os.path.join(
            self.config['data_storage']['backtest_results'],
            f"{strategy_name}_backtest.csv"
        )
        
        if os.path.exists(data_path):
            return pd.read_csv(data_path)
        
        # 尝试从策略目录获取
        strategy_config = next(
            (s for s in self.strategies if s['name'] == strategy_name), 
            None
        )
        
        if strategy_config:
            backtest_path = os.path.join(
                strategy_config['path'],
                'data', 'backtest_results.csv'
            )
            if os.path.exists(backtest_path):
                return pd.read_csv(backtest_path)
        
        # 生成模拟回测数据（演示用）
        return self._generate_mock_backtest_data(strategy_name)
    
    def _generate_mock_backtest_data(self, strategy_name: str) -> pd.DataFrame:
        """生成模拟回测数据（用于演示）"""
        np.random.seed(42)
        
        n_trades = 100
        dates = pd.date_range(start='2024-01-01', periods=n_trades, freq='D')
        
        # 模拟交易数据
        data = {
            'date': dates,
            'signal': np.random.choice([1, 0], n_trades, p=[0.3, 0.7]),
            'entry_price': np.random.uniform(10, 100, n_trades),
            'exit_price': np.random.uniform(10, 110, n_trades),
            'profit_pct': np.random.normal(2, 8, n_trades),
            'holding_days': np.random.randint(1, 20, n_trades)
        }
        
        df = pd.DataFrame(data)
        
        # 确保胜率在合理范围
        df['is_win'] = df['profit_pct'] > 0
        
        return df
    
    def _get_current_weights(self, strategy_name: str) -> Dict:
        """获取当前评分权重"""
        weights_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            strategy_name, 'config', 'scoring_weights.yaml'
        )
        
        if os.path.exists(weights_path):
            with open(weights_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('weights', {})
        
        return {}
    
    def _generate_optimization_report(self, strategy_name: str,
                                       current: Dict,
                                       optimized: Dict,
                                       validation: Dict) -> str:
        """生成优化报告"""
        report = []
        report.append("=" * 70)
        report.append(f"策略优化报告 - {strategy_name}")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 70)
        
        report.append("\n【当前策略表现】")
        report.append(f"  胜率: {current.get('win_rate', 0):.2f}%")
        report.append(f"  夏普比率: {current.get('sharpe_ratio', 0):.2f}")
        report.append(f"  最大回撤: {current.get('max_drawdown', 0):.2f}%")
        report.append(f"  盈亏比: {current.get('profit_loss_ratio', 0):.2f}")
        
        report.append("\n【优化参数建议】")
        for param, value in optimized.items():
            report.append(f"  {param}: {value}")
        
        report.append("\n【预期改善效果】")
        report.append(f"  胜率提升: +{validation.get('win_rate_improvement', 0):.2f}%")
        report.append(f"  夏普提升: +{validation.get('sharpe_improvement', 0):.2f}")
        report.append(f"  回撤降低: -{validation.get('drawdown_reduction', 0):.2f}%")
        
        report.append("\n【优化建议】")
        for suggestion in validation.get('suggestions', []):
            report.append(f"  • {suggestion}")
        
        report.append("\n" + "=" * 70)
        
        return "\n".join(report)
    
    def _generate_comprehensive_report(self, results: List[Dict]) -> str:
        """生成综合优化报告"""
        report = []
        report.append("=" * 80)
        report.append("策略综合优化报告")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)
        
        report.append("\n【各策略优化摘要】")
        report.append("-" * 60)
        
        for result in results:
            if 'error' in result:
                continue
            
            strategy = result.get('strategy', 'Unknown')
            current = result.get('current_performance', {})
            validation = result.get('validation', {})
            
            report.append(f"\n{strategy}:")
            report.append(f"  当前胜率: {current.get('win_rate', 0):.2f}%")
            report.append(f"  优化后预期胜率: {current.get('win_rate', 0) + validation.get('win_rate_improvement', 0):.2f}%")
            report.append(f"  改善幅度: +{validation.get('win_rate_improvement', 0):.2f}%")
        
        report.append("\n" + "=" * 80)
        
        return "\n".join(report)
    
    def _output_optimization_suggestion(self, result: Dict):
        """输出优化建议"""
        if 'error' in result:
            print(f"\n❌ {result['error']}")
            return
        
        print(f"\n✅ {result['strategy']} 优化完成")
        print(f"   胜率改善: +{result['validation'].get('win_rate_improvement', 0):.2f}%")
        print(f"   优化参数: {len(result['optimized_params'])}个")
    
    def _save_optimization_result(self, strategy_name: str, data: Dict):
        """保存优化结果"""
        save_dir = self.config['data_storage']['optimized_params']
        os.makedirs(save_dir, exist_ok=True)
        
        file_path = os.path.join(save_dir, f"{strategy_name}_optimized.json")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"优化结果已保存: {file_path}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='策略优化器')
    parser.add_argument('--strategy', type=str, help='优化指定策略')
    parser.add_argument('--all', action='store_true', help='优化所有策略')
    parser.add_argument('--weights', type=str, help='优化评分权重')
    
    args = parser.parse_args()
    
    optimizer = StrategyOptimizer()
    
    if args.strategy:
        result = optimizer.optimize_strategy(args.strategy)
        
        if 'report' in result:
            print(result['report'])
        else:
            print(f"优化失败: {result.get('error', '未知错误')}")
    
    elif args.all:
        results = optimizer.optimize_all_strategies()
        print(f"\n共优化 {len(results)} 个策略")
    
    elif args.weights:
        result = optimizer.optimize_scoring_weights(args.weights)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()