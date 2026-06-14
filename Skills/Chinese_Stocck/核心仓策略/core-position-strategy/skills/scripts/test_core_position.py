"""
核心仓交易系统 - 单元测试
严格验证是否符合《核心仓策略 V3.0》四份设计文档
"""
import unittest
import sys
import os
from datetime import datetime, timedelta

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import (
    MacroLiquidity, MacroEnvironment, MarketContext, MarketStatus,
    SectorRating, SectorLifecycle, StockInitialScore, StockSecondaryScore,
    FinancialReport, EarningsVerification, SignalLevel,
    CorePosition, PositionStatus, BuyPointType, BuyPointQuality,
    BuyPointSignal, DailyTechMonitor, WeeklyFundamentalMonitor, MonitorSignal
)
from macro_filter import MacroFilter
from sector_scorer import SectorScorer
from initial_scorer import InitialScorer
from secondary_scorer import SecondaryScorer
from buy_signal import BuySignalDetector
from position_monitor import PositionMonitor
from portfolio_manager import CorePortfolioManager
from core_position_pipeline import CorePositionPipeline


class TestMacroFilter(unittest.TestCase):
    """测试宏观流动性过滤器"""

    def setUp(self):
        self.filter = MacroFilter()

    def test_expansion_environment(self):
        """测试扩张期判断"""
        macro = self.filter.evaluate({
            'social_financing_growth': 15.0,
            'social_financing_mom_change': 2.0,
            'treasury_yield_10y': 2.5,
            'risk_premium': 2.5
        })
        self.assertEqual(macro.environment, MacroEnvironment.EXPANSION)
        self.assertGreater(macro.win_rate_adjustment, 0)

    def test_contraction_environment(self):
        """测试收缩期判断 - 应暂停建仓"""
        macro = self.filter.evaluate({
            'social_financing_growth': 5.0,
            'social_financing_mom_change': -1.0,
            'treasury_yield_10y': 3.5,
            'risk_premium': 6.0
        })
        self.assertEqual(macro.environment, MacroEnvironment.CONTRACTION)

        can_proceed, reason, adjustment = self.filter.can_proceed(macro)
        self.assertFalse(can_proceed)
        self.assertIn("收缩期", reason)
        self.assertLess(adjustment, 0)

    def test_stable_environment(self):
        """测试稳定期"""
        macro = self.filter.evaluate({
            'social_financing_growth': 10.0,
            'social_financing_mom_change': 0.5,
            'treasury_yield_10y': 3.0,
            'risk_premium': 4.0
        })
        self.assertEqual(macro.environment, MacroEnvironment.STABLE)

        can_proceed, reason, adjustment = self.filter.can_proceed(macro)
        self.assertTrue(can_proceed)


class TestSectorScorer(unittest.TestCase):
    """测试赛道评分器"""

    def setUp(self):
        self.scorer = SectorScorer()
        self.macro = MacroLiquidity(
            social_financing_growth=12.0,
            treasury_yield_10y=2.8,
            risk_premium=3.0
        )

    def test_early_explosion_sector(self):
        """测试爆发初期赛道"""
        sector = self.scorer.score({
            'sector_name': 'AI算力',
            'penetration_rate': 8.0,
            'policy_strength_score': 90.0,
            'foreign_consensus_score': 85.0,
            'capex_score': 80.0
        }, self.macro)

        self.assertEqual(sector.lifecycle, SectorLifecycle.EARLY_EXPLOSION)
        self.assertIn(sector.rating, ['S', 'A'])
        self.assertGreaterEqual(sector.max_allocation_pct, 0.15)

    def test_mature_sector(self):
        """测试成熟期赛道 - 应排除"""
        sector = self.scorer.score({
            'sector_name': '传统制造',
            'penetration_rate': 50.0,
            'policy_strength_score': 40.0,
            'foreign_consensus_score': 30.0,
            'capex_score': 20.0
        }, self.macro)

        self.assertEqual(sector.lifecycle, SectorLifecycle.MATURE)
        self.assertEqual(sector.max_allocation_pct, 0.05)

    def test_filter_target_sectors(self):
        """测试赛道过滤"""
        sectors = [
            SectorRating(sector_name='AI', lifecycle=SectorLifecycle.EARLY_EXPLOSION),
            SectorRating(sector_name='传统', lifecycle=SectorLifecycle.MATURE),
            SectorRating(sector_name='机器人', lifecycle=SectorLifecycle.INTRODUCTION),
        ]

        targets = self.scorer.filter_target_sectors(sectors)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].sector_name, 'AI')


