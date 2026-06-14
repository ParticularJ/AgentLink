"""
核心仓交易系统 - 持仓监控器（止损、止盈、加仓）
严格遵循《核心仓策略 V3.0》第四份设计文档
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from models import (
    CorePosition, PositionStatus, MonitorSignal, MonitorFrequency,
    DailyTechMonitor, WeeklyFundamentalMonitor, MarketContext, MarketStatus
)


class PositionMonitor:
    """持仓监控器"""
    
    def __init__(self):
        pass
    
    # ========== 止损检查 ==========
    
    def check_stop_loss(self, position: CorePosition, 
                       current_price: float,
                       ma60: float = 0) -> List[MonitorSignal]:
        """
        检查所有止损条件
        
        Returns:
            止损信号列表（优先级排序）
        """
        signals = []
        
        # 更新最高价
        if current_price > position.highest_price:
            position.highest_price = current_price
        
        # 1. ATR自适应止损（V3.0新增，优先）
        if position.entry_atr > 0:
            atr_stop = position.entry_price - 2 * position.entry_atr
            if current_price <= atr_stop:
                signals.append(MonitorSignal(
                    stock_code=position.stock_code,
                    signal_type="STOP_LOSS",
                    signal_desc=f"ATR自适应止损触发：当前价{current_price:.2f} <= 止损位{atr_stop:.2f}",
                    action="SELL",
                    suggested_ratio=1.0,
                    price=current_price,
                    urgency="urgent"
                ))
        
        # 2. 固定止损 -10%
        if current_price <= position.fixed_stop_loss_price:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="STOP_LOSS",
                signal_desc=f"固定止损触发：当前价{current_price:.2f} <= 止损价{position.fixed_stop_loss_price:.2f}",
                action="SELL",
                suggested_ratio=1.0,
                price=current_price,
                urgency="urgent"
            ))
        
        # 3. 移动止损 -6%（浮盈后启用）
        unrealized_pct = (current_price - position.avg_cost) / position.avg_cost * 100
        if unrealized_pct > 0:
            drawdown_pct = (position.highest_price - current_price) / position.highest_price * 100
            if drawdown_pct >= 6:
                signals.append(MonitorSignal(
                    stock_code=position.stock_code,
                    signal_type="STOP_LOSS",
                    signal_desc=f"移动止损触发：从最高点{position.highest_price:.2f}回撤{drawdown_pct:.1f}%",
                    action="SELL",
                    suggested_ratio=1.0,
                    price=current_price,
                    urgency="urgent"
                ))
        
        # 4. 均线止损：破60日线
        if ma60 > 0 and current_price < ma60:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="STOP_LOSS",
                signal_desc=f"均线止损触发：收盘价{current_price:.2f} < 60日线{ma60:.2f}",
                action="SELL",
                suggested_ratio=1.0,
                price=current_price,
                urgency="urgent"
            ))
        
        # 5. 时间止损：2个月未达预期
        hold_days = (datetime.now() - position.entry_date).days
        if hold_days >= 60:  # 约2个月
            if unrealized_pct <= 0:
                signals.append(MonitorSignal(
                    stock_code=position.stock_code,
                    signal_type="TIME_STOP",
                    signal_desc=f"时间止损触发：持有{hold_days}天未盈利",
                    action="SELL",
                    suggested_ratio=1.0,
                    price=current_price,
                    urgency="normal"
                ))
        
        return signals
    
    # ========== 止盈检查 ==========
    
    def check_take_profit(self, position: CorePosition, 
                         current_price: float,
                         market: MarketContext) -> List[MonitorSignal]:
        """
        检查止盈条件
        
        Args:
            market: 市场环境（用于调整止盈策略）
            
        Returns:
            止盈信号列表
        """
        signals = []
        unrealized_pct = (current_price - position.avg_cost) / position.avg_cost * 100
        
        # 根据市场环境调整止盈阈值
        env_adjustment = self._get_profit_adjustment(market)
        
        # 标准止盈层级（根据文档）
        levels = [
            {"pct": 15 * env_adjustment, "sell_ratio": 0.333, "label": "15%-25%区间"},
            {"pct": 25 * env_adjustment, "sell_ratio": 0.333, "label": "25%-40%区间"},
            {"pct": 40 * env_adjustment, "sell_ratio": 0.0, "label": "40%-60%区间", "move_stop": 20},
            {"pct": 60 * env_adjustment, "sell_ratio": 0.0, "label": ">60%区间", "move_stop": 40}
        ]
        
        for level in levels:
            target_pct = level["pct"]
            
            # 检查是否已触发过该层级
            triggered = any(
                r.get("take_profit_level") == target_pct
                for r in position.sold_records
            )
            
            if not triggered and unrealized_pct >= target_pct:
                if level.get("move_stop"):
                    # 移动止损至成本+X%
                    new_stop = position.avg_cost * (1 + level["move_stop"] / 100)
                    if new_stop > position.moving_stop_price:
                        position.moving_stop_price = new_stop
                        position.moving_stop_triggered = True
                        signals.append(MonitorSignal(
                            stock_code=position.stock_code,
                            signal_type="TAKE_PROFIT",
                            signal_desc=f"浮盈{unrealized_pct:.1f}%，移动止损至成本+{level['move_stop']}%",
                            action="HOLD",
                            suggested_ratio=0,
                            price=current_price,
                            urgency="normal"
                        ))
                else:
                    # 正常止盈卖出
                    signals.append(MonitorSignal(
                        stock_code=position.stock_code,
                        signal_type="TAKE_PROFIT",
                        signal_desc=f"触发{level['label']}止盈，浮盈{unrealized_pct:.1f}%",
                        action="SELL",
                        suggested_ratio=level["sell_ratio"],
                        price=current_price,
                        urgency="normal"
                    ))
        
        return signals
    
    def _get_profit_adjustment(self, market: MarketContext) -> float:
        """
        根据市场环境调整止盈阈值
        
        Returns:
            调整系数
        """
        status = market.status
        if status == MarketStatus.STRONG:
            return 1.30  # 牛市放宽30%
        elif status == MarketStatus.WEAK:
            return 0.80  # 熊市收紧20%
        else:
            return 1.0   # 震荡市标准
    
    # ========== 加仓检查 ==========
    
    def check_add_position(self, position: CorePosition,
                          current_price: float,
                          tech_data: Dict,
                          sector_data: Dict) -> Optional[MonitorSignal]:
        """
        检查加仓条件
        
        Args:
            tech_data: {
                'is_pullback_ma20': bool,     # 回踩20日线
                'volume_shrink_pct': float,   # 缩量程度%
                'ma20_trend': str,            # 'up'/'down'
            }
            sector_data: {
                'sector_vs_index': float,     # 板块相对大盘强度
                'earnings_beat': bool,        # 财报是否超预期
            }
            
        Returns:
            加仓信号 or None
        """
        unrealized_pct = (current_price - position.avg_cost) / position.avg_cost * 100
        
        # 检查加仓次数
        add_count = len(position.add_positions)
        if add_count >= 2:
            return None
        
        # 检查浮盈门槛
        if add_count == 0 and unrealized_pct < 20:
            return None
        if add_count == 1 and unrealized_pct < 40:
            return None
        
        # 必要条件检查
        # 1. 技术形态：回踩20日线企稳
        if not tech_data.get('is_pullback_ma20', False):
            return None
        
        # 2. 量能配合：缩量至均量60%以下
        if tech_data.get('volume_shrink_pct', 0) < 40:  # 缩量>60%
            return None
        
        # 3. 板块强度（V3.0新增必要条件）：板块指数强于大盘
        if sector_data.get('sector_vs_index', 0) <= 1.0:
            return None  # 逆板块不加仓（sector_vs_index <= 1.0 表示弱于或等于大盘）
        
        # 确定加仓比例
        if add_count == 0:
            ratio_range = (0.25, 0.35)
        else:
            ratio_range = (0.10, 0.20)
        
        # 业绩验证加分
        earnings_bonus = "，财报超预期" if sector_data.get('earnings_beat', False) else ""
        
        return MonitorSignal(
            stock_code=position.stock_code,
            signal_type="ADD_POSITION",
            signal_desc=f"满足加仓条件：浮盈{unrealized_pct:.1f}%，回踩20日线+缩量+板块强于大盘{earnings_bonus}",
            action="BUY",
            suggested_ratio=ratio_range[0],  # 取区间下限，保守
            price=current_price,
            urgency="normal"
        )
    
    # ========== 每日技术监控 ==========
    
    def daily_tech_monitor(self, position: CorePosition,
                          monitor_data: DailyTechMonitor) -> List[MonitorSignal]:
        """
        每日技术监控（15分钟）
        
        Returns:
            监控信号列表
        """
        signals = []
        
        # 更新当前价格
        position.current_price = monitor_data.close_price
        
        # 1. 均线监控：收盘>20日线
        if not monitor_data.above_ma20:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="收盘跌破20日线，观察3日",
                action="HOLD",
                suggested_ratio=0,
                price=monitor_data.close_price,
                urgency="normal"
            ))
        
        # 2. 量价监控：高位放量滞涨
        if monitor_data.volume_vs_ma20 > 1.5:  # 放量50%以上
            daily_change = (monitor_data.close_price - position.entry_price) / position.entry_price * 100
            if daily_change < 2:  # 涨幅<2%
                signals.append(MonitorSignal(
                    stock_code=position.stock_code,
                    signal_type="ALERT",
                    signal_desc="高位放量滞涨，建议减仓30%",
                    action="REDUCE",
                    suggested_ratio=0.30,
                    price=monitor_data.close_price,
                    urgency="normal"
                ))
        
        # 3. RSI监控
        if monitor_data.rsi > 80:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc=f"RSI={monitor_data.rsi:.0f}>80，准备止盈",
                action="HOLD",
                suggested_ratio=0,
                price=monitor_data.close_price,
                urgency="low"
            ))
        
        # 4. MACD监控：顶背离
        if monitor_data.macd_signal == "顶背离":
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="MACD顶背离，建议减仓50%",
                action="REDUCE",
                suggested_ratio=0.50,
                price=monitor_data.close_price,
                urgency="normal"
            ))
        
        # 5. 板块相对强度（V3.0新增）
        if monitor_data.sector_relative_strength < 1.0:
            # 连续5日弱于板块需要历史数据，这里简化处理
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="个股弱于板块指数",
                action="REDUCE",
                suggested_ratio=0.20,
                price=monitor_data.close_price,
                urgency="low"
            ))
        
        # 6. 波动率异常（V3.0新增）
        if monitor_data.atr_14 > 0:
            volatility_ratio = monitor_data.daily_volatility / monitor_data.atr_14
            if volatility_ratio > 3:
                signals.append(MonitorSignal(
                    stock_code=position.stock_code,
                    signal_type="ALERT",
                    signal_desc=f"单日波动{monitor_data.daily_volatility:.1f}% > 3倍ATR，排查消息",
                    action="HOLD",
                    suggested_ratio=0,
                    price=monitor_data.close_price,
                    urgency="urgent"
                ))
        
        return signals
    
    # ========== 每周基本面监控 ==========
    
    def weekly_fundamental_monitor(self, position: CorePosition,
                                   monitor_data: WeeklyFundamentalMonitor) -> List[MonitorSignal]:
        """
        每周基本面监控（30分钟/周）
        
        Returns:
            监控信号列表
        """
        signals = []
        
        # 1. 行业动态：政策转向/技术路线变更
        if monitor_data.industry_policy_change:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="行业政策/技术路线变更，重新评估投资逻辑",
                action="REDUCE",
                suggested_ratio=0.50,
                price=position.current_price,
                urgency="urgent"
            ))
        
        # 2. 公司公告：减持/诉讼/管理层变动
        if monitor_data.company_bad_news:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="公司利空公告（减持/诉讼/管理层变动），减仓50%或清仓",
                action="REDUCE",
                suggested_ratio=0.50,
                price=position.current_price,
                urgency="urgent"
            ))
        
        # 3. 研报跟踪：连续2周无新报告或评级下调
        if monitor_data.analyst_coverage_dropped:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc="研报覆盖下降或评级下调",
                action="REDUCE",
                suggested_ratio=0.20,
                price=position.current_price,
                urgency="normal"
            ))
        
        # 4. 估值变化：PEG>2.0或PB>历史90%分位
        if monitor_data.peg_ratio > 2.0:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc=f"PEG={monitor_data.peg_ratio:.2f}>2.0，估值偏高",
                action="REDUCE",
                suggested_ratio=0.30,
                price=position.current_price,
                urgency="normal"
            ))
        
        # 5. 北向资金（V3.0新增）：连续10日净流出
        if monitor_data.northbound_outflow_days >= 10:
            signals.append(MonitorSignal(
                stock_code=position.stock_code,
                signal_type="ALERT",
                signal_desc=f"北向资金连续{monitor_data.northbound_outflow_days}日净流出",
                action="REDUCE",
                suggested_ratio=0.20,
                price=position.current_price,
                urgency="normal"
            ))
        
        return signals
    
    # ========== 组合层面风控 ==========
    
    def check_portfolio_risk(self, 
                            positions: List[CorePosition],
                            sector_positions: Dict[str, List[CorePosition]],
                            vix: float = 20) -> List[MonitorSignal]:
        """
        组合层面风控（三道防线）
        
        Args:
            positions: 所有持仓
            sector_positions: {sector: [positions]}
            vix: 波动率指数
            
        Returns:
            风控信号列表
        """
        signals = []
        
        # 第一道：个股止损（在check_stop_loss中处理）
        
        # 第二道：行业止损
        for sector, sector_pos in sector_positions.items():
            sector_pnl = self._calculate_sector_pnl(sector_pos)
            if sector_pnl < -8:  # 行业整体亏损>8%
                signals.append(MonitorSignal(
                    stock_code="PORTFOLIO",
                    signal_type="SECTOR_STOP",
                    signal_desc=f"{sector}行业整体亏损{sector_pnl:.1f}%>8%，减仓50%",
                    action="REDUCE",
                    suggested_ratio=0.50,
                    price=0,
                    urgency="urgent"
                ))
        
        # 第三道：组合止损
        total_pnl = self._calculate_total_pnl(positions)
        if total_pnl < -15:  # 核心仓整体回撤>15%
            signals.append(MonitorSignal(
                stock_code="PORTFOLIO",
                signal_type="PORTFOLIO_STOP",
                signal_desc=f"核心仓整体回撤{total_pnl:.1f}%>15%，总仓位降至30%以下",
                action="REDUCE",
                suggested_ratio=0.70,  # 降至30%
                price=0,
                urgency="urgent"
            ))
        
        # 极端防线：VIX>30
        if vix > 30:
            signals.append(MonitorSignal(
                stock_code="PORTFOLIO",
                signal_type="EXTREME_STOP",
                signal_desc=f"VIX={vix:.0f}>30，系统性风险，降至10%或空仓",
                action="REDUCE",
                suggested_ratio=0.90,  # 降至10%
                price=0,
                urgency="urgent"
            ))
        
        return signals
    
    def _calculate_sector_pnl(self, positions: List[CorePosition]) -> float:
        """计算行业整体盈亏%"""
        if not positions:
            return 0.0
        
        total_cost = sum(p.avg_cost * p.total_shares for p in positions)
        total_value = sum(p.current_price * p.remaining_shares for p in positions)
        
        if total_cost <= 0:
            return 0.0
        
        return (total_value - total_cost) / total_cost * 100
    
    def _calculate_total_pnl(self, positions: List[CorePosition]) -> float:
        """计算组合整体盈亏%"""
        if not positions:
            return 0.0
        
        total_cost = sum(p.avg_cost * p.total_shares for p in positions)
        total_value = sum(p.current_price * p.remaining_shares for p in positions)
        
        if total_cost <= 0:
            return 0.0
        
        return (total_value - total_cost) / total_cost * 100
