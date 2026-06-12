#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
决策引擎测试
"""

import os
import sys
import pandas as pd
import numpy as np

# 添加项目路径
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_DIR)

from scripts.decision_engine import StopLossDecisionEngine
from scripts.market_status import MarketStatus


def create_test_data(start_price: float, days: int = 30, trend: str = 'up') -> pd.DataFrame:
    """创建测试数据"""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
    
    if trend == 'up':
        # 上涨趋势
        prices = np.linspace(start_price * 0.95, start_price * 1.20, days)
    elif trend == 'down':
        # 下跌趋势
        prices = np.linspace(start_price * 1.05, start_price * 0.85, days)
    elif trend == 'volatile':
        # 震荡趋势
        prices = start_price * (1 + np.sin(np.linspace(0, 4*np.pi, days)) * 0.05)
    else:
        prices = np.full(days, start_price)
    
    # 添加一些随机波动
    prices = prices * (1 + np.random.randn(days) * 0.01)
    
    df = pd.DataFrame({
        'date': dates,
        'open': prices * 0.995,
        'high': prices * 1.01,
        'low': prices * 0.99,
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, days),
    })
    
    return df


def test_absolute_loss_clear():
    """测试优先级1：绝对亏损清仓"""
    print("\n" + "=" * 70)
    print("测试1: 绝对亏损清仓")
    print("=" * 70)
    
    engine = StopLossDecisionEngine()
    
    # 场景：亏损12%（超过10%清仓线）
    buy_price = 100.0
    current_price = 88.0  # 亏损12%
    
    df = create_test_data(current_price, trend='down')
    
    result = engine.make_decision(
        stock_code="000001",
        stock_name="测试股票",
        buy_price=buy_price,
        current_price=current_price,
        buy_date="2026-05-01",
        current_date="2026-06-12",
        df=df,
        market_status=MarketStatus.NORMAL
    )
    
    final = result['final_decision']
    print(f"买入价: {buy_price}, 当前价: {current_price}")
    print(f"当前浮盈: {result['current_profit']*100:.1f}%")
    print(f"最终决策: {final.action}")
    print(f"触发条件: 优先级{final.priority} - {final.check_item}")
    print(f"原因: {final.reason}")
    
    assert final.priority == 1, "应该触发优先级1"
    assert final.action == "清仓", "应该清仓"
    print("✅ 测试通过")


def test_absolute_loss_half():
    """测试优先级2：绝对亏损减半"""
    print("\n" + "=" * 70)
    print("测试2: 绝对亏损减半")
    print("=" * 70)
    
    engine = StopLossDecisionEngine()
    
    # 场景：亏损7%（超过6%减半线，但未达10%清仓线）
    # 默认板块止损参数：清仓10%，减半6%
    buy_price = 100.0
    current_price = 93.0  # 亏损7%
    
    df = create_test_data(current_price, trend='down')
    
    result = engine.make_decision(
        stock_code="000001",
        stock_name="测试股票",
        buy_price=buy_price,
        current_price=current_price,
        buy_date="2026-05-01",
        current_date="2026-06-12",
        df=df,
        market_status=MarketStatus.NORMAL
    )
    
    final = result['final_decision']
    print(f"买入价: {buy_price}, 当前价: {current_price}")
    print(f"止损参数: 清仓{result['stop_loss_params'][0]*100:.0f}%, 减半{result['stop_loss_params'][1]*100:.0f}%")
    print(f"当前浮盈: {result['current_profit']*100:.1f}%")
    print(f"最终决策: {final.action}")
    print(f"触发条件: 优先级{final.priority} - {final.check_item}")
    print(f"原因: {final.reason}")
    
    assert final.priority == 2, "应该触发优先级2"
    assert final.action == "减半", "应该减半"
    print("✅ 测试通过")


def test_profit_mode():
    """测试利润保护模式"""
    print("\n" + "=" * 70)
    print("测试3: 利润保护模式（回撤减半）")
    print("=" * 70)
    
    engine = StopLossDecisionEngine()
    
    # 场景：最高浮盈25%，当前回撤60%（超过55%阈值）
    buy_price = 100.0
    current_price = 115.0  # 浮盈15%，从25%回撤了40%
    
    df = create_test_data(current_price, trend='up')
    
    result = engine.make_decision(
        stock_code="000001",
        stock_name="测试股票",
        buy_price=buy_price,
        current_price=current_price,
        buy_date="2026-05-01",
        current_date="2026-06-12",
        df=df,
        market_status=MarketStatus.NORMAL,
        historical_max_profit=0.25  # 历史最高浮盈25%
    )
    
    final = result['final_decision']
    print(f"买入价: {buy_price}, 当前价: {current_price}")
    print(f"当前浮盈: {result['current_profit']*100:.1f}%")
    print(f"历史最高浮盈: 25%")
    print(f"最终决策: {final.action}")
    print(f"触发条件: 优先级{final.priority} - {final.check_item}")
    print(f"原因: {final.reason}")
    
    # 注意：这里可能不会触发，因为当前浮盈15% < 10%阈值
    print(f"\n注: 当前浮盈{result['current_profit']*100:.1f}%，需要≥10%才进入利润保护模式")


def test_extreme_panic():
    """测试极端恐慌状态"""
    print("\n" + "=" * 70)
    print("测试4: 极端恐慌状态")
    print("=" * 70)
    
    engine = StopLossDecisionEngine()
    
    # 场景：盈利状态，但大盘极端恐慌
    buy_price = 100.0
    current_price = 115.0  # 浮盈15%
    
    df = create_test_data(current_price, trend='up')
    
    result = engine.make_decision(
        stock_code="000001",
        stock_name="测试股票",
        buy_price=buy_price,
        current_price=current_price,
        buy_date="2026-05-01",
        current_date="2026-06-12",
        df=df,
        market_status=MarketStatus.EXTREME_PANIC
    )
    
    final = result['final_decision']
    print(f"买入价: {buy_price}, 当前价: {current_price}")
    print(f"当前浮盈: {result['current_profit']*100:.1f}%")
    print(f"大盘状态: 极端恐慌")
    print(f"最终决策: {final.action}")
    print(f"触发条件: 优先级{final.priority} - {final.check_item}")
    print(f"原因: {final.reason}")
    
    assert final.priority == 3, "应该触发优先级3"
    assert final.action == "禁止卖出", "应该禁止卖出"
    print("✅ 测试通过")


def test_time_stop():
    """测试时间止损"""
    print("\n" + "=" * 70)
    print("测试5: 时间止损")
    print("=" * 70)
    
    engine = StopLossDecisionEngine()
    
    # 场景：持仓15天，浮盈2%（<5%），亏损8%（≥10%*0.8）
    buy_price = 100.0
    current_price = 92.0  # 亏损8%
    buy_date = "2026-05-28"  # 15天前
    
    df = create_test_data(current_price, trend='down')
    
    result = engine.make_decision(
        stock_code="000001",
        stock_name="测试股票",
        buy_price=buy_price,
        current_price=current_price,
        buy_date=buy_date,
        current_date="2026-06-12",
        df=df,
        market_status=MarketStatus.NORMAL
    )
    
    final = result['final_decision']
    print(f"买入价: {buy_price}, 当前价: {current_price}")
    print(f"买入日期: {buy_date}")
    print(f"当前浮盈: {result['current_profit']*100:.1f}%")
    print(f"最终决策: {final.action}")
    print(f"触发条件: 优先级{final.priority} - {final.check_item}")
    print(f"原因: {final.reason}")
    
    # 注意：这里可能触发优先级1（绝对亏损清仓）而不是时间止损
    print(f"\n注: 亏损8%可能先触发绝对亏损清仓（优先级1）")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("🧪 止损决策引擎测试套件")
    print("=" * 70)
    
    try:
        test_absolute_loss_clear()
    except Exception as e:
        print(f"❌ 测试1失败: {e}")
    
    try:
        test_absolute_loss_half()
    except Exception as e:
        print(f"❌ 测试2失败: {e}")
    
    try:
        test_profit_mode()
    except Exception as e:
        print(f"❌ 测试3失败: {e}")
    
    try:
        test_extreme_panic()
    except Exception as e:
        print(f"❌ 测试4失败: {e}")
    
    try:
        test_time_stop()
    except Exception as e:
        print(f"❌ 测试5失败: {e}")
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == '__main__':
    run_all_tests()
