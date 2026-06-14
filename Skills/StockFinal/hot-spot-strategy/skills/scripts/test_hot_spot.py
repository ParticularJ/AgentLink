"""
热点仓交易系统 - 单元测试
"""
import unittest
import sys
import os
from datetime import datetime, timedelta

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import (
    StrategyType, SignalLevel, PositionStatus, StopLossType,
    MarketEnvironment, SectorHeat, StockScore, Position,
    HotSpotPortfolio, MonitorSignal
)
from strategy_scorer import (
    FirstLimitUpScorer, LimitUpRetraceScorer,
    SectorLeaderScorer, NewStockScorer
)
from portfolio_manager import PortfolioManager
from risk_manager import RiskManager
from hot_spot_pipeline import HotSpotPipeline


class TestModels(unittest.TestCase):
    """测试数据模型"""
    
    def test_strategy_type_enum(self):
        """测试策略类型枚举"""
        self.assertEqual(StrategyType.FIRST_LIMIT_UP.value, "首次涨停板")
        self.assertEqual(StrategyType.LIMIT_UP_RETRACE.value, "涨停回调")
        self.assertEqual(StrategyType.SECTOR_LEADER.value, "热门板块龙头")
        self.assertEqual(StrategyType.NEW_STOCK.value, "次新股")
    
    def test_signal_level_enum(self):
        """测试信号等级枚举"""
        self.assertEqual(SignalLevel.STRONG_BUY.value, "强烈买入")
        self.assertEqual(SignalLevel.BUY.value, "买入")
        self.assertEqual(SignalLevel.WATCH.value, "观望")
        self.assertEqual(SignalLevel.PASS.value, "放弃")
    
    def test_stock_score_creation(self):
        """测试股票评分创建"""
        score = StockScore(
            strategy_type=StrategyType.FIRST_LIMIT_UP,
            stock_code="000001",
            stock_name="平安银行",
            total_score=85.0,
            signal_level=SignalLevel.BUY,
            suggested_position_pct=0.25
        )
        self.assertEqual(score.stock_code, "000001")
        self.assertEqual(score.total_score, 85.0)
        self.assertTrue(score.veto_passed)
    
    def test_position_creation(self):
        """测试持仓创建"""
        position = Position(
            stock_code="000001",
            stock_name="平安银行",
            strategy_type=StrategyType.FIRST_LIMIT_UP,
            entry_price=10.0,
            initial_shares=1000,
            stop_loss_price=9.3
        )
        self.assertEqual(position.entry_price, 10.0)
        self.assertEqual(position.stop_loss_price, 9.3)
        self.assertEqual(position.status, PositionStatus.HOLDING)


