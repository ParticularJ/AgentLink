"""
波段交易系统 - 第一阶段：大盘环境评估
"""
from typing import Dict, Optional
from src.common.models import MarketEnvironmentScore, MarketEnvironment, MarketStatus
from src.common.constants import (
    MARKET_ENVIRONMENT_THRESHOLDS,
    MARKET_STATUS_RPS_THRESHOLDS,
    MARKET_LIQUIDITY_THRESHOLDS,
)


class MarketEnvironmentEvaluator:
    """大盘环境评估器"""

    def __init__(self):
        pass

    def evaluate_index_trend(
        self,
        rps50: float,
        rps120: float,
        ma20: float,
        ma60: float,
        current_index: float,
    ) -> float:
        """
        评估指数趋势
        
        Args:
            rps50: 沪深300 RPS50
            rps120: 沪深300 RPS120
            ma20: 20日均线
            ma60: 60日均线
            current_index: 当前指数点位
            
        Returns:
            0-40分
        """
        # 多头排列(20>60>120)且指数在两线之上
        if ma20 > ma60 and current_index > ma20 and current_index > ma60:
            if rps50 > 70 and rps120 > 60:
                return 35.0 + min((rps50 - 70) / 30 * 5, 5.0)
            else:
                return 30.0
        # 震荡(20与60纠缠)
        elif abs(ma20 - ma60) / ma60 < 0.05:
            return 22.0
        # 空头排列
        else:
            if rps50 < 40 and rps120 < 40:
                return 5.0
            else:
                return 10.0

    def evaluate_liquidity(
        self,
        avg_daily_volume_5d: float,  # 亿元
    ) -> float:
        """
        评估市场流动性
        
        Args:
            avg_daily_volume_5d: 近5日全市场日均成交额（亿元）
            
        Returns:
            0-30分
        """
        if avg_daily_volume_5d >= MARKET_LIQUIDITY_THRESHOLDS["high"]:
            return 25.0 + min((avg_daily_volume_5d - 15000) / 5000 * 5, 5.0)
        elif avg_daily_volume_5d >= MARKET_LIQUIDITY_THRESHOLDS["medium"]:
            return 15.0 + (avg_daily_volume_5d - 8000) / 7000 * 9
        else:
            return max(avg_daily_volume_5d / 8000 * 14, 0.0)

    def evaluate_sentiment(
        self,
        rise_fall_ratio: float,  # 涨跌比
        limit_up_count: int,     # 涨停家数
    ) -> float:
        """
        评估市场情绪
        
        Args:
            rise_fall_ratio: 涨跌比
            limit_up_count: 涨停家数
            
        Returns:
            0-20分
        """
        if rise_fall_ratio >= 3.0 and limit_up_count >= 80:
            return 15.0 + min((rise_fall_ratio - 3) / 2 * 5, 5.0)
        elif 1.0 <= rise_fall_ratio < 3.0:
            return 8.0 + (rise_fall_ratio - 1) / 2 * 6
        else:
            return max(rise_fall_ratio * 7, 0.0)

    def evaluate_northbound(
        self,
        net_inflow_20d: float,  # 近20日累计净流入（亿元）
    ) -> float:
        """
        评估北向资金
        
        Args:
            net_inflow_20d: 近20日累计净流入（亿元）
            
        Returns:
            0-10分
        """
        if net_inflow_20d >= 200:
            return 8.0 + min((net_inflow_20d - 200) / 100 * 2, 2.0)
        elif net_inflow_20d >= 0:
            return 4.0 + net_inflow_20d / 200 * 4
        else:
            return max(3.0 + net_inflow_20d / 100, 0.0)

    def determine_market_status(
        self,
        rps50: float,
        rps120: float,
    ) -> MarketStatus:
        """
        判定市场状态
        
        Args:
            rps50: RPS50
            rps120: RPS120
            
        Returns:
            MarketStatus
        """
        bull_threshold = MARKET_STATUS_RPS_THRESHOLDS["bull"]
        bear_threshold = MARKET_STATUS_RPS_THRESHOLDS["bear"]

        if rps50 >= bull_threshold["rps50"] and rps120 >= bull_threshold["rps120"]:
            return MarketStatus.BULL
        elif rps50 <= bear_threshold["rps50"] and rps120 <= bear_threshold["rps120"]:
            return MarketStatus.BEAR
        else:
            return MarketStatus.OSCILLATION

    def evaluate(
        self,
        rps50: float,
        rps120: float,
        ma20: float,
        ma60: float,
        current_index: float,
        avg_daily_volume_5d: float,
        rise_fall_ratio: float,
        limit_up_count: int,
        net_inflow_20d: float,
    ) -> MarketEnvironmentScore:
        """
        综合评估大盘环境
        
        Returns:
            MarketEnvironmentScore
        """
        index_trend = self.evaluate_index_trend(rps50, rps120, ma20, ma60, current_index)
        liquidity = self.evaluate_liquidity(avg_daily_volume_5d)
        sentiment = self.evaluate_sentiment(rise_fall_ratio, limit_up_count)
        northbound = self.evaluate_northbound(net_inflow_20d)

        total = index_trend + liquidity + sentiment + northbound

        # 判定环境等级
        if total >= MARKET_ENVIRONMENT_THRESHOLDS["green"]:
            environment = MarketEnvironment.GREEN
        elif total >= MARKET_ENVIRONMENT_THRESHOLDS["yellow"]:
            environment = MarketEnvironment.YELLOW
        else:
            environment = MarketEnvironment.RED

        market_status = self.determine_market_status(rps50, rps120)

        return MarketEnvironmentScore(
            index_trend_score=index_trend,
            liquidity_score=liquidity,
            sentiment_score=sentiment,
            northbound_score=northbound,
            total_score=total,
            environment=environment,
            market_status=market_status,
        )

    def should_suspend_screening(self, score: MarketEnvironmentScore) -> bool:
        """
        判断是否暂停初筛
        
        Args:
            score: 大盘环境评分
            
        Returns:
            是否暂停
        """
        return score.environment == MarketEnvironment.RED

    def get_screening_adjustments(self, score: MarketEnvironmentScore) -> Dict:
        """
        获取初筛流程调整参数
        
        Args:
            score: 大盘环境评分
            
        Returns:
            调整参数字典
        """
        if score.environment == MarketEnvironment.GREEN:
            return {
                "track_filter": "all",           # 筛选全部赛道
                "rise_threshold_multiplier": 1.0,  # 标准阈值
                "position_limit": 1.0,            # 标准仓位上限
            }
        elif score.environment == MarketEnvironment.YELLOW:
            return {
                "track_filter": "S_only",        # 仅筛选S级赛道
                "rise_threshold_multiplier": 0.8,  # 阈值收紧
                "position_limit": 0.5,            # 仓位上限减半
            }
        else:  # RED
            return {
                "track_filter": "none",          # 暂停筛选
                "rise_threshold_multiplier": 0.0,
                "position_limit": 0.0,
            }
