"""
热点仓交易系统 - 单元测试
严格验证评分逻辑是否符合《热点仓完整操作流程V4.0专业版》设计文档
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
    """测试策略一：首次涨停板评分器 - 严格按设计文档表3/表4"""
    
    def setUp(self):
        self.scorer = FirstLimitUpScorer()
    
    def test_perfect_score(self):
        """测试满分情况 - 所有维度最优"""
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
        # 验证各维度满分
        self.assertEqual(score.dimension_scores["涨停时间"], 30.0)
        self.assertEqual(score.dimension_scores["封单质量"], 25.0)
        self.assertEqual(score.dimension_scores["板块效应"], 25.0)
        self.assertEqual(score.dimension_scores["换手率"], 20.0)
        self.assertEqual(score.total_score, 100.0)
        self.assertEqual(score.signal_level, SignalLevel.STRONG_BUY)
        self.assertEqual(score.suggested_position_pct, 0.30)  # 表4：极强势30%
    
    def test_one_word_veto(self):
        """测试一字板一票否决 - 设计文档2.1节"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'is_one_word': True,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertEqual(score.veto_reason, "一字板无法买入")
    
    def test_index_below_ma20_veto(self):
        """测试大盘破20日线一票否决 - 设计文档2.1节"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'index_below_ma20': True,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertEqual(score.veto_reason, "大盘破20日线，系统性风险")
    
    def test_bad_news_veto(self):
        """测试个股利空一票否决 - 设计文档2.1节"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'has_bad_news': True,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertEqual(score.veto_reason, "个股存在利空消息")
    
    def test_time_scoring(self):
        """测试涨停时间评分 - 严格按表3"""
        test_cases = [
            ("09:35", 30.0),   # 9:35前
            ("09:30", 30.0),   # 9:30整（开盘即涨停）
            ("09:45", 20.0),   # 10:00前
            ("10:00", 20.0),   # 10:00整
            ("10:15", 10.0),   # 10:30前
            ("10:30", 10.0),   # 10:30整
            ("11:00", 0.0),    # 10:30后
            ("14:00", 0.0),    # 下午
        ]
        for time_str, expected in test_cases:
            score = self.scorer._score_limit_up_time(time_str)
            self.assertEqual(score, expected, f"时间{time_str}应得{expected}分")
    
    def test_seal_quality_scoring(self):
        """测试封单质量评分 - 严格按表3"""
        test_cases = [
            (100000, 10000, 25.0),   # 1000% > 80%
            (80000, 10000, 25.0),    # 800% >= 80%
            (50000, 10000, 25.0),    # 500% >= 50% (>=80%得25分)
            (30000, 10000, 25.0),    # 300% >= 30% (>=80%得25分)
            (10000, 10000, 25.0),    # 100% >= 10% (>=80%得25分)
            (5000, 10000, 20.0),     # 50% >= 50%
            (3000, 10000, 15.0),     # 30% >= 30%
            (1000, 10000, 10.0),     # 10% >= 10%
            (500, 10000, 5.0),       # 5% < 10%
        ]
        for seal, avg_vol, expected in test_cases:
            score = self.scorer._score_seal_quality(seal, avg_vol)
            self.assertEqual(score, expected, f"封单{seal}/均量{avg_vol}应得{expected}分")
    
    def test_sector_effect_scoring(self):
        """测试板块效应评分 - 严格按表3"""
        test_cases = [
            (5, 25.0),   # ≥5只
            (3, 15.0),   # ≥3只
            (1, 5.0),    # ≥1只
            (0, 0.0),    # 0只
        ]
        for count, expected in test_cases:
            score = self.scorer._score_sector_effect(count)
            self.assertEqual(score, expected, f"板块涨停{count}只应得{expected}分")
    
    def test_turnover_scoring(self):
        """测试换手率评分 - 严格按表3"""
        test_cases = [
            (10.0, 20.0),   # 5%-15%
            (5.0, 20.0),    # 边界5%
            (15.0, 20.0),   # 边界15%
            (20.0, 15.0),   # 15%-25%
            (4.0, 10.0),    # 3%-5%
            (30.0, 8.0),    # 25%-35%
            (50.0, 5.0),    # 其他
        ]
        for turnover, expected in test_cases:
            score = self.scorer._score_turnover(turnover)
            self.assertEqual(score, expected, f"换手率{turnover}%应得{expected}分")
    
    def test_position_sizing(self):
        """测试仓位建议 - 严格按表4"""
        test_cases = [
            (95, 0.30),   # 90-100分：30%
            (85, 0.25),   # 80-89分：25%
            (77, 0.20),   # 75-79分：20%
            (70, 0.15),   # 70-74分：15%（龙头策略）
        ]
        for score_val, expected_pct in test_cases:
            pct = self.scorer._get_position_pct(score_val, StrategyType.FIRST_LIMIT_UP)
            self.assertEqual(pct, expected_pct, f"{score_val}分应建议仓位{expected_pct}")