class TestInitialScorer(unittest.TestCase):
    """测试个股初筛评分器"""

    def setUp(self):
        self.scorer = InitialScorer()

    def test_perfect_stock(self):
        """测试满分股票"""
        score = self.scorer.score({
            'code': '000001',
            'name': '测试股',
            'sector': 'AI算力',
            'sector_heat_score': 90.0,
            'chain_position_score': 85.0,
            'tech_barrier_score': 80.0,
            'earnings_certainty_score': 75.0,
            'management_quality_score': 70.0,
            'institution_consensus_score': 60.0,
            'management_violation_2y': False,
            'analyst_coverage_count': 5,
            'revenue_decline_quarters': 0,
            'revenue_decline_pct': 0,
            'daily_avg_volume': 3.0,
            'goodwill_to_net_asset': 0.1,
            'pledge_ratio': 20.0,
            'roe_y1': 15.0,
            'roe_y2': 12.0,
            'audit_opinion': '标准无保留'
        })

        self.assertTrue(score.veto_passed)
        self.assertGreater(score.total_score, 70)

    def test_management_violation_veto(self):
        """测试管理层违规一票否决 - V3.0新增"""
        score = self.scorer.score({
            'code': '000002',
            'name': '违规股',
            'sector': 'AI算力',
            'management_violation_2y': True,
            'analyst_coverage_count': 5,
            'daily_avg_volume': 3.0,
            'roe_y1': 15.0,
            'roe_y2': 12.0,
        })

        self.assertFalse(score.veto_passed)
        self.assertIn("违规", score.veto_reason)

    def test_low_coverage_veto(self):
        """测试机构覆盖不足一票否决"""
        score = self.scorer.score({
            'code': '000003',
            'name': '冷门股',
            'sector': 'AI算力',
            'management_violation_2y': False,
            'analyst_coverage_count': 1,
            'daily_avg_volume': 3.0,
            'roe_y1': 15.0,
            'roe_y2': 12.0,
        })

        self.assertFalse(score.veto_passed)
        self.assertIn("覆盖", score.veto_reason)

    def test_low_roe_veto(self):
        """测试ROE不足一票否决"""
        score = self.scorer.score({
            'code': '000004',
            'name': '低ROE股',
            'sector': 'AI算力',
            'management_violation_2y': False,
            'analyst_coverage_count': 5,
            'daily_avg_volume': 3.0,
            'roe_y1': 5.0,
            'roe_y2': 6.0,
        })

        self.assertFalse(score.veto_passed)
        self.assertIn("ROE", score.veto_reason)