class TestFirstLimitUpScorer(unittest.TestCase):
    """测试策略一：首次涨停板评分器"""
    
    def setUp(self):
        self.scorer = FirstLimitUpScorer()
    
    def test_perfect_score(self):
        """测试满分情况"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'limit_up_time': '09:32',
            'seal_amount': 100000,
            'avg_daily_volume_20d': 10000,
            'turnover': 10.0,
            'sector_limit_up_count': 6,
            'is_one_word': False,
        }
        score = self.scorer.score(stock_data)
        self.assertIsNotNone(score)
        self.assertTrue(score.veto_passed)
        self.assertEqual(score.dimension_scores["涨停时间"], 30.0)
        self.assertEqual(score.dimension_scores["封单质量"], 25.0)
        self.assertEqual(score.dimension_scores["板块效应"], 25.0)
        self.assertEqual(score.dimension_scores["换手率"], 20.0)
        self.assertEqual(score.total_score, 100.0)
        self.assertEqual(score.signal_level, SignalLevel.STRONG_BUY)
    
    def test_one_word_veto(self):
        """测试一字板一票否决"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'is_one_word': True,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertEqual(score.veto_reason, "一字板无法买入")
    
    def test_low_score(self):
        """测试低分情况"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'limit_up_time': '14:00',
            'seal_amount': 1000,
            'avg_daily_volume_20d': 10000,
            'turnover': 2.0,
            'sector_limit_up_count': 0,
            'is_one_word': False,
        }
        score = self.scorer.score(stock_data)
        self.assertTrue(score.veto_passed)
        self.assertEqual(score.dimension_scores["涨停时间"], 0.0)
        self.assertEqual(score.dimension_scores["板块效应"], 0.0)
        self.assertLess(score.total_score, 75.0)


class TestLimitUpRetraceScorer(unittest.TestCase):
    """测试策略二：涨停回调评分器"""
    
    def setUp(self):
        self.scorer = LimitUpRetraceScorer()
    
    def test_optimal_retrace(self):
        """测试最优回调"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'retrace_pct': -10.0,
            'retrace_days': 3,
            'volume_shrink_pct': 65.0,
            'stop_signal': '锤子线',
            'is_above_ma5': True,
            'daily_change_pct': -2.0,
        }
        score = self.scorer.score(stock_data)
        self.assertIsNotNone(score)
        self.assertTrue(score.veto_passed)
        self.assertGreaterEqual(score.total_score, 80.0)
    
    def test_borderline_score(self):
        """测试及格线附近"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'retrace_pct': -5.0,
            'retrace_days': 2,
            'volume_shrink_pct': 35.0,
            'stop_signal': '小阳线',
            'is_above_ma5': False,
            'daily_change_pct': -4.0,
        }
        score = self.scorer.score(stock_data)
        self.assertTrue(score.veto_passed)
        # 应该在及格线附近
        self.assertGreaterEqual(score.total_score, 60.0)


class TestSectorLeaderScorer(unittest.TestCase):
    """测试策略三：板块龙头评分器"""
    
    def setUp(self):
        self.scorer = SectorLeaderScorer()
    
    def test_strong_leader(self):
        """测试强势龙头"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'rank_in_sector': 1,
            'has_limit_up': True,
            'consecutive_limit': 2,
            'sector_heat_score': 90.0,
            'leadership_score': 85.0,
            'turnover': 15.0,
            'float_market_cap': 100.0,
        }
        score = self.scorer.score(stock_data)
        self.assertIsNotNone(score)
        self.assertTrue(score.veto_passed)
        self.assertGreaterEqual(score.total_score, 85.0)
        self.assertEqual(score.signal_level, SignalLevel.STRONG_BUY)
    
    def test_weak_leader(self):
        """测试弱势龙头"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'rank_in_sector': 15,
            'has_limit_up': False,
            'consecutive_limit': 0,
            'sector_heat_score': 60.0,
            'leadership_score': 30.0,
            'turnover': 3.0,
            'float_market_cap': 600.0,
        }
        score = self.scorer.score(stock_data)
        self.assertTrue(score.veto_passed)
        self.assertLess(score.total_score, 70.0)


class TestNewStockScorer(unittest.TestCase):
    """测试策略四：次新股评分器"""
    
    def setUp(self):
        self.scorer = NewStockScorer()
    
    def test_good_new_stock(self):
        """测试优质次新股"""
        stock_data = {
            'code': '000001',
            'name': '测试新股',
            'industry_level': 'core',
            'first_day_turnover': 70.0,
            'is_small_cap': False,
            'stable_closing': True,
            'pe_ratio': 20.0,
            'industry_pe': 25.0,
            'is_new_low': False,
            'seller_institution': False,
        }
        score = self.scorer.score(stock_data)
        self.assertIsNotNone(score)
        self.assertTrue(score.veto_passed)
        self.assertGreaterEqual(score.total_score, 80.0)
    
    def test_veto_high_turnover(self):
        """测试换手率过高一票否决"""
        stock_data = {
            'code': '000001',
            'name': '测试新股',
            'first_day_turnover': 85.0,
            'is_small_cap': False,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertIn("抛压过重", score.veto_reason)
    
    def test_veto_new_low(self):
        """测试创新低一票否决"""
        stock_data = {
            'code': '000001',
            'name': '测试新股',
            'first_day_turnover': 65.0,
            'is_small_cap': False,
            'is_new_low': True,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)


class TestPortfolioManager(unittest.TestCase):
    """测试组合管理器"""
    
    def setUp(self):
        self.pm = PortfolioManager(total_capital=1000000.0)
    
    def test_initial_state(self):
        """测试初始状态"""
        self.assertEqual(self.pm.portfolio.total_capital, 1000000.0)
        self.assertEqual(self.pm.portfolio.hot_spot_capital, 250000.0)
        self.assertEqual(self.pm.portfolio.cash, 250000.0)
    
    def test_can_open_position(self):
        """测试开仓检查"""
        can_open, reason = self.pm.can_open_position(0.20)
        self.assertTrue(can_open)
        
        # 测试超过单只上限
        can_open, reason = self.pm.can_open_position(0.35)
        self.assertFalse(can_open)
    
    def test_open_position(self):
        """测试开仓"""
        score = StockScore(
            strategy_type=StrategyType.FIRST_LIMIT_UP,
            stock_code="000001",
            stock_name="平安银行",
            suggested_position_pct=0.20,
            stop_loss_pct=-7.0
        )
        position = self.pm.open_position(score, entry_price=10.0)
        self.assertIsNotNone(position)
        self.assertEqual(position.stock_code, "000001")
        self.assertEqual(position.entry_price, 10.0)
        self.assertAlmostEqual(position.stop_loss_price, 9.3, places=1)  # 10 * 0.93
    
    def test_max_positions(self):
        """测试最大持仓限制"""
        for i in range(4):
            score = StockScore(
                strategy_type=StrategyType.FIRST_LIMIT_UP,
                stock_code=f"00000{i+1}",
                stock_name=f"测试股{i+1}",
                suggested_position_pct=0.20,
                stop_loss_pct=-7.0
            )
            self.pm.open_position(score, entry_price=10.0)
        
        # 第4只应该无法开仓
        score = StockScore(
            strategy_type=StrategyType.FIRST_LIMIT_UP,
            stock_code="000005",
            stock_name="测试股5",
            suggested_position_pct=0.20,
            stop_loss_pct=-7.0
        )
        position = self.pm.open_position(score, entry_price=10.0)
        self.assertIsNone(position)
    
    def test_sell_position(self):
        """测试卖出"""
        score = StockScore(
            strategy_type=StrategyType.FIRST_LIMIT_UP,
            stock_code="000001",
            stock_name="平安银行",
            suggested_position_pct=0.20,
            stop_loss_pct=-7.0
        )
        position = self.pm.open_position(score, entry_price=10.0)
        self.assertIsNotNone(position)
        
        # 卖出一半
        result = self.pm.sell_position("000001", sell_price=11.0, sell_ratio=0.5, reason="测试卖出")
        self.assertIsNotNone(result)
        self.assertEqual(position.status, PositionStatus.PARTIAL_SELL)
    
    def test_fuse_mechanism(self):
        """测试熔断机制"""
        # 模拟大幅亏损
        self.pm.portfolio.daily_pnl = -6000.0
        self.pm.portfolio.daily_pnl_pct = -2.4
        
        # 应该触发熔断
        can_open, reason = self.pm.can_open_position(0.20)
        self.assertFalse(can_open)
        self.assertIn("熔断", reason)


class TestRiskManager(unittest.TestCase):
    """测试风险管理器"""
    
    def setUp(self):
        self.rm = RiskManager()
        self.position = Position(
            stock_code="000001",
            stock_name="平安银行",
            strategy_type=StrategyType.FIRST_LIMIT_UP,
            entry_price=10.0,
            stop_loss_price=9.3,
            highest_price=10.0
        )
    
    def test_fixed_stop_loss(self):
        """测试固定止损"""
        signal = self.rm.check_stop_loss(self.position, current_price=9.2)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "STOP_LOSS")
        self.assertEqual(signal.action, "SELL")
    
    def test_moving_stop_loss(self):
        """测试移动止损"""
        # 先涨价到12（浮盈20%），更新highest_price
        self.position.highest_price = 12.0
        # 从12回撤5%以上，比如11.3
        # 11.3相对10.0浮盈13%，满足>5%条件
        # 回撤(12-11.3)/12 = 5.8%，满足回撤条件
        signal = self.rm.check_stop_loss(self.position, current_price=11.3)
        self.assertIsNotNone(signal)
        self.assertIn("回撤", signal.signal_desc)
    
    def test_time_stop(self):
        """测试时间止损"""
        # 设置持仓6天（超过5天限制）
        self.position.entry_date = datetime.now() - timedelta(days=6)
        self.position.current_price = 9.5  # 亏损
        
        signal = self.rm.check_time_stop(self.position)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "TIME_STOP")
    
    def test_take_profit(self):
        """测试止盈"""
        self.position.take_profit_levels = [
            {"pct": 5, "sell_ratio": 0.333},
            {"pct": 10, "sell_ratio": 0.333}
        ]
        
        # 价格涨到11（浮盈10%），应该触发5%和10%两个止盈层级
        signals = self.rm.check_take_profit(self.position, current_price=11.0)
        self.assertGreaterEqual(len(signals), 1)  # 至少触发5%止盈
        self.assertEqual(signals[0].signal_type, "TAKE_PROFIT")
    
    def test_special_signals(self):
        """测试特殊信号"""
        market_data = {
            '炸板': True,
            '炸板_duration': 20,
            '监管出手': True,
        }
        
        signals = self.rm.check_special_signals(self.position, market_data)
        self.assertEqual(len(signals), 2)
        
        # 检查是否有炸板信号
        炸板_signals = [s for s in signals if "炸板" in s.signal_desc]
        self.assertEqual(len(炸板_signals), 1)
        
        # 检查是否有监管信号
        监管_signals = [s for s in signals if "监管" in s.signal_desc]
        self.assertEqual(len(监管_signals), 1)


class TestHotSpotPipeline(unittest.TestCase):
    """测试主流程管道"""
    
    def setUp(self):
        self.pipeline = HotSpotPipeline(total_capital=1000000.0)
    
    def test_scan_strategies(self):
        """测试策略扫描"""
        stocks_data = {
            StrategyType.FIRST_LIMIT_UP: [
                {
                    'code': '000001',
                    'name': '平安银行',
                    'limit_up_time': '09:35',
                    'seal_amount': 50000,
                    'avg_daily_volume_20d': 30000,
                    'turnover': 12.5,
                    'sector_limit_up_count': 5,
                    'is_one_word': False,
                }
            ],
            StrategyType.LIMIT_UP_RETRACE: [
                {
                    'code': '000002',
                    'name': '万科A',
                    'retrace_pct': -10.0,
                    'retrace_days': 3,
                    'volume_shrink_pct': 60.0,
                    'stop_signal': '锤子线',
                    'is_above_ma5': True,
                    'daily_change_pct': -2.0,
                }
            ]
        }
        
        scores = self.pipeline.scan_strategies(stocks_data)
        self.assertEqual(len(scores), 2)
    
    def test_multi_strategy_bonus(self):
        """测试多策略加分"""
        scores = [
            StockScore(
                strategy_type=StrategyType.FIRST_LIMIT_UP,
                stock_code="000001",
                stock_name="测试股",
                total_score=80.0,
                signal_level=SignalLevel.BUY
            ),
            StockScore(
                strategy_type=StrategyType.LIMIT_UP_RETRACE,
                stock_code="000001",
                stock_name="测试股",
                total_score=70.0,
                signal_level=SignalLevel.WATCH
            )
        ]
        
        result = self.pipeline.apply_multi_strategy_bonus(scores)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].total_score, 83.0)  # 80 + 3
        self.assertEqual(len(result[0].hit_strategies), 2)
    
    def test_filter_and_rank(self):
        """测试过滤排序"""
        scores = [
            StockScore(
                strategy_type=StrategyType.FIRST_LIMIT_UP,
                stock_code="000001",
                stock_name="股A",
                total_score=90.0,
                signal_level=SignalLevel.STRONG_BUY
            ),
            StockScore(
                strategy_type=StrategyType.LIMIT_UP_RETRACE,
                stock_code="000002",
                stock_name="股B",
                total_score=85.0,
                signal_level=SignalLevel.BUY
            ),
            StockScore(
                strategy_type=StrategyType.SECTOR_LEADER,
                stock_code="000003",
                stock_name="股C",
                total_score=60.0,
                signal_level=SignalLevel.PASS
            ),
        ]
        
        result = self.pipeline.filter_and_rank(scores, max_results=3)
        self.assertEqual(len(result), 2)  # 过滤掉<65分的
        self.assertEqual(result[0].stock_code, "000001")  # 最高分在前


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_full_workflow(self):
        """测试完整工作流程"""
        pipeline = HotSpotPipeline(total_capital=1000000.0)
        
        # 1. 准备股票数据
        stocks_data = {
            StrategyType.FIRST_LIMIT_UP: [
                {
                    'code': '000001',
                    'name': '平安银行',
                    'limit_up_time': '09:35',
                    'seal_amount': 50000,
                    'avg_daily_volume_20d': 30000,
                    'turnover': 12.5,
                    'sector_limit_up_count': 5,
                    'is_one_word': False,
                }
            ],
            StrategyType.LIMIT_UP_RETRACE: [
                {
                    'code': '000002',
                    'name': '万科A',
                    'retrace_pct': -10.0,
                    'retrace_days': 3,
                    'volume_shrink_pct': 60.0,
                    'stop_signal': '锤子线',
                    'is_above_ma5': True,
                    'daily_change_pct': -2.0,
                }
            ],
            StrategyType.SECTOR_LEADER: [],
            StrategyType.NEW_STOCK: [],
        }
        
        # 2. 生成推荐
        recommendations = pipeline.generate_recommendations(stocks_data)
        self.assertGreater(len(recommendations), 0)
        
        # 3. 执行买入
        for rec in recommendations[:1]:  # 只买第一只
            position = pipeline.execute_buy(rec, entry_price=10.0)
            self.assertIsNotNone(position)
        
        # 4. 监控持仓
        market_data = {
            '000001': {
                'intraday_data': {
                    'current_price': 9.2,
                    'below_ma_minutes': 20,
                },
                'daily_data': {
                    'close_price': 9.2,
                    'above_ma5': False,
                }
            }
        }
        signals = pipeline.monitor_positions(market_data)
        self.assertGreater(len(signals), 0)
        
        # 5. 执行卖出
        for signal in signals:
            if signal.urgency == "urgent":
                pipeline.execute_sell(signal)
        
        # 6. 每日复盘
        summary = pipeline.daily_review()
        self.assertIn("热点仓资金", summary)


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
