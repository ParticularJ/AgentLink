#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""common/holdings.py：代码规范化、读写、备份、原子写。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import support

import holdings


class TestCodeNormalisation(unittest.TestCase):

    def test_to_pure_code(self):
        cases = {
            "sh600584": "600584",
            "sz000001": "000001",
            "600584": "600584",
            "000001": "000001",
            "SH600584": "600584",
            "  sz300750  ": "300750",
            "": "",
        }
        for raw, expected in cases.items():
            self.assertEqual(holdings.to_pure_code(raw), expected, f"输入 {raw!r}")

    def test_lstrip_prefix_bug_is_avoided(self):
        """lstrip("sh") 会按字符集剥离，必须用前缀切片。"""
        self.assertEqual(holdings.to_pure_code("sz300750"), "300750")
        self.assertEqual("sz300750".lstrip("sh").lstrip("sz"), "300750")  # 巧合正确
        # 真正的差异：代码里出现前缀字符集内的首字符时
        self.assertEqual(holdings.to_pure_code("sh600519"), "600519")

    def test_to_sina_code(self):
        cases = {
            "600584": "sh600584",
            "688825": "sh688825",
            "510880": "sh510880",
            "000001": "sz000001",
            "300750": "sz300750",
            "159915": "sz159915",
            "sh600584": "sh600584",
            "sz000001": "sz000001",
        }
        for raw, expected in cases.items():
            self.assertEqual(holdings.to_sina_code(raw), expected, f"输入 {raw!r}")

    def test_to_sina_code_matches_legacy_behaviour(self):
        """与改造前 add_position_analyzer / position_monitor 的行为逐例对照。"""
        def legacy_add_position(code):
            c = code.strip().lstrip("sh").lstrip("sz")
            if c.startswith(("6", "5")):
                return f"sh{c}"
            if c.startswith(("0", "3", "4")):
                return f"sz{c}"
            if c.startswith("8") or c.startswith("9"):
                return f"sh{c}"
            return f"sz{c}"

        def legacy_position_monitor(code):
            c = code.strip().lstrip("sh").lstrip("sz")
            if c.startswith(("6", "5", "8", "9")):
                return f"sh{c}"
            return f"sz{c}"

        for code in ("600584", "688825", "510880", "000001", "300750", "159915", "002415", "900901"):
            new = holdings.to_sina_code(code)
            self.assertEqual(new, legacy_add_position(code), code)
            self.assertEqual(new, legacy_position_monitor(code), code)


class TestHoldingsIO(unittest.TestCase):

    def test_load_holdings_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = support.write_holdings(d, support.sample_holdings())
            data = holdings.load_holdings(path)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["code"], "600584")

    def test_load_holdings_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            data = holdings.load_holdings(Path(d) / "nope.json")
            self.assertEqual(data, [])

    def test_load_holdings_corrupt_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "broken.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(holdings.load_holdings(path), [])

    def test_load_holdings_non_list_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "obj.json"
            path.write_text('{"a": 1}', encoding="utf-8")
            self.assertEqual(holdings.load_holdings(path), [])

    def test_holding_codes_strips_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            rows = support.sample_holdings() + [{"code": "sz300750", "name": "宁德时代"}]
            path = support.write_holdings(d, rows)
            self.assertEqual(holdings.holding_codes(path), {"600584", "300750"})

    def test_find_holding_accepts_both_forms(self):
        rows = support.sample_holdings()
        self.assertIsNotNone(holdings.find_holding("600584", rows))
        self.assertIsNotNone(holdings.find_holding("sh600584", rows))
        self.assertIsNone(holdings.find_holding("000001", rows))

    def test_save_creates_backup_and_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            path = support.write_holdings(d, support.sample_holdings())
            new_rows = support.sample_holdings() + [{"code": "300750", "name": "宁德时代"}]
            holdings.save_holdings(new_rows, path)

            self.assertEqual(len(holdings.load_holdings(path)), 2)
            backups = list((Path(d) / "backup").glob("*_holdings.json"))
            self.assertEqual(len(backups), 1, "写入前必须留一份备份")
            self.assertEqual(len(json.loads(backups[0].read_text(encoding="utf-8"))), 1)

    def test_atomic_write_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cash_balance.json"
            holdings.atomic_write_json(path, {"available_cash": 1.0})
            leftovers = [p for p in Path(d).iterdir() if p.suffix == ".json" and p.name != "cash_balance.json"]
            self.assertEqual(leftovers, [], f"残留临时文件: {leftovers}")

    def test_backup_skipped_when_target_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(holdings.backup_file(Path(d) / "missing.json"))
            self.assertFalse((Path(d) / "backup").exists())

    def test_save_cash_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cash_balance.json"
            holdings.save_cash({"available_cash": 123.45}, path)
            self.assertEqual(holdings.load_cash(path)["available_cash"], 123.45)


if __name__ == "__main__":
    unittest.main()
