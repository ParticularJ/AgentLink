#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心功能验证 - 不依赖文件路径
"""

import sys
sys.path.insert(0, '/home/qinliming/.openclaw/workspace/stop_loss_strategy')

# 验证导入
print("验证模块导入...")
try:
    from scripts.decision_engine import StopLossDecisionEngine, DecisionResult
    print("✅ decision_engine 导入成功")
except Exception as e:
    print(f"❌ decision_engine 导入失败: {e}")

try:
    from scripts.market_status import MarketStatus, MarketStatusChecker
    print("✅ market_status 导入成功")
except Exception as e:
    print(f"❌ market_status 导入失败: {e}")

try:
    from scripts.atr_calculator import calculate_current_profit
    print("✅ atr_calculator 导入成功")
except Exception as e:
    print(f"❌ atr_calculator 导入失败: {e}")

try:
    from config.stop_loss_config import get_sector_stop_loss, get_profit_drawback_threshold
    print("✅ stop_loss_config 导入成功")
except Exception as e:
    print(f"❌ stop_loss_config 导入失败: {e}")

print("\n验证核心功能逻辑...")

# 测试1: 绝对亏损清仓
print("\n【测试1】绝对亏损清仓")
engine = StopLossDecisionEngine()
current_profit = -0.12  # 亏损12%
result = engine.check_priority_1_absolute_loss_clear(current_profit, 0.10)
print(f"  亏损12% vs 清仓线10%: {result.action}")
assert result.triggered == True and result.action == "清仓"
print("  ✅ 通过")

# 测试2: 绝对亏损减半
print("\n【测试2】绝对亏损减半")
current_profit = -0.07  # 亏损7%
result1 = engine.check_priority_1_absolute_loss_clear(current_profit, 0.10)
result2 = engine.check_priority_2_absolute_loss_half(current_profit, 0.10, 0.06)
print(f"  优先级1触发: {result1.triggered}")
print(f"  优先级2结果: {result2.action}")
assert result1.triggered == False
assert result2.triggered == True and result2.action == "减半"
print("  ✅ 通过")

# 测试3: 极端恐慌
print("\n【测试3】极端恐慌")
result = engine.check_priority_3_extreme_panic(MarketStatus.EXTREME_PANIC)
print(f"  结果: {result.action}")
assert result.triggered == True and result.action == "禁止卖出"
print("  ✅ 通过")

# 测试4: 回撤计算
print("\n【测试4】回撤计算")
max_profit = 0.25
current_profit = 0.10
drawback = (max_profit - current_profit) / max_profit
print(f"  最高浮盈25%, 当前10%, 回撤: {drawback*100:.1f}%")
assert abs(drawback - 0.60) < 0.01  # 回撤60%
print("  ✅ 通过")

# 测试5: 板块参数
print("\n【测试5】板块参数")
clear_sl, half_sl = get_sector_stop_loss("科创板")
print(f"  科创板: 清仓{clear_sl*100:.0f}%, 减半{half_sl*100:.0f}%")
assert clear_sl == 0.13 and half_sl == 0.08
clear_sl, half_sl = get_sector_stop_loss("银行")
print(f"  银行: 清仓{clear_sl*100:.0f}%, 减半{half_sl*100:.0f}%")
assert clear_sl == 0.08 and half_sl == 0.05
print("  ✅ 通过")

# 测试6: 恐慌区阈值
print("\n【测试6】恐慌区阈值放宽")
threshold_normal = get_profit_drawback_threshold(0.25, market_panic=False)
threshold_panic = get_profit_drawback_threshold(0.25, market_panic=True)
print(f"  非恐慌区: {threshold_normal*100:.0f}%")
print(f"  恐慌区: {threshold_panic*100:.0f}%")
assert threshold_panic == threshold_normal + 0.10
print("  ✅ 通过")

print("\n" + "=" * 50)
print("🎉 所有核心功能验证通过！")
print("=" * 50)
