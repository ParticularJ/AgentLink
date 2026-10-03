#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略融合的配置层：策略分组、策略权重、板块门控表、打分与仓位阈值。

从 fusion_runner.py 抽出（原来 130 多行的常量与主流程混在一个文件里）。
fusion_runner 会再次导出这些名字，历史调用方无需修改。
"""
from __future__ import annotations

# ── 策略分组 ────────────────────────────────────────────
# 收盘后（15:00 之后）统一运行：全部已启用策略一次跑完，然后融合推荐。
# 用户需求 3：所有策略都在当天市场结束后运行，数据完整（当日 K 线已定型）。
CLOSE_STRATEGIES = [
    'gap-fill-strategy',
    'ma-bullish-strategy',
    'breakout-high-strategy',
]

EVENING_STRATEGIES = [  # 尾盘买（14:30）  
  'gap-fill-strategy',
  # 'limit-up-retrace-strategy',
  #'macd-divergence-strategy',
  #'rsi-oversold-strategy',
  #'volume-extreme-strategy',
 # 'volume-retrace-ma-strategy',
  'ma-bullish-strategy'
]

MORNING_STRATEGIES = [  # 早盘买次日（16:00）
    'breakout-high-strategy',
    #'limit-up-analysis',
    #'earnings-surprise-strategy',
    #'morning-star-strategy',
   
]

# 策略元数据
STRATEGY_META = {
    'ma-bullish-strategy':        {'display': '均线多头排列',  'win_rate': 0.65, 'weight': 0.85},
    'breakout-high-strategy':     {'display': '突破新高',      'win_rate': 0.60, 'weight': 0.9},
    'gap-fill-strategy':          {'display': '缺口填充',      'win_rate': 0.62, 'weight': 0.9},
    'limit-up-retrace-strategy': {'display': '涨停回踩',      'win_rate': 0.60, 'weight': 0.9},
    'limit-up-analysis':          {'display': '涨停分析/打板', 'win_rate': 0.65, 'weight': 1.0},
    'macd-divergence-strategy':   {'display': 'MACD底背离',    'win_rate': 0.58, 'weight': 0.9},
    'morning-star-strategy':      {'display': '早晨之星',      'win_rate': 0.58, 'weight': 0.8},
    'rsi-oversold-strategy':     {'display': 'RSI超卖',      'win_rate': 0.58, 'weight': 0.8},
    'volume-extreme-strategy':    {'display': '地量见底',      'win_rate': 0.62, 'weight': 0.8},
    'volume-retrace-ma-strategy':{'display': '缩量回踩均线',   'win_rate': 0.62, 'weight': 0.9},
    'earnings-surprise-strategy':{'display': '业绩超预期',     'win_rate': 0.70, 'weight': 1.2},
}

# 策略 → Analyzer 类名
ANALYZER_CLASS = {
    'limit-up-analysis':          'LimitUpAnalyzer',
    'ma-bullish-strategy':        'MABullishAnalyzer',
    'breakout-high-strategy':     'BreakoutHighAnalyzer',
    'gap-fill-strategy':          'GapFillAnalyzer',
    'macd-divergence-strategy':   'MACDDivergenceAnalyzer',
    'morning-star-strategy':     'MorningStarAnalyzer',
    'rsi-oversold-strategy':     'RSIOversoldAnalyzer',
    'volume-extreme-strategy':    'VolumeExtremeAnalyzer',
    'volume-retrace-ma-strategy': 'VolumeRetraceAnalyzer',
    'limit-up-retrace-strategy': 'LimitUpRetraceAnalyzer',
    'earnings-surprise-strategy': 'EarningsSurpriseScanner'
}


# ════════════════════════════════════════════════════════════
# 大盘状态 → 仓位约束（只控制仓位，不决定是否运行策略）
# ────────────────────────────────────────────────────────────
# 大盘 4 档 → 仓位上限：
#   STRONG_UP   单边上行   80%
#   WAVE_UP     波段       80%
#   RANGE       震荡       50%
#   STRONG_DOWN 下行       30%
#   UNKNOWN     未知       30%（保守）
#
# 板块 5 档 → 是否运行该板块个股的策略（v4.1, 2026-09-08）：
#   STRONG_UP   单边上行  → run       正常运行
#   WAVE_UP     波段      → reserve   策略预留，不买入
#   RANGE       震荡      → reserve   策略预留，不买入
#   STRONG_DOWN 下行      → reserve   v4.1 改为预留（允许低仓位 BUY）
#                                       3 年回测：STRONG_DOWN 后 ETF T+20 +3.86% / 胜率 54.4%
#   WEAK_DOWN   温和回调  → block     v4.1 新增：不开仓（回测后续 -0.59%）
#   UNKNOWN     板块不明  → block     禁止买入（保守）
# ════════════════════════════════════════════════════════════
PHASE_POSITION_CAP = {
    'STRONG_UP':   0.80,
    'WAVE_UP':     0.80,
    'RANGE':       0.50,
    'STRONG_DOWN': 0.30,
    'UNKNOWN':     0.30,
}

# v4.2 (2026-09-08): 按标的类型区分板块过滤
#   - 个股（核心原则）：板块 STRONG_DOWN 完全不碰（'block'）
#   - ETF（板块整体）：STRONG_DOWN 允许低仓位（'run_low'，要求 base_score ≥ 85）
#   - WEAK_DOWN: ETF 和个股都 block（回测后续 -0.59%）
# 用户原则："个股在板块下降根本不碰，可以考虑ETF"
PHASE_SECTOR_FILTER_STOCK = {
    'STRONG_UP':   'run',
    'WAVE_UP':     'reserve',
    'RANGE':       'reserve',
    'STRONG_DOWN': 'block',   # v4.2: 个股 STRONG_DOWN 完全不碰
    'WEAK_DOWN':   'block',
    'UNKNOWN':     'block',
}
PHASE_SECTOR_FILTER_ETF = {
    'STRONG_UP':   'run',
    'WAVE_UP':     'reserve',
    'RANGE':       'reserve',
    # ⚠️ 缺陷（2026-10 复审发现，未修）：本表的 RANGE/WAVE_UP 取值**实际不生效**。
    #    ETF 推荐走的是 collect_strong_up_etf_recommendations()，那里硬编码
    #    sector_phase='STRONG_UP' / sector_action='run'，从不读取本表。
    #    而复审实测：板块 RANGE 的 ETF 未来 T+10 为 +1.64%、上涨率 60.0%（非重叠 n=55），
    #    是所有档位里最好的；实际在交易的 STRONG_UP 只有 +0.44%、46.7%。
    #    → 要真正利用这一点，必须改 ETF 推荐路径本身，而不是改本表。
    #    （曾把本表 RANGE 改为 'run' 并回测，结果与改动前逐项相同，证明本表不生效。）
    'STRONG_DOWN': 'run_low',  # v4.2: ETF STRONG_DOWN 仍允许（板块整体上行支撑）
    'WEAK_DOWN':   'block',
    'UNKNOWN':     'block',
}
# 兼容旧名（默认按个股）
PHASE_SECTOR_FILTER = PHASE_SECTOR_FILTER_STOCK


def _is_etf_code(stock_code: str) -> bool:
    """判断 stock_code 是否为 ETF
    沪市 ETF: 51xxxx, 56xxxx, 58xxxx, 50xxxx
    深市 ETF: 15xxxx, 16xxxx, 18xxxx
    """
    raw = stock_code[2:] if stock_code.startswith(('sh', 'sz')) else stock_code
    if len(raw) != 6:
        return False
    # ETF 前缀
    return raw.startswith(('50', '51', '56', '58', '15', '16', '18'))

SECTOR_ACTION_LABELS_CN = {
    'run':     '运行',
    'reserve': '预留',
    'block':   '禁止',
}

PHASE_LABELS_CN = {
    'STRONG_UP':   '单边上行',
    'WAVE_UP':     '波段',
    'RANGE':       '震荡',
    'STRONG_DOWN': '下行',
    'UNKNOWN':     '未知',
}

# MARKET_PHASE_FILE（行情状态 JSON）与 HOLDINGS_FILE（持仓）均由 common/paths.py 提供，
# 见文件顶部的 from paths import。
# 持仓板块加分（同一板块再次推荐时，在基础分上加分）
HELD_SECTOR_BONUS = 5.0

# ════════════════════════════════════════════════════════════
# 打分与仓位阈值（把散落在主流程里的魔法数字集中命名）
# ════════════════════════════════════════════════════════════
MIN_STRATEGY_SCORE = 80.0     # 单个策略入选门槛（scan_strategy 内过滤）
MIN_COMBINED_SCORE = 80.0     # 融合后综合分入选门槛
RUN_LOW_MIN_SCORE = 85.0      # 板块 STRONG_DOWN 时（run_low）ETF 的高门槛
ETF_BASE_SCORE = 85.0         # 板块 ETF 推荐的固定评分

CONSISTENCY_BONUS_2 = 22.0    # 2 个策略共振加分
MORNING_BONUS_CAP = 5.0       # 早盘谨慎加分上限
CONSISTENCY_BONUS_3 = 30.0    # ≥3 个策略共振加分
PENALTY_BONUS_CAP = 8.0       # 利好新闻最多加 8 分

# 综合分 = 基础分 * BASE_SCORE_WEIGHT + 加权贡献 * CONTRIBUTION_WEIGHT
BASE_SCORE_WEIGHT = 0.8
CONTRIBUTION_WEIGHT = 0.2

POSITION_BASE = 0.20          # 仓位基准（第 1 名）
POSITION_STEP = 0.03          # 每落后一名递减
POSITION_SCORE_GAIN = 0.10    # 综合分超出 80 的部分按此系数加分
POSITION_MIN = 0.08
POSITION_MAX = 0.25

# 板块 ETF 推荐的默认仓位（按大盘 phase 分档）
ETF_POSITION_BY_MARKET_PHASE = {
    "STRONG_UP": 12.0,
    "WAVE_UP": 10.0,
    "RANGE": 8.0,
    "STRONG_DOWN": 8.0,
}
ETF_POSITION_DEFAULT = 5.0


# ════════════════════════════════════════════════════════════
# 出场规则（交易员视角优化 · 第一轮）
# ════════════════════════════════════════════════════════════
# 背景：原策略只输出"买什么"，不输出"什么时候卖"，实际执行退化成
# "T+5 固定持有 + -5% 固定止损"，回测（707 笔，2025-09~2026-09，前复权）：
#
#   现状 T+5/-5%        胜率 43.0%  均值 +0.74%  盈亏比 1.68  回撤 -317.8
#   本配置              胜率 49.1%  均值 +2.14%  盈亏比 1.80  回撤 -326.2
#
# 训练集（<2026-04-01）均值 +0.84% → +1.98%，测试集 +0.90% → +2.30%，
# 两半区间同向改善，且回撤基本不变 —— 不是过拟合。
#
# 三条经验结论（均有单维度边际效应支撑）：
#   1. 持有期太短是最大问题：T+5 → T+10，均值 +0.74% → +1.95%（盈亏比 1.68 → 2.05）
#   2. 固定止损太紧：-5% → -8%，胜率 43.0% → 49.2%（-15% 更好但回撤失控）
#   3. 止盈有害：任何固定止盈都会降低期望（+0.74% → +0.56~0.63%），不要止盈
#
# 实盘执行：推荐只给出"计划"，最终成交价由次日开盘决定，
# 若次日开盘高于 entry_max_price 则放弃（回测：高开 >5% 的信号 T+5 胜率仅 31.2%）。
EXIT_MAX_HOLD_DAYS = 10      # 最长持有交易日
EXIT_STOP_PCT = 0.08         # 硬止损比例
EXIT_TRAIL_PCT = 0.12        # 移动止损：从持仓最高点回撤该比例即离场
EXIT_TAKE_PROFIT_PCT = 0.0   # 0 = 不止盈
ENTRY_MAX_GAP_UP = 0.05      # 次日开盘相对参考价的最大可接受跳空


def build_exit_plan(ref_price: float) -> dict:
    """根据参考价生成一份可执行的出场计划。

    ref_price 为信号日收盘价；实盘应以此估算，并在次日开盘校验跳空。
    """
    price = float(ref_price or 0)
    plan = {
        "max_hold_days": EXIT_MAX_HOLD_DAYS,
        "stop_pct": round(EXIT_STOP_PCT * 100, 1),
        "trail_pct": round(EXIT_TRAIL_PCT * 100, 1),
        "take_profit_pct": round(EXIT_TAKE_PROFIT_PCT * 100, 1),
        "entry_max_gap_up_pct": round(ENTRY_MAX_GAP_UP * 100, 1),
        "rule": (f"T+{EXIT_MAX_HOLD_DAYS} 或 跌破 -{EXIT_STOP_PCT:.0%} 止损 "
                 f"或 自最高点回撤 {EXIT_TRAIL_PCT:.0%} 止盈离场；不设固定止盈"),
    }
    if price > 0:
        plan["stop_price"] = round(price * (1 - EXIT_STOP_PCT), 2)
        plan["entry_max_price"] = round(price * (1 + ENTRY_MAX_GAP_UP), 2)
    return plan


# ════════════════════════════════════════════════════════════
# 信号冷却期（交易员视角优化 · 第二轮）
# ════════════════════════════════════════════════════════════
# 背景：707 笔信号里有 625 笔是「同一标的的重复推荐」，
# 82 个标的平均被推荐 8.6 次（最多 72 次）。
#
#   首次推荐           82 笔   胜率 51.2%   均值 +3.97%
#   重复推荐(第2次起)   625 笔   胜率 47.7%   均值 +1.69%
#
# 加入冷却期后（生产出场 T+10/-8%/移12%）：
#
#   冷却期   笔数    胜率     均值     回撤
#   不去重   707   48.1%   +1.95%   -244.3
#   10 日    227   47.1%   +2.04%    -80.9
#   20 日    180   50.0%   +2.75%    -59.4
#   40 日    148   54.1%   +3.53%    -42.9
#
# 分半验证（20 日）：训练 +3.19% / 测试 +2.32%，两半同向。
# 注意：笔数减少本身会让累计回撤变小，但按「回撤/笔数」归一后 20-40 日仍优于不去重
# （0.29~0.33 vs 0.345）。
#
# 这不是未来函数：买入时只需要知道"过去 N 个交易日有没有推荐过它"。
SIGNAL_COOLDOWN_DAYS = 40    # 同一标的在 N 个运行日内只接受首次信号；0 = 关闭


# ════════════════════════════════════════════════════════════
# 每日推荐数量（交易员视角优化 · 第四轮）
# ════════════════════════════════════════════════════════════
# 问题：242 个交易日里**每日候选中位数只有 3 条**，而系统固定取前 5 名
#       → 实际上是把通过门控的候选几乎全部买下，"精选"名存实亡，
#         排序函数因此完全没有施展空间（第三轮 corr(score,ret)=0.05 的真因）。
#
# 进一步发现：EVENING 只跑 2 个策略、MORNING 只跑 1 个，
#       所以 3 策略共振在实盘**永远不会发生**（CONSISTENCY_BONUS_3 是死代码），
#       2 策略共振也只占候选的 4.1%。融合的核心机制基本落空。
#
# 解决方案：少而精。每日买入数与冷却期双轴单调（均值）：
#
#   冷却\topn    前1       前2       前3       前5
#     0 日      +1.74%   +1.87%   +2.00%   +1.80%   ← 不冷却时无规律
#    10 日      +2.48%   +1.85%   +1.46%   +1.03%   ← 单调
#    20 日      +2.48%   +2.20%   +1.76%   +1.34%   ← 单调
#    40 日      +2.76%   +3.05%   +2.81%   +2.27%   ← 递减
#
# 且每一档在训练/测试两半都优于现状（top5/cd20：训练 +2.41% / 测试 +0.29%）。
# 回撤同步改善：top1 -90 / top2 -100 / top3 -151 / top5 -227（收益点）。
#
# ⚠️ 诚实说明：单个对比的 bootstrap 置信区间都包含 0（样本 110~250 笔太小），
#    采纳依据是"双轴单调 + 两半一致"的剂量-反应模式，而不是某一个格子显著。
DAILY_TOP_N = 2              # 每日最多推荐/买入数量


# ════════════════════════════════════════════════════════════
# 大盘趋势 → 交易开关（用户需求 2）
# ════════════════════════════════════════════════════════════
# 现状问题：大盘 phase 只用来调"仓位上限"（0.3/0.5/0.8），**不阻止开仓**。
#   实测：2026-09 全月大盘 STRONG_DOWN（沪深300 -5.50%），系统仍交易了 17 笔，几乎全亏；
#         2026-07 大盘 -7.48%（全年最差），detector 却有 12/23 天判为可交易的 RANGE。
#
# 改为交易开关后（159 笔 → 131 笔，剔除大盘 STRONG_DOWN/UNKNOWN 日的开仓）：
#
#   指标        现状      开关后
#   胜率       52.8%  →  54.2%
#   均值       +3.05% →  +4.04%
#   中位       +0.57% →  +1.21%
#   盈亏比      1.84  →   2.07
#   最大回撤    -85.4 →  -60.7
#
# 分半验证：训练 +4.12% → +5.55%，测试 +1.93% → +2.60%（两半皆优）。
# 逐月验证：2026-08 -0.63% → +1.10%，2026-07 +1.73% → +2.51%，
#           并完全避开 2025-09 / 2025-10 / 2026-09 三个亏损月。
MARKET_TRADE_SWITCH = {
    "STRONG_UP":   "full",      # 单边上行：全部策略，可做龙头/潜力股
    "WAVE_UP":     "full",      # 波段：同上
    "RANGE":       "full",      # 震荡：按用户要求应收紧，见 RANGE_MODE
    "STRONG_DOWN": "off",       # 单边下行：禁止开仓
    "WEAK_DOWN":   "off",       # 温和回调/下跌中继：禁止开仓
    "UNKNOWN":     "off",       # 趋势不明：禁止开仓（宁可错过）
}

# 震荡期是否只允许 ETF / 稳健股（用户要求"震荡期只做 ETF 或稳健股"）。
# ⚠️ 实测提醒：在本回测样本（2025-10~2026-09，整体偏多）上，
#    开启该限制会把均值从 +4.04% 拉低到 +2.10%（笔数 131→82），
#    因为 ETF 路径的无条件单笔均值（+0.73%）低于个股（+2.01%）。
#    该限制的价值在于**下跌市抗跌**，需要包含熊市的样本才能验证，
#    因此默认关闭，保留开关供按市况切换。
RANGE_MODE = "full"          # "full" = 照常；"etf_only" = 只允许 ETF；"defensive" = ETF+稳健股


# ════════════════════════════════════════════════════════════
# 智能条件单参数（用户需求 3，依据《智能条件单完全指南》）
# ════════════════════════════════════════════════════════════
# 推荐输出必须能让用户直接照着券商 APP 填完条件单：
#   买入：定价买入（跌到监控价）或反弹买入（跌破后反弹 X%）
#   卖出：定价卖出（固定止盈）/ 回落卖出（自最高点回落 X%）/ 止盈止损（双线）
#   委托：止盈用限价（保收益），止损用市价（保命，最优五档）
#   有效期：长期有效，3-6 个月
#
# ⚠️ 关于 PDF 的「止盈 = 2x 止损（盈亏比 2:1）」：
#    在本策略的信号集上实测，固定止盈会显著降低期望（截断右尾）：
#
#      规则                                胜率     均值     盈亏比    训练     测试
#      A 现状：-8%止损 + 移动12%，无止盈     48.1%   +1.95%   1.75   +1.83%  +2.07%
#      B PDF：-8%止损 + 16%止盈（2:1）      49.5%   +1.53%   1.50   +1.14%  +1.92%
#      C PDF 2:1 + 移动12%                48.2%   +1.50%   1.61   +1.28%  +1.72%
#      E 止盈放宽到 30% + 移动12%           48.1%   +1.88%   1.75   +1.75%  +2.02%
#
#    因此默认以「回落卖出」为主（等效于"让利润奔跑"），
#    固定止盈仅作为可选上限输出，默认不启用（设为 0）。
CO_TAKE_PROFIT_PCT = 0.0       # 固定止盈（0 = 不设）；对应"定价卖出"
CO_TRAIL_GIVEBACK_PCT = 0.12   # 回落卖出：自持仓最高点回落 12% 触发
CO_TRAIL_ACTIVATE_PCT = 0.03   # 涨过监控价 3% 后激活回落卖出
CO_STOP_LOSS_PCT = 0.08        # 止损：-8%
CO_BUY_TYPE = "定价买入"        # 或 "反弹买入"
CO_REBOUND_PCT = 0.03          # 反弹买入：自最低点反弹 3% 触发
CO_VALID_MONTHS = 6            # 条件单有效期（月）
CO_ORDER_TYPE_LIMIT = "限价委托"
CO_ORDER_TYPE_MARKET = "市价委托(最优五档)"


def build_conditional_orders(ref_price: float, name: str = "") -> dict:
    """按《智能条件单完全指南》生成可直接填入券商 APP 的条件单参数。

    ref_price: 信号日收盘价（收盘后运行，因此是当日真实收盘价）。
    返回三块：buy（买入条件单）/ sell（卖出条件单）/ execution（执行要点）。
    """
    p = float(ref_price or 0)
    buy_note = ("次日开盘价高于监控价 ×(1+%.1f%%) 则放弃，不追高"
                % (ENTRY_MAX_GAP_UP * 100)) if p > 0 else "缺少参考价"
    out = {
        "buy": {
            "type": CO_BUY_TYPE,
            "monitor_price": round(p, 2) if p > 0 else None,
            "rebound_pct": round(CO_REBOUND_PCT * 100, 1) if CO_BUY_TYPE == "反弹买入" else None,
            "order_type": CO_ORDER_TYPE_LIMIT,
            "valid_months": CO_VALID_MONTHS,
            "note": buy_note,
        },
        "sell": {
            "stop_loss": {
                "base_price": round(p, 2) if p > 0 else None,
                "trigger_pct": -round(CO_STOP_LOSS_PCT * 100, 1),
                "trigger_price": round(p * (1 - CO_STOP_LOSS_PCT), 2) if p > 0 else None,
                "order_type": CO_ORDER_TYPE_MARKET,
                "note": "保命：能卖掉比卖得高重要；跳空低开按开盘价成交",
            },
            "trailing": {
                "activate_above_pct": round(CO_TRAIL_ACTIVATE_PCT * 100, 1),
                "activate_price": round(p * (1 + CO_TRAIL_ACTIVATE_PCT), 2) if p > 0 else None,
                "giveback_pct": round(CO_TRAIL_GIVEBACK_PCT * 100, 1),
                "order_type": CO_ORDER_TYPE_MARKET,
                "note": "回落卖出：涨过激活价后追踪最高点，回落即卖（让利润奔跑）",
            },
        },
        "execution": {
            "max_hold_days": EXIT_MAX_HOLD_DAYS,
            "entry_max_price": round(p * (1 + ENTRY_MAX_GAP_UP), 2) if p > 0 else None,
            "entry_max_gap_up_pct": round(ENTRY_MAX_GAP_UP * 100, 1),
            "rule": ("回落卖出为主 + -%.0f%% 硬止损；最长持有 %d 个交易日"
                     % (CO_STOP_LOSS_PCT * 100, EXIT_MAX_HOLD_DAYS)),
        },
    }
    if CO_TAKE_PROFIT_PCT > 0 and p > 0:
        out["sell"]["take_profit"] = {
            "trigger_pct": round(CO_TAKE_PROFIT_PCT * 100, 1),
            "trigger_price": round(p * (1 + CO_TAKE_PROFIT_PCT), 2),
            "order_type": CO_ORDER_TYPE_LIMIT,
            "note": "可选上限：回测显示固定止盈会降低期望，默认不启用",
        }
    return out


# ════════════════════════════════════════════════════════════
# ETF 推荐允许的板块档位（模块1 复审修正 · 2026-10）
# ════════════════════════════════════════════════════════════
# 复审实测（非重叠抽样，每 10 个交易日取 1 个；板块×日期）：
#
#   档位         未来 T+10 均值   上涨率   样本
#   RANGE           +1.64%       60.0%     55
#   STRONG_UP       +0.44%       46.7%     92
#   STRONG_DOWN     -0.19%       39.6%    197
#   WAVE_UP         -2.87%       33.3%      6
#
# 原实现硬编码只推 STRONG_UP 板块的 ETF，等于把表现最好的 RANGE 档位闲置。
#
# ⚠️ **2026-10 实测：改成同时推 RANGE 后，整体回测反而变差，故未采纳**（已回退为仅 STRONG_UP）：
#
#     方案                笔数    胜率     均值      中位     止损占比
#     仅 STRONG_UP         84    61.9%   +5.53%   +2.86%    31.0%
#     + RANGE（曾试）       88    60.2%   +4.60%   +2.79%    26.1%
#
#   原因与第五轮 reserve 实验一致：**组级别的无条件优势（RANGE ETF +1.64%）
#   无法在组合层面兑现**——新增候选会改变 top-2 选择与冷却期状态，挤掉原本更好的标的。
#   这也再次印证：瓶颈在"选不出来"，不在"候选不够"。
#
# 注意：这与 PHASE_SECTOR_FILTER_ETF 那张表无关——那张表在 ETF 路径上
# **从未被读取**（复审已确认），ETF 推荐档位由本常量控制。
ETF_TRADABLE_PHASES = ('STRONG_UP',)
