# skills/ma_bullish/scripts/risk_manager.py

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple

class RiskManager:
    """风险管理器"""
    
    def __init__(self):
        self.max_position_size = 0.3      # 单只股票最大仓位30%
        self.max_portfolio_risk = 0.05    # 组合最大风险5%
        self.stop_loss_atr_multiple = 2   # 止损倍数
        self.trailing_stop_pct = 0.08     # 移动止盈比例
        
    def calculate_position_size(self, stock_data: pd.DataFrame, 
                                account_balance: float) -> Dict:
        """计算建议仓位"""
        latest = stock_data.iloc[-1]
        
        # 计算波动率
        volatility = stock_data['pct_change'].std() * np.sqrt(252)
        
        # 基于波动率的仓位计算
        if volatility < 0.2:
            risk_per_trade = 0.02  # 每笔交易承担2%风险
        elif volatility < 0.3:
            risk_per_trade = 0.015
        else:
            risk_per_trade = 0.01
        
        # 计算止损距离
        stop_distance = self._calculate_stop_distance(stock_data)
        
        # 计算仓位
        position_value = (account_balance * risk_per_trade) / stop_distance
        shares = position_value / latest['close']
        
        # 限制最大仓位
        max_position_value = account_balance * self.max_position_size
        if position_value > max_position_value:
            position_value = max_position_value
            shares = position_value / latest['close']
        
        return {
            'suggested_shares': int(shares),
            'suggested_amount': round(position_value, 2),
            'risk_per_trade': risk_per_trade,
            'stop_distance': round(stop_distance, 4),
            'volatility': round(volatility, 4)
        }
    
    def _calculate_stop_distance(self, df: pd.DataFrame) -> float:
        """计算止损距离（百分比）"""
        latest = df.iloc[-1]
        
        if 'atr' in latest:
            atr_pct = latest['atr'] / latest['close']
            return atr_pct * self.stop_loss_atr_multiple
        else:
            return 0.05  # 默认5%止损
    
    def set_stop_loss(self, entry_price: float, df: pd.DataFrame) -> Dict:
        """设置止损位"""
        latest = df.iloc[-1]
        
        # 技术止损
        if 'ma20' in latest:
            tech_stop = latest['ma20'] * 0.98
        else:
            tech_stop = entry_price * 0.93
        
        # ATR止损
        if 'atr' in latest:
            atr_stop = entry_price - latest['atr'] * 2
        else:
            atr_stop = entry_price * 0.92
        
        # 百分比止损
        pct_stop = entry_price * 0.92
        
        # 取最严格的止损
        stop_loss = max(tech_stop, atr_stop, pct_stop)
        
        return {
            'stop_loss': round(stop_loss, 2),
            'stop_loss_pct': round((entry_price - stop_loss) / entry_price * 100, 2),
            'tech_stop': round(tech_stop, 2),
            'atr_stop': round(atr_stop, 2),
            'pct_stop': round(pct_stop, 2)
        }
    
    def set_take_profit(self, entry_price: float, df: pd.DataFrame) -> Dict:
        """设置止盈位"""
        # 计算阻力位
        highs = df['high'].tail(20)
        resistance = highs.max()
        
        # 基于ATR的止盈
        if 'atr' in df.iloc[-1]:
            atr = df.iloc[-1]['atr']
            target1 = entry_price + atr * 2
            target2 = entry_price + atr * 3
            target3 = entry_price + atr * 4
        else:
            target1 = entry_price * 1.10
            target2 = entry_price * 1.15
            target3 = entry_price * 1.20
        
        # 如果阻力位低于目标，优先使用阻力位
        if resistance > entry_price and resistance < target1:
            target1 = resistance
        
        return {
            'target1': round(target1, 2),  # 第一目标：10-15%
            'target2': round(target2, 2),  # 第二目标：15-20%
            'target3': round(target3, 2),  # 第三目标：20-25%
            'resistance': round(resistance, 2)
        }
    
    def update_trailing_stop(self, position: Dict, current_price: float) -> float:
        """更新移动止损"""
        if 'highest_price' not in position:
            position['highest_price'] = current_price
        else:
            position['highest_price'] = max(position['highest_price'], current_price)
        
        # 移动止损 = 最高价 * (1 - 移动止损比例)
        trailing_stop = position['highest_price'] * (1 - self.trailing_stop_pct)
        
        return max(trailing_stop, position['stop_loss'])
    
    def check_risk_limits(self, portfolio: Dict) -> Dict:
        """检查组合风险限制"""
        warnings = []
        
        # 检查单只股票仓位
        for stock in portfolio['positions']:
            if stock['position_pct'] > self.max_position_size:
                warnings.append(f"{stock['name']}仓位{stock['position_pct']:.1%}超过限制")
        
        # 检查总风险
        total_risk = portfolio.get('total_risk', 0)
        if total_risk > self.max_portfolio_risk:
            warnings.append(f"组合风险{total_risk:.1%}超过{self.max_portfolio_risk:.1%}")
        
        return {
            'is_safe': len(warnings) == 0,
            'warnings': warnings,
            'max_position_size': self.max_position_size,
            'max_portfolio_risk': self.max_portfolio_risk
        }