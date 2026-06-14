"""
核心仓交易系统 - 宏观流动性过滤器
严格遵循《核心仓策略 V3.0》第一阶段设计文档
"""
from typing import Optional, Tuple
from models import MacroLiquidity, MacroEnvironment


class MacroFilter:
    """宏观流动性过滤器"""
    
    def __init__(self):
        pass
    
    def evaluate(self, macro_data: dict) -> MacroLiquidity:
        """
        评估宏观流动性环境
        
        Args:
            macro_data: {
                'social_financing_growth': float,      # 社融增速%
                'social_financing_mom_change': float,  # 社融环比变化%
                'treasury_yield_10y': float,           # 10年期国债收益率%
                'risk_premium': float,                 # 风险溢价%
            }
            
        Returns:
            MacroLiquidity对象
        """
        return MacroLiquidity(
            social_financing_growth=macro_data.get('social_financing_growth', 0),
            social_financing_mom_change=macro_data.get('social_financing_mom_change', 0),
            treasury_yield_10y=macro_data.get('treasury_yield_10y', 0),
            risk_premium=macro_data.get('risk_premium', 0)
        )
    
    def can_proceed(self, macro: MacroLiquidity) -> Tuple[bool, str, float]:
        """
        判断是否可继续建仓
        
        Returns:
            (是否可继续, 原因, 胜率调整)
        """
        env = macro.environment
        adjustment = macro.win_rate_adjustment
        
        if env == MacroEnvironment.EXPANSION:
            return True, f"扩张期：正常建仓，胜率调整{adjustment:+.1%}", adjustment
        elif env == MacroEnvironment.STABLE:
            return True, f"稳定期：正常建仓，胜率调整{adjustment:+.1%}", adjustment
        else:
            return False, f"收缩期：减仓/观望，胜率调整{adjustment:+.1%}", adjustment
    
    def get_strategy_action(self, macro: MacroLiquidity) -> str:
        """获取策略操作建议"""
        env = macro.environment
        if env == MacroEnvironment.EXPANSION:
            return "正常建仓"
        elif env == MacroEnvironment.STABLE:
            return "正常建仓"
        else:
            return "减仓/观望"
