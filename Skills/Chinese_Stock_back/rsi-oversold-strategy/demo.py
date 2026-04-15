#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RSI超卖反弹策略演示脚本
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills', 'scripts'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def create_mock_rsi_oversold_data():
    """创建模拟RSI超卖数据"""
    dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
    
    base_price = 100
    prices = []
    
    # 前20天：持续下跌
    for i in range(20):
        price = base_price - i * 1.5 + np.random.normal(0, 0.5)
        prices.append(price)
    
    # 后10天：RSI超卖区域震荡
    for i in range(10):
        price = prices[-1] + np.random.normal(0, 1)
        prices.append(price)
    
    # 成交量（下跌放量，超卖缩量）
    volumes = []
    for i in range(30):
        if i < 20:
            vol = 1200000 + np.random.normal(0, 100000)
        else:
            vol = 700000 + np.random.normal(0, 50000)
        volumes.append(max(500000, vol))
    
    df = pd.DataFrame({
        'date': dates,
        'open': [p * 1.005 for p in prices],
        'high': [p * 1.02 for p in prices],
        'low': [p * 0.98 for p in prices],
        'close': prices,
        'volume': volumes
    })
    
    return df


def calculate_rsi(prices, period=14):
    """计算RSI"""
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def analyze_mock_rsi_oversold(df, stock_code, stock_name):
    """分析模拟数据的RSI超卖"""
    prices = df['close'].values
    latest_price = prices[-1]
    
    # 计算RSI
    rsi = calculate_rsi(prices)
    
    # 计算均线
    ma20 = np.mean(prices[-20:])
    deviation = (ma20 - latest_price) / ma20 * 100
    
    # 计算成交量
    latest_volume = df['volume'].iloc[-1]
    volume_ma5 = df['volume'].tail(5).mean()
    shrink_ratio = latest_volume / volume_ma5 if volume_ma5 > 0 else 1
    
    # 判断超卖
    is_oversold = rsi <= 30
    
    # 评分
    if is_oversold:
        rsi_score = 100 if rsi <= 20 else 85
        deviation_score = 90 if deviation >= 10 else 80
        volume_score = 85 if shrink_ratio < 0.7 else 70
        stability_score = 75
        
        weights = {
            'rsi': 0.35,
            'deviation': 0.25,
            'volume': 0.20,
            'stability': 0.20
        }
        
        total_score = (
            rsi_score * weights['rsi'] +
            deviation_score * weights['deviation'] +
            volume_score * weights['volume'] +
            stability_score * weights['stability']
        )
        
        signal = '强烈买入' if total_score >= 85 else '买入'
        rsi_status = '极度超卖' if rsi <= 20 else '超卖'
    else:
        total_score = 0
        signal = '无信号'
        rsi_status = '正常'
    
    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'score': round(total_score, 2),
        'signal': signal,
        'current_price': round(latest_price, 2),
        'rsi_value': round(rsi, 2),
        'rsi_status': rsi_status,
        'price_deviation': round(deviation, 2),
        'volume_shrink': round((1 - shrink_ratio) * 100, 1),
        'is_oversold': is_oversold
    }


def main():
    print("="*80)
    print("RSI超卖反弹策略 - 模拟数据演示")
    print("="*80)
    print()
    print("创建模拟股票数据（RSI超卖形态）...")
    print()
    
    # 模拟股票
    mock_stocks = [
        ('000001', '平安银行'),
        ('600519', '贵州茅台'),
        ('002594', '比亚迪'),
        ('300750', '宁德时代'),
    ]
    
    results = []
    for code, name in mock_stocks:
        df = create_mock_rsi_oversold_data()
        result = analyze_mock_rsi_oversold(df, code, name)
        results.append(result)
    
    # 按得分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    print("="*80)
    print("模拟分析结果")
    print("="*80)
    print()
    
    for i, r in enumerate(results, 1):
        if r['is_oversold']:
            emoji = '🔥' if r['score'] >= 85 else '✅'
            print(f"{emoji} {i}. {r['stock_name']} ({r['stock_code']})")
            print(f"   综合得分: {r['score']}分 | 信号: {r['signal']}")
            print(f"   当前价: {r['current_price']}元")
            print(f"   RSI值: {r['rsi_value']} ({r['rsi_status']})")
            print(f"   价格偏离: -{r['price_deviation']}%")
            print(f"   缩量程度: {r['volume_shrink']}%")
        else:
            print(f"❌ {i}. {r['stock_name']} ({r['stock_code']}) - RSI未超卖")
        print()
    
    print("="*80)
    print("演示完成")
    print("注意：以上数据为模拟数据，用于展示策略分析功能")
    print("实际使用请运行: python3 skills/scripts/rsi_oversold_scanner.py --scan")
    print("="*80)


if __name__ == '__main__':
    main()
