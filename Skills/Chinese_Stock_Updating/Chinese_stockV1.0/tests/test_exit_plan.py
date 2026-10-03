#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出场计划（交易员视角优化第一轮）的测试。"""
from __future__ import annotations

import sys
import unittest

from tests import support

sys.path.insert(0, str(support.REPO_ROOT / "strategy-fusion-advisor" / "skills" / "scripts"))

import fusion_config as fc


class TestExitPlan(unittest.TestCase):

    def test_plan_has_all_executable_fields(self):
        plan = fc.build_exit_plan(10.0)
        for key in ("max_hold_days", "stop_pct", "trail_pct", "take_profit_pct",
                    "entry_max_gap_up_pct", "rule", "stop_price", "entry_max_price"):
            self.assertIn(key, plan)

    def test_stop_and_max_entry_price(self):
        plan = fc.build_exit_plan(10.0)
        self.assertAlmostEqual(plan["stop_price"], 10.0 * (1 - fc.EXIT_STOP_PCT), places=2)
        self.assertAlmostEqual(plan["entry_max_price"], 10.0 * (1 + fc.ENTRY_MAX_GAP_UP), places=2)

    def test_no_fixed_take_profit(self):
        """回测结论：任何固定止盈都降低期望，因此默认关闭。"""
        self.assertEqual(fc.EXIT_TAKE_PROFIT_PCT, 0.0)
        self.assertEqual(fc.build_exit_plan(10.0)["take_profit_pct"], 0.0)

    def test_verified_defaults(self):
        """这些数值来自 707 笔样本的样本外验证，改动即改变策略行为，需重新回测。"""
        self.assertEqual(fc.EXIT_MAX_HOLD_DAYS, 10)
        self.assertEqual(fc.EXIT_STOP_PCT, 0.08)
        self.assertEqual(fc.EXIT_TRAIL_PCT, 0.12)
        self.assertEqual(fc.ENTRY_MAX_GAP_UP, 0.05)

    def test_missing_price_degrades_gracefully(self):
        """拿不到参考价时不能崩，也不能编造价格。"""
        for bad in (0, None, 0.0, -1):
            plan = fc.build_exit_plan(bad)
            self.assertNotIn("stop_price", plan)
            self.assertNotIn("entry_max_price", plan)
            self.assertIn("rule", plan)


if __name__ == "__main__":
    unittest.main()
