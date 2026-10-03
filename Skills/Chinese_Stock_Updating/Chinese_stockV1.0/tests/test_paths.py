#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""common/paths.py：路径推导与环境变量覆盖。"""
from __future__ import annotations

import importlib
import os
import unittest
from pathlib import Path

from tests import support  # noqa: F401  (导入即完成 sys.path 引导)

import paths


class TestPathResolution(unittest.TestCase):

    def test_root_is_repo_root(self):
        self.assertTrue((paths.ROOT / "my_holdings").is_dir())
        self.assertTrue((paths.ROOT / "strategy-fusion-advisor").is_dir())
        self.assertTrue((paths.ROOT / "common" / "paths.py").is_file())

    def test_all_paths_are_absolute(self):
        for name in dir(paths):
            value = getattr(paths, name)
            if isinstance(value, Path) and name.isupper():
                self.assertTrue(value.is_absolute(), f"{name} 不是绝对路径: {value}")

    def test_key_files_exist(self):
        self.assertTrue(paths.HOLDINGS_FILE.is_file())
        self.assertTrue(paths.CASH_FILE.is_file())
        self.assertTrue(paths.WATCHLIST_FILE.is_file())
        self.assertTrue(paths.WATCHLIST_CORE_FILE.is_file())
        self.assertTrue(paths.MARKET_PHASE_FILE.is_file())
        self.assertTrue(paths.FUSION_SCRIPTS_DIR.is_dir())

    def test_recommendations_dir_holds_daily_output(self):
        self.assertTrue(paths.RECO_DIR.is_dir())
        self.assertTrue(any(paths.RECO_DIR.glob("*_buy_recommendation.json")))

    def test_detection_works_from_nested_files(self):
        """任意深度的文件都能推导出同一个 ROOT（这是替换硬编码路径的核心保证）。"""
        candidates = [
            paths.FUSION_SCRIPTS_DIR / "fusion_runner.py",
            paths.HOLDING_SCRIPTS_DIR / "send_holding_card.py",
            paths.ROOT / "gap-fill-strategy" / "skills" / "scripts" / "gap_fill_scanner.py",
            paths.ROOT / "Medium-termHoldingStrategy" / "skills" / "trade_executor.py",
        ]
        for f in candidates:
            self.assertTrue(f.is_file(), f"测试样本缺失: {f}")
            root = f.parent
            while not (root / "common" / "paths.py").exists() and root != root.parent:
                root = root.parent
            self.assertEqual(root, paths.ROOT, f"{f} 推导出的 ROOT 不正确")

    def test_env_override(self):
        original = os.environ.get("STOCK_ROOT")
        try:
            os.environ["STOCK_ROOT"] = str(support.REPO_ROOT)
            reloaded = importlib.reload(paths)
            self.assertEqual(reloaded.ROOT, support.REPO_ROOT.resolve())
        finally:
            if original is None:
                os.environ.pop("STOCK_ROOT", None)
            else:
                os.environ["STOCK_ROOT"] = original
            importlib.reload(paths)

    def test_ensure_dirs_is_idempotent(self):
        paths.ensure_dirs()
        paths.ensure_dirs()
        self.assertTrue(paths.LOG_DIR.is_dir())
        self.assertTrue(paths.ANALYSIS_LOG_DIR.is_dir())


if __name__ == "__main__":
    unittest.main()
