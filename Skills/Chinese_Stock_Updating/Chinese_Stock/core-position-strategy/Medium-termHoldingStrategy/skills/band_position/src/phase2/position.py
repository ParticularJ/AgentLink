"""
波段交易系统 - 第二阶段：仓位计算与止损设定
"""
import math
from typing import Tuple
from src.common.models import (
    Phase2Result, Grade, FinalDecision,
    ValuationConclusion, MoatLevel
)
from src.common.constants import (
    MAX_POSITION,
    MAX_INDUSTRY_POSITION,
    STOP_LOSS_THRESHOLDS,
    TIME_STOP_THRESHOLDS,
)


class PositionCalculator:
    """仓位计算器"""

    def __init__(self):
        pass

    def calculate_base_position(
        self,
        financial_score: float,
        valuation_conclusion: ValuationConclusion,
        surprise_score: float,
    ) -> float:
        """
        计算建议基准仓位
        
        Returns:
            基准仓位%
        """
        # 黄金机会：财报优秀 + 严重低估 + 大幅超预期
        if financial_score >= 45 and valuation_conclusion == ValuationConclusion.SEVERELY_UNDERVALUED and surprise_score >= 8:
            return 8.0

        # 优质合理：财报优秀 + 合理估值
        elif financial_score >= 45 and valuation_conclusion in [ValuationConclusion.FAIRLY_LOW, ValuationConclusion.FAIR]:
            return 5.0

        # 高性价比：财报中等 + 严重低估 + 超预期
        elif financial_score >= 35 and valuation_conclusion == ValuationConclusion.SEVERELY_UNDERVALUED and surprise_score >= 6:
            return 5.0

        # 可考虑：财报中等 + 合理估值
        elif financial_score >= 35 and valuation_conclusion in [ValuationConclusion.FAIRLY_LOW, ValuationConclusion.FAIR]:
            return 3.0

        # 基本面优秀但估值偏贵
        elif financial_score >= 45 and valuation_conclusion in [ValuationConclusion.OVERVALUED, ValuationConclusion.HIGHLY_OVERVALUED]:
            return 0.0

        # 其他情况
        else:
            return 2.0

    def calculate_final_position(
        self,
        base_position: float,
        valuation_coefficient: float,
        moat_coefficient: float,
        grade: Grade,
        industry_position: float = 0.0,
    ) -> float:
        """
        计算最终仓位
        
        公式：最终仓位 = 建议基准仓位 x 估值仓位系数 x 护城河调整系数
        
        Args:
            base_position: 建议基准仓位%
            valuation_coefficient: 估值仓位系数
            moat_coefficient: 护城河调整系数
            grade: 档位
            industry_position: 当前行业已配置仓位%
            
        Returns:
            最终仓位%
        """
        # 计算
        final = base_position * valuation_coefficient * moat_coefficient

        # 档位上限约束
        max_pos = MAX_POSITION[grade.value]
        final = min(final, max_pos)

        # 行业上限约束
        remaining = MAX_INDUSTRY_POSITION - industry_position
        final = min(final, remaining)

        # 向下取整至1%整数倍
        final = math.floor(final)

        return max(final, 0.0)

    def determine_final_decision(
        self,
        financial_score: float,
        pass_score: float,
        veto_passed: bool,
        final_position: float,
        valuation_conclusion: ValuationConclusion,
    ) -> FinalDecision:
        """
        确定最终决策
        
        Returns:
            FinalDecision
        """
        # 一票否决未通过
        if not veto_passed:
            return FinalDecision.REJECT

        # 财报评分未达标
        if financial_score < pass_score:
            return FinalDecision.REJECT

        # 估值过高
        if valuation_conclusion in [ValuationConclusion.OVERVALUED, ValuationConclusion.HIGHLY_OVERVALUED]:
            return FinalDecision.WATCH

        # 仓位为0
        if final_position <= 0:
            return FinalDecision.WATCH

        return FinalDecision.BUY_CANDIDATE

    def calculate_stop_loss(
        self,
        beta: float,
    ) -> Tuple[float, int]:
        """
        计算止损位
        
        Returns:
            (价格止损%, 时间止损周数)
        """
        if beta < 1.0:
            stop_loss = STOP_LOSS_THRESHOLDS["beta_lt_1"]
            time_stop = TIME_STOP_THRESHOLDS["beta_lt_1"]
        elif beta < 1.3:
            stop_loss = STOP_LOSS_THRESHOLDS["beta_1_to_1_3"]
            time_stop = TIME_STOP_THRESHOLDS["beta_1_to_1_3"]
        elif beta < 1.5:
            stop_loss = STOP_LOSS_THRESHOLDS["beta_1_3_to_1_5"]
            time_stop = TIME_STOP_THRESHOLDS["beta_1_3_to_1_5"]
        else:
            stop_loss = STOP_LOSS_THRESHOLDS["beta_gt_1_5"]
            time_stop = TIME_STOP_THRESHOLDS["beta_gt_1_5"]

        return stop_loss, time_stop

    def calculate(
        self,
        financial_score: float,
        pass_score: float,
        valuation_conclusion: ValuationConclusion,
        valuation_coefficient: float,
        moat_level: MoatLevel,
        moat_coefficient: float,
        grade: Grade,
        beta: float,
        veto_passed: bool,
        industry_position: float = 0.0,
        surprise_score: float = 0.0,
    ) -> Tuple[float, float, FinalDecision, float, int]:
        """
        综合计算仓位和止损
        
        Returns:
            (建议基准仓位, 最终仓位, 最终决策, 止损位, 时间止损)
        """
        # 计算基准仓位
        base_position = self.calculate_base_position(
            financial_score, valuation_conclusion, surprise_score
        )

        # 计算最终仓位
        final_position = self.calculate_final_position(
            base_position, valuation_coefficient, moat_coefficient,
            grade, industry_position
        )

        # 确定决策
        decision = self.determine_final_decision(
            financial_score, pass_score, veto_passed,
            final_position, valuation_conclusion
        )

        # 计算止损
        stop_loss, time_stop = self.calculate_stop_loss(beta)

        return base_position, final_position, decision, stop_loss, time_stop
