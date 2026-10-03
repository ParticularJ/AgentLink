#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回测工具中纯逻辑部分的测试（不联网、不需要缓存数据）。"""
from __future__ import annotations

import sys
import unittest

from tests import support

REPO = support.REPO_ROOT
sys.path.insert(0, str(REPO / "backtests"))

import backtest_september as bt


class TestLegacyOrder(unittest.TestCase):

    def test_orders_by_combined_score_then_arrival(self):
        cands = [
            {"stock_code": "A", "combined_score": 90.0},
            {"stock_code": "B", "combined_score": 95.0},
            {"stock_code": "C", "combined_score": 90.0},
        ]
        # C 比 A 先出现在原始信号里 → 并列时 C 在前
        recs = [{"stock_code": "C"}, {"stock_code": "A"}, {"stock_code": "B"}]
        ordered = [c["stock_code"] for c in bt.legacy_order(cands, recs)]
        self.assertEqual(ordered, ["B", "C", "A"])

    def test_unknown_symbol_goes_last(self):
        cands = [{"stock_code": "Z", "combined_score": 99.0},
                 {"stock_code": "A", "combined_score": 99.0}]
        recs = [{"stock_code": "A"}]
        ordered = [c["stock_code"] for c in bt.legacy_order(cands, recs)]
        self.assertEqual(ordered, ["A", "Z"])


class TestSummarise(unittest.TestCase):

    def test_empty(self):
        s = bt.summarise([], "x")
        self.assertEqual(s["trades"], 0)

    def test_basic_stats(self):
        trades = [
            bt.Trade("2026-09-01", "sh600000", "A", "s", 90, 10, "2026-09-02", 10.0,
                     "2026-09-09", 11.0, "hold", 0.10),
            bt.Trade("2026-09-01", "sh600001", "B", "s", 90, 10, "2026-09-02", 10.0,
                     "2026-09-04", 9.5, "stop", -0.05),
        ]
        s = bt.summarise(trades, "v")
        self.assertEqual(s["trades"], 2)
        self.assertAlmostEqual(s["win_rate"], 50.0)
        self.assertAlmostEqual(s["avg"], 2.5, places=6)
        self.assertEqual(s["stop_count"], 1)
        self.assertEqual(s["time_stop_count"], 0)


class TestSinaSymbol(unittest.TestCase):

    def test_normalisation(self):
        for raw, expected in (("600584", "sh600584"), ("sh600584", "sh600584"),
                              ("000001", "sz000001"), ("sz300750", "sz300750"),
                              ("510880", "sh510880")):
            self.assertEqual(bt.to_sina_code(raw), expected)


if __name__ == "__main__":
    unittest.main()
