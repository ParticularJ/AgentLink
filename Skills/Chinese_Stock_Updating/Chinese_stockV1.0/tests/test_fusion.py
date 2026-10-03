#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fusion_runner 的融合打分、板块门控与推荐生成。"""
from __future__ import annotations

import sys
import unittest
from unittest import mock

from tests import support  # noqa: F401

import fusion_runner as fr
import fusion_config as fc


def rec(code, score, weight=1.0, win=0.6, action="run", name=None, strategy="均线多头排列"):
    """构造一条 scan_strategy 产出的推荐记录。"""
    return {
        "stock_code": code,
        "stock_name": name or f"股票{code}",
        "strategy_name": "ma-bullish-strategy",
        "strategy_display": strategy,
        "strategy_win_rate": win,
        "strategy_weight": weight,
        "strategy_score": score,
        "sector": "半导体",
        "sector_phase": "STRONG_UP",
        "sector_action": action,
        "reasons": "测试用理由",
    }


class FusionTestBase(unittest.TestCase):

    def setUp(self):
        self._patches = [
            mock.patch.object(fr, "news_penalty", return_value=(0, [])),
            mock.patch.object(fr, "dangerous_stocks", return_value=[]),
            mock.patch.object(fr, "load_holded_sectors", return_value=set()),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def fuse(self, recs, top_n=5, session="EVENING"):
        return fr.fuse_recommendations(recs, top_n=top_n, session=session)


class TestFusionScoring(FusionTestBase):

    def test_single_strategy_above_threshold_is_kept(self):
        top = self.fuse([rec("600584", 90)])
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0]["strategy_count"], 1)
        self.assertEqual(top[0]["best_score"], 90.0)
        self.assertEqual(top[0]["penalty"], 0)

    def test_low_score_is_filtered(self):
        self.assertEqual(self.fuse([rec("600584", 70)]), [])

    def test_single_strategy_has_no_consistency_bonus(self):
        top = self.fuse([rec("600584", 90)])
        self.assertEqual(top[0]["consistency_bonus"], 0)
        self.assertEqual(top[0]["base_score"], 90.0)

    def test_two_strategies_trigger_bonus(self):
        top = self.fuse([rec("600584", 88), rec("600584", 86, strategy="缺口填充")])
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0]["strategy_count"], 2)
        self.assertEqual(top[0]["consistency_bonus"], fc.CONSISTENCY_BONUS_2)

    def test_three_strategies_trigger_bigger_bonus(self):
        three = self.fuse([rec("600584", 88), rec("600584", 87, strategy="缺口填充"),
                           rec("600584", 86, strategy="突破新高")])
        self.assertEqual(three[0]["strategy_count"], 3)
        self.assertEqual(three[0]["consistency_bonus"], fc.CONSISTENCY_BONUS_3)

    def test_public_score_still_capped_at_100(self):
        """对外契约不变：base_score 仍是 0~100。"""
        two = self.fuse([rec("600584", 88), rec("600584", 87, strategy="缺口填充")])
        self.assertEqual(two[0]["base_score"], 100.0)

    def test_resonance_is_not_lost_after_the_cap(self):
        """修复验证：截断只作用于对外分数，排序信息不再丢失。

        入选门槛是 80 分，再加 22/30 的共振加分必然 >= 102，
        因此 base_score 一定并列 100。修复前排序直接用 base_score，
        于是「2 个策略共振」与「3 个策略共振」被视为同分，top-N 退化为
        按插入顺序截取。现在排序走未截断的 rank_score / base_score_raw。
        """
        two = self.fuse([rec("600584", 88), rec("600584", 87, strategy="缺口填充")])
        three = self.fuse([rec("600584", 88), rec("600584", 87, strategy="缺口填充"),
                           rec("600584", 86, strategy="突破新高")])
        self.assertEqual(two[0]["base_score"], three[0]["base_score"])          # 对外分数仍相同
        self.assertLess(two[0]["base_score_raw"], three[0]["base_score_raw"])   # 原始分不同
        self.assertLess(two[0]["rank_score"], three[0]["rank_score"])           # 排序分不同

    def test_ranking_prefers_more_resonance_on_tie(self):
        """同分并列时，共振更多的标的必须排在前面。"""
        recs = [rec("600001", 88)]
        recs += [rec("600002", 88), rec("600002", 87, strategy="缺口填充"),
                 rec("600002", 86, strategy="突破新高")]
        top = self.fuse(recs, top_n=5)
        self.assertEqual(top[0]["stock_code"], "600002")
        self.assertEqual(top[0]["strategy_count"], 3)

    def test_combined_score_formula(self):
        """combined = base * 0.8 + 贡献 * 0.2，且封顶 100。"""
        top = self.fuse([rec("600584", 90, weight=0.9)])
        row = top[0]
        contribution = (90 * 0.5 + 0.6 * 100 * 0.5) * 0.9
        expected = min(100.0, row["base_score"] * fc.BASE_SCORE_WEIGHT + contribution * fc.CONTRIBUTION_WEIGHT)
        self.assertAlmostEqual(row["combined_score"], round(expected, 2), places=2)
        self.assertAlmostEqual(row["total_contribution"], round(contribution, 2), places=2)

    def test_scores_are_capped_at_100(self):
        top = self.fuse([rec("600584", 100), rec("600584", 100, strategy="缺口填充"),
                         rec("600584", 100, strategy="突破新高")])
        self.assertEqual(top[0]["combined_score"], 100.0)
        self.assertEqual(top[0]["base_score"], 100.0)

    def test_negative_news_penalty_reduces_score(self):
        with mock.patch.object(fr, "news_penalty", return_value=(-30, ["重大利空"])):
            top = self.fuse([rec("600584", 90)])
        self.assertEqual(top, [], "利空扣分后应低于入选门槛")

    def test_positive_penalty_is_capped(self):
        with mock.patch.object(fr, "news_penalty", return_value=(100, [])):
            top = self.fuse([rec("600584", 90)])
        self.assertEqual(top[0]["penalty"], fc.PENALTY_BONUS_CAP)

    def test_dangerous_stock_is_dropped(self):
        with mock.patch.object(fr, "dangerous_stocks",
                               return_value=[{"stock_code": "600584", "stock_name": "长电科技"}]):
            self.assertEqual(self.fuse([rec("600584", 95)]), [])

    def test_run_low_requires_higher_score(self):
        low = self.fuse([rec("600584", 82, action="run_low")])
        high = self.fuse([rec("600584", 95, action="run_low")])
        self.assertEqual(low, [], "run_low 板块需要 >= 85 分")
        self.assertEqual(len(high), 1)

    def test_held_sector_bonus_applied(self):
        with mock.patch.object(fr, "load_holded_sectors", return_value={"半导体"}):
            top = self.fuse([rec("600584", 88)])
        self.assertEqual(top[0]["sector_held_bonus"], fc.HELD_SECTOR_BONUS)

    def test_results_sorted_desc(self):
        top = self.fuse([rec("600001", 82), rec("600002", 95), rec("600003", 88)])
        scores = [r["combined_score"] for r in top]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_morning_bonus_only_for_strong_signal(self):
        evening = self.fuse([rec("600584", 95)], session="EVENING")
        morning = self.fuse([rec("600584", 95)], session="MORNING")
        self.assertGreaterEqual(morning[0]["combined_score"], evening[0]["combined_score"])


