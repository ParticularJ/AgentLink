"""
波段交易系统 - 第一阶段单元测试
"""
import unittest
import sys
import os

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.common.models import (
    Stock, Track, MarketStatus, PositionRating, ChainLevel,
    TrackRating, RotationPhase
)
from src.phase1.market_environment import MarketEnvironmentEvaluator
from src.phase1.track_discovery import TrackDiscovery, TrackSourceData
from src.phase1.filters import Phase1Filter
from src.phase1.scoring import Phase1Scorer


class TestMarketEnvironment(unittest.TestCase):
    """测试大盘环境评估"""

    def setUp(self):
        self.evaluator = MarketEnvironmentEvaluator()

    def test_bull_market(self):
        """测试牛市环境"""
        score = self.evaluator.evaluate(
            rps50=75, rps120=65,
            ma20=4000, ma60=3800, current_index=4100,
            avg_daily_volume_5d=16000,
            rise_fall_ratio=3.5, limit_up_count=100,
            net_inflow_20d=250
        )
        self.assertGreaterEqual(score.total_score, 60)
        self.assertEqual(score.market_status, MarketStatus.BULL)

    def test_bear_market(self):
        """测试熊市环境"""
        score = self.evaluator.evaluate(
            rps50=30, rps120=35,
            ma20=3000, ma60=3200, current_index=2900,
            avg_daily_volume_5d=5000,
            rise_fall_ratio=0.5, limit_up_count=10,
            net_inflow_20d=-100
        )
        self.assertLess(score.total_score, 40)
        self.assertEqual(score.market_status, MarketStatus.BEAR)

    def test_suspend_screening(self):
        """测试暂停初筛"""
        score = self.evaluator.evaluate(
            rps50=30, rps120=35,
            ma20=3000, ma60=3200, current_index=2900,
            avg_daily_volume_5d=5000,
            rise_fall_ratio=0.5, limit_up_count=10,
            net_inflow_20d=-100
        )
        self.assertTrue(self.evaluator.should_suspend_screening(score))


class TestTrackDiscovery(unittest.TestCase):
    """测试赛道发现"""

    def setUp(self):
        self.discovery = TrackDiscovery()

    def test_discover_from_policy(self):
        """测试政策驱动赛道发现"""
        policy_tracks = ["AI芯片", "固态电池", "人形机器人"]
        tracks = self.discovery.discover_from_policy(policy_tracks)
        self.assertEqual(len(tracks), 3)
        self.assertEqual(tracks[0].policy_score, 20.0)

    def test_discover_from_capital(self):
        """测试资金驱动赛道发现"""
        capital_data = [
            TrackSourceData(name="AI芯片", source_type="capital", rps20=90, volume_ratio=0.05),
            TrackSourceData(name="白酒", source_type="capital", rps20=60, volume_ratio=0.02),
        ]
        tracks = self.discovery.discover_from_capital(capital_data)
        self.assertEqual(len(tracks), 1)  # 只有AI芯片满足条件
        self.assertEqual(tracks[0].name, "AI芯片")

    def test_filter_tracks(self):
        """测试赛道过滤"""
        tracks = [
            Track(name="AI芯片", total_score=90, rating=TrackRating.S),
            Track(name="固态电池", total_score=80, rating=TrackRating.A),
            Track(name="白酒", total_score=50, rating=TrackRating.B),
        ]
        filtered = self.discovery.filter_tracks(tracks)
        self.assertLessEqual(len(filtered), 12)


class TestPhase1Filter(unittest.TestCase):
    """测试强制过滤"""

    def setUp(self):
        self.filter = Phase1Filter(MarketStatus.OSCILLATION)

    def test_financial_mines(self):
        """测试财务雷区过滤"""
        stock = Stock(
            code="000001",
            name="测试股票",
            operating_cash_flow_ttm=-100,
            operating_cash_flow_last=-200,
        )
        passed, reason = self.filter.filter_financial_mines(stock)
        self.assertFalse(passed)
        self.assertIn("现金流", reason)

    def test_excessive_rise(self):
        """测试涨幅过滤"""
        stock = Stock(
            code="000001",
            name="测试股票",
            rise_60d=200,  # 超过震荡市150%阈值
        )
        passed, reason = self.filter.filter_excessive_rise(stock)
        self.assertFalse(passed)
        self.assertIn("60日涨幅", reason)

    def test_liquidity(self):
        """测试流动性过滤"""
        stock = Stock(
            code="000001",
            name="测试股票",
            latest_price=3.0,  # 低于5元
            float_market_cap=20,  # 低于30亿
        )
        passed, reason = self.filter.filter_liquidity(stock)
        self.assertFalse(passed)

    def test_pass_all_filters(self):
        """测试通过所有过滤"""
        stock = Stock(
            code="000001",
            name="测试股票",
            latest_price=10.0,
            float_market_cap=100,
            rise_60d=50,
            rise_20d=20,
            avg_volume_20d=10000,
            operating_cash_flow_ttm=100,
            operating_cash_flow_last=200,
            receivables_revenue_ratio=0.3,
            goodwill_total_assets_ratio=0.1,
            net_profit_ttm=100,
            net_profit_last=200,
            interest_bearing_debt_ratio=0.3,
        )
        passed, reason = self.filter.filter(stock)
        self.assertTrue(passed)
        self.assertIsNone(reason)


class TestPhase1Scorer(unittest.TestCase):
    """测试三因子评分"""

    def setUp(self):
        self.scorer = Phase1Scorer(MarketStatus.OSCILLATION)

    def test_industry_momentum(self):
        """测试产业动量评分"""
        stock = Stock(code="000001", name="测试")
        track = Track(name="AI芯片", rating=TrackRating.S)
        score = self.scorer.score_industry_momentum(stock, track, catalyst_count=2)
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 35)

    def test_individual_flexibility(self):
        """测试个股弹性评分"""
        stock = Stock(
            code="000001",
            name="测试",
            float_market_cap=500,
            volatility_60d=45,
        )
        score = self.scorer.score_individual_flexibility(
            stock, historical_avg_rise=50, historical_win_rate=70
        )
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 35)

    def test_safety_margin(self):
        """测试安全边际评分"""
        stock = Stock(code="000001", name="测试", beta=0.9)
        score = self.scorer.score_safety_margin(
            stock, earnings_accelerating=True,
            has_reduction_risk=False, has_unlock_risk=False
        )
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 30)

    def test_total_score(self):
        """测试总分计算"""
        stock = Stock(
            code="000001",
            name="测试",
            float_market_cap=500,
            volatility_60d=45,
            beta=0.9,
        )
        track = Track(name="AI芯片", rating=TrackRating.S)
        score = self.scorer.calculate_total_score(
            stock, track, catalyst_count=2,
            historical_avg_rise=50, historical_win_rate=70,
            earnings_accelerating=True,
            has_reduction_risk=False, has_unlock_risk=False
        )
        self.assertGreaterEqual(score.total_score, 0)
        self.assertLessEqual(score.total_score, 100)

    def test_grade_determination(self):
        """测试档位判定"""
        stock = Stock(
            code="000001",
            name="测试",
            float_market_cap=500,
            beta=0.9,
            position_rating=PositionRating.CORE,
        )
        score = self.scorer.calculate_total_score(
            stock, Track(name="AI芯片", rating=TrackRating.S),
            catalyst_count=2
        )
        score.grade = self.scorer.determine_grade(score, stock, catalyst_count=2)
        self.assertIn(score.grade.value, ["一档", "二档", "三档"])


if __name__ == "__main__":
    unittest.main()
