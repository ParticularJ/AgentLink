"""
波段交易系统 - 第二阶段单元测试
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.common.models import (
    Stock, IndustryType, MoatLevel, ValuationConclusion,
    FinalDecision, Grade, MoatScore, MarketStatus
)
from src.phase2.moat import MoatEvaluator
from src.phase2.veto import VetoChecker
from src.phase2.financial import FinancialScorer
from src.phase2.valuation import ValuationEvaluator
from src.phase2.position import PositionCalculator


class TestMoatEvaluator(unittest.TestCase):
    """测试护城河评估"""

    def setUp(self):
        self.evaluator = MoatEvaluator(IndustryType.TECH_GROWTH)

    def test_strong_moat(self):
        """测试强护城河"""
        score = self.evaluator.evaluate(
            gross_margin=45,
            industry_avg_margin=30,
            rd_ratio=12,
            top5_customer_ratio=30,
            net_profit_cash_ratio=110,
            renewal_rate=85,
        )
        self.assertGreaterEqual(score.total_score, 14)
        self.assertEqual(score.level, MoatLevel.STRONG)

    def test_weak_moat(self):
        """测试弱护城河"""
        score = self.evaluator.evaluate(
            gross_margin=20,
            industry_avg_margin=30,
            rd_ratio=2,
            top5_customer_ratio=90,
            net_profit_cash_ratio=40,
        )
        self.assertLess(score.total_score, 9)
        self.assertEqual(score.level, MoatLevel.WEAK)

    def test_position_adjustment(self):
        """测试仓位调整"""
        score = MoatScore(total_score=16, level=MoatLevel.STRONG)
        coef, conclusion = self.evaluator.get_position_adjustment(score)
        self.assertEqual(coef, 1.0)
        self.assertEqual(conclusion, "通过")


class TestVetoChecker(unittest.TestCase):
    """测试一票否决"""

    def setUp(self):
        self.checker = VetoChecker(MarketStatus.OSCILLATION)

    def test_management_violation(self):
        """测试管理层违规"""
        result = self.checker.check(has_violation=True)
        self.assertFalse(result.passed)
        self.assertIn("违规", result.triggered_item)

    def test_northbound_outflow(self):
        """测试北向资金流出"""
        result = self.checker.check(
            northbound_outflow_days=5,
            northbound_outflow_amount=5000
        )
        self.assertFalse(result.passed)
        self.assertIn("北向", result.triggered_item)

    def test_pass_all(self):
        """测试全部通过"""
        result = self.checker.check()
        self.assertTrue(result.passed)


class TestFinancialScorer(unittest.TestCase):
    """测试财报评分"""

    def setUp(self):
        self.scorer = FinancialScorer(IndustryType.TECH_GROWTH)

    def test_excellent_financials(self):
        """测试优秀财报"""
        score = self.scorer.evaluate(
            revenue_growth=50,
            profit_growth=60,
            last_profit_growth=40,
            net_profit_cash_ratio=120,
            roe=25,
            actual_profit=100,
            expected_profit=80,
            rating_upgraded=True,
        )
        self.assertGreaterEqual(score.total_score, 45)

    def test_poor_financials(self):
        """测试差财报"""
        score = self.scorer.evaluate(
            revenue_growth=5,
            profit_growth=-10,
            last_profit_growth=20,
            net_profit_cash_ratio=40,
            roe=5,
            actual_profit=80,
            expected_profit=100,
            rating_downgraded=True,
        )
        self.assertLess(score.total_score, 30)

    def test_surprise_scoring(self):
        """测试超预期评分"""
        score = self.scorer.score_surprise(actual_profit=120, expected_profit=100)
        self.assertEqual(score, 8.0)  # 超预期20%


class TestValuationEvaluator(unittest.TestCase):
    """测试估值评估"""

    def setUp(self):
        self.evaluator = ValuationEvaluator(IndustryType.TECH_GROWTH)

    def test_peg_undervalued(self):
        """测试PEG低估"""
        conclusion, coefficient = self.evaluator.evaluate_peg(pe_ttm=20, profit_growth=40)
        # PEG = 20/40 = 0.5 < 0.6, 严重低估
        self.assertEqual(conclusion, ValuationConclusion.SEVERELY_UNDERVALUED)
        self.assertEqual(coefficient, 1.0)

    def test_peg_overvalued(self):
        """测试PEG高估"""
        conclusion, coefficient = self.evaluator.evaluate_peg(pe_ttm=80, profit_growth=20)
        self.assertEqual(conclusion, ValuationConclusion.HIGHLY_OVERVALUED)
        self.assertEqual(coefficient, 0.0)

    def test_pb_roe(self):
        """测试PB-ROE"""
        conclusion, coefficient = self.evaluator.evaluate_pb_roe(pb_mrq=2, roe_ttm=20)
        # 合理PB = 20 * 100 * 0.9 = 18, 实际PB=2, 溢价率 = 2/18 - 1 = -89% < -40%, 严重低估
        self.assertEqual(conclusion, ValuationConclusion.SEVERELY_UNDERVALUED)
        self.assertEqual(coefficient, 1.0)

    def test_ps_valuation(self):
        """测试PS估值"""
        conclusion, coefficient = self.evaluator.evaluate_ps(ps_ttm=5, revenue_growth=50)
        # 合理PS = 50 * 0.3 = 15, 实际PS=5, 比值 = 5/15 = 0.33 < 0.5, 严重低估
        self.assertEqual(conclusion, ValuationConclusion.SEVERELY_UNDERVALUED)
        self.assertEqual(coefficient, 1.0)

    def test_historical_percentile(self):
        """测试历史分位点"""
        percentile = self.evaluator.evaluate_historical_percentile(
            current_valuation=25,
            historical_values=[10, 15, 20, 25, 30, 35, 40]
        )
        self.assertGreater(percentile, 0)
        self.assertLess(percentile, 100)


class TestPositionCalculator(unittest.TestCase):
    """测试仓位计算"""

    def setUp(self):
        self.calculator = PositionCalculator()

    def test_base_position_golden(self):
        """测试黄金机会基准仓位"""
        base = self.calculator.calculate_base_position(
            financial_score=50,
            valuation_conclusion=ValuationConclusion.SEVERELY_UNDERVALUED,
            surprise_score=10,
        )
        self.assertEqual(base, 8.0)

    def test_final_position_calculation(self):
        """测试最终仓位计算"""
        final = self.calculator.calculate_final_position(
            base_position=8.0,
            valuation_coefficient=1.0,
            moat_coefficient=1.0,
            grade=Grade.FIRST,
        )
        self.assertLessEqual(final, 8.0)
        self.assertGreaterEqual(final, 0.0)

    def test_stop_loss(self):
        """测试止损位"""
        stop_loss, time_stop = self.calculator.calculate_stop_loss(beta=0.8)
        self.assertEqual(stop_loss, -7)
        self.assertEqual(time_stop, 12)

    def test_high_beta_stop_loss(self):
        """测试高Beta止损"""
        stop_loss, time_stop = self.calculator.calculate_stop_loss(beta=1.6)
        self.assertEqual(stop_loss, -4)
        self.assertEqual(time_stop, 6)

    def test_decision_reject(self):
        """测试剔除决策"""
        decision = self.calculator.determine_final_decision(
            financial_score=30,
            pass_score=35,
            veto_passed=True,
            final_position=5.0,
            valuation_conclusion=ValuationConclusion.FAIR,
        )
        self.assertEqual(decision, FinalDecision.REJECT)


if __name__ == "__main__":
    unittest.main()
