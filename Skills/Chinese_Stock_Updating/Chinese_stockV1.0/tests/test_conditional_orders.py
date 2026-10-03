#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""需求3 的测试：收盘后统一运行 + 智能条件单参数。"""
from __future__ import annotations

import sys
import unittest

from tests import support

sys.path.insert(0, str(support.REPO_ROOT / "strategy-fusion-advisor" / "skills" / "scripts"))

import fusion_config as fc


class TestCloseSession(unittest.TestCase):

    def test_close_runs_all_enabled_strategies(self):
        """用户需求：所有策略都在收盘后（15:00 后）统一运行。"""
        self.assertEqual(
            sorted(fc.CLOSE_STRATEGIES),
            sorted(["gap-fill-strategy", "ma-bullish-strategy", "breakout-high-strategy"]))

    def test_close_is_superset_of_both_sessions(self):
        for s in list(fc.EVENING_STRATEGIES) + list(fc.MORNING_STRATEGIES):
            self.assertIn(s, fc.CLOSE_STRATEGIES)


class TestConditionalOrders(unittest.TestCase):

    def setUp(self):
        self.p = 34.56
        self.co = fc.build_conditional_orders(self.p)

    def test_three_blocks_present(self):
        for k in ("buy", "sell", "execution"):
            self.assertIn(k, self.co)

    def test_buy_order_is_fillable_in_broker_app(self):
        """买入条件单必须给出：类型 / 监控价 / 委托方式 / 有效期。"""
        b = self.co["buy"]
        self.assertIn(b["type"], ("定价买入", "反弹买入"))
        self.assertEqual(b["monitor_price"], round(self.p, 2))
        self.assertTrue(b["order_type"])
        self.assertGreater(b["valid_months"], 0)

    def test_stop_loss_uses_market_order(self):
        """PDF：止损用市价（保命，能卖掉比卖得高重要）。"""
        sl = self.co["sell"]["stop_loss"]
        self.assertEqual(sl["base_price"], round(self.p, 2))
        self.assertAlmostEqual(sl["trigger_price"], round(self.p * (1 - fc.CO_STOP_LOSS_PCT), 2), places=2)
        self.assertIn("市价", sl["order_type"])

    def test_trailing_has_activation_and_giveback(self):
        """回落卖出：涨过激活价后追踪最高点，回落 X% 触发。"""
        tr = self.co["sell"]["trailing"]
        self.assertIn("activate_price", tr)
        self.assertIn("giveback_pct", tr)
        self.assertGreater(tr["giveback_pct"], 0)

    def test_no_fixed_take_profit_by_default(self):
        """PDF 建议 2:1 固定止盈，但本策略实测会降低期望，故默认不启用。"""
        self.assertEqual(fc.CO_TAKE_PROFIT_PCT, 0.0)
        self.assertNotIn("take_profit", self.co["sell"])

    def test_take_profit_appears_when_enabled(self):
        old = fc.CO_TAKE_PROFIT_PCT
        try:
            fc.CO_TAKE_PROFIT_PCT = 0.16
            co = fc.build_conditional_orders(self.p)
            self.assertEqual(co["sell"]["take_profit"]["trigger_price"], round(self.p * 1.16, 2))
            self.assertIn("限价", co["sell"]["take_profit"]["order_type"])
        finally:
            fc.CO_TAKE_PROFIT_PCT = old

    def test_missing_price_degrades_gracefully(self):
        for bad in (0, None, -1):
            co = fc.build_conditional_orders(bad)
            self.assertIsNone(co["buy"]["monitor_price"])
            self.assertIsNone(co["sell"]["stop_loss"]["trigger_price"])

    def test_execution_carries_max_hold_and_gap_limit(self):
        ex = self.co["execution"]
        self.assertEqual(ex["max_hold_days"], fc.EXIT_MAX_HOLD_DAYS)
        self.assertEqual(ex["entry_max_gap_up_pct"], round(fc.ENTRY_MAX_GAP_UP * 100, 1))


if __name__ == "__main__":
    unittest.main()
