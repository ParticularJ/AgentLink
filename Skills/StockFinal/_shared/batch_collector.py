#!/usr/bin/env python3
"""
批量数据采集器 - 一键采集所有策略当日结果
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

# 策略列表及入口（路径使用下划线对应实际Python模块路径）
STRATEGIES = [
    {
        'name': 'ma-bullish-strategy',
        'module': 'skills.ma_bullish.scripts.ma_analyzer',
        'class': 'MABullishAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 20},
    },
    {
        'name': 'limit-up-retrace-strategy',
        'module': 'skills.limit_up_retrace.scripts.limit_up_retrace_analyzer',
        'class': 'LimitUpRetraceAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 20},
    },
    {
        'name': 'macd-divergence-strategy',
        'module': 'skills.macd_divergence.scripts.macd_divergence_analyzer',
        'class': 'MACDDivergenceAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 20},
    },
    {
        'name': 'morning-star-strategy',
        'module': 'skills.morning_star.scripts.morning_star_analyzer',
        'class': 'MorningStarAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 20},
    },
    {
        'name': 'breakout-high-strategy',
        'module': 'skills.breakout_high.scripts.breakout_high_analyzer',
        'class': 'BreakoutHighAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 20},
    },
    {
        'name': 'rsi-oversold-strategy',
        'module': 'skills.rsi_oversold.scripts.rsi_oversold_analyzer',
        'class': 'RSIOversoldAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 20},
    },
    {
        'name': 'volume-extreme-strategy',
        'module': 'skills.volume_extreme.scripts.volume_extreme_analyzer',
        'class': 'VolumeExtremeAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 20},
    },
    {
        'name': 'gap-fill-strategy',
        'module': 'skills.gap_fill.scripts.gap_fill_analyzer',
        'class': 'GapFillAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 20},
    },
    {
        'name': 'volume-retrace-ma-strategy',
        'module': 'skills.volume_retrace_ma.scripts.retrace_analyzer',
        'class': 'VolumeRetraceAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 20},
    },
]


def get_strategy_base_dir(strategy_name: str) -> str:
    """获取策略根目录"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', strategy_name)


def run_strategy(cfg: dict, date: str, collector, dry_run: bool) -> dict:
    """运行单个策略采集"""
    name = cfg['name']
    strategy_dir = get_strategy_base_dir(name)
    
    # 动态导入
    try:
        sys.path.insert(0, strategy_dir)
        mod = __import__(cfg['module'], fromlist=[cfg['class']])
        cls = getattr(mod, cfg['class'])
        
        # 实例化
        try:
            analyzer = cls(data_source='baostock')
        except TypeError:
            try:
                analyzer = cls()
            except TypeError:
                analyzer = cls(data_source='auto')
        
        # 调用扫描方法
        method = getattr(analyzer, cfg['method'])
        results = method(**cfg['kwds'])
        
        if not dry_run and results:
            filepath = collector.save(name, results, date)
            return {'strategy': name, 'count': len(results), 'saved': filepath}
        return {'strategy': name, 'count': len(results), 'saved': None}
        
    except Exception as e:
        return {'strategy': name, 'count': 0, 'error': str(e)}


def run_batch_collect(date: str = None, dry_run: bool = False):
    """批量采集所有策略"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    # 初始化采集器
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from data_collector import DataCollector
    collector = DataCollector()
    
    results_summary = []
    
    for cfg in STRATEGIES:
        name = cfg['name']
        print(f"\n{'='*60}")
        print(f"策略: {name}")
        print(f"{'='*60}")
        
        result = run_strategy(cfg, date, collector, dry_run)
        
        if 'error' in result:
            print(f"  ❌ 失败: {result['error']}")
        elif result['count'] > 0:
            if result['saved']:
                print(f"  ✅ 扫描到 {result['count']} 只，已保存: {result['saved']}")
            else:
                print(f"  🔍 [dry-run] 扫描到 {result['count']} 只")
        else:
            print(f"  ⚠️ 无候选结果")
        
        results_summary.append(result)
    
    # 汇总
    total = sum(r.get('count', 0) for r in results_summary)
    success = sum(1 for r in results_summary if r.get('saved'))
    failed = sum(1 for r in results_summary if 'error' in r)
    
    print(f"\n{'='*60}")
    print(f"采集完成 - {date}")
    print(f"{'='*60}")
    print(f"总计候选: {total} 只 | 成功保存: {success} | 失败: {failed}")
    
    return results_summary


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='批量采集所有策略当日结果')
    parser.add_argument('--date', type=str, default=None, help='日期 YYYY-MM-DD')
    parser.add_argument('--dry-run', action='store_true', help='仅扫描不保存')
    args = parser.parse_args()
    
    run_batch_collect(date=args.date, dry_run=args.dry_run)