class TestSecondaryScorer(unittest.TestCase):
    """测试二次筛选评分器"""

    def setUp(self):
        self.scorer = SecondaryScorer()

    def test_perfect_financial_report(self):
        """测试满分财报"""
        report = FinancialReport(
            revenue_growth=80.0,
            profit_growth=100.0,
            gross_margin_trend=5.0,
            cash_flow_to_profit=1.2,
            guidance_adjustment="上调",
            order_visibility="饱满"
        )

        score = self.scorer.score_financial(report)
        self.assertGreaterEqual(score, 90)

    def test_cash_flow_veto(self):
        """测试现金流连续为负一票否决"""
        report = FinancialReport(
            cash_flow_negative_quarters=2,
            revenue_growth=30.0,
            profit_growth=40.0
        )

        risk = self.scorer.check_risk(report)
        self.assertTrue(risk['should_veto'])

    def test_expectation_verification(self):
        """测试超预期验证"""
        verification = EarningsVerification(
            price_reaction=True,
            analyst_reaction=True,
            volume_reaction=True,
            northbound_inflow=True
        )

        self.assertEqual(verification.match_count, 4)
        self.assertEqual(verification.win_rate, 0.88)

        score = self.scorer.calculate_expectation_score(verification)
        self.assertEqual(score, 100.0)

    def test_comprehensive_score(self):
        """测试综合评分计算"""
        secondary = StockSecondaryScore(
            stock_code="000001",
            stock_name="测试股",
            sector="AI算力",
            initial_score=85.0,
            financial_score=90.0,
            expectation_score=85.0
        )

        # 综合 = 85*0.35 + 90*0.40 + 85*0.25 = 29.75 + 36 + 21.25 = 87
        expected = 85 * 0.35 + 90 * 0.40 + 85 * 0.25
        self.assertAlmostEqual(secondary.total_score, expected, places=1)
        self.assertEqual(secondary.signal_level, SignalLevel.BUY)


class TestBuySignalDetector(unittest.TestCase):
    """测试买点识别器"""

    def setUp(self):
        self.detector = BuySignalDetector()

    def test_ideal_buy_point(self):
        """测试理想买点"""
        signal = self.detector.detect_buy_point("000001", "测试股", {
            'ma20': 105.0, 'ma60': 100.0, 'ma120': 95.0,
            'ma20_trend': 'up', 'ma60_trend': 'up', 'ma120_trend': 'up',
            'recent_high': 110.0, 'current_price': 100.0,  # 回调9%
            'volume': 5000, 'volume_ma20': 10000,  # 缩量50%
            'days_not_new_low': 3,
            'rsi': 45,
            'atr_14_pct': 3.0,
            'is_pullback_ma20': True
        })

        self.assertIsNotNone(signal)
        self.assertEqual(signal.quality, BuyPointQuality.IDEAL)
        self.assertTrue(signal.all_necessary_passed)
        self.assertTrue(signal.atr_volatility_pass)

    def test_weak_market_no_trade(self):
        """测试弱势市场暂停建仓"""
        market = MarketContext(
            index_price=2800, ma60=3000, ma250=3100,
            volume=5000, advance_decline_ratio=0.8, vix=30
        )

        can_trade, reason, coeff = self.detector.check_market_environment(market)
        self.assertFalse(can_trade)
        self.assertEqual(coeff, 0.0)

    def test_position_size_calculation(self):
        """测试仓位计算"""
        candidate = StockSecondaryScore(
            stock_code="000001",
            stock_name="测试股",
            sector="AI算力",
            initial_score=90.0,
            financial_score=95.0,
            expectation_score=90.0
        )

        buy_point = BuyPointSignal(
            stock_code="000001",
            stock_name="测试股",
            quality=BuyPointQuality.IDEAL,
            ma_alignment_pass=True,
            pullback_pct=8.0,
            volume_shrink_pass=True,
            price_stabilize_pass=True
        )

        market = MarketContext(
            index_price=3200, ma60=3100, ma250=3000,
            volume=12000, advance_decline_ratio=2.0, vix=15
        )

        position_pct = self.detector.calculate_position_size(
            candidate, buy_point, market
        )

        # ≥90分 → 1.0, 理想买点 → 1.0, 强势市场 → 1.0
        # 仓位上限18% * 1.0 * 1.0 * 1.0 = 18%
        self.assertGreater(position_pct, 0)
        self.assertLessEqual(position_pct, 0.18)

    def test_final_checklist(self):
        """测试最终确认清单"""
        buy_point = BuyPointSignal(
            stock_code="000001",
            stock_name="测试股",
            ma_alignment_pass=True,
            pullback_pct=8.0,
            volume_shrink_pass=True,
            price_stabilize_pass=True
        )

        checklist = self.detector.final_checklist({
            'penetration_rate': 12.0,
            'revenue_growth': 30.0,
            'profit_growth': 50.0,
            'analyst_coverage': 8,
            'expectation_conservative': True,
            'peg_ratio': 1.2,
            'is_credit_contraction': False
        }, buy_point)

        self.assertTrue(self.detector.can_execute_buy(checklist))
        self.assertTrue(all(checklist.values()))


