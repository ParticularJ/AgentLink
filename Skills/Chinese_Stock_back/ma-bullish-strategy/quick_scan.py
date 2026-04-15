#!/usr/bin/env python3
"""
快速扫描工具 - 分析指定数量的股票
"""

import sys
sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/ma-bullish-strategy')

from skills.ma_bullish.scripts.ma_analyzer import MABullishAnalyzer
from skills.ma_bullish.scripts.data_source_adapter import DataSourceAdapter
from datetime import datetime

def quick_scan(max_stocks=500, top_n=20, data_source='baostock'):
    """
    快速扫描指定数量的股票
    
    Args:
        max_stocks: 最大分析股票数量
        top_n: 返回前N名
        data_source: 数据源
    """
    print('='*80)
    print(f'均线多头排列策略 - 快速扫描（前{max_stocks}只）')
    print('='*80)
    print(f'开始时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()
    
    # 创建分析器
    analyzer = MABullishAnalyzer(data_source=data_source)
    
    # 获取股票列表
    print('正在获取股票列表...')
    try:
        stock_list = analyzer.data_adapter.get_stock_list()
        if stock_list is None or stock_list.empty:
            print("❌ 获取股票列表失败")
            return []
        print(f'✅ 获取到 {len(stock_list)} 只股票')
        print(f'📊 限制扫描前 {max_stocks} 只以加快速度')
        print()
    except Exception as e:
        print(f"❌ 获取股票列表失败: {e}")
        return []
    
    # 限制股票数量
    stock_list = stock_list.head(max_stocks)
    
    # 扫描股票
    candidates = []
    total = len(stock_list)
    
    print('开始扫描...')
    for idx, (_, row) in enumerate(stock_list.iterrows(), 1):
        stock_code = row['code']
        stock_name = row.get('name', stock_code)
        
        # 进度显示
        if idx % 50 == 0 or idx == total:
            print(f'  进度: {idx}/{total} ({idx/total*100:.1f}%)')
        
        # 过滤
        if analyzer._should_filter(stock_code, stock_name):
            continue
        
        # 分析
        try:
            result = analyzer.analyze_stock(stock_code, stock_name)
            if result and result['signal'] == 'BUY' and result['score'] >= 70:
                candidates.append(result)
                print(f'    ✅ {stock_name}({stock_code}): {result["score"]}分')
        except Exception as e:
            pass
    
    # 按得分排序
    candidates.sort(key=lambda x: x['score'], reverse=True)
    
    # 输出结果
    print()
    print('='*80)
    print('扫描结果')
    print('='*80)
    print(f'扫描股票数: {total}')
    print(f'符合条件: {len(candidates)} 只')
    print(f'完成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()
    
    if candidates:
        print(f'前{min(top_n, len(candidates))}名:')
        print('-'*80)
        for i, stock in enumerate(candidates[:top_n], 1):
            print(f'{i}. {stock["stock_name"]}({stock["stock_code"]})')
            print(f'   评分: {stock["score"]}分 | 信号: {stock["signal"]}')
            print(f'   当前价: {stock["current_price"]} | 入场: {stock["entry_price"]}')
            print(f'   止损: {stock["stop_loss"]} | 目标: {stock["target_price"]}')
            print(f'   建议: {stock["suggestion"]}')
            print()
    else:
        print('❌ 未发现符合条件的股票')
        print()
        print('可能原因:')
        print('  - 当前市场环境不适合均线多头排列策略')
        print('  - 扫描的股票数量较少')
        print('  - 建议增加扫描数量或调整分析日期')
    
    print('='*80)
    
    return candidates[:top_n]


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='均线多头排列策略快速扫描')
    parser.add_argument('--max', type=int, default=500, help='最大分析股票数量 (默认500)')
    parser.add_argument('--top', type=int, default=20, help='返回前N名 (默认20)')
    parser.add_argument('--source', type=str, default='baostock', 
                       choices=['auto', 'akshare', 'tushare', 'baostock', 'yfinance'],
                       help='数据源选择')
    
    args = parser.parse_args()
    
    quick_scan(max_stocks=args.max, top_n=args.top, data_source=args.source)
