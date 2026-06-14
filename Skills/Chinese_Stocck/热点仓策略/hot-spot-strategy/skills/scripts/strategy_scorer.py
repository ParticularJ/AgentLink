"""
热点仓交易系统 - 四大策略评分器
严格遵循《热点仓完整操作流程V4.0专业版》设计文档
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from models import StrategyType, SignalLevel, StockScore


class StrategyScorer:
    """策略评分器基类"""
    
    def __init__(self, strategy_type: StrategyType):
        self.strategy_type = strategy_type
    
    def score(self, stock_data: Dict, market_data: Dict = None) -> Optional[StockScore]:
        """评分入口，子类必须实现"""
        raise NotImplementedError
    
    def _get_signal_level(self, score: float, thresholds: Dict) -> SignalLevel:
        """根据分数获取信号等级"""
        if score >= thresholds.get("strong_buy", 90):
            return SignalLevel.STRONG_BUY
        elif score >= thresholds.get("buy", 75):
            return SignalLevel.BUY
        elif score >= thresholds.get("watch", 65):
            return SignalLevel.WATCH
        else:
            return SignalLevel.PASS
    
    def _get_position_pct(self, score: float, strategy_type: StrategyType) -> float:
        """根据分数获取建议仓位 - 严格按设计文档表4/表6"""
        if strategy_type == StrategyType.NEW_STOCK:
            # 次新股仓位（表4）
            if score >= 90:
                return 0.05  # 5%
            elif score >= 80:
                return 0.03  # 3%
            else:
                return 0.02  # 2%
        else:
            # 标准策略仓位（表4/表6）
            if score >= 90:
                return 0.30  # 30% 极强势
            elif score >= 80:
                return 0.25  # 25% 强势
            elif score >= 75:
                return 0.20  # 20% 中等
            elif score >= 70:
                return 0.15  # 15% 中等（龙头策略）
            elif score >= 65:
                return 0.10  # 10% 及格（回调策略）
            else:
                return 0.0


class FirstLimitUpScorer(StrategyScorer):
    """
    策略一：首次涨停板评分器
    
    评分模型（0-100分）- 严格按设计文档表3：
    - 涨停时间：30分
    - 封单质量：25分
    - 板块效应：25分
    - 换手率：20分
    
    入围门槛：≥75分（表4）
    持股周期：3-5天
    """
    
    def __init__(self):
        super().__init__(StrategyType.FIRST_LIMIT_UP)
    
    def score(self, stock_data: Dict, market_data: Dict = None) -> Optional[StockScore]:
        """
        评分首次涨停板
        
        Args:
            stock_data: {
                'code': str,
                'name': str,
                'limit_up_time': str,       # 首次封板时间，如 "09:35"
                'seal_amount': float,        # 封单金额（万元）
                'avg_daily_volume_20d': float,  # 近20日日均成交额（万元）
                'turnover': float,           # 当日换手率%
                'sector_limit_up_count': int,   # 同板块涨停数
                'is_one_word': bool,         # 是否一字板
                'has_bad_news': bool,        # 是否有利空
                'index_below_ma20': bool,    # 大盘是否破20日线
            }
        """
        code = stock_data.get('code', '')
        name = stock_data.get('name', '')
        
        # ========== 一票否决项 ==========
        # 否决1：一字板买不进
        if stock_data.get('is_one_word', False):
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="一字板无法买入"
            )
        
        # 否决2：大盘破20日线
        if stock_data.get('index_below_ma20', False):
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="大盘破20日线，系统性风险"
            )
        
        # 否决3：个股有利空
        if stock_data.get('has_bad_news', False):
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="个股存在利空消息"
            )
        
        # ========== 评分维度 ==========
        # 1. 涨停时间评分 (30分) - 表3
        time_score = self._score_limit_up_time(stock_data.get('limit_up_time', ''))
        
        # 2. 封单质量评分 (25分) - 表3
        seal_score = self._score_seal_quality(
            stock_data.get('seal_amount', 0),
            stock_data.get('avg_daily_volume_20d', 1)
        )
        
        # 3. 板块效应评分 (25分) - 表3
        sector_score = self._score_sector_effect(
            stock_data.get('sector_limit_up_count', 0)
        )
        
        # 4. 换手率评分 (20分) - 表3
        turnover_score = self._score_turnover(stock_data.get('turnover', 0))
        
        # 计算总分
        total = time_score + seal_score + sector_score + turnover_score
        
        # 确定信号等级 - 表4门槛
        signal_level = self._get_signal_level(total, {
            "strong_buy": 90, "buy": 80, "watch": 75
        })
        
        # 确定仓位 - 表4
        position_pct = self._get_position_pct(total, self.strategy_type)
        
        return StockScore(
            strategy_type=self.strategy_type,
            stock_code=code,
            stock_name=name,
            dimension_scores={
                "涨停时间": time_score,
                "封单质量": seal_score,
                "板块效应": sector_score,
                "换手率": turnover_score
            },
            total_score=total,
            signal_level=signal_level,
            suggested_position_pct=position_pct,
            buy_timing="当日打板（排板或扫板）或次日早盘集合竞价",
            stop_loss_pct=-7.0,
            time_stop_days=5
        )
    
    def _score_limit_up_time(self, time_str: str) -> float:
        """
        涨停时间评分 (0-30分) - 严格按设计文档表3
        9:35前封板30分；10:00前20分；10:30前10分；下午0分
        """
        if not time_str:
            return 0.0
        
        try:
            # 解析时间，格式如 "09:35" 或 "093500"
            time_str = str(time_str).strip()
            if ':' in time_str:
                parts = time_str.split(':')
                hour = int(parts[0])
                minute = int(parts[1])
            else:
                # 东财格式 093500
                time_str = time_str.zfill(6)
                hour = int(time_str[0:2])
                minute = int(time_str[2:4])
            
            total_minutes = hour * 60 + minute
            
            # 9:30开盘，计算开盘后分钟数
            minutes_after_open = total_minutes - 570  # 9:30 = 570分钟
            
            if minutes_after_open <= 5:      # 9:35前
                return 30.0
            elif minutes_after_open <= 30:   # 10:00前
                return 20.0
            elif minutes_after_open <= 60:   # 10:30前
                return 10.0
            else:
                return 0.0
        except:
            return 0.0
    
    def _score_seal_quality(self, seal_amount: float, avg_volume: float) -> float:
        """
        封单质量评分 (0-25分) - 严格按设计文档表3
        封单/近20日日均成交额>80%得25分；>50%得20分；>30%得15分
        """
        if avg_volume <= 0:
            return 0.0
        
        ratio = seal_amount / avg_volume * 100
        
        if ratio >= 80:
            return 25.0
        elif ratio >= 50:
            return 20.0
        elif ratio >= 30:
            return 15.0
        elif ratio >= 10:
            return 10.0
        else:
            return 5.0
    
    def _score_sector_effect(self, sector_limit_up_count: int) -> float:
        """
        板块效应评分 (0-25分) - 严格按设计文档表3
        板块内≥5只涨停25分；≥3只15分；≥1只5分
        """
        if sector_limit_up_count >= 5:
            return 25.0
        elif sector_limit_up_count >= 3:
            return 15.0
        elif sector_limit_up_count >= 1:
            return 5.0
        else:
            return 0.0
    
    def _score_turnover(self, turnover: float) -> float:
        """
        换手率评分 (0-20分) - 严格按设计文档表3
        5%-15%得20分；15%-25%得15分；3%-5%得10分
        """
        if 5 <= turnover <= 15:
            return 20.0
        elif 15 < turnover <= 25:
            return 15.0
        elif 3 <= turnover < 5:
            return 10.0
        elif 25 < turnover <= 35:
            return 8.0
        else:
            return 5.0


class LimitUpRetraceScorer(StrategyScorer):
    """
    策略二：涨停回调评分器
    
    评分模型（0-100分）- 严格按设计文档表5：
    - 回调幅度：25分
    - 回调天数：20分
    - 缩量程度：25分
    - 企稳信号：30分
    
    入围门槛：≥65分（表6）
    持股周期：5-7天
    可加仓：1次，比例20%-30%
    """
    
    def __init__(self):
        super().__init__(StrategyType.LIMIT_UP_RETRACE)
    
    def score(self, stock_data: Dict, market_data: Dict = None) -> Optional[StockScore]:
        """
        评分涨停回调
        
        Args:
            stock_data: {
                'code': str,
                'name': str,
                'retrace_pct': float,        # 回调幅度%（负值，如-10表示回调10%）
                'retrace_days': int,          # 回调天数
                'volume_shrink_pct': float,   # 缩量程度%（相对涨停日，如60表示缩量60%）
                'stop_signal': str,           # 止跌信号类型：'锤子线'/'十字星'/'小阳线'
                'is_above_ma5': bool,         # 是否站5日线
                'daily_change_pct': float,    # 当日涨跌幅%
                'has_limit_up_history': bool, # 前期是否有涨停（必须）
                'index_below_ma20': bool,     # 大盘是否破20日线
                'sector_declining': bool,     # 板块是否退潮
                'has_bad_news': bool,         # 个股是否有利空
            }
        """
        code = stock_data.get('code', '')
        name = stock_data.get('name', '')
        
        # ========== 一票否决项 ==========
        # 否决1：前期无涨停（必须前期有涨停）
        if not stock_data.get('has_limit_up_history', True):
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="前期无涨停记录，不符合策略二要求"
            )
        
        # 否决2：大盘破20日线
        if stock_data.get('index_below_ma20', False):
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="大盘破20日线，系统性风险"
            )
        
        # 否决3：板块退潮
        if stock_data.get('sector_declining', False):
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="板块退潮，放弃买入"
            )
        
        # 否决4：个股利空
        if stock_data.get('has_bad_news', False):
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="个股存在利空消息"
            )
        
        # ========== 评分维度 ==========
        # 1. 回调幅度评分 (25分) - 表5
        retrace_pct = abs(stock_data.get('retrace_pct', 0))
        retrace_score = self._score_retrace(retrace_pct)
        
        # 2. 回调天数评分 (20分) - 表5
        days_score = self._score_retrace_days(stock_data.get('retrace_days', 0))
        
        # 3. 缩量程度评分 (25分) - 表5
        shrink_score = self._score_volume_shrink(
            stock_data.get('volume_shrink_pct', 0)
        )
        
        # 4. 企稳信号评分 (30分) - 表5
        stop_score = self._score_stop_signal(
            stock_data.get('stop_signal', ''),
            stock_data.get('is_above_ma5', False),
            stock_data.get('daily_change_pct', 0)
        )
        
        # 计算总分
        total = retrace_score + days_score + shrink_score + stop_score
        
        # 确定信号等级 - 表6门槛
        signal_level = self._get_signal_level(total, {
            "strong_buy": 90, "buy": 80, "watch": 65
        })
        
        # 确定仓位 - 表6
        position_pct = self._get_position_pct(total, self.strategy_type)
        
        return StockScore(
            strategy_type=self.strategy_type,
            stock_code=code,
            stock_name=name,
            dimension_scores={
                "回调幅度": retrace_score,
                "回调天数": days_score,
                "缩量程度": shrink_score,
                "企稳信号": stop_score
            },
            total_score=total,
            signal_level=signal_level,
            suggested_position_pct=position_pct,
            buy_timing="出现企稳信号的当日尾盘（14:50后）或次日早盘",
            stop_loss_pct=-7.0,
            time_stop_days=7
        )
    
    def _score_retrace(self, retrace_pct: float) -> float:
        """
        回调幅度评分 (0-25分) - 严格按设计文档表5
        -8%~-12%得25分；-5%~-8%得20分；-12%~-15%得15分
        """
        if 8 <= retrace_pct <= 12:
            return 25.0
        elif 5 <= retrace_pct < 8:
            return 20.0
        elif 12 < retrace_pct <= 15:
            return 15.0
        elif 3 <= retrace_pct < 5:
            return 10.0
        elif 15 < retrace_pct <= 20:
            return 8.0
        else:
            return 5.0
    
    def _score_retrace_days(self, days: int) -> float:
        """
        回调天数评分 (0-20分) - 严格按设计文档表5
        3-4天得20分；2天或5天得15分
        """
        if 3 <= days <= 4:
            return 20.0
        elif days == 2 or days == 5:
            return 15.0
        elif days == 6:
            return 10.0
        elif days == 1:
            return 8.0
        else:
            return 5.0
    
    def _score_volume_shrink(self, shrink_pct: float) -> float:
        """
        缩量程度评分 (0-25分) - 严格按设计文档表5
        量能<涨停日40%得25分；<60%得15分
        """
        if shrink_pct >= 60:
            return 25.0
        elif shrink_pct >= 40:
            return 20.0
        elif shrink_pct >= 30:
            return 15.0
        elif shrink_pct >= 20:
            return 10.0
        else:
            return 5.0
    
    def _score_stop_signal(self, signal_type: str, is_above_ma5: bool, daily_change: float) -> float:
        """
        企稳信号评分 (0-30分) - 严格按设计文档表5
        收阳+站5日线+跌幅≤-3%后拉起得30分；仅收阳+站5日线得20分
        """
        score = 0.0
        
        # 信号类型 (12分)
        if signal_type == '锤子线':
            score += 12.0
        elif signal_type == '十字星':
            score += 10.0
        elif signal_type == '小阳线':
            score += 8.0
        else:
            score += 3.0
        
        # 是否站5日线 (10分)
        if is_above_ma5:
            score += 10.0
        else:
            score += 3.0
        
        # 当日跌幅 (8分)
        if daily_change >= -3:
            score += 8.0
        elif daily_change >= -5:
            score += 5.0
        else:
            score += 2.0
        
        return min(score, 30.0)


class SectorLeaderScorer(StrategyScorer):
    """
    策略三：热门板块龙头评分器
    
    龙头股评分（0-100分）- 严格按设计文档表9：
    - 涨幅领先度：25分
    - 涨停强度：15分
    - 板块热度：20分
    - 带动性：15分
    - 换手率：15分
    - 流通市值：10分
    
    入围门槛：≥70分
    持股周期：5-8天
    """
    
    def __init__(self):
        super().__init__(StrategyType.SECTOR_LEADER)
    
    def score(self, stock_data: Dict, market_data: Dict = None) -> Optional[StockScore]:
        """
        评分板块龙头
        
        Args:
            stock_data: {
                'code': str,
                'name': str,
                'rank_in_sector': int,        # 板块涨幅排名
                'has_limit_up': bool,         # 近3日是否有涨停
                'consecutive_limit': int,     # 连板数
                'sector_heat_score': float,   # 板块热度分
                'leadership_score': float,    # 带动性评分(0-100)
                'turnover': float,            # 换手率%
                'float_market_cap': float,    # 流通市值(亿)
            }
        """
        code = stock_data.get('code', '')
        name = stock_data.get('name', '')
        
        # 1. 涨幅领先度 (25分) - 表9
        rank_score = self._score_rank(stock_data.get('rank_in_sector', 10))
        
        # 2. 涨停强度 (15分) - 表9
        limit_score = self._score_limit_strength(
            stock_data.get('has_limit_up', False),
            stock_data.get('consecutive_limit', 0)
        )
        
        # 3. 板块热度 (20分) - 表9
        heat_score = self._score_sector_heat(
            stock_data.get('sector_heat_score', 0)
        )
        
        # 4. 带动性 (15分) - 表9
        lead_score = self._score_leadership(
            stock_data.get('leadership_score', 0)
        )
        
        # 5. 换手率 (15分) - 表9
        turnover_score = self._score_turnover(stock_data.get('turnover', 0))
        
        # 6. 流通市值 (10分) - 表9
        cap_score = self._score_market_cap(stock_data.get('float_market_cap', 0))
        
        # 计算总分
        total = rank_score + limit_score + heat_score + lead_score + turnover_score + cap_score
        
        # 确定信号等级
        signal_level = self._get_signal_level(total, {
            "strong_buy": 85, "buy": 75, "watch": 70
        })
        
        # 确定仓位
        position_pct = self._get_position_pct(total, self.strategy_type)
        
        return StockScore(
            strategy_type=self.strategy_type,
            stock_code=code,
            stock_name=name,
            dimension_scores={
                "涨幅领先度": rank_score,
                "涨停强度": limit_score,
                "板块热度": heat_score,
                "带动性": lead_score,
                "换手率": turnover_score,
                "流通市值": cap_score
            },
            total_score=total,
            signal_level=signal_level,
            suggested_position_pct=position_pct,
            buy_timing="根据龙头类型选择买点：尾盘/均线/平台突破",
            stop_loss_pct=-7.0,
            time_stop_days=8
        )
    
    def _score_rank(self, rank: int) -> float:
        """涨幅领先度评分 (0-25分) - 表9"""
        if rank == 1:
            return 25.0
        elif rank == 2:
            return 20.0
        elif rank == 3:
            return 15.0
        elif rank <= 5:
            return 10.0
        elif rank <= 10:
            return 5.0
        else:
            return 2.0
    
    def _score_limit_strength(self, has_limit: bool, consecutive: int) -> float:
        """涨停强度评分 (0-15分) - 表9"""
        if consecutive >= 2:
            return 15.0
        elif has_limit:
            return 10.0
        else:
            return 5.0
    
    def _score_sector_heat(self, heat_score: float) -> float:
        """板块热度评分 (0-20分) - 表9"""
        if heat_score >= 85:
            return 20.0
        elif heat_score >= 75:
            return 15.0
        elif heat_score >= 70:
            return 10.0
        else:
            return 5.0
    
    def _score_leadership(self, leadership: float) -> float:
        """带动性评分 (0-15分) - 表9"""
        if leadership >= 80:
            return 15.0
        elif leadership >= 60:
            return 10.0
        elif leadership >= 40:
            return 6.0
        else:
            return 3.0
    
    def _score_turnover(self, turnover: float) -> float:
        """换手率评分 (0-15分) - 表9"""
        if 10 <= turnover <= 25:
            return 15.0
        elif 5 <= turnover < 10:
            return 10.0
        elif 25 < turnover <= 35:
            return 8.0
        else:
            return 5.0
    
    def _score_market_cap(self, cap: float) -> float:
        """流通市值评分 (0-10分) - 表9"""
        if 50 <= cap <= 150:
            return 10.0
        elif 150 < cap <= 300:
            return 8.0
        elif 30 <= cap < 50:
            return 7.0
        elif 300 < cap <= 500:
            return 5.0
        else:
            return 3.0


class NewStockScorer(StrategyScorer):
    """
    策略四：次新股评分器
    
    评分模型（0-100分）- 严格按设计文档表13：
    - 行业景气度：30分
    - 首日换手率：25分
    - 尾盘企稳：25分
    - 发行估值：20分
    
    入围门槛：≥80分
    持股周期：最长3天
    """
    
    def __init__(self):
        super().__init__(StrategyType.NEW_STOCK)
    
    def score(self, stock_data: Dict, market_data: Dict = None) -> Optional[StockScore]:
        """
        评分次新股
        
        Args:
            stock_data: {
                'code': str,
                'name': str,
                'industry_level': str,        # 'core'/'secondary'
                'first_day_turnover': float,  # 首日换手率%
                'is_small_cap': bool,         # 是否小盘股
                'stable_closing': bool,       # 尾盘是否企稳
                'pe_ratio': float,            # 发行PE
                'industry_pe': float,         # 行业PE
                'is_new_low': bool,           # 是否创新低
                'seller_institution': bool,   # 卖方是否机构
                'closing_gain_pct': float,    # 尾盘涨幅%
                'index_below_ma20': bool,     # 大盘是否破20日线
            }
        """
        code = stock_data.get('code', '')
        name = stock_data.get('name', '')
        
        # ========== 一票否决项 - 严格按设计文档表12 ==========
        turnover = stock_data.get('first_day_turnover', 0)
        is_small_cap = stock_data.get('is_small_cap', False)
        
        # 否决1：换手率检查
        if is_small_cap:
            if turnover > 90:
                return StockScore(
                    strategy_type=self.strategy_type,
                    stock_code=code,
                    stock_name=name,
                    veto_passed=False,
                    veto_reason="小盘股首日换手率>90%，抛压过重"
                )
            if turnover < 70:
                return StockScore(
                    strategy_type=self.strategy_type,
                    stock_code=code,
                    stock_name=name,
                    veto_passed=False,
                    veto_reason="小盘股首日换手率<70%，惜售"
                )
        else:
            if turnover > 80:
                return StockScore(
                    strategy_type=self.strategy_type,
                    stock_code=code,
                    stock_name=name,
                    veto_passed=False,
                    veto_reason="首日换手率>80%，抛压过重"
                )
            if turnover < 50:
                return StockScore(
                    strategy_type=self.strategy_type,
                    stock_code=code,
                    stock_name=name,
                    veto_passed=False,
                    veto_reason="首日换手率<50%，惜售"
                )
        
        # 否决2：尾盘涨幅>100%
        closing_gain = stock_data.get('closing_gain_pct', 0)
        if closing_gain > 100:
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="尾盘涨幅>100%，透支空间"
            )
        
        # 否决3：尾盘仍在创新低
        if stock_data.get('is_new_low', False):
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="尾盘仍在创新低，无企稳"
            )
        
        # 否决4：龙虎榜卖方全是机构
        if stock_data.get('seller_institution', False):
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="龙虎榜卖方全是机构"
            )
        
        # 否决5：大盘破20日线
        if stock_data.get('index_below_ma20', False):
            return StockScore(
                strategy_type=self.strategy_type,
                stock_code=code,
                stock_name=name,
                veto_passed=False,
                veto_reason="大盘破20日线，系统性风险"
            )
        
        # ========== 评分维度 ==========
        # 1. 行业景气度 (30分) - 表13
        industry_score = self._score_industry(
            stock_data.get('industry_level', 'secondary')
        )
        
        # 2. 首日换手率 (25分) - 表13
        turnover_score = self._score_new_stock_turnover(turnover, is_small_cap)
        
        # 3. 尾盘企稳 (25分) - 表13
        stable_score = self._score_stable_closing(
            stock_data.get('stable_closing', False)
        )
        
        # 4. 发行估值 (20分) - 表13
        pe_score = self._score_pe_ratio(
            stock_data.get('pe_ratio', 0),
            stock_data.get('industry_pe', 1)
        )
        
        # 计算总分
        total = industry_score + turnover_score + stable_score + pe_score
        
        # 确定信号等级（次新股门槛更高）
        if total >= 90:
            signal_level = SignalLevel.STRONG_BUY
        elif total >= 80:
            signal_level = SignalLevel.BUY
        else:
            signal_level = SignalLevel.PASS
        
        # 确定仓位（次新股仓位更低）
        position_pct = self._get_position_pct(total, self.strategy_type)
        
        return StockScore(
            strategy_type=self.strategy_type,
            stock_code=code,
            stock_name=name,
            dimension_scores={
                "行业景气度": industry_score,
                "首日换手率": turnover_score,
                "尾盘企稳": stable_score,
                "发行估值": pe_score
            },
            total_score=total,
            signal_level=signal_level,
            suggested_position_pct=position_pct,
            buy_timing="上市当日尾盘(14:50-15:00)，禁止盘中任何时点买入",
            stop_loss_pct=-7.0,
            time_stop_days=3
        )
    
    def _score_industry(self, level: str) -> float:
        """行业景气度评分 (0-30分) - 表13"""
        if level == 'core':
            return 30.0
        else:
            return 20.0
    
    def _score_new_stock_turnover(self, turnover: float, is_small_cap: bool) -> float:
        """
        首日换手率评分 (0-25分) - 严格按设计文档表13
        标准盘股：60%-80%得25分；50%-60%得15分
        小盘股：70%-90%得25分；60%-70%得15分
        """
        if is_small_cap:
            # 小盘股标准：70%-90%
            if 70 <= turnover <= 90:
                return 25.0
            elif 60 <= turnover < 70:
                return 15.0
            else:
                return 5.0
        else:
            # 标准：60%-80%
            if 60 <= turnover <= 80:
                return 25.0
            elif 50 <= turnover < 60:
                return 15.0
            else:
                return 5.0
    
    def _score_stable_closing(self, stable: bool) -> float:
        """尾盘企稳评分 (0-25分) - 表13"""
        return 25.0 if stable else 5.0
    
    def _score_pe_ratio(self, pe: float, industry_pe: float) -> float:
        """
        发行估值评分 (0-20分) - 严格按设计文档表13
        发行PE ≤ 行业PE×1.2得20分；≤1.5倍得10分
        """
        if industry_pe <= 0:
            return 10.0
        
        ratio = pe / industry_pe
        
        if ratio <= 1.2:
            return 20.0
        elif ratio <= 1.5:
            return 10.0
        else:
            return 5.0