class TestPositionMonitor(unittest.TestCase):
    """测试持仓监控器"""

    def setUp(self):
        self.monitor = PositionMonitor()
        self.position = CorePosition(
            stock_code="000001",
            stock_name="测试股",
            sector="AI算力",
            entry_price=100.0,
            initial_shares=1000,
            initial_position_pct=0.10,
            fixed_stop_loss_price=90.0,
            entry_atr=3.0,  # ATR=3, 止损位=100-6=94
            remaining_shares=1000,
            remaining_position_pct=0.10
        )

    def test_atr_stop_loss(self):
        """测试ATR自适应止损"""
        # ATR=3, 止损位=100-2*3=94
        signals = self.monitor.check_stop_loss(self.position, 93.0)

        atr_signals = [s for s in signals if "ATR" in s.signal_desc]
        self.assertEqual(len(atr_signals), 1)
        self.assertEqual(atr_signals[0].urgency, "urgent")

    def test_fixed_stop_loss(self):
        """测试固定止损"""
        signals = self.monitor.check_stop_loss(self.position, 89.0)

        fixed_signals = [s for s in signals if "固定" in s.signal_desc]
        self.assertEqual(len(fixed_signals), 1)

    def test_moving_stop_loss(self):
        """测试移动止损"""
        # 先涨到120
        self.position.highest_price = 120.0
        # 从120回撤6%到112.8
        signals = self.monitor.check_stop_loss(self.position, 112.0)

        moving_signals = [s for s in signals if "回撤" in s.signal_desc]
        self.assertEqual(len(moving_signals), 1)

    def test_take_profit_levels(self):
        """测试止盈层级"""
        market = MarketContext(
            index_price=3200, ma60=3100, ma250=3000,
            volume=12000, vix=15
        )

        # 价格涨到130（浮盈30%）
        signals = self.monitor.check_take_profit(self.position, 130.0, market)

        # 应触发15%和25%两个止盈层级
        profit_signals = [s for s in signals if s.signal_type == "TAKE_PROFIT"]
        self.assertGreaterEqual(len(profit_signals), 2)

    def test_add_position_check(self):
        """测试加仓检查"""
        # 浮盈25%
        tech_data = {
            'is_pullback_ma20': True,
            'volume_shrink_pct': 50.0,  # 缩量50%
            'ma20_trend': 'up'
        }
        sector_data = {
            'sector_vs_index': 1.05,  # 板块强于大盘
            'earnings_beat': True
        }

        signal = self.monitor.check_add_position(
            self.position, 125.0, tech_data, sector_data
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "ADD_POSITION")

    def test_add_position_sector_weak(self):
        """测试板块弱势时不加仓 - V3.0铁律"""
        tech_data = {
            'is_pullback_ma20': True,
            'volume_shrink_pct': 50.0,
            'ma20_trend': 'up'
        }
        sector_data = {
            'sector_vs_index': 0.95,  # 板块弱于大盘 (<1.0)
            'earnings_beat': False
        }

        signal = self.monitor.check_add_position(
            self.position, 125.0, tech_data, sector_data
        )

        self.assertIsNone(signal)  # 不应产生加仓信号

    def test_daily_tech_monitor(self):
        """测试每日技术监控"""
        monitor_data = DailyTechMonitor(
            stock_code="000001",
            close_price=95.0,
            above_ma20=False,
            volume_vs_ma20=2.0,
            rsi=85,
            macd_signal="顶背离",
            sector_relative_strength=0.95,
            atr_14=2.0,
            daily_volatility=8.0  # > 3*2=6
        )

        signals = self.monitor.daily_tech_monitor(self.position, monitor_data)

        # 应产生多个信号：破20日线、RSI过高、顶背离、波动率异常
        self.assertGreater(len(signals), 3)

    def test_portfolio_risk(self):
        """测试组合风控"""
        positions = [self.position]
        sector_positions = {"AI算力": [self.position]}

        # VIX=35 > 30
        signals = self.monitor.check_portfolio_risk(positions, sector_positions, vix=35)

        extreme_signals = [s for s in signals if "VIX" in s.signal_desc]
        self.assertEqual(len(extreme_signals), 1)
        self.assertEqual(extreme_signals[0].suggested_ratio, 0.90)


