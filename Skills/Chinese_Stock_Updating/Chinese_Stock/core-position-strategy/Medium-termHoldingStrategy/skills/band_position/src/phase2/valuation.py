"""
波段交易系统 - 第二阶段：估值判断
"""
from typing import Optional, Tuple
from src.common.models import (
    Stock, ValuationResult, ValuationMethod, ValuationConclusion, IndustryType
)
from src.common.constants import (
    VALUATION_PEG_THRESHOLDS,
    VALUATION_PB_ROE_THRESHOLDS,
    VALUATION_PS_THRESHOLDS,
    HISTORICAL_PERCENTILE_THRESHOLDS,
    INDUSTRY_PB_ROE_COEFFICIENTS,
    PS_COEFFICIENTS,
)


class ValuationEvaluator:
    """估值评估器"""

    def __init__(self, industry_type: IndustryType):
        self.industry_type = industry_type

    def select_valuation_method(
        self,
        pe_ttm: Optional[float],
        profit_growth: float,
        net_profit: float,
    ) -> ValuationMethod:
        """
        选择估值方法
        
        Returns:
            ValuationMethod
        """
        # 净利润为负，使用PS法
        if net_profit <= 0:
            return ValuationMethod.PS

        # 增速为负或极低，切换至PB-ROE
        if profit_growth <= 10:
            return ValuationMethod.PB_ROE

        # 默认PEG法
        return ValuationMethod.PEG

    def evaluate_peg(
        self,
        pe_ttm: float,
        profit_growth: float,
    ) -> Tuple[ValuationConclusion, float]:
        """
        PEG估值法
        
        Returns:
            (估值结论, 仓位系数)
        """
        if profit_growth <= 0:
            return ValuationConclusion.HIGHLY_OVERVALUED, 0.0

        peg = pe_ttm / profit_growth

        if peg < VALUATION_PEG_THRESHOLDS["severely_undervalued"]:
            return ValuationConclusion.SEVERELY_UNDERVALUED, 1.0
        elif peg < VALUATION_PEG_THRESHOLDS["undervalued"]:
            return ValuationConclusion.UNDERVALUED, 0.9
        elif peg < VALUATION_PEG_THRESHOLDS["fairly_low"]:
            return ValuationConclusion.FAIRLY_LOW, 0.8
        elif peg < VALUATION_PEG_THRESHOLDS["fair"]:
            return ValuationConclusion.FAIR, 0.6
        elif peg < VALUATION_PEG_THRESHOLDS["overvalued"]:
            return ValuationConclusion.OVERVALUED, 0.2
        else:
            return ValuationConclusion.HIGHLY_OVERVALUED, 0.0

    def evaluate_pb_roe(
        self,
        pb_mrq: float,
        roe_ttm: float,
    ) -> Tuple[ValuationConclusion, float]:
        """
        PB-ROE估值法
        
        Returns:
            (估值结论, 仓位系数)
        """
        # 获取行业系数
        coefficient = INDUSTRY_PB_ROE_COEFFICIENTS.get(self.industry_type.value, 0.8)

        # 计算合理PB
        reasonable_pb = roe_ttm * 100 * coefficient

        if reasonable_pb <= 0:
            return ValuationConclusion.HIGHLY_OVERVALUED, 0.0

        # 计算溢价率
        premium = pb_mrq / reasonable_pb - 1

        if premium < VALUATION_PB_ROE_THRESHOLDS["severely_undervalued"]:
            return ValuationConclusion.SEVERELY_UNDERVALUED, 1.0
        elif premium < VALUATION_PB_ROE_THRESHOLDS["undervalued"]:
            return ValuationConclusion.UNDERVALUED, 0.9
        elif premium < VALUATION_PB_ROE_THRESHOLDS["fairly_low"]:
            return ValuationConclusion.FAIRLY_LOW, 0.8
        elif premium < VALUATION_PB_ROE_THRESHOLDS["fair"]:
            return ValuationConclusion.FAIR, 0.6
        elif premium < VALUATION_PB_ROE_THRESHOLDS["overvalued"]:
            return ValuationConclusion.OVERVALUED, 0.2
        else:
            return ValuationConclusion.HIGHLY_OVERVALUED, 0.0

    def evaluate_ps(
        self,
        ps_ttm: float,
        revenue_growth: float,
    ) -> Tuple[ValuationConclusion, float]:
        """
        PS估值法
        
        Returns:
            (估值结论, 仓位系数)
        """
        coefficient = PS_COEFFICIENTS.get(self.industry_type.value, 0.3)
        reasonable_ps = revenue_growth * coefficient

        if reasonable_ps <= 0:
            return ValuationConclusion.HIGHLY_OVERVALUED, 0.0

        ratio = ps_ttm / reasonable_ps

        if ratio < VALUATION_PS_THRESHOLDS["severely_undervalued"]:
            return ValuationConclusion.SEVERELY_UNDERVALUED, 1.0
        elif ratio < VALUATION_PS_THRESHOLDS["undervalued"]:
            return ValuationConclusion.UNDERVALUED, 0.8
        elif ratio < VALUATION_PS_THRESHOLDS["fairly_low"]:
            return ValuationConclusion.FAIRLY_LOW, 0.6
        elif ratio < VALUATION_PS_THRESHOLDS["fair"]:
            return ValuationConclusion.FAIR, 0.2
        else:
            return ValuationConclusion.HIGHLY_OVERVALUED, 0.0

    def evaluate_historical_percentile(
        self,
        current_valuation: float,
        historical_values: list,
    ) -> float:
        """
        计算历史估值分位点
        
        Args:
            current_valuation: 当前估值
            historical_values: 历史估值列表
            
        Returns:
            分位点 0-100
        """
        if not historical_values:
            return 50.0  # 无历史数据，默认中位

        count = sum(1 for v in historical_values if v < current_valuation)
        percentile = (count / len(historical_values)) * 100

        return min(max(percentile, 0.0), 100.0)

    def adjust_by_percentile(
        self,
        base_coefficient: float,
        percentile: float,
    ) -> float:
        """
        根据历史分位点调整仓位系数
        
        Returns:
            调整后的系数
        """
        if percentile < HISTORICAL_PERCENTILE_THRESHOLDS["extremely_low"]:
            return min(base_coefficient + 0.1, 1.0)
        elif percentile < HISTORICAL_PERCENTILE_THRESHOLDS["low"]:
            return base_coefficient
        elif percentile < HISTORICAL_PERCENTILE_THRESHOLDS["high"]:
            return base_coefficient
        elif percentile < HISTORICAL_PERCENTILE_THRESHOLDS["extremely_high"]:
            return max(base_coefficient - 0.1, 0.0)
        else:
            return max(base_coefficient - 0.2, 0.0)

    def evaluate_institution_holding(
        self,
        holding_change: float,  # 基金持仓环比变化%
    ) -> float:
        """
        评估机构持仓变化对估值容忍度的影响
        
        Returns:
            估值容忍度调整系数
        """
        if holding_change > 30:
            return 0.1  # 上调10%
        elif holding_change > 10:
            return 0.05  # 上调5%
        elif holding_change < -30:
            return -0.2  # 下调20%
        elif holding_change < -10:
            return -0.1  # 下调10%
        else:
            return 0.0

    def evaluate(
        self,
        pe_ttm: Optional[float] = None,
        pb_mrq: Optional[float] = None,
        ps_ttm: Optional[float] = None,
        profit_growth: float = 0.0,
        revenue_growth: float = 0.0,
        roe_ttm: float = 0.0,
        net_profit: float = 0.0,
        historical_pe_values: Optional[list] = None,
        historical_pb_values: Optional[list] = None,
        historical_ps_values: Optional[list] = None,
        institution_holding_change: Optional[float] = None,
    ) -> ValuationResult:
        """
        综合估值评估
        
        Returns:
            ValuationResult
        """
        # 选择估值方法
        method = self.select_valuation_method(pe_ttm, profit_growth, net_profit)

        # 执行估值
        if method == ValuationMethod.PEG and pe_ttm is not None:
            conclusion, coefficient = self.evaluate_peg(pe_ttm, profit_growth)
            peg = pe_ttm / profit_growth if profit_growth > 0 else None
            pb_roe_premium = None
            ps_ratio = None
            current_valuation = pe_ttm
            historical_values = historical_pe_values
        elif method == ValuationMethod.PB_ROE and pb_mrq is not None:
            conclusion, coefficient = self.evaluate_pb_roe(pb_mrq, roe_ttm)
            peg = None
            coefficient_pb = INDUSTRY_PB_ROE_COEFFICIENTS.get(self.industry_type, 0.8)
            reasonable_pb = roe_ttm * 100 * coefficient_pb
            pb_roe_premium = pb_mrq / reasonable_pb - 1 if reasonable_pb > 0 else None
            ps_ratio = None
            current_valuation = pb_mrq
            historical_values = historical_pb_values
        else:  # PS
            if ps_ttm is not None:
                conclusion, coefficient = self.evaluate_ps(ps_ttm, revenue_growth)
            else:
                conclusion, coefficient = ValuationConclusion.HIGHLY_OVERVALUED, 0.0
            peg = None
            pb_roe_premium = None
            coefficient_ps = PS_COEFFICIENTS.get(self.industry_type, 0.3)
            ps_ratio = ps_ttm / (revenue_growth * coefficient_ps) if revenue_growth > 0 else None
            current_valuation = ps_ttm
            historical_values = historical_ps_values

        # 计算历史分位点
        percentile = None
        if current_valuation is not None and historical_values:
            percentile = self.evaluate_historical_percentile(current_valuation, historical_values)
            coefficient = self.adjust_by_percentile(coefficient, percentile)

        # 机构持仓调整
        if institution_holding_change is not None:
            adjustment = self.evaluate_institution_holding(institution_holding_change)
            coefficient = min(max(coefficient + adjustment, 0.0), 1.0)

        return ValuationResult(
            method=method,
            peg=peg,
            pb_roe_premium=pb_roe_premium,
            ps_ratio=ps_ratio,
            conclusion=conclusion,
            position_coefficient=coefficient,
            historical_percentile=percentile,
            institution_holding_change=institution_holding_change,
        )

    def evaluate_stock(
        self,
        stock: Stock,
        valuation_data: dict,
    ) -> ValuationResult:
        """
        对股票进行估值评估
        
        Args:
            stock: 股票
            valuation_data: 估值数据字典
            
        Returns:
            ValuationResult
        """
        return self.evaluate(
            pe_ttm=valuation_data.get("pe_ttm"),
            pb_mrq=valuation_data.get("pb_mrq"),
            ps_ttm=valuation_data.get("ps_ttm"),
            profit_growth=valuation_data.get("profit_growth", 0.0),
            revenue_growth=valuation_data.get("revenue_growth", 0.0),
            roe_ttm=valuation_data.get("roe_ttm", 0.0),
            net_profit=valuation_data.get("net_profit", 0.0),
            historical_pe_values=valuation_data.get("historical_pe_values"),
            historical_pb_values=valuation_data.get("historical_pb_values"),
            historical_ps_values=valuation_data.get("historical_ps_values"),
            institution_holding_change=valuation_data.get("institution_holding_change"),
        )
