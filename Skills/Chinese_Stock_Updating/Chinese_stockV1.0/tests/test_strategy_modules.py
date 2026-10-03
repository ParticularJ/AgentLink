#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略模块的离线冒烟测试：
  - 各 analyzer 能被 import、类与入口方法齐全
  - 纯计算部分（均线、多头判定）在合成数据上给出正确结论
  - fusion_runner 能动态加载已启用的三个策略

不联网、不依赖 akshare/pytdx（缺失时由 tests/support.py 打桩）。
"""
from __future__ import annotations

import unittest

from tests import support  # noqa: F401


class TestMABullishAnalyzer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import sys

        from tests.support import REPO_ROOT

        path = str(REPO_ROOT / "ma-bullish-strategy" / "skills" / "scripts")
        if path not in sys.path:
            sys.path.insert(0, path)
        import ma_bullish_strategy_analyzer as mod

        cls.mod = mod
        cls.analyzer = mod.MABullishAnalyzer()

    def test_market_environment_score_in_range(self):
        score = self.mod.MarketEnvironment().get_market_score()
        self.assertIsInstance(score, (int, float))
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_scan_and_analyze_api_present(self):
        for name in ("scan_all_stocks", "analyze_stock", "calculate_ma", "is_ma_bullish"):
            self.assertTrue(callable(getattr(self.analyzer, name)), name)

    def test_realtime_datasource_is_preferred(self):
        """get_stock_realtime 可用时不应再构造 DataSourceAdapter（pytdx 已失效）。"""
        if self.mod._HAS_REALTIME and self.mod.get_stock_realtime is not None:
            self.assertIsNone(self.analyzer.data_adapter)

    def test_get_stock_data_falls_back_safely(self):
        """两条数据链路都不可用时返回 None，而不是抛异常。"""
        with self.subTest("no datasource"):
            saved_realtime, saved_adapter = self.mod._HAS_REALTIME, self.analyzer.data_adapter
            try:
                self.mod._HAS_REALTIME = False
                self.analyzer.data_adapter = None
                self.assertIsNone(self.analyzer._get_stock_data("600584"))
            finally:
                self.mod._HAS_REALTIME = saved_realtime
                self.analyzer.data_adapter = saved_adapter

    def test_calculate_ma_adds_expected_columns(self):
        df = support.make_kline(support.linear_closes(80, 10.0, 0.3))
        out = self.analyzer.calculate_ma(df)
        for col in ("ma5", "ma10", "ma20"):
            self.assertIn(col, out.columns)

    def test_uptrend_is_judged_bullish(self):
        df = self.analyzer.calculate_ma(support.make_kline(support.linear_closes(80, 10.0, 0.3)))
        self.assertTrue(self.analyzer.is_ma_bullish(df))

    def test_flat_market_is_not_bullish(self):
        closes = [10.0 + (i % 2) * 0.01 for i in range(80)]
        df = self.analyzer.calculate_ma(support.make_kline(closes))
        self.assertFalse(self.analyzer.is_ma_bullish(df))

    def test_load_holdings_uses_shared_loader(self):
        self.assertIsInstance(self.analyzer._load_holdings(), set)

    def test_load_watchlist_returns_dataframe(self):
        df = self.analyzer._load_watchlist()
        self.assertIsNotNone(df)
        self.assertIn("code", df.columns)
        self.assertGreater(len(df), 50)


class TestLimitUpAnalyzer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import sys

        from tests.support import REPO_ROOT

        path = str(REPO_ROOT / "limit-up-analysis" / "skills" / "scripts")
        if path not in sys.path:
            sys.path.insert(0, path)
        import limit_up_analysis_analyzer as mod

        cls.mod = mod

    def test_classes_present(self):
        self.assertTrue(hasattr(self.mod, "LimitUpAnalyzer"))
        self.assertTrue(hasattr(self.mod, "StockDataFetcher"))

    def test_entry_method_present(self):
        self.assertTrue(callable(getattr(self.mod.LimitUpAnalyzer, "analyze_all_limit_up")))

    def test_analyzer_constructs(self):
        self.assertIsNotNone(self.mod.LimitUpAnalyzer())


class TestEarningsDataFetcher(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import sys

        from tests.support import REPO_ROOT

        path = str(REPO_ROOT / "earnings-surprise-strategy" / "skills" / "scripts")
        if path not in sys.path:
            sys.path.insert(0, path)
        import data_fetcher as mod

        cls.mod = mod
        cls.fetcher = mod.EarningsDataFetcher()

    def test_helper_methods_present(self):
        for name in ("_to_full_code", "_parse_number", "_get_quarter_from_date"):
            self.assertTrue(callable(getattr(self.fetcher, name)), name)

    def test_watchlist_codes_come_from_shared_loader(self):
        codes = self.fetcher._load_watchlist_codes()
        self.assertIsInstance(codes, list)
        self.assertGreater(len(codes), 50)

    def test_to_full_code(self):
        self.assertEqual(self.fetcher._to_full_code("600584"), "sh600584")
        self.assertEqual(self.fetcher._to_full_code("000001"), "sz000001")


class TestFusionCanLoadStrategies(unittest.TestCase):

    def test_enabled_strategies_resolve(self):
        import sys

        from tests.support import REPO_ROOT

        path = str(REPO_ROOT / "strategy-fusion-advisor" / "skills" / "scripts")
        if path not in sys.path:
            sys.path.insert(0, path)
        import fusion_config
        import fusion_runner

        for name in fusion_config.EVENING_STRATEGIES + fusion_config.MORNING_STRATEGIES:
            analyzer = fusion_runner.get_analyzer(name)
            self.assertIsNotNone(analyzer, f"{name} 的 analyzer 未能加载")
            self.assertTrue(callable(getattr(analyzer, "scan_all_stocks", None))
                            or callable(getattr(analyzer, "analyze_all_limit_up", None))
                            or callable(getattr(analyzer, "scan_daily_earnings", None)), name)


if __name__ == "__main__":
    unittest.main()
