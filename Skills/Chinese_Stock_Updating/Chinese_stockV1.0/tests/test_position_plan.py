#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""需求5 的测试：持仓监控的动态条件单止盈止损。"""
from __future__ import annotations

import sys
import unittest

from tests import support

sys.path.insert(0, str(support.REPO_ROOT / "Medium-termHoldingStrategy" / "skills" / "scripts"))

import daily_stop_plan as dsp


class TestDynamicPlan(unittest.TestCase):

    def test_default_is_fixed_params_not_phase_adaptive(self):
        """回测结论：按 phase 动态调整更差，默认使用固定参数。

        131 笔实测：固定 +4.04%(胜率54.2%) vs 动态 +2.60%(胜率58.8%)，
        训练/测试两半都是固定更优。"""
        self.assertFalse(dsp.DYNAMIC_BY_PHASE)
        self.assertEqual(dsp.plan_for_phase("STRONG_UP"), dsp.DEFAULT_PLAN)
        self.assertEqual(dsp.plan_for_phase("RANGE"), dsp.DEFAULT_PLAN)
        self.assertEqual(dsp.plan_for_phase("STRONG_DOWN"), dsp.DEFAULT_PLAN)

    def test_phase_table_is_still_available_and_ordered(self):
        """动态表本身保留（可开关），且下跌时确实比上涨时更紧。"""
        tbl = dsp.POSITION_PLAN_BY_PHASE
        self.assertGreater(tbl["STRONG_UP"]["stop"], tbl["RANGE"]["stop"])
        self.assertGreater(tbl["RANGE"]["stop"], tbl["STRONG_DOWN"]["stop"])

    def test_dynamic_mode_can_be_enabled(self):
        old = dsp.DYNAMIC_BY_PHASE
        try:
            dsp.DYNAMIC_BY_PHASE = True
            self.assertGreater(dsp.plan_for_phase("STRONG_UP")["stop"],
                               dsp.plan_for_phase("STRONG_DOWN")["stop"])
        finally:
            dsp.DYNAMIC_BY_PHASE = old

    def test_unknown_phase_uses_default(self):
        self.assertEqual(dsp.plan_for_phase("NO_SUCH"), dsp.DEFAULT_PLAN)

    def test_breakeven_armed_by_peak_not_current(self):
        """关键回归：保本看「持仓期最高浮盈」，不能用当前浮盈。

        否则会出现「浮盈一度 13%，回落后却以 -3.6% 离场」的荒谬结果。
        保本默认关闭（回测显示降低期望），这里显式打开验证逻辑。
        """
        old = dsp.BREAKEVEN_ENABLED
        try:
            dsp.BREAKEVEN_ENABLED = True
            o = dsp.build_position_order(cost=34.56, current=38.00, highest=39.20,
                                         phase="STRONG_UP")
            self.assertTrue(o["breakeven_armed"])
            self.assertEqual(o["sell_order"]["trigger_reason"], "保本止损")
            self.assertGreaterEqual(o["sell_order"]["pnl_at_trigger_pct"], 0)
        finally:
            dsp.BREAKEVEN_ENABLED = old

    def test_breakeven_off_by_default(self):
        """默认关闭保本：它在样本上把期望从 +4.04% 压到 +3.44%。"""
        self.assertFalse(dsp.BREAKEVEN_ENABLED)

    def test_new_position_uses_cost_stop(self):
        o = dsp.build_position_order(cost=10.0, current=9.5, highest=10.1, phase="RANGE")
        self.assertFalse(o["breakeven_armed"])
        self.assertEqual(o["sell_order"]["trigger_reason"], "成本止损")
        self.assertLess(o["sell_order"]["pnl_at_trigger_pct"], 0)

    def test_trailing_only_tightens(self):
        """最高价越高，回落止损价越高（只收紧不下移）。"""
        a = dsp.build_position_order(10.0, 12.0, 12.0, "RANGE")
        b = dsp.build_position_order(10.0, 12.0, 15.0, "RANGE")
        self.assertGreaterEqual(b["sell_order"]["trigger_price"], a["sell_order"]["trigger_price"])

    def test_never_below_cost_once_profitable(self):
        """启用保本后，充分盈利过的仓位在任何 phase 下止损都不低于成本。"""
        old = dsp.BREAKEVEN_ENABLED
        dsp.BREAKEVEN_ENABLED = True
        try:
            self._check_never_below_cost()
        finally:
            dsp.BREAKEVEN_ENABLED = old

    def _check_never_below_cost(self):
        for phase in dsp.POSITION_PLAN_BY_PHASE:
            o = dsp.build_position_order(cost=10.0, current=13.0, highest=14.0, phase=phase)
            if o["breakeven_armed"]:
                self.assertGreaterEqual(o["sell_order"]["trigger_price"], 10.0, phase)

    def test_order_is_broker_ready(self):
        o = dsp.build_position_order(10.0, 11.0, 11.5, "WAVE_UP", code="sh600150", name="测试")
        self.assertEqual(o["code"], "600150")
        so = o["sell_order"]
        for k in ("type", "trigger_price", "order_type", "note"):
            self.assertIn(k, so)
        self.assertIn("市价", so["order_type"])

    def test_missing_cost_degrades_gracefully(self):
        o = dsp.build_position_order(None, None, None, "RANGE")
        self.assertIsNone(o["sell_order"]["trigger_price"])

    def test_daily_plan_over_holdings(self):
        plan = dsp.build_daily_plan(
            holdings=[{"code": "600150", "name": "A", "cost": 10, "current_price": 11},
                      {"code": "512480", "name": "B", "cost": 1, "current_price": 4}],
            phase_of=lambda c: "RANGE")
        self.assertEqual(plan["position_count"], 2)
        self.assertEqual([o["code"] for o in plan["orders"]], ["600150", "512480"])


if __name__ == "__main__":
    unittest.main()
