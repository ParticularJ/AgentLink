#!/usr/bin/env python3
"""
MACD底背离策略 - 演示脚本
使用模拟数据展示策略功能
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def create_mock_divergence_data():
    """创建模拟MACD底背离数据"""
    dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
    
    # 模拟股价下跌但MACD不创新低（底背离）
    # 第1-10天：下跌
    # 第11-20天：继续下跌但MACD走平
    # 第21-30天：企稳反弹
    
    base_price = 100
    prices = []
    macd_values = []
    
    # 第一阶段：下跌（价格和MACD同步下跌）
    for i in range(10):
        price = base_price - i * 1.5 + np.random.normal(0, 0.3)
        macd = -0.5 - i * 0.05 + np.random.normal(0, 0.02)
        prices.append(price)
        macd_values.append(macd)
    
    # 第二阶段：继续下跌但MACD走平（底背离形成）
    prev_low = prices[-1]
    for i in range(10):
        price = prev_low - i * 0.8 + np.random.normal(0, 0.3)
        macd = -0.8 + i * 0.03 + np.random.normal(0, 0.02)  # MACD开始回升
        prices.append(price)
        macd_values.append(macd)
    
    # 第三阶段：企稳反弹
    prev_price = prices[-1]
    for i in range(10):
        price = prev_price + i * 0.5 + np.random.normal(0, 0.3)
        macd = -0.5 + i * 0.08 + np.random.normal(0, 0.02)
        prices.append(price)
        macd_values.append(macd)
    
    # 计算DIF和DEA
    dif = [m + 0.2 for m in macd_values]
    dea = [m + 0.1 for m in macd_values]
    
    # 成交量（下跌缩量，反弹放量）
    volumes = []
    for i in range(30):
        if i < 20:
            vol = 800000 - i * 10000 + np.random.normal(0, 50000)
        else:
            vol = 600000 + (i - 20) * 50000 + np.random.normal(0, 50000)
        volumes.append(max(400000, vol))
    
    df = pd.DataFrame({
        'date': dates,
        'open': [p * 0.99 for p in prices],
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.98 for p in prices],
        'close': prices,
        'volume': volumes,
        'DIF': dif,
        'DEA': dea,
        'MACD': [2 * (d - e) for d, e in zip(dif, dea)]
    })
    
    return df


def analyze_mock_divergence(df, stock_code, stock_name):
    """分析模拟数据的MACD底背离"""
    # 计算成交量均线
    df['volume_ma5'] = df['volume'].rolling(window=5).mean()
    
    # 获取近期数据（最后10天）
    recent_df = df.tail(10).reset_index(drop=True)
    
    # 找到价格低点
    price_low_idx = recent_df['close'].idxmin()
    price_low = recent_df.loc[price_low_idx, 'close']
    macd_at_price_low = recent_df.loc[price_low_idx, 'MACD']
    
    # 找到之前的低点
    prev_df = recent_df.iloc[:price_low_idx]
    if len(prev_df) > 0:
        prev_price_low_idx = prev_df['close'].idxmin()
        prev_price_low = prev_df.loc[prev_price_low_idx, 'close']
        prev_macd_low = prev_df.loc[prev_price_low_idx, 'MACD']
    else:
        prev_price_low = price_low * 1.05
        prev_macd_low = macd_at_price_low - 0.2
    
    # 判断背离
    price_lower = price_low < prev_price_low
    macd_not_lower = macd_at_price_low > prev_macd_low
    is_divergence = price_lower and macd_not_lower
    
    # 最新数据
    latest = df.iloc[-1]
    
    # MACD金叉
    prev = df.iloc[-2]
    has_golden_cross = prev['DIF'] < prev['DEA'] and latest['DIF'] > latest['DEA']
    
    # 成交量
    volume_ma5 = latest['volume_ma5']
    volume_increase = latest['volume'] / volume_ma5 if volume_ma5 > 0 else 1
    
    # K线形态
    body = abs(latest['close'] - latest['open'])
    upper_shadow = latest['high'] - max(latest['open'], latest['close'])
    lower_shadow = min(latest['open'], latest['close']) - latest['low']
    
    is_hammer = lower_shadow > body * 2 and upper_shadow < body * 0.5
    is_small_yang = latest['close'] > latest['open'] and body < (latest['high'] - latest['low']) * 0.3
    
    # 评分
    divergence_score = 100 if is_divergence else 0
    golden_cross_score = 100 if has_golden_cross else 70
    volume_score = 100 if volume_increase >= 1.5 else 85 if volume_increase >= 1.2 else 70
    candlestick_score = 100 if is_hammer else 85 if is_small_yang else 70
    support_score = 85  # 模拟前期低点支撑
    
    # 综合得分
    weights = {
        'divergence': 0.25,
        'golden_cross': 0.20,
        'volume': 0.20,
        'candlestick': 0.20,
        'support': 0.15
    }
    
    total_score = (
        divergence_score * weights['divergence'] +
        golden_cross_score * weights['golden_cross'] +
        volume_score * weights['volume'] +
        candlestick_score * weights['candlestick'] +
        support_score * weights['support']
    )
    
    signal = '强烈买入' if total_score >= 85 else '买入' if total_score >= 75 else '观望'
    
    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'score': round(total_score, 2),
        'signal': signal,
        'current_price': round(latest['close'], 2),
        'divergence_type': '强背离' if is_divergence else '无背离',
        'price_low': round(price_low, 2),
        'macd_low': round(macd_at_price_low, 4),
        'prev_price_low': round(prev_price_low, 2),
        'prev_macd_low': round(prev_macd_low, 4),
        'golden_cross': has_golden_cross,
        'volume_increase': round((volume_increase - 1) * 100, 1),
        'candlestick': '锤子线' if is_hammer else '小阳线' if is_small_yang else '普通',
        'support_level': '前期低点',
        'details': {
            'divergence_score': divergence_score,
            'golden_cross_score': golden_cross_score,
            'volume_score': volume_score,
            'candlestick_score': candlestick_score,
            'support_score': support_score
        }
    }


def main():
    print('='*80)
    print('MACD底背离策略 - 模拟数据演示')
    print('='*80)
    print()
    print('创建模拟股票数据（股价下跌但MACD不创新低的底背离形态）...')
    print()
    
    # 模拟股票
    mock_stocks = [
        ('000001', '平安银行'),
        ('600519', '贵州茅台'),
        ('002594', '比亚迪'),
        ('300750', '宁德时代'),
        ('000858', '五粮液'),
    ]
    
    results = []
    for code, name in mock_stocks:
        df = create_mock_divergence_data()
        result = analyze_mock_divergence(df, code, name)
        results.append(result)
    
    # 按得分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # 统计
    strong_buy = sum(1 for r in results if r['score'] >= 85)
    buy = sum(1 for r in results if 75 <= r['score'] < 85)
    
    print('='*80)
    print('模拟分析结果')
    print('='*80)
    print(f'分析股票数: {len(results)}')
    print(f'强烈买入(≥85分): {strong_buy}只')
    print(f'买入(75-84分): {buy}只')
    print()
    
    print('【推荐标的】')
    print('-'*80)
    
    for i, r in enumerate(results, 1):
        emoji = '🔥' if r['score'] >= 85 else '✅' if r['score'] >= 75 else '👀'
        print(f'{emoji} {i}. {r["stock_name"]} ({r["stock_code"]})')
        print(f'   综合得分: {r["score"]}分 | 信号: {r["signal"]}')
        print(f'   背离类型: {r["divergence_type"]}')
        print(f'   价格低点: {r["price_low"]}元 (前低{r["prev_price_low"]}元)')
        print(f'   MACD低点: {r["macd_low"]} (前低{r["prev_macd_low"]})')
        print(f'   MACD金叉: {"已确认" if r["golden_cross"] else "未确认"}')
        print(f'   成交量放大: {r["volume_increase"]}%')
        print(f'   K线形态: {r["candlestick"]}')
        print(f'   支撑位置: {r["support_level"]}')
        print()
        
        # 显示详细评分
        print('   五维度评分:')
        for dim, score in r['details'].items():
            dim_name = {
                'divergence_score': '背离强度',
                'golden_cross_score': 'MACD金叉',
                'volume_score': '量能确认',
                'candlestick_score': 'K线形态',
                'support_score': '支撑位置'
            }.get(dim, dim)
            bar = '█' * int(score / 10) + '░' * (10 - int(score / 10))
            print(f'     {dim_name:12s}: {bar} {score}分')
        print()
    
    print('='*80)
    print('演示完成')
    print('注意：以上数据为模拟数据，用于展示策略分析功能')
    print('实际使用请运行: python3 skills/scripts/macd_divergence_scanner.py --scan')
    print('='*80)


if __name__ == '__main__':
    main()
