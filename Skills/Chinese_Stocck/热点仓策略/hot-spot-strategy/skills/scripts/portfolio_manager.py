"""
热点仓交易系统 - 组合管理器
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

from models import (
    HotSpotPortfolio, Position, PositionStatus, 
    StrategyType, StockScore, MonitorSignal
)


class PortfolioManager:
    """热点仓组合管理器"""
    
    def __init__(self, total_capital: float = 1000000.0):
        self.portfolio = HotSpotPortfolio(total_capital=total_capital)
        self._update_hot_spot_capital()
    
    def _update_hot_spot_capital(self):
        """更新热点仓资金"""
        self.portfolio.hot_spot_capital = self.portfolio.total_capital * self.portfolio.hot_spot_ratio
        self.portfolio.cash = self.portfolio.hot_spot_capital
    
    def set_hot_spot_ratio(self, ratio: float):
        """设置热点仓占比（根据市场环境动态调整）"""
        if 0.15 <= ratio <= 0.30:
            self.portfolio.hot_spot_ratio = ratio
            self._update_hot_spot_capital()
    
    def can_open_position(self, position_pct: float, 
                         strategy_type: StrategyType = None) -> Tuple[bool, str]:
        """
        检查是否可以开仓
        
        Args:
            position_pct: 建议仓位比例
            strategy_type: 策略类型（用于次新股特殊限制）
        
        Returns:
            (是否可以, 原因)
        """
        # 检查熔断
        if self.portfolio.fuse_triggered:
            return False, "已触发熔断，禁止开仓"
        
        # 检查日亏损预警
        if self.portfolio.daily_pnl_pct <= -self.portfolio.daily_loss_warning_pct:
            return False, f"日亏损达{abs(self.portfolio.daily_pnl_pct):.2f}%，触发一级熔断，禁止开新仓"
        
        # 检查持仓数量
        active_positions = [p for p in self.portfolio.positions if p.status == PositionStatus.HOLDING]
        if len(active_positions) >= self.portfolio.max_positions:
            return False, f"已达最大持仓数{self.portfolio.max_positions}只"
        
        # 次新股特殊限制
        if strategy_type == StrategyType.NEW_STOCK:
            # 检查是否已有次新股持仓
            new_stock_positions = [p for p in active_positions 
                                  if p.strategy_type == StrategyType.NEW_STOCK]
            if len(new_stock_positions) >= 1:
                return False, "已有次新股持仓，最多持有1只"
            
            # 次新股仓位上限5%
            if position_pct > 0.05:
                return False, f"次新股仓位{position_pct:.1%}超过上限5%"
        
        # 检查资金
        required_capital = self.portfolio.hot_spot_capital * position_pct
        if required_capital > self.portfolio.cash:
            return False, f"可用资金不足，需要{required_capital:.0f}，仅有{self.portfolio.cash:.0f}"
        
        # 检查单只仓位上限
        if position_pct > self.portfolio.max_single_position_pct:
            return False, f"单只仓位{position_pct:.1%}超过上限{self.portfolio.max_single_position_pct:.1%}"
        
        return True, "可以开仓"
    
    def open_position(self, stock_score: StockScore, entry_price: float, 
                     shares: int = None) -> Optional[Position]:
        """
        开仓
        
        Args:
            stock_score: 股票评分
            entry_price: 买入价格
            shares: 股数（不指定则按仓位计算）
            
        Returns:
            Position or None
        """
        can_open, reason = self.can_open_position(
            stock_score.suggested_position_pct, 
            stock_score.strategy_type
        )
        if not can_open:
            print(f"❌ 无法开仓: {reason}")
            return None
        
        # 计算买入金额和股数
        position_value = self.portfolio.hot_spot_capital * stock_score.suggested_position_pct
        
        if shares is None:
            shares = int(position_value / entry_price / 100) * 100  # 整手
        
        actual_value = shares * entry_price
        
        # 创建持仓
        position = Position(
            stock_code=stock_score.stock_code,
            stock_name=stock_score.stock_name,
            strategy_type=stock_score.strategy_type,
            entry_price=entry_price,
            entry_date=datetime.now(),
            initial_shares=shares,
            initial_position_pct=stock_score.suggested_position_pct,
            current_price=entry_price,
            highest_price=entry_price,
            stop_loss_price=entry_price * (1 + stock_score.stop_loss_pct / 100),
            stop_loss_pct=stock_score.stop_loss_pct,
            time_stop_days=stock_score.time_stop_days,
            remaining_shares=shares,
            remaining_pct=stock_score.suggested_position_pct
        )
        
        # 设置止盈参数
        position.take_profit_levels = self._get_take_profit_levels(stock_score.strategy_type)
        
        # 更新组合
        self.portfolio.positions.append(position)
        self.portfolio.cash -= actual_value
        
        print(f"✅ 开仓成功: {stock_score.stock_name}({stock_score.stock_code})")
        print(f"   买入价: {entry_price:.2f}, 股数: {shares}, 金额: {actual_value:.0f}")
        print(f"   仓位: {stock_score.suggested_position_pct:.1%}, 策略: {stock_score.strategy_type.value}")
        
        return position
    
    def _get_take_profit_levels(self, strategy_type: StrategyType) -> List[Dict]:
        """获取止盈层级"""
        if strategy_type == StrategyType.SECTOR_LEADER:
            # 龙头股四档止盈
            return [
                {"pct": 5, "sell_ratio": 0.25},
                {"pct": 10, "sell_ratio": 0.25},
                {"pct": 20, "sell_ratio": 0.25},
                {"pct": 30, "sell_ratio": 0.25}
            ]
        elif strategy_type == StrategyType.NEW_STOCK:
            # 次新股两档止盈
            return [
                {"pct": 5, "sell_ratio": 0.5},
                {"pct": 10, "sell_ratio": 0.5}
            ]
        else:
            # 普通热点股三档止盈
            return [
                {"pct": 5, "sell_ratio": 0.333},
                {"pct": 10, "sell_ratio": 0.333},
                {"pct": 20, "sell_ratio": 0.334}
            ]
    
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
        position = self._find_position(stock_code)
        if not position:
            print(f"❌ 未找到持仓: {stock_code}")
            return None
        
        # 检查策略是否允许加仓
        if position.strategy_type not in [StrategyType.LIMIT_UP_RETRACE, StrategyType.SECTOR_LEADER]:
            print(f"❌ 策略{position.strategy_type.value}不允许加仓")
            return None
        
        # 检查加仓次数
        if len(position.add_positions) >= 1:
            print(f"❌ 已达最大加仓次数1次")
            return None
        
        # 检查浮盈
        unrealized_pct = (add_price - position.entry_price) / position.entry_price * 100
        if unrealized_pct < 5:
            print(f"❌ 浮盈{unrealized_pct:.1f}%不足5%，不满足加仓条件")
            return None
        
        # 检查持有天数
        hold_days = (datetime.now() - position.entry_date).days
        if hold_days > 3:
            print(f"❌ 持有{hold_days}天超过3天，不满足加仓条件")
            return None
        
        # 计算加仓股数
        add_shares = int(position.initial_shares * add_ratio / 100) * 100
        add_value = add_shares * add_price
        
        if add_value > self.portfolio.cash:
            print(f"❌ 可用资金不足")
            return None
        
        # 执行加仓
        add_record = {
            "price": add_price,
            "shares": add_shares,
            "date": datetime.now(),
            "ratio": add_ratio
        }
        position.add_positions.append(add_record)
        
        # 更新止损线为首仓成本价
        position.stop_loss_price = position.entry_price
        position.stop_loss_pct = 0  # 保本
        
        # 更新持仓
        position.remaining_shares += add_shares
        self.portfolio.cash -= add_value
        
        print(f"✅ 加仓成功: {position.stock_name}")
        print(f"   加仓价: {add_price:.2f}, 股数: {add_shares}")
        print(f"   止损线上移至成本价: {position.entry_price:.2f}")
        
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
        position = self._find_position(stock_code)
        if not position or position.status == PositionStatus.CLOSED:
            print(f"❌ 未找到持仓或已平仓: {stock_code}")
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
        position.remaining_pct = position.remaining_pct * (1 - sell_ratio)
        
        if position.remaining_shares <= 0:
            position.status = PositionStatus.CLOSED
            position.remaining_pct = 0
        else:
            position.status = PositionStatus.PARTIAL_SELL
        
        # 更新现金
        self.portfolio.cash += sell_value
        
        # 计算盈亏
        cost = sum(r["price"] * r["shares"] for r in position.add_positions)
        cost += position.entry_price * position.initial_shares
        total_shares = position.initial_shares + sum(r["shares"] for r in position.add_positions)
        avg_cost = cost / total_shares if total_shares > 0 else 0
        pnl = (sell_price - avg_cost) * sell_shares
        pnl_pct = (sell_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
        
        print(f"✅ 卖出成功: {position.stock_name}")
        print(f"   卖出价: {sell_price:.2f}, 股数: {sell_shares}")
        print(f"   盈亏: {pnl:.0f} ({pnl_pct:+.1f}%)")
        print(f"   原因: {reason}")
        
        return sell_record
    
    def _find_position(self, stock_code: str) -> Optional[Position]:
        """查找持仓"""
        for p in self.portfolio.positions:
            if p.stock_code == stock_code and p.status in [PositionStatus.HOLDING, PositionStatus.PARTIAL_SELL]:
                return p
        return None
    
    def update_daily_pnl(self):
        """更新当日盈亏"""
        total_pnl = 0.0
        for position in self.portfolio.positions:
            if position.status == PositionStatus.HOLDING:
                unrealized = (position.current_price - position.entry_price) * position.remaining_shares
                total_pnl += unrealized
        
        self.portfolio.daily_pnl = total_pnl
        self.portfolio.daily_pnl_pct = total_pnl / self.portfolio.hot_spot_capital * 100
        
        # 检查熔断
        if self.portfolio.daily_pnl_pct <= -self.portfolio.daily_loss_limit_pct:
            self.portfolio.fuse_triggered = True
            print(f"🚨 触发二级熔断！日亏损达{abs(self.portfolio.daily_pnl_pct):.2f}%")
    
    def reset_fuse(self):
        """重置熔断（次日开盘前调用）"""
        self.portfolio.fuse_triggered = False
        self.portfolio.daily_pnl = 0.0
        self.portfolio.daily_pnl_pct = 0.0
        print("✅ 熔断已重置")
    
    def get_portfolio_summary(self) -> Dict:
        """获取组合摘要"""
        active_positions = [p for p in self.portfolio.positions if p.status == PositionStatus.HOLDING]
        
        return {
            "总资金": self.portfolio.total_capital,
            "热点仓资金": self.portfolio.hot_spot_capital,
            "热点仓占比": self.portfolio.hot_spot_ratio,
            "可用现金": self.portfolio.cash,
            "当前持仓数": len(active_positions),
            "最大持仓数": self.portfolio.max_positions,
            "当日盈亏": self.portfolio.daily_pnl,
            "当日盈亏%": self.portfolio.daily_pnl_pct,
            "熔断状态": "已触发" if self.portfolio.fuse_triggered else "正常",
            "持仓列表": [
                {
                    "代码": p.stock_code,
                    "名称": p.stock_name,
                    "策略": p.strategy_type.value,
                    "成本": p.entry_price,
                    "现价": p.current_price,
                    "盈亏%": p.unrealized_pnl_pct,
                    "仓位": p.remaining_pct
                }
                for p in active_positions
            ]
        }