class TestPortfolioManager(unittest.TestCase):
    """测试组合管理器"""

    def setUp(self):
        self.pm = CorePortfolioManager(total_capital=1000000.0, core_ratio=0.50)

    def test_initial_state(self):
        """测试初始状态"""
        self.assertEqual(self.pm.portfolio.total_capital, 1000000.0)
        self.assertEqual(self.pm.portfolio.core_capital, 500000.0)
        self.assertEqual(self.pm.portfolio.cash, 500000.0)

    def test_open_position(self):
        """测试开仓"""
        candidate = StockSecondaryScore(
            stock_code="000001",
            stock_name="测试股",
            sector="AI算力",
            initial_score=90.0,
            financial_score=95.0,
            expectation_score=90.0
        )

        buy_point = BuyPointSignal(
            stock_code="000001",
            stock_name="测试股",
            quality=BuyPointQuality.IDEAL,
            ma_alignment_pass=True,
            pullback_pct=8.0,
            volume_shrink_pass=True,
            price_stabilize_pass=True,
            suggested_position_pct=0.15
        )

        position = self.pm.open_position(candidate, buy_point, 100.0, atr=3.0)

        self.assertIsNotNone(position)
        self.assertEqual(position.entry_price, 100.0)
        self.assertEqual(position.fixed_stop_loss_price, 90.0)
        self.assertEqual(position.entry_atr, 3.0)

    def test_max_position_limit(self):
        """测试单只仓位上限"""
        can_open, reason = self.pm.can_open_position(0.10)
        self.assertTrue(can_open)

        can_open, reason = self.pm.can_open_position(0.20)
        self.assertFalse(can_open)
        self.assertIn("18.0%", reason)

    def test_add_position(self):
        """测试加仓"""
        # 先开仓
        candidate = StockSecondaryScore(
            stock_code="000001", stock_name="测试股", sector="AI算力"
        )
        buy_point = BuyPointSignal(
            stock_code="000001", stock_name="测试股",
            suggested_position_pct=0.10
        )
        position = self.pm.open_position(candidate, buy_point, 100.0)

        # 加仓
        result = self.pm.add_position("000001", 120.0, 0.25)
        self.assertIsNotNone(result)

        # 检查累计仓位
        self.assertGreater(position.remaining_position_pct, 0.10)


