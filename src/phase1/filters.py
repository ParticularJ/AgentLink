"""
波段交易系统 - 第一阶段：强制过滤层
"""
from typing import List, Tuple, Optional
from src.common.models import Stock, MarketStatus
from src.common.constants import (
    RISE_FILTER_THRESHOLDS,
    LIQUIDITY_FILTER_THRESHOLDS,
    FINANCIAL_FILTER_THRESHOLDS,
)


class Phase1Filter:
    """第一阶段强制过滤器"""

    def __init__(self, market_status: MarketStatus):
        self.market_status = market_status

    def filter_financial_mines(
        self,
        stock: Stock,
    ) -> Tuple[bool, Optional[str]]:
        """
        财务雷区过滤
        
        Returns:
            (是否通过, 剔除原因)
        """
        # 连续两季度经营现金流为负
        if stock.operating_cash_flow_ttm < 0 and stock.operating_cash_flow_last < 0:
            return False, "连续两季度经营现金流为负"

        # 应收账款/营收 > 50%
        if stock.receivables_revenue_ratio > FINANCIAL_FILTER_THRESHOLDS["max_receivables_revenue_ratio"]:
            return False, f"应收账款/营收={stock.receivables_revenue_ratio:.1%}>50%"

        # 商誉/总资产 > 30%
        if stock.goodwill_total_assets_ratio > FINANCIAL_FILTER_THRESHOLDS["max_goodwill_total_assets_ratio"]:
            return False, f"商誉/总资产={stock.goodwill_total_assets_ratio:.1%}>30%"

        # 连续两季度亏损
        if stock.net_profit_ttm < 0 and stock.net_profit_last < 0:
            return False, "连续两季度净利润为负"

        # 有息负债率 > 60% 且 现金流为负
        if (stock.interest_bearing_debt_ratio > FINANCIAL_FILTER_THRESHOLDS["max_interest_bearing_debt_ratio"]
                and stock.operating_cash_flow_ttm < 0):
            return False, f"有息负债率={stock.interest_bearing_debt_ratio:.1%}>60%且现金流为负"

        return True, None

    def filter_excessive_rise(
        self,
        stock: Stock,
    ) -> Tuple[bool, Optional[str]]:
        """
        过度涨幅过滤
        
        Returns:
            (是否通过, 剔除原因)
        """
        # 近60日涨幅阈值
        threshold_60d = RISE_FILTER_THRESHOLDS["60d"][self.market_status.value]
        if stock.rise_60d > threshold_60d:
            return False, f"近60日涨幅={stock.rise_60d:.1f}%>{threshold_60d}%"

        # 近20日涨幅阈值
        threshold_20d = RISE_FILTER_THRESHOLDS["20d"][self.market_status.value]
        if stock.rise_20d > threshold_20d:
            return False, f"近20日涨幅={stock.rise_20d:.1f}%>{threshold_20d}%"

        return True, None

    def filter_liquidity(
        self,
        stock: Stock,
    ) -> Tuple[bool, Optional[str]]:
        """
        流动性过滤
        
        Returns:
            (是否通过, 剔除原因)
        """
        # 股价 < 5元
        if stock.latest_price < LIQUIDITY_FILTER_THRESHOLDS["min_price"]:
            return False, f"股价={stock.latest_price:.2f}元<5元"

        # 流通市值 < 30亿
        if stock.float_market_cap < LIQUIDITY_FILTER_THRESHOLDS["min_float_market_cap"]:
            return False, f"流通市值={stock.float_market_cap:.1f}亿<30亿"

        # 日均成交额阈值
        if self.market_status == MarketStatus.BULL:
            min_volume = LIQUIDITY_FILTER_THRESHOLDS["min_daily_volume_bull"]
        else:
            min_volume = LIQUIDITY_FILTER_THRESHOLDS["min_daily_volume_bear"]

        if stock.avg_volume_20d < min_volume:
            return False, f"日均成交额={stock.avg_volume_20d:.0f}万<{min_volume}万"

        return True, None

    def filter(
        self,
        stock: Stock,
    ) -> Tuple[bool, Optional[str]]:
        """
        执行所有强制过滤
        
        Returns:
            (是否通过, 剔除原因)
        """
        # 财务雷区
        passed, reason = self.filter_financial_mines(stock)
        if not passed:
            return False, reason

        # 过度涨幅
        passed, reason = self.filter_excessive_rise(stock)
        if not passed:
            return False, reason

        # 流动性
        passed, reason = self.filter_liquidity(stock)
        if not passed:
            return False, reason

        return True, None

    def filter_batch(
        self,
        stocks: List[Stock],
    ) -> Tuple[List[Stock], List[Tuple[Stock, str]]]:
        """
        批量过滤
        
        Returns:
            (通过的股票列表, 剔除的股票及原因列表)
        """
        passed = []
        rejected = []

        for stock in stocks:
            is_passed, reason = self.filter(stock)
            if is_passed:
                passed.append(stock)
            else:
                rejected.append((stock, reason))

        return passed, rejected
