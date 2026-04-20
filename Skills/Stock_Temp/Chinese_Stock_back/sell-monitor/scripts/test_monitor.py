#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 sell-monitor 的核心逻辑
"""

import sys
import os

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitor import (
    calculate_stop_loss_action,
    calculate_profit_take_action,
    calculate_drawdown_action,
    analyze_position,
    STOP_LOSS_CONFIG
)


def test_stop_loss():
    """测试止损逻辑"""
    print("=" * 60)
    print("测试 1: 止损逻辑")
    print("=" * 60)
    
    test_cases = [
        ('breakout_high', -8, True, "激进策略 -8% 应止损"),
        ('breakout_high', -5, False, "激进策略 -5% 不应止损"),
        ('ma_bullish', -6, True, "稳健策略 -6% 应止损"),
        ('ma_bullish', -3, False, "稳健策略 -3% 不应止损"),
        ('macd_divergence', -4, True, "保守策略 -4% 应止损"),
        ('macd_divergence', -2, False, "保守策略 -2% 不应止损"),
        ('a_stock_1430', -3, True, "超短策略 -3% 应止损"),
        ('a_stock_1430', -1, False, "超短策略 -1% 不应止损"),
    ]
    
    for buy_reason, profit_pct, expected, desc in test_cases:
        result, msg = calculate_stop_loss_action(profit_pct, buy_reason)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {desc}: {msg if result else '未触发'}")
    
    print()


def test_profit_take():
    """测试固定比例止盈逻辑"""
    print("=" * 60)
    print("测试 2: 固定比例止盈")
    print("=" * 60)
    
    test_cases = [
        ('breakout_high', 15, True, 20, "激进策略 +15% 应减仓20%"),
        ('breakout_high', 35, True, 30, "激进策略 +35% 应减仓30%"),
        ('breakout_high', 45, True, 50, "激进策略 +45% 应减仓50%"),
        ('breakout_high', 10, False, 0, "激进策略 +10% 不应止盈"),
        ('ma_bullish', 12, True, 30, "稳健策略 +12% 应减仓30%"),
        ('ma_bullish', 18, True, 50, "稳健策略 +18% 应减仓50%"),
        ('macd_divergence', 6, True, 20, "保守策略 +6% 应减仓20%"),
        ('macd_divergence', 12, True, 50, "保守策略 +12% 应减仓50%"),
        ('a_stock_1430', 3, True, 50, "超短策略 +3% 应减仓50%"),
    ]
    
    for buy_reason, profit_pct, expected, expected_pct, desc in test_cases:
        result, reduce_pct, msg = calculate_profit_take_action(profit_pct, buy_reason)
        status = "✅" if result == expected and (not expected or reduce_pct == expected_pct) else "❌"
        print(f"  {status} {desc}: {msg if result else '未触发'}")
    
    print()


def test_drawdown():
    """测试动态回撤止盈逻辑"""
    print("=" * 60)
    print("测试 3: 动态回撤止盈")
    print("=" * 60)
    
    # (current_price, high_price, buy_price, buy_reason, expected, desc)
    test_cases = [
        (135, 150, 100, 'breakout_high', True, "激进: 100→150(高点)→135, 回撤10%, 应触发"),
        (140, 150, 100, 'breakout_high', False, "激进: 100→150→140, 回撤6.7%<10%, 不应触发"),
        (120, 150, 100, 'breakout_high', True, "激进: 100→150→120, 回撤20%>10%, 应触发"),
        (92, 100, 100, 'breakout_high', False, "激进: 未盈利, 不应触发"),
        (102, 110, 100, 'breakout_high', False, "激进: 高点盈利仅10%<回撤阈值, 不应触发"),
        (138, 150, 100, 'ma_bullish', True, "稳健: 100→150→138, 回撤8%, 应触发"),
        (142, 150, 100, 'ma_bullish', False, "稳健: 100→150→142, 回撤5.3%<8%, 不应触发"),
        (104, 110, 100, 'macd_divergence', True, "保守: 100→110→104, 回撤5.5%>5%, 应触发"),
        (106, 110, 100, 'macd_divergence', False, "保守: 100→110→106, 回撤3.6%<5%, 不应触发"),
    ]
    
    for current, high, buy, reason, expected, desc in test_cases:
        result, msg = calculate_drawdown_action(current, high, buy, reason)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {desc}")
        if result:
            print(f"      → {msg}")
    
    print()


def test_analyze_position():
    """测试完整的持仓分析"""
    print("=" * 60)
    print("测试 4: 完整持仓分析")
    print("=" * 60)
    
    test_cases = [
        # 止损场景
        {
            'holding': {'code': '000001', 'name': '测试股', 'buy_price': 100, 'buy_reason': 'breakout_high', 'high_price': 105},
            'current_price': 92,
            'expected_signal': '🚨 减仓（止损）',
            'desc': '激进策略亏损8%，应止损'
        },
        # 固定止盈场景
        {
            'holding': {'code': '000002', 'name': '测试股2', 'buy_price': 100, 'buy_reason': 'breakout_high', 'high_price': 130},
            'current_price': 118,
            'expected_signal': '💰 减仓（止盈）',
            'desc': '激进策略盈利18%，应触发15%止盈'
        },
        # 动态回撤止盈场景（注意：当前盈利33% >= 30%，会触发固定止盈，不是回撤止盈）
        {
            'holding': {'code': '000003', 'name': '测试股3', 'buy_price': 100, 'buy_reason': 'breakout_high', 'high_price': 125},
            'current_price': 112,
            'expected_signal': '💰 减仓（回撤止盈）',
            'desc': '激进策略从125回撤到112(10.4%)，当前盈利12%<15%，应触发回撤止盈'
        },
        # 持有场景
        {
            'holding': {'code': '000004', 'name': '测试股4', 'buy_price': 100, 'buy_reason': 'ma_bullish', 'high_price': 108},
            'current_price': 106,
            'expected_signal': '🟢 持有',
            'desc': '稳健策略盈利6%，未达止盈/止损，应持有'
        },
    ]
    
    for case in test_cases:
        result = analyze_position(case['holding'], case['current_price'])
        status = "✅" if result['signal'] == case['expected_signal'] else "❌"
        print(f"  {status} {case['desc']}")
        print(f"      信号: {result['signal']}")
        print(f"      操作: {result['action']}")
        print(f"      理由: {result['reason']}")
        print()


def test_generate_report():
    """测试报告生成"""
    print("=" * 60)
    print("测试 5: 报告生成")
    print("=" * 60)
    
    from monitor import generate_report
    
    # 模拟持仓
    holdings = [
        {'code': '000001', 'name': '平安银行', 'buy_price': 50, 'buy_reason': 'ma_bullish'},
        {'code': '000002', 'name': '万科A', 'buy_price': 80, 'buy_reason': 'macd_divergence'},
    ]
    
    # 模拟推荐
    recommendations = [
        {'code': '000001', 'name': '平安银行', 'source': 'ma_bullish', 'reason': '均线多头排列'},
        {'code': '000063', 'name': '中兴通讯', 'source': 'breakout_high', 'reason': '突破新高'},
    ]
    
    # 模拟信号
    position_signals = {
        '000001': {
            'code': '000001',
            'name': '平安银行',
            'signal': '🟢 持有',
            'action': '继续持有',
            'reduce_pct': 0,
            'current_price': 53,
            'profit_pct': 6.0,
            'reason': '浮盈 6.0%，未达到止盈/止损条件',
            'buy_reason': 'ma_bullish',
        },
        '000002': {
            'code': '000002',
            'name': '万科A',
            'signal': '🚨 减仓（止损）',
            'action': '清仓',
            'reduce_pct': 100,
            'current_price': 77,
            'profit_pct': -3.75,
            'reason': '亏损 3.8% 触及止损线 -3%，建议清仓',
            'buy_reason': 'macd_divergence',
        },
    }
    
    report = generate_report(holdings, recommendations, position_signals, '14:30')
    print(report)
    print()


def test_config():
    """测试配置是否正确"""
    print("=" * 60)
    print("测试 6: 配置检查")
    print("=" * 60)
    
    print("  策略配置:")
    for reason, config in STOP_LOSS_CONFIG.items():
        if reason == 'default':
            continue
        print(f"    • {reason}:")
        print(f"      止损线: {config['stop_loss']}%")
        print(f"      止盈阶梯: {config['profit_levels']}")
        print(f"      回撤阈值: {config.get('max_drawdown', 0.10)*100:.0f}%")
    
    print()


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Sell-Monitor 逻辑测试")
    print("=" * 60 + "\n")
    
    test_config()
    test_stop_loss()
    test_profit_take()
    test_drawdown()
    test_analyze_position()
    test_generate_report()
    
    print("=" * 60)
    print("测试完成!")
    print("=" * 60)
