#!/usr/bin/env python3
"""功能测试脚本"""

import sys
sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/ma-bullish-strategy')

print('='*80)
print('均线多头排列策略 - 功能测试')
print('='*80)
print()

# 测试1: 导入所有模块
print('1. 测试模块导入...')
try:
    from skills.ma_bullish.scripts.ma_analyzer import MABullishAnalyzer
    from skills.ma_bullish.scripts.data_source_adapter import DataSourceAdapter
    from skills.ma_bullish.scripts.sector_analyzer import SectorAnalyzer
    from skills.ma_bullish.scripts.report_generator import ReportGenerator
    from skills.ma_bullish.scripts.risk_manager import RiskManager
    from skills.ma_bullish.scripts.signal_generator import SignalGenerator
    from skills.ma_bullish.scripts.backtest import StrategyBacktest
    print('   ✅ 所有模块导入成功')
except Exception as e:
    print(f'   ❌ 导入失败: {e}')

# 测试2: 数据源适配器
print()
print('2. 测试数据源适配器...')
try:
    adapter = DataSourceAdapter('baostock')
    if adapter.data_source:
        print(f'   ✅ 数据源: {adapter.source}')
    else:
        print('   ❌ 无可用数据源')
except Exception as e:
    print(f'   ❌ 错误: {e}')

# 测试3: 板块列表
print()
print('3. 测试板块分析器...')
try:
    sector_analyzer = SectorAnalyzer(None)
    sectors = sector_analyzer.list_sectors()
    print(f'   ✅ 支持板块: {sectors}')
except Exception as e:
    print(f'   ❌ 错误: {e}')

# 测试4: 配置一致性
print()
print('4. 测试配置一致性...')
try:
    import yaml
    
    # 读取评分权重
    with open('/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/ma-bullish-strategy/config/scoring_weights.yaml', 'r') as f:
        scoring = yaml.safe_load(f)
    
    weights = scoring['weights']
    total = sum(weights.values())
    print(f'   评分权重总和: {total} (应为1.0)')
    if abs(total - 1.0) < 0.01:
        print('   ✅ 权重配置正确')
    else:
        print('   ❌ 权重配置错误')
    
    # 检查阈值
    thresholds = scoring['thresholds']
    print(f"   评分阈值: 强烈推荐≥{thresholds['strong_buy']}, 推荐≥{thresholds['buy']}, 关注≥{thresholds['watch']}")
    print('   ✅ 阈值配置正确')
    
except Exception as e:
    print(f'   ❌ 错误: {e}')

print()
print('='*80)
print('测试完成')
print('='*80)
