from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class RiskLevel(str, Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CONFIRM = 4

class MarketState(str, Enum):
    STRONG_UP = "强势主升"
    RANGE_UP = "震荡偏多"
    RANGE_WEAK = "弱势震荡"
    DOWN_TREND = "下跌趋势"
    SYSTEM_RISK = "系统性风险"

@dataclass
class StockData:
    """股票实时数据"""
    code: str
    name: str
    price: float
    open: float
    high: float
    low: float
    volume: int
    turnover: float
    change_pct: float
    volume_ratio: float  # 量比
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class TechnicalIndicators:
    """技术指标"""
    ma5: float
    ma10: float
    ma20: float
    ma60: float
    macd: float
    macd_signal: float
    macd_hist: float
    kdj_k: float
    kdj_d: float
    kdj_j: float

@dataclass
class StockScore:
    """个股综合评分"""
    total_score: float
    sector_name: str
    technical_score: float
    money_flow_score: float
    sector_score: float
    fundamental_score: float
    volume_score: float
    sentiment_score: float

@dataclass
class Holding:
    """持仓信息"""
    code: str
    name: str
    cost: float
    shares: int
    init_shares: int
    current_price: float
    highest_price: float
    entry_date: datetime
      # 加仓日期
    last_add_date: datetime 
    strategy_name: str
    score: float = 0
    tech_indicators: Optional[TechnicalIndicators] = None
    # 各档位是否已触发过
    stop_level_hit: List[bool] = field(default_factory=lambda: [False, False, False])  
    # 止损各档位是否触发，MA5,MA10, -6%, -8%
    stop_lose_hit: List[bool] = field(default_factory=lambda: [False, False, False, False])  
  
    # 加仓次数
    add_count: int = 0
  


@dataclass
class Alert:
    """预警信息"""
    code: str
    name: str
    risk_level: RiskLevel
    message: str
    action: str
    current_price: float
    ma_value: float
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class PositionAdvice:
    """仓位建议"""
    market_state: MarketState
    suggested_position: float
    current_position: float
    available_position: float
    trend_coef: float
    reason: str
