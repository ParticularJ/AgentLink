"""
波段交易系统 - 第二阶段：护城河定量评估
"""
from typing import Tuple
from src.common.models import Stock, MoatScore, MoatLevel, IndustryType
from src.common.constants import MOAT_THRESHOLDS


class MoatEvaluator:
    """护城河评估器"""

    def __init__(self, industry_type: IndustryType):
        self.industry_type = industry_type

    def evaluate_pricing_power(
        self,
        gross_margin: float,
        industry_avg_margin: float,
    ) -> float:
        """
        评估定价权/差异化壁垒
        
        Args:
            gross_margin: 毛利率%
            industry_avg_margin: 行业平均毛利率%
            
        Returns:
            0-6分
        """
        margin_diff = gross_margin - industry_avg_margin

        if margin_diff > 5:
            return 6.0
        elif margin_diff > 3:
            return 4.0
        elif margin_diff > 0:
            return 2.0
        else:
            return 0.0

    def evaluate_rd_ratio(
        self,
        rd_ratio: float,
    ) -> float:
        """
        评估研发费用率
        
        Args:
            rd_ratio: 研发费用率%
            
        Returns:
            0-4分
        """
        # 根据行业类型调整标准
        if self.industry_type == IndustryType.TECH_GROWTH:
            thresholds = [8, 5, 3]
        elif self.industry_type == IndustryType.CONSUMER_VALUE:
            # 消费类用销售费用率代替
            thresholds = [15, 10, 5]
        elif self.industry_type == IndustryType.MANUFACTURING:
            thresholds = [5, 3, 2]
        else:
            # 周期资源型不适用
            return 2.0

        if rd_ratio > thresholds[0]:
            return 4.0
        elif rd_ratio > thresholds[1]:
            return 3.0
        elif rd_ratio > thresholds[2]:
            return 2.0
        else:
            return 0.0

    def evaluate_customer_concentration(
        self,
        top5_customer_ratio: float,
    ) -> float:
        """
        评估客户集中度
        
        Args:
            top5_customer_ratio: 前5大客户占比%
            
        Returns:
            0-4分
        """
        if top5_customer_ratio < 40:
            return 4.0
        elif top5_customer_ratio < 60:
            return 3.0
        elif top5_customer_ratio < 80:
            return 1.0
        else:
            return 0.0

    def evaluate_customer_loyalty(
        self,
        renewal_rate: float = 0.0,
        avg_cooperation_years: float = 0.0,
    ) -> float:
        """
        评估客户粘性
        
        Args:
            renewal_rate: 客户续约率%
            avg_cooperation_years: 平均合作年限
            
        Returns:
            0-3分
        """
        if renewal_rate > 80 or avg_cooperation_years > 3:
            return 3.0
        else:
            return 0.0

    def evaluate_profit_quality(
        self,
        net_profit_cash_ratio: float,
    ) -> float:
        """
        评估利润含金量
        
        Args:
            net_profit_cash_ratio: 净利润现金含量%
            
        Returns:
            0-3分
        """
        if net_profit_cash_ratio > 100:
            return 3.0
        elif net_profit_cash_ratio > 80:
            return 2.0
        elif net_profit_cash_ratio > 60:
            return 1.0
        else:
            return 0.0

    def evaluate(
        self,
        gross_margin: float,
        industry_avg_margin: float,
        rd_ratio: float,
        top5_customer_ratio: float,
        net_profit_cash_ratio: float,
        renewal_rate: float = 0.0,
        avg_cooperation_years: float = 0.0,
    ) -> MoatScore:
        """
        综合评估护城河
        
        Returns:
            MoatScore
        """
        pricing_power = self.evaluate_pricing_power(gross_margin, industry_avg_margin)
        rd = self.evaluate_rd_ratio(rd_ratio)
        customer_conc = self.evaluate_customer_concentration(top5_customer_ratio)
        customer_loyal = self.evaluate_customer_loyalty(renewal_rate, avg_cooperation_years)
        profit_quality = self.evaluate_profit_quality(net_profit_cash_ratio)

        total = pricing_power + rd + customer_conc + customer_loyal + profit_quality

        # 判定等级
        if total >= MOAT_THRESHOLDS["strong"]:
            level = MoatLevel.STRONG
        elif total >= MOAT_THRESHOLDS["medium"]:
            level = MoatLevel.MEDIUM
        else:
            level = MoatLevel.WEAK

        return MoatScore(
            pricing_power_score=pricing_power,
            rd_ratio_score=rd,
            customer_concentration_score=customer_conc,
            customer_loyalty_score=customer_loyal,
            profit_quality_score=profit_quality,
            total_score=total,
            level=level,
        )

    def get_position_adjustment(
        self,
        moat_score: MoatScore,
        financial_score: float = 0.0,
    ) -> Tuple[float, str]:
        """
        获取仓位调整系数
        
        Returns:
            (调整系数, 处理结论)
        """
        if moat_score.level == MoatLevel.STRONG:
            return 1.0, "通过"
        elif moat_score.level == MoatLevel.MEDIUM:
            return 0.6, "降级"
        else:
            # 护城河弱，但业绩优秀且估值严重低估可保留
            if financial_score >= 45:
                return 0.4, "保留（业绩优秀补偿）"
            else:
                return 0.0, "剔除"
