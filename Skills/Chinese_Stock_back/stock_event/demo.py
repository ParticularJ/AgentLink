#!/usr/bin/env python3
"""
涨停板首次回调策略 - 演示脚本
使用模拟数据展示策略功能
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def create_mock_limit_up_data():
    """创建模拟涨停后回调数据"""
    dates = pd.date_range(end=datetime.now(), periods=10, freq='D')
    
    # 第1天：涨停（+10%）
    # 第2-4天：回调
    # 第5-10天：企稳
    
    base_price = 100
    prices = [
        base_price * 1.10,  # 涨停
        base_price * 1.08,  # 回调开始
        base_price * 1.05,
        base_price * 1.02,  # 回调至涨停价附近
        base_price * 1.03,  # 企稳
        base_price * 1.02,
        base_price * 1.04,
        base_price * 1.03,
        base_price * 1.05,
        base_price * 1.06,
    ]
    
    volumes = [
        2000000,  # 涨停放量
        1200000,  # 回调缩量
        900000,
        800000,   # 缩量至40%
        850000,   # 企稳
        820000,
        900000,
        880000,
        950000,
        1000000,
    ]
    
    df = pd.DataFrame({
        'date': dates,
        'open': [p * 0.99 for p in prices],
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.98 for p in prices],
        'close': prices,
        'volume': volumes
    })
    
    # 计算涨跌幅
    df['pct_change'] = df['close'].pct_change() * 100
    
    return df


def analyze_mock_limit_up_retrace(df, stock_code, stock_name):
    """分析模拟数据的涨停回调"""
    # 计算均线
    df['MA5'] = df['close'].rolling(window=5).mean()
    df['volume_ma3'] = df['volume'].rolling(window=3).mean()
    
    # 查找涨停（第1天）
    limit_up_idx = 0
    limit_up_price = df.iloc[limit_up_idx]['close']
    limit_up_date = df.iloc[limit_up_idx]['date']
    
    # 最新数据
    latest = df.iloc[-1]
    current_price = latest['close']
    
    # 计算回调幅度
    retrace_pct = (limit_up_price - current_price) / limit_up_price * 100
    
    # 支撑位分析
    distance_to_limit_up = abs(current_price - limit_up_price) / current_price * 100
    is_at_support = distance_to_limit_up <= 2
    
    # 成交量分析
    volume_ma3 = latest['volume_ma3']
    shrink_ratio = latest['volume'] / volume_ma3 if volume_ma3 > 0 else 1
    
    # K线形态（最后一天）
    body = abs(latest['close'] - latest['open'])
    upper_shadow = latest['high'] - max(latest['open'], latest['close'])
    lower_shadow = min(latest['open'], latest['close']) - latest['low']
    
    is_hammer = lower_shadow > body * 2
    is_doji = body < (latest['high'] - latest['low']) * 0.1
    
    # 评分
    limit_up_score = 100  # 涨停质量
    retrace_score = 100 if retrace_pct <= 5 else 85 if retrace_pct <= 10 else 70
    support_score = 100 if is_at_support else 70
    volume_score = 100 if shrink_ratio < 0.4 else 85 if shrink_ratio < 0.5 else 70
    signal_score = 100 if is_hammer else 85 if is_doji else 70
    
    # 综合得分
    weights = {
        'limit_up': 0.25,
        'retrace': 0.20,
        'support': 0.20,
        'volume': 0.20,
        'signal': 0.15
    }
    
    total_score = (
        limit_up_score * weights['limit_up'] +
        retrace_score * weights['retrace'] +
        support_score * weights['support'] +
        volume_score * weights['volume'] +
        signal_score * weights['signal']
    )
    
    signal = '强烈买入' if total_score >= 85 else '买入' if total_score >= 75 else '观望'
    
    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'score': round(total_score, 2),
        'signal': signal,
        'current_price': round(current_price, 2),
        'limit_up_date': limit_up_date.strftime('%Y-%m-%d'),
        'limit_up_price': round(limit_up_price, 2),
        'retrace_pct': round(retrace_pct, 2),
        'support_level': '涨停价',
        'support_price': round(limit_up_price, 2),
        'volume_shrink': round((1 - shrink_ratio) * 100, 1),
        'stop_signal': '锤子线' if is_hammer else '十字星' if is_doji else '小阳线',
        'details': {
            'limit_up_score': limit_up_score,
            'retrace_score': retrace_score,
            'support_score': support_score,
            'volume_score': volume_score,
            'signal_score': signal_score
        }
    }


def main():
    print('='*80)
    print('涨停板首次回调策略 - 模拟数据演示')
    print('='*80)
    print()
    print('创建模拟股票数据（涨停后回调至涨停价附近）...')
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
        df = create_mock_limit_up_data()
        result = analyze_mock_limit_up_retrace(df, code, name)
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
        print(f'   涨停日期: {r["limit_up_date"]}')
        print(f'   涨停价: {r["limit_up_price"]}元')
        print(f'   当前价: {r["current_price"]}元 (回调{r["retrace_pct"]}%)')
        print(f'   支撑位: {r["support_level"]} @ {r["support_price"]}元')
        print(f'   缩量程度: {r["volume_shrink"]}% (相比前3日均量)')
        print(f'   止跌信号: {r["stop_signal"]}')
        print()
        
        # 显示详细评分
        print('   五维度评分:')
        for dim, score in r['details'].items():
            dim_name = {
                'limit_up_score': '涨停质量',
                'retrace_score': '回调质量',
                'support_score': '支撑强度',
                'volume_score': '缩量程度',
                'signal_score': '止跌信号'
            }.get(dim, dim)
            bar = '█' * int(score / 10) + '░' * (10 - int(score / 10))
            print(f'     {dim_name:12s}: {bar} {score}分')
        print()
    
    print('='*80)
    print('演示完成')
    print('注意：以上数据为模拟数据，用于展示策略分析功能')
    print('实际使用请运行: python3 skills/scripts/limit_up_retrace_scanner.py --scan')
    print('='*80)


if __name__ == '__main__':
    main()
