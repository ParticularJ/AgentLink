"""
核心仓交易系统 - 组合管理器
管理核心仓的开仓、加仓、卖出、资金分配
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from models import (
    CorePortfolio, CorePosition, PositionStatus,
    StockSecondaryScore, BuyPointSignal, MonitorSignal
)


class CorePortfolioManager:
    """核心仓组合管理器"""
    
    def __init__(self, total_capital: float = 1000000.0, core_ratio: float = 0.50):
        self.portfolio = CorePortfolio(
            total_capital=total_capital,
            core_ratio=core_ratio
        )
    
    def can_open_position(self, position_pct: float) -> Tuple[bool, str]:
        """
        检查是否可以开仓
        
        Returns:
            (是否可以, 原因)
        """
        # 检查持仓数量
        active_positions = [p for p in self.portfolio.positions 
                           if p.status in [PositionStatus.HOLDING, PositionStatus.PARTIAL_SELL]]
        if len(active_positions) >= self.portfolio.max_positions:
            return False, f"已达最大持仓数{self.portfolio.max_positions}只"
        
        # 检查单只仓位上限
        if position_pct > self.portfolio.max_single_position_pct:
            return False, f"单只仓位{position_pct:.1%}超过上限{self.portfolio.max_single_position_pct:.1%}"
        
        # 检查资金
        required_capital = self.portfolio.core_capital * position_pct
        if required_capital > self.portfolio.cash:
            return False, f"可用资金不足，需要{required_capital:.0f}，仅有{self.portfolio.cash:.0f}"
        
        return True, "可以开仓"
    
    def open_position(self, 
                     candidate: StockSecondaryScore,
                     buy_point: BuyPointSignal,
                     entry_price: float,
                     atr: float = 0) -> Optional[CorePosition]:
        """
        开仓
        
        Args:
            candidate: 二次筛选评分
            buy_point: 买点信号
            entry_price: 买入价格
            atr: 14日ATR值（用于自适应止损）
            
        Returns:
            CorePosition or None
        """
        position_pct = buy_point.suggested_position_pct
        
        can_open, reason = self.can_open_position(position_pct)
        if not can_open:
            print(f"❌ 无法开仓: {reason}")
            return None
        
        # 计算买入金额和股数
        position_value = self.portfolio.core_capital * position_pct
        
        # 整手买入（A股100股/手）
        shares = int(position_value / entry_price / 100) * 100
        actual_value = shares * entry_price
        
        # 创建持仓
        position = CorePosition(
            stock_code=candidate.stock_code,
            stock_name=candidate.stock_name,
            sector=candidate.sector,
            entry_price=entry_price,
            entry_date=datetime.now(),
            initial_shares=shares,
            initial_position_pct=position_pct,
            current_price=entry_price,
            highest_price=entry_price,
            fixed_stop_loss_price=entry_price * 0.90,  # -10%
            entry_atr=atr,
            remaining_shares=shares,
            remaining_position_pct=position_pct
        )
        
        # 设置止盈层级
        position.take_profit_levels = [
            {"pct": 15, "sell_ratio": 0.333},
            {"pct": 25, "sell_ratio": 0.333},
            {"pct": 40, "sell_ratio": 0.0, "move_stop": 20},
            {"pct": 60, "sell_ratio": 0.0, "move_stop": 40}
        ]
        
        # 更新组合
        self.portfolio.positions.append(position)
        self.portfolio.cash -= actual_value
        
        print(f"✅ 开仓成功: {candidate.stock_name}({candidate.stock_code})")
        print(f"   买入价: {entry_price:.2f}, 股数: {shares}, 金额: {actual_value:.0f}")
        print(f"   仓位: {position_pct:.1%}, 买点质量: {buy_point.quality.value}")
        print(f"   固定止损: {position.fixed_stop_loss_price:.2f}")
        if atr > 0:
            print(f"   ATR止损: {entry_price - 2*atr:.2f}")
        
        return position
    
    def add_position(self, stock_code: str, add_price: float,
                    add_ratio: float = 0.25) -> Optional[Dict]:
        """
        加仓
        
        Args:
            stock_code: 股票代码
            add_price: 加仓价格
            add_ratio: 加仓比例（相对首仓）
            
        Returns:
            加仓记录 or None
        """
        position = self._find_active_position(stock_code)
        if not position:
            print(f"❌ 未找到持仓: {stock_code}")
            return None
        
        # 检查加仓次数
        if len(position.add_positions) >= 2:
            print(f"❌ 已达最大加仓次数2次")
            return None
        
        # 计算加仓股数
        add_shares = int(position.initial_shares * add_ratio / 100) * 100
        add_value = add_shares * add_price
        
        if add_value > self.portfolio.cash:
            print(f"❌ 可用资金不足")
            return None
        
        # 检查累计仓位上限
        current_total_pct = position.remaining_position_pct
        new_add_pct = add_value / self.portfolio.core_capital
        if current_total_pct + new_add_pct > 0.65:  # 累计不超过65%
            print(f"❌ 累计仓位将超过65%上限")
            return None
        
        # 执行加仓
        add_record = {
            "price": add_price,
            "shares": add_shares,
            "date": datetime.now(),
            "ratio": add_ratio
        }
        position.add_positions.append(add_record)
        
        # 更新持仓
        position.remaining_shares += add_shares
        position.remaining_position_pct += new_add_pct
        self.portfolio.cash -= add_value
        
        print(f"✅ 加仓成功: {position.stock_name}")
        print(f"   加仓价: {add_price:.2f}, 股数: {add_shares}")
        print(f"   累计仓位: {position.remaining_position_pct:.1%}")
        
        return add_record
    
    def sell_position(self, stock_code: str, sell_price: float,
                     sell_ratio: float = 1.0, reason: str = "") -> Optional[Dict]:
        """
        卖出持仓
        
        Args:
            stock_code: 股票代码
            sell_price: 卖出价格
            sell_ratio: 卖出比例（1.0=全部）
            reason: 卖出原因
            
        Returns:
            卖出记录 or None
        """
        position = self._find_active_position(stock_code)
        if not position:
            print(f"❌ 未找到活跃持仓: {stock_code}")
            return None
        
        # 计算卖出股数
        sell_shares = int(position.remaining_shares * sell_ratio)
        sell_value = sell_shares * sell_price
        
        # 记录卖出
        sell_record = {
            "price": sell_price,
            "shares": sell_shares,
            "date": datetime.now(),
            "ratio": sell_ratio,
            "reason": reason
        }
        position.sold_records.append(sell_record)
        
        # 更新持仓
        position.remaining_shares -= sell_shares
        position.remaining_position_pct *= (1 - sell_ratio)
        
        if position.remaining_shares <= 0:
            position.status = PositionStatus.CLOSED
            position.remaining_position_pct = 0
        else:
            position.status = PositionStatus.PARTIAL_SELL
        
        # 更新现金
        self.portfolio.cash += sell_value
        
        # 计算盈亏
        pnl = (sell_price - position.avg_cost) * sell_shares
        pnl_pct = (sell_price - position.avg_cost) / position.avg_cost * 100 if position.avg_cost > 0 else 0
        
        print(f"✅ 卖出成功: {position.stock_name}")
        print(f"   卖出价: {sell_price:.2f}, 股数: {sell_shares}")
        print(f"   盈亏: {pnl:.0f} ({pnl_pct:+.1f}%)")
        print(f"   原因: {reason}")
        
        return sell_record
    
    def execute_signal(self, signal: MonitorSignal) -> bool:
        """
        执行监控信号
        
        Args:
            signal: 监控信号
            
        Returns:
            是否成功执行
        """
        if signal.action == "SELL":
            result = self.sell_position(
                signal.stock_code,
                signal.price,
                signal.suggested_ratio,
                signal.signal_desc
            )
            return result is not None
        
        elif signal.action == "REDUCE":
            result = self.sell_position(
                signal.stock_code,
                signal.price,
                signal.suggested_ratio,
                signal.signal_desc
            )
            return result is not None
        
        elif signal.action == "ADD_POSITION":
            result = self.add_position(
                signal.stock_code,
                signal.price,
                signal.suggested_ratio
            )
            return result is not None
        
        return False
    
    def _find_active_position(self, stock_code: str) -> Optional[CorePosition]:
        """查找活跃持仓"""
        for p in self.portfolio.positions:
            if (p.stock_code == stock_code and 
                p.status in [PositionStatus.HOLDING, PositionStatus.PARTIAL_SELL]):
                return p
        return None
    
    def get_portfolio_summary(self) -> Dict:
        """获取组合摘要"""
        active_positions = [p for p in self.portfolio.positions 
                           if p.status in [PositionStatus.HOLDING, PositionStatus.PARTIAL_SELL]]
        
        # 计算总盈亏
        total_pnl = 0.0
        for p in active_positions:
            pnl = (p.current_price - p.avg_cost) * p.remaining_shares
            total_pnl += pnl
        
        total_pnl_pct = total_pnl / self.portfolio.core_capital * 100 if self.portfolio.core_capital > 0 else 0
        
        return {
            "总资金": self.portfolio.total_capital,
            "核心仓资金": self.portfolio.core_capital,
            "核心仓占比": self.portfolio.core_ratio,
            "可用现金": self.portfolio.cash,
            "当前持仓数": len(active_positions),
            "最大持仓数": self.portfolio.max_positions,
            "组合盈亏": total_pnl,
            "组合盈亏%": total_pnl_pct,
            "持仓列表": [
                {
                    "代码": p.stock_code,
                    "名称": p.stock_name,
                    "板块": p.sector,
                    "成本": p.avg_cost,
                    "现价": p.current_price,
                    "盈亏%": (p.current_price - p.avg_cost) / p.avg_cost * 100 if p.avg_cost > 0 else 0,
                    "仓位": p.remaining_position_pct,
                    "状态": p.status.value
                }
                for p in active_positions
            ]
        }
    
    def get_sector_positions(self) -> Dict[str, List[CorePosition]]:
        """按行业分组持仓"""
        sector_map = {}
        for p in self.portfolio.positions:
            if p.status in [PositionStatus.HOLDING, PositionStatus.PARTIAL_SELL]:
                if p.sector not in sector_map:
                    sector_map[p.sector] = []
                sector_map[p.sector].append(p)
        return sector_map
