#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
成交量地量见底全市场扫描器
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# ── 统一路径：不再硬编码 / 相对 cwd 的路径 ──────────────────
_root = os.path.abspath(os.path.dirname(__file__))
while not os.path.exists(os.path.join(_root, "common", "paths.py")) and _root != os.path.dirname(_root):
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "common"))
from watchlist import load_watchlist_df               # noqa: E402


import argparse
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd


from volume_extreme_strategy_analyzer import VolumeExtremeAnalyzer

def _load_watchlist() -> Optional[pd.DataFrame]:
    """加载自选股池。

    实现见 common/watchlist.py：原先这里依赖 ./my_stock_pool 这类相对当前工作目录的
    路径，换个 cwd 就静默返回 None；现在由 common/paths.py 给出绝对路径。
    """
    return load_watchlist_df()

def scan_all_stocks(analyzer: VolumeExtremeAnalyzer, top_n: int = 20) -> List[Dict]:
    """扫描全市场"""
    print("开始扫描全市场地量见底股票...")
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
        if idx % 20 == 0:
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


def analyze_sector(analyzer: VolumeExtremeAnalyzer, sector_name: str) -> List[Dict]:
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
    print(f"成交量地量见底策略 - {title}")
    print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    print()
    
    if not results:
        print("未发现符合条件的股票")
        print()
        print("说明：")
        print("  - 当前市场无地量见底股票")
        print("  - 成交量未极度萎缩")
        print("  - 未出现企稳信号")
        return
    
    print(f"发现 {len(results)} 只符合条件的股票")
    print()
    
    for i, r in enumerate(results, 1):
        emoji = '🔥' if r['score'] >= 85 else '✅' if r['score'] >= 75 else '👀'
        print(f"{emoji} {i}. {r['stock_name']}({r['stock_code']})")
        print(f"   综合得分: {r['score']}分 | 信号: {r['signal']}")
        print(f"   当前价: {r['current_price']}元")
        print(f"   成交量比: {r['volume_ratio']} ({r['volume_status']})")
        print(f"   价格偏离: -{r['price_deviation']}%")
        print(f"   企稳信号: {r['stability_signal']}")
        print(f"   后续走势: {r['follow_up']}")
        print()
    
    print("="*80)


def main():
    parser = argparse.ArgumentParser(description='成交量地量见底策略')
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
    print("成交量地量见底策略")
    print("="*80)
    print()
    
    # 创建分析器
    try:
        analyzer = VolumeExtremeAnalyzer(data_source=args.source)
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
            print(f"{args.stock} 未检测到地量见底信号")
            print()
            print("地量见底条件：")
            print("  1. 成交量 ≤ 20日均量的40%（极度地量）")
            print("  2. 价格低于20日均线 ≥ 5%")
            print("  3. 出现企稳信号（小实体/长下影线）")
            print("  4. 有反弹迹象")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