class TestPositionSizing(FusionTestBase):

    def test_positions_are_within_bounds_and_descending(self):
        recs = [rec(f"60000{i}", 95 - i) for i in range(5)]
        top = self.fuse(recs, top_n=5)
        self.assertTrue(top)
        positions = [r["position_pct"] for r in top]
        self.assertEqual(positions, sorted(positions, reverse=True))
        for pct in positions:
            self.assertGreaterEqual(pct, fc.POSITION_MIN * 100 - 1e-6)
            self.assertLessEqual(pct, fc.POSITION_MAX * 100 + 1e-6)
        for r in top:
            self.assertAlmostEqual(r["position_value"], r["position_pct"] / 100, places=4)

    def test_top_n_limits_output(self):
        recs = [rec(f"6000{i:02d}", 95) for i in range(10)]
        self.assertEqual(len(self.fuse(recs, top_n=3)), 3)


class TestETFDetection(unittest.TestCase):

    def test_etf_codes(self):
        for code in ("sh510880", "sh512480", "sz159915", "sh588000", "sz159995", "sh515180"):
            self.assertTrue(fr._is_etf_code(code), code)

    def test_stock_codes(self):
        for code in ("sh600584", "sz000001", "sz300750", "sh688825"):
            self.assertFalse(fr._is_etf_code(code), code)

    def test_raw_length_guard(self):
        self.assertFalse(fr._is_etf_code("600"))


