#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试脚本 - 验证止损策略核心功能
"""

import sys
import os
# 获取当前脚本所在目录
if '__file__' in dir():
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
else:
    _SCRIPT_DIR = os.getcwd()
sys.path.insert(0, _SCRIPT_DIR)

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 导入模块
from scripts.decision_engine import StopLossDecisionEngine, DecisionResult
from scripts.market_status import MarketStatus, MarketStatusChecker
from scripts.atr_calculator import calculate_current_profit
from scripts.profit_protect import ProfitProtectMode
from scripts.principal_protect import PrincipalProtectMode
from scripts.time_stop import TimeStopLoss
from config.stop_loss_config import get_sector_stop_loss, get_profit_drawback_threshold

print("=" * 70)
print("🧪 止损策略功能测试")
print("=" * 70)

# 测试1: 绝对亏损清仓
print("\n【测试1】绝对亏损清仓")
print("-" * 70)
engine = StopLossDecisionEngine()
buy_price = 100.0
current_price = 88.0  # 亏损12%
current_profit = calculate_current_profit(current_price, buy_price)
print(f"买入价: {buy_price}, 当前价: {current_price}")
print(f"当前浮盈: {current_profit*100:.1f}%")

# 手动测试优先级1
result = engine.check_priority_1_absolute_loss_clear(current_profit, 0.10)
print(f"优先级1结果: {result.action}")
print(f"触发: {result.triggered}")
print(f"原因: {result.reason}")
assert result.triggered == True, "应该触发"
assert result.action == "清仓", "应该清仓"
print("✅ 测试通过")

# 测试2: 绝对亏损减半
print("\n【测试2】绝对亏损减半")
print("-" * 70)
buy_price = 100.0
current_price = 93.0  # 亏损7%
current_profit = calculate_current_profit(current_price, buy_price)
print(f"买入价: {buy_price}, 当前价: {current_price}")
print(f"当前浮盈: {current_profit*100:.1f}%")

# 先检查优先级1（应该不触发）
result1 = engine.check_priority_1_absolute_loss_clear(current_profit, 0.10)
print(f"优先级1触发: {result1.triggered}")
assert result1.triggered == False, "优先级1不应该触发"

# 再检查优先级2
result2 = engine.check_priority_2_absolute_loss_half(current_profit, 0.10, 0.06)
print(f"优先级2结果: {result2.action}")
print(f"触发: {result2.triggered}")
print(f"原因: {result2.reason}")
assert result2.triggered == True, "应该触发"
assert result2.action == "减半", "应该减半"
print("✅ 测试通过")

# 测试3: 极端恐慌
print("\n【测试3】极端恐慌状态")
print("-" * 70)
result = engine.check_priority_3_extreme_panic(MarketStatus.EXTREME_PANIC)
print(f"大盘状态: 极端恐慌")
print(f"结果: {result.action}")
print(f"触发: {result.triggered}")
assert result.triggered == True, "应该触发"
assert result.action == "禁止卖出", "应该禁止卖出"
print("✅ 测试通过")

# 测试4: 利润保护模式 - 回撤计算
print("\n【测试4】利润保护模式 - 回撤计算")
print("-" * 70)
profit_protect = ProfitProtectMode()
max_profit = 0.25  # 最高浮盈25%
current_profit = 0.15  # 当前浮盈15%

# 计算回撤
drawback = (max_profit - current_profit) / max_profit
print(f"最高浮盈: {max_profit*100:.1f}%")
print(f"当前浮盈: {current_profit*100:.1f}%")
print(f"回撤: {drawback*100:.1f}%")

# 获取阈值（非恐慌区）
threshold = get_profit_drawback_threshold(max_profit, market_panic=False)
print(f"回撤阈值: {threshold*100:.1f}%")
print(f"是否触发: {drawback >= threshold}")
assert drawback < threshold, "回撤40%应该小于阈值55%"
print("✅ 测试通过")

# 测试5: 利润保护模式 - 触发减半
print("\n【测试5】利润保护模式 - 触发减半")
print("-" * 70)
max_profit = 0.25  # 最高浮盈25%
current_profit = 0.10  # 当前浮盈10%（回撤60%）

drawback = (max_profit - current_profit) / max_profit
print(f"最高浮盈: {max_profit*100:.1f}%")
print(f"当前浮盈: {current_profit*100:.1f}%")
print(f"回撤: {drawback*100:.1f}%")

threshold = get_profit_drawback_threshold(max_profit, market_panic=False)
print(f"回撤阈值: {threshold*100:.1f}%")
print(f"是否触发: {drawback >= threshold}")
assert drawback >= threshold, "回撤60%应该大于等于阈值55%"
print("✅ 测试通过")

# 测试6: 时间止损
print("\n【测试6】时间止损")
print("-" * 70)
time_stop = TimeStopLoss()
buy_date = "2026-05-28"
current_date = "2026-06-12"
hold_days = time_stop.calculate_hold_days(buy_date, current_date)
print(f"买入日期: {buy_date}")
print(f"当前日期: {current_date}")
print(f"持仓天数: {hold_days}天")
assert hold_days == 15, "应该持仓15天"

# 检查时间止损触发
current_profit = -0.08  # 亏损8%
clear_stop_loss = 0.10  # 清仓止损10%
triggered, reason, ratio = time_stop.check_time_stop(
    hold_days, current_profit, clear_stop_loss, MarketStatus.NORMAL
)
print(f"当前浮盈: {current_profit*100:.1f}%")
print(f"触发: {triggered}")
print(f"原因: {reason}")
assert triggered == True, "应该触发时间止损"
assert ratio == 1.0, "应该清仓"
print("✅ 测试通过")

# 测试7: 板块止损参数
print("\n【测试7】板块止损参数")
print("-" * 70)
# 科创板
sector = "科创板"
clear_sl, half_sl = get_sector_stop_loss(sector)
print(f"板块: {sector}")
print(f"清仓止损: {clear_sl*100:.1f}%, 减半止损: {half_sl*100:.1f}%")
assert clear_sl == 0.13, "科创板清仓应该是13%"
assert half_sl == 0.08, "科创板减半应该是8%"

# 银行
sector = "银行"
clear_sl, half_sl = get_sector_stop_loss(sector)
print(f"板块: {sector}")
print(f"清仓止损: {clear_sl*100:.1f}%, 减半止损: {half_sl*100:.1f}%")
assert clear_sl == 0.08, "银行清仓应该是8%"
assert half_sl == 0.05, "银行减半应该是5%"
print("✅ 测试通过")

# 测试8: 恐慌区阈值放宽
print("\n【测试8】恐慌区回撤阈值放宽")
print("-" * 70)
max_profit = 0.25  # 最高浮盈25%

# 非恐慌区
threshold_normal = get_profit_drawback_threshold(max_profit, market_panic=False)
print(f"非恐慌区阈值: {threshold_normal*100:.1f}%")

# 恐慌区
threshold_panic = get_profit_drawback_threshold(max_profit, market_panic=True)
print(f"恐慌区阈值: {threshold_panic*100:.1f}%")

assert threshold_panic > threshold_normal, "恐慌区阈值应该放宽"
assert threshold_panic == threshold_normal + 0.10, "应该放宽10个百分点"
print("✅ 测试通过")

print("\n" + "=" * 70)
print("🎉 所有测试通过！")
print("=" * 70)
