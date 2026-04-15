#!/usr/bin/env python3
"""
财报超预期策略 - 命令行入口
"""

import sys
import os

# 添加脚本路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills', 'scripts'))

from earnings_scanner import EarningsSurpriseScanner
from datetime import datetime
import argparse


def main():
    parser = argparse.ArgumentParser(description='财报超预期策略分析')
    parser.add_argument('--scan', action='store_true', help='扫描财报')
    parser.add_argument('--stock', type=str, help='股票代码')
    parser.add_argument('--name', type=str, help='股票名称')
    parser.add_argument('--date', type=str, help='日期 (YYYY-MM-DD)')
    parser.add_argument('--quarter', type=str, help='季度 (如: 2026Q1)')
    parser.add_argument('--top', type=int, default=10, help='显示前N名')
    
    args = parser.parse_args()
    
    print('='*80)
    print('财报超预期策略')
    print('='*80)
    print()
    
    # 创建扫描器
    scanner = EarningsSurpriseScanner()
    
    if args.scan:
        # 扫描模式
        date = args.date or datetime.now().strftime('%Y-%m-%d')
        print(f'扫描日期: {date}')
        print()
        
        try:
            results = scanner.scan_daily_earnings(date)
            
            if results:
                print(f'\n发现 {len(results)} 只符合条件的股票')
                print()
                
                # 显示前N名
                for i, result in enumerate(results[:args.top], 1):
                    print(f'{i}. {result.get("stock_name", "")} ({result.get("stock_code", "")})')
                    print(f'   得分: {result.get("score", 0)}分')
                    print(f'   信号: {result.get("signal", "")}')
                    print()
            else:
                print('未发现符合条件的股票')
                
        except Exception as e:
            print(f'扫描失败: {e}')
            print()
            print('可能原因:')
            print('  - 当前环境无法连接akshare')
            print('  - 指定日期无财报发布')
            print('  - 网络连接问题')
    
    elif args.stock:
        # 单只股票分析
        print(f'分析股票: {args.stock}')
        if args.name:
            print(f'股票名称: {args.name}')
        print()
        
        try:
            # 创建模拟财报数据（实际应从数据源获取）
            test_earnings = {
                'stock_code': args.stock,
                'stock_name': args.name or args.stock,
                'quarter': args.quarter or '2026Q1',
                'net_profit_yoy': 35.0,
                'revenue_yoy': 25.0,
                'eps_surprise': 15.0,
                'gross_margin': 30.0,
                'roe': 15.0
            }
            
            result = scanner.analyze_earnings(test_earnings)
            
            if result:
                print('分析结果:')
                print(f'  股票: {result.get("stock_name", "")} ({result.get("stock_code", "")})')
                print(f'  季度: {result.get("quarter", "")}')
                print(f'  综合得分: {result.get("score", 0)}分')
                print(f'  信号: {result.get("signal", "")}')
                print()
                
                # 显示详细分析
                if 'details' in result:
                    details = result['details']
                    if 'surprise' in details:
                        print('  超预期分析:')
                        print(f'    是否超预期: {details["surprise"].get("is_surprise", False)}')
                        print(f'    超预期得分: {details["surprise"].get("score", 0)}分')
                        print()
            else:
                print('不符合条件')
                
        except Exception as e:
            print(f'分析失败: {e}')
    
    else:
        parser.print_help()
    
    print()
    print('='*80)


if __name__ == '__main__':
    main()
