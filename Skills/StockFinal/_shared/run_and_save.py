#!/usr/bin/env python3
"""
统一执行器 - 运行指定策略并保存结果
用法: python3 run_and_save.py <策略名> [日期]
示例: python3 run_and_save.py ma-bullish-strategy 2026-04-11
"""
import os
import sys
import json
from datetime import datetime

# 策略配置：策略名 -> (模块路径, 类名, 方法名)
STRATEGY_CONFIG = {
    'ma-bullish-strategy': {
        'module': 'skills.ma_bullish.scripts.ma_analyzer',
        'class': 'MABullishAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 5},
        'save_name': 'ma-bullish-strategy',
    },
    'limit-up-retrace-strategy': {
        'module': 'skills.scripts.limit_up_retrace_analyzer',
        'class': 'LimitUpRetraceAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 5},
        'save_name': 'limit-up-retrace-strategy',
    },
    'macd-divergence-strategy': {
        'module': 'skills.scripts.macd_divergence_scanner',
        'class': 'MACDDivergenceAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 5},
        'save_name': 'macd-divergence-strategy',
    },
    'morning-star-strategy': {
        'module': 'skills.scripts.morning_star_analyzer',
        'class': 'MorningStarAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 5},
        'save_name': 'morning-star-strategy',
    },
    'breakout-high-strategy': {
        'module': 'skills.scripts.breakout_high_analyzer',
        'class': 'BreakoutHighAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 5},
        'save_name': 'breakout-high-strategy',
    },
    'rsi-oversold-strategy': {
        'module': 'skills.scripts.rsi_oversold_analyzer',
        'class': 'RSIOversoldAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 5},
        'save_name': 'rsi-oversold-strategy',
    },
    'volume-extreme-strategy': {
        'module': 'skills.scripts.volume_extreme_analyzer',
        'class': 'VolumeExtremeAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 5},
        'save_name': 'volume-extreme-strategy',
    },
    'gap-fill-strategy': {
        'module': 'skills.scripts.gap_fill_analyzer',
        'class': 'GapFillAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 5},
        'save_name': 'gap-fill-strategy',
    },
    'volume-retrace-ma-strategy': {
        'module': 'skills.scripts.retrace_analyzer',
        'class': 'VolumeRetraceAnalyzer',
        'method': 'scan_all_stocks',
        'kwds': {'top_n': 5},
        'save_name': 'volume-retrace-ma-strategy',
    },
    'earnings-surprise-strategy': {
        'module': 'skills.scripts.earnings_scanner',
        'class': 'EarningsSurpriseScanner',
        'method': 'scan_daily_earnings',
        'kwds': {'date': None},  # date 由外部传入
        'save_name': 'earnings-surprise-strategy',
    },
    'limit-up-analysis': {
        'module': 'skills.limit_up.scripts.analyzer',
        'class': 'LimitUpAnalyzer',
        'method': 'analyze_all_limit_up',
        'kwds': {},
        'save_name': 'limit-up-analysis',
    },
}


def run_strategy(strategy_name: str, date: str, save: bool = True) -> dict:
    """运行单个策略并返回结果"""
    cfg = STRATEGY_CONFIG.get(strategy_name)
    if not cfg:
        return {'error': f'未知策略: {strategy_name}'}
    
    strategy_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', strategy_name)
    # 添加到路径
    sys.path.insert(0, strategy_dir)
    
    try:
        # 动态导入
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
        
        # 准备参数
        kwds = dict(cfg['kwds'])
        if 'date' in kwds and kwds['date'] is None:
            kwds['date'] = date
        
        # 调用扫描
        method = getattr(analyzer, cfg['method'])
        results = method(**kwds)
        print(results)
        # 保存
        if save and results:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from data_collector import DataCollector
            collector = DataCollector()
            filepath = collector.save(cfg['save_name'], results, date)
            return {'strategy': strategy_name, 'count': len(results), 'saved': filepath}
        
        return {'strategy': strategy_name, 'count': len(results) if results else 0, 'saved': None}
    
    except Exception as e:
        return {'strategy': strategy_name, 'count': 0, 'error': str(e)}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python3 run_and_save.py <策略名> [日期] [--no-save]')
        print('策略列表:')
        for name in STRATEGY_CONFIG:
            print(f'  - {name}')
        sys.exit(1)
    
    strategy_name = sys.argv[1]
    date = sys.argv[2] if len(sys.argv) > 2 else datetime.now().strftime('%Y%m%d')
    save = '--no-save' not in sys.argv
    
    print(f'策略: {strategy_name}, 日期: {date}, 保存: {save}')
    
    result = run_strategy(strategy_name, date, save)
    
    if 'error' in result:
        print(f'❌ 失败: {result["error"]}')
    elif result['count'] > 0:
        print(f'✅ 扫描到 {result["count"]} 只')
        if result.get('saved'):
            print(f'   保存: {result["saved"]}')
    else:
        print(f'⚠️ 无候选结果')
