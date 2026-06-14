#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略优化器演示脚本
展示策略优化器的功能和效果
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills', 'scripts'))

from datetime import datetime
import json


def print_header():
    """打印标题"""
    print("="*80)
    print("策略优化器 - 演示")
    print("="*80)
    print()
    print(f"演示时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()


def print_strategy_list():
    """打印策略列表"""
    strategies = [
        ("ma-bullish-strategy", "均线多头排列策略", "v1.2.0"),
        ("limit-up-analysis", "涨停板连板分析", "v1.1.0"),
        ("earnings-surprise-strategy", "财报超预期策略", "v1.0.0"),
        ("volume-retrace-ma-strategy", "缩量回踩均线策略", "v1.0.0"),
        ("limit-up-retrace-strategy", "涨停首次回调策略", "v1.0.0"),
        ("macd-divergence-strategy", "MACD底背离策略", "v1.0.0"),
        ("morning-star-strategy", "早晨之星形态策略", "v1.0.0"),
        ("breakout-high-strategy", "突破前期高点策略", "v1.0.0"),
        ("rsi-oversold-strategy", "RSI超卖反弹策略", "v1.0.0"),
        ("volume-extreme-strategy", "成交量地量见底策略", "v1.0.0"),
        ("gap-fill-strategy", "缺口回补策略", "v1.0.0"),
    ]
    
    print("="*80)
    print("可优化的策略列表 (11个)")
    print("="*80)
    print()
    
    for i, (name, desc, version) in enumerate(strategies, 1):
        print(f"{i:2d}. {desc}")
        print(f"    代码: {name}")
        print(f"    版本: {version}")
        print()
    
    print("="*80)
    print()


def print_optimization_process():
    """打印优化过程示例"""
    print("="*80)
    print("优化过程示例 - ma-bullish-strategy")
    print("="*80)
    print()
    
    print("步骤1: 加载回测数据")
    print("  ✅ 加载100条模拟交易记录")
    print()
    
    print("步骤2: 分析当前表现")
    print("  📊 胜率: 63.00%")
    print("  📊 夏普比率: 5.17")
    print("  📊 最大回撤: 135.87%")
    print("  📊 盈亏比: 1.33")
    print()
    
    print("步骤3: 执行参数优化 (网格搜索)")
    print("  🔍 生成81个参数组合")
    print("  📈 进度: 10/81")
    print("  📈 进度: 20/81")
    print("  📈 进度: 30/81")
    print("  ...")
    print("  📈 进度: 80/81")
    print("  ✅ 最佳得分: 56.50")
    print()
    
    print("步骤4: 优化参数建议")
    print("  📋 ma_short: 3 (原5)")
    print("  📋 ma_mid: 8 (原10)")
    print("  📋 ma_long: 15 (原20)")
    print("  📋 volume_ratio_min: 1.0 (原1.2)")
    print()
    
    print("步骤5: 验证优化效果")
    print("  ✅ 优化结果已保存")
    print()
    
    print("="*80)
    print()


def print_optimization_results():
    """打印优化结果摘要"""
    print("="*80)
    print("优化结果摘要")
    print("="*80)
    print()
    
    results = [
        ("ma-bullish-strategy", "✅", "81", "56.50"),
        ("limit-up-analysis", "❌", "-", "无配置"),
        ("earnings-surprise-strategy", "✅", "100", "56.50"),
        ("volume-retrace-ma-strategy", "❌", "-", "无配置"),
        ("limit-up-retrace-strategy", "❌", "-", "无配置"),
        ("macd-divergence-strategy", "✅", "81", "61.50"),
        ("morning-star-strategy", "✅", "27", "56.50"),
        ("breakout-high-strategy", "✅", "64", "56.50"),
        ("rsi-oversold-strategy", "✅", "27", "61.50"),
        ("volume-extreme-strategy", "✅", "48", "66.50"),
        ("gap-fill-strategy", "✅", "64", "56.50"),
    ]
    
    print(f"{'策略名称':<35} {'状态':<6} {'组合数':<8} {'最佳得分':<10}")
    print("-"*80)
    
    for name, status, combos, score in results:
        print(f"{name:<35} {status:<6} {combos:<8} {score:<10}")
    
    print()
    print("统计:")
    success_count = sum(1 for _, s, _, _ in results if s == "✅")
    print(f"  成功优化: {success_count}/11")
    print(f"  缺少配置: {11 - success_count}/11")
    print()
    print("="*80)
    print()


def print_usage():
    """打印使用方法"""
    print("="*80)
    print("使用方法")
    print("="*80)
    print()
    print("1. 优化所有策略:")
    print("   python3 skills/scripts/strategy_optimizer.py --all")
    print()
    print("2. 优化单个策略:")
    print("   python3 skills/scripts/strategy_optimizer.py --strategy ma-bullish-strategy")
    print()
    print("3. 优化评分权重:")
    print("   python3 skills/scripts/strategy_optimizer.py --weights ma-bullish-strategy")
    print()
    print("4. 查看优化结果:")
    print("   cat data/optimized_params/ma-bullish-strategy_optimized.json")
    print()
    print("="*80)
    print()


def print_features():
    """打印功能特性"""
    print("="*80)
    print("功能特性")
    print("="*80)
    print()
    print("📊 性能分析:")
    print("  • 胜率、夏普比率、最大回撤、盈亏比")
    print("  • 综合评分计算")
    print()
    print("🔧 参数优化:")
    print("  • 网格搜索算法")
    print("  • 多参数组合测试")
    print("  • 自动寻找最优参数")
    print()
    print("✅ 效果验证:")
    print("  • 优化前后对比")
    print("  • 改善幅度评估")
    print("  • 优化建议生成")
    print()
    print("📈 权重优化:")
    print("  • 评分权重调整")
    print("  • 多维度平衡")
    print()
    print("="*80)
    print()


def main():
    print_header()
    print_strategy_list()
    print_optimization_process()
    print_optimization_results()
    print_features()
    print_usage()
    
    print("演示完成!")
    print()
    print("注意: 以上数据基于模拟回测数据")
    print("实际使用请确保有真实的回测数据文件")


if __name__ == '__main__':
    main()
