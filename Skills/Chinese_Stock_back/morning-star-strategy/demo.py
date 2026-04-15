#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
早晨之星形态策略演示脚本
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills', 'scripts'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def create_mock_morning_star_data():
    """创建模拟早晨之星形态数据"""
    dates = pd.date_range(end=datetime.now(), periods=10, freq='D')
    
    # 模拟早晨之星形态
    # 第1天：大阴线（下跌）
    # 第2天：十字星（平衡）
    # 第3天：大阳线（上涨）
    
    base_price = 100
    
    # 前7天：下跌趋势
    prices = []
    for i in range(7):
        price = base_price - i * 1.2 + np.random.normal(0, 0.3)
        prices.append(price)
    
    # 第8天：大阴线（第一根）
    day8_open = prices[-1]
    day8_close = day8_open * 0.95  # 下跌5%
    prices.append(day8_close)
    
    # 第9天：十字星（第二根）
    day9_open = day8_close * 0.98  # 低开
    day9_close = day9_open * 1.005  # 小涨，形成十字星
    prices.append(day9_close)
    
    # 第10天：大阳线（第三根）
    day10_open = day9_close
    day10_close = day8_open * 1.02  # 上涨，收盘价深入第一根实体
    prices.append(day10_close)
    
    # 构建OHLC数据
    data = []
    for i, price in enumerate(prices):
        if i < 7:
            # 普通下跌日
            open_p = price * 1.01
            close_p = price * 0.99
            high_p = price * 1.02
            low_p = price * 0.98
            vol = 1000000
        elif i == 7:
            # 第一根：大阴线
            open_p = price * 1.02
            close_p = price * 0.95
            high_p = open_p * 1.01
            low_p = close_p * 0.99
            vol = 1500000  # 放量下跌
        elif i == 8:
            # 第二根：十字星
            open_p = price * 0.98
            close_p = price * 1.005
            high_p = max(open_p, close_p) * 1.02
            low_p = min(open_p, close_p) * 0.98
            vol = 600000  # 缩量
        else:
            # 第三根：大阳线
            open_p = price * 0.99
            close_p = price * 1.06
            high_p = close_p * 1.02
            low_p = open_p * 0.99
            vol = 1400000  # 放量上涨
        
        data.append({
            'date': dates[i],
            'open': open_p,
            'high': high_p,
            'low': low_p,
            'close': close_p,
            'volume': vol
        })
    
    df = pd.DataFrame(data)
    return df


def analyze_mock_morning_star(df, stock_code, stock_name):
    """分析模拟数据的早晨之星"""
    # 计算K线特征
    df['body'] = abs(df['close'] - df['open'])
    df['total_range'] = df['high'] - df['low']
    df['body_ratio'] = df['body'] / df['total_range']
    df['change_pct'] = (df['close'] - df['open']) / df['open'] * 100
    
    # 检查最近3根K线
    first = df.iloc[-3]   # 第一根
    second = df.iloc[-2]  # 第二根
    third = df.iloc[-1]   # 第三根
    
    # 检查第一根（大阴线）
    first_is_bearish = first['close'] < first['open']
    first_decline = abs(first['change_pct'])
    first_is_large = first_decline >= 3.0
    
    # 检查第二根（十字星）
    second_is_doji = second['body_ratio'] <= 0.2
    
    # 检查第三根（大阳线）
    third_is_bullish = third['close'] > third['open']
    third_advance = third['change_pct']
    third_is_large = third_advance >= 3.0
    third_closes_into_first = third['close'] > (first['open'] + first['close']) / 2
    
    # 综合判断
    is_morning_star = (
        first_is_bearish and first_is_large and
        second_is_doji and
        third_is_bullish and third_is_large and third_closes_into_first
    )
    
    # 评分
    if is_morning_star:
        pattern_score = 100 if first_decline >= 5 else 85
        position_score = 100  # 下跌末端
        volume_score = 90     # 成交量配合
        follow_up_score = 85  # 后续确认
        
        weights = {
            'pattern': 0.35,
            'position': 0.25,
            'volume': 0.20,
            'follow_up': 0.20
        }
        
        total_score = (
            pattern_score * weights['pattern'] +
            position_score * weights['position'] +
            volume_score * weights['volume'] +
            follow_up_score * weights['follow_up']
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
        'current_price': round(third['close'], 2),
        'is_morning_star': is_morning_star,
        'first_decline': round(first_decline, 2),
        'third_advance': round(third_advance, 2),
        'second_is_doji': second_is_doji,
        'third_closes_into_first': third_closes_into_first
    }


def main():
    print("="*80)
    print("早晨之星形态策略 - 模拟数据演示")
    print("="*80)
    print()
    print("创建模拟股票数据（标准早晨之星形态）...")
    print()
    
    # 模拟股票
    mock_stocks = [
        ('000001', '平安银行'),
        ('600519', '贵州茅台'),
        ('002594', '比亚迪'),
    ]
    
    results = []
    for code, name in mock_stocks:
        df = create_mock_morning_star_data()
        result = analyze_mock_morning_star(df, code, name)
        results.append(result)
    
    print("="*80)
    print("模拟分析结果")
    print("="*80)
    print()
    
    for i, r in enumerate(results, 1):
        if r['is_morning_star']:
            emoji = '🔥' if r['score'] >= 85 else '✅'
            print(f"{emoji} {i}. {r['stock_name']} ({r['stock_code']})")
            print(f"   综合得分: {r['score']}分 | 信号: {r['signal']}")
            print(f"   当前价: {r['current_price']}元")
            print(f"   第一根跌幅: {r['first_decline']}%")
            print(f"   第三根涨幅: {r['third_advance']}%")
            print(f"   十字星: {'是' if r['second_is_doji'] else '否'}")
            print(f"   收盘价深入第一根: {'是' if r['third_closes_into_first'] else '否'}")
        else:
            print(f"❌ {i}. {r['stock_name']} ({r['stock_code']}) - 未检测到早晨之星")
        print()
    
    print("="*80)
    print("演示完成")
    print("注意：以上数据为模拟数据，用于展示策略分析功能")
    print("实际使用请运行: python3 skills/scripts/morning_star_scanner.py --scan")
    print("="*80)


if __name__ == '__main__':
    main()
