#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
成交量地量见底策略演示脚本
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills', 'scripts'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def create_mock_volume_extreme_data():
    """创建模拟地量数据"""
    dates = pd.date_range(end=datetime.now(), periods=40, freq='D')
    
    base_price = 100
    prices = []
    volumes = []
    
    # 前30天：持续下跌，成交量正常
    for i in range(30):
        price = base_price - i * 0.8 + np.random.normal(0, 0.5)
        prices.append(price)
        vol = 1000000 + np.random.normal(0, 100000)
        volumes.append(max(800000, vol))
    
    # 后10天：继续下跌但成交量极度萎缩（地量）
    for i in range(10):
        price = prices[-1] - i * 0.3 + np.random.normal(0, 0.3)
        prices.append(price)
        vol = 400000 + np.random.normal(0, 30000)  # 地量
        volumes.append(max(300000, vol))
    
    df = pd.DataFrame({
        'date': dates,
        'open': [p * 1.005 for p in prices],
        'high': [p * 1.015 for p in prices],
        'low': [p * 0.985 for p in prices],
        'close': prices,
        'volume': volumes
    })
    
    return df


def analyze_mock_volume_extreme(df, stock_code, stock_name):
    """分析模拟数据的地量"""
    # 计算指标
    df['volume_ma20'] = df['volume'].rolling(window=20).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['body'] = abs(df['close'] - df['open'])
    df['total_range'] = df['high'] - df['low']
    
    latest = df.iloc[-1]
    
    # 成交量分析
    volume_ma20 = latest['volume_ma20']
    current_volume = latest['volume']
    volume_ratio = current_volume / volume_ma20 if volume_ma20 > 0 else 1
    
    # 价格偏离
    ma20 = latest['MA20']
    current_price = latest['close']
    deviation = (ma20 - current_price) / ma20 * 100 if ma20 > 0 else 0
    
    # 判断地量
    is_extreme_volume = volume_ratio <= 0.5
    
    # 评分
    if is_extreme_volume:
        volume_score = 100 if volume_ratio <= 0.4 else 85
        price_score = 90 if deviation >= 10 else 80
        stability_score = 85
        follow_up_score = 75
        
        weights = {
            'volume': 0.35,
            'price': 0.25,
            'stability': 0.25,
            'follow_up': 0.15
        }
        
        total_score = (
            volume_score * weights['volume'] +
            price_score * weights['price'] +
            stability_score * weights['stability'] +
            follow_up_score * weights['follow_up']
        )
        
        signal = '强烈买入' if total_score >= 85 else '买入'
        volume_status = '极度地量' if volume_ratio <= 0.4 else '显著缩量'
    else:
        total_score = 0
        signal = '无信号'
        volume_status = '正常'
    
    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'score': round(total_score, 2),
        'signal': signal,
        'current_price': round(current_price, 2),
        'volume_ratio': round(volume_ratio, 2),
        'volume_status': volume_status,
        'price_deviation': round(deviation, 2),
        'is_extreme_volume': is_extreme_volume
    }


def main():
    print("="*80)
    print("成交量地量见底策略 - 模拟数据演示")
    print("="*80)
    print()
    print("创建模拟股票数据（成交量极度萎缩地量）...")
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
        df = create_mock_volume_extreme_data()
        result = analyze_mock_volume_extreme(df, code, name)
        results.append(result)
    
    # 按得分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    print("="*80)
    print("模拟分析结果")
    print("="*80)
    print()
    
    for i, r in enumerate(results, 1):
        if r['is_extreme_volume']:
            emoji = '🔥' if r['score'] >= 85 else '✅'
            print(f"{emoji} {i}. {r['stock_name']} ({r['stock_code']})")
            print(f"   综合得分: {r['score']}分 | 信号: {r['signal']}")
            print(f"   当前价: {r['current_price']}元")
            print(f"   成交量比: {r['volume_ratio']} ({r['volume_status']})")
            print(f"   价格偏离: -{r['price_deviation']}%")
        else:
            print(f"❌ {i}. {r['stock_name']} ({r['stock_code']}) - 未出现地量")
        print()
    
    print("="*80)
    print("演示完成")
    print("注意：以上数据为模拟数据，用于展示策略分析功能")
    print("实际使用请运行: python3 skills/scripts/volume_extreme_scanner.py --scan")
    print("="*80)


if __name__ == '__main__':
    main()
