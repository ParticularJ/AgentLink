#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
缺口回补全市场扫描器
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import argparse
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd
import yaml


from gap_fill_strategy_analyzer import GapFillAnalyzer

def _load_watchlist() -> Optional[pd.DataFrame]:
    """加载自选股池"""
    watchlist_path = '/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/watchlist.yaml'
    if not os.path.exists(watchlist_path):
        print(f"watchlist.yaml 文件不存在: {watchlist_path}")
        return None
    
    try:
        with open(watchlist_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        stocks = []
        if 'watchlist' in data:
            for sector, categories in data['watchlist'].items():
                for category, stock_list in categories.items():
                    for stock in stock_list:
                        if len(stock) >= 2:
                            stocks.append({
                                'code': stock[1],
                                'name': stock[0]
                            })
        
        if stocks:
            return pd.DataFrame(stocks)
        return None
        
    except Exception as e:
        print(f"加载自选股池失败: {e}")
        return None
    
def scan_all_stocks(analyzer: GapFillAnalyzer, top_n: int = 20) -> List[Dict]:
    """扫描全市场"""
    print(f"开始扫描全市场缺口回补机会...")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"使用数据源: {analyzer.data_adapter.source}")
    print("-" * 60)
    
    # 优先使用自选股池
    stock_list = _load_watchlist()
    if stock_list is not None and not stock_list.empty:
        print(f"使用自选股池，共{len(stock_list)}只股票")
    else:
        # 获取A股列表
        try:
            stock_list = analyzer.data_adapter.get_stock_list()
            if stock_list is None or stock_list.empty:
                print("获取股票列表失败")
                return []
            print(f"获取到{len(stock_list)}只股票")
        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return []
    
    candidates = []
    total = len(stock_list)
    
    for idx, (_, row) in enumerate(stock_list.iterrows(), 1):
        stock_code = row['code']
        stock_name = row.get('name', stock_code)
        
        # 进度显示
        if idx % 100 == 0:
            print(f"进度: {idx}/{total} ({idx/total*100:.1f}%)")
        
        # 分析
        result = analyzer.analyze_stock(stock_code, stock_name)
        if result and result['score'] >= 70:
            candidates.append(result)
            print(f"  ✅ {stock_name}({stock_code}): {result['score']}分")
    
    # 排序
    candidates.sort(key=lambda x: x['score'], reverse=True)
    
    print(f"\n扫描完成，发现{len(candidates)}只符合条件的股票")
    return candidates[:top_n]


def analyze_sector(analyzer: GapFillAnalyzer, sector_name: str) -> List[Dict]:
    """分析指定板块"""
    # 板块股票列表
    sectors = {
        '科技': ['000938', '000977', '002230', '002236', '002415', '300033', '300059', '600570', '600584', '603019'],
        '医药': ['000538', '000623', '000999', '002001', '002007', '300003', '300015', '600276', '600436', '603259'],
        '金融': ['000001', '000002', '600000', '600016', '600030', '600036', '600837', '601318', '601398', '601628'],
        '新能源': ['002074', '002129', '002202', '002594', '300014', '300124', '600438', '601012', '601727', '603806'],
        '半导体': ['002049', '002156', '300046', '300223', '300661', '600360', '600584', '603005', '603501', '688008'],
    }
    
    if sector_name not in sectors:
        print(f"未知板块: {sector_name}")
        print(f"可用板块: {', '.join(sectors.keys())}")
        return []
    
    stocks = sectors[sector_name]
    print(f"分析 {sector_name} 板块 ({len(stocks)}只股票)...")
    
    candidates = []
    for stock_code in stocks:
        print(f"  分析 {stock_code}...", end=' ')
        result = analyzer.analyze_stock(stock_code)
        if result and result['score'] >= 70:
            candidates.append(result)
            print(f"✅ {result['score']}分")
        else:
            print("❌")
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates


def print_results(results: List[Dict], title: str = "扫描结果"):
    """打印结果"""
    print("\n" + "="*80)
    print(f"缺口回补策略 - {title}")
    print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    print()
    
    if not results:
        print("未发现符合条件的股票")
        print()
        print("说明：")
        print("  - 当前市场无缺口回踩股票")
        print("  - 未出现突破性缺口")
        print("  - 未出现回踩确认信号")
        return
    
    print(f"发现 {len(results)} 只符合条件的股票")
    print()
    
    for i, r in enumerate(results, 1):
        emoji = '🔥' if r['score'] >= 85 else '✅' if r['score'] >= 75 else '👀'
        print(f"{emoji} {i}. {r['stock_name']}({r['stock_code']})")
        print(f"   综合得分: {r['score']}分 | 信号: {r['signal']}")
        print(f"   当前价: {r['current_price']}元")
        print(f"   缺口类型: {r['gap_type']}")
        print(f"   缺口大小: {r['gap_size']}%")
        print(f"   缺口区间: {r['gap_low']} - {r['gap_high']}元")
        print(f"   回踩确认: {'是' if r['pullback_confirmed'] else '否'}")
        print(f"   趋势方向: {r['trend_direction']}")
        print()
    
    print("="*80)


def main():
    parser = argparse.ArgumentParser(description='缺口回补策略')
    parser.add_argument('--scan', action='store_true', help='扫描全市场')
    parser.add_argument('--stock', type=str, help='分析单只股票')
    parser.add_argument('--name', type=str, help='股票名称')
    parser.add_argument('--sector', type=str, help='分析板块')
    parser.add_argument('--top', type=int, default=20, help='显示前N名')
    parser.add_argument('--source', type=str, default='auto',
                       choices=['auto', 'akshare', 'tushare', 'baostock', 'yfinance'],
                       help='数据源选择')
    
    args = parser.parse_args()
    
    print("="*80)
    print("缺口回补策略")
    print("="*80)
    print()
    
    # 创建分析器
    try:
        analyzer = GapFillAnalyzer(data_source=args.source)
    except RuntimeError as e:
        print(f"错误: {e}")
        print("\n请安装数据源:")
        print("  pip install akshare  # 推荐")
        print("  pip install baostock")
        return
    
    if args.scan:
        # 全市场扫描
        results = scan_all_stocks(analyzer, top_n=args.top)
        print_results(results, "全市场扫描")
    
    elif args.sector:
        # 板块分析
        results = analyze_sector(analyzer, args.sector)
        print_results(results, f"{args.sector}板块分析")
    
    elif args.stock:
        # 单只股票分析
        result = analyzer.analyze_stock(args.stock, args.name)
        if result:
            print_results([result], "单股分析")
        else:
            print(f"{args.stock} 未检测到缺口回踩信号")
            print()
            print("缺口回补条件：")
            print("  1. 出现向上跳空缺口（≥3%）")
            print("  2. 缺口伴随放量（≥1.5倍均量）")
            print("  3. 价格回踩到缺口区域")
            print("  4. 趋势向好（均线多头排列）")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
