#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""信号冷却期（第二轮优化）的测试。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests import support

sys.path.insert(0, str(support.REPO_ROOT / "strategy-fusion-advisor" / "skills" / "scripts"))

import fusion_config as fc
import fusion_runner as fr


class TestCooldown(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = fr.COOLDOWN_HISTORY_FILE
        fr.COOLDOWN_HISTORY_FILE = str(Path(self.tmp.name) / "recent_picks.json")

    def tearDown(self):
        fr.COOLDOWN_HISTORY_FILE = self._orig
        self.tmp.cleanup()

    def test_default_is_on_and_documented(self):
        """冷却期是回测验证过的默认行为，改动需重新回测。"""
        self.assertEqual(fc.SIGNAL_COOLDOWN_DAYS, 40)

    def test_daily_top_n_is_verified(self):
        """每日推荐数量由第四轮回测确定（原为 5，而每日候选中位数只有 3）。"""
        self.assertEqual(fc.DAILY_TOP_N, 2)

    def test_empty_history_means_no_filtering(self):
        self.assertEqual(fr.load_recent_picks(), {})
        self.assertIsNone(fr.trading_days_since("2026-01-01"))

    def test_record_and_read_back(self):
        fr.record_recent_picks(["600150", "510300"], "2026-09-01")
        last = fr.load_recent_picks()
        self.assertEqual(last["600150"], "2026-09-01")
        self.assertEqual(last["510300"], "2026-09-01")

    def test_trading_days_since_counts_runs(self):
        for d in ("2026-09-01", "2026-09-02", "2026-09-03"):
            fr.record_recent_picks(["600150"], d)
        # 09-01 之后还有 09-02、09-03 两次运行 → 间隔 2 个运行日
        self.assertEqual(fr.trading_days_since("2026-09-01"), 2)
        self.assertEqual(fr.trading_days_since("2026-09-03"), 0)

    def test_same_date_overwrites_not_duplicates(self):
        fr.record_recent_picks(["600150"], "2026-09-01")
        fr.record_recent_picks(["600001"], "2026-09-01")
        hist = json.loads(Path(fr.COOLDOWN_HISTORY_FILE).read_text(encoding="utf-8"))
        self.assertEqual(len(hist["runs"]), 1)
        self.assertEqual(hist["runs"][0]["codes"], ["600001"])

    def test_history_is_capped(self):
        for i in range(fr.COOLDOWN_HISTORY_MAX + 30):
            fr.record_recent_picks([f"6{i:05d}"], f"2026-01-01{i:03d}")
        hist = json.loads(Path(fr.COOLDOWN_HISTORY_FILE).read_text(encoding="utf-8"))
        self.assertEqual(len(hist["runs"]), fr.COOLDOWN_HISTORY_MAX)

    def test_corrupt_history_degrades_to_empty(self):
        Path(fr.COOLDOWN_HISTORY_FILE).write_text("{ not json", encoding="utf-8")
        self.assertEqual(fr.load_recent_picks(), {})


if __name__ == "__main__":
    unittest.main()
