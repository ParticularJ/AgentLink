"""
热点仓交易系统 - 风险管理器
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

from models import Position, PositionStatus, StrategyType, MonitorSignal


class RiskManager:
    """风险管理器"""
    
    def __init__(self):
        pass
    
    def check_stop_loss(self, position: Position, current_price: float) -> Optional[MonitorSignal]:
        """
        检查止损条件
        
        Returns:
            MonitorSignal or None
        """
        # 更新最高价
        if current_price > position.highest_price:
            position.highest_price = current_price
        
        # 1. 固定止损
        if current_price <= position.stop_loss_price:
            return MonitorSignal(
                stock_code=position.stock_code,
                signal_type="STOP_LOSS",
                signal_desc=f"触发固定止损，当前价{current_price:.2f} <= 止损价{position.stop_loss_price:.2f}",
                action="SELL",
                suggested_ratio=1.0,
                price=current_price,
                urgency="urgent"
            )
        
        # 2. 移动止损（浮盈>5%后启用）
        unrealized_pct = (current_price - position.entry_price) / position.entry_price * 100
        if unrealized_pct > 5:
            # 从最高点回撤-5%
            drawdown_pct = (position.highest_price - current_price) / position.highest_price * 100
            if drawdown_pct >= 5:
                return MonitorSignal(
                    stock_code=position.stock_code,
                    signal_type="STOP_LOSS",
                    signal_desc=f"触发移动止损，从最高点{position.highest_price:.2f}回撤{drawdown_pct:.1f}%",
                    action="SELL",
                    suggested_ratio=1.0,
                    price=current_price,
                    urgency="urgent"
                )
        
        # 3. 均线止损
        # 这里需要传入MA5数据，简化处理
        # 实际使用时需要传入技术指标
        
        return None
    
    def check_time_stop(self, position: Position) -> Optional[MonitorSignal]:
        """
        检查时间止损
        
        Returns:
            MonitorSignal or None
        """
        hold_days = (datetime.now() - position.entry_date).days
        
        # 次新股3天，其他5天
        limit_days = 3 if position.strategy_type == StrategyType.NEW_STOCK else position.time_stop_days
        
        if hold_days >= limit_days:
            # 检查是否盈利
            unrealized_pct = (position.current_price - position.entry_price) / position.entry_price * 100
            
            if unrealized_pct <= 0:
                return MonitorSignal(
                    stock_code=position.stock_code,
                    signal_type="TIME_STOP",
                    signal_desc=f"持有{hold_days}天未盈利，触发时间止损",
                    action="SELL",
                    suggested_ratio=1.0,
                    price=position.current_price,
                    urgency="normal"
                )
        
        return None
    
    def check_take_profit(self, position: Position, current_price: float) -> List[MonitorSignal]:
        """
        检查止盈条件
        
        Returns:
            List[MonitorSignal]
        """
        signals = []
        unrealized_pct = (current_price - position.entry_price) / position.entry_price * 100
        
        # 检查各止盈层级
        for level in position.take_profit_levels:
            target_pct = level["pct"]
            sell_ratio = level["sell_ratio"]
            
            # 检查是否已触发过该层级
            triggered = any(
                r.get("take_profit_level") == target_pct 
                for r in position.sold_records
            )
            
            if not triggered and unrealized_pct >= target_pct:
                signals.append(MonitorSignal(
                    stock_code=position.stock_code,
                    signal_type="TAKE_PROFIT",
                    signal_desc=f"触发止盈层级{target_pct}%，浮盈{unrealized_pct:.1f}%",
                    action="SELL",
                    suggested_ratio=sell_ratio,
                    price=current_price,
                    urgency="normal"
                ))
        
        return signals
    
    def check_special_signals(self, position: Position, 
                             market_data: Dict) -> List[MonitorSignal]:
        """
        检查特殊止盈信号
        
        Args:
            position: 持仓
            market_data: {
                '炸板': bool,
                '炸板_duration': int,  # 炸板持续时间（分钟）
                '尾盘涨停被砸': bool,
                '板块龙头被替换': bool,
                '高位巨量阴线': bool,
                '巨量阴线跌幅': float,
                '巨量阴线量能_ratio': float,
                '监管出手': bool,
            }
            
        Returns:
            List[MonitorSignal]
        """
        signals = []
        
        # 1. 盘中炸板>15分钟未回封
        if market_data.get('炸板', False) and market_data.get('炸板_duration', 0) > 15:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="SPECIAL",
                signal_desc="炸板超过15分钟未回封",
                action="SELL",
                suggested_ratio=1.0,
                price=position.current_price,
                urgency="urgent"
            ))
        
        # 2. 尾盘涨停被砸
        if market_data.get('尾盘涨停被砸', False):
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="SPECIAL",
                signal_desc="尾盘涨停被砸",
                action="SELL",
                suggested_ratio=0.5,
                price=position.current_price,
                urgency="urgent"
            ))
        
        # 3. 板块龙头被替换
        if market_data.get('板块龙头被替换', False):
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="SPECIAL",
                signal_desc="板块龙头被替换",
                action="SELL",
                suggested_ratio=0.5,
                price=position.current_price,
                urgency="normal"
            ))
        
        # 4. 高位巨量阴线
        if (market_data.get('高位巨量阴线', False) and 
            market_data.get('巨量阴线跌幅', 0) >= 3 and
            market_data.get('巨量阴线量能_ratio', 0) > 1.5):
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="SPECIAL",
                signal_desc="高位巨量阴线，跌幅≥3%且量能>前日1.5倍",
                action="SELL",
                suggested_ratio=1.0,
                price=position.current_price,
                urgency="urgent"
            ))
        
        # 5. 监管出手
        if market_data.get('监管出手', False):
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="SPECIAL",
                signal_desc="监管出手",
                action="SELL",
                suggested_ratio=1.0,
                price=position.current_price,
                urgency="urgent"
            ))
        
        return signals
    
    def intraday_monitor(self, position: Position, 
                        intraday_data: Dict) -> List[MonitorSignal]:
        """
        盘中实时监控
        
        Args:
            position: 持仓
            intraday_data: {
                'current_price': float,
                'below_ma_minutes': int,  # 跌破分时均线分钟数
                'volume_surge_ratio': float,  # 量能放大比例
                'sector_limit_down_count': int,  # 板块跌停数
                'is_limit_up': bool,  # 是否涨停
                '炸板_duration': int,
                'is_leader': bool,  # 是否仍为龙头
            }
            
        Returns:
            List[MonitorSignal]
        """
        signals = []
        current_price = intraday_data.get('current_price', position.current_price)
        
        # 更新当前价格
        position.current_price = current_price
        
        # 1. 止损检查
        stop_signal = self.check_stop_loss(position, current_price)
        if stop_signal:
            signals.append(stop_signal)
            return signals  # 止损信号优先级最高
        
        # 2. 跌破分时均线>15分钟
        if intraday_data.get('below_ma_minutes', 0) > 15:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="跌破分时均线超过15分钟",
                action="SELL",
                suggested_ratio=0.333,
                price=current_price,
                urgency="normal"
            ))
        
        # 3. 爆量（+100%以上且不涨）
        volume_surge = intraday_data.get('volume_surge_ratio', 0)
        if volume_surge > 1.0:  # 放大100%以上
            daily_change = (current_price - position.entry_price) / position.entry_price
            if daily_change < 0.02:  # 涨幅<2%
                signals.append(MonitorSignal(
                    stock_code=position.stock_code,
                    signal_type="ALERT",
                    signal_desc=f"爆量{volume_surge:.0%}但涨幅仅{daily_change:.1%}",
                    action="SELL",
                    suggested_ratio=0.5,
                    price=current_price,
                    urgency="normal"
                ))
        
        # 4. 板块跌停≥3只
        if intraday_data.get('sector_limit_down_count', 0) >= 3:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="板块内出现≥3只跌停",
                action="SELL",
                suggested_ratio=1.0,
                price=current_price,
                urgency="urgent"
            ))
        
        # 5. 炸板检查
        if intraday_data.get('is_limit_up', False):
            炸板_duration = intraday_data.get('炸板_duration', 0)
            if 炸板_duration > 10:
                signals.append(MonitorSignal(
                    stock_code=position.stock_code,
                    signal_type="ALERT",
                    signal_desc=f"炸板{炸板_duration}分钟未回封",
                    action="SELL",
                    suggested_ratio=1.0,
                    price=current_price,
                    urgency="urgent"
                ))
        
        # 6. 龙头地位丧失
        if not intraday_data.get('is_leader', True):
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="龙头地位被超越",
                action="SELL",
                suggested_ratio=0.5,
                price=current_price,
                urgency="normal"
            ))
        
        return signals
    
    def daily_monitor(self, position: Position, 
                     daily_data: Dict) -> List[MonitorSignal]:
        """
        收盘后每日监控
        
        Args:
            position: 持仓
            daily_data: {
                'close_price': float,
                'above_ma5': bool,
                'volume_ratio': float,  # 量能/前日
                'is_high_volume_stagnation': bool,  # 高位放量滞涨
                'kline_pattern': str,  # '长上影'/'大阳线'/...
                'turnover': float,
                'leader_score': float,  # 龙头评分
                'sector_heat_score': float,
                'is_limit_up': bool,  # 是否涨停
            }
            
        Returns:
            List[MonitorSignal]
        """
        signals = []
        close_price = daily_data.get('close_price', position.current_price)
        position.current_price = close_price
        
        # 1. 收盘破5日线
        if not daily_data.get('above_ma5', True):
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="收盘跌破5日线",
                action="SELL",
                suggested_ratio=1.0,
                price=close_price,
                urgency="urgent"
            ))
        
        # 2. 高位放量滞涨
        if daily_data.get('is_high_volume_stagnation', False):
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="高位放量滞涨",
                action="SELL",
                suggested_ratio=0.5,
                price=close_price,
                urgency="normal"
            ))
        
        # 3. 长上影
        if daily_data.get('kline_pattern', '') == '长上影':
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="长上影线（>实体2倍）",
                action="SELL",
                suggested_ratio=0.5,
                price=close_price,
                urgency="normal"
            ))
        
        # 4. 换手率危险线
        turnover = daily_data.get('turnover', 0)
        if turnover > 35:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc=f"换手率{turnover:.1f}%超过35%危险线",
                action="SELL",
                suggested_ratio=1.0,
                price=close_price,
                urgency="normal"
            ))
        
        # 5. 龙头评分连续下降
        leader_score = daily_data.get('leader_score', 100)
        if leader_score < 70:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc=f"龙头评分降至{leader_score:.0f}分",
                action="SELL",
                suggested_ratio=0.5,
                price=close_price,
                urgency="normal"
            ))
        
        # 6. 板块热度退出前5
        sector_heat = daily_data.get('sector_heat_score', 100)
        if sector_heat < 70:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="板块热度退出前5",
                action="SELL",
                suggested_ratio=1.0,
                price=close_price,
                urgency="normal"
            ))
        
        # 7. 止盈检查
        profit_signals = self.check_take_profit(position, close_price)
        signals.extend(profit_signals)
        
        # 8. 时间止损检查
        time_signal = self.check_time_stop(position)
        if time_signal:
            signals.append(time_signal)
        
        return signals
