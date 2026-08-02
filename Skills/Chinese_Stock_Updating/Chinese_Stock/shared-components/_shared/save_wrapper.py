#!/usr/bin/env python3
"""
财报超预期策略 - 带保存的结果扫描
在 run_scanner.py 基础上增加结果保存功能
"""
import sys
import os

# 添加路径
SHARED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), '_shared')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills', 'scripts'))
sys.path.insert(0, SHARED_DIR)

from earnings_scanner import EarningsSurpriseScanner
from data_collector import DataCollector
from datetime import datetime
import argparse


def main():
    parser = argparse.ArgumentParser(description='财报超预期策略（带保存）')
    parser.add_argument('--scan', action='store_true', help='扫描财报')
    parser.add_argument('--stock', type=str, help='股票代码')
    parser.add_argument('--date', type=str, help='日期 (YYYY-MM-DD)')
    parser.add_argument('--top', type=int, default=10, help='显示前N名')
    parser.add_argument('--no-save', action='store_true', help='不保存结果')
    
    args = parser.parse_args()
    
    date = args.date or datetime.now().strftime('%Y-%m-%d')
    collector = None if args.no_save else DataCollector()
    
    print('='*80)
    print('财报超预期策略')
    print('='*80)
    print(f'日期: {date}')
    print()
    
    scanner = EarningsSurpriseScanner()
    
    if args.scan:
        try:
            results = scanner.scan_daily_earnings(date)
            
            if results:
                print(f'发现 {len(results)} 只符合条件的股票')
                
                # 保存结果
                if collector:
                    filepath = collector.save('earnings-surprise-strategy', results, date)
                    print(f'✅ 已保存: {filepath}')
                
                # 显示前N名
                for i, result in enumerate(results[:args.top], 1):
                    print(f'{i}. {result.get("stock_name", "")} ({result.get("stock_code", "")})')
                    print(f'   得分: {result.get("score", 0)}分 | 信号: {result.get("signal", "")}')
            else:
                print('未发现符合条件的股票')
                
        except Exception as e:
            print(f'扫描失败: {e}')

    elif args.stock:
        # 单只股票分析
        test_earnings = {
            'stock_code': args.stock,
            'stock_name': args.stock,
            'quarter': '2026Q1',
        }
        result = scanner.analyze_earnings(test_earnings)
        if result and collector:
            collector.save('earnings-surprise-strategy', [result], date)
            print(f'✅ 已保存单股票结果')


if __name__ == '__main__':
    main()
