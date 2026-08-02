"""
波段交易系统 - 数据模型定义
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum
from datetime import date


class MarketEnvironment(Enum):
    """大盘环境等级"""
    GREEN = "绿灯"      # >= 60分
    YELLOW = "黄灯"     # 40-59分
    RED = "红灯"        # < 40分


class MarketStatus(Enum):
    """市场状态"""
    BULL = "牛市"
    OSCILLATION = "震荡市"
    BEAR = "熊市"


class TrackRating(Enum):
    """赛道评级"""
    S = "S级"
    A = "A级"
    B = "B级"


class ChainLevel(Enum):
    """产业链层级"""
    UPSTREAM = "上游"
    MIDSTREAM = "中游"
    DOWNSTREAM = "下游"
    SUPPORT = "支撑层"


class PositionRating(Enum):
    """卡位评级"""
    CORE = "核心"
    IMPORTANT = "重要"
    GENERAL = "一般"
    EDGE = "边缘"


class Phase(Enum):
    """景气传导阶段"""
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    FULL_CYCLE = "全周期"


class RotationPhase(Enum):
    """板块轮动阶段"""
    START = "启动期"
    ACCELERATE = "加速期"
    PEAK = "高潮期"
    DECLINE = "衰退期"


class Grade(Enum):
    """档位"""
    FIRST = "一档"
    SECOND = "二档"
    THIRD = "三档"


class IndustryType(Enum):
    """行业类型"""
    TECH_GROWTH = "科技成长型"
    CONSUMER_VALUE = "消费价值型"
    CYCLICAL_RESOURCE = "周期资源型"
    MANUFACTURING = "制造工业型"


class MoatLevel(Enum):
    """护城河等级"""
    STRONG = "强"
    MEDIUM = "中"
    WEAK = "弱"


class ValuationMethod(Enum):
    """估值方法"""
    PEG = "PEG"
    PB_ROE = "PB-ROE"
    PS = "PS"


class ValuationConclusion(Enum):
    """估值结论"""
    SEVERELY_UNDERVALUED = "严重低估"
    UNDERVALUED = "低估"
    FAIRLY_LOW = "合理偏低"
    FAIR = "合理"
    OVERVALUED = "偏贵"
    HIGHLY_OVERVALUED = "高估"


class FinalDecision(Enum):
    """最终决策"""
    BUY_CANDIDATE = "买入候选"
    WATCH = "观察"
    REJECT = "剔除"


@dataclass
class MarketEnvironmentScore:
    """大盘环境评分"""
    index_trend_score: float = 0.0      # 指数趋势 0-40分
    liquidity_score: float = 0.0         # 市场流动性 0-30分
    sentiment_score: float = 0.0         # 市场情绪 0-20分
    northbound_score: float = 0.0        # 北向资金 0-10分
    total_score: float = 0.0             # 总分
    environment: MarketEnvironment = MarketEnvironment.RED
    market_status: MarketStatus = MarketStatus.BEAR


@dataclass
class Track:
    """赛道"""
    name: str
    policy_score: float = 0.0            # 政策强度 0-25分
    industry_phase_score: float = 0.0    # 产业阶段 0-30分
    capital_consensus_score: float = 0.0 # 资金共识 0-30分
    catalyst_density_score: float = 0.0  # 催化密度 0-15分
    total_score: float = 0.0             # 总分
    rating: TrackRating = TrackRating.B
    sources: List[str] = field(default_factory=list)  # 来源：政策/资金/产业
    rotation_phase: RotationPhase = RotationPhase.START


@dataclass
class Stock:
    """股票基础信息"""
    code: str
    name: str
    track: str = ""
    chain_level: ChainLevel = ChainLevel.MIDSTREAM
    chain_link: str = ""                 # 产业链环节
    position_rating: PositionRating = PositionRating.GENERAL
    prosperity_phase: str = ""           # 景气传导阶段
    catalyst_calendar: str = ""          # 催化日历

    # 行情数据
    latest_price: float = 0.0
    market_cap: float = 0.0              # 总市值（亿元）
    float_market_cap: float = 0.0        # 流通市值（亿元）
    rise_60d: float = 0.0                # 近60日涨幅%
    rise_20d: float = 0.0                # 近20日涨幅%
    avg_volume_20d: float = 0.0          # 近20日日均成交额（万元）
    avg_turnover_60d: float = 0.0        # 近60日日均换手率%
    volatility_60d: float = 0.0          # 近60日年化波动率%
    beta: float = 1.0                    # Beta系数

    # 财务数据（用于过滤和评分）
    operating_cash_flow_ttm: float = 0.0  # 经营现金流TTM
    operating_cash_flow_last: float = 0.0 # 上季度经营现金流
    receivables_revenue_ratio: float = 0.0 # 应收账款/营收
    goodwill_total_assets_ratio: float = 0.0 # 商誉/总资产
    net_profit_ttm: float = 0.0          # 净利润TTM
    net_profit_last: float = 0.0         # 上季度净利润
    interest_bearing_debt_ratio: float = 0.0 # 有息负债率


@dataclass
class Phase1Score:
    """第一阶段三因子评分"""
    # 产业动量 满分35分
    track_rating_score: float = 0.0      # 赛道评级 0-15分
    chain_position_score: float = 0.0    # 产业链卡位 0-12分
    catalyst_score: float = 0.0          # 催化日历密度 0-8分
    industry_momentum: float = 0.0       # 产业动量总分

    # 个股弹性 满分35分
    market_cap_score: float = 0.0        # 流通市值 0-12分
    historical_performance_score: float = 0.0  # 历史股性 0-12分
    volatility_score: float = 0.0        # 波动率弹性 0-11分
    individual_flexibility: float = 0.0  # 个股弹性总分

    # 安全边际 满分30分
    earnings_trend_score: float = 0.0    # 业绩趋势 0-12分
    reduction_risk_score: float = 0.0    # 减持/解禁风险 0-9分
    beta_control_score: float = 0.0      # Beta控制 0-9分
    safety_margin: float = 0.0           # 安全边际总分

    total_score: float = 0.0             # 总分
    grade: Grade = Grade.THIRD           # 档位


@dataclass
class Phase1Result:
    """第一阶段输出结果"""
    stock: Stock
    track_obj: Track
    phase1_score: Phase1Score
    market_status: MarketStatus
    rotation_phase: RotationPhase
    core_logic: str = ""
    remark: str = ""


@dataclass
class MoatScore:
    """护城河评分"""
    pricing_power_score: float = 0.0     # 定价权/差异化壁垒 0-6分
    rd_ratio_score: float = 0.0          # 研发费用率 0-4分
    customer_concentration_score: float = 0.0  # 客户集中度 0-4分
    customer_loyalty_score: float = 0.0  # 客户续约率 0-3分
    profit_quality_score: float = 0.0    # 利润含金量 0-3分
    total_score: float = 0.0             # 总分
    level: MoatLevel = MoatLevel.WEAK


@dataclass
class VetoResult:
    """一票否决结果"""
    passed: bool = True
    triggered_item: str = ""             # 触发的否决项


@dataclass
class FinancialReportScore:
    """财报评分"""
    revenue_growth_score: float = 0.0    # 营收增速 0-8分
    profit_growth_score: float = 0.0     # 利润增速 0-8分
    earnings_trend_score: float = 0.0    # 业绩趋势 0-8分
    cash_quality_score: float = 0.0      # 盈利质量 0-8分
    roe_score: float = 0.0               # ROE 0-8分
    surprise_score: float = 0.0          # 季报超预期 0-10分
    institution_attitude_score: float = 0.0  # 机构态度 0-10分
    total_score: float = 0.0             # 总分


@dataclass
class ValuationResult:
    """估值结果"""
    method: ValuationMethod = ValuationMethod.PEG
    peg: Optional[float] = None
    pb_roe_premium: Optional[float] = None
    ps_ratio: Optional[float] = None
    conclusion: ValuationConclusion = ValuationConclusion.FAIR
    position_coefficient: float = 0.0    # 估值仓位系数
    historical_percentile: Optional[float] = None  # 历史分位点
    institution_holding_change: Optional[float] = None  # 机构持仓变化


@dataclass
class Phase2Result:
    """第二阶段输出结果"""
    stock: Stock
    phase1_result: Phase1Result
    moat_score: MoatScore
    veto_result: VetoResult
    financial_score: FinancialReportScore
    valuation: ValuationResult
    base_position: float = 0.0           # 建议基准仓位%
    final_position: float = 0.0          # 最终仓位%
    stop_loss: float = -7.0              # 止损位%
    time_stop: int = 12                  # 时间止损（周）
    trigger_condition: str = ""          # 触发条件
    final_decision: FinalDecision = FinalDecision.WATCH
    remark: str = ""
