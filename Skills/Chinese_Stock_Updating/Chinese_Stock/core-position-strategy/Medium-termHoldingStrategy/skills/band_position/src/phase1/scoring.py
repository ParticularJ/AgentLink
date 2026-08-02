"""
波段交易系统 - 第一阶段：三因子评分模型
"""
from typing import Optional, List, Tuple
from src.common.models import (
    Stock, Track, Phase1Score, Grade, MarketStatus,
    PositionRating, ChainLevel
)
from src.common.constants import (
    INDUSTRY_MOMENTUM_WEIGHTS,
    FLEXIBILITY_WEIGHTS,
    SAFETY_MARGIN_WEIGHTS,
    PHASE1_PASS_SCORE,
    GRADE_THRESHOLDS,
    FIRST_GRADE_RATIO,
)


class Phase1Scorer:
    """第一阶段评分器"""

    def __init__(self, market_status: MarketStatus):
        self.market_status = market_status

    def score_industry_momentum(
        self,
        stock: Stock,
        track: Track,
        catalyst_count: int = 0,
    ) -> float:
        """
        产业动量评分（满分35分）
        
        Args:
            stock: 股票
            track: 赛道
            catalyst_count: 未来30天催化事件数量
            
        Returns:
            0-35分
        """
        # 赛道评级分数
        if track.rating.value == "S级":
            track_score = 15.0
        elif track.rating.value == "A级":
            track_score = 11.0
        else:
            track_score = 7.0

        # 产业链卡位分数
        if stock.position_rating == PositionRating.CORE:
            position_score = 12.0
        elif stock.position_rating == PositionRating.IMPORTANT:
            position_score = 8.0
        elif stock.position_rating == PositionRating.GENERAL:
            position_score = 5.0
        else:
            position_score = 2.0

        # 催化日历密度
        if catalyst_count >= 2:
            catalyst_score = 8.0
        elif catalyst_count >= 1:
            catalyst_score = 4.0
        else:
            catalyst_score = 0.0

        return track_score + position_score + catalyst_score

    def score_individual_flexibility(
        self,
        stock: Stock,
        historical_avg_rise: float = 0.0,
        historical_win_rate: float = 0.0,
    ) -> float:
        """
        个股弹性评分（满分35分）
        
        Args:
            stock: 股票
            historical_avg_rise: 近2年波段平均涨幅%
            historical_win_rate: 近2年波段胜率%
            
        Returns:
            0-35分
        """
        # 流通市值分数
        cap = stock.float_market_cap
        if 100 <= cap <= 800:
            cap_score = 12.0
        elif 800 < cap <= 3000:
            cap_score = 9.0
        elif 3000 < cap <= 8000:
            cap_score = 5.0
        else:
            cap_score = 2.0

        # 历史股性分数
        if historical_avg_rise > 40 and historical_win_rate > 60:
            performance_score = 12.0
        elif historical_avg_rise > 30:
            performance_score = 8.0
        elif historical_avg_rise > 20:
            performance_score = 5.0
        else:
            performance_score = 2.0

        # 波动率弹性分数
        vol = stock.volatility_60d
        if 35 <= vol <= 60:
            vol_score = 11.0
        elif 25 <= vol < 35:
            vol_score = 7.0
        elif 60 < vol <= 80:
            vol_score = 5.0
        else:
            vol_score = 2.0

        return cap_score + performance_score + vol_score

    def score_safety_margin(
        self,
        stock: Stock,
        earnings_accelerating: bool = True,
        has_reduction_risk: bool = False,
        has_unlock_risk: bool = False,
    ) -> float:
        """
        安全边际评分（满分30分）
        
        Args:
            stock: 股票
            earnings_accelerating: 业绩是否连续两季度加速
            has_reduction_risk: 是否有实控人减持风险
            has_unlock_risk: 是否有未来3个月大额解禁风险
            
        Returns:
            0-30分
        """
        # 业绩趋势
        if earnings_accelerating:
            earnings_score = 12.0
        else:
            earnings_score = 7.0  # 默认给改善分

        # 减持/解禁风险
        if not has_reduction_risk and not has_unlock_risk:
            risk_score = 9.0
        elif not has_reduction_risk or not has_unlock_risk:
            risk_score = 4.0
        else:
            risk_score = 0.0

        # Beta控制
        beta = stock.beta
        if beta < 1.0:
            beta_score = 9.0
        elif 1.0 <= beta < 1.3:
            beta_score = 5.0
        elif 1.3 <= beta < 1.5:
            beta_score = 3.0
        else:
            beta_score = 1.0

        return earnings_score + risk_score + beta_score

    def calculate_total_score(
        self,
        stock: Stock,
        track: Track,
        catalyst_count: int = 0,
        historical_avg_rise: float = 0.0,
        historical_win_rate: float = 0.0,
        earnings_accelerating: bool = True,
        has_reduction_risk: bool = False,
        has_unlock_risk: bool = False,
    ) -> Phase1Score:
        """
        计算三因子总分
        
        Returns:
            Phase1Score
        """
        industry_momentum = self.score_industry_momentum(stock, track, catalyst_count)
        individual_flexibility = self.score_individual_flexibility(
            stock, historical_avg_rise, historical_win_rate
        )
        safety_margin = self.score_safety_margin(
            stock, earnings_accelerating, has_reduction_risk, has_unlock_risk
        )

        total = industry_momentum + individual_flexibility + safety_margin

        return Phase1Score(
            track_rating_score=min(industry_momentum, INDUSTRY_MOMENTUM_WEIGHTS["track_rating"]),
            chain_position_score=min(industry_momentum, INDUSTRY_MOMENTUM_WEIGHTS["chain_position"]),
            catalyst_score=min(industry_momentum, INDUSTRY_MOMENTUM_WEIGHTS["catalyst"]),
            industry_momentum=industry_momentum,
            market_cap_score=min(individual_flexibility, FLEXIBILITY_WEIGHTS["market_cap"]),
            historical_performance_score=min(individual_flexibility, FLEXIBILITY_WEIGHTS["historical_performance"]),
            volatility_score=min(individual_flexibility, FLEXIBILITY_WEIGHTS["volatility"]),
            individual_flexibility=individual_flexibility,
            earnings_trend_score=min(safety_margin, SAFETY_MARGIN_WEIGHTS["earnings_trend"]),
            reduction_risk_score=min(safety_margin, SAFETY_MARGIN_WEIGHTS["reduction_risk"]),
            beta_control_score=min(safety_margin, SAFETY_MARGIN_WEIGHTS["beta_control"]),
            safety_margin=safety_margin,
            total_score=total,
        )

    def determine_grade(
        self,
        score: Phase1Score,
        stock: Stock,
        catalyst_count: int = 0,
    ) -> Grade:
        """
        判定档位
        
        Returns:
            Grade
        """
        first_thresholds = GRADE_THRESHOLDS["first"]
        second_thresholds = GRADE_THRESHOLDS["second"]

        # 第一档判定（需满足至少4项）
        first_conditions = 0

        if stock.position_rating == PositionRating.CORE:
            first_conditions += 1

        if score.total_score >= first_thresholds["min_score"]:
            first_conditions += 1

        # 近60日涨幅检查
        rise_threshold = first_thresholds.get(f"max_rise_60d_{self.market_status.value}", 100)
        if stock.rise_60d < rise_threshold:
            first_conditions += 1

        if stock.float_market_cap < first_thresholds["max_float_market_cap"]:
            first_conditions += 1

        if stock.beta < first_thresholds["max_beta"]:
            first_conditions += 1

        if catalyst_count >= first_thresholds["min_catalyst"]:
            first_conditions += 1

        # 第二档判定
        second_conditions = 0

        if stock.position_rating in [PositionRating.CORE, PositionRating.IMPORTANT]:
            second_conditions += 1

        if second_thresholds["min_score"] <= score.total_score <= second_thresholds["max_score"]:
            second_conditions += 1

        # 判定档位 - 优先检查第一档
        if first_conditions >= 4 and score.total_score >= PHASE1_PASS_SCORE:
            return Grade.FIRST
        
        # 第二档条件放宽：总分>=70且不是第三档
        if score.total_score >= PHASE1_PASS_SCORE:
            return Grade.SECOND
        
        return Grade.THIRD

    def score_and_grade(
        self,
        stock: Stock,
        track: Track,
        catalyst_count: int = 0,
        historical_avg_rise: float = 0.0,
        historical_win_rate: float = 0.0,
        earnings_accelerating: bool = True,
        has_reduction_risk: bool = False,
        has_unlock_risk: bool = False,
    ) -> Phase1Score:
        """
        评分并判定档位
        
        Returns:
            Phase1Score（包含档位）
        """
        score = self.calculate_total_score(
            stock, track, catalyst_count,
            historical_avg_rise, historical_win_rate,
            earnings_accelerating, has_reduction_risk, has_unlock_risk
        )

        score.grade = self.determine_grade(score, stock, catalyst_count)

        return score
