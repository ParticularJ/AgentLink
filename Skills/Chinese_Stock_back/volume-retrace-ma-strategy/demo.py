#!/usr/bin/env python3
"""
缩量回踩重要均线策略 - 演示脚本
使用模拟数据展示策略功能
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def create_mock_stock_data(trend='uptrend', stage='retrace'):
    """创建模拟股票数据"""
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')
    
    if trend == 'uptrend' and stage == 'retrace':
        # 上升趋势中的回踩
        base_price = 100
        prices = []
        volumes = []
        
        # 前40天：上升趋势
        for i in range(40):
            price = base_price + i * 0.5 + np.random.normal(0, 0.5)
            prices.append(price)
            volumes.append(1000000 + np.random.normal(0, 100000))
        
        # 中间10天：回调至均线
        for i in range(10):
            price = prices[-1] - i * 0.3 + np.random.normal(0, 0.3)
            prices.append(price)
            volumes.append(400000 + np.random.normal(0, 50000))  # 缩量
        
        # 最后10天：止跌企稳
        for i in range(10):
            price = prices[-1] + np.random.normal(0, 0.2)
            prices.append(price)
            volumes.append(450000 + np.random.normal(0, 50000))
    
    else:
        # 默认数据
        prices = [100 + np.random.normal(0, 1) for _ in range(60)]
        volumes = [1000000 + np.random.normal(0, 100000) for _ in range(60)]
    
    df = pd.DataFrame({
        'date': dates,
        'open': [p + np.random.normal(0, 0.1) for p in prices],
        'high': [p + abs(np.random.normal(0, 0.5)) for p in prices],
        'low': [p - abs(np.random.normal(0, 0.5)) for p in prices],
        'close': prices,
        'volume': [max(100000, v) for v in volumes]
    })
    
    return df


def analyze_mock_retrace(df, stock_code, stock_name):
    """分析模拟数据的缩量回踩"""
    # 计算均线
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA30'] = df['close'].rolling(window=30).mean()
    df['MA60'] = df['close'].rolling(window=60).mean()
    df['volume_ma5'] = df['volume'].rolling(window=5).mean()
    
    latest = df.iloc[-1]
    
    # 趋势判断
    ma20_gt_ma60 = latest['MA20'] > latest['MA60']
    ma20_slope = (latest['MA20'] - df.iloc[-5]['MA20']) / latest['MA20'] * 100
    
    # 回踩分析
    prev_high = df['close'].rolling(window=20).max().iloc[-1]
    retrace_pct = (prev_high - latest['close']) / prev_high * 100
    
    # 判断最近均线
    ma_types = [('MA20', latest['MA20']), ('MA30', latest['MA30']), ('MA60', latest['MA60'])]
    closest_ma = min(ma_types, key=lambda x: abs(latest['close'] - x[1]))
    distance_to_ma = abs(latest['close'] - closest_ma[1]) / latest['close'] * 100
    
    # 缩量分析
    volume_ma5 = latest['volume_ma5']
    shrink_ratio = latest['volume'] / volume_ma5 if volume_ma5 > 0 else 1
    
    # K线形态
    body = abs(latest['close'] - latest['open'])
    upper_shadow = latest['high'] - max(latest['open'], latest['close'])
    lower_shadow = min(latest['open'], latest['close']) - latest['low']
    
    is_hammer = lower_shadow > body * 2 and upper_shadow < body * 0.5
    is_doji = body < (latest['high'] - latest['low']) * 0.1
    
    # 评分
    trend_score = 100 if ma20_gt_ma60 and ma20_slope > 2 else 85 if ma20_gt_ma60 else 0
    retrace_score = 100 if distance_to_ma <= 1 else 85 if distance_to_ma <= 3 else 0
    volume_score = 100 if shrink_ratio < 0.4 else 85 if shrink_ratio < 0.5 else 70 if shrink_ratio < 0.6 else 0
    signal_score = 100 if is_hammer else 85 if is_doji else 70
    support_score = 100 if ma20_slope > 2 else 85 if ma20_slope > 1 else 70
    
    # 综合得分
    total_score = (
        trend_score * 0.25 +
        retrace_score * 0.20 +
        volume_score * 0.20 +
        signal_score * 0.20 +
        support_score * 0.15
    )
    
    signal = '强烈买入' if total_score >= 80 else '买入' if total_score >= 70 else '观望'
    
    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'score': round(total_score, 2),
        'signal': signal,
        'current_price': round(latest['close'], 2),
        'retrace_ma': closest_ma[0],
        'ma_price': round(closest_ma[1], 2),
        'retrace_pct': round(retrace_pct, 2),
        'volume_shrink': round((1 - shrink_ratio) * 100, 1),
        'stop_signal': '锤子线' if is_hammer else '十字星' if is_doji else '小阳线',
        'details': {
            'trend_score': trend_score,
            'retrace_score': retrace_score,
            'volume_score': volume_score,
            'signal_score': signal_score,
            'support_score': support_score
        }
    }


def main():
    print('='*80)
    print('缩量回踩重要均线策略 - 模拟数据演示')
    print('='*80)
    print()
    print('创建模拟股票数据（上升趋势中的缩量回踩）...')
    print()
    
    # 创建模拟数据
    mock_stocks = [
        ('000001', '平安银行', 'uptrend', 'retrace'),
        ('600519', '贵州茅台', 'uptrend', 'retrace'),
        ('000858', '五粮液', 'uptrend', 'retrace'),
        ('002594', '比亚迪', 'uptrend', 'retrace'),
        ('300750', '宁德时代', 'uptrend', 'retrace'),
    ]
    
    results = []
    for code, name, trend, stage in mock_stocks:
        df = create_mock_stock_data(trend, stage)
        result = analyze_mock_retrace(df, code, name)
        results.append(result)
    
    # 按得分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # 统计
    strong_buy = sum(1 for r in results if r['score'] >= 80)
    buy = sum(1 for r in results if 70 <= r['score'] < 80)
    
    print('='*80)
    print('模拟分析结果')
    print('='*80)
    print(f'分析股票数: {len(results)}')
    print(f'强烈买入(≥80分): {strong_buy}只')
    print(f'买入(70-79分): {buy}只')
    print()
    
    print('【推荐标的】')
    print('-'*80)
    
    for i, r in enumerate(results, 1):
        emoji = '🔥' if r['score'] >= 80 else '✅' if r['score'] >= 70 else '👀'
        print(f'{emoji} {i}. {r["stock_name"]} ({r["stock_code"]})')
        print(f'   综合得分: {r["score"]}分 | 信号: {r["signal"]}')
        print(f'   当前价: {r["current_price"]}元')
        print(f'   回踩均线: {r["retrace_ma"]} @ {r["ma_price"]}元')
        print(f'   回调幅度: {r["retrace_pct"]}%')
        print(f'   缩量程度: {r["volume_shrink"]}% (相比前5日均量)')
        print(f'   止跌信号: {r["stop_signal"]}')
        print()
        
        # 显示详细评分
        print('   五维度评分:')
        for dim, score in r['details'].items():
            dim_name = {
                'trend_score': '趋势强度',
                'retrace_score': '回踩质量',
                'volume_score': '缩量程度',
                'signal_score': '止跌信号',
                'support_score': '支撑强度'
            }.get(dim, dim)
            bar = '█' * int(score / 10) + '░' * (10 - int(score / 10))
            print(f'     {dim_name:12s}: {bar} {score}分')
        print()
    
    print('='*80)
    print('演示完成')
    print('注意：以上数据为模拟数据，用于展示策略分析功能')
    print('实际使用请运行: python3 skills/scripts/retrace_scanner.py --scan')
    print('='*80)


if __name__ == '__main__':
    main()