class TestModuleIsolation(unittest.TestCase):

    def test_heavy_modules_are_not_imported_eagerly(self):
        """config 层不能因为 import 就把新闻/财报模块拉起来（离线可测的前提）。"""
        self.assertNotIn("test_news", [m for m in sys.modules if m == "test_news"] or [],
                         "fusion_runner 不应在 import 期加载 test_news")

    def test_news_penalty_degrades_gracefully_without_deps(self):
        with mock.patch.dict(sys.modules, {"test_news": None}):
            penalty, reason = fr.news_penalty("600584", "长电科技")
        self.assertEqual(penalty, 0)
        self.assertEqual(reason, [])

    def test_dangerous_stocks_degrades_gracefully(self):
        with mock.patch.dict(sys.modules, {"earnings_caculate": None}):
            self.assertEqual(fr.dangerous_stocks(), [])


class TestMarketPhaseLoading(unittest.TestCase):

    def test_missing_file_returns_unknown(self):
        with mock.patch.object(fr, "MARKET_PHASE_FILE", "/nonexistent/market_phase.json"):
            info = fr.load_market_phase()
        self.assertEqual(info["phase"], "UNKNOWN")
        self.assertFalse(info["has_sector_data"])
        self.assertIn("不存在", info["error"])

    def test_real_market_phase_file_parses(self):
        info = fr.load_market_phase()
        self.assertIn(info["phase"], ("STRONG_UP", "WAVE_UP", "RANGE", "STRONG_DOWN", "UNKNOWN"))
        self.assertTrue(info["has_sector_data"], "真实 market_phase.json 应能解析出板块状态")
        self.assertGreater(len(info["sector_phases"]), 20)

    def test_etf_recommendations_follow_configured_phases(self):
        """ETF 推荐档位由 ETF_TRADABLE_PHASES 控制。

        模块1 复审实测（非重叠抽样）：板块 RANGE 的 ETF 未来 T+10 +1.64%/上涨率 60%，
        优于 STRONG_UP 的 +0.44%/46.7%，因此 RANGE 也纳入可推档位；
        原先硬编码只推 STRONG_UP，等于把最好的档位闲置。
        """
        info = fr.load_market_phase()
        recs = fr.collect_strong_up_etf_recommendations(info)
        allowed = set(fc.ETF_TRADABLE_PHASES)
        for r in recs:
            self.assertIn(r["sector_phase"], allowed)
            self.assertTrue(r["is_etf"])
            self.assertTrue(r["stock_code"][:2] in ("sh", "sz"))

    def test_untradable_phases_are_not_recommended(self):
        """STRONG_DOWN / WEAK_DOWN / UNKNOWN 绝不推 ETF。"""
        for ph in ("STRONG_DOWN", "WEAK_DOWN", "UNKNOWN"):
            self.assertNotIn(ph, fc.ETF_TRADABLE_PHASES)
            info = {"phase": "STRONG_UP", "sectors_detail": [
                {"sector": "油气", "stable_phase": ph,
                 "meta": {"etf_codes": ["sz159309"]}, "indicator": {}}]}
            self.assertEqual(fr.collect_strong_up_etf_recommendations(info), [])

    def test_range_sector_etf_is_not_recommended_by_default(self):
        """RANGE 板块的 ETF 默认不推。

        复审曾实测把 RANGE 纳入可推档位（依据：RANGE ETF 未来 T+10 +1.64%
        优于 STRONG_UP 的 +0.44%），但整体回测反而变差
        （84 笔/+5.53% → 88 笔/+4.60%），故回退。
        组级别优势无法在组合层面兑现 —— 与第五轮 reserve 实验结论一致。
        """
        self.assertEqual(fc.ETF_TRADABLE_PHASES, ("STRONG_UP",))
        info = {"phase": "STRONG_UP", "sectors_detail": [
            {"sector": "油气", "stable_phase": "RANGE",
             "meta": {"etf_codes": ["sz159309"]},
             "indicator": {"gain_20d": 0.01, "ma20_slope_5d_pct": 0.1, "n_above_ma60": 5}}]}
        self.assertEqual(fr.collect_strong_up_etf_recommendations(info), [])

    def test_etf_recommendation_shape(self):
        info = {
            "phase": "STRONG_UP",
            "sectors_detail": [{
                "sector": "油气",
                "phase": "STRONG_UP",
                "stable_phase": "STRONG_UP",
                "meta": {"etf_codes": ["sz159309"]},
                "indicator": {"gain_20d": 0.052, "ma20_slope_5d_pct": 1.54, "n_above_ma60": 28},
            }],
        }
        recs = fr.collect_strong_up_etf_recommendations(info)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["stock_code"], "sz159309")
        self.assertEqual(recs[0]["combined_score"], fc.ETF_BASE_SCORE)
        self.assertEqual(recs[0]["position_pct"], fc.ETF_POSITION_BY_MARKET_PHASE["STRONG_UP"])

    def test_etf_recommendation_skips_non_etf_codes(self):
        info = {"phase": "STRONG_UP", "sectors_detail": [
            {"sector": "半导体", "stable_phase": "STRONG_UP",
             "meta": {"etf_codes": ["sh600584"]}, "indicator": {}},
        ]}
        self.assertEqual(fr.collect_strong_up_etf_recommendations(info), [])


