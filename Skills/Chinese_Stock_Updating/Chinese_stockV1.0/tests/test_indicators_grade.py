#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""common/indicators.py 与 common/grade.py 的纯计算测试。"""
from __future__ import annotations

import unittest

import pandas as pd

from tests import support

import grade as grade_mod
import indicators


class TestRSI(unittest.TestCase):

    def test_all_up_is_100(self):
        closes = pd.Series(support.linear_closes(40))
        self.assertAlmostEqual(indicators.rsi(closes), 100.0, places=6)

    def test_all_down_is_zero(self):
        closes = pd.Series([100 - i for i in range(40)])
        self.assertAlmostEqual(indicators.rsi(closes), 0.0, places=6)

    def test_alternating_stays_midrange(self):
        closes = pd.Series([10 + (i % 2) for i in range(60)])
        value = indicators.rsi(closes)
        self.assertGreater(value, 20)
        self.assertLess(value, 80)

    def test_short_series_is_safe(self):
        self.assertEqual(indicators.rsi(pd.Series([10.0])), 50.0)
        self.assertEqual(indicators.rsi(pd.Series([], dtype=float)), 50.0)

    def test_matches_reference_wilder_formula(self):
        """与 add_position_analyzer 中原本（正确）的实现逐步对照。"""
        closes = pd.Series([10, 11, 10.5, 12, 11.8, 13, 12.5, 14, 13.6, 15,
                            14.4, 16, 15.2, 17, 16.1, 18, 17.3, 19, 18.2, 20.0])

        def reference(c, period=14):
            delta = c.diff()
            gain = delta.where(delta > 0, 0.0)
            loss = (-delta).where(delta < 0, 0.0)
            avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, float("nan"))
            return float((100 - (100 / (1 + rs))).iloc[-1])

        self.assertAlmostEqual(indicators.rsi(closes), reference(closes), places=9)


class TestHelpers(unittest.TestCase):

    def test_pct_change(self):
        self.assertAlmostEqual(indicators.pct_change(10, 11), 10.0)
        self.assertEqual(indicators.pct_change(0, 11), 0.0)
        self.assertEqual(indicators.pct_change(-1, 11), 0.0)

    def test_upward_shadow_ratio(self):
        self.assertAlmostEqual(
            indicators.upward_shadow_ratio({"high": 12, "low": 10, "close": 11}), 0.5
        )
        self.assertEqual(indicators.upward_shadow_ratio({"high": 10, "low": 10, "close": 10}), 0.0)

    def test_ma(self):
        series = pd.Series([1, 2, 3, 4, 5], dtype=float)
        self.assertAlmostEqual(float(indicators.ma(series, 5).iloc[-1]), 3.0)


class TestGrade(unittest.TestCase):

    GRADES = {"600584": "L1_行业龙头", "002384": "L2_细分龙头"}
    CONFIG = {
        "L1_行业龙头": {"profit_targets": [0.18, 0.38, 0.58]},
        "L2_细分龙头": {"profit_targets": [0.12, 0.26, 0.42]},
        "L3_题材跟风": {"profit_targets": [0.10, 0.19, 0.30]},
    }

    def test_known_grade(self):
        self.assertEqual(grade_mod.stock_grade("600584", self.GRADES), "L1_行业龙头")

    def test_unknown_grade_falls_back_to_l3(self):
        self.assertEqual(grade_mod.stock_grade("999999", self.GRADES), "L3_题材跟风")

    def test_profit_targets(self):
        self.assertEqual(
            grade_mod.profit_targets("600584", self.GRADES, self.CONFIG), [0.18, 0.38, 0.58]
        )
        self.assertEqual(
            grade_mod.profit_targets("999999", self.GRADES, self.CONFIG), [0.10, 0.19, 0.30]
        )

    def test_first_profit_target_pct_is_percent(self):
        self.assertAlmostEqual(
            grade_mod.first_profit_target_pct("002384", self.GRADES, self.CONFIG), 12.0
        )

    def test_grade_config_is_a_copy(self):
        cfg = grade_mod.grade_config("600584", self.GRADES, self.CONFIG)
        cfg["profit_targets"].append(9.9)
        self.assertEqual(self.CONFIG["L1_行业龙头"]["profit_targets"][-1], 0.58)

    def test_real_project_tables_are_consistent(self):
        """真实 config.py 里每只登记股票都能查到等级配置。"""
        from config import GRADE_CONFIG, STOCK_GRADE

        for code, level in STOCK_GRADE.items():
            self.assertIn(level, GRADE_CONFIG, f"{code} 的等级 {level} 未在 GRADE_CONFIG 中定义")
        for level, cfg in GRADE_CONFIG.items():
            self.assertEqual(len(cfg["profit_targets"]), 3)
            self.assertEqual(len(cfg["sell_ratio"]), 3)
            self.assertLess(cfg["stop_loss"], 0)


if __name__ == "__main__":
    unittest.main()
