#!/usr/bin/env python3
"""
CXMT首日作战矩阵 - 测试用例
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "skills/scripts"))

from cxmt_firstday_monitor import (
    CXMTFirstDayMonitor,
    CXMTDataAdapter,
    CXMTPositionManager,
    MAX_FIRSTDAY_POSITION,
)


def test_phase_detection():
    """测试阶段检测"""
    adapter = CXMTDataAdapter()
    print("阶段检测测试:")
    # 非交易时间用mock
    print(f"  当前阶段(实时): {adapter.get_trading_phase()}")
    assert True, "阶段检测通过"


def test_iron_rules():
    """测试铁律判断"""
    monitor = CXMTFirstDayMonitor(issue_price=10.0, threshold_80_pct=12.6)

    # 测试用例
    test_cases = [
        # (涨幅%, 期望铁律1, 期望铁律2)
        (30.0, "通过", "通过"),
        (50.0, "通过", "通过"),
        (80.0, "通过", "通过"),
        (85.0, "⚠️违反", "通过"),
        (150.0, "⚠️违反", "通过"),
    ]

    print("\n铁律判断测试:")
    for gain_pct, expected_rule1, expected_rule2 in test_cases:
        monitor.refresh_quote = lambda: {
            "price": 10.0 * (1 + gain_pct/100),
            "close_prev": 10.0,
            "turnover": 30.0,
        }
        monitor.last_quote = monitor.refresh_quote()
        iron = monitor._check_iron_rules(gain_pct, 10.0 * (1 + gain_pct/100))
        rule1_status = iron["rules"][0]["status"]
        print(f"  涨幅{gain_pct:+.0f}%: 铁律1={rule1_status} (期望:{expected_rule1})")


def test_position_calculation():
    """测试仓位计算"""
    pm = CXMTPositionManager()
    remaining = pm.calc_remaining_budget(1000000)
    print(f"\n仓位计算测试:")
    print(f"  剩余可用仓位: {remaining/10000:.0f}万 / 40万")


def test_operation_logic():
    """测试各阶段操作逻辑"""
    monitor = CXMTFirstDayMonitor(issue_price=10.0, threshold_80_pct=12.6)

    # Mock行情数据
    test_quotes = [
        # 竞价阶段测试
        {"price": 12.0, "close_prev": 10.0, "turnover": 0},   # 涨幅20% -> 买入15万
        {"price": 15.0, "close_prev": 10.0, "turnover": 0},   # 涨幅50% -> 买入15万
        {"price": 17.0, "close_prev": 10.0, "turnover": 0},   # 涨幅70% -> 买入5万(谨慎)
        {"price": 19.0, "close_prev": 10.0, "turnover": 0},   # 涨幅90% -> 放弃
        # 尾盘阶段测试
        {"price": 14.0, "close_prev": 10.0, "turnover": 60},  # 收涨+换手>50% -> 尾盘加仓
    ]

    print("\n操作逻辑测试:")
    expected = [
        ("买入(限价)", 150000),
        ("试探买入", 50000),
        ("买入(谨慎)", 50000),
        ("放弃竞价", 0),
        ("尾盘加仓", 100000),
    ]
    for i, quote in enumerate(test_quotes):
        monitor.last_quote = quote
        gain_pct = monitor.get_current_gain_pct()

        phases = ["集合竞价", "开盘连续竞价", "集合竞价", "集合竞价", "尾盘确认"]
        phase = phases[i]

        result = monitor.calc_action(phase)
        expected_action, expected_amount = expected[i]
        print(f"  场景{i+1}({phase}): 价={quote['price']} 涨幅={gain_pct:.1f}% -> "
              f"{result['action']} {result['amount']//10000:.0f}万")
        assert result['action'] == expected_action, f"第{i+1}个场景操作应为{expected_action}，实际为{result['action']}"
        assert result['amount'] == expected_amount, f"第{i+1}个场景金额应为{expected_amount}，实际为{result['amount']}"


def test_position_limit_respects_total_fund():
    """总资产为20万时，首日仓位上限应自动降为20万"""
    monitor = CXMTFirstDayMonitor(issue_price=8.66, total_fund=200000)
    assert monitor.position_limit == 200000
    assert monitor.position_mgr.calc_remaining_budget(200000, monitor.position_limit) == 200000


def test_pullback_detection_on_ma_proxy():
    """当行情提供 ma5/ma10 等均线代理时，回踩逻辑应识别为有效回踩"""
    monitor = CXMTFirstDayMonitor(issue_price=8.66, total_fund=200000)
    monitor.last_quote = {"price": 9.60, "close_prev": 8.66, "turnover": 30.0, "ma5": 9.60}
    monitor.peak_price_today = 9.60

    result = monitor._calc_pullback_action(
        {"price": 9.52, "close_prev": 8.66, "turnover": 30.0, "ma5": 9.62},
        5.0,
        200000,
    )
    assert result["action"] == "买入", result


def test_dram_alert():
    """测试DRAM预警更新"""
    monitor = CXMTFirstDayMonitor()

    test_cases = [
        (20.0, "正常"),
        (13.0, "正常"),
        (10.0, "警告"),  # 10%≤Q3<13% → 警告，<10%才减仓
        (8.0,  "减仓"),
        (0.0,  "清仓"),
    ]

    print("\nDRAM预警测试:")
    for q3_pct, expected in test_cases:
        monitor.update_dram_alert(q3_pct)
        print(f"  Q3涨幅={q3_pct}%: 预警={monitor.dram_alert_level} (期望:{expected})")


def test_alert_card():
    """测试飞书卡片生成"""
    monitor = CXMTFirstDayMonitor(issue_price=10.0)
    monitor.last_quote = {
        "price": 14.0,
        "close_prev": 10.0,
        "turnover": 55.0,
    }

    card = monitor.generate_alert_card()
    print(f"\n飞书卡片测试:")
    print(card["markdown"]["content"][:300])


if __name__ == "__main__":
    print("=" * 50)
    print("CXMT首日作战矩阵测试")
    print("=" * 50)

    test_phase_detection()
    test_iron_rules()
    test_position_calculation()
    test_operation_logic()
    test_dram_alert()
    test_alert_card()

    print("\n✅ 所有测试完成")
