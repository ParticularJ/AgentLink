"""
波段交易系统 - 第二阶段：财报核心指标评分
"""
from typing import Optional
from src.common.models import Stock, FinancialReportScore, IndustryType


class FinancialScorer:
    """财报评分器"""

    def __init__(self, industry_type: IndustryType):
        self.industry_type = industry_type

    def _get_industry_thresholds(self) -> dict:
        """获取行业适配阈值"""
        thresholds = {
            IndustryType.TECH_GROWTH: {
                "revenue_growth": 25,
                "profit_growth": 35,
                "roe": 15,
            },
            IndustryType.CONSUMER_VALUE: {
                "revenue_growth": 20,
                "profit_growth": 25,
                "roe": 25,
            },
            IndustryType.CYCLICAL_RESOURCE: {
                "revenue_growth": 50,
                "profit_growth": 60,
                "roe": 12,
            },
            IndustryType.MANUFACTURING: {
                "revenue_growth": 20,
                "profit_growth": 25,
                "roe": 15,
            },
        }
        return thresholds.get(self.industry_type, thresholds[IndustryType.TECH_GROWTH])

    def score_revenue_growth(
        self,
        revenue_growth: float,  # 单季营收同比增速%
    ) -> float:
        """
        评分营收增速（0-8分）
        """
        thresholds = self._get_industry_thresholds()
        excellent = thresholds["revenue_growth"] * 1.2  # 优秀线
        pass_line = thresholds["revenue_growth"] * 0.6   # 及格线

        if revenue_growth > excellent:
            return 8.0
        elif revenue_growth > thresholds["revenue_growth"]:
            return 6.0
        elif revenue_growth > pass_line:
            return 4.0
        else:
            return 2.0

    def score_profit_growth(
        self,
        profit_growth: float,  # 单季净利润同比增速%
    ) -> float:
        """
        评分利润增速（0-8分）
        """
        thresholds = self._get_industry_thresholds()
        excellent = thresholds["profit_growth"] * 1.14  # 优秀线
        pass_line = thresholds["profit_growth"] * 0.57   # 及格线

        if profit_growth > excellent:
            return 8.0
        elif profit_growth > thresholds["profit_growth"]:
            return 6.0
        elif profit_growth > pass_line:
            return 4.0
        else:
            return 2.0

    def score_earnings_trend(
        self,
        current_profit_growth: float,  # 本季净利润增速%
        last_profit_growth: float,     # 上季净利润增速%
    ) -> float:
        """
        评分业绩趋势（0-8分）
        """
        deceleration = last_profit_growth - current_profit_growth

        if current_profit_growth > 20 and current_profit_growth > last_profit_growth:
            # 加速增长
            return 8.0
        elif current_profit_growth > 20 and deceleration < 10:
            # 高增长但小幅减速
            return 4.0
        elif current_profit_growth > 20 and deceleration >= 10:
            # 高增长但大幅减速
            return 1.0
        elif current_profit_growth > 0:
            # 正增长但幅度有限
            return 2.0
        else:
            # 负增长
            return 0.0

    def score_cash_quality(
        self,
        net_profit_cash_ratio: float,  # 净利润现金含量%
    ) -> float:
        """
        评分盈利质量（0-8分）
        """
        if net_profit_cash_ratio > 100:
            return 8.0
        elif net_profit_cash_ratio > 80:
            return 5.0
        else:
            return 2.0

    def score_roe(
        self,
        roe: float,  # 单季年化ROE%
    ) -> float:
        """
        评分ROE（0-8分）
        """
        thresholds = self._get_industry_thresholds()
        excellent = thresholds["roe"] * 1.33  # 优秀线
        pass_line = thresholds["roe"] * 0.75   # 及格线

        if roe > excellent:
            return 8.0
        elif roe > thresholds["roe"]:
            return 5.0
        elif roe > pass_line:
            return 3.0
        else:
            return 2.0

    def score_surprise(
        self,
        actual_profit: float,      # 实际净利润
        expected_profit: float,    # 一致预期净利润
    ) -> float:
        """
        评分季报超预期（0-10分）
        
        Args:
            actual_profit: 实际净利润
            expected_profit: 一致预期净利润
            
        Returns:
            0-10分
        """
        if expected_profit == 0:
            return 3.0  # 无预期数据，给中性分

        surprise = (actual_profit - expected_profit) / abs(expected_profit) * 100

        if surprise >= 30:
            return 10.0
        elif surprise >= 15:
            return 8.0
        elif surprise >= 5:
            return 6.0
        elif surprise >= -5:
            return 3.0
        else:
            return 0.0

    def score_institution_attitude(
        self,
        rating_upgraded: bool = False,
        target_price_upgraded: bool = False,
        rating_downgraded: bool = False,
        no_coverage: bool = False,
    ) -> float:
        """
        评分机构态度（0-10分）
        
        Returns:
            0-10分
        """
        if no_coverage:
            return 3.0  # 无机构覆盖

        if rating_upgraded or target_price_upgraded:
            return 10.0
        elif rating_downgraded:
            return 0.0
        else:
            return 5.0  # 维持评级

    def evaluate(
        self,
        revenue_growth: float,
        profit_growth: float,
        last_profit_growth: float,
        net_profit_cash_ratio: float,
        roe: float,
        actual_profit: float,
        expected_profit: float,
        rating_upgraded: bool = False,
        target_price_upgraded: bool = False,
        rating_downgraded: bool = False,
        no_coverage: bool = False,
    ) -> FinancialReportScore:
        """
        综合财报评分
        
        Returns:
            FinancialReportScore
        """
        revenue_score = self.score_revenue_growth(revenue_growth)
        profit_score = self.score_profit_growth(profit_growth)
        trend_score = self.score_earnings_trend(profit_growth, last_profit_growth)
        cash_score = self.score_cash_quality(net_profit_cash_ratio)
        roe_score = self.score_roe(roe)
        surprise = self.score_surprise(actual_profit, expected_profit)
        institution = self.score_institution_attitude(
            rating_upgraded, target_price_upgraded, rating_downgraded, no_coverage
        )

        total = (revenue_score + profit_score + trend_score +
                 cash_score + roe_score + surprise + institution)

        return FinancialReportScore(
            revenue_growth_score=revenue_score,
            profit_growth_score=profit_score,
            earnings_trend_score=trend_score,
            cash_quality_score=cash_score,
            roe_score=roe_score,
            surprise_score=surprise,
            institution_attitude_score=institution,
            total_score=total,
        )

    def evaluate_stock(
        self,
        stock: Stock,
        financial_data: dict,
    ) -> FinancialReportScore:
        """
        对股票进行财报评分
        
        Args:
            stock: 股票
            financial_data: 财务数据字典
            
        Returns:
            FinancialReportScore
        """
        return self.evaluate(
            revenue_growth=financial_data.get("revenue_growth", 0.0),
            profit_growth=financial_data.get("profit_growth", 0.0),
            last_profit_growth=financial_data.get("last_profit_growth", 0.0),
            net_profit_cash_ratio=financial_data.get("net_profit_cash_ratio", 0.0),
            roe=financial_data.get("roe", 0.0),
            actual_profit=financial_data.get("actual_profit", 0.0),
            expected_profit=financial_data.get("expected_profit", 0.0),
            rating_upgraded=financial_data.get("rating_upgraded", False),
            target_price_upgraded=financial_data.get("target_price_upgraded", False),
            rating_downgraded=financial_data.get("rating_downgraded", False),
            no_coverage=financial_data.get("no_coverage", False),
        )