class TestLimitUpRetraceScorer(unittest.TestCase):
    """测试策略二：涨停回调评分器 - 严格按设计文档表5/表6"""
    
    def setUp(self):
        self.scorer = LimitUpRetraceScorer()
    
    def test_optimal_retrace(self):
        """测试最优回调 - 所有维度最优"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'retrace_pct': -10.0,       # 最优回调-8%~-12%
            'retrace_days': 3,           # 最优3-4天
            'volume_shrink_pct': 65.0,   # 缩量60%以上
            'stop_signal': '锤子线',      # 最强信号
            'is_above_ma5': True,        # 站5日线
            'daily_change_pct': -2.0,    # 跌幅≤-3%
            'has_limit_up_history': True,
        }
        score = self.scorer.score(stock_data)
        self.assertIsNotNone(score)
        self.assertTrue(score.veto_passed)
        self.assertGreaterEqual(score.total_score, 80.0)
        self.assertEqual(score.dimension_scores["回调幅度"], 25.0)
        self.assertEqual(score.dimension_scores["回调天数"], 20.0)
        self.assertEqual(score.dimension_scores["缩量程度"], 25.0)
        self.assertEqual(score.dimension_scores["企稳信号"], 30.0)
    
    def test_no_limit_up_history_veto(self):
        """测试前期无涨停一票否决"""
        stock_data = {
            'code': '000001',
            'name': '测试股',
            'has_limit_up_history': False,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertIn("前期无涨停", score.veto_reason)
    
    def test_retrace_scoring(self):
        """测试回调幅度评分 - 严格按表5"""
        test_cases = [
            (10.0, 25.0),   # -8%~-12%
            (8.0, 25.0),    # 边界8%
            (12.0, 25.0),   # 边界12%
            (6.0, 20.0),    # -5%~-8%
            (13.0, 15.0),   # -12%~-15%
            (4.0, 10.0),    # -3%~-5%
            (18.0, 8.0),    # -15%~-20%
            (25.0, 5.0),    # 其他
        ]
        for retrace, expected in test_cases:
            score = self.scorer._score_retrace(retrace)
            self.assertEqual(score, expected, f"回调{retrace}%应得{expected}分")
    
    def test_retrace_days_scoring(self):
        """测试回调天数评分 - 严格按表5"""
        test_cases = [
            (3, 20.0),   # 3-4天
            (4, 20.0),   # 3-4天
            (2, 15.0),   # 2天
            (5, 15.0),   # 5天
            (6, 10.0),   # 6天
            (1, 8.0),    # 1天
            (7, 5.0),    # 其他
        ]
        for days, expected in test_cases:
            score = self.scorer._score_retrace_days(days)
            self.assertEqual(score, expected, f"回调{days}天应得{expected}分")
    
    def test_volume_shrink_scoring(self):
        """测试缩量程度评分 - 严格按表5"""
        test_cases = [
            (60.0, 25.0),   # ≥60%
            (40.0, 20.0),   # ≥40%
            (30.0, 15.0),   # ≥30%
            (20.0, 10.0),   # ≥20%
            (10.0, 5.0),    # <20%
        ]
        for shrink, expected in test_cases:
            score = self.scorer._score_volume_shrink(shrink)
            self.assertEqual(score, expected, f"缩量{shrink}%应得{expected}分")
    
    def test_stop_signal_scoring(self):
        """测试企稳信号评分 - 严格按表5"""
        # 锤子线 + 站5日线 + 跌幅≤-3%
        score = self.scorer._score_stop_signal('锤子线', True, -2.0)
        self.assertEqual(score, 30.0)
        
        # 十字星 + 站5日线 + 跌幅≤-3%
        score = self.scorer._score_stop_signal('十字星', True, -2.0)
        self.assertEqual(score, 28.0)
        
        # 无明显信号 + 不站5日线 + 大跌
        score = self.scorer._score_stop_signal('大阴线', False, -8.0)
        self.assertEqual(score, 8.0)  # 3+3+2=8
    
    def test_position_sizing(self):
        """测试仓位建议 - 严格按表6"""
        test_cases = [
            (95, 0.30),   # 90-100分：30%（使用标准仓位）
            (85, 0.25),   # 80-89分：25%
            (75, 0.20),   # 70-79分：20%
            (67, 0.10),   # 65-69分：10%
            (60, 0.0),    # <65分：0%
        ]
        for score_val, expected_pct in test_cases:
            pct = self.scorer._get_position_pct(score_val, StrategyType.LIMIT_UP_RETRACE)
            self.assertEqual(pct, expected_pct, f"{score_val}分应建议仓位{expected_pct}")


class TestSectorLeaderScorer(unittest.TestCase):
    """测试策略三：热门板块龙头评分器 - 严格按设计文档表9"""
    
    def setUp(self):
        self.scorer = SectorLeaderScorer()
    
    def test_strong_leader(self):
        """测试强势龙头 - 所有维度最优"""
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
        self.assertEqual(score.dimension_scores["涨幅领先度"], 25.0)
        self.assertEqual(score.dimension_scores["涨停强度"], 15.0)
        self.assertEqual(score.dimension_scores["板块热度"], 20.0)
    
    def test_rank_scoring(self):
        """测试涨幅领先度评分 - 严格按表9"""
        test_cases = [
            (1, 25.0),   # 第1
            (2, 20.0),   # 第2
            (3, 15.0),   # 第3
            (5, 10.0),   # 前5
            (10, 5.0),   # 前10
            (15, 2.0),   # 其他
        ]
        for rank, expected in test_cases:
            score = self.scorer._score_rank(rank)
            self.assertEqual(score, expected, f"排名{rank}应得{expected}分")
    
    def test_limit_strength_scoring(self):
        """测试涨停强度评分 - 严格按表9"""
        test_cases = [
            (True, 2, 15.0),   # 2连板
            (True, 1, 10.0),   # 1连板（consecutive=1 < 2，但has_limit=True）
            (True, 0, 10.0),   # 有涨停但无连板
            (False, 0, 5.0),   # 无涨停
        ]
        for has_limit, consecutive, expected in test_cases:
            score = self.scorer._score_limit_strength(has_limit, consecutive)
            self.assertEqual(score, expected, f"涨停{has_limit}连板{consecutive}应得{expected}分")
    
    def test_turnover_scoring(self):
        """测试换手率评分 - 严格按表9"""
        test_cases = [
            (15.0, 15.0),   # 10%-25%
            (10.0, 15.0),   # 边界10%
            (25.0, 15.0),   # 边界25%
            (7.0, 10.0),    # 5%-10%
            (30.0, 8.0),    # 25%-35%
            (50.0, 5.0),    # 其他
        ]
        for turnover, expected in test_cases:
            score = self.scorer._score_turnover(turnover)
            self.assertEqual(score, expected, f"换手率{turnover}%应得{expected}分")
    
    def test_market_cap_scoring(self):
        """测试流通市值评分 - 严格按表9"""
        test_cases = [
            (100.0, 10.0),   # 50-150亿
            (50.0, 10.0),    # 边界50亿
            (150.0, 10.0),   # 边界150亿
            (200.0, 8.0),    # 150-300亿
            (40.0, 7.0),     # 30-50亿
            (400.0, 5.0),    # 300-500亿
            (600.0, 3.0),    # 其他
        ]
        for cap, expected in test_cases:
            score = self.scorer._score_market_cap(cap)
            self.assertEqual(score, expected, f"市值{cap}亿应得{expected}分")


class TestNewStockScorer(unittest.TestCase):
    """测试策略四：次新股评分器 - 严格按设计文档表11/12/13"""
    
    def setUp(self):
        self.scorer = NewStockScorer()
    
    def test_good_new_stock(self):
        """测试优质次新股 - 所有维度最优"""
        stock_data = {
            'code': '000001',
            'name': '测试新股',
            'industry_level': 'core',
            'first_day_turnover': 70.0,   # 标准盘60%-80%
            'is_small_cap': False,
            'stable_closing': True,
            'pe_ratio': 20.0,
            'industry_pe': 25.0,          # 比值0.8 < 1.2
            'is_new_low': False,
            'seller_institution': False,
            'closing_gain_pct': 80.0,     # <100%
        }
        score = self.scorer.score(stock_data)
        self.assertIsNotNone(score)
        self.assertTrue(score.veto_passed)
        self.assertGreaterEqual(score.total_score, 80.0)
        self.assertEqual(score.dimension_scores["行业景气度"], 30.0)
        self.assertEqual(score.dimension_scores["首日换手率"], 25.0)
        self.assertEqual(score.dimension_scores["尾盘企稳"], 25.0)
        self.assertEqual(score.dimension_scores["发行估值"], 20.0)
    
    def test_veto_high_turnover_standard(self):
        """测试标准盘股换手率过高一票否决 - 表12"""
        stock_data = {
            'code': '000001',
            'name': '测试新股',
            'first_day_turnover': 85.0,   # >80%
            'is_small_cap': False,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertIn("抛压过重", score.veto_reason)
    
    def test_veto_high_turnover_small_cap(self):
        """测试小盘股换手率过高一票否决 - 表12"""
        stock_data = {
            'code': '000001',
            'name': '测试新股',
            'first_day_turnover': 95.0,   # >90%
            'is_small_cap': True,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertIn("抛压过重", score.veto_reason)
    
    def test_veto_low_turnover(self):
        """测试换手率过低一票否决 - 表12"""
        stock_data = {
            'code': '000001',
            'name': '测试新股',
            'first_day_turnover': 40.0,   # <50%
            'is_small_cap': False,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertIn("惜售", score.veto_reason)
    
    def test_veto_closing_gain_too_high(self):
        """测试尾盘涨幅过高一票否决 - 表12"""
        stock_data = {
            'code': '000001',
            'name': '测试新股',
            'first_day_turnover': 65.0,
            'is_small_cap': False,
            'closing_gain_pct': 120.0,    # >100%
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertIn("透支空间", score.veto_reason)
    
    def test_veto_new_low(self):
        """测试创新低一票否决 - 表12"""
        stock_data = {
            'code': '000001',
            'name': '测试新股',
            'first_day_turnover': 65.0,
            'is_small_cap': False,
            'is_new_low': True,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertIn("无企稳", score.veto_reason)
    
    def test_veto_seller_institution(self):
        """测试卖方机构一票否决 - 表12"""
        stock_data = {
            'code': '000001',
            'name': '测试新股',
            'first_day_turnover': 65.0,
            'is_small_cap': False,
            'seller_institution': True,
        }
        score = self.scorer.score(stock_data)
        self.assertFalse(score.veto_passed)
        self.assertIn("机构", score.veto_reason)
    
    def test_turnover_scoring_standard(self):
        """测试标准盘股换手率评分 - 表13"""
        test_cases = [
            (70.0, 25.0),   # 60%-80%
            (60.0, 25.0),   # 边界60%
            (80.0, 25.0),   # 边界80%
            (55.0, 15.0),   # 50%-60%
            (90.0, 5.0),    # 其他
        ]
        for turnover, expected in test_cases:
            score = self.scorer._score_new_stock_turnover(turnover, False)
            self.assertEqual(score, expected, f"标准盘换手率{turnover}%应得{expected}分")
    
    def test_turnover_scoring_small_cap(self):
        """测试小盘股换手率评分 - 表13"""
        test_cases = [
            (80.0, 25.0),   # 70%-90%
            (70.0, 25.0),   # 边界70%
            (90.0, 25.0),   # 边界90%
            (65.0, 15.0),   # 60%-70%
            (95.0, 5.0),    # 其他
        ]
        for turnover, expected in test_cases:
            score = self.scorer._score_new_stock_turnover(turnover, True)
            self.assertEqual(score, expected, f"小盘换手率{turnover}%应得{expected}分")
    
    def test_pe_ratio_scoring(self):
        """测试发行估值评分 - 表13"""
        test_cases = [
            (20.0, 25.0, 20.0),   # PE=20, 行业PE=25, 比值0.8 <= 1.2
            (30.0, 25.0, 20.0),   # 比值1.2 <= 1.2
            (37.5, 25.0, 10.0),   # 比值1.5 <= 1.5
            (50.0, 25.0, 5.0),    # 比值2.0 > 1.5
        ]
        for pe, industry_pe, expected in test_cases:
            score = self.scorer._score_pe_ratio(pe, industry_pe)
            self.assertEqual(score, expected, f"PE{pe}/行业PE{industry_pe}应得{expected}分")
    
    def test_position_sizing(self):
        """测试次新股仓位 - 严格按设计文档"""
        test_cases = [
            (95, 0.05),   # 90-100分：5%
            (85, 0.03),   # 80-89分：3%
            (80, 0.03),   # 80分：3%（>=80且<90）
            (75, 0.02),   # 75分：2%（>=65的默认）
        ]
        for score_val, expected_pct in test_cases:
            pct = self.scorer._get_position_pct(score_val, StrategyType.NEW_STOCK)
            self.assertEqual(pct, expected_pct, f"{score_val}分应建议仓位{expected_pct}")


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
    
    def test_new_stock_position_limit(self):
        """测试次新股仓位限制"""
        # 次新股仓位超过5%应被拒绝
        can_open, reason = self.pm.can_open_position(0.10, StrategyType.NEW_STOCK)
        self.assertFalse(can_open)
        self.assertIn("次新股", reason)
    
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
        self.assertAlmostEqual(position.stop_loss_price, 9.3, places=1)
    
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
        self.assertGreaterEqual(len(signals), 1)
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
                    'has_limit_up_history': True,
                }
            ]
        }
        
        scores = self.pipeline.scan_strategies(stocks_data)
        self.assertEqual(len(scores), 2)
    
    def test_multi_strategy_bonus(self):
        """测试多策略加分 - 严格按3.1节"""
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
        self.assertEqual(result[0].total_score, 83.0)  # 80 + 3（2个策略+3分）
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
                    'has_limit_up_history': True,
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
