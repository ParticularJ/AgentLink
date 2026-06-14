"""
核心仓交易系统 - 数据模型定义
严格遵循《核心仓策略 V3.0》四份设计文档
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum
from datetime import datetime


# ========== 枚举定义 ==========

class MacroEnvironment(Enum):
    """宏观流动性环境"""
    EXPANSION = "扩张期"      # 社融>12%且环比上升, 10Y国债<2.8%, 风险溢价<3%
    STABLE = "稳定期"         # 社融8%-12%, 10Y国债2.8%-3.2%, 风险溢价3%-5%
    CONTRACTION = "收缩期"    # 社融<8%或环比下降, 10Y国债>3.2%, 风险溢价>5%


class MarketStatus(Enum):
    """大盘状态"""
    STRONG = "强势"           # 上证>60日线 + 成交>万亿 + 涨跌比>1.5 + VIX<20
    OSCILLATING = "震荡"      # 上证在60-250日线之间 + 成交6000亿-1万亿
    WEAK = "弱势"             # 上证<250日线 或 成交<6000亿 或 VIX>25


class SectorLifecycle(Enum):
    """赛道生命周期"""
    INTRODUCTION = "导入期"   # 渗透率<5%
    EARLY_EXPLOSION = "爆发初期"  # 渗透率5%-10%
    MID_EXPLOSION = "爆发中期"    # 渗透率10%-20%
    MATURE = "成熟期"         # 渗透率>20%


class SignalLevel(Enum):
    """信号等级"""
    STRONG_BUY = "强烈推荐"   # ≥90分
    BUY = "推荐"              # 82-89分
    WATCH = "观察"            # 75-81分
    PASS = "剔除"             # <75分


class BuyPointType(Enum):
    """买点类型"""
    PULLBACK_MA20 = "上升趋势回踩20日线"   # 首选，胜率72%
    EARNINGS_GAP_PULLBACK = "净利润断层回踩"  # 次选，胜率68%
    PULLBACK_MA60 = "上升趋势回踩60日线"   # 次级，胜率58%
    BREAKOUT_CONSOLIDATION = "盘整突破"     # 谨慎，胜率55%


class BuyPointQuality(Enum):
    """买点质量"""
    IDEAL = "理想买点"        # 4项必要 + ≥2项加分，胜率75%+
    NORMAL = "一般买点"       # 4项必要 + 1项加分，胜率60-70%
    MARGINAL = "勉强买点"     # 仅4项必要，胜率50-60%


class PositionStatus(Enum):
    """持仓状态"""
    HOLDING = "持仓中"
    PARTIAL_SELL = "部分卖出"
    CLOSED = "已平仓"


class StopLossType(Enum):
    """止损类型"""
    FIXED = "固定止损"
    ATR_ADAPTIVE = "ATR自适应止损"
    MOVING = "移动止损"
    MA_BREAK = "均线止损"
    TIME = "时间止损"


class MonitorFrequency(Enum):
    """监控频率"""
    DAILY = "每日"
    WEEKLY = "每周"
    MONTHLY = "每月"


# ========== 宏观环境模型 ==========

@dataclass
class MacroLiquidity:
    """宏观流动性指标"""
    social_financing_growth: float = 0.0      # 社融增速%
    social_financing_mom_change: float = 0.0  # 社融环比变化%
    treasury_yield_10y: float = 0.0           # 10年期国债收益率%
    risk_premium: float = 0.0                 # 风险溢价%
    
    @property
    def environment(self) -> MacroEnvironment:
        """判断宏观环境"""
        if (self.social_financing_growth > 12 and 
            self.social_financing_mom_change > 0 and
            self.treasury_yield_10y < 2.8 and
            self.risk_premium < 3):
            return MacroEnvironment.EXPANSION
        elif (8 <= self.social_financing_growth <= 12 and
              2.8 <= self.treasury_yield_10y <= 3.2 and
              3 <= self.risk_premium <= 5):
            return MacroEnvironment.STABLE
        else:
            return MacroEnvironment.CONTRACTION
    
    @property
    def win_rate_adjustment(self) -> float:
        """胜率调整"""
        env = self.environment
        if env == MacroEnvironment.EXPANSION:
            return 0.10  # +8%~+12%, 取中值
        elif env == MacroEnvironment.STABLE:
            return 0.015  # +0%~+3%, 取中值
        else:
            return -0.115  # -8%~-15%, 取中值


@dataclass
class MarketContext:
    """大盘环境"""
    index_price: float = 0.0
    ma60: float = 0.0
    ma250: float = 0.0
    volume: float = 0.0              # 成交额（亿）
    advance_decline_ratio: float = 1.0  # 涨跌比
    vix: float = 20.0                # 波动率指数
    
    @property
    def status(self) -> MarketStatus:
        """判断大盘状态"""
        if (self.index_price > self.ma60 and 
            self.volume > 10000 and
            self.advance_decline_ratio > 1.5 and
            self.vix < 20):
            return MarketStatus.STRONG
        elif (self.ma60 <= self.index_price <= self.ma250 or
              (6000 <= self.volume <= 10000)):
            return MarketStatus.OSCILLATING
        else:
            return MarketStatus.WEAK
    
    @property
    def position_coefficient(self) -> float:
        """仓位系数"""
        status_map = {
            MarketStatus.STRONG: 1.0,
            MarketStatus.OSCILLATING: 0.5,
            MarketStatus.WEAK: 0.0
        }
        return status_map.get(self.status, 0.0)


# ========== 赛道模型 ==========

@dataclass
class SectorRating:
    """赛道评级"""
    sector_name: str
    rating: str = "C"                    # S/A/B/C
    lifecycle: SectorLifecycle = SectorLifecycle.INTRODUCTION
    penetration_rate: float = 0.0        # 渗透率%
    max_allocation_pct: float = 0.05     # 配置上限
    
    # 五维评分
    industry_stage_score: float = 0.0    # 产业阶段 40%
    macro_match_score: float = 0.0       # 宏观匹配度 15%
    policy_strength_score: float = 0.0   # 政策强度 20%
    foreign_consensus_score: float = 0.0 # 外资共识度 15%
    capex_score: float = 0.0             # 资本开支 10%
    
    @property
    def total_score(self) -> float:
        """赛道综合评分"""
        return (self.industry_stage_score * 0.40 +
                self.macro_match_score * 0.15 +
                self.policy_strength_score * 0.20 +
                self.foreign_consensus_score * 0.15 +
                self.capex_score * 0.10)


# ========== 个股初筛模型 ==========

@dataclass
class StockInitialScore:
    """个股初筛评分结果"""
    stock_code: str
    stock_name: str
    sector: str
    
    # 六维评分
    sector_heat_score: float = 0.0       # 赛道热度 25%
    chain_position_score: float = 0.0    # 产业链地位 25%
    tech_barrier_score: float = 0.0      # 技术壁垒 20%
    earnings_certainty_score: float = 0.0 # 业绩确定性 15%
    management_quality_score: float = 0.0 # 管理层质量 10%
    institution_consensus_score: float = 0.0 # 机构共识 5%
    
    # 一票否决标记
    veto_passed: bool = True
    veto_reason: str = ""
    
    # 原始数据（用于二筛）
    raw_data: Dict = field(default_factory=dict)
    
    @property
    def total_score(self) -> float:
        """初筛总分"""
        return (self.sector_heat_score * 0.25 +
                self.chain_position_score * 0.25 +
                self.tech_barrier_score * 0.20 +
                self.earnings_certainty_score * 0.15 +
                self.management_quality_score * 0.10 +
                self.institution_consensus_score * 0.05)


# ========== 财报验证模型 ==========

@dataclass
class FinancialReport:
    """财报数据"""
    revenue_growth: float = 0.0          # 营收增速%
    profit_growth: float = 0.0           # 利润增速%
    gross_margin_trend: float = 0.0      # 毛利率环比变化pct
    cash_flow_to_profit: float = 0.0     # 现金流/利润
    
    # 前瞻指标
    guidance_adjustment: str = "持平"     # 上调/持平/下调
    order_visibility: str = "一般"        # 饱满/一般/不足
    
    # 风险指标
    cash_flow_negative_quarters: int = 0  # 连续负现金流季度数
    receivable_growth_vs_revenue: float = 0.0  # 应收增速/营收增速
    inventory_growth_vs_revenue: float = 0.0   # 存货增速/营收增速
    major_holder_reduction_pct: float = 0.0    # 大股东减持%


@dataclass
class EarningsVerification:
    """超预期验证"""
    price_reaction: bool = False         # 财报后1-3日股价上涨
    analyst_reaction: bool = False       # ≥3家券商上调评级/目标价
    volume_reaction: bool = False        # 后续3日成交量放大
    northbound_inflow: bool = False      # 财报后5日净流入>5000万
    
    @property
    def match_count(self) -> int:
        """满足验证项数量"""
        return sum([self.price_reaction, self.analyst_reaction, 
                   self.volume_reaction, self.northbound_inflow])
    
    @property
    def win_rate(self) -> float:
        """对应胜率"""
        rates = {4: 0.88, 3: 0.78, 2: 0.68, 1: 0.55, 0: 0.35}
        return rates.get(self.match_count, 0.35)


@dataclass
class StockSecondaryScore:
    """二次筛选综合评分"""
    stock_code: str
    stock_name: str
    sector: str
    
    # 各阶段分数
    initial_score: float = 0.0           # 初筛分
    financial_score: float = 0.0         # 业绩得分
    expectation_score: float = 0.0       # 预期差分
    
    # 财报风险扣分
    risk_deduction: float = 0.0
    
    # 验证结果
    verification: Optional[EarningsVerification] = None
    
    @property
    def total_score(self) -> float:
        """综合评分 = 初筛分×35% + 业绩得分×40% + 预期差分×25%"""
        return (self.initial_score * 0.35 +
                self.financial_score * 0.40 +
                self.expectation_score * 0.25 -
                self.risk_deduction)
    
    @property
    def signal_level(self) -> SignalLevel:
        """信号等级"""
        score = self.total_score
        if score >= 90:
            return SignalLevel.STRONG_BUY
        elif score >= 82:
            return SignalLevel.BUY
        elif score >= 75:
            return SignalLevel.WATCH
        else:
            return SignalLevel.PASS
    
    @property
    def max_position_pct(self) -> float:
        """仓位上限"""
        score = self.total_score
        if score >= 90:
            return 0.18  # 18%
        elif score >= 82:
            return 0.12  # 12%
        else:
            return 0.0


# ========== 买点模型 ==========

@dataclass
class BuyPointSignal:
    """买点信号"""
    stock_code: str
    stock_name: str
    
    buy_point_type: BuyPointType = BuyPointType.PULLBACK_MA20
    quality: BuyPointQuality = BuyPointQuality.MARGINAL
    
    # 必要条件检查结果
    ma_alignment_pass: bool = False      # 均线排列
    pullback_pct: float = 0.0            # 回调幅度%
    volume_shrink_pass: bool = False     # 缩量标准
    price_stabilize_pass: bool = False   # 企稳信号
    
    # 加分项
    rsi_score: float = 0.0               # RSI 35-50加分
    atr_volatility_pass: bool = False    # ATR<5%
    
    # 计算出的仓位
    suggested_position_pct: float = 0.0
    
    # 六项确认清单
    checklist: Dict[str, bool] = field(default_factory=dict)
    
    @property
    def all_necessary_passed(self) -> bool:
        """所有必要条件通过"""
        return (self.ma_alignment_pass and 
                5 <= self.pullback_pct <= 12 and
                self.volume_shrink_pass and
                self.price_stabilize_pass)


# ========== 持仓模型 ==========

@dataclass
class CorePosition:
    """核心仓持仓记录"""
    stock_code: str
    stock_name: str
    sector: str
    
    # 买入信息
    entry_price: float = 0.0
    entry_date: datetime = field(default_factory=datetime.now)
    initial_shares: int = 0
    initial_position_pct: float = 0.0    # 初始仓位占比（相对核心仓资金）
    
    # 加仓记录
    add_positions: List[Dict] = field(default_factory=list)
    
    # 当前状态
    current_price: float = 0.0
    highest_price: float = 0.0           # 持仓期间最高价
    unrealized_pnl_pct: float = 0.0      # 浮动盈亏%
    status: PositionStatus = PositionStatus.HOLDING
    
    # 止损参数
    stop_loss_price: float = 0.0         # ATR自适应止损价
    fixed_stop_loss_price: float = 0.0   # 固定止损价（-10%）
    ma60_stop_price: float = 0.0         # 60日线止损价
    entry_atr: float = 0.0               # 买入时ATR
    
    # 止盈参数
    take_profit_levels: List[Dict] = field(default_factory=list)
    # 例如: [{"pct": 15, "sell_ratio": 0.333}, {"pct": 25, "sell_ratio": 0.333}]
    
    # 移动止损参数
    moving_stop_triggered: bool = False
    moving_stop_price: float = 0.0
    
    # 已执行卖出
    sold_records: List[Dict] = field(default_factory=list)
    remaining_shares: int = 0
    remaining_position_pct: float = 0.0
    
    # 时间止损
    time_stop_months: int = 2
    
    @property
    def total_cost(self) -> float:
        """总成本"""
        base_cost = self.entry_price * self.initial_shares
        add_cost = sum(p["price"] * p["shares"] for p in self.add_positions)
        return base_cost + add_cost
    
    @property
    def total_shares(self) -> int:
        """总股数"""
        return self.initial_shares + sum(p["shares"] for p in self.add_positions)
    
    @property
    def avg_cost(self) -> float:
        """平均成本"""
        total = self.total_shares
        return self.total_cost / total if total > 0 else 0


@dataclass
class CorePortfolio:
    """核心仓组合管理"""
    total_capital: float = 1000000.0     # 总资金
    core_ratio: float = 0.50             # 核心仓占比50%（默认）
    
    # 动态计算
    core_capital: float = 500000.0       # 核心仓资金
    max_single_position_pct: float = 0.18  # 单只最大18%
    max_positions: int = 8               # 最多持有8只
    
    # 组合风控
    portfolio_stop_loss_pct: float = 15.0  # 组合止损线15%
    sector_stop_loss_pct: float = 8.0      # 行业止损线8%
    
    # 持仓
    positions: List[CorePosition] = field(default_factory=list)
    cash: float = 500000.0               # 可用现金
    
    # 当日盈亏
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    
    def __post_init__(self):
        self.core_capital = self.total_capital * self.core_ratio
        if self.cash == 500000.0:  # 默认值时更新
            self.cash = self.core_capital


# ========== 监控信号模型 ==========

@dataclass
class MonitorSignal:
    """监控信号"""
    stock_code: str
    signal_type: str                     # STOP_LOSS / TAKE_PROFIT / ADD_POSITION / REDUCE / ALERT
    signal_desc: str
    action: str                          # SELL / BUY / REDUCE / HOLD
    suggested_ratio: float = 1.0         # 建议操作比例
    price: float = 0.0
    urgency: str = "normal"              # urgent / normal / low
    frequency: MonitorFrequency = MonitorFrequency.DAILY


@dataclass
class DailyTechMonitor:
    """每日技术监控数据"""
    stock_code: str
    close_price: float = 0.0
    above_ma20: bool = True
    volume_vs_ma20: float = 1.0          # 成交量/20日均量
    rsi: float = 50.0
    macd_signal: str = "金叉"             # 金叉/死叉/顶背离
    sector_relative_strength: float = 1.0 # 个股/板块指数相对强度
    atr_14: float = 0.0
    daily_volatility: float = 0.0        # 当日波动率


@dataclass
class WeeklyFundamentalMonitor:
    """每周基本面监控数据"""
    stock_code: str
    industry_policy_change: bool = False  # 政策转向
    company_bad_news: bool = False        # 公司利空（减持/诉讼/管理层变动）
    analyst_coverage_dropped: bool = False # 研报覆盖下降
    peg_ratio: float = 0.0
    pb_percentile: float = 0.0            # PB历史分位
    northbound_outflow_days: int = 0      # 北向连续净流出天数


# ========== 策略配置模型 ==========

@dataclass
class CoreStrategyConfig:
    """核心仓策略配置"""
    # 宏观过滤
    enable_macro_filter: bool = True
    
    # 赛道筛选
    target_lifecycles: List[SectorLifecycle] = field(
        default_factory=lambda: [SectorLifecycle.EARLY_EXPLOSION, SectorLifecycle.MID_EXPLOSION]
    )
    
    # 初筛参数
    initial_pool_size: int = 60          # 初筛池目标大小
    min_daily_volume: float = 1.5        # 最小日均成交额（亿）
    min_roe: float = 8.0                 # 最小ROE
    
    # 二筛参数
    min_revenue_growth: float = 15.0     # 最低营收增速
    min_profit_growth: float = 30.0      # 最低利润增速
    min_cash_flow_ratio: float = 0.6     # 最低现金流/利润比
    
    # 买点参数
    pullback_min_pct: float = 5.0        # 最小回调幅度
    pullback_max_pct: float = 12.0       # 最大回调幅度
    volume_shrink_threshold: float = 0.6 # 缩量阈值
    max_atr_pct: float = 5.0             # ATR上限
    
    # 止损参数
    fixed_stop_loss_pct: float = -10.0   # 固定止损-10%
    atr_multiplier: float = 2.0          # ATR倍数
    moving_stop_pct: float = -6.0        # 移动止损-6%
    time_stop_months: int = 2            # 时间止损2个月
    
    # 止盈参数
    profit_level_1: float = 15.0         # 第一止盈线15%
    profit_level_2: float = 25.0         # 第二止盈线25%
    profit_level_3: float = 40.0         # 第三止盈线40%
    profit_level_4: float = 60.0         # 第四止盈线60%
    
    # 加仓参数
    add_position_1_threshold: float = 20.0   # 第一次加仓浮盈门槛
    add_position_2_threshold: float = 40.0   # 第二次加仓浮盈门槛
    add_position_1_ratio: Tuple[float, float] = (0.25, 0.35)  # 第一次加仓比例
    add_position_2_ratio: Tuple[float, float] = (0.10, 0.20)  # 第二次加仓比例
    max_cumulative_position_pct: float = 0.65  # 累计仓位上限65%
