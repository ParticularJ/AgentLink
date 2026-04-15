#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
突破前期高点策略演示脚本
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills', 'scripts'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def create_mock_breakout_data():
    """创建模拟突破前期高点数据"""
    dates = pd.date_range(end=datetime.now(), periods=70, freq='D')
    
    base_price = 100
    prices = []
    
    # 前60天：震荡整理，形成前期高点
    for i in range(60):
        if i < 30:
            price = base_price + i * 0.3 + np.random.normal(0, 0.5)
        elif i < 50:
            price = 109 - (i - 30) * 0.2 + np.random.normal(0, 0.5)
        else:
            price = 105 + (i - 50) * 0.1 + np.random.normal(0, 0.5)
        prices.append(price)
    
    # 前期高点约为110
    previous_high = max(prices)
    
    # 第61-65天：蓄势整理
    for i in range(5):
        price = 108 + np.random.normal(0, 0.3)
        prices.append(price)
    
    # 第66-70天：突破上涨
    for i in range(5):
        price = 108 + i * 0.8 + np.random.normal(0, 0.3)
        prices.append(price)
    
    # 成交量（突破时放量）
    volumes = []
    for i in range(70):
        if i < 65:
            vol = 1000000 + np.random.normal(0, 100000)
        else:
            vol = 1600000 + np.random.normal(0, 150000)  # 放量
        volumes.append(max(800000, vol))
    
    df = pd.DataFrame({
        'date': dates,
        'open': [p * 0.995 for p in prices],
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.985 for p in prices],
        'close': prices,
        'volume': volumes
    })
    
    return df, previous_high


def analyze_mock_breakout(df, previous_high, stock_code, stock_name):
    """分析模拟数据的突破"""
    # 计算指标
    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA10'] = df['close'].rolling(window=10).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['volume_ma20'] = df['volume'].rolling(window=20).mean()
    
    latest = df.iloc[-1]
    
    # 突破分析
    breakout_pct = (latest['close'] - previous_high) / previous_high * 100
    is_breakout = breakout_pct >= 3.0
    
    # 成交量分析
    volume_ratio = latest['volume'] / latest['volume_ma20'] if latest['volume_ma20'] > 0 else 1
    
    # 趋势分析
    ma_bullish = latest['MA5'] > latest['MA10'] > latest['MA20']
    
    # 评分
    if is_breakout:
        breakout_score = 100 if breakout_pct >= 5 else 85
        volume_score = 100 if volume_ratio >= 2.0 else 85 if volume_ratio >= 1.5 else 70
        trend_score = 100 if ma_bullish else 70
        pullback_score = 90
        
        weights = {
            'breakout': 0.35,
            'volume': 0.25,
            'trend': 0.25,
            'pullback': 0.15
        }
        
        total_score = (
            breakout_score * weights['breakout'] +
            volume_score * weights['volume'] +
            trend_score * weights['trend'] +
            pullback_score * weights['pullback']
        )
        
        signal = '强烈买入' if total_score >= 85 else '买入'
    else:
        total_score = 0
        signal = '无信号'
    
    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'score': round(total_score, 2),
        'signal': signal,
        'current_price': round(latest['close'], 2),
        'previous_high': round(previous_high, 2),
        'breakout_pct': round(breakout_pct, 2),
        'volume_ratio': round(volume_ratio, 2),
        'ma_bullish': ma_bullish,
        'is_breakout': is_breakout
    }


def main():
    print("="*80)
    print("突破前期高点策略 - 模拟数据演示")
    print("="*80)
    print()
    print("创建模拟股票数据（突破60日前期高点）...")
    print()
    
    # 模拟股票
    mock_stocks = [
        ('000001', '平安银行'),
        ('600519', '贵州茅台'),
        ('002594', '比亚迪'),
    ]
    
    results = []
    for code, name in mock_stocks:
        df, previous_high = create_mock_breakout_data()
        result = analyze_mock_breakout(df, previous_high, code, name)
        results.append(result)
    
    # 按得分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    print("="*80)
    print("模拟分析结果")
    print("="*80)
    print()
    
    for i, r in enumerate(results, 1):
        if r['is_breakout']:
            emoji = '🔥' if r['score'] >= 85 else '✅'
            print(f"{emoji} {i}. {r['stock_name']} ({r['stock_code']})")
            print(f"   综合得分: {r['score']}分 | 信号: {r['signal']}")
            print(f"   当前价: {r['current_price']}元")
            print(f"   前期高点: {r['previous_high']}元")
            print(f"   突破幅度: +{r['breakout_pct']}%")
            print(f"   成交量比: {r['volume_ratio']}倍")
            print(f"   均线多头: {'是' if r['ma_bullish'] else '否'}")
        else:
            print(f"❌ {i}. {r['stock_name']} ({r['stock_code']}) - 未突破前期高点")
        print()
    
    print("="*80)
    print("演示完成")
    print("注意：以上数据为模拟数据，用于展示策略分析功能")
    print("实际使用请运行: python3 skills/scripts/breakout_high_scanner.py --scan")
    print("="*80)


if __name__ == '__main__':
    main()