class TestIntegration(unittest.TestCase):
    """集成测试"""

    def test_full_pipeline(self):
        """测试完整流程"""
        pipeline = CorePositionPipeline(total_capital=1000000.0)

        # 1. 宏观数据
        macro_data = {
            'social_financing_growth': 12.0,
            'social_financing_mom_change': 1.0,
            'treasury_yield_10y': 2.8,
            'risk_premium': 3.5
        }

        # 2. 赛道数据
        sectors_data = [
            {
                'sector_name': 'AI算力',
                'penetration_rate': 12.0,
                'policy_strength_score': 90.0,
                'foreign_consensus_score': 85.0,
                'capex_score': 80.0
            }
        ]

        # 3. 股票数据
        stocks_data = [
            {
                'code': '000001',
                'name': 'AI龙头',
                'sector': 'AI算力',
                'sector_heat_score': 90.0,
                'chain_position_score': 85.0,
                'tech_barrier_score': 80.0,
                'earnings_certainty_score': 75.0,
                'management_quality_score': 70.0,
                'institution_consensus_score': 60.0,
                'management_violation_2y': False,
                'analyst_coverage_count': 10,
                'revenue_decline_quarters': 0,
                'daily_avg_volume': 5.0,
                'goodwill_to_net_asset': 0.05,
                'pledge_ratio': 15.0,
                'roe_y1': 18.0,
                'roe_y2': 15.0,
                'audit_opinion': '标准无保留'
            }
        ]

        # 4. 财报数据
        financial_reports = {
            '000001': {
                'revenue_growth': 50.0,
                'profit_growth': 80.0,
                'gross_margin_trend': 3.0,
                'cash_flow_to_profit': 1.0,
                'guidance_adjustment': '上调',
                'order_visibility': '饱满',
                'cash_flow_negative_quarters': 0,
                'receivable_growth_vs_revenue': 1.2,
                'inventory_growth_vs_revenue': 1.0,
                'major_holder_reduction_pct': 0.0
            }
        }

        # 5. 验证数据
        verifications = {
            '000001': {
                'price_reaction': True,
                'analyst_reaction': True,
                'volume_reaction': True,
                'northbound_inflow': True
            }
        }

        # 6. 市场数据
        market_data = {
            'index_price': 3200,
            'ma60': 3100,
            'ma250': 3000,
            'volume': 12000,
            'advance_decline_ratio': 2.0,
            'vix': 15
        }

        # 7. 技术数据
        tech_data_map = {
            '000001': {
                'ma20': 105.0, 'ma60': 100.0, 'ma120': 95.0,
                'ma20_trend': 'up', 'ma60_trend': 'up', 'ma120_trend': 'up',
                'recent_high': 110.0, 'current_price': 100.0,
                'volume': 5000, 'volume_ma20': 10000,
                'days_not_new_low': 3,
                'rsi': 45,
                'atr_14_pct': 3.0,
                'is_pullback_ma20': True
            }
        }

        # 8. 基本面数据
        stock_fundamentals = {
            '000001': {
                'penetration_rate': 12.0,
                'revenue_growth': 50.0,
                'profit_growth': 80.0,
                'analyst_coverage': 8,
                'expectation_conservative': True,
                'peg_ratio': 1.2,
                'is_credit_contraction': False
            }
        }

        # 执行完整流程
        result = pipeline.run_full_pipeline(
            macro_data, sectors_data, stocks_data,
            financial_reports, verifications,
            market_data, tech_data_map, stock_fundamentals
        )

        self.assertEqual(result['status'], 'success')
        self.assertGreater(result['buy_signals'], 0)

        # 执行买入
        buy_signals = pipeline.phase3_buy_timing(
            market_data, tech_data_map, stock_fundamentals
        )
        for candidate, buy_point in buy_signals:
            position = pipeline.execute_buy(candidate, buy_point, 100.0, atr=3.0)
            self.assertIsNotNone(position)

        # 监控持仓
        daily_tech = {
            '000001': {
                'close_price': 130.0,
                'above_ma20': True,
                'volume_vs_ma20': 1.2,
                'rsi': 75,
                'macd_signal': '正常',
                'sector_relative_strength': 1.1,
                'atr_14': 2.5,
                'daily_volatility': 3.0
            }
        }
        weekly_fund = {
            '000001': {
                'industry_policy_change': False,
                'company_bad_news': False,
                'analyst_coverage_dropped': False,
                'peg_ratio': 1.3,
                'northbound_outflow_days': 3
            }
        }

        monitor_result = pipeline.run_daily_monitor(
            daily_tech, weekly_fund, market_data
        )

        self.assertIn('portfolio_summary', monitor_result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
