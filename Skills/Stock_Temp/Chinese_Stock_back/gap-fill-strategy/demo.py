#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
缺口回补策略演示脚本
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills', 'scripts'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def create_mock_gap_fill_data():
    """创建模拟缺口回补数据"""
    dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
    
    base_price = 100
    prices = []
    volumes = []
    
    # 前15天：横盘整理
    for i in range(15):
        price = base_price + np.random.normal(0, 1)
        prices.append(price)
        vol = 800000 + np.random.normal(0, 50000)
        volumes.append(max(700000, vol))
    
    # 第16天：向上跳空缺口（5%）
    gap_price = prices[-1] * 1.05
    prices.append(gap_price)
    vol = 1500000  # 放量
    volumes.append(vol)
    
    # 后14天：回踩缺口
    for i in range(14):
        # 逐渐回踩到缺口区域
        if i < 7:
            price = prices[-1] - i * 0.3 + np.random.normal(0, 0.2)
        else:
            price = prices[-1] * 0.995 + np.random.normal(0, 0.2)
        prices.append(price)
        vol = 900000 + np.random.normal(0, 30000)
        volumes.append(max(800000, vol))
    
    df = pd.DataFrame({
        'date': dates,
        'open': [p * 0.998 for p in prices],
        'high': [p * 1.02 for p in prices],
        'low': [p * 0.98 for p in prices],
        'close': prices,
        'volume': volumes
    })
    
    return df


def analyze_mock_gap_fill(df, stock_code, stock_name):
    """分析模拟数据的缺口"""
    # 查找缺口
    prev_close = df['close'].shift(1)
    gap_up = (df['low'] - prev_close) / prev_close * 100
    
    # 找到最大的向上跳空缺口
    max_gap_idx = gap_up.idxmax()
    max_gap = gap_up.max()
    
    if max_gap < 3.0:
        return {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'score': 0,
            'signal': '无信号',
            'has_gap': False
        }
    
    # 计算均线
    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA10'] = df['close'].rolling(window=10).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()
    
    latest = df.iloc[-1]
    gap_row = df.loc[max_gap_idx]
    
    # 缺口信息
    gap_low = prev_close.loc[max_gap_idx]
    gap_high = gap_row['low']
    current_price = latest['close']
    
    # 检查回踩
    in_gap_zone = gap_low <= current_price <= gap_high
    above_gap = current_price > gap_high
    
    # 趋势判断
    ma_bullish = latest['MA5'] > latest['MA10'] > latest['MA20'] if not pd.isna(latest['MA20']) else False
    
    # 评分
    if in_gap_zone and max_gap >= 5:
        score = 90
        signal = '强烈买入'
    elif in_gap_zone:
        score = 80
        signal = '买入'
    elif above_gap and (current_price - gap_high) / gap_high < 0.02:
        score = 75
        signal = '观望'
    else:
        score = 0
        signal = '无信号'
    
    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'score': score,
        'signal': signal,
        'has_gap': True,
        'current_price': round(current_price, 2),
        'gap_type': '突破性缺口' if max_gap >= 5 else '普通缺口',
        'gap_size': round(max_gap, 2),
        'gap_low': round(gap_low, 2),
        'gap_high': round(gap_high, 2),
        'pullback_confirmed': in_gap_zone or (above_gap and (current_price - gap_high) / gap_high < 0.02),
        'trend_direction': '多头排列' if ma_bullish else '趋势不明'
    }


def main():
    print("="*80)
    print("缺口回补策略 - 模拟数据演示")
    print("="*80)
    print()
    print("创建模拟股票数据（向上跳空缺口+回踩）...")
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
        df = create_mock_gap_fill_data()
        result = analyze_mock_gap_fill(df, code, name)
        results.append(result)
    
    # 按得分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    print("="*80)
    print("模拟分析结果")
    print("="*80)
    print()
    
    for i, r in enumerate(results, 1):
        if r['has_gap'] and r['score'] > 0:
            emoji = '🔥' if r['score'] >= 85 else '✅' if r['score'] >= 75 else '👀'
            print(f"{emoji} {i}. {r['stock_name']} ({r['stock_code']})")
            print(f"   综合得分: {r['score']}分 | 信号: {r['signal']}")
            print(f"   当前价: {r['current_price']}元")
            print(f"   缺口类型: {r['gap_type']}")
            print(f"   缺口大小: {r['gap_size']}%")
            print(f"   缺口区间: {r['gap_low']} - {r['gap_high']}元")
            print(f"   回踩确认: {'是' if r['pullback_confirmed'] else '否'}")
            print(f"   趋势方向: {r['trend_direction']}")
        elif r['has_gap']:
            print(f"👀 {i}. {r['stock_name']} ({r['stock_code']}) - 有缺口但未回踩")
        else:
            print(f"❌ {i}. {r['stock_name']} ({r['stock_code']}) - 无跳空缺口")
        print()
    
    print("="*80)
    print("演示完成")
    print("注意：以上数据为模拟数据，用于展示策略分析功能")
    print("实际使用请运行: python3 skills/scripts/gap_fill_scanner.py --scan")
    print("="*80)


if __name__ == '__main__':
    main()
