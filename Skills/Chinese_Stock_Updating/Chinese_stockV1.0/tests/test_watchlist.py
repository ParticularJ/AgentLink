#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""common/watchlist.py：股票池解析容错。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import support  # noqa: F401

import watchlist


class TestRealWatchlist(unittest.TestCase):

    def setUp(self):
        self.entries = watchlist.load_watchlist_entries()

    def test_parses_reasonable_number_of_entries(self):
        self.assertGreater(len(self.entries), 80, "真实股票池条目数偏少，解析可能漏项")
        self.assertTrue(support.REPO_ROOT.is_dir(), "support 应已完成仓库路径引导")

    def test_known_members_are_present(self):
        by_code = {e["code"]: e for e in self.entries}
        self.assertIn("600900", by_code)
        self.assertEqual(by_code["600900"]["name"], "长江电力")
        self.assertEqual(by_code["600900"]["sector"], "base_holding")
        self.assertEqual(by_code["600900"]["category"], "core")
        # 688017 绿的谐波在 humanoid_robot.core（2026-09 新增持仓同步）
        self.assertEqual(by_code["688017"]["category"], "core")

    def test_no_non_stock_entries_leak_in(self):
        """level: B 这类标量字段不能变成股票条目。"""
        codes = {e["code"] for e in self.entries}
        self.assertNotIn("B", codes)
        self.assertNotIn("level", codes)
        for code in codes:
            self.assertGreaterEqual(len(code), 6, f"可疑代码: {code!r}")

    def test_all_entries_have_required_keys(self):
        for e in self.entries:
            self.assertEqual(set(e), {"name", "code", "sector", "category"})

    def test_codes_helper_matches_entries(self):
        self.assertEqual(watchlist.load_watchlist_codes(), {e["code"] for e in self.entries})


class TestWatchlistEdgeCases(unittest.TestCase):

    def _load(self, text: str):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "w.yaml"
            path.write_text(text, encoding="utf-8")
            return watchlist.load_watchlist_entries(path)

    def test_scalar_field_is_skipped(self):
        entries = self._load(
            "watchlist:\n"
            "  etf_narrow:\n"
            "    level: B\n"
            "    core:\n"
            '      - ["芯片ETF", "159995"]\n'
        )
        self.assertEqual([e["code"] for e in entries], ["159995"])

    def test_empty_category_is_skipped(self):
        entries = self._load(
            "watchlist:\n"
            "  a:\n"
            "    core: []\n"
            "    focus:\n"
            '      - ["X", "000001"]\n'
        )
        self.assertEqual([e["code"] for e in entries], ["000001"])
        self.assertEqual(entries[0]["category"], "focus")

    def test_sector_as_plain_list(self):
        entries = self._load(
            "watchlist:\n"
            "  a:\n"
            '    - ["Y", "000002"]\n'
        )
        self.assertEqual([e["code"] for e in entries], ["000002"])
        self.assertEqual(entries[0]["category"], "core")

    def test_malformed_items_are_ignored(self):
        entries = self._load(
            "watchlist:\n"
            "  a:\n"
            "    core:\n"
            "      - [\"只有名字\"]\n"
            "      - \"裸字符串\"\n"
            '      - ["正常", "000003"]\n'
        )
        self.assertEqual([e["code"] for e in entries], ["000003"])

    def test_missing_section_returns_empty(self):
        self.assertEqual(self._load("other: 1\n"), [])


if __name__ == "__main__":
    unittest.main()