class TestConfigTables(unittest.TestCase):

    def test_enabled_strategies_exist_as_directories(self):
        for name in fc.EVENING_STRATEGIES + fc.MORNING_STRATEGIES:
            self.assertIn(name, fc.ANALYZER_CLASS, f"{name} 缺少 analyzer 映射")
            self.assertTrue((support.REPO_ROOT / name).is_dir(), f"{name} 目录不存在")

    def test_unknown_sector_never_trades(self):
        for table in (fc.PHASE_SECTOR_FILTER_STOCK, fc.PHASE_SECTOR_FILTER_ETF):
            self.assertEqual(table["UNKNOWN"], "block")
            self.assertEqual(table["WEAK_DOWN"], "block")

    def test_stock_blocked_in_downtrend(self):
        self.assertEqual(fc.PHASE_SECTOR_FILTER_STOCK["STRONG_DOWN"], "block")
        self.assertEqual(fc.PHASE_SECTOR_FILTER_ETF["STRONG_DOWN"], "run_low")

    def test_position_caps_monotonic(self):
        caps = fc.PHASE_POSITION_CAP
        self.assertGreaterEqual(caps["STRONG_UP"], caps["RANGE"])
        self.assertGreaterEqual(caps["RANGE"], caps["STRONG_DOWN"])


if __name__ == "__main__":
    unittest.main()
