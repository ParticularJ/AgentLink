"""
波段交易系统 - 第二阶段：一票否决清单验证
"""
from typing import Tuple, Optional
from datetime import datetime, timedelta
from src.common.models import Stock, VetoResult, MarketStatus
from src.common.constants import VETO_THRESHOLDS


class VetoChecker:
    """一票否决检查器"""

    def __init__(self, market_status: MarketStatus):
        self.market_status = market_status

    def check_management_violation(
        self,
        has_violation: bool,
    ) -> Tuple[bool, Optional[str]]:
        """
        检查管理层违规记录
        
        Args:
            has_violation: 近2年是否有违规记录
            
        Returns:
            (是否通过, 否决原因)
        """
        if has_violation:
            return False, "管理层近2年存在违规记录"
        return True, None

    def check_audit_opinion(
        self,
        is_standard: bool,
    ) -> Tuple[bool, Optional[str]]:
        """
        检查审计意见
        
        Args:
            is_standard: 是否为标准无保留意见
            
        Returns:
            (是否通过, 否决原因)
        """
        if not is_standard:
            return False, "审计意见非标准无保留"
        return True, None

    def check_northbound_outflow(
        self,
        outflow_days: int,
        outflow_amount: float,  # 万元
    ) -> Tuple[bool, Optional[str]]:
        """
        检查北向资金持续流出
        
        Args:
            outflow_days: 连续净卖出天数
            outflow_amount: 累计净卖出金额（万元）
            
        Returns:
            (是否通过, 否决原因)
        """
        threshold_days = VETO_THRESHOLDS["northbound_outflow_days"]
        threshold_amount = VETO_THRESHOLDS["northbound_outflow_amount"]

        if outflow_days >= threshold_days and outflow_amount > threshold_amount:
            return False, f"北向资金连续{outflow_days}日净卖出{outflow_amount:.0f}万"
        return True, None

    def check_major_shareholder_pledge(
        self,
        pledge_ratio: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        检查大股东质押比例
        
        Args:
            pledge_ratio: 大股东质押比例%
            
        Returns:
            (是否通过, 否决原因)
        """
        threshold = VETO_THRESHOLDS["major_shareholder_pledge_ratio"]
        if pledge_ratio > threshold * 100:
            return False, f"大股东质押比例={pledge_ratio:.1f}%>{threshold*100:.0f}%"
        return True, None

    def check_recent_unlock(
        self,
        unlock_market_cap_ratio: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        检查近期大额解禁
        
        Args:
            unlock_market_cap_ratio: 未来30日解禁市值/流通市值
            
        Returns:
            (是否通过, 否决原因)
        """
        threshold = VETO_THRESHOLDS["unlock_market_cap_ratio"]
        if unlock_market_cap_ratio > threshold * 100:
            return False, f"未来30日解禁占比={unlock_market_cap_ratio:.1f}%>{threshold*100:.0f}%"
        return True, None

    def check_pre_report_rise(
        self,
        rise_20d_before_report: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        检查财报前涨幅
        
        Args:
            rise_20d_before_report: 财报前20日涨幅%
            
        Returns:
            (是否通过, 否决原因)
        """
        if self.market_status == MarketStatus.BULL:
            threshold = VETO_THRESHOLDS["pre_report_rise_bull"]
        elif self.market_status == MarketStatus.OSCILLATION:
            threshold = VETO_THRESHOLDS["pre_report_rise_oscillation"]
        else:
            threshold = VETO_THRESHOLDS["pre_report_rise_bear"]

        if rise_20d_before_report > threshold:
            return False, f"财报前20日涨幅={rise_20d_before_report:.1f}%>{threshold}%"
        return True, None

    def check(
        self,
        has_violation: bool = False,
        is_standard_audit: bool = True,
        northbound_outflow_days: int = 0,
        northbound_outflow_amount: float = 0.0,
        major_shareholder_pledge_ratio: float = 0.0,
        unlock_market_cap_ratio: float = 0.0,
        pre_report_rise_20d: float = 0.0,
    ) -> VetoResult:
        """
        执行一票否决检查
        
        Returns:
            VetoResult
        """
        checks = [
            ("管理层违规", self.check_management_violation(has_violation)),
            ("审计意见", self.check_audit_opinion(is_standard_audit)),
            ("北向资金流出", self.check_northbound_outflow(northbound_outflow_days, northbound_outflow_amount)),
            ("大股东质押", self.check_major_shareholder_pledge(major_shareholder_pledge_ratio)),
            ("近期解禁", self.check_recent_unlock(unlock_market_cap_ratio)),
            ("财报前涨幅", self.check_pre_report_rise(pre_report_rise_20d)),
        ]

        for name, (passed, reason) in checks:
            if not passed:
                return VetoResult(passed=False, triggered_item=f"{name}: {reason}")

        return VetoResult(passed=True)

    def check_stock(
        self,
        stock: Stock,
        veto_data: dict,
    ) -> VetoResult:
        """
        对股票执行一票否决检查
        
        Args:
            stock: 股票
            veto_data: 否决相关数据字典
            
        Returns:
            VetoResult
        """
        return self.check(
            has_violation=veto_data.get("has_violation", False),
            is_standard_audit=veto_data.get("is_standard_audit", True),
            northbound_outflow_days=veto_data.get("northbound_outflow_days", 0),
            northbound_outflow_amount=veto_data.get("northbound_outflow_amount", 0.0),
            major_shareholder_pledge_ratio=veto_data.get("major_shareholder_pledge_ratio", 0.0),
            unlock_market_cap_ratio=veto_data.get("unlock_market_cap_ratio", 0.0),
            pre_report_rise_20d=veto_data.get("pre_report_rise_20d", 0.0),
        )
