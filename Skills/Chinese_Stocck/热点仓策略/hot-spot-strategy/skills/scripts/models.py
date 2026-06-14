"""
热点仓交易系统 - 数据模型定义
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum
from datetime import datetime


class StrategyType(Enum):
    """四大策略类型"""
    FIRST_LIMIT_UP = "首次涨停板"      # 策略一
    LIMIT_UP_RETRACE = "涨停回调"      # 策略二
    SECTOR_LEADER = "热门板块龙头"      # 策略三
    NEW_STOCK = "次新股"               # 策略四


class SignalLevel(Enum):
    """信号等级"""
    STRONG_BUY = "强烈买入"    # 90-100分
    BUY = "买入"               # 75-89分
    WATCH = "观望"             # 65-74分
    PASS = "放弃"              # <65分


class PositionStatus(Enum):
    """持仓状态"""
    HOLDING = "持仓中"
    CLOSED = "已平仓"
    PARTIAL_SELL = "部分卖出"


class StopLossType(Enum):
    """止损类型"""
    FIXED = "固定止损"
    ATR = "ATR动态止损"
    MOVING = "移动止损"
    CHANDELIER = "Chandelier Exit"
    TIME = "时间止损"
    MA = "均线止损"


@dataclass
class MarketEnvironment:
    """市场环境"""
    index_above_ma20: bool = True       # 大盘是否站20日线
    market_status: str = "正常"          # 正常/谨慎/停止
    daily_loss_pct: float = 0.0         # 当日亏损百分比
    consecutive_loss_days: int = 0      # 连续亏损天数


@dataclass
class SectorHeat:
    """板块热度"""
    sector_name: str
    rise_pct: float = 0.0               # 板块涨幅%
    limit_up_count: int = 0             # 涨停家数
    capital_inflow_pct: float = 0.0     # 资金净流入占成交额%
    above_ma20: bool = False            # 板块指数是否站20日线
    trend_up: bool = False              # 趋势向上
    max_consecutive_limit: int = 0      # 最高连板数
    total_score: float = 0.0            # 板块热度总分


@dataclass
class StockScore:
    """股票评分结果"""
    strategy_type: StrategyType
    stock_code: str
    stock_name: str
    
    # 各维度得分
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    
    # 评级
    signal_level: SignalLevel = SignalLevel.PASS
    
    # 仓位建议
    suggested_position_pct: float = 0.0  # 建议仓位百分比
    
    # 买入信息
    buy_timing: str = ""                # 买入时机说明
    entry_price: float = 0.0            # 建议买入价
    
    # 风控参数
    stop_loss_price: float = 0.0        # 止损价
    stop_loss_pct: float = -7.0         # 止损百分比
    time_stop_days: int = 5             # 时间止损天数
    
    # 多策略加分
    multi_strategy_bonus: float = 0.0   # 多策略加分
    hit_strategies: List[StrategyType] = field(default_factory=list)
    
    # 一票否决
    veto_passed: bool = True
    veto_reason: str = ""
    
    # 时间戳
    score_time: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    """持仓记录"""
    stock_code: str
    stock_name: str
    strategy_type: StrategyType
    
    # 买入信息
    entry_price: float = 0.0
    entry_date: datetime = field(default_factory=datetime.now)
    initial_shares: int = 0
    initial_position_pct: float = 0.0   # 初始仓位占比
    
    # 加仓记录
    add_positions: List[Dict] = field(default_factory=list)  # [{price, shares, date}]
    
    # 当前状态
    current_price: float = 0.0
    highest_price: float = 0.0          # 持仓期间最高价
    unrealized_pnl_pct: float = 0.0     # 浮动盈亏%
    status: PositionStatus = PositionStatus.HOLDING
    
    # 止损参数
    stop_loss_price: float = 0.0
    stop_loss_pct: float = -7.0
    time_stop_days: int = 5
    
    # 止盈参数
    take_profit_levels: List[Dict] = field(default_factory=list)
    # 例如: [{"pct": 5, "sell_ratio": 0.333}, {"pct": 10, "sell_ratio": 0.333}]
    
    # 已执行卖出
    sold_records: List[Dict] = field(default_factory=list)
    remaining_shares: int = 0
    remaining_pct: float = 0.0          # 剩余仓位占比


@dataclass
class HotSpotPortfolio:
    """热点仓组合管理"""
    total_capital: float = 1000000.0    # 总资金
    hot_spot_ratio: float = 0.25        # 热点仓占比25%
    
    # 动态计算
    hot_spot_capital: float = 250000.0  # 热点仓资金
    max_single_position_pct: float = 0.30  # 单只最大30%
    max_positions: int = 3              # 最多持有3只
    
    # 熔断机制
    daily_loss_limit_pct: float = 2.0   # 日亏损上限2%
    daily_loss_warning_pct: float = 1.5 # 日亏损预警1.5%
    fuse_triggered: bool = False        # 是否触发熔断
    
    # 持仓
    positions: List[Position] = field(default_factory=list)
    cash: float = 250000.0              # 可用现金
    
    # 当日盈亏
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0


@dataclass
class MonitorSignal:
    """监控信号"""
    stock_code: str
    signal_type: str                    # STOP_LOSS / TAKE_PROFIT / ADD_POSITION / TIME_STOP / ALERT
    signal_desc: str
    action: str                         # SELL / BUY / HOLD
    suggested_ratio: float = 1.0        # 建议操作比例
    price: float = 0.0
    urgency: str = "normal"             # urgent / normal / low
