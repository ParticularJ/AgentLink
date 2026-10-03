#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第五轮改动的测试：每日推荐数量与 sector_action 归并。"""
from __future__ import annotations

import sys
import unittest

from tests import support

sys.path.insert(0, str(support.REPO_ROOT / "strategy-fusion-advisor" / "skills" / "scripts"))

import fusion_config as fc
import fusion_runner as fr


class TestDailyTopN(unittest.TestCase):

    def test_verified_default(self):
        """每日推荐数由第四轮回测确定（原为 5，而每日候选中位数只有 3）。"""
        self.assertEqual(fc.DAILY_TOP_N, 2)

    def test_run_fusion_uses_the_constant(self):
        import inspect
        sig = inspect.signature(fr.run_fusion)
        self.assertEqual(sig.parameters["top_n"].default, fc.DAILY_TOP_N)


class TestDominantAction(unittest.TestCase):

    def test_most_conservative_wins(self):
        self.assertEqual(fr._dominant_action({"run", "run_low"}), "run_low")
        self.assertEqual(fr._dominant_action({"run", "reserve"}), "reserve")
        self.assertEqual(fr._dominant_action({"run_low", "reserve"}), "reserve")
        self.assertEqual(fr._dominant_action({"run", "block"}), "block")

    def test_single_and_empty(self):
        self.assertEqual(fr._dominant_action({"run"}), "run")
        self.assertEqual(fr._dominant_action(set()), "run")

    def test_regression_run_low_no_longer_mislabelled(self):
        """scored 此前从不携带 sector_action，输出 JSON 里恒为默认值 run，
        把 STRONG_DOWN 板块走 run_low 的 ETF 误标成 run。"""
        self.assertEqual(fr._dominant_action({"run_low"}), "run_low")


if __name__ == "__main__":
    unittest.main()
