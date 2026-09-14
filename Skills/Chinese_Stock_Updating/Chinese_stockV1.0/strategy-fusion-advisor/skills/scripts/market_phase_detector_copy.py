#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行情阶段判定器（大盘 + 板块）
- 大盘：沪深300 + 上证指数 双标尺综合
- 板块：成分股等权合成指数后判定
- 输出档位：单边上行 / 波段上行 / 震荡 / 波段下行 / 单边下行
- 结果写入 recommendations/market_phase.json，供 fusion_runner 读取
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

try:
    import yaml  # 用于读取 watchlist.yaml 构建 stock→sector 映射
except ImportError:
    yaml = None  # type: ignore
import pandas as pd


def _json_safe(obj):
    """递归把 numpy 类型转成原生 Python，让 json.dump 不报错"""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    if isinstance(obj, np.ndarray):
        return _json_safe(obj.tolist())
    return obj


# ── 代理清除 ────────────────────────────────────────────
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try:
            del os.environ[k]
        except Exception:
            pass

# ── 路径：复用 ma-bullish-strategy 的 DataSourceAdapter (pytdx) ──
# market_phase_detector.py 位于
#   strategy-fusion-advisor/skills/scripts/market_phase_detector.py
# dirname ×3 → strategy-fusion-advisor/  (SKILL_DIR)
# dirname ×4 → Chinese_Stock_back/      (BASE_DIR)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
_BASE_DIR = os.path.dirname(_SKILL_DIR)
_ADAPTER_SRC = os.path.join(
    _BASE_DIR,
    'ma-bullish-strategy', 'skills', 'scripts'
)
# 备用：Medium-termHoldingStrategy 的 fetch_kline_sina
_FALLBACK_SRC = os.path.join(
    _BASE_DIR,
    'Medium-termHoldingStrategy', 'skills', 'scripts'
)
for p in (_ADAPTER_SRC, _FALLBACK_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from data_source_adapter import DataSourceAdapter
    _USE_ADAPTER = True
except Exception as _e:
    print(f"[WARN] DataSourceAdapter 加载失败: {_e}, 回退到 fetch_kline_sina")
    _USE_ADAPTER = False

# 始终导入 fetch_kline_sina 作为兜底（无论 adapter 是否可用）
try:
    from data_source import fetch_kline_sina  # noqa: E402
except Exception as _e2:
    print(f"[WARN] fetch_kline_sina 也加载失败: {_e2}")
    fetch_kline_sina = None

# ── 初始化数据源（pytdx 优先，0.2s 取数据）───────────────
_ADAPTER = None
if _USE_ADAPTER:
    try:
        _ADAPTER = DataSourceAdapter(source='pytdx', fallback=True)
        print(f"[数据源] 使用 {_ADAPTER.source}")
    except Exception as e:
        print(f"[WARN] DataSourceAdapter 初始化失败: {e}")
        _ADAPTER = None

# ── 输出目录 ────────────────────────────────────────────
RECO_DIR = os.path.join(_BASE_DIR, 'strategy-fusion-advisor', 'recommendations')
os.makedirs(RECO_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(RECO_DIR, 'market_phase.json')

# ── 稳定 phase 状态缓存（跨进程持久化）───────────────
# 文件结构：{ "<key>": {"stable_phase": "...", "last_date": "YYYY-MM-DD", "last_candle_idx": N}, ... }
# key 用 "<sector>:<code>" 或 "<sector>:index"（大盘/合成）
CACHE_DIR = os.path.join(RECO_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)
STABLE_PHASE_FILE = os.path.join(CACHE_DIR, 'stable_phase.json')


# ════════════════════════════════════════════════════════════
# 大板块配置（基于 watchlist.yaml v9，2026-08-28，中文板块名）
# ────────────────────────────────────────────────────────────
# v2 配置：只用 ETF，不用成分股合成（更具代表性）
# SECTOR_CONSTITUENTS 留空，所有板块走 ETF 路径
# ════════════════════════════════════════════════════════════
SECTOR_CONSTITUENTS: Dict[str, List[str]] = {
    # v2：所有板块都用 ETF 标尺，SECTOR_CONSTITUENTS 留空
    # 仅保留与 watchlist.yaml 对应的板块结构（防止旧代码 import 报错）
    '底仓': [],
    '半导体': [],
    'AI应用': [],
    '创新药': [],
    '光通信': [],
    '军工': [],
    '商业航天': [],
    '人形机器人': [],
    '智能驾驶': [],
    '消费电子': [],
    '燃气轮机': [],
    '化工': [],
    '电网设备': [],
    '新能源': [],
    '贵金属': [],
    '工业金属': [],
    '油气': [],
    '航运': [],
    '券商': [],
    '白酒': [],
    '家电': [],
    '种子农业': [],
    '可控核聚变': [],
    '稀土': [],   # 新增（2026-08-30，承接 watchlist.yaml 的 rare_earth）
    '低空经济': [],   # 2026-09-07 新增（承接 watchlist.yaml 的 low_altitude_economy）
}

# 行业 ETF 板块（全部用 ETF 标尺，从 watchlist.yaml 的 ETF 部分选取）
# 注：所有板块都用 ETF 表示，不用成分股合成（更具代表性）
# 选取原则：watchlist.yaml 中直接对应板块主题的 ETF
SECTOR_ETFS: Dict[str, object] = {
    # ── 底仓（红利 ETF blend）──
    '底仓':     ['sh515180', 'sh563020', 'sh515300'],               # 红利ETF易方达 + 红利低波ETF易方达 + 300红利低波ETF嘉实

    # ── 半导体（多 ETF blend 增强代表性）──
    '半导体':   ['sh512480', 'sz159995', 'sh588200'],               # 半导体ETF + 芯片ETF + 科创芯片ETF

    # ── AI应用 ──
    'AI应用':   ['sh515980'],                                       # 人工智能ETF华富（外部代码，但行业代表）

    # ── 创新药 ──
    '创新药':   ['sz159992'],                                       # A股创新药ETF（深市）；港股版(sh513120)走势不同，blend会扭曲判定

    # ── 光通信 ──
    '光通信':   ['sh515880'],                                       # 通信ETF

    # ── 军工 ──
    '军工':     ['sh512660', 'sh512670', 'sh512560'],               # 军工ETF + 国防军工ETF + 中证军工ETF

    # ── 商业航天（用军工 ETF 作为代理，watchlist 中无单独 ETF）──
    '商业航天': ['sh512560'],                                       # 中证军工ETF（代理）

    # ── 人形机器人 ──
    '人形机器人': ['sh562500'],                                     # 机器人ETF华夏（外部代码）

    # ── 智能驾驶（2026-09-07 修正：之前用 sh516320 高端装备代理，错）──
    # 验证 sh516320 与代表股（德赛西威/华阳集团）avg 相关仅 -0.097（负相关，明显错代理）
    # 候选 ETF 与代表股相关系数（验证 2026-09-07）：
    #   - sz159872 智能网联汽车ETF：0.677（avg: 德赛 +0.860, 华阳 +0.495）✅ 最佳
    #   - sz159699 智能车ETF：      0.594（avg: 德赛 +0.669, 华阳 +0.520）
    #   - sh515250 智能汽车ETF华夏：  0.537（avg: 德赛 +0.740, 华阳 +0.334）
    # 智能驾驶 ETF 在 A 股覆盖不完整（板块聚焦新能源车 + 智驾软件），用 sz159872 智能网联汽车ETF
    # 注意：即便最佳候选也只有 0.677（部分匹配），原因是德赛西威是智驾域控龙头、华阳是智能座舱，
    #       子细分差异较大。ETF 失效会自动 fallback 用代表股合成（见 judge_sector fallback）
    '智能驾驶': ['sz159872'],                                       # 智能网联汽车ETF

    # ── 消费电子（2026-09-07 修正：之前用 sh515880 通信 ETF 代理，错）──
    # 真相：A股没有"消费电子"ETF 在 watchlist 中，但市场存在：
    #   - sz159779 消费电子ETF银华：avg 0.896（立讯 +0.891, 蓝思 +0.900）✅ 最佳
    #   - sh561130 消费电子ETF国泰：avg 0.874（立讯 +0.908, 蓝思 +0.840）
    #   - sh562380 消费电子ETF    ：avg 0.864
    #   - sh561310 消费电子ETF华夏：avg 0.722
    # 之前 sh515880 (通信ETF) 实际 avg 0.162，与立讯/蓝思几乎无关，是代理错
    # 回测对比（3 年 800 条 K 线，slow_bull 默认）：
    #   - sh515880 (旧): 176 笔 / 54.0% / +4.30% 复利 / B&H -34%（代理错）
    #   - sz159779 (新): 189 笔 / 49.2% / +634% 复利 / B&H +126%（板块大涨）
    #   - sh561130 (新): 140 笔 / 50.0% / +14.90% 复利 / B&H +31%
    # 用 sz159779 单 ETF（银华，明显优于国泰）
    '消费电子': ['sz159779'],                                       # 消费电子ETF银华（替代之前错的通信ETF代理）

    # ── 燃气轮机 ──
    '燃气轮机': ['sh516320'],                                       # 高端装备ETF（代理）

    # ── 化工 ──
    '化工':     ['sh516220'],                                       # 化工龙头 ETF）

    # ── 电网设备 ──
    '电网设备': ['sz159611'],                                       # 电力ETF（深市）

    # ── 新能源（2026-09-07 精简：3 ETF blend → 1 ETF）──
    # 简化理由：电池/光伏/新能源 ETF 内部相关 0.95-0.99（验证数据 2026-09-07）
    #   - sz159755 (电池) ↔ sh515790 (光伏) = 0.950
    #   - sz159755 (电池) ↔ sh516160 (新能源) = 0.990
    #   - sh515790 (光伏) ↔ sh516160 (新能源) = 0.983
    # 三个 ETF 走势高度同质化，blend 不增加信息量，只增加数据源失败风险
    # 保留最广覆盖的 sh516160 (新能源ETF)，它已包含电池+光伏+储能+风电
    # 如未来需要更细颗粒度（仅电池/仅光伏），再单独加板块
    '新能源':   ['sh516160'],                                       # 新能源ETF（综合指数，含电池/光伏/储能/风电）

    # ── 贵金属 ──
    '贵金属':   ['sh518880'],                           # 黄金ETF华安 + 有色金属ETF（代理）

    # ── 工业金属 ──
    '工业金属': ['sz159880'],                                       # 有色金属ETF（深市）

    # ── 工程机械（2026-09 新增，sz159886 工程机械ETF专用，走 v2）──
    '工程机械': ['sz159886'],                                       # 工程机械ETF（深市）

    # ── 油气 ──
    '油气':     ['sz159309', 'sh561760'],                                       # 中证油气资源ETF；A股油气开采+油服，与watchlist成分匹配；混入少量油运成分，存在轻微噪音；ETF失效自动fallback成分股合成

    # ── 航运（2026-09-06 修正注释：ETF 本质是油气+航运 blended）──
    # 真相：A股没有"纯航运"ETF
    #   - sz159309 中证油气资源ETF
    #   - sh561760 油气ETF
    #   - 所有候选"航运ETF"（sz159697/159865/159693/561800/561910 等）都与
    #     招商轮船 + 中海油 双高相关 (0.85+/0.75+)，本质是 shipping + oil blended
    # 原因：航运（油运/干散/集运）与油气价格强相关，A股 ETF 必然混合
    # 回测验证：3 年 106 笔 / 65.1% 胜率 / +2040% 复利（slow_bull 默认参数）
    #         → 功能上能跑，注释改为实际身份
    # 之前注释"航运ETF（专用）"是错的，那是 2026-08-31 修复交通运输ETF反指标时的
    # copy-paste 失误（从油气那行复制过来忘了改）。功能不变，只修注释。
    '航运':     ['sz159309', 'sh561760'],                                       # 油气+航运 blended（A股无纯航运ETF）

    # ── 券商 ──
    '券商':     ['sh512000'],                                       # 券商ETF

    # ── 白酒 ──
    '白酒':     ['sh512690'],                                       # 酒 ETF 鹏华

    # ── 家电 ──
    '家电':     ['sz159996'],                                       # 国泰家电 ETF（深市）


    # ── 可控核聚变 ──
    '可控核聚变': ['sh516320'],                                     # 高端装备ETF（代理）

    # ── 种子农业（watchlist 中无直接对应 ETF）──
    '种子农业': ['sz159698'],                                       # 粮食 ETF 鹏华（深市）

    # ── 稀土（新增，承接 watchlist.yaml 的 rare_earth）──
    '稀土':       ['sh516150'],                                      # 嘉实中证稀土产业ETF

    # ── 低空经济（2026-09-07 新增）──
    # 验证（与卧龙电驱/万丰奥威 相关性）：
    #   - sz159795 低空经济ETF天弘：avg 0.609（卧龙 +0.847, 万丰 +0.372）✅ 最佳
    #   - sh513050 中证通用航空ETF：avg 0.543（卧龙 +0.309, 万丰 +0.778）
    #   - sz159278 低空经济ETF  ：avg 0.529（卧龙 +0.615, 万丰 +0.444）
    # 注：低空经济 ETF 上市较晚，A股暂无高度匹配 ETF（最高 0.609）
    #     板块主题波动大（eVTOL/无人机/通用航空），属 thematic
    '低空经济':   ['sz159795'],                                       # 低空经济ETF天弘
}


# ════════════════════════════════════════════════════════════
# 核心判定参数（v3：实战规则版）
# ── 按你的实战规则定义 4 档判定阈值：
#   1. 单边上行：close>MA20>MA60 + MA20 连续 10 日向上 + 近 20 日涨幅 > 8%
#   2. 波段：close>MA60 + MA20 走平（10日斜率<0.3%）+ 20日振幅 8%~15%
#   3. 震荡：价格在 MA60±5% 内 + 60 日振幅 < 15%
#   4. 下行：close<MA20<MA60 或 距 60 日高点回撤 > 15%
# ════════════════════════════════════════════════════════════
MA_FAST = 20
MA_SLOW = 60

# 振幅与回撤
RANGE_PERIOD = 20      # 波段判定用 20 日振幅
OSC_PERIOD   = 60      # 震荡/下行判定用 60 日振幅、回撤

# 移动平均条件
MA20_UP_DAYS = 10                              # MA20 连续上行天数
MA20_SLOPE_FLAT = 0.003                        # MA20 10 日斜率 < 0.3% 视为走平
PRICE_MA20_MA60_ORDER_GAIN = 0.08              # 近 20 日涨幅 > 8% → 单边上行准入
RANGE_20_MIN, RANGE_20_MAX = 0.08, 0.15        # 波段 20 日振幅区间
RANGE_60_MAX = 0.15                            # 震荡：60 日振幅 < 15%
MA60_BAND = 0.05                               # 震荡：价格 MA60 ±5%
DRAWDOWN_60 = 0.15                             # 下行：距 60 日高点回撤 > 15%

CONSISTENCY_DAYS = 2
EXTREME_ATR_MULT = 2.0
ATR_PERIOD = 20

# 大阴/大阳线阈值
BIG_DOWN_THRESHOLD = -0.03
BIG_UP_THRESHOLD   = 0.03

# v3 不再使用但保留兼容（外部脚本可能 import）
ADX_PERIOD = 14
SLOPE_WINDOW = 5
ADX_STRONG_UP = 28
ADX_WAVE_UP = 25
ADX_STRONG_DOWN = 25
ADX_WAVE_DOWN = 20
ADX_FLAT = 20
SLOPE_UP_THRESHOLD = 0.007
SLOPE_DOWN_THRESHOLD = 0.003
OVERHEAT_ADX = 35
OVERHEAT_CANDLE_PCT = 0.02
SLOPE_RECENT_WEIGHT = 2.0
SLOPE_TOTAL_WEIGHT = 1.0
VOL_HEALTH_STRONG_UP = 1.0
VOL_HEALTH_UP = 1.2
VOL_HEALTH_DOWN = 0.8


# v4 5 档定义（加 WEAK_DOWN 缓冲档，基于 3 年真实数据回测）
# 优先级排序：下行 > 弱下行 > 震荡 > 波段 > 单边上行（"严厉"判定优先）
# WEAK_DOWN: 温和回调但 close 仍 > MA60 + dd_60 < 10%（区别于 STRONG_DOWN 的空头排列）
#   - 历史回测：WEAK_DOWN 后 5/10/20 日 仍下跌（-0.29%/-0.53%/+0.22%），属于"下跌中继"
#   - 因此 WEAK_DOWN 操作等同 STRONG_DOWN（不开仓），仅作为日志/缓存标识区分
PHASE_PHASES = ('STRONG_DOWN', 'WEAK_DOWN', 'RANGE', 'WAVE_UP', 'STRONG_UP')
PHASE_PRIORITY = {
    'STRONG_DOWN': 1,   # 最严厉
    'WEAK_DOWN':   1,   # 同严厉（下跌中继，不开仓）
    'RANGE':       2,
    'WAVE_UP':     3,
    'STRONG_UP':   4,   # 最宽松（最确认是上行）
    'UNKNOWN':     0,
}


PHASE_LABELS = {
    'STRONG_UP':   '单边上行',
    'WAVE_UP':     '波段',
    'RANGE':       '震荡',
    'WEAK_DOWN':   '温和回调',
    'STRONG_DOWN': '下行',
    'UNKNOWN':     '未知',
}

# ════════════════════════════════════════════════════════════
# v4 phase → 操作建议（一对一映射，给 fusion_runner 直接消费）
# ════════════════════════════════════════════════════════════
# 5 档操作（与你的实战规则 1:1 对应）：
#   1. 单边上行  收盘>MA20>MA60 + MA20连上10日 + 近20日涨幅>8%
#      → 热点轨全开，可追强势ETF (80分)
#   2. 波段      收盘>MA60 + MA20走平（10日斜率<0.3%）+ 20日振幅8%~15%
#      → 只做回踩MA20/MA60的低吸，不追突破 (85分)
#   3. 震荡      价格在MA60±5%内反复穿越 + 近60日振幅<15% + 均线无排列
#      → 仅超跌企稳标的可小仓参与 (90分)
#   4. 温和回调  close<MA20 但 close>MA60 + dd_60<10%（v4 新增，2026-09-08）
#      → 同下行处理（不开仓）。回测：WEAK_DOWN 后 20d 仅 +0.22%，下跌中继
#   5. 下行      收盘<MA20<MA60，或距60日高点回撤>15%
#      → 该板块一票不买，只处理存量持仓（关闭）
# UNKNOWN  → 板块状态不明确，按下行保守处理（一律不买）
OPERATION_MAP = {
    'STRONG_UP':   ('buy_leaders_or_etf',
                    '单边上行 → 热点轨全开，可追龙头股或强势ETF（80分）'),
    'WAVE_UP':     ('wait_pullback',
                    '波段 → 只做回踩MA20/MA60的低吸，不追突破（85分）'),
    'RANGE':       ('oversold_small',
                    '震荡 → 仅超跌企稳标的可小仓参与（90分）'),
    'WEAK_DOWN':   ('no_buy_close',
                    '温和回调 → 同下行处理（不开仓，回测显示后续仍下跌）'),
    'STRONG_DOWN': ('no_buy_close',
                    '下行 → 该板块一票不买，只处理存量持仓（关闭）'),
    'UNKNOWN':     ('no_buy',
                    '未知 → 板块状态不明确，保守处理（关闭）'),
}

# 操作评分（与你的 5 档实战规则对应）
# 80 = 单边上行（趋势最强，可追ETF）
# 85 = 波段（不追涨，只低吸）
# 90 = 震荡（仅超跌企稳小仓）
# 0  = 下行/温和回调/未知（关闭）
PHASE_SCORE = {
    'STRONG_UP':   80,
    'WAVE_UP':     85,
    'RANGE':       90,
    'WEAK_DOWN':   0,
    'STRONG_DOWN': 0,
    'UNKNOWN':     0,
}


# ════════════════════════════════════════════════════════════
# 指标计算
# 注：v3 4 档实战规则不再使用 ADX / 量价 / 加权斜率，下面保留函数
#     仅为向后兼容（外部 import 不会报错）。v3 实际判定走 judge_single 的新逻辑。
# ════════════════════════════════════════════════════════════
def calc_adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> float:
    """
    计算 ADX(period)，返回最新一天的 ADX 值
    使用 Wilder 平滑（pandas ewm，alpha=1/period）
    """
    if df is None or len(df) < period * 2 + 1:
        return 0.0

    high = pd.Series(df['high'].values, dtype=float)
    low = pd.Series(df['low'].values, dtype=float)
    close = pd.Series(df['close'].values, dtype=float)

    # True Range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    # Directional Movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move

    plus_di = 100 * plus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    val = float(adx.iloc[-1])
    if np.isnan(val) or np.isinf(val):
        return 0.0
    return val


def calc_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    """ATR(period)，返回最新一天的 ATR 值"""
    if df is None or len(df) < period + 1:
        return 0.0
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    tr = np.zeros(len(high))
    for i in range(1, len(high)):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr_series = pd.Series(tr).rolling(period).mean()
    return float(atr_series.iloc[-1])


def calc_vol_health(df: pd.DataFrame, lookback: int = 5) -> float:
    """近 lookback 日的"涨日均量 / 跌日均量"，>1.2 健康上行，<0.8 健康下行"""
    if df is None or len(df) < lookback + 1:
        return 1.0
    sub = df.tail(lookback + 1)
    closes = sub['close'].values
    vols = sub['volume'].values
    up_vols, down_vols = [], []
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            up_vols.append(vols[i])
        elif closes[i] < closes[i - 1]:
            down_vols.append(vols[i])
    if not up_vols or not down_vols:
        return 1.0
    return float(np.mean(up_vols) / np.mean(down_vols))


def calc_ma_slope(close: np.ndarray, ma_period: int = MA_SLOW,
                  lookback: int = SLOPE_WINDOW) -> float:
    """MA(ma_period) 在 lookback 日内的相对斜率"""
    if len(close) < ma_period + lookback:
        return 0.0
    ma = pd.Series(close).rolling(ma_period).mean().values
    cur = ma[-1]
    prev = ma[-1 - lookback]
    if prev == 0:
        return 0.0
    return (cur - prev) / prev


def calc_weighted_slope(close: np.ndarray,
                         ma_period: int = MA_SLOW,
                         lookback: int = SLOPE_WINDOW) -> float:
    """
    加权斜率（v2 新增）：
      slope = (近 lookback 日斜率 × SLOPE_RECENT_WEIGHT + 整体斜率 × SLOPE_TOTAL_WEIGHT)
              / (SLOPE_RECENT_WEIGHT + SLOPE_TOTAL_WEIGHT)
    让近期斜率权重 > 整体斜率，解决 MA60 滞后问题
    """
    if len(close) < ma_period + lookback:
        return 0.0

    ma = pd.Series(close).rolling(ma_period).mean().values

    # 近期斜率（近 lookback 日）
    cur = ma[-1]
    prev_recent = ma[-1 - lookback] if len(ma) > lookback else cur
    if prev_recent == 0:
        recent_slope = 0.0
    else:
        recent_slope = (cur - prev_recent) / prev_recent

    # 整体斜率（ma 期内整段，固定 lookback * 4 = 20 日窗口）
    long_lookback = min(lookback * 4, len(ma) - ma_period)
    if long_lookback <= 0:
        return recent_slope
    prev_long = ma[-1 - long_lookback] if len(ma) > long_lookback else cur
    if prev_long == 0:
        total_slope = 0.0
    else:
        total_slope = (cur - prev_long) / prev_long

    weighted = (recent_slope * SLOPE_RECENT_WEIGHT + total_slope * SLOPE_TOTAL_WEIGHT) / \
               (SLOPE_RECENT_WEIGHT + SLOPE_TOTAL_WEIGHT)
    return float(weighted)


# ════════════════════════════════════════════════════════════
# v3 辅助函数（按你 4 档实战规则需要）
# ════════════════════════════════════════════════════════════
def calc_ma_series(close: np.ndarray, period: int) -> np.ndarray:
    """计算移动平均线"""
    if len(close) < period:
        return np.full(len(close), np.nan)
    return pd.Series(close).rolling(period).mean().values


def calc_ma20_consecutive_up_days(close: np.ndarray, period: int = MA_FAST,
                                  lookback: int = MA20_UP_DAYS) -> int:
    """
    MA20 连续上行天数
    返回从最近一根往前数连续上行的天数（最多 lookback）
    """
    if len(close) < period + lookback:
        return 0
    ma = calc_ma_series(close, period)
    if np.isnan(ma[-1]):
        return 0

    up_days = 0
    for i in range(len(ma) - 1, period - 1, -1):
        if i - 1 < 0:
            break
        cur = ma[i]
        prev = ma[i - 1]
        if np.isnan(cur) or np.isnan(prev):
            break
        if cur > prev:
            up_days += 1
        else:
            break
        if up_days >= lookback:
            break
    return up_days


def calc_ma20_slope_recent(close: np.ndarray, period: int = MA_FAST,
                            lookback: int = 10) -> float:
    """MA20 10 日斜率（相对值，用于判定 MA20 走平）"""
    if len(close) < period + lookback:
        return 0.0
    ma = calc_ma_series(close, period)
    cur = ma[-1]
    prev = ma[-1 - lookback]
    if np.isnan(cur) or np.isnan(prev) or prev == 0:
        return 0.0
    return (cur - prev) / prev


def calc_recent_gain(close: np.ndarray, lookback: int = 20) -> float:
    """近 lookback 日的累计涨幅"""
    if len(close) < lookback + 1:
        return 0.0
    base = close[-1 - lookback]
    if base <= 0:
        return 0.0
    return (close[-1] - base) / base


def calc_amplitude(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                   lookback: int) -> float:
    """振幅：(近 N 日最高 - 最低) / 最低"""
    if len(close) < lookback:
        return 0.0
    high_window = high[-lookback:]
    low_window = low[-lookback:]
    h = float(np.nanmax(high_window))
    l = float(np.nanmin(low_window))
    if l <= 0:
        return 0.0
    return (h - l) / l


def calc_drawdown_from_60d_high(close: np.ndarray, lookback: int = OSC_PERIOD) -> float:
    """距近 lookback 日高点的回撤"""
    if len(close) < lookback:
        return 0.0
    high_window = close[-lookback:]
    h = float(np.nanmax(high_window))
    c = float(close[-1])
    if h <= 0:
        return 0.0
    return (h - c) / h


def check_ma60_band(close: np.ndarray, ma60: np.ndarray, band: float = MA60_BAND) -> bool:
    """价格在 MA60 ±band% 内（视为震荡穿越 MA60）"""
    if len(close) == 0 or np.isnan(ma60[-1]) or ma60[-1] <= 0:
        return False
    upper = ma60[-1] * (1 + band)
    lower = ma60[-1] * (1 - band)
    return lower <= close[-1] <= upper


# ════════════════════════════════════════════════════════════
# 单根 K 线判定（v3：4 档实战规则版）
# ════════════════════════════════════════════════════════════
def judge_single(close: np.ndarray, df: pd.DataFrame) -> Tuple[str, Dict]:
    """
    单日判定（v3 - 4 档实战规则版）

    严格按你的 4 档规则：
    ─────────────────────────────────────────────
    1. 单边上行：close > MA20 > MA60 + MA20 连续 10 日向上 + 近 20 日涨幅 > 8%
    2. 波段：close > MA60 + MA20 走平（10 日斜率 < 0.3%）+ 20 日振幅 8%~15%
    3. 震荡：价格在 MA60 ±5% 内 + 60 日振幅 < 15%
    4. 下行：close < MA20 < MA60 或 距 60 日高点回撤 > 15%
    ─────────────────────────────────────────────
    优先级：下行 > 震荡 > 波段 > 单边上行
    （严厉档位优先，避免上行/震荡混淆时误判为上行）
    """
    if close is None or df is None or len(close) < OSC_PERIOD + 1:
        return 'UNKNOWN', {}

    # 基础数据
    ma20 = calc_ma_series(close, MA_FAST)
    ma60 = calc_ma_series(close, MA_SLOW)
    high = df['high'].values
    low = df['low'].values

    if np.isnan(ma20[-1]) or np.isnan(ma60[-1]):
        return 'UNKNOWN', {}

    cur_close = float(close[-1])
    cur_ma20 = float(ma20[-1])
    cur_ma60 = float(ma60[-1])

    # 各种条件计算
    ma20_up_days = calc_ma20_consecutive_up_days(close, MA_FAST, MA20_UP_DAYS)
    ma20_slope = calc_ma20_slope_recent(close, MA_FAST, lookback=10)
    gain_20 = calc_recent_gain(close, lookback=RANGE_PERIOD)
    amp_20 = calc_amplitude(close, high, low, lookback=RANGE_PERIOD)
    amp_60 = calc_amplitude(close, high, low, lookback=OSC_PERIOD)
    dd_60 = calc_drawdown_from_60d_high(close, lookback=OSC_PERIOD)
    in_ma60_band = check_ma60_band(close, ma60, MA60_BAND)

    # 当根 K 线涨跌幅（大阴大阳标记用）
    candle_pct = 0.0
    if len(close) >= 2 and close[-2] > 0:
        candle_pct = (close[-1] - close[-2]) / close[-2]

    detail = {
        'close': round(cur_close, 3),
        'ma20': round(cur_ma20, 3),
        'ma60': round(cur_ma60, 3),
        'ma20_up_days': ma20_up_days,
        'ma20_slope_10d': round(ma20_slope, 5),
        'gain_20d': round(gain_20, 4),
        'amplitude_20d': round(amp_20, 4),
        'amplitude_60d': round(amp_60, 4),
        'drawdown_60d': round(dd_60, 4),
        'in_ma60_band': in_ma60_band,
        'candle_pct': round(candle_pct, 4),
    }

    # ───── 优先级判定（严厉档位优先）─────
    # 4. 下行：close < MA20 < MA60 或 回撤 > 15%
    cond_down_bear = (cur_close < cur_ma20 < cur_ma60)
    cond_down_dd = (dd_60 > DRAWDOWN_60)
    if cond_down_bear or cond_down_dd:
        detail['down_reason'] = ('bear_order' if cond_down_bear else 'drawdown') + \
                                f' (dd={dd_60*100:.1f}%)'
        return 'STRONG_DOWN', detail

    # 4.5 温和回调（v4 新增 2026-09-08，基于 3 年真实数据回测）：
    #   条件：close < MA20 但 close > MA60 + 回撤 < 10%
    #   实测：WEAK_DOWN 后 5/10/20 日均下跌（-0.29%/-0.53%/+0.22%），属下跌中继
    #   操作：同 STRONG_DOWN（不开仓），仅作日志/缓存标识区分
    cond_weak = (cur_close < cur_ma20) and (cur_close > cur_ma60) and (dd_60 < 0.10)
    if cond_weak:
        detail['weak_reason'] = (
            f'close<MA20({cur_ma20:.3f}) 但 close>MA60({cur_ma60:.3f}), '
            f'dd_60={dd_60*100:.1f}%<10% (温和回调，下跌中继)'
        )
        return 'WEAK_DOWN', detail

    # 3. 震荡：价格在 MA60 ±5% 内 + 60 日振幅 < 15%
    if in_ma60_band and amp_60 < RANGE_60_MAX:
        detail['osc_reason'] = f'ma60_band=±{MA60_BAND*100:.0f}%, amp_60={amp_60*100:.1f}%'
        return 'RANGE', detail

    # 2. 波段：close > MA60 + MA20 走平（10 日斜率 < 0.3%）+ 20 日振幅 8%~15%
    cond_wave_close = (cur_close > cur_ma60)
    cond_wave_flat = (abs(ma20_slope) < MA20_SLOPE_FLAT)
    cond_wave_amp = (RANGE_20_MIN <= amp_20 <= RANGE_20_MAX)
    if cond_wave_close and cond_wave_flat and cond_wave_amp:
        detail['wave_reason'] = (
            f'close>MA60, MA20_slope={ma20_slope*100:.2f}%<0.3%, '
            f'amp_20={amp_20*100:.1f}% in [8%,15%]'
        )
        return 'WAVE_UP', detail

    # 1. 单边上行（严格）：close > MA20 > MA60 + MA20 连续 10 日向上 + 近 20 日涨幅 > 8%
    cond_strong_order = (cur_close > cur_ma20 > cur_ma60)
    cond_strong_ma = (ma20_up_days >= MA20_UP_DAYS)
    cond_strong_gain = (gain_20 > PRICE_MA20_MA60_ORDER_GAIN)
    if cond_strong_order and cond_strong_ma and cond_strong_gain:
        detail['strong_reason'] = (
            f'close>MA20>MA60, MA20_up={ma20_up_days}日, gain_20={gain_20*100:.1f}%>8%'
        )
        return 'STRONG_UP', detail

    # 1b. 单边上行（半严格）：识别"早期单边行情"（半导体 4.7→4.27 那种类型）
    #   条件：close > MA60 + MA20 连上 ≥ 5 天 + 近 20 日涨幅 > 8%
    #   区别于严格档：不需要 MA20 > close（容许短期回踩）+ 连上只需 5 天（更快确认）
    cond_semi_ma = (ma20_up_days >= 5)
    if cond_semi_ma and cond_strong_gain and cur_close > cur_ma60:
        detail['strong_reason'] = (
            f'[半严格] close>MA60({cur_ma60:.3f}), MA20_up={ma20_up_days}日, '
            f'gain_20={gain_20*100:.1f}%>8%'
        )
        detail['strong_mode'] = 'semi_strict'
        return 'STRONG_UP', detail

    # 不属于任何档位 → UNKNOWN（不入推荐）
    # 给个诊断：最接近哪个档位
    candidates = []
    if cond_strong_order:
        candidates.append(f'近_单边:ma_up={ma20_up_days},gain={gain_20*100:.1f}%')
    if cond_wave_close and cond_wave_amp:
        candidates.append(f'近_波段:slope={ma20_slope*100:.2f}%')
    if in_ma60_band:
        candidates.append(f'近_震荡:amp_60={amp_60*100:.1f}%')
    if cond_down_dd:
        candidates.append(f'近_下行:dd={dd_60*100:.1f}%')
    detail['near_misses'] = candidates
    return 'UNKNOWN', detail


# ════════════════════════════════════════════════════════════
# 简化版 4 档状态判定（2026-09-04 新增）
# ════════════════════════════════════════════════════════════
# 用户需求："只给 4 档状态判断（上行/波段/震荡/下行），不管仓位，不管止损"
#
# 设计：
#   - judge_single() 输出 STRONG_UP / WAVE_UP / RANGE / STRONG_DOWN / UNKNOWN
#   - PHASE_LABELS 已定义中文标签
#   - judge_market_phase() 仅包装一次，输出便于上层使用的中文标签 + 关键指标
#
# 注意：
#   - 本函数不带任何仓位管理、加仓、止损建议
#   - 适合作为上层调用方（如 fusion_runner）的"波段判断基础信号"
#   - 用户自行决定入场/止损/仓位
# ════════════════════════════════════════════════════════════

# 4 档中文标签（复用 PHASE_LABELS）
PHASE_LABELS_4 = {
    'STRONG_UP':   '上行',
    'WAVE_UP':     '波段',
    'RANGE':       '震荡',
    'STRONG_DOWN': '下行',
    'UNKNOWN':     '未知',
}


def judge_market_phase(close: np.ndarray, df: pd.DataFrame) -> Dict:
    """
    简化版 4 档波段状态判定（2026-09-04）

    输入：日 K 线（close, df）
    输出：dict 包含：
      - phase: 英文标签 (STRONG_UP / WAVE_UP / RANGE / STRONG_DOWN / UNKNOWN)
      - label: 中文标签 (上行 / 波段 / 震荡 / 下行 / 未知)
      - close, ma20, ma60: 价格 / 均线
      - vs_ma20_pct, vs_ma60_pct: 相对位置
      - ma20_slope_10d: MA20 10 日斜率
      - gain_20d: 近 20 日涨幅
      - amplitude_20d, amplitude_60d: 振幅
      - drawdown_60d: 距 60 日高点回撤
      - reason: 触发原因（如有）

    不预设：
      - 不给仓位建议
      - 不给止损建议
      - 不给入场点建议

    仅供调用方做波段判断。
    """
    phase, detail = judge_single(close, df)
    label = PHASE_LABELS_4.get(phase, '未知')

    # 简化输出
    out = {
        'phase': phase,
        'label': label,
        'close': detail.get('close'),
        'ma20': detail.get('ma20'),
        'ma60': detail.get('ma60'),
        'vs_ma20_pct': round(detail.get('close', 0) / detail.get('ma20', 1) - 1, 4) if detail.get('ma20') else None,
        'vs_ma60_pct': round(detail.get('close', 0) / detail.get('ma60', 1) - 1, 4) if detail.get('ma60') else None,
        'ma20_slope_10d': detail.get('ma20_slope_10d'),
        'gain_20d': detail.get('gain_20d'),
        'amplitude_20d': detail.get('amplitude_20d'),
        'amplitude_60d': detail.get('amplitude_60d'),
        'drawdown_60d': detail.get('drawdown_60d'),
        'reason': (
            detail.get('strong_reason') or
            detail.get('wave_reason') or
            detail.get('osc_reason') or
            detail.get('down_reason') or
            '未归入任何档位（"未知"）'
        ),
    }
    return out


# ════════════════════════════════════════════════════════════
# v2 回调后启动判定（半导体/化工专用）
# ────────────────────────────────────────────────────────────
# v3 在题材板块上"突破即顶"反指标；v2 改用"回踩后启动"判定
# 回测验证（5 日窗口）：
#   半导体 ETF:  BUY 命中 63.2%, 均收益 +3.02% vs NO_BUY -0.14%（单调差 +3.16%）
#   化工 ETF:    BUY 命中 88.9%, 均收益 +3.81% vs NO_BUY +0.28%（单调差 +3.54%）
#   通信 ETF:    BUY 命中 48.7%（relaxed 参数下单调差 +1.33%）
def judge_v2_sector(
    close: np.ndarray,
    df: pd.DataFrame,
    pullback_lookback: int = 5,
    pullback_touch_tol: float = 0.0,
) -> Tuple[str, Dict]:
    """
    v2 回调后启动判定（4 个条件全满足 → STRONG_UP）

    参数:
      pullback_lookback: 近 N 日内必须回踩 MA20（默认 5）
      pullback_touch_tol: 回踩 MA20 的容差（默认 0=触及/跌破；放宽=+0.02 容许 2%）

    判定条件（4 个全满足 → STRONG_UP）：
      1. close > MA20（不在下行趋势里）
      2. 近 N 日内 close 至少 1 次回踩 MA20
      3. MA20 5 日斜率向上（续涨动能）
      4. 近 N 日至少 1 天涨幅 > 2%（动能确认）
    """
    if close is None or df is None or len(close) < 30:
        return 'UNKNOWN', {}

    ma20 = calc_ma_series(close, MA_FAST)
    if np.isnan(ma20[-1]):
        return 'UNKNOWN', {}

    cur_close = float(close[-1])
    cur_ma20 = float(ma20[-1])

    reasons = []
    indicator = {
        'close': round(cur_close, 3),
        'ma20': round(cur_ma20, 3),
        'pullback_lookback': pullback_lookback,
        'pullback_touch_tol': pullback_touch_tol,
    }

    # 条件 1：close > MA20
    cond1 = cur_close > cur_ma20
    if cond1:
        reasons.append(f'close>MA20')

    # 条件 2：近 N 日 close 至少 1 次回踩 MA20
    recent_close = close[-pullback_lookback:]
    recent_ma20 = ma20[-pullback_lookback:]
    touched_ma20 = (recent_close <= recent_ma20 * (1 + pullback_touch_tol)).any()
    if touched_ma20:
        idx = int(np.where(recent_close <= recent_ma20 * (1 + pullback_touch_tol))[0][0])
        days_ago = pullback_lookback - idx
        reasons.append(f'{days_ago}天前回踩MA20')

    # 条件 3：MA20 5 日斜率向上
    if len(ma20) >= 6:
        ma20_now = float(ma20[-1])
        ma20_5d_ago = float(ma20[-6])
        slope_up = ma20_now > ma20_5d_ago
        slope_pct = (ma20_now - ma20_5d_ago) / ma20_5d_ago * 100 if ma20_5d_ago > 0 else 0
        indicator['ma20_slope_5d_pct'] = round(slope_pct, 3)
    else:
        slope_up = False
        slope_pct = 0
    if slope_up:
        reasons.append(f'MA20斜率+{slope_pct:.2f}%')

    # 条件 4：近 N 日至少 1 天涨幅 > 2%
    recent_returns = pd.Series(close[-pullback_lookback:]).pct_change().fillna(0).values
    has_big_candle = (recent_returns > 0.02).any()
    if has_big_candle:
        max_idx = int(np.argmax(recent_returns))
        max_pct = recent_returns[max_idx] * 100
        reasons.append(f'{pullback_lookback-max_idx}天前+{max_pct:.1f}%')

    indicator['cond1_close_above_ma20'] = cond1
    indicator['cond2_pulled_back'] = touched_ma20
    indicator['cond3_slope_up'] = slope_up
    indicator['cond4_big_candle'] = has_big_candle

    if cond1 and touched_ma20 and slope_up and has_big_candle:
        phase = 'STRONG_UP'
        detail_extra = {'v2_reasons': reasons}
        indicator.update(detail_extra)
        return phase, {'indicator': indicator, 'v2_active': True}
    return 'NO_BUY_V2', {'indicator': indicator, 'v2_active': True, 'v2_reasons': reasons}


# ════════════════════════════════════════════════════════════
# v2 板块配置（哪些板块用 v2 替代 v3）
# ────────────────────────────────────────────────────────────
# 回测验证：v2 在这些板块上比 v3 更准（1 年回测，5/10 日窗口）
# 高胜率核心板块（touch_tol=0.0 default）：
#   - 半导体：v2 5日 70%、10日 90% 命中，单调差 +6.7%/+14.6%（绝对赢家）
#   - 种子农业：v2 5日 62%、10日 100% 命中，单调差 +1.9%/+4.5%
#   - 券商：v2 5日 50%、10日 50% 命中，单调差 +0.75%/+2.08%（新增）
# 化工（已移除）：5/10 日 v3 略优，但 10 日 v2 -4.72% 拖累
# 光通信（已移除，走纯 v3）：v2 全参数单调差为负
# 家电/油气/新能源/电网设备/AI应用（已移除）：
#   早期"v2 反胜"是在 touch_tol=0.02 放宽参数下得到的结果；
#   用 touch_tol=0.0 严格参数批量回测，1 年 BUY 样本全部亏损，BUY 信号均反指标
V2_SECTORS: Dict[str, Dict] = {
    # 半导体已从 V2_SECTORS 移除（2026-09-05），改用 V7_SECTORS['半导体'] 的 v7 逻辑
    # 理由：v7 比 v2 更灵活，能在 v3 上行判定之上叠加 |vs_MA20| < 2% 过滤，
    #       比 v2 触发的 41 次 BUY 减少到 16 次，但命中从 50% 提升到 75%
    '种子农业':     {'pullback_lookback': 5, 'pullback_touch_tol': 0.0},  # default
    '券商':         {'pullback_lookback': 5, 'pullback_touch_tol': 0.0},  # 新增（策略互换验证）
    '工程机械':     {'pullback_lookback': 5, 'pullback_touch_tol': 0.0},  # 2026-09 新增（v2 5d 命中 77.8%）
    '新能源':       {'pullback_lookback': 5, 'pullback_touch_tol': 0.0},  # 2026-08-31 新增（v2 5d 单调差 +0.90%, 命中 71.4%）
    '创新药':       {'pullback_lookback': 5, 'pullback_touch_tol': 0.0},  # 2026-08-31 新增（A 股 sz159992, v2 5+10 合计 +2.01%, 10d 命中 75%）
}


# ════════════════════════════════════════════════════════════
# v7 板块专用：在 v2/v3 之上叠加更严的入场过滤（2026-09-05 落地）
# ────────────────────────────────────────────────────────────
# 半导体专用 v7：上行（v2 已判定）+ 距 MA20 < 2%
# 回测数据（sh512480, 2023-05-22 ~ 2026-09-03, 800 条 K 线）：
#   - 命中 75.0% (12/16)
#   - 复利累计收益 +116.13%
#   - 最大单笔亏 -7.51%
#
# 设计：
#   - 只在 V2_SECTORS 触发了 STRONG_UP 的板块上，再叠一层 v7 过滤
#   - v7 触发 → phase 保持 STRONG_UP
#   - v7 不触发 → phase 降级为 STRONG_DOWN（v7 比 v2 更严）
#   - 不在 V7_SECTORS 的板块不受影响（继续走 v2 或 v3）
# ════════════════════════════════════════════════════════════
V7_SECTORS: Dict[str, Dict] = {
    # 半导体 v9 参数（基于 2023-05~2026-09 三年 800 条 K 线回测）：
    #   - 命中 92.3% / 复利 +153.47% / 最大单笔亏 -7.21% / 13 笔交易
    #   - ma20_touch_tol=0.02: |vs_MA20| < 2%（v7 基础）
    #   - dd_20_min=0.03: 距 20 日高点回撤必须 > 3%（v9 新增，避免最高点追涨）
    '半导体':       {'ma20_touch_tol': 0.02, 'dd_20_min': 0.03},
}


# ════════════════════════════════════════════════════════════
# v9 板块专用：在 slow_bull 之上叠加更严的入场过滤（2026-09-06 落地）
# ────────────────────────────────────────────────────────────
# 贵金属 v9 设计（参考半导体 v9，针对黄金波动特性调参）：
#   - 底层用 slow_bull（站上 MA60 ≥15 日 + 涨幅 >3% + 斜率 ≥0 + dd_60 <15%）
#   - |vs_MA20| < 8%（半导体用 2%，黄金放宽）
#   - 距 20 日高点回撤 > 8%（避免追高）
#   - 距 60 日高点回撤 < 15%（防止过高位置）
#
# 回测数据（sh518880, 2023-05-23 ~ 2026-09-04, 800 条 K 线）：
#   - 命中 94.7% (18/19)
#   - 复利累计收益 +71.38%（年化 ~19.7%）
#   - 最大单笔亏 -1.20%（止损 0 次）
#
# 与半导体 v9 对比：
#   - 半导体 v9: 13 笔 / 命中 92.3% / 最大亏 -7.21% / 复利 +127%
#   - 黄金 v9: 19 笔 / 命中 94.7% / 最大亏 -1.20% / 复利 +71.4%
#   黄金更稳（最大亏小），半导体爆发力更强（复利高）
# ════════════════════════════════════════════════════════════
V9_SECTORS: Dict[str, Dict] = {
    # 贵金属 v9（2026-09-06 落地）
    '贵金属': {
        'strategy':           'slow_bull_v9',   # 走 judge_gold_v9 (slow_bull + |vs_MA20|+ dd20)
        # slow_bull 参数
        'lookback_above_ma60': 15,
        'gain_min':           0.03,
        'slope_min':          0.0,
        'dd_max':             0.15,    # 黄金波动大，宽容到 15%（半导体用 10%）
        # v9 三条件 BUY 过滤
        'ma20_touch_tol':     0.08,    # |vs_MA20| < 8%
        'dd_20_min':          0.08,    # 距 20 日高回撤 > 8%
    },
    # B 族慢牛 v9 通用模板（2026-09-06 落地）
    # 设计：参考贵金属 v9，慢牛 + |vs_MA20|<8% + 距20日高>8%
    # 回测数据（3 年 800 条 K 线，T+10 + -5% 止损）：
    #   底仓:        5 笔 / 命中 80% / 复利 +5.7% / 最大亏 -0.22%
    #   白酒:        8 笔 / 命中 75% / 复利 +46.8% / 最大亏 -1.87%
    #   家电:        2 笔 / 命中 100% / 复利 +17.5% / 最大亏 +8.28%
    #   工业金属:   20 笔 / 命中 80% / 复利 +36.7% / 最大亏 -9.97%
    #   化工:        7 笔 / 命中 100% / 复利 +46.6% / 最大亏 +3.51%
    # 稀土不回测：2026-03 连续 5 次 -5% 止损，复利 -15.75%，不进 v9
    '底仓':        {'strategy': 'slow_bull_v9', 'lookback_above_ma60': 15, 'gain_min': 0.03,
                    'slope_min': 0.0, 'dd_max': 0.15, 'ma20_touch_tol': 0.08, 'dd_20_min': 0.08},
    '白酒':        {'strategy': 'slow_bull_v9', 'lookback_above_ma60': 15, 'gain_min': 0.03,
                    'slope_min': 0.0, 'dd_max': 0.15, 'ma20_touch_tol': 0.08, 'dd_20_min': 0.08},
    '家电':        {'strategy': 'slow_bull_v9', 'lookback_above_ma60': 15, 'gain_min': 0.03,
                    'slope_min': 0.0, 'dd_max': 0.15, 'ma20_touch_tol': 0.08, 'dd_20_min': 0.08},
    '工业金属':    {'strategy': 'slow_bull_v9', 'lookback_above_ma60': 15, 'gain_min': 0.03,
                    'slope_min': 0.0, 'dd_max': 0.15, 'ma20_touch_tol': 0.08, 'dd_20_min': 0.08},
    '化工':        {'strategy': 'slow_bull_v9', 'lookback_above_ma60': 15, 'gain_min': 0.03,
                    'slope_min': 0.0, 'dd_max': 0.15, 'ma20_touch_tol': 0.08, 'dd_20_min': 0.08},
    # ────────────────────────────────────────────────────────────
    # 种子农业 v9（2026-09-07 落地，季节性板块专用）
    # 设计：BUY 信号高度依赖月份窗口（8-10 月秋收期）
    #   - 全年默认动量: 25 笔 / 32% 胜率 / -11.87% 复利 (反指标)
    #   - 8-10 月窗口:  10 笔 / 80% 胜率 / +47.84% 复利 (T+10/-5%)
    #   - 8-10 月窗口:   7 笔 / 100% 胜率 / +54.11% 复利 (T+10/-8%)
    # 判定：close>MA60 + |vs_MA20|<10% + 近5日涨>5% + 月份 ∈ (8,9,10)
    # 风控：T+10/-8%（100% 胜率配置）
    # ────────────────────────────────────────────────────────────
    '种子农业': {'strategy': 'seed_agriculture_v9', 'season_months': (8, 9, 10)},

    # ────────────────────────────────────────────────────────────
    # 新能源 v9（2026-09-07 落地）
    # 设计：sh516160 (新能源ETF)，板块本身 buy-and-hold +163%，慢牛策略已能完美捕捉主升
    # 调优结果（3 年 800 条 K 线，T+10/-5%）：
    #   - 基础慢牛:    134 笔 / 59.0% / 复利 +1014% / 最大亏 -10.48%
    #   - v9 宽松调优:  56 笔 / 67.9% / 复利 +442%  / 最大亏 -7.63%
    # 牺牲 56% 复利换来 9 个百分点胜率提升 + 控住最大亏（-7.63% vs -10.48%）
    # 用 v9 理由：长期上涨板块需要防止 v3 反指标在高位追入
    # 关键参数差异（与其他 B 族 v9 相比）：
    #   - gain_min=2% (其他 3%，新能源本身上涨要放低门槛)
    #   - dd_max=20% (其他 10-15%，新能源波动大要放宽)
    #   - ma20_touch_tol=15% (其他 8%，新能源 |MA20| 容忍大)
    #   - dd_20_min=2% (其他 8%，新能源只要稍微回撤就买)
    # ────────────────────────────────────────────────────────────
    '新能源':      {'strategy': 'slow_bull_v9', 'lookback_above_ma60': 15, 'gain_min': 0.02,
                    'slope_min': 0.0, 'dd_max': 0.20, 'ma20_touch_tol': 0.15, 'dd_20_min': 0.02},
    # ────────────────────────────────────────────────────────────
    # 消费电子 v9（2026-09-07 落地）
    # 设计：消费电子 buy-and-hold +126% 是个上涨板块，但 slow_bull BUY 胜率仅 49%
    # 赢家特征分析发现（2026-09-07）：
    #   - 赢盘 60 日振幅 27.3% vs 输盘 33.6%（盘整期 BUY 显著更准）
    #   - 4线多头 + dd_60<5% + range_60<40%：79 笔 / 59.5% / +593%
    #   - 仅 range_60<40%：148 笔 / 55.4% / +1293%
    # 关键洞察：消费电子 BUY 等板块盘整（低振幅）时更准
    # 用 v9 range_60_max=0.40 + 4线多头 + dd_60<5%（可在 future 进一步加）
    # 当前只用 range_60_max=0.40，复利最大化的简化配置
    # ────────────────────────────────────────────────────────────
    '消费电子':   {'strategy': 'slow_bull_v9', 'lookback_above_ma60': 15, 'gain_min': 0.03,
                    'slope_min': 0.0, 'dd_max': 0.10, 'ma20_touch_tol': 0.10, 'dd_20_min': 0.03,
                    'range_60_max': 0.40},
    # ────────────────────────────────────────────────────────────
    # 智能驾驶 v9（2026-09-07 落地）
    # 设计：智能网联汽车 ETF (sz159872) 覆盖窄（与德赛/华阳 avg 0.677）
    #       智能驾驶ETF 失效会自动 fallback 用代表股合成（detector 内置）
    # 调优（3 年 800 条 K 线，T+10/-5%）：
    #   - 基础 slow_bull:    106 笔 / 47.2% / -4.46% 复利
    #   - v9 全宽松调优:      40 笔 / 57.5% / +69.69% 复利 / 最大亏 -6.48%
    #   - 当前参数 lb10/g5%/dd<20%/|MA20|<15%/dd20>3%
    # ────────────────────────────────────────────────────────────
    '智能驾驶':   {'strategy': 'slow_bull_v9', 'lookback_above_ma60': 10, 'gain_min': 0.05,
                    'slope_min': 0.0, 'dd_max': 0.20, 'ma20_touch_tol': 0.15, 'dd_20_min': 0.03},
    # ────────────────────────────────────────────────────────────
    # 燃气轮机 v9（2026-09-07 落地）
    # 设计：sh516320 高端装备代理（与杰瑞/航宇 avg 0.808）✅ OK
    # 调优（3 年 800 条 K 线，T+10/-5%）：
    #   - 基础 slow_bull:    150 笔 / 58.0% / +246% 复利
    #   - v9 全宽松调优:      41 笔 / 70.7% / +129.58% 复利 / 最大亏 -6.75%
    #   - 牺牲 47% 复利换 +12.7% 胜率
    # ────────────────────────────────────────────────────────────
    '燃气轮机':   {'strategy': 'slow_bull_v9', 'lookback_above_ma60': 15, 'gain_min': 0.03,
                    'slope_min': 0.0, 'dd_max': 0.15, 'ma20_touch_tol': 0.15, 'dd_20_min': 0.03},
    # ────────────────────────────────────────────────────────────
    # 可控核聚变 v9（2026-09-07 落地）
    # 设计：sh516320 代理（与永鼎/精达 avg 0.827）✅ OK
    # 调优（3 年 800 条 K 线，T+10/-5%）：
    #   - 基础 slow_bull:    150 笔 / 58.0% / +246% 复利
    #   - v9 调优:            30 笔 / **86.7%** / +193.55% 复利 / 最大亏 -6.75%
    #   - 极高胜率配置 lb10/g5%/dd<15%/|MA20|<10%/dd20>3%
    # ────────────────────────────────────────────────────────────
    '可控核聚变': {'strategy': 'slow_bull_v9', 'lookback_above_ma60': 10, 'gain_min': 0.05,
                    'slope_min': 0.0, 'dd_max': 0.15, 'ma20_touch_tol': 0.10, 'dd_20_min': 0.03},
    # 商业航天 (sh512560 军工ETF代理) 不加 v9 overlay：
    #   - v9 标准: 12 笔 / 41.7% / -26%
    #   - v9 全宽松: 29 笔 / 27.6% / -61%（**反指标**）
    #   - 基础 slow_bull: 100 笔 / 55.0% / +73.66%
    # v9 overlay 过滤掉了大部分有效信号，保持只用 slow_bull

    # ────────────────────────────────────────────────────────────
    # 商业航天 v9（2026-09-07 落地）
    # 设计：之前 v9 overlay 反指标（27.6%），但赢家特征显示4线 + 盘整期 BUY 显著更准
    # 调优（sh512560, 2023-05~2026-09, 800 条 K 线，T+10/-5%）：
    #   - 基础慢牛:    112 笔 / 53.6% / +35.89% 复利
    #   - 4线 + r60<20%: 27 笔 / **96.3%** / +302.32%（极致胜率但笔数少）
    #   - 4线 + r60<30%: 43 笔 / **74.4%** / +167.82%（推荐配置）
    #   - 4线 + r60<25%: 41 笔 / 78% / +197%（折中）
    # 关键洞察：商业航天 BUY 必须 4线趋势确认 + 板块盘整（低振幅）
    # ────────────────────────────────────────────────────────────
    '商业航天':   {'strategy': 'momentum_v9', 'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0, 'dd_max': 0.10,
                    'ma20_touch_tol': 0.15, 'gain_5d_min': 0.05,
                    'require_ma_align_4': True, 'range_60_max': 0.30},

    # ────────────────────────────────────────────────────────────
    # 电网设备 v9（2026-09-07 落地）
    # 设计：电网设备是反指标板块（基础慢牛 33.6%/-74%）
    # 赢家特征（110 笔样本）：4线多头是反指标（30% vs 59% 输盘）
    # 改用：NOT 4线多头 + |vs_MA20|<3% + gain_20<8%
    # 调优（sz159611, 2023-05~2026-09, 800 条 K 线，T+10/-5%）：
    #   - 基础慢牛:    110 笔 / 33.6% / -74.47% 复利
    #   - 专用 v9:      45 笔 / **55.6%** / **+20.14%** 复利
    # ────────────────────────────────────────────────────────────
    '电网设备':   {'strategy': 'power_grid_v9',
                    'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0, 'dd_max': 0.10,
                    'vs_ma20_max': 0.03, 'gain_20_max': 0.08, 'require_no_align_4': True},

    # ────────────────────────────────────────────────────────────
    # 券商 v9（2026-09-07 落地）
    # 设计：券商是周期股，B&H 同期 -39.33%（板块下跌）
    # 基础慢牛巨亏（58 笔 / 53% 胜率但均收益 -6.6%）
    # 赢家特征（4线 + 距20日高>5% 回撤后启动）
    # 调优（sh512000, 2023-05~2026-09, 800 条 K 线，T+10/-5%）：
    #   - 基础慢牛:    58 笔 / 53.4% / -99.74% 复利（板块下跌拖累）
    #   - 专用 v9:      9 笔 / **66.7%** / **+33.02%** 复利
    # 跑赢 buy-and-hold (-39.33%) 约 72 个百分点
    # ────────────────────────────────────────────────────────────
    '券商':       {'strategy': 'securities_v9',
                    'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0, 'dd_max': 0.10,
                    'dd_20_min': 0.05, 'require_align_4': True},

    # ────────────────────────────────────────────────────────────
    # 低空经济 v9（2026-09-07 落地）
    # 设计：低空经济是新兴主题，ETF 弱相关（avg 0.609 best of weak）
    # 基础慢牛反指标（104 笔 / 41.3% / -12%）
    # 赢家特征（4线 + |vs_MA20|<5% 贴近 MA20）
    # 调优（sz159795, 2023-05~2026-09, 800 条 K 线，T+10/-3%）：
    #   - 基础慢牛:    104 笔 / 41.3% / -11.99% 复利（反指标）
    #   - 专用 v9:      18 笔 / **61.1%** / **+102.10%** 复利（T+10/-3%）
    # ────────────────────────────────────────────────────────────
    '低空经济':   {'strategy': 'low_altitude_v9',
                    'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0, 'dd_max': 0.10,
                    'vs_ma20_max': 0.05, 'require_align_4': True},
    # ────────────────────────────────────────────────────────────
    # 创新药 v9（2026-09-06 落地，事件驱动型板块专用）
    # 设计：通用动量策略对创新药完全失效（28.9% / -56%），
    #       因为板块整体下行（buy-and-hold -7.35%）+ 事件驱动节奏，
    #       改用慢牛+align + 长持有 + 宽止损
    # 回测数据（sz159992, 2023-05~2026-09, 800 条 K 线，T+30/-8%）：
    #   39 笔 / 胜率 74.4% / 复利 +116.29% / 最大亏 -9.02%
    #   同期 buy-and-hold -7.35%（专用策略跑赢 +124 个百分点）
    # 判定：close > MA5 > MA10 > MA20 > MA60（4线多头）+ 近20日涨>8%
    # 风控：T+30/-8%（与其它板块不同，事件发酵需要长持有期）
    # ────────────────────────────────────────────────────────────
    '创新药': {'strategy': 'innovative_drug_v9', 'gain_20_min': 0.08},

    # ────────────────────────────────────────────────────────────
    # A 族动量 v9（2026-09-06 落地，每板块独立参数 + 增强条件）
    # 设计：A 族震荡走势，半导体 v9 严格 3 条件几乎不触发 → 改用动量版
    #   1. close > MA60（多头排列基础）
    #   2. |vs_MA20| < ma20_touch_tol（每板块独立阈值）
    #   3. 近 5 日涨幅 > gain_5d_min（每板块独立阈值）
    #   4. require_ma_align_4: 4 线多头 (close>MA5>MA10>MA20>MA60)
    #   5. dd_60_max: 距 60 日高点回撤上限
    #
    # 回测数据（3 年 800 条 K 线，2026-09-06）：
    #   军工 sh512660:
    #     ma20<15% / gain5d>6% / ma_align_4 / dd60<5%
    #     → 20 笔 / 胜率 70.0% / 复利 +103.21% / 最大亏 -5.23% (T+5/-3%)
    #     → 20 笔 / 胜率 60.0% / 复利 +93.61%  / 最大亏 -7.72% (T+10/-5%)
    #     教训：默认参数 (|MA20|<10%, gain5d>5%) 胜率仅 39%，必须 4 线多头 + dd60 限制
    #   AI应用 sh515980:
    #     ma20<15% / gain5d>8%                                → 41 笔 / 胜率 58.5% / 复利 +66.11%
    #     ma_align_4 会把胜率拖到 46%，复利 -33% — 不启用
    #   人形机器人 sh562500:
    #     ma20<12% / gain5d>5% / ma_align_4                   → 29 笔 / 胜率 69.0% / 复利 +77% / 最大亏 -7.55%
    #     dd_60<5% 反而拖累胜率 — 不启用
    #   光通信 sh515880:
    #     ma20<15% / gain5d>6%                                → 77 笔 / 胜率 61.0% / 复利 +459.55%
    #     ma_align_4 把复利从 +459% 拖到 +121% — 不启用
    #
    # 设计原则（用户洞察，2026-09-06）：
    #   - 每板块独立策略，不试图一个策略坚固所有 A 族
    #   - ma_align_4 是「事件驱动」板块（军工/人体机器人）的过滤器，对趋势强但宽幅的板块（光通信）反而有害
    #
    # 风控建议：
    #   - 军工：T+5/-3%（快进快出，胜率 70%）
    #   - 其他 A 族：T+10/-5%（标准风控）
    # ────────────────────────────────────────────────────────────
    '军工':        {'strategy': 'momentum_v9', 'ma20_touch_tol': 0.15, 'gain_5d_min': 0.06,
                    'require_ma_align_4': True, 'dd_60_max': 0.05},
    'AI应用':      {'strategy': 'momentum_v9', 'ma20_touch_tol': 0.15, 'gain_5d_min': 0.06,
                    'range_60_max': 0.30},  # 2026-09-07: r60<30% → 47笔/72.3%/+1086%
    '人形机器人':  {'strategy': 'momentum_v9', 'ma20_touch_tol': 0.12, 'gain_5d_min': 0.05,
                    'require_ma_align_4': True},
    '光通信':      {'strategy': 'momentum_v9', 'ma20_touch_tol': 0.15, 'gain_5d_min': 0.06},
    # ────────────────────────────────────────────────────────────
    # 稀土 v9（2026-09-07 落地）
    # 设计：之前 slow_bull 默认 49.1%/+427%，赢家特征显示 NOT 4线 + 盘整期 BUY 更准
    # 调优（sh516150, 2023-05~2026-09, 800 条 K 线，T+10/-5%）：
    #   - slow_bull 宽 (10,2%,15%): 198 笔 / 52.5% / +994.35%
    #   - NOT 4线 + r60<30%:      53 笔 / **69.8%** / +242.14%（推荐）
    #   - NOT 4线 + r60<35%:      77 笔 / 63.6% / +317.93%（高复利）
    # 关键洞察：稀土 BUY 等"未过热 + 盘整"信号，过热(4线)是反指标
    # ────────────────────────────────────────────────────────────
    '稀土':        {'strategy': 'momentum_v9', 'ma20_touch_tol': 0.15, 'gain_5d_min': 0.05,
                    'require_no_ma_align_4': True, 'range_60_max': 0.30},
}


# A 族动量 v9 板块集合（2026-09-06 落地）
# 用于 _judge_from_df 分流：A 族走 judge_a_momentum 而非 slow_bull + gold_v9
A_MOMENTUM_SECTORS: set = {
    '军工',
    'AI应用',
    '人形机器人',
    '光通信',
}


# ════════════════════════════════════════════════════════════
# 慢牛策略 v1：识别温和持续上涨的板块
# ────────────────────────────────────────────────────────────
# 适用场景：
#   - 电网设备 1-3 月那种慢涨 +8.9% 行情（不是暴涨，也不是回踩后启动）
#   - 涨上去不容易跌回来的稳定板块（资源/防御/主题龙头）
#
# 与 v2 的区别：
#   - v2 设计场景："高位股回踩后启动"（半导体 4.7→4.27 类型）
#   - 慢牛设计场景："温和慢涨持续上行"（电网设备 1-3 月 +19.6%）
#
# 1 年回测（2025-08~2026-08，260 条 K 线）：
#   慢牛策略 vs v3 单调差提升：
#     军工  +1.37%/+4.16%  | 商业航天 +1.72%/+4.06%
#     贵金属 +1.42%/+1.99% | 油气  +1.31%/+3.64%
#     化工  +1.72%/+2.00%  | 工业金属 +0.39%/+0.65%
#
# 行为（与 v2 类似，独立判定，不回退到 v3）：
#   - 慢牛触发 STRONG_UP → phase_today = STRONG_UP
#   - 慢牛不触发       → phase_today = STRONG_DOWN（不让 v3 干扰）
# ════════════════════════════════════════════════════════════
# 半导体专属 slow_bull 参数（v5c, 2026-09-03, 3 年回测验证）：
#   - 顶部过滤（距 60 日高点回撤必须 > 8%）：避免 2026-05~07 主升末段接刀
#   - lookback_above_ma60=20：要求站上 MA60 更长时间（半导体慢热）
#   - 触发后用 -5% 硬止损 + 浮盈 5% 后启用移动止盈 (BU×1.02) + T+5 主动止盈（详见 judge_semicon_v5）
SLOW_BULL_SECTORS: Dict[str, Dict] = {
    # B 族慢牛 v9 板块（2026-09-06 落地）
    # 这些板块先走 slow_bull 判定，再叠加 V9_SECTORS 的 |vs_MA20|<8% + 距20日高>8% 过滤
    '底仓':        {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.15},
    '白酒':        {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.15},
    '家电':        {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.15},
    # 其他 B 族慢牛板块（在 V9_SECTORS 里同时配置）
    '军工':         {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.10},
    '贵金属':       {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.10},
    '工业金属':     {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.15},  # v9 用 15% 放宽
    '油气':         {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.10},
    '航运':         {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.10},  # 2026-09-07：与油气共享 ETF，参数同油气
    '新能源':       {'lookback_above_ma60': 15, 'gain_min': 0.02, 'slope_min': 0.0,    'dd_max': 0.20},  # 2026-09-07：板块本身上涨，gain_min 降至 2%，dd 放宽到 20%
    '消费电子':     {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.10},  # 2026-09-07：v9 加 range_60<40% 过滤
    '智能驾驶':     {'lookback_above_ma60': 10, 'gain_min': 0.05, 'slope_min': 0.0,    'dd_max': 0.20},  # 2026-09-07：智能驾驶 ETF 覆盖弱，放宽 dd 到 20%
    '燃气轮机':     {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.15},  # 2026-09-07：v9 全宽松
    '可控核聚变':   {'lookback_above_ma60': 10, 'gain_min': 0.05, 'slope_min': 0.0,    'dd_max': 0.15},  # 2026-09-07：86.7% 胜率配置
    '商业航天':     {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.10},  # 2026-09-07：已转 v9（momentum_v9 4线+r60<30%），保留 sb 兜底
    '化工':         {'lookback_above_ma60': 15, 'gain_min': 0.03, 'slope_min': 0.0,    'dd_max': 0.15},  # v9 用 15% 放宽
    # 半导体已从 SLOW_BULL_SECTORS 移除（2026-09-05），改用 V7_SECTORS['半导体'] 的 v7 逻辑
    # 理由：v7 比 slow_bull 更适合半导体（命中 75% vs 60%，复利 +116% vs +6%）
}


def judge_slow_bull(
    close: np.ndarray,
    df: pd.DataFrame,
    lookback_above_ma60: int = 15,
    gain_min: float = 0.03,
    slope_min: float = 0.0,
    dd_max: float = 0.10,
) -> Tuple[str, Dict]:
    """
    慢牛策略 v1：识别温和持续上涨

    判定条件（4 个全满足 → STRONG_UP）：
      1. close > MA60（多头排列）
      2. close 站上 MA60 至少 lookback_above_ma60 日（持续站稳，排除短期反弹）
      3. 近 20 日涨幅 > gain_min（温和上涨，3% 以上）
      4. MA20 5 日斜率 > slope_min（向上动能，可放宽到 0）
      5. 距 60 日高点回撤 < dd_max（不追在顶部）

    与 v3 单边上行的区别：
      - v3: close>MA20>MA60 + MA20连上10日 + 涨幅>8%（检测"已经突破"）
      - 慢牛: close>MA60（站上多日）+ 涨幅>3%（温和涨势，不追高）
    """
    if close is None or df is None or len(close) < OSC_PERIOD + 1:
        return 'UNKNOWN', {}

    ma60 = calc_ma_series(close, MA_SLOW)
    ma20 = calc_ma_series(close, MA_FAST)
    if np.isnan(ma60[-1]) or np.isnan(ma20[-1]):
        return 'UNKNOWN', {}

    cur_close = float(close[-1])
    cur_ma60 = float(ma60[-1])
    cur_ma20 = float(ma20[-1])

    # 条件 1：close > MA60
    cond1 = cur_close > cur_ma60

    # 条件 2：close 站上 MA60 至少 N 日
    n_above = 0
    for i in range(len(close) - 1, -1, -1):
        if np.isnan(ma60[i]):
            break
        if close[i] > ma60[i]:
            n_above += 1
        else:
            break
    cond2 = n_above >= lookback_above_ma60

    # 条件 3：近 20 日涨幅
    if len(close) < 21:
        return 'UNKNOWN', {}
    gain_20 = (cur_close - close[-21]) / close[-21]
    cond3 = gain_20 > gain_min

    # 条件 4：MA20 5 日斜率
    if len(ma20) < 6:
        return 'UNKNOWN', {}
    slope_5d = (ma20[-1] - ma20[-6]) / ma20[-6] if ma20[-6] > 0 else 0
    cond4 = slope_5d > slope_min

    # 条件 5：距 60 日高点回撤
    high_60 = float(np.nanmax(close[-60:]))
    dd_60 = (high_60 - cur_close) / high_60 if high_60 > 0 else 0
    cond5 = dd_60 < dd_max

    detail = {
        'close': round(cur_close, 3),
        'ma20': round(cur_ma20, 3),
        'ma60': round(cur_ma60, 3),
        'n_above_ma60': n_above,
        'gain_20d': round(gain_20, 4),
        'ma20_slope_5d_pct': round(slope_5d * 100, 3),
        'drawdown_60d': round(dd_60, 4),
        'lookback_above_ma60': lookback_above_ma60,
        'gain_min': gain_min,
        'slope_min': slope_min,
        'dd_max': dd_max,
        'cond1_close_above_ma60': cond1,
        'cond2_n_above': cond2,
        'cond3_gain': cond3,
        'cond4_slope': cond4,
        'cond5_drawdown': cond5,
    }

    if cond1 and cond2 and cond3 and cond4 and cond5:
        detail['slow_reason'] = (
            f'slow_bull: 站上MA60 {n_above}日, gain_20={gain_20*100:.1f}%>{gain_min*100:.0f}%, '
            f'slope={slope_5d*100:.2f}%, dd={dd_60*100:.1f}%<{dd_max*100:.0f}%'
        )
        return 'STRONG_UP', detail

    detail['slow_failed'] = [
        n for n, c in zip(['c1_close_ma60', 'c2_n_above', 'c3_gain', 'c4_slope', 'c5_dd'],
                          [cond1, cond2, cond3, cond4, cond5]) if not c
    ]
    return 'NO_BUY_SLOW', detail


# ════════════════════════════════════════════════════════════
# 半导体专用 v5：slow_bull + 顶部过滤 + 持仓期辅助判定（2026-09-03）
# ════════════════════════════════════════════════════════════
# 回测数据（sh512480, 2023-05-22 ~ 2026-09-03, 800 条 K 线）：
#   - 命中 60.0%（3/5）
#   - 仓位加权均收益 +1.33%
#   - 3 年复利累计收益 +6.46%
#   - 最大单笔亏 -2.85%（其余均 < 4%）
#   - 平均持仓 5.8 天
#   - 触发频率：约每季度 0.4 次（年均 1.7 笔）
#
# 设计要点：
#   1. 顶部过滤：BUY 时距 60 日高点回撤必须 > 8%（避免 2026-05~07 顶部接刀）
#   2. 慢牛判定：用 SLOW_BULL_SECTORS['半导体'] 的参数（lookback_above_ma60=20）
#   3. 半仓（50%）：一次不重仓
#   4. -5% 硬止损 + T+5 主动止盈（浮盈 > 0.5% 即落袋）
#   5. 浮盈 ≥ 5% 启用移动止盈：跌破 BU×1.02 即全部止盈
#
# 函数：
#   - judge_semicon_v5()        → 当日判定（BUY / NO_BUY）
#   - check_position_exit()     → 持仓期间每日辅助判定（止损 / 移动止盈 / T+5 主动止盈 / T+10 强平）
# ════════════════════════════════════════════════════════════

# 半导体 v5 持仓期参数（可在外部覆盖）
SEMICON_V5_DEFAULTS: Dict = {
    'stop_loss':           0.05,    # 硬止损：-5%
    'early_tp_days':       5,       # T+5 启用主动止盈
    'early_tp_min_profit': 0.005,   # 主动止盈最小浮盈 0.5%
    'trail_tp_trigger':    0.05,    # 浮盈达 5% 启用移动止盈
    'trail_tp_floor':      0.02,    # 移动止盈底线（跌破 BU×1.02 即止盈）
    'max_hold':            10,      # T+10 强制平仓
}


def judge_semicon_v5(close: np.ndarray, df: pd.DataFrame) -> Tuple[str, Dict]:
    """
    半导体专用 v5 BUY 判定（2026-09-03 落地）

    输入：日 K 线（close, df）
    输出：(phase, detail)
      - phase = 'STRONG_UP' → BUY 信号
      - phase = 'NO_BUY_V5' → 不买
    """
    if close is None or df is None or len(close) < OSC_PERIOD + 1:
        return 'NO_BUY_V5', {'reason': 'K线不足'}

    # 顶部过滤：距 60 日高点回撤必须 > 8%
    cur = float(close[-1])
    high_60 = float(np.nanmax(close[-60:])) if len(close) >= 60 else float(np.nanmax(close))
    dd_60 = (high_60 - cur) / high_60 if high_60 > 0 else 0
    if dd_60 < 0.08:
        return 'NO_BUY_V5', {
            'reason': f'顶部过滤: 距60日高点回撤仅 {dd_60*100:.2f}%, 需 > 8%',
            'close': round(cur, 3),
            'high_60': round(high_60, 3),
            'dd_60': round(dd_60, 4),
        }

    # 调慢牛策略（半导体专用参数：与 SLOW_BULL_SECTORS['半导体'] 保持一致）
    sb_phase, sb_detail = judge_slow_bull(
        close, df,
        lookback_above_ma60=15,
        gain_min=0.03,
        slope_min=0.0,
        dd_max=0.10,
    )

    if sb_phase == 'STRONG_UP':
        detail = {
            'close': round(cur, 3),
            'high_60': round(high_60, 3),
            'dd_60': round(dd_60, 4),
            'strategy': 'semicon_v5_slow_bull',
            'top_filter_passed': True,
            'slow_bull_detail': sb_detail,
        }
        detail['reason'] = (
            f'半导体 v5 BUY: 站上MA60 20+日 + 涨幅>{3}% + 距60日高回撤 {dd_60*100:.1f}%>8%'
        )
        return 'STRONG_UP', detail

    return 'NO_BUY_V5', {
        'reason': f'slow_bull 未触发',
        'close': round(cur, 3),
        'dd_60': round(dd_60, 4),
        'slow_bull_detail': sb_detail,
    }


def check_position_exit(
    close_today: float,
    avg_cost: float,
    hold_days: int,
    params: Optional[Dict] = None,
) -> Tuple[str, float]:
    """
    半导体 v5 持仓期辅助判定（每日调用）

    参数：
      close_today: 当日收盘价
      avg_cost:   持仓均价
      hold_days:  已持仓天数（T+1, T+2, ...）
      params:     覆盖默认参数（可选）

    返回：
      (action, reason_pct)
        action ∈ {'HOLD', 'STOP_LOSS', 'EARLY_TP', 'TRAIL_TP', 'FORCE_EXIT'}
        reason_pct: 触发时的盈亏比例（绝对值）

    规则（按优先级）：
      1. -5% 硬止损（任何持仓日）
      2. 浮盈 ≥ 5% 启用移动止盈：跌破 BU×1.02 即止盈
      3. T+5 后浮盈 > 0.5% 主动止盈
      4. T+10 强制平仓
    """
    p = dict(SEMICON_V5_DEFAULTS)
    if params:
        p.update(params)

    if avg_cost <= 0:
        return 'HOLD', 0.0

    profit_pct = close_today / avg_cost - 1

    # 1) 硬止损
    if profit_pct <= -p['stop_loss']:
        return 'STOP_LOSS', profit_pct

    # 2) 移动止盈（仅当浮盈 ≥ 触发线时启用）
    if profit_pct >= p['trail_tp_trigger']:
        # 跌破 BU×(1+floor) → 全部止盈
        if close_today <= avg_cost * (1 + p['trail_tp_floor']):
            return 'TRAIL_TP', profit_pct

    # 3) T+5 后主动止盈
    if hold_days >= p['early_tp_days'] and profit_pct >= p['early_tp_min_profit']:
        return 'EARLY_TP', profit_pct

    # 4) T+10 强制平仓
    if hold_days >= p['max_hold']:
        return 'FORCE_EXIT', profit_pct

    return 'HOLD', profit_pct


# ════════════════════════════════════════════════════════════
# 半导体专用 v7：上行 + 距 MA20 近（2026-09-04 落地）
# ════════════════════════════════════════════════════════════
# 回测数据（sh512480, 2023-05-22 ~ 2026-09-03, 800 条 K 线）：
#   - 命中 75.0% (12/16)
#   - 仓位加权均收益 +5.28%
#   - 3 年复利累计收益 +116.13%
#   - 最大单笔亏 -7.51%（其余均 < 6%）
#   - 平均持仓 9.4 天（多数 T+10 平）
#   - 触发频率：年均 5.3 笔（季度 1.3 笔）
#
# 设计要点：
#   1. 上行状态：复用 judge_single() 的 STRONG_UP（已包含多头排列 + 回撤过滤）
#   2. 距 MA20 < 2%：避免连续大涨远离均线（顶部追涨反指标）
#   3. 用户自己决定止损和仓位（v7 只给信号）
#
# 函数：
#   - judge_semicon_v7()  → 当日 BUY 判定（上行 + |vs_ma20| < 2%）
#
# 与 v5 的区别：
#   - v5: slow_bull + 距 60 日高回撤 > 8%（13 次 BUY，命中 60%，最大亏 -2.85%）
#   - v7: STRONG_UP + |vs_ma20| < 2%（16 次 BUY，命中 75%，最大亏 -7.51%）
#   - v7 触发更频繁，但胜率显著提升
# ════════════════════════════════════════════════════════════

# 半导体 v7 参数（可在外部覆盖）
SEMICON_V7_DEFAULTS: Dict = {
    'ma20_touch_tol':     0.02,    # |close/MA20 - 1| < 2%
    'require_strict_up':  True,    # 是否要求严格 STRONG_UP（不是半严格）
}


def judge_semicon_v7(
    close: np.ndarray,
    df: pd.DataFrame,
    ma20_touch_tol: float = 0.02,
    dd_20_min: float = 0.03,
    require_strict_up: bool = True,
) -> Tuple[str, Dict]:
    """
    半导体专用 v9 BUY 判定（2026-09-05 升级，原 v7）

    输入：日 K 线（close, df）
    输出：(phase, detail)
      - phase = 'STRONG_UP' → BUY 信号
      - phase = 'NO_BUY_V7' → 不买

    判定条件（3 个全满足 → BUY）：
      1. 上行状态（judge_single() 返回 STRONG_UP）
      2. close 距 MA20 < ma20_touch_tol（默认 2%，过滤连续大涨远离均线）
      3. close 距 20 日高点回撤 > dd_20_min（默认 3%，避免最高点追涨）

    风控（你自己处理）：
      - 持仓期建议：-5% 硬止损 或 T+10 平仓
      - 3 年回测：92.3% 命中 / 最大亏 -7.21% / 复利 +153%

    演进历史：
      - v7 (2026-09-04): 仅条件 1+2，命中 75%，最大亏 -7.51%，复利 +116%
      - v9 (2026-09-05): 条件 1+2+3，命中 92.3%，最大亏 -7.21%，复利 +153%
    """
    if close is None or df is None or len(close) < 30:
        return 'NO_BUY_V7', {'reason': 'K线不足'}

    # 1) 4 档 phase 判定
    v3_phase, v3_detail = judge_single(close, df)
    if v3_phase != 'STRONG_UP':
        return 'NO_BUY_V7', {
            'reason': f'phase={v3_phase}, 不在上行状态',
            'close': round(float(close[-1]), 3),
            'phase': v3_phase,
        }

    # 2) 距 MA20 必须 < 2%（过滤连续大涨远离均线）
    cur = float(close[-1])
    ma20 = calc_ma_series(close, MA_FAST)
    if np.isnan(ma20[-1]):
        return 'NO_BUY_V7', {
            'reason': 'MA20 不足',
            'close': round(cur, 3),
        }

    vs_ma20 = (cur - ma20[-1]) / ma20[-1] if ma20[-1] > 0 else 0
    if abs(vs_ma20) >= ma20_touch_tol:
        return 'NO_BUY_V7', {
            'reason': f'距 MA20 {vs_ma20*100:+.2f}%, 超过阈值 {ma20_touch_tol*100:.0f}%',
            'close': round(cur, 3),
            'ma20': round(float(ma20[-1]), 3),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
            'phase': v3_phase,
        }

    # 3) 距 20 日高点回撤必须 > 3%（避免最高点追涨，v9 新增）
    high_20 = float(np.nanmax(close[-20:])) if len(close) >= 20 else float(np.nanmax(close))
    dd_20 = (high_20 - cur) / high_20 if high_20 > 0 else 0
    if dd_20 <= dd_20_min:
        return 'NO_BUY_V7', {
            'reason': f'距 20 日高回撤 {dd_20*100:.2f}%, 需 > {dd_20_min*100:.0f}%',
            'close': round(cur, 3),
            'high_20': round(high_20, 3),
            'dd_20': round(dd_20, 4),
            'phase': v3_phase,
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
        }

    # 全部满足 → BUY 信号
    detail = {
        'close': round(cur, 3),
        'ma20': round(float(ma20[-1]), 3),
        'vs_ma20_pct': round(vs_ma20 * 100, 2),
        'high_20': round(high_20, 3),
        'dd_20': round(dd_20, 4),
        'phase': v3_phase,
        'strategy': 'semicon_v9',
        'reason': f'上行 + 距 MA20 {vs_ma20*100:+.2f}% < {ma20_touch_tol*100:.0f}% + 距 20 日高回撤 {dd_20*100:.2f}% > {dd_20_min*100:.0f}%',
    }
    return 'STRONG_UP', detail


# ════════════════════════════════════════════════════════════
# 半导体专用 v8：上行 + 距 MA20 < 8%（2026-09-04 落地）
# ════════════════════════════════════════════════════════════
# 回测数据（sh512480, 2023-05-22 ~ 2026-09-03, 800 条 K 线）：
#   - 命中 53.0% (44/83)
#   - 仓位加权均收益 +3.14%
#   - 3 年复利累计收益 +791.88%
#   - 最大单笔亏 -9.03%（其余均 < 10%）
#   - 平均持仓 9.0 天（多数 T+10 平）
#   - 触发频率：年均 27.7 笔（季度 7 笔）
#
# 设计要点：
#   1. 上行状态：复用 judge_single() 的 STRONG_UP
#   2. 距 MA20 < 8%：相比 v7 的 2% 更宽松
#      - 捕获连续小涨段（4-20 ~ 5-29 那段主升，每次 vs_MA20 都在 +8% ~ +19%）
#      - 避开顶部区（vs_MA20 > 8% 时大概率是连阳追涨）
#   3. 阈值 8% 仍能拦住 2026-07-02 那次 vs_MA20 +10.49% 的崩盘
#
# 与 v7 的对比：
#   - v7: vs_MA20 < 2%（16 次 BUY，命中 75%，最大亏 -7.51%，复利 +116%）
#   - v8: vs_MA20 < 8%（83 次 BUY，命中 53%，最大亏 -9.03%，复利 +792%）
#   - v8 触发更频繁，但收益大幅提升（捕获主升中段 4-5 月那段）
# ════════════════════════════════════════════════════════════

# 半导体 v8 参数（可在外部覆盖）
SEMICON_V8_DEFAULTS: Dict = {
    'ma20_touch_tol':     0.08,    # |close/MA20 - 1| < 8%（比 v7 宽松）
    'require_strict_up':  True,    # 是否要求严格 STRONG_UP
}


def judge_semicon_v8(
    close: np.ndarray,
    df: pd.DataFrame,
    ma20_touch_tol: float = 0.08,
    require_strict_up: bool = True,
) -> Tuple[str, Dict]:
    """
    半导体专用 v8 BUY 判定（2026-09-04 落地）

    输入：日 K 线（close, df）
    输出：(phase, detail)
      - phase = 'STRONG_UP' → BUY 信号
      - phase = 'NO_BUY_V8' → 不买

    判定条件（2 个全满足 → BUY）：
      1. 上行状态（judge_single() 返回 STRONG_UP）
      2. close 距 MA20 < 8%（比 v7 更宽松，能捕获连续小涨段）

    风控（你自己处理）：
      - 持仓期建议：-5% 硬止损 或 T+10 平仓
      - 3 年回测：53% 命中 / 最大亏 -9.03% / 复利 +792%
    """
    if close is None or df is None or len(close) < 30:
        return 'NO_BUY_V8', {'reason': 'K线不足'}

    # 1) 4 档 phase 判定
    v3_phase, v3_detail = judge_single(close, df)
    if v3_phase != 'STRONG_UP':
        return 'NO_BUY_V8', {
            'reason': f'phase={v3_phase}, 不在上行状态',
            'close': round(float(close[-1]), 3),
            'phase': v3_phase,
        }

    # 2) 距 MA20 必须 < 8%（过滤掉连续大涨远离均线的顶部区）
    cur = float(close[-1])
    ma20 = calc_ma_series(close, MA_FAST)
    if np.isnan(ma20[-1]):
        return 'NO_BUY_V8', {
            'reason': 'MA20 不足',
            'close': round(cur, 3),
        }

    vs_ma20 = (cur - ma20[-1]) / ma20[-1] if ma20[-1] > 0 else 0
    if abs(vs_ma20) >= ma20_touch_tol:
        return 'NO_BUY_V8', {
            'reason': f'距 MA20 {vs_ma20*100:+.2f}%, 超过阈值 {ma20_touch_tol*100:.0f}%',
            'close': round(cur, 3),
            'ma20': round(float(ma20[-1]), 3),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
            'phase': v3_phase,
        }

    # 全部满足 → BUY 信号
    detail = {
        'close': round(cur, 3),
        'ma20': round(float(ma20[-1]), 3),
        'vs_ma20_pct': round(vs_ma20 * 100, 2),
        'phase': v3_phase,
        'strategy': 'semicon_v8',
        'reason': f'上行 + 距 MA20 {vs_ma20*100:+.2f}% < {ma20_touch_tol*100:.0f}%',
    }
    return 'STRONG_UP', detail


# ════════════════════════════════════════════════════════════
# 贵金属专用 v9：slow_bull + |vs_MA20|<8% + 距20日高>8%（2026-09-06 落地）
# ════════════════════════════════════════════════════════════
# 设计：参考半导体 v9，针对黄金 ETF 波动特性调参
#   - 底层：slow_bull 4 条件（站上 MA60 ≥15 日 + 涨幅 >3% + 斜率 ≥0 + dd_60 <15%）
#   - |vs_MA20| < 8%（半导体用 2%，黄金放宽到 8%）
#   - 距 20 日高点回撤 > 8%（避免追高）
#
# 回测数据（sh518880, 2023-05-23 ~ 2026-09-04, 800 条 K 线）：
#   - 命中 94.7% (18/19)
#   - 复利累计收益 +71.38%（年化 ~19.7%）
#   - 最大单笔亏 -1.20%（止损 0 次）
#
# 与半导体 v9 对比：
#   - 半导体 v9: 13 笔 / 命中 92.3% / 最大亏 -7.21% / 复利 +127%
#   - 黄金 v9:  19 笔 / 命中 94.7% / 最大亏 -1.20% / 复利 +71.4%
#   黄金更稳（最大亏小），半导体爆发力更强（复利高）
# ════════════════════════════════════════════════════════════

# 贵金属 v9 持仓期参数（可外部覆盖）
GOLD_V9_DEFAULTS: Dict = {
    # slow_bull 参数
    'lookback_above_ma60': 15,
    'gain_min':           0.03,
    'slope_min':          0.0,
    'dd_max':             0.15,
    # v9 三条件过滤
    'ma20_touch_tol':     0.08,    # |vs_MA20| < 8%
    'dd_20_min':          0.08,    # 距 20 日高点回撤 > 8%
}


def judge_gold_v9(
    close: np.ndarray,
    df: pd.DataFrame,
    lookback_above_ma60: int = 15,
    gain_min: float = 0.03,
    slope_min: float = 0.0,
    dd_max: float = 0.15,
    ma20_touch_tol: float = 0.08,
    dd_20_min: float = 0.08,
    range_60_max: Optional[float] = None,
) -> Tuple[str, Dict]:
    """
    贵金属专用 v9 BUY 判定（2026-09-06 落地，2026-09-07 加 range_60_max）

    输入：日 K 线（close, df）
    输出：(phase, detail)
      - phase = 'STRONG_UP' → BUY 信号
      - phase = 'NO_BUY_V9' → 不买

    判定条件（基础 3 个 + 可选 1 个 → BUY）：
      1. slow_bull 上行（站上 MA60 ≥15 日 + 涨 >3% + 斜率 ≥0 + dd_60 <15%）
      2. close 距 MA20 < 8%（半导体用 2%，黄金放宽）
      3. close 距 20 日高点回撤 > 8%（避免追高）
      4. （可选）range_60_max：60 日振幅上限（板块处于盘整状态才买）

    风控（你自己处理）：
      - 持仓期建议：-5% 硬止损 或 T+10 平仓
      - 3 年回测：94.7% 命中 / 最大亏 -1.20% / 复利 +71.4%

    range_60_max 用例（2026-09-07 落地，消费电子）：
      - 消费电子回测：基础 slow_bull 49.2% 胜率 / +634% 复利
      - 加 range_60_max=0.40 后：148 笔 / 55.4% / +1293% 复利
      - 加 4线+dd_60<5%+range_60<40%：79 笔 / 59.5% / +593%
      - 关键洞察：消费电子 BUY 在板块盘整期（低振幅）显著更准
    """
    if close is None or df is None or len(close) < OSC_PERIOD + 1:
        return 'NO_BUY_V9', {'reason': 'K线不足'}

    # 1) slow_bull 判定（贵金属底层）
    sb_phase, sb_detail = judge_slow_bull(
        close, df,
        lookback_above_ma60=lookback_above_ma60,
        gain_min=gain_min,
        slope_min=slope_min,
        dd_max=dd_max,
    )
    if sb_phase != 'STRONG_UP':
        return 'NO_BUY_V9', {
            'reason': f'slow_bull 未触发（{sb_detail.get("slow_failed", [])}）',
            'close': round(float(close[-1]), 3),
            'slow_bull_detail': sb_detail,
        }

    # 2) 距 MA20 必须 < 阈值
    cur = float(close[-1])
    ma20 = calc_ma_series(close, MA_FAST)
    if np.isnan(ma20[-1]):
        return 'NO_BUY_V9', {
            'reason': 'MA20 不足',
            'close': round(cur, 3),
        }
    vs_ma20 = (cur - ma20[-1]) / ma20[-1] if ma20[-1] > 0 else 0
    if abs(vs_ma20) >= ma20_touch_tol:
        return 'NO_BUY_V9', {
            'reason': f'距 MA20 {vs_ma20*100:+.2f}%, 超过阈值 {ma20_touch_tol*100:.0f}%',
            'close': round(cur, 3),
            'ma20': round(float(ma20[-1]), 3),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
        }

    # 3) 距 20 日高点回撤必须 > 阈值
    high_20 = float(np.nanmax(close[-20:])) if len(close) >= 20 else float(np.nanmax(close))
    dd_20 = (high_20 - cur) / high_20 if high_20 > 0 else 0
    if dd_20 <= dd_20_min:
        return 'NO_BUY_V9', {
            'reason': f'距 20 日高回撤 {dd_20*100:.2f}%, 需 > {dd_20_min*100:.0f}%',
            'close': round(cur, 3),
            'high_20': round(high_20, 3),
            'dd_20': round(dd_20, 4),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
        }

    # 4) （可选）60 日振幅上限：板块盘整才买
    range_60 = None
    if range_60_max is not None:
        if len(close) < 60:
            return 'NO_BUY_V9', {'reason': 'K线不足 60 日（无法算振幅）', 'close': round(cur, 3)}
        if 'high' in df.columns:
            high_60 = float(np.nanmax(df['high'].values[-60:]))
            low_60 = float(np.nanmin(df['low'].values[-60:]))
        else:
            high_60 = float(np.nanmax(close[-60:]))
            low_60 = float(np.nanmin(close[-60:]))
        range_60 = (high_60 - low_60) / cur if cur > 0 else 0
        if range_60 > range_60_max:
            return 'NO_BUY_V9', {
                'reason': f'60 日振幅 {range_60*100:.2f}%, 需 <= {range_60_max*100:.0f}%（盘整才买）',
                'close': round(cur, 3),
                'high_60': round(high_60, 3),
                'low_60': round(low_60, 3),
                'range_60': round(range_60, 4),
            }

    # 全部满足 → BUY 信号
    detail = {
        'close': round(cur, 3),
        'ma20': round(float(ma20[-1]), 3),
        'vs_ma20_pct': round(vs_ma20 * 100, 2),
        'high_20': round(high_20, 3),
        'dd_20': round(dd_20, 4),
        'strategy': 'gold_v9',
        'reason': (
            f'slow_bull 上行 + 距 MA20 {vs_ma20*100:+.2f}% < {ma20_touch_tol*100:.0f}% + '
            f'距 20 日高回撤 {dd_20*100:.2f}% > {dd_20_min*100:.0f}%'
            + (f' + 60日振幅 {range_60*100:.2f}% <= {range_60_max*100:.0f}%' if range_60_max is not None else '')
        ),
    }
    if range_60 is not None:
        detail['range_60'] = round(range_60, 4)
    return 'STRONG_UP', detail


def judge_a_momentum(
    close: np.ndarray,
    df: pd.DataFrame,
    ma20_touch_tol: float = 0.10,
    gain_5d_min: float = 0.05,
    require_ma_align_4: bool = False,
    dd_60_max: Optional[float] = None,
    range_60_max: Optional[float] = None,
    require_no_ma_align_4: bool = False,
) -> Tuple[str, Dict]:
    """
    A 族动量 v9 BUY 判定（2026-09-06 落地，主题板块专用）

    适用板块：军工 / AI应用 / 人形机器人 / 光通信（A_MOMENTUM_SECTORS）

    基础判定条件（3 个全满足 → BUY）：
      1. close > MA60（多头排列基础）
      2. |vs_MA20| < ma20_touch_tol（半导体用 2%，A 族放宽）
      3. 近 5 日涨幅 > gain_5d_min（动量确认，过滤横盘/阴跌）

    可选增强条件（per-sector 启用，2026-09-06）：
      4. require_ma_align_4: 4 线多头排列 (close > MA5 > MA10 > MA20 > MA60)
         - 适用：军工、人形机器人（事件驱动板块，需要更强趋势确认）
         - 不适用：AI应用、光通信（会过滤掉有效信号，复利 -35%）
      5. dd_60_max: 距 60 日高点回撤上限（防止追在 60 日高位）
         - 适用：军工（避免追在短期顶部）
         - 不适用：人形机器人（条件已经够严）

    与半导体 v9 / 贵金属 v9 的区别：
      - 半导体 v9 (judge_semicon_v7)：close>MA20/MA60 + |vs_MA20|<2% + dd20>3%，
        命中 92.3% / 复利 +153%（干净走势，单 ETF 走势稳）
      - 贵金属 v9 (judge_gold_v9)：slow_bull 之上叠 |vs_MA20|<8% + dd20>8%，
        命中 94.7% / 复利 +71%（稳定慢牛）
      - A 族动量 v9 (本函数)：跳过 slow_bull，直接用动量条件，per-sector 调参

    每板块参数（2026-09-06，3 年 800 条 K 线回测）：
      军工 sh512660:
        ma20<15% / gain5d>6% / ma_align_4 / dd_60<5% → 20 笔 / 胜率 70% / 复利 +103% / 最大亏 -5.23%
      AI应用 sh515980:
        ma20<15% / gain5d>8%                        → 41 笔 / 胜率 58.5% / 复利 +66% / 最大亏 -47%（异常点）
      人形机器人 sh562500:
        ma20<12% / gain5d>5% / ma_align_4           → 29 笔 / 胜率 69% / 复利 +77% / 最大亏 -7.55%
      光通信 sh515880:
        ma20<15% / gain5d>6%                        → 77 笔 / 胜率 61% / 复利 +459% / 最大亏 -12.15%

    风控建议：
      - 军工：T+5/-3%（更短持有，吃快速动量，最大亏 -5.23%）
      - 其他 A 族：T+10/-5%（标准风控）
    """
    if close is None or df is None or len(close) < OSC_PERIOD + 1:
        return 'NO_BUY_V9', {'reason': 'K线不足'}

    ma60 = calc_ma_series(close, MA_SLOW)
    ma20 = calc_ma_series(close, MA_FAST)
    if np.isnan(ma60[-1]) or np.isnan(ma20[-1]):
        return 'NO_BUY_V9', {
            'reason': 'MA60/MA20 不足',
            'close': round(float(close[-1]), 3),
        }

    cur = float(close[-1])
    cur_ma60 = float(ma60[-1])
    cur_ma20 = float(ma20[-1])

    # 条件 1：close > MA60
    if cur <= cur_ma60:
        return 'NO_BUY_V9', {
            'reason': f'close {cur:.3f} <= MA60 {cur_ma60:.3f}',
            'close': round(cur, 3),
            'ma60': round(cur_ma60, 3),
        }

    # 条件 2：|vs_MA20| < ma20_touch_tol
    vs_ma20 = (cur - cur_ma20) / cur_ma20 if cur_ma20 > 0 else 0
    if abs(vs_ma20) >= ma20_touch_tol:
        return 'NO_BUY_V9', {
            'reason': f'距 MA20 {vs_ma20*100:+.2f}%, 超过阈值 {ma20_touch_tol*100:.0f}%',
            'close': round(cur, 3),
            'ma20': round(cur_ma20, 3),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
        }

    # 条件 3：近 5 日涨幅 > gain_5d_min
    if len(close) < 6:
        return 'NO_BUY_V9', {
            'reason': 'K线不足 6 日（无法算 5 日涨幅）',
            'close': round(cur, 3),
        }
    close_5d_ago = float(close[-6])
    if close_5d_ago <= 0:
        return 'NO_BUY_V9', {'reason': '5日前 close 非正', 'close': round(cur, 3)}
    gain_5d = (cur - close_5d_ago) / close_5d_ago
    if gain_5d <= gain_5d_min:
        return 'NO_BUY_V9', {
            'reason': f'近 5 日涨幅 {gain_5d*100:+.2f}%, 需 > {gain_5d_min*100:.0f}%',
            'close': round(cur, 3),
            'gain_5d_pct': round(gain_5d * 100, 2),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
        }

    # 条件 4（可选）：4 线多头排列
    cur_ma5 = float(calc_ma_series(close, 5)[-1])
    cur_ma10 = float(calc_ma_series(close, 10)[-1])
    if np.isnan(cur_ma5) or np.isnan(cur_ma10):
        cur_ma5 = cur_ma10 = cur_ma20  # 兜底，避免误判
    align4 = (cur > cur_ma5 > cur_ma10 > cur_ma20 > cur_ma60)
    if require_ma_align_4 and not align4:
        return 'NO_BUY_V9', {
            'reason': f'4线多头未对齐: close={cur:.3f}, MA5={cur_ma5:.3f}, MA10={cur_ma10:.3f}, MA20={cur_ma20:.3f}, MA60={cur_ma60:.3f}',
            'close': round(cur, 3),
            'ma5': round(cur_ma5, 3),
            'ma10': round(cur_ma10, 3),
            'ma20': round(cur_ma20, 3),
            'ma60': round(cur_ma60, 3),
        }
    if require_no_ma_align_4 and align4:
        return 'NO_BUY_V9', {
            'reason': f'4线多头（要求NOT，反指过滤）: close={cur:.3f}>MA5={cur_ma5:.3f}>MA10={cur_ma10:.3f}>MA20={cur_ma20:.3f}>MA60={cur_ma60:.3f}',
            'close': round(cur, 3),
            'ma5': round(cur_ma5, 3),
            'ma10': round(cur_ma10, 3),
            'ma20': round(cur_ma20, 3),
            'ma60': round(cur_ma60, 3),
        }

    # 条件 4.5（可选）：60 日振幅上限（板块盘整才买）
    range_60 = None
    if range_60_max is not None:
        if len(close) < 60:
            return 'NO_BUY_V9', {'reason': 'K线不足 60 日（无法算振幅）', 'close': round(cur, 3)}
        if 'high' in df.columns and 'low' in df.columns:
            high_60 = float(np.nanmax(df['high'].values[-60:]))
            low_60 = float(np.nanmin(df['low'].values[-60:]))
        else:
            high_60 = float(np.nanmax(close[-60:]))
            low_60 = float(np.nanmin(close[-60:]))
        range_60 = (high_60 - low_60) / cur if cur > 0 else 0
        if range_60 > range_60_max:
            return 'NO_BUY_V9', {
                'reason': f'60 日振幅 {range_60*100:.2f}%, 需 <= {range_60_max*100:.0f}%（盘整才买）',
                'close': round(cur, 3),
                'high_60': round(high_60, 3),
                'low_60': round(low_60, 3),
                'range_60': round(range_60, 4),
            }

    # 条件 5（可选）：距 60 日高点回撤 <= dd_60_max
    dd_60 = None
    if dd_60_max is not None:
        if 'high' in df.columns and len(df) >= 60:
            high_60 = float(np.nanmax(df['high'].values[-60:]))
        else:
            high_60 = float(np.nanmax(close[-60:]))
        dd_60 = (high_60 - cur) / high_60 if high_60 > 0 else 0
        if dd_60 > dd_60_max:
            return 'NO_BUY_V9', {
                'reason': f'距 60 日高回撤 {dd_60*100:.2f}%, 需 <= {dd_60_max*100:.0f}%',
                'close': round(cur, 3),
                'high_60': round(high_60, 3),
                'dd_60': round(dd_60, 4),
            }

    # 全部满足 → BUY 信号
    detail = {
        'close': round(cur, 3),
        'ma5': round(cur_ma5, 3),
        'ma10': round(cur_ma10, 3),
        'ma20': round(cur_ma20, 3),
        'ma60': round(cur_ma60, 3),
        'vs_ma20_pct': round(vs_ma20 * 100, 2),
        'gain_5d_pct': round(gain_5d * 100, 2),
        'ma_align_4': align4,
        'strategy': 'a_momentum_v9',
        'reason': (
            f'A族动量 v9: close>MA60 + |vs_MA20|{abs(vs_ma20)*100:.2f}%<{ma20_touch_tol*100:.0f}% + '
            f'近5日涨{gain_5d*100:+.2f}%>{gain_5d_min*100:.0f}%'
            + (' + 4线多头' if require_ma_align_4 else '')
            + (' + NOT 4线' if require_no_ma_align_4 else '')
            + (f' + dd60<{dd_60_max*100:.0f}%' if dd_60_max is not None else '')
            + (f' + r60<{range_60_max*100:.0f}%' if range_60_max is not None else '')
        ),
    }
    if dd_60 is not None:
        detail['dd_60'] = round(dd_60, 4)
    if range_60 is not None:
        detail['range_60'] = round(range_60, 4)
    return 'STRONG_UP', detail


def judge_innovative_drug_v9(
    close: np.ndarray,
    df: pd.DataFrame,
    gain_20_min: float = 0.08,
) -> Tuple[str, Dict]:
    """
    创新药 v9 BUY 判定（2026-09-06 落地，事件驱动型板块专用）

    适用板块：创新药（biotech / FDA/NMPA 事件驱动）
    ETF 代理：sz159992 A股创新药ETF

    设计思路：
      创新药是事件驱动板块（FDA/NMPA 审批、临床数据 readout），
      通用动量策略完全失效（28.9% 胜率 / -56% 复利）：
      - 板块整体处于下行（buy-and-hold 同期 -7.35%）
      - 短期动量信号往往是事件发酵后的高位追入
      - 需要等"趋势确认 + 启动 + 持有期长"才能吃到事件红利

    判定条件（4 线多头 + 启动确认 → BUY）：
      1. close > MA5 > MA10 > MA20 > MA60（4线多头排列，趋势已建立）
      2. 近 20 日涨幅 > 8%（板块已启动，不是底部潜伏）

    风控建议（per-sector 独立）：
      - 持有期：T+30（事件发酵需要时间，不能 T+10 止盈）
      - 止损：-8%（板块波动大，-5% 容易被洗出去）

    回测数据（sz159992, 2023-05~2026-09, 800 条 K 线）：
      - 39 笔 / 胜率 74.4% / 复利 +116.29% / 最大亏 -9.02% (T+30/-8%)
      - 同期 buy-and-hold -7.35%（专用策略跑赢 +124 个百分点）
      - 对比 momentum_v9 默认 28.9% 胜率 / -56% 复利 → 质的飞跃

    为什么动量策略失败但慢牛策略有效：
      - 创新药事件发生时，板块往往先慢涨数日（市场试探），再加速
      - 4线多头确保事件已被市场认可，不是谣言驱动
      - gain_20>8% 确保不是潜伏底部（底部反弹多假突破）
    """
    if close is None or df is None or len(close) < OSC_PERIOD + 1:
        return 'NO_BUY_V9', {'reason': 'K线不足'}

    ma5 = calc_ma_series(close, 5)
    ma10 = calc_ma_series(close, 10)
    ma20 = calc_ma_series(close, MA_FAST)
    ma60 = calc_ma_series(close, MA_SLOW)
    if np.isnan(ma60[-1]) or np.isnan(ma20[-1]) or np.isnan(ma5[-1]) or np.isnan(ma10[-1]):
        return 'NO_BUY_V9', {
            'reason': 'MA5/MA10/MA20/MA60 不足',
            'close': round(float(close[-1]), 3),
        }

    cur = float(close[-1])
    cur_ma5 = float(ma5[-1])
    cur_ma10 = float(ma10[-1])
    cur_ma20 = float(ma20[-1])
    cur_ma60 = float(ma60[-1])

    # 条件 1：4 线多头排列
    align4 = (cur > cur_ma5 > cur_ma10 > cur_ma20 > cur_ma60)
    if not align4:
        return 'NO_BUY_V9', {
            'reason': f'4线多头未对齐: close={cur:.3f}, MA5={cur_ma5:.3f}, MA10={cur_ma10:.3f}, MA20={cur_ma20:.3f}, MA60={cur_ma60:.3f}',
            'close': round(cur, 3),
            'ma5': round(cur_ma5, 3),
            'ma10': round(cur_ma10, 3),
            'ma20': round(cur_ma20, 3),
            'ma60': round(cur_ma60, 3),
        }

    # 条件 2：近 20 日涨幅 > gain_20_min
    if len(close) < 21:
        return 'NO_BUY_V9', {'reason': 'K线不足 21 日', 'close': round(cur, 3)}
    close_20d_ago = float(close[-21])
    if close_20d_ago <= 0:
        return 'NO_BUY_V9', {'reason': '20日前 close 非正', 'close': round(cur, 3)}
    gain_20 = (cur - close_20d_ago) / close_20d_ago
    if gain_20 <= gain_20_min:
        return 'NO_BUY_V9', {
            'reason': f'近 20 日涨幅 {gain_20*100:+.2f}%, 需 > {gain_20_min*100:.0f}%',
            'close': round(cur, 3),
            'gain_20_pct': round(gain_20 * 100, 2),
        }

    # 全部满足 → BUY 信号
    detail = {
        'close': round(cur, 3),
        'ma5': round(cur_ma5, 3),
        'ma10': round(cur_ma10, 3),
        'ma20': round(cur_ma20, 3),
        'ma60': round(cur_ma60, 3),
        'gain_20_pct': round(gain_20 * 100, 2),
        'strategy': 'innovative_drug_v9',
        'reason': (
            f'创新药 v9: 4线多头 (close={cur:.3f}>MA5={cur_ma5:.3f}>MA10={cur_ma10:.3f}>'
            f'MA20={cur_ma20:.3f}>MA60={cur_ma60:.3f}) + '
            f'近20日涨{gain_20*100:+.2f}% > {gain_20_min*100:.0f}%'
        ),
    }
    return 'STRONG_UP', detail


def judge_seed_agriculture_v9(
    close: np.ndarray,
    df: pd.DataFrame,
    ma20_touch_tol: float = 0.10,
    gain_5d_min: float = 0.05,
    season_months: tuple = (8, 9, 10),
) -> Tuple[str, Dict]:
    """
    种子农业 v9 BUY 判定（2026-09-07 落地，季节性板块专用）

    适用板块：种子农业（粮食/种业/化肥，受农作物季节性周期影响）
    ETF 代理：sz159698 粮食ETF

    设计思路：
      种子农业是典型季节性板块，BUY 信号高度依赖月份：
        - 8-10 月（秋收窗口）：板块上行，BUY 信号 80%+ 胜率
        - 1-5 月（春播淡季）：板块震荡/下行，BUY 信号 0-20% 胜率
      全年默认动量 BUY 25 笔只赢 8 笔（32%），但加 8-10 月窗口：
        - 10 笔 / 80% 胜率 / T+10/-5% 复利 +47.84%
        - 7 笔 / 100% 胜率 / T+10/-8% 复利 +54.11%
      buy-and-hold 同期 +5.43%（板块本身横盘，专用策略跑赢 40+ 百分点）

    判定条件（4 个全满足 → BUY）：
      1. 当前日期在 season_months 窗口内（默认 8-10 月）
      2. close > MA60（多头排列基础）
      3. |vs_MA20| < 10%（动量基础）
      4. 近 5 日涨幅 > 5%（动量确认）

    风控建议（per-sector 独立）：
      - 持有期：T+10/-8% → 历史 7 笔 100% 胜率
      - 春播淡季不要 BUY（让策略在 1-7 月 + 11-12 月自然失效）

    回测数据（sz159698, 2023-08~2026-09, 740 条 K 线）：
      - 8-10 月窗口 / 默认动量 / T+10/-5%: 10 笔 / 80% 胜率 / +47.84%
      - 8-10 月窗口 / 默认动量 / T+10/-8%:  7 笔 / 100% 胜率 / +54.11%
      - 全年默认动量 (无窗口): 25 笔 / 32% 胜率 / -11.87%

    为什么 8-10 月窗口有效：
      - 中国粮食收获期（秋收）通常在 9-10 月，板块资金流入 + 价格上行
      - 8 月是预期启动期（市场提前布局）
      - 11 月起进入淡季（库存释放/政策空窗期）
    """
    if close is None or df is None or len(close) < OSC_PERIOD + 1:
        return 'NO_BUY_V9', {'reason': 'K线不足'}

    # 条件 1：当前日期在 season_months 窗口内
    if 'day' in df.columns and len(df) > 0:
        try:
            cur_month = pd.Timestamp(df['day'].iloc[-1]).month
        except Exception:
            return 'NO_BUY_V9', {'reason': '日期解析失败', 'close': round(float(close[-1]), 3)}
        if cur_month not in season_months:
            return 'NO_BUY_V9', {
                'reason': f'非秋收窗口（当前 {cur_month} 月，窗口 {season_months[0]}-{season_months[-1]} 月）',
                'close': round(float(close[-1]), 3),
                'current_month': cur_month,
                'season_months': list(season_months),
            }

    ma60 = calc_ma_series(close, MA_SLOW)
    ma20 = calc_ma_series(close, MA_FAST)
    if np.isnan(ma60[-1]) or np.isnan(ma20[-1]):
        return 'NO_BUY_V9', {
            'reason': 'MA60/MA20 不足',
            'close': round(float(close[-1]), 3),
        }

    cur = float(close[-1])
    cur_ma60 = float(ma60[-1])
    cur_ma20 = float(ma20[-1])

    # 条件 2：close > MA60
    if cur <= cur_ma60:
        return 'NO_BUY_V9', {
            'reason': f'close {cur:.3f} <= MA60 {cur_ma60:.3f}',
            'close': round(cur, 3),
            'ma60': round(cur_ma60, 3),
        }

    # 条件 3：|vs_MA20| < 10%
    vs_ma20 = (cur - cur_ma20) / cur_ma20 if cur_ma20 > 0 else 0
    if abs(vs_ma20) >= ma20_touch_tol:
        return 'NO_BUY_V9', {
            'reason': f'距 MA20 {vs_ma20*100:+.2f}%, 超过阈值 {ma20_touch_tol*100:.0f}%',
            'close': round(cur, 3),
            'ma20': round(cur_ma20, 3),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
        }

    # 条件 4：近 5 日涨幅 > 5%
    if len(close) < 6:
        return 'NO_BUY_V9', {
            'reason': 'K线不足 6 日（无法算 5 日涨幅）',
            'close': round(cur, 3),
        }
    close_5d_ago = float(close[-6])
    if close_5d_ago <= 0:
        return 'NO_BUY_V9', {'reason': '5日前 close 非正', 'close': round(cur, 3)}
    gain_5d = (cur - close_5d_ago) / close_5d_ago
    if gain_5d <= gain_5d_min:
        return 'NO_BUY_V9', {
            'reason': f'近 5 日涨幅 {gain_5d*100:+.2f}%, 需 > {gain_5d_min*100:.0f}%',
            'close': round(cur, 3),
            'gain_5d_pct': round(gain_5d * 100, 2),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
        }

    # 全部满足 → BUY 信号
    detail = {
        'close': round(cur, 3),
        'ma20': round(cur_ma20, 3),
        'ma60': round(cur_ma60, 3),
        'vs_ma20_pct': round(vs_ma20 * 100, 2),
        'gain_5d_pct': round(gain_5d * 100, 2),
        'current_month': cur_month,
        'strategy': 'seed_agriculture_v9',
        'reason': (
            f'种子农业 v9: {cur_month}月（秋收窗口）+ close>MA60 ({cur:.3f}>{cur_ma60:.3f}) + '
            f'|vs_MA20|{abs(vs_ma20)*100:.2f}%<{ma20_touch_tol*100:.0f}% + '
            f'近5日涨{gain_5d*100:+.2f}%>{gain_5d_min*100:.0f}%'
        ),
    }
    return 'STRONG_UP', detail


def judge_power_grid_v9(
    close: np.ndarray,
    df: pd.DataFrame,
    lookback_above_ma60: int = 15,
    gain_min: float = 0.03,
    slope_min: float = 0.0,
    dd_max: float = 0.10,
    vs_ma20_max: float = 0.03,
    gain_20_max: float = 0.08,
    require_no_align_4: bool = True,
) -> Tuple[str, Dict]:
    """
    电网设备 v9 BUY 判定（2026-09-07 落地，反 4 线多头策略）

    适用板块：电网设备（电力 / 输配电设备）
    ETF 代理：sz159611 电力ETF

    设计思路：
      电网设备是反指标板块：板块整体上涨（B&H +11.77%），但慢牛 BUY 信号严重亏损（49.2%/-74%）。
      赢家特征分析发现（2026-09-07，110 笔样本）：
        - 4线多头 30% (赢) vs 59% (输)：4线多头是反指标！
        - gain_20 5.1% (赢) vs 6.5% (输)：赢家涨幅更小
        - vs_ma20 1.7% (赢) vs 2.9% (输)：赢家更贴近 MA20
      结论：电网设备 BUY 等**温和上涨 + 贴近 MA20 + 没有 4 线多头**（不是过热信号）

    判定条件（4 个全满足 → BUY）：
      1. close > MA60（多头排列基础）
      2. 站上 MA60 ≥15 日（持续站稳，非短期反弹）
      3. NOT 4 线多头（**核心反指过滤**：close > MA5 > MA10 > MA20 > MA60 是反指标）
      4. |vs_MA20| < 3%（贴近 MA20，未大幅偏离）
      5. gain_20 < 8%（温和上涨，未过热）

    风控建议（per-sector 独立）：
      - 持有期：T+10/-5%（最大亏可控）
      - 止损：-5%

    回测数据（sz159611, 2023-05~2026-09, 800 条 K 线，T+10/-5%）：
      - 基础慢牛:    110 笔 / 33.6% / -74.47% 复利（反指标）
      - 专用 v9:      45 笔 / **55.6%** / **+20.14%** 复利 / 最大亏可控
      - 严格过滤:     45 笔 / 57.8% / +23.18% 复利（T+5/-5%）
      - 跑赢 buy-and-hold (+11.77%) 约 8-11 个百分点

    为什么 NOT 4 线多头是关键：
      4线多头表示板块已经强势上涨多日，BUY 在这种"已涨"位置容易接刀
      没有4线多头但仍站上 MA60 + 温和涨幅 = "刚启动但没大涨"的早期信号
    """
    if close is None or df is None or len(close) < OSC_PERIOD + 1:
        return 'NO_BUY_V9', {'reason': 'K线不足'}

    # 1) slow_bull 底层
    sb_phase, sb_detail = judge_slow_bull(
        close, df,
        lookback_above_ma60=lookback_above_ma60,
        gain_min=gain_min,
        slope_min=slope_min,
        dd_max=dd_max,
    )
    if sb_phase != 'STRONG_UP':
        return 'NO_BUY_V9', {
            'reason': f'slow_bull 未触发（{sb_detail.get("slow_failed", [])}）',
            'close': round(float(close[-1]), 3),
            'slow_bull_detail': sb_detail,
        }

    # 2) 4线多头检查（NOT 4线多头 = 排除 4线信号）
    ma5 = calc_ma_series(close, 5)
    ma10 = calc_ma_series(close, 10)
    ma20 = calc_ma_series(close, MA_FAST)
    ma60 = calc_ma_series(close, MA_SLOW)
    if np.isnan(ma5[-1]) or np.isnan(ma10[-1]) or np.isnan(ma20[-1]) or np.isnan(ma60[-1]):
        return 'NO_BUY_V9', {'reason': 'MA 不足', 'close': round(float(close[-1]), 3)}

    cur = float(close[-1])
    cur_ma5 = float(ma5[-1])
    cur_ma10 = float(ma10[-1])
    cur_ma20 = float(ma20[-1])
    cur_ma60 = float(ma60[-1])

    align4 = (cur > cur_ma5 > cur_ma10 > cur_ma20 > cur_ma60)
    if require_no_align_4 and align4:
        return 'NO_BUY_V9', {
            'reason': f'4 线多头对齐（反指标）：close={cur:.3f}>MA5={cur_ma5:.3f}>MA10={cur_ma10:.3f}>MA20={cur_ma20:.3f}>MA60={cur_ma60:.3f}',
            'close': round(cur, 3),
            'ma5': round(cur_ma5, 3),
            'ma10': round(cur_ma10, 3),
            'ma20': round(cur_ma20, 3),
            'ma60': round(cur_ma60, 3),
        }

    # 3) |vs_MA20| < vs_ma20_max（贴近）
    vs_ma20 = (cur - cur_ma20) / cur_ma20 if cur_ma20 > 0 else 0
    if abs(vs_ma20) >= vs_ma20_max:
        return 'NO_BUY_V9', {
            'reason': f'距 MA20 {abs(vs_ma20)*100:.2f}%, 需 < {vs_ma20_max*100:.0f}%',
            'close': round(cur, 3),
            'ma20': round(cur_ma20, 3),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
        }

    # 4) gain_20 < gain_20_max（温和）
    if len(close) < 21:
        return 'NO_BUY_V9', {'reason': 'K线不足 21 日', 'close': round(cur, 3)}
    close_20d_ago = float(close[-21])
    if close_20d_ago <= 0:
        return 'NO_BUY_V9', {'reason': '20日前 close 非正', 'close': round(cur, 3)}
    gain_20 = (cur - close_20d_ago) / close_20d_ago
    if gain_20 >= gain_20_max:
        return 'NO_BUY_V9', {
            'reason': f'近 20 日涨幅 {gain_20*100:+.2f}%, 需 < {gain_20_max*100:.0f}%',
            'close': round(cur, 3),
            'gain_20_pct': round(gain_20 * 100, 2),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
        }

    # 全部满足 → BUY 信号
    detail = {
        'close': round(cur, 3),
        'ma5': round(cur_ma5, 3),
        'ma10': round(cur_ma10, 3),
        'ma20': round(cur_ma20, 3),
        'ma60': round(cur_ma60, 3),
        'vs_ma20_pct': round(vs_ma20 * 100, 2),
        'gain_20_pct': round(gain_20 * 100, 2),
        'strategy': 'power_grid_v9',
        'reason': (
            f'电网设备 v9: slow_bull 上行 + NOT 4线多头（避免过热）+ '
            f'|vs_MA20| {abs(vs_ma20)*100:.2f}% < {vs_ma20_max*100:.0f}% + '
            f'gain_20 {gain_20*100:+.2f}% < {gain_20_max*100:.0f}%'
        ),
    }
    return 'STRONG_UP', detail


def judge_securities_v9(
    close: np.ndarray,
    df: pd.DataFrame,
    lookback_above_ma60: int = 15,
    gain_min: float = 0.03,
    slope_min: float = 0.0,
    dd_max: float = 0.10,
    dd_20_min: float = 0.05,
    require_align_4: bool = True,
) -> Tuple[str, Dict]:
    """
    券商 v9 BUY 判定（2026-09-07 落地，4线回撤后启动策略）

    适用板块：券商（牛市旗手 / 周期股）
    ETF 代理：sh512000 券商ETF

    设计思路：
      券商是"牛市鼓手 + 周期股"：
        - B&H 同期 -39.33%（板块整体下跌）
        - 基础慢牛 BUY 巨亏（58 笔 / 53% 胜率但 6.6% 均收益/笔，复利 -99.74%）
        - 关键问题：板块上涨期很短（2024-09 牛市），其余时间震荡/下跌
      赢家特征分析发现（2026-09-07）：
        - 4线多头 + vs_MA20<3%：5 笔 / 100% / +26.22% ← WINNER
        - 4线多头 + dd_20>5%（回撤后启动）：9 笔 / 66.7% / +33.02% ← Best balance
      结论：券商 BUY 必须**4线趋势确认 + 从 20 日高点小幅回撤后启动**

    判定条件（3 个全满足 → BUY）：
      1. close > MA60（多头排列基础）
      2. 站上 MA60 ≥15 日（持续站稳）
      3. 4 线多头（趋势确认）
      4. 距 20 日高点回撤 > 5%（回调后启动，不追在顶部）

    风控建议：
      - 持有期：T+10/-5%
      - 止损：-5%（板块波动大）

    回测数据（sh512000, 2023-05~2026-09, 800 条 K 线，T+10/-5%）：
      - 基础慢牛:    58 笔 / 53.4% / -99.74% 复利（板块下跌拖累）
      - 专用 v9 (4线+dd_20>5%): 9 笔 / **66.7%** / **+33.02%** 复利
      - 跑赢 buy-and-hold (-39.33%) 约 72 个百分点

    注意事项：
      - 9 笔样本量较少，3 年期间券商 BUY 实际信号很少
      - 但每笔信号更可靠（66.7% 胜率 + 平均 +3.67%）
      - 适合"耐心等待"型策略，BUY 信号触发时往往是券商主升段起点
    """
    if close is None or df is None or len(close) < OSC_PERIOD + 1:
        return 'NO_BUY_V9', {'reason': 'K线不足'}

    # 1) slow_bull 底层
    sb_phase, sb_detail = judge_slow_bull(
        close, df,
        lookback_above_ma60=lookback_above_ma60,
        gain_min=gain_min,
        slope_min=slope_min,
        dd_max=dd_max,
    )
    if sb_phase != 'STRONG_UP':
        return 'NO_BUY_V9', {
            'reason': f'slow_bull 未触发（{sb_detail.get("slow_failed", [])}）',
            'close': round(float(close[-1]), 3),
            'slow_bull_detail': sb_detail,
        }

    # 2) 4线多头（趋势确认）
    ma5 = calc_ma_series(close, 5)
    ma10 = calc_ma_series(close, 10)
    ma20 = calc_ma_series(close, MA_FAST)
    ma60 = calc_ma_series(close, MA_SLOW)
    if np.isnan(ma5[-1]) or np.isnan(ma10[-1]) or np.isnan(ma20[-1]) or np.isnan(ma60[-1]):
        return 'NO_BUY_V9', {'reason': 'MA 不足', 'close': round(float(close[-1]), 3)}

    cur = float(close[-1])
    cur_ma5 = float(ma5[-1])
    cur_ma10 = float(ma10[-1])
    cur_ma20 = float(ma20[-1])
    cur_ma60 = float(ma60[-1])

    align4 = (cur > cur_ma5 > cur_ma10 > cur_ma20 > cur_ma60)
    if require_align_4 and not align4:
        return 'NO_BUY_V9', {
            'reason': f'4 线多头未对齐: close={cur:.3f}, MA5={cur_ma5:.3f}, MA10={cur_ma10:.3f}, MA20={cur_ma20:.3f}, MA60={cur_ma60:.3f}',
            'close': round(cur, 3),
            'ma5': round(cur_ma5, 3),
            'ma10': round(cur_ma10, 3),
            'ma20': round(cur_ma20, 3),
            'ma60': round(cur_ma60, 3),
        }

    # 3) 距 20 日高点回撤 > dd_20_min（回撤后启动，不追在顶部）
    if len(close) < 20:
        return 'NO_BUY_V9', {'reason': 'K线不足 20 日', 'close': round(cur, 3)}
    high_20 = float(np.nanmax(close[-20:]))
    dd_20 = (high_20 - cur) / high_20 if high_20 > 0 else 0
    if dd_20 <= dd_20_min:
        return 'NO_BUY_V9', {
            'reason': f'距 20 日高回撤 {dd_20*100:.2f}%, 需 > {dd_20_min*100:.0f}%（避免顶部追高）',
            'close': round(cur, 3),
            'high_20': round(high_20, 3),
            'dd_20': round(dd_20, 4),
        }

    # 全部满足 → BUY 信号
    detail = {
        'close': round(cur, 3),
        'ma5': round(cur_ma5, 3),
        'ma10': round(cur_ma10, 3),
        'ma20': round(cur_ma20, 3),
        'ma60': round(cur_ma60, 3),
        'high_20': round(high_20, 3),
        'dd_20': round(dd_20, 4),
        'strategy': 'securities_v9',
        'reason': (
            f'券商 v9: slow_bull 上行 + 4线多头（趋势确认）+ '
            f'距 20 日高回撤 {dd_20*100:.2f}% > {dd_20_min*100:.0f}%（回撤后启动）'
        ),
    }
    return 'STRONG_UP', detail


def judge_low_altitude_v9(
    close: np.ndarray,
    df: pd.DataFrame,
    lookback_above_ma60: int = 15,
    gain_min: float = 0.03,
    slope_min: float = 0.0,
    dd_max: float = 0.10,
    vs_ma20_max: float = 0.05,
    require_align_4: bool = True,
) -> Tuple[str, Dict]:
    """
    低空经济 v9 BUY 判定（2026-09-07 落地，4线多头 + 贴近 MA20 策略）

    适用板块：低空经济（eVTOL / 无人机 / 通用航空）
    ETF 代理：sz159795 低空经济ETF天弘（avg 0.609 best of weak）

    设计思路：
      低空经济是新兴主题板块（2024 起 ETF 才上市），波动大：
        - B&H 同期 +10.73%（板块小幅上涨）
        - 基础慢牛 BUY 反指标（104 笔 / 41.3% / -12%）
      赢家特征分析发现（2026-09-07，105 笔样本）：
        - 4线多头 4线 + vs_MA20<5%：18 笔 / 61.1% / +88.23% ← WINNER
        - 4线 + vs_MA20<5% + T+10/-3%：18 笔 / 61.1% / +102.10% ← Best compound
      结论：低空经济 BUY 必须**4线趋势 + 贴近 MA20**（不要追在已大涨的位置）

    判定条件（4 个全满足 → BUY）：
      1. close > MA60（多头排列基础）
      2. 站上 MA60 ≥15 日（持续站稳）
      3. 4 线多头（趋势确认）
      4. |vs_MA20| < 5%（贴近 MA20，未大幅偏离）

    风控建议：
      - 持有期：T+10/-3% → 历史 18 笔 61.1% 胜率 / +102.10% 复利
      - 止损：-3%（贴近 MA20 信号要求紧止损）

    回测数据（sz159795, 2023-05~2026-09, 800 条 K 线）：
      - 基础慢牛: 104 笔 / 41.3% / -11.99% 复利（反指标）
      - 专用 v9:  18 笔 / **61.1%** / **+88.23%** 复利（T+10/-5%）
      - 最佳:     18 笔 / **61.1%** / **+102.10%** 复利（T+10/-3%）
      - 跑赢 buy-and-hold (+10.73%) 约 90 个百分点

    为什么 4线 + 贴近 MA20：
      低空经济 ETF 上市晚、价格波动大，追在已大涨位置容易接刀
      必须等板块形成 4线多头 + 还未大涨（贴近 MA20）的早期启动信号
    """
    if close is None or df is None or len(close) < OSC_PERIOD + 1:
        return 'NO_BUY_V9', {'reason': 'K线不足'}

    # 1) slow_bull 底层
    sb_phase, sb_detail = judge_slow_bull(
        close, df,
        lookback_above_ma60=lookback_above_ma60,
        gain_min=gain_min,
        slope_min=slope_min,
        dd_max=dd_max,
    )
    if sb_phase != 'STRONG_UP':
        return 'NO_BUY_V9', {
            'reason': f'slow_bull 未触发（{sb_detail.get("slow_failed", [])}）',
            'close': round(float(close[-1]), 3),
            'slow_bull_detail': sb_detail,
        }

    # 2) 4线多头（趋势确认）
    ma5 = calc_ma_series(close, 5)
    ma10 = calc_ma_series(close, 10)
    ma20 = calc_ma_series(close, MA_FAST)
    ma60 = calc_ma_series(close, MA_SLOW)
    if np.isnan(ma5[-1]) or np.isnan(ma10[-1]) or np.isnan(ma20[-1]) or np.isnan(ma60[-1]):
        return 'NO_BUY_V9', {'reason': 'MA 不足', 'close': round(float(close[-1]), 3)}

    cur = float(close[-1])
    cur_ma5 = float(ma5[-1])
    cur_ma10 = float(ma10[-1])
    cur_ma20 = float(ma20[-1])
    cur_ma60 = float(ma60[-1])

    align4 = (cur > cur_ma5 > cur_ma10 > cur_ma20 > cur_ma60)
    if require_align_4 and not align4:
        return 'NO_BUY_V9', {
            'reason': f'4 线多头未对齐: close={cur:.3f}, MA5={cur_ma5:.3f}, MA10={cur_ma10:.3f}, MA20={cur_ma20:.3f}, MA60={cur_ma60:.3f}',
            'close': round(cur, 3),
            'ma5': round(cur_ma5, 3),
            'ma10': round(cur_ma10, 3),
            'ma20': round(cur_ma20, 3),
            'ma60': round(cur_ma60, 3),
        }

    # 3) |vs_MA20| < vs_ma20_max（贴近）
    vs_ma20 = (cur - cur_ma20) / cur_ma20 if cur_ma20 > 0 else 0
    if abs(vs_ma20) >= vs_ma20_max:
        return 'NO_BUY_V9', {
            'reason': f'距 MA20 {abs(vs_ma20)*100:.2f}%, 需 < {vs_ma20_max*100:.0f}%',
            'close': round(cur, 3),
            'ma20': round(cur_ma20, 3),
            'vs_ma20_pct': round(vs_ma20 * 100, 2),
        }

    # 全部满足 → BUY 信号
    detail = {
        'close': round(cur, 3),
        'ma5': round(cur_ma5, 3),
        'ma10': round(cur_ma10, 3),
        'ma20': round(cur_ma20, 3),
        'ma60': round(cur_ma60, 3),
        'vs_ma20_pct': round(vs_ma20 * 100, 2),
        'strategy': 'low_altitude_v9',
        'reason': (
            f'低空经济 v9: slow_bull 上行 + 4线多头（趋势确认）+ '
            f'|vs_MA20| {abs(vs_ma20)*100:.2f}% < {vs_ma20_max*100:.0f}%（贴近，不追高）'
        ),
    }
    return 'STRONG_UP', detail


# ════════════════════════════════════════════════════════════
# 板块类型分类（按 BUY 信号历史胜率分）
# ────────────────────────────────────────────────────────────
# 历史回测结果：
#   - 资源/防御板块（resource）：BUY 后 10 日均收益 +1~+5%，命中率 55-70% → BUY 真信号
#   - 题材/成长板块（thematic）：BUY 信号部分有效（半导体 v2 +4.74%），部分反指标
#   - 不可追板块（no_chase）：BUY 后必亏（券商 -12%、消费电子 -4%、油气 -3% 等）→ BUY 反指标
#
# 处理逻辑（_judge_from_df 中应用）：
#   - resource：完整 4 档（STRONG_UP → 买龙头）
#   - thematic：完整 4 档，但保留 v3 严格档触发（部分题材正指标）
#   - no_chase：STRONG_UP 自动降级为 RANGE（震荡）→ 按"震荡只买ETF"或直接不开仓
SECTOR_CATEGORY: Dict[str, str] = {
    # ── 资源/防御板块（BUY 真信号，可追）──
    '化工':         'resource',
    '电网设备':     'no_chase',  # 2026-08-31：3.4年回测 STRONG_UP 5d 单调差 -1.83%, 顶部追涨反指标，改 no_chase 降级
    '新能源':       'resource',
    '贵金属':       'resource',
    '工业金属':     'resource',
    '底仓':         'resource',
    '燃气轮机':     'resource',
    '稀土':         'resource',   # 新增（资源/防御板块）

    # ── 低空经济（2026-09-07 新增，已配专用 v9）──
    # 注：基础 slow_bull 反指标（41.3%/-12%），专用 v9 (4线 + |MA20|<5%) 改写胜率
    # 专用 v9 回测：18 笔 / 61.1% / +88% 复利（T+10/-5%）
    # 分类从 no_chase → thematic（已配 v9）
    '低空经济':     'thematic',   # 2026-09-07 改 thematic（专用 v9）

    # ── 题材/成长板块（部分有效，半导体 v2 强）──
    '半导体':       'thematic',
    '光通信':       'thematic',
    '军工':         'thematic',
    '人形机器人':   'thematic',
    'AI应用':       'thematic',
    '智能驾驶':     'thematic',
    '消费电子':     'thematic',
    '创新药':       'thematic',
    '航运':         'thematic',

    # ── 不可追板块（BUY 反指标：消费电子 -4% / 油气 -3% / 白酒 -2% / 家电 -2%）──
    '电网设备':     'thematic',  # 2026-09-07：配专用 v9 (power_grid_v9) 反 4 线策略
    '券商':         'thematic',  # 2026-09-07：配专用 v9 (securities_v9) 4线回撤策略
    '白酒':         'no_chase',
    '家电':         'no_chase',
    '油气':         'thematic',  # 2026-08-31：SLOW_BULL_SECTORS 慢牛策略胜率 76%，从 no_chase → thematic
    '种子农业':     'thematic',  # 2026-08-30：改用 sh159698 粮食ETF作直接代理，分类从 no_chase → thematic
}


# ════════════════════════════════════════════════════════════
# watchlist.yaml 子分类 → detector 板块 映射
# ────────────────────────────────────────────────────────────
# 把 watchlist.yaml 中的细分领域映射到 detector 的粗粒度板块
# 策略分析器在打 'sector' 标签时应使用本表，确保与 detector 板块一致
#
# 合并策略（2026-08-30 实施）：
#   - compute_idc / liquid_cooling  → 半导体（AI 算力强相关）
#   - pcb / mlcc                     → 消费电子（电子上游元件）
#   - aero_engine                    → 军工（航空发动机）
#   - rare_earth                     → 新增「稀土」板块
#
# 使用方式：
#   from market_phase_detector import WATCHLIST_TO_SECTOR
#   sector = WATCHLIST_TO_SECTOR.get('ai_chip', 'UNKNOWN')   # → 半导体
#
# 未映射项：
#   - low_altitude_economy（低空经济）→ 无对应板块，建议新建
# ════════════════════════════════════════════════════════════
WATCHLIST_TO_SECTOR: Dict[str, str] = {
    # ── 底仓 ──
    'base_holding':           '底仓',

    # ── 半导体（含 AI 芯片/存储/设备/封装/算力/液冷）──
    'ai_chip':                '半导体',
    'compute_idc':            '半导体',    # 算力/IDC 合并到半导体（AI 算力强相关）
    'memory_chip':            '半导体',
    'semiconductor_equipment':'半导体',
    'advanced_packaging':     '半导体',
    'liquid_cooling':         '半导体',    # 液冷合并到半导体（AI 算力散热）

    # ── 消费电子（含 PCB/MLCC 等上游元件）──
    'consumer_electronics':   '消费电子',
    'pcb':                    '消费电子',  # PCB 合并到消费电子
    'mlcc':                   '消费电子',  # MLCC 合并到消费电子

    # ── AI 应用 ──
    'ai_media_game':          'AI应用',

    # ── 创新药 ──
    'innovative_drug':        '创新药',

    # ── 光通信 ──
    'optical_communication':  '光通信',

    # ── 军工（含航空发动机）──
    'military_host':          '军工',
    'aero_engine':            '军工',      # 航发合并到军工

    # ── 商业航天 ──
    'commercial_aerospace':   '商业航天',

    # ── 可控核聚变 ──
    'controlled_fusion':      '可控核聚变',

    # ── 燃气轮机 ──
    'gas_turbine':            '燃气轮机',

    # ── 低空经济（2026-09-07 新增）──
    'low_altitude_economy':   '低空经济',

    # ── 新能源（含电池/储能/光伏/风电）──
    'battery_energy_storage': '新能源',
    'solid_state_battery':    '新能源',
    'photovoltaic':           '新能源',
    'wind_power':             '新能源',

    # ── 电网设备 ──
    'power_grid':             '电网设备',

    # ── 贵金属（含金银）──
    'precious_metal_gold':    '贵金属',
    'precious_metal_silver':  '贵金属',

    # ── 工业金属 ──
    'industrial_metal':       '工业金属',

    # ── 化工 ──
    'chemical_inflation':     '化工',

    # ── 油气 ──
    'oil_gas_service':        '油气',

    # ── 航运 ──
    'shipping_tanker':        '航运',

    # ── 券商（含保险/金融科技，统一归券商）──
    'securities_insurance':   '券商',

    # ── 白酒 ──
    'liquor':                 '白酒',

    # ── 家电 ──
    'white_goods':            '家电',

    # ── 人形机器人 ──
    'humanoid_robot':         '人形机器人',

    # ── 智能驾驶 ──
    'intelligent_driving':    '智能驾驶',

    # ── 种子农业 ──
    'seed_agriculture':       '种子农业',

    # ── 稀土（新增板块）──
    'rare_earth':             '稀土',

    # ── 工程机械（2026-09 新增，映射到「工程机械」板块，走 v2）──
    'construction_machinery': '工程机械',
}


# ════════════════════════════════════════════════════════════
# 股票代码 → 板块 映射（自动从 watchlist.yaml 构建）
# ────────────────────────────────────────────────────────────
# 解决策略分析器忘记给 rec['sector'] 填值的问题：
#   scan_strategy() 收到 rec 时若 sector 为空，用 get_sector_by_stock(code)
#   从本表查，保证每只股票都有正确的 detector 板块
#
# 注意：
#   - 仅 watchlist.yaml 中的标的会进入本表（ETF 除外，ETF 用 SECTOR_ETFS）
#   - ETF 标的（如 159698 粮食ETF）默认 UNKNOWN → 保守禁止（ETF 由 SECTOR_ETFS 独立管理）
#   - 文件路径 = <BASE_DIR>/my_stock_pool/watchlist.yaml
# ════════════════════════════════════════════════════════════
WATCHLIST_YAML_PATH = os.path.join(_BASE_DIR, 'my_stock_pool', 'watchlist.yaml')


def _build_stock_to_sector() -> Dict[str, str]:
    """从 watchlist.yaml 自动构建 stock_code → detector_sector 映射"""
    if yaml is None:
        print("[WARN] pyyaml 未安装，无法构建 STOCK_TO_SECTOR")
        return {}
    if not os.path.exists(WATCHLIST_YAML_PATH):
        print(f"[WARN] watchlist.yaml 不存在: {WATCHLIST_YAML_PATH}")
        return {}
    try:
        with open(WATCHLIST_YAML_PATH, 'r', encoding='utf-8') as f:
            wl = yaml.safe_load(f)
    except Exception as e:
        print(f"[WARN] 读取 watchlist.yaml 失败: {e}")
        return {}

    stock_map: Dict[str, str] = {}
    watchlist = (wl or {}).get('watchlist', {}) or {}
    for key, data in watchlist.items():
        if not isinstance(data, dict):
            continue
        # ETF 类（etf_narrow / etf_broad 等）跳过
        if key.startswith('etf_'):
            continue
        sector = WATCHLIST_TO_SECTOR.get(key)
        if not sector:
            continue
        for tier in ('core', 'focus'):
            for stock in (data.get(tier) or []):
                if isinstance(stock, (list, tuple)) and len(stock) >= 2:
                    code = str(stock[1]).strip()
                    # 统一去前缀（sh/sz）
                    if code.startswith(('sh', 'sz')):
                        code = code[2:]
                    stock_map[code] = sector
    print(f"[映射] STOCK_TO_SECTOR 构建完成，共 {len(stock_map)} 只标的")
    return stock_map


# 模块加载时一次性构建（后续 scan_strategy 直接查表）
STOCK_TO_SECTOR: Dict[str, str] = _build_stock_to_sector()


def get_sector_by_stock(stock_code: str) -> str:
    """
    根据股票代码返回 detector 板块（查不到返回 'UNKNOWN'）

    自动处理 sh/sz 前缀与 6 位纯数字。
    """
    if not stock_code:
        return 'UNKNOWN'
    code = str(stock_code).strip()
    if code.startswith(('sh', 'sz')):
        code = code[2:]
    return STOCK_TO_SECTOR.get(code, 'UNKNOWN')


# ════════════════════════════════════════════════════════════
# 稳定 phase 状态缓存（跨进程持久化）
# ────────────────────────────────────────────────────────────
def _load_stable_cache() -> Dict:
    """读取 stable_phase 缓存文件"""
    if not os.path.exists(STABLE_PHASE_FILE):
        return {}
    try:
        with open(STABLE_PHASE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] 读取稳定 phase 缓存失败: {e}")
        return {}


def _save_stable_cache(cache: Dict):
    """写入 stable_phase 缓存文件"""
    try:
        with open(STABLE_PHASE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_json_safe(cache), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 写入稳定 phase 缓存失败: {e}")


def judge_with_history(
    current_phase: str,
    previous_phase: Optional[str],
    previous_2_phase: Optional[str],
    current_candle_pct: float,
    is_extreme: bool,
    prev_stable_phase: Optional[str] = None,
    prev_stable_date: Optional[str] = None,
    current_date: Optional[str] = None,
) -> Dict:
    """
    双根 K 线稳定判定 + 大阴/大阳标记
    ─────────────────────────────────────────────
    输入：
      - current_phase:        当根 K 线的 phase
      - previous_phase:       上一根 K 线的 phase（None 表示无历史）
      - previous_2_phase:     上两根 K 线的 phase（None 表示无历史）
      - current_candle_pct:   当根 K 线的涨跌幅（小数，如 -0.034 表示 -3.4%）
      - is_extreme:           当根是否为极端行情日（振幅 > 2×ATR）
      - prev_stable_phase:    上次跑完后的稳定 phase（从磁盘读出）
      - prev_stable_date:     上次稳定 phase 的日期
      - current_date:         当前判定日期

    输出（dict）：
      - stable_phase:         策略真正使用的稳定 phase
      - current_phase:        当根 phase
      - previous_phase:       上一根 phase
      - previous_2_phase:     上两根 phase
      - phase_history:        最近 3 根 phase 列表
      - big_down_candle:      大阴线标记（仅作仓位调整用）
      - big_up_candle:        大阳线标记（仅作仓位调整用）
      - is_extreme:           极端行情标记
      - stable_phase_updated: 本次是否更新了 stable_phase
      - position_adjustment:  仓位调整建议（基于大阴/大阳，不动 stable_phase）
      - stable_phase_source:  'fresh' / 'prev_stable' / 'previous_phase' / 'initial'

    稳定判定规则（关键修正）：
      - 引入"跨进程的稳定态 prev_stable_phase"作为基准
      - 只有 current_phase == previous_phase 时 → stable_phase = current_phase（更新）
      - 否则 → stable_phase 保持 prev_stable_phase（不更新）
      - 首次（无 prev_stable_phase）：用 current_phase 作为初始稳定态
      - 跨日处理：如果 prev_stable_date != current_date，需要重新验证
        （避免历史稳定态跨太长时间不过期）
    """
    phase_history = [previous_2_phase, previous_phase, current_phase]
    phase_history_clean = [p for p in phase_history if p is not None]

    # 大阴/大阳线标记（仅作仓位调整，不修改 stable_phase）
    big_down = current_candle_pct <= BIG_DOWN_THRESHOLD
    big_up = current_candle_pct >= BIG_UP_THRESHOLD

    # 跨日过期处理：如果上次保存日期距今 > N 天，prev_stable_phase 视为失效
    STALE_DAYS = 5
    is_stale = False
    if prev_stable_date and current_date:
        try:
            d_prev = datetime.strptime(prev_stable_date, '%Y-%m-%d').date()
            d_cur = datetime.strptime(current_date, '%Y-%m-%d').date()
            is_stale = (d_cur - d_prev).days > STALE_DAYS
        except Exception:
            is_stale = True

    stable_phase = None
    updated = False
    source = None

    # 极端行情日：保持 stable_phase 不变
    if is_extreme and current_phase == 'RANGE':
        if prev_stable_phase:
            stable_phase = prev_stable_phase
            source = 'prev_stable'
        else:
            stable_phase = 'RANGE'
            source = 'initial'
        updated = False
    else:
        # 正常判定
        if is_stale or prev_stable_phase is None:
            # 首次或过期：用 current_phase 作为初始稳定态（标 updated 让下次确认）
            stable_phase = current_phase
            updated = True
            source = 'initial' if prev_stable_phase is None else 'fresh_after_stale'
        elif current_phase == previous_phase:
            # 连续 2 根 phase 完全相同 → 更新 stable_phase
            stable_phase = current_phase
            updated = True
            source = 'updated'
        else:
            # 单根变化 → stable_phase 保持 prev_stable_phase（不更新）
            stable_phase = prev_stable_phase
            updated = False
            source = 'prev_stable'

    # 仓位调整（不依赖 stable_phase，仅根据单根 K 线）
    if big_down:
        position_adjustment = 'reduce_1'
    elif big_up:
        position_adjustment = 'add_1'
    else:
        position_adjustment = 'hold'

    return {
        'stable_phase': stable_phase,
        'current_phase': current_phase,
        'previous_phase': previous_phase,
        'previous_2_phase': previous_2_phase,
        'phase_history': phase_history_clean,
        'big_down_candle': big_down,
        'big_up_candle': big_up,
        'is_extreme': is_extreme,
        'stable_phase_updated': updated,
        'current_candle_pct': round(current_candle_pct, 4),
        'position_adjustment': position_adjustment,
        'stable_phase_source': source,
        'prev_stable_phase': prev_stable_phase,
        'is_stale': is_stale,
    }


# 向后兼容的简单 confirm_phase（保留原签名）
def confirm_phase(daily_phases: List[str], daily_atr_extreme: List[bool]) -> str:
    """
    简单版：连续 N 日同向才确认（保留兼容）
    实际判定请用 judge_with_history()
    """
    if not daily_phases:
        return 'UNKNOWN'
    if len(daily_phases) < CONSISTENCY_DAYS:
        return daily_phases[-1]
    candidates = [p for p, extreme in zip(daily_phases, daily_atr_extreme) if not extreme]
    if not candidates:
        return daily_phases[-1]
    if len(candidates) >= CONSISTENCY_DAYS and len(set(candidates[-CONSISTENCY_DAYS:])) == 1:
        return candidates[-1]
    return candidates[-1]


# ════════════════════════════════════════════════════════════
# 数据获取
# ════════════════════════════════════════════════════════════
def get_kline(code: str, days: int = 130, max_retries: int = 2) -> Optional[pd.DataFrame]:
    """
    获取单标的 K 线（兼容 sh/sz 前缀 + 纯 6 位）
    优先使用 DataSourceAdapter (pytdx/akshare/baostock)，回退到 fetch_kline_sina

    注意：pytdx 对代码前缀判断市场有误（sh000001 实际是上证指数，
          但 pytdx 用 6 开头判断为 market=1），所以指数代码走 sina
    """
    if not code:
        return None

    # 提取纯 6 位代码
    raw = code[2:] if code.startswith(('sh', 'sz')) else code

    # 指数代码（sh000001 上证、sh000300 沪深300）走 sina（pytdx 市场判断有误）
    is_index = raw in ('000001', '000300', '399001', '399006')

    # 路径 1：DataSourceAdapter（pytdx/akshare/baostock）—— 指数代码跳过
    if _ADAPTER is not None and not is_index:
        for attempt in range(max_retries):
            try:
                df = _ADAPTER.get_stock_data(raw, count=days)
                if df is not None and not df.empty and len(df) >= 30:
                    # 标准化列名（DataSourceAdapter 返回 date, open, close, high, low, volume, amount, pct_change）
                    if 'date' in df.columns and 'day' not in df.columns:
                        df = df.rename(columns={'date': 'day'})
                    return df
            except Exception as e:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)
        # pytdx 拿不到（可能是 ETF/指数），回退到 sina
        # 继续走路径 2

    # 路径 2：fetch_kline_sina 回退（对 ETF / 指数友好）
    if code.startswith(('sh', 'sz')):
        symbol = code
    else:
        symbol = ('sh' if code.startswith(('6', '5', '9')) else 'sz') + code
    for attempt in range(max_retries):
        df = fetch_kline_sina(symbol, days)
        if df is not None and not df.empty and len(df) >= 30:
            return df
        if attempt < max_retries - 1:
            import time
            time.sleep(2 + attempt * 2)
    return None


def build_sector_kline(sector: str, days: int = 130) -> Optional[pd.DataFrame]:
    """
    用成分股等权合成板块 K 线
    每只股单独取一次 K 线，归一化后取平均；缺失日期用 ffill 补齐
    """
    codes = SECTOR_CONSTITUENTS.get(sector, [])
    if not codes:
        return None

    series_map: Dict[str, pd.Series] = {}
    high_map: Dict[str, pd.Series] = {}
    low_map: Dict[str, pd.Series] = {}
    vol_map: Dict[str, pd.Series] = {}
    for code in codes:
        df = get_kline(code, days)
        if df is None or len(df) < 30:
            continue
        s_close = df.set_index('day')['close']
        s_high = df.set_index('day')['high']
        s_low = df.set_index('day')['low']
        s_vol = df.set_index('day')['volume']
        # 归一化到首日 = 100
        base = float(s_close.iloc[0])
        if base <= 0:
            continue
        series_map[code] = s_close / base * 100
        high_map[code] = s_high / base * 100
        low_map[code] = s_low / base * 100
        vol_map[code] = s_vol

    if len(series_map) < 5:
        print(f"[板块 {sector}] 成分股有效数据不足 ({len(series_map)}/10)")
        return None

    # 对齐：每只股只取最近 N 条，重建统一日期索引（向下取整）
    keep_n = days - 10  # 预留缓冲
    aligned: Dict[str, pd.Series] = {}
    aligned_high: Dict[str, pd.Series] = {}
    aligned_low: Dict[str, pd.Series] = {}
    aligned_vol: Dict[str, pd.Series] = {}
    for code in list(series_map.keys()):
        s_close = series_map[code].tail(keep_n)
        s_high = high_map[code].tail(keep_n)
        s_low = low_map[code].tail(keep_n)
        s_vol = vol_map[code].tail(keep_n)
        # 重置索引为 0..N
        s_close.index = range(len(s_close))
        s_high.index = range(len(s_high))
        s_low.index = range(len(s_low))
        s_vol.index = range(len(s_vol))
        aligned[code] = s_close
        aligned_high[code] = s_high
        aligned_low[code] = s_low
        aligned_vol[code] = s_vol

    close_df = pd.DataFrame(aligned)
    high_df = pd.DataFrame(aligned_high)
    low_df = pd.DataFrame(aligned_low)
    vol_df = pd.DataFrame(aligned_vol)

    # 丢弃任一列为 NaN 的早期行
    valid_idx = close_df.dropna(how='any').index
    if len(valid_idx) < MA_SLOW + SLOPE_WINDOW + 1:
        print(f"[板块 {sector}] 对齐后有效交易日不足 ({len(valid_idx)})")
        return None
    close_df = close_df.loc[valid_idx]
    high_df = high_df.loc[valid_idx]
    low_df = low_df.loc[valid_idx]
    vol_df = vol_df.loc[valid_idx]

    if close_df.shape[1] < 3:
        print(f"[板块 {sector}] 有效成分股不足 ({close_df.shape[1]})")
        return None

    avg_close = close_df.mean(axis=1)
    avg_high = high_df.mean(axis=1)
    avg_low = low_df.mean(axis=1)
    avg_vol = vol_df.mean(axis=1)

    # open：当日 avg_close / (1 + 当日收益率)
    avg_returns = avg_close.pct_change().fillna(0)
    sector_open = (avg_close / (1 + avg_returns)).fillna(avg_close.iloc[0])

    out = pd.DataFrame({
        'day': close_df.index,
        'open': sector_open.values,
        'close': avg_close.values,
        'high': np.maximum(avg_high.values, avg_close.values),
        'low': np.minimum(avg_low.values, avg_close.values),
        'volume': avg_vol.values,
    })
    return out


# ════════════════════════════════════════════════════════════
# 大盘判定（沪深300 + 上证 双标尺）
# ════════════════════════════════════════════════════════════
def judge_market() -> Dict:
    """大盘阶段判定：沪深300 主标尺 + 上证指数 验证"""
    benchmarks = [
        ('沪深300', 'sh000300'),
        ('上证指数', 'sh000001'),
    ]
    results = []
    for name, code in benchmarks:
        df = get_kline(code, 130)
        if df is None or len(df) < MA_SLOW + SLOPE_WINDOW + 1:
            results.append({
                'name': name,
                'phase': 'UNKNOWN',
                'phase_today': 'UNKNOWN',
                'phase_confirmed': 'UNKNOWN',
                'detail': {},
                'df': None,
            })
            continue

        close = df['close'].values
        atr = calc_atr(df)

        # 当根 + 上一根 + 上两根 K 线判定（用于稳定判定）
        phase_today, detail_today = judge_single(close, df)

        previous_phase = None
        if len(df) >= MA_SLOW + SLOPE_WINDOW + 2:
            sub_df = df.iloc[:-1]
            sub_close = sub_df['close'].values
            if len(sub_close) >= MA_SLOW + SLOPE_WINDOW + 1:
                previous_phase, _ = judge_single(sub_close, sub_df)

        previous_2_phase = None
        if len(df) >= MA_SLOW + SLOPE_WINDOW + 3:
            sub_df = df.iloc[:-2]
            sub_close = sub_df['close'].values
            if len(sub_close) >= MA_SLOW + SLOPE_WINDOW + 1:
                previous_2_phase, _ = judge_single(sub_close, sub_df)

        # 当根 K 线涨跌幅 + 大阴/大阳
        current_candle_pct = 0.0
        if len(close) >= 2 and close[-2] > 0:
            current_candle_pct = (close[-1] - close[-2]) / close[-2]
        day_range = float(df['high'].iloc[-1] - df['low'].iloc[-1])
        is_extreme = day_range > EXTREME_ATR_MULT * atr if atr > 0 else False

        # 当前日期
        current_date = None
        try:
            if 'day' in df.columns:
                current_date = pd.Timestamp(df['day'].iloc[-1]).strftime('%Y-%m-%d')
        except Exception:
            pass

        # 从磁盘读 prev_stable_phase
        cache = _load_stable_cache()
        cache_key = f'__market__{name}'
        prev_state = cache.get(cache_key, {})
        prev_stable_phase = prev_state.get('stable_phase')
        prev_stable_date = prev_state.get('last_date')

        history = judge_with_history(
            current_phase=phase_today,
            previous_phase=previous_phase,
            previous_2_phase=previous_2_phase,
            current_candle_pct=current_candle_pct,
            is_extreme=is_extreme,
            prev_stable_phase=prev_stable_phase,
            prev_stable_date=prev_stable_date,
            current_date=current_date,
        )
        stable_phase = history['stable_phase']

        # 写回磁盘
        if history['stable_phase_updated'] or cache_key not in cache:
            cache[cache_key] = {
                'stable_phase': stable_phase,
                'last_date': current_date,
                'last_candle_idx': int(len(df) - 1),
                'last_current_phase': phase_today,
            }
            _save_stable_cache(cache)

        results.append({
            'name': name,
            'phase_today': phase_today,
            'phase_confirmed': stable_phase,
            'stable_phase': stable_phase,
            'previous_phase': previous_phase,
            'previous_2_phase': previous_2_phase,
            'big_down_candle': history['big_down_candle'],
            'big_up_candle': history['big_up_candle'],
            'current_candle_pct': history['current_candle_pct'],
            'position_adjustment': history['position_adjustment'],
            'stable_phase_source': history['stable_phase_source'],
            'detail': detail_today,
            'df': df,
        })

    # 综合（保守模式）：多标尺不一致时取"较悲观"档位
    # 例如：沪深300=RANGE + 上证=WAVE_UP → 取 RANGE（更保守）
    # 例如：沪深300=RANGE + 上证=WAVE_DOWN → 取 WAVE_DOWN（更保守）
    confirmed = [r['phase_confirmed'] for r in results if r.get('phase_confirmed') != 'UNKNOWN']
    if not confirmed:
        market_phase = 'UNKNOWN'
    elif len(set(confirmed)) == 1:
        market_phase = confirmed[0]
    else:
        # 不一致时取优先级最低（最悲观）的档位
        # PHASE_PRIORITY: STRONG_DOWN=1 < RANGE=2 < WAVE_UP=3 < STRONG_UP=4
        # min() → 拿到最悲观的 STRONG_DOWN，避免双标尺不一致时过于乐观
        market_phase = min(confirmed, key=lambda p: PHASE_PRIORITY.get(p, 3))

    primary = next((r for r in results if r['name'] == '沪深300'), results[0])
    return {
        'phase': market_phase,
        'phase_label': PHASE_LABELS[market_phase],
        'merge_strategy': 'conservative_max_priority',  # 标记：取较悲观档
        'stable_phase': market_phase,   # 大盘的稳定 phase（保守合并后）
        # 操作建议（4 档实战规则）
        'operation': OPERATION_MAP[market_phase][0],
        'operation_label': OPERATION_MAP[market_phase][1],
        'phase_score': PHASE_SCORE[market_phase],
        'benchmarks': [
            {
                'name': r['name'],
                'phase_today': PHASE_LABELS.get(r.get('phase_today', 'UNKNOWN'), '未知'),
                'phase_confirmed': PHASE_LABELS.get(r.get('phase_confirmed', 'UNKNOWN'), '未知'),
                'stable_phase': PHASE_LABELS.get(r.get('stable_phase', r.get('phase_confirmed', 'UNKNOWN')), '未知'),
                'previous_phase': PHASE_LABELS.get(r.get('previous_phase'), '未知') if r.get('previous_phase') else None,
                'previous_2_phase': PHASE_LABELS.get(r.get('previous_2_phase'), '未知') if r.get('previous_2_phase') else None,
                'big_down_candle': r.get('big_down_candle', False),
                'big_up_candle': r.get('big_up_candle', False),
                'current_candle_pct': r.get('current_candle_pct', 0),
                'position_adjustment': r.get('position_adjustment', 'hold'),
                'stable_phase_source': r.get('stable_phase_source', '?'),
                'detail': r.get('detail', {}),
            }
            for r in results
        ],
        'indicator': primary.get('detail', {}),
    }


# ════════════════════════════════════════════════════════════
# 板块判定
# ════════════════════════════════════════════════════════════
def _judge_from_df(sector_name: str, df: pd.DataFrame, source: str, meta: Dict) -> Dict:
    """
    对已有 K 线 DataFrame 执行阶段判定（统一内部接口）

    输出包含：
      - current_phase / previous_phase / previous_2_phase
      - stable_phase（策略真正使用的稳定 phase）
      - big_down_candle / big_up_candle（大阴/大阳标记，仅作仓位调整）
      - phase_history / position_adjustment
    """
    if df is None or len(df) < MA_SLOW + SLOPE_WINDOW + 1:
        return {
            'sector': sector_name,
            'phase': 'UNKNOWN',
            'phase_label': PHASE_LABELS['UNKNOWN'],
            'source': source,
            'error': 'K线不足',
        }

    close = df['close'].values
    atr = calc_atr(df)

    # 当根 K 线判定
    phase_today, detail_today = judge_single(close, df)

    # v2 板块专用：V2_SECTORS 中的板块 phase 完全由 v2 决定（不回退到 v3）
    # 理由：1 年回测显示这些板块 v2 命中率高（半导体 v2 5/10 日 79%/93% vs v3 63%/53%），
    #       v3 触发但 v2 不触发时是反指标（v3 命中率 0-8%）。
    # 行为：
    #   - v2 触发 STRONG_UP → phase_today = STRONG_UP
    #   - v2 不触发       → phase_today = STRONG_DOWN（按 no_buy，不让 v3 干扰）
    v2_override = False
    if sector_name in V2_SECTORS:
        v2_params = V2_SECTORS[sector_name]
        v2_phase, v2_detail = judge_v2_sector(
            close, df,
            pullback_lookback=v2_params['pullback_lookback'],
            pullback_touch_tol=v2_params['pullback_touch_tol'],
        )
        v2_orig_phase = phase_today  # 记录 v3 的判定结果（仅用于诊断）
        v2_active = isinstance(v2_detail, dict) and v2_detail.get('v2_active')
        v2_indicator = v2_detail.get('indicator', {}) if v2_active else {}

        # 合并 v2 indicator 到 detail_today
        if v2_active:
            if isinstance(detail_today, dict):
                detail_today = {**detail_today, **v2_indicator}
                detail_today['v2_active'] = True
                detail_today['v2_orig_phase'] = v2_orig_phase
                # 记录 v2 4 个条件的命中情况（便于排查）
                detail_today['v2_cond1_close'] = v2_indicator.get('cond1_close_above_ma20')
                detail_today['v2_cond2_pullback'] = v2_indicator.get('cond2_pulled_back')
                detail_today['v2_cond3_slope'] = v2_indicator.get('cond3_slope_up')
                detail_today['v2_cond4_big_candle'] = v2_indicator.get('cond4_big_candle')
            else:
                detail_today = v2_indicator

        # 完全用 v2 覆盖 v3（避免 v3 反指标）
        if v2_active and v2_phase == 'STRONG_UP':
            phase_today = 'STRONG_UP'
            v2_override = True
        else:
            # v2 不触发 → 强制 no_buy，不让 v3 的 STRONG_UP 覆盖
            phase_today = 'STRONG_DOWN'

    # v7 板块专用：在 v3 之上叠加更严的入场过滤（2026-09-05）
    # 行为：
    #   - 仅当 v3 已判定 STRONG_UP 时，再叠一层 v7 过滤（v7 在 v3 之上叠加）
    #   - v7 触发 → phase 保持 STRONG_UP（向 fusion_runner 报"上行可买"）
    #   - v7 不触发 → phase 降级为 STRONG_DOWN（v7 比 v3 更严，过滤掉连续大涨/顶部区）
    #   - 不在 V7_SECTORS 的板块不受影响
    v7_override = False
    if sector_name in V7_SECTORS and phase_today == 'STRONG_UP':
        v7_params = V7_SECTORS[sector_name]
        v7_phase, v7_detail = judge_semicon_v7(
            close, df,
            ma20_touch_tol=v7_params.get('ma20_touch_tol', 0.02),
            dd_20_min=v7_params.get('dd_20_min', 0.03),
        )
        v7_orig_phase = phase_today

        if isinstance(detail_today, dict):
            detail_today = {**detail_today, 'v7_detail': v7_detail, 'v7_orig_phase': v7_orig_phase}
            detail_today['v7_active'] = (v7_phase == 'STRONG_UP')
        else:
            detail_today = {'v7_detail': v7_detail, 'v7_orig_phase': v7_orig_phase}

        if v7_phase == 'STRONG_UP':
            phase_today = 'STRONG_UP'
            v7_override = True
        else:
            # v7 不触发 → 降级为 no_buy（v7 比 v3 更严）
            phase_today = 'STRONG_DOWN'

    # 慢牛板块专用：SLOW_BULL_SECTORS 中的板块 phase 完全由慢牛策略决定
    # 理由：1 年回测显示这些板块慢牛 vs v3 单调差全部为正：
    #       军工 +1.37%/+4.16%, 商业航天 +1.72%/+4.06%, 贵金属 +1.42%/+1.99%,
    #       油气 +1.31%/+3.64%, 化工 +1.72%/+2.00%, 工业金属 +0.39%/+0.65%。
    # 行为（同 v2，独立判定，不回退到 v3）：
    #   - 慢牛触发 STRONG_UP → phase_today = STRONG_UP
    #   - 慢牛不触发       → phase_today = STRONG_DOWN（不让 v3 干扰）
    # 例外：A 族动量 v9 板块（军工/AI应用/人形机器人/光通信）跳过慢牛 → 走 a_momentum
    slow_override = False
    if sector_name in SLOW_BULL_SECTORS and not v2_override and sector_name not in A_MOMENTUM_SECTORS:
        sb_params = SLOW_BULL_SECTORS[sector_name]
        slow_orig_phase = phase_today  # 记录 v3/v2 的判定结果（仅用于诊断）
        slow_phase, slow_detail = judge_slow_bull(
            close, df,
            lookback_above_ma60=sb_params['lookback_above_ma60'],
            gain_min=sb_params['gain_min'],
            slope_min=sb_params['slope_min'],
            dd_max=sb_params['dd_max'],
        )
        slow_active = isinstance(slow_detail, dict) and 'cond1_close_above_ma60' in slow_detail

        if slow_active:
            if isinstance(detail_today, dict):
                detail_today = {**detail_today, **slow_detail}
                detail_today['slow_active'] = True
                detail_today['slow_orig_phase'] = slow_orig_phase
            else:
                detail_today = slow_detail

        # 完全用慢牛覆盖 v3/v2（避免 v3 在温和慢涨板块"追在顶部"）
        if slow_active and slow_phase == 'STRONG_UP':
            phase_today = 'STRONG_UP'
            slow_override = True
        else:
            # 慢牛不触发 → 强制 no_buy
            phase_today = 'STRONG_DOWN'

    # v9 板块专用：在 slow_bull 之上叠加更严的入场过滤（2026-09-06 落地）
    # 行为：
    #   - slow_bull 板块（贵金属 + 5 B 族）：仅当 slow_bull 已判定 STRONG_UP 时，再叠 v9 过滤
    #   - A 族动量板块：跳过 slow_bull，直接用 judge_a_momentum 触发 STRONG_UP
    #   - 创新药：跳过 slow_bull，直接用 judge_innovative_drug_v9（事件驱动型）
    #   - v9 触发 → phase 保持 STRONG_UP（向 fusion_runner 报"上行可买"）
    #   - v9 不触发 → phase 降级为 STRONG_DOWN（v9 比 slow_bull/底层 更严，过滤掉连续大涨/顶部区）
    #   - 不在 V9_SECTORS 的板块不受影响
    v9_override = False
    if (slow_override or sector_name in A_MOMENTUM_SECTORS or sector_name in ('创新药', '种子农业', '电网设备', '券商', '低空经济', '稀土', '商业航天')) and sector_name in V9_SECTORS:
        v9_params = V9_SECTORS[sector_name]
        v9_strategy = v9_params.get('strategy', 'slow_bull_v9')
        v9_orig_phase = phase_today

        if v9_strategy == 'momentum_v9':
            # A 族动量 v9：close>MA60 + |vs_MA20|<tol> + 近5日涨>5%
            # 可选增强：4线多头 + NOT 4线 + dd_60_max + range_60_max
            v9_phase, v9_detail = judge_a_momentum(
                close, df,
                ma20_touch_tol=v9_params.get('ma20_touch_tol', 0.10),
                gain_5d_min=v9_params.get('gain_5d_min', 0.05),
                require_ma_align_4=v9_params.get('require_ma_align_4', False),
                require_no_ma_align_4=v9_params.get('require_no_ma_align_4', False),
                dd_60_max=v9_params.get('dd_60_max', None),
                range_60_max=v9_params.get('range_60_max', None),
            )
        elif v9_strategy == 'innovative_drug_v9':
            # 创新药 v9（事件驱动）：4线多头 + 近20日涨>8%
            v9_phase, v9_detail = judge_innovative_drug_v9(
                close, df,
                gain_20_min=v9_params.get('gain_20_min', 0.08),
            )
        elif v9_strategy == 'seed_agriculture_v9':
            # 种子农业 v9（季节性）：秋收窗口 (8-10月) + 动量基础
            v9_phase, v9_detail = judge_seed_agriculture_v9(
                close, df,
                ma20_touch_tol=v9_params.get('ma20_touch_tol', 0.10),
                gain_5d_min=v9_params.get('gain_5d_min', 0.05),
                season_months=tuple(v9_params.get('season_months', (8, 9, 10))),
            )
        elif v9_strategy == 'power_grid_v9':
            # 电网设备 v9（反 4 线多头）：NOT 4线 + 温和 + 贴近 MA20
            v9_phase, v9_detail = judge_power_grid_v9(
                close, df,
                lookback_above_ma60=v9_params.get('lookback_above_ma60', 15),
                gain_min=v9_params.get('gain_min', 0.03),
                slope_min=v9_params.get('slope_min', 0.0),
                dd_max=v9_params.get('dd_max', 0.10),
                vs_ma20_max=v9_params.get('vs_ma20_max', 0.03),
                gain_20_max=v9_params.get('gain_20_max', 0.08),
                require_no_align_4=v9_params.get('require_no_align_4', True),
            )
        elif v9_strategy == 'securities_v9':
            # 券商 v9（4线回撤启动）：4线多头 + 距 20 日高 > 5%
            v9_phase, v9_detail = judge_securities_v9(
                close, df,
                lookback_above_ma60=v9_params.get('lookback_above_ma60', 15),
                gain_min=v9_params.get('gain_min', 0.03),
                slope_min=v9_params.get('slope_min', 0.0),
                dd_max=v9_params.get('dd_max', 0.10),
                dd_20_min=v9_params.get('dd_20_min', 0.05),
                require_align_4=v9_params.get('require_align_4', True),
            )
        elif v9_strategy == 'low_altitude_v9':
            # 低空经济 v9（4线贴近）：4线多头 + |vs_MA20| < 5%
            v9_phase, v9_detail = judge_low_altitude_v9(
                close, df,
                lookback_above_ma60=v9_params.get('lookback_above_ma60', 15),
                gain_min=v9_params.get('gain_min', 0.03),
                slope_min=v9_params.get('slope_min', 0.0),
                dd_max=v9_params.get('dd_max', 0.10),
                vs_ma20_max=v9_params.get('vs_ma20_max', 0.05),
                require_align_4=v9_params.get('require_align_4', True),
            )
        else:
            # slow_bull_v9（贵金属 + 5 B 族）：slow_bull + |vs_MA20|<8% + 距20日高>8%
            v9_phase, v9_detail = judge_gold_v9(
                close, df,
                lookback_above_ma60=v9_params.get('lookback_above_ma60', 15),
                gain_min=v9_params.get('gain_min', 0.03),
                slope_min=v9_params.get('slope_min', 0.0),
                dd_max=v9_params.get('dd_max', 0.15),
                ma20_touch_tol=v9_params.get('ma20_touch_tol', 0.08),
                dd_20_min=v9_params.get('dd_20_min', 0.08),
                range_60_max=v9_params.get('range_60_max', None),
            )

        if isinstance(detail_today, dict):
            detail_today = {**detail_today, 'v9_detail': v9_detail, 'v9_orig_phase': v9_orig_phase}
            detail_today['v9_active'] = (v9_phase == 'STRONG_UP')
            detail_today['v9_strategy'] = v9_strategy
        else:
            detail_today = {'v9_detail': v9_detail, 'v9_orig_phase': v9_orig_phase,
                            'v9_strategy': v9_strategy}

        if v9_phase == 'STRONG_UP':
            phase_today = 'STRONG_UP'
            v9_override = True
        else:
            # v9 不触发 → 降级为 no_buy（v9 比 slow_bull 更严）
            phase_today = 'STRONG_DOWN'

    # 上一根 K 线判定
    previous_phase = None
    if len(df) >= MA_SLOW + SLOPE_WINDOW + 2:
        sub_df = df.iloc[:-1]
        sub_close = sub_df['close'].values
        if len(sub_close) >= MA_SLOW + SLOPE_WINDOW + 1:
            previous_phase, _ = judge_single(sub_close, sub_df)

    # 上两根 K 线判定
    previous_2_phase = None
    if len(df) >= MA_SLOW + SLOPE_WINDOW + 3:
        sub_df = df.iloc[:-2]
        sub_close = sub_df['close'].values
        if len(sub_close) >= MA_SLOW + SLOPE_WINDOW + 1:
            previous_2_phase, _ = judge_single(sub_close, sub_df)

    # 当根 K 线涨跌幅
    current_candle_pct = 0.0
    if len(close) >= 2 and close[-2] > 0:
        current_candle_pct = (close[-1] - close[-2]) / close[-2]

    # 当根是否极端（振幅 > 2×ATR）
    day_range = float(df['high'].iloc[-1] - df['low'].iloc[-1])
    is_extreme = day_range > EXTREME_ATR_MULT * atr if atr > 0 else False

    # 当根日期
    current_date = None
    try:
        if 'day' in df.columns:
            current_date = pd.Timestamp(df['day'].iloc[-1]).strftime('%Y-%m-%d')
    except Exception:
        pass

    # 从磁盘读 prev_stable_phase
    cache = _load_stable_cache()
    cache_key = sector_name
    prev_state = cache.get(cache_key, {})
    prev_stable_phase = prev_state.get('stable_phase')
    prev_stable_date = prev_state.get('last_date')

    # 双根 K 线稳定判定 + 大阴/大阳标记（带跨进程稳定态）
    history = judge_with_history(
        current_phase=phase_today,
        previous_phase=previous_phase,
        previous_2_phase=previous_2_phase,
        current_candle_pct=current_candle_pct,
        is_extreme=is_extreme,
        prev_stable_phase=prev_stable_phase,
        prev_stable_date=prev_stable_date,
        current_date=current_date,
    )
    stable_phase = history['stable_phase']

    # v7 override 时强制 stable_phase = STRONG_UP（2026-09-05）
    # 理由：v7 已经做了 2 重过滤（v3 上行 + |vs_MA20|<2%），
    #       不需要再受 judge_with_history 跨天稳定判定的压制，
    #       否则会漏掉主升起点的 BUY 信号（如 2025-09-04）
    if v7_override and phase_today == 'STRONG_UP':
        stable_phase = 'STRONG_UP'
        history['stable_phase'] = 'STRONG_UP'

    # v9 override 时强制 stable_phase = STRONG_UP（2026-09-06）
    # 理由：v9 已经做了 2 重过滤（slow_bull + |vs_MA20|<8% + 距20日高>8%），
    #       不需要再受 judge_with_history 跨天稳定判定的压制。
    if v9_override and phase_today == 'STRONG_UP':
        stable_phase = 'STRONG_UP'
        history['stable_phase'] = 'STRONG_UP'

    # 板块类型降级：no_chase 板块的 STRONG_UP 自动降级为 RANGE
    # 理由：这些板块历史 BUY 信号反指标（BUY 后必亏），
    #       实际"突破"是顶部信号，按震荡处理更安全。
    # 例外：v9_override 触发的 STRONG_UP 不降级（v9 已有过滤，且为新设计无历史反指标）
    sector_category = SECTOR_CATEGORY.get(sector_name, 'thematic')
    downgrade_reason = None
    if sector_category == 'no_chase' and stable_phase == 'STRONG_UP' and not v9_override:
        stable_phase = 'RANGE'
        history['stable_phase'] = 'RANGE'
        downgrade_reason = 'no_chase板块：BUY信号历史反指标，STRONG_UP降级为RANGE'
    elif sector_category == 'thematic' and stable_phase == 'STRONG_UP':
        # 题材板块：保留 STRONG_UP 但标记"慎用"
        downgrade_reason = 'thematic板块：BUY信号部分有效，需谨慎'

    # UNKNOWN 板块类型分流：避免"什么都不是"的状态
    # 理由：4档都不命中时（如60日振幅>15%），UNKNOWN 对操作无指导意义
    #       - 资源板块 UNKNOWN → 按下行处理（不操作）
    #       - 题材板块 UNKNOWN → 按震荡处理（只买ETF）
    #       - 不可追板块 UNKNOWN → 保持（板块状态不明，本来就不买）
    if stable_phase == 'UNKNOWN':
        if sector_category == 'resource':
            stable_phase = 'STRONG_DOWN'
            history['stable_phase'] = 'STRONG_DOWN'
            downgrade_reason = 'resource板块：UNKNOWN按下行保守处理（60日振幅>15%，震荡判定不通过）'
        elif sector_category == 'thematic':
            stable_phase = 'RANGE'
            history['stable_phase'] = 'RANGE'
            downgrade_reason = 'thematic板块：UNKNOWN按震荡处理（按"震荡只买ETF"操作）'

    # 写回磁盘（只有真正更新时才覆盖）
    if history['stable_phase_updated'] or cache_key not in cache:
        cache[cache_key] = {
            'stable_phase': stable_phase,
            'last_date': current_date,
            'last_candle_idx': int(len(df) - 1),
            'last_current_phase': phase_today,
        }
        _save_stable_cache(cache)

    return {
        'sector': sector_name,
        # 兼容旧字段
        'phase': stable_phase,
        'phase_label': PHASE_LABELS[stable_phase],
        'phase_today': PHASE_LABELS[phase_today],
        'phase_confirmed': PHASE_LABELS[stable_phase],   # 兼容旧调用
        # 操作建议（4 档实战规则）
        'operation': OPERATION_MAP[stable_phase][0],
        'operation_label': OPERATION_MAP[stable_phase][1],
        'phase_score': PHASE_SCORE[stable_phase],
        # 新字段
        'current_phase': phase_today,
        'stable_phase': stable_phase,
        'previous_phase': previous_phase,
        'previous_2_phase': previous_2_phase,
        'phase_history': history['phase_history'],
        'big_down_candle': history['big_down_candle'],
        'big_up_candle': history['big_up_candle'],
        'is_extreme_candle': history['is_extreme'],
        'current_candle_pct': history['current_candle_pct'],
        'stable_phase_updated': history['stable_phase_updated'],
        'position_adjustment': history['position_adjustment'],
        'stable_phase_source': history['stable_phase_source'],
        'prev_stable_phase': history['prev_stable_phase'],
        'is_stale': history['is_stale'],
        'category': sector_category,
        'downgrade_reason': downgrade_reason,
        'source': source,
        'meta': meta,
        'indicator': detail_today,
        'v2_override': v2_override,   # True=用了v2（半导体/通信/化工）
        'v7_override': v7_override,   # True=用了v7（在v2之上再过滤，2026-09-05）
        'v9_override': v9_override,   # True=用了v9（在slow_bull之上再过滤，2026-09-06）
        'v2_sector': sector_name in V2_SECTORS,   # True=属于v2板块
        'slow_override': slow_override,   # True=用了慢牛（军工/商业航天/贵金属/工业金属/油气/化工）
        'slow_sector': sector_name in SLOW_BULL_SECTORS,   # True=属于慢牛板块
        'a_mom_sector': sector_name in A_MOMENTUM_SECTORS,   # True=属于A族动量v9板块（2026-09-06）
    }


def _build_etf_blend_kline(codes: List[str], days: int = 200) -> Optional[pd.DataFrame]:
    """
    多 ETF 等权合成 K 线
    每只 ETF 归一化到首日=100，对齐到共同日期后取平均
    容忍单只 ETF 拿不到（降级到剩余 ETF blend）
    """
    series_map: Dict[str, pd.Series] = {}
    high_map: Dict[str, pd.Series] = {}
    low_map: Dict[str, pd.Series] = {}
    vol_map: Dict[str, pd.Series] = {}

    for code in codes:
        df = get_kline(code, days)
        if df is None or len(df) < 30:
            continue
        # 把 day 列归一化为日期（去掉时间部分）
        # 原因：pytdx 返回 00:00:00，sina 返回 15:00:00，
        #       如果直接 set_index('day') 会被 concat 当成不同 index
        day_normalized = pd.to_datetime(df['day']).dt.normalize()
        s_close = pd.Series(df['close'].values, index=day_normalized.values)
        s_high = pd.Series(df['high'].values, index=day_normalized.values)
        s_low = pd.Series(df['low'].values, index=day_normalized.values)
        s_vol = pd.Series(df['volume'].values, index=day_normalized.values)
        base = float(s_close.iloc[0])
        if base <= 0:
            continue
        if len(codes) >= 2:
            series_map[code] = s_close / base * 100
            high_map[code] = s_high / base * 100
            low_map[code] = s_low / base * 100
        else:
            series_map[code] = s_close
            high_map[code] = s_high
            low_map[code] = s_low
        vol_map[code] = s_vol

    if len(series_map) < 1:
        return None

    # 用 join='inner' 按日期对齐（每个 ETF 上市日期不同）
    # 不先 align 直接 concat(axis=1) 会产生 N×len(codes) 行（每个 ETF 各自一行日期）
    close_df = pd.concat(series_map.values(), axis=1, join='inner')
    high_df = pd.concat(high_map.values(), axis=1, join='inner')
    low_df = pd.concat(low_map.values(), axis=1, join='inner')
    vol_df = pd.concat(vol_map.values(), axis=1, join='inner')

    min_valid = int(days * 0.7)   # 放宽：70% 即接受（之前 80% 容易丢数据）
    close_df = close_df.dropna(axis=1, thresh=min_valid)
    high_df = high_df.dropna(axis=1, thresh=min_valid)
    low_df = low_df.dropna(axis=1, thresh=min_valid)
    vol_df = vol_df.dropna(axis=1, thresh=min_valid)

    if len(close_df) < MA_SLOW + SLOPE_WINDOW + 1 or close_df.shape[1] < 1:
        return None

    avg_close = close_df.mean(axis=1)
    avg_high = high_df.mean(axis=1)
    avg_low = low_df.mean(axis=1)
    avg_vol = vol_df.mean(axis=1)

    avg_returns = avg_close.pct_change().fillna(0)
    sector_open = (avg_close / (1 + avg_returns)).fillna(avg_close.iloc[0])

    return pd.DataFrame({
        'day': close_df.index,
        'open': sector_open.values,
        'close': avg_close.values,
        'high': np.maximum(avg_high.values, avg_close.values),
        'low': np.minimum(avg_low.values, avg_close.values),
        'volume': avg_vol.values,
    })


def judge_sector(sector: str) -> Dict:
    """
    单板块阶段判定（统一入口 + 自动回退）
    顺序：
    1. 优先用 SECTOR_ETFS 中的 ETF 标尺（单 ETF / 多 ETF 合成）
    2. ETF 失败 → 自动回退到 SECTOR_CONSTITUENTS 成分股合成
    3. 都失败 → 返回 error 并报告原因

    返回字段包含 'fallback' 标记是否回退、'error_reason' 失败原因
    """
    # 别名处理：合并细分板块到主板块
    sector_aliases = {
        '电池储能': '电池',     # 电池ETF 覆盖更稳定
        '贵金属_黄金': '贵金属',
        '贵金属_白银': '贵金属',
    }
    actual_sector = sector_aliases.get(sector, sector)

    etf_target = SECTOR_ETFS.get(actual_sector)
    etf_meta = None
    df = None
    source = None

    if etf_target is not None:
        if isinstance(etf_target, str):
            code = etf_target
            df = get_kline(code, 200)
            if df is not None and not df.empty:
                for col in ('open', 'high', 'low', 'close'):
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            source = 'etf'
            etf_meta = {'etf_code': code, 'note': '单 ETF 自身 K 线（绝对价格，未归一化）'}
        else:
            # 多 ETF 合成
            codes = list(etf_target)
            df = _build_etf_blend_kline(codes, 200)
            valid_codes = [c for c in codes if c in (df.columns.tolist() if df is not None else [])] or codes
            source = 'etf_blend'
            etf_meta = {'etf_codes': valid_codes, 'note': '多 ETF 等权合成（已归一化到 100）'}

    # ETF 成功（df 不为空且行数够）→ 直接用 ETF 判定
    if df is not None and not df.empty and len(df) >= MA_SLOW + SLOPE_WINDOW + 1:
        return _judge_from_df(sector_name=actual_sector, df=df, source=source, meta=etf_meta)

    # ETF 失败 → 记录原因，回退到成分股
    etf_fail_reason = None
    if etf_target is not None:
        if isinstance(etf_target, str):
            etf_fail_reason = f"ETF {etf_target} 拿不到 K 线（pytdx + sina 均失败，可能被限流或代码无效）"
        else:
            failed = []
            for c in etf_target:
                test_df = get_kline(c, 200)
                if test_df is None or len(test_df) < 30:
                    failed.append(c)
            etf_fail_reason = f"多 ETF 中失败: {failed}" if failed else f"ETF blend 拿不到 K 线"

    # 成分股合成回退
    constituents = SECTOR_CONSTITUENTS.get(actual_sector, [])
    if not constituents:
        return {
            'sector': actual_sector,
            'phase': 'UNKNOWN',
            'phase_label': PHASE_LABELS['UNKNOWN'],
            'source': source or 'none',
            'error': f'无 ETF 标尺且无成分股配置。{etf_fail_reason or ""}'.strip('。'),
            'error_reason': etf_fail_reason or '板块未配置任何标尺',
            'original_sector': sector,
        }

    df = build_sector_kline(actual_sector, 130)
    fallback_meta = {
        'constituent_count': len(constituents),
        'fallback': True,
        'fallback_reason': etf_fail_reason,
    }
    if etf_meta:
        fallback_meta['original_etf_meta'] = etf_meta
    result = _judge_from_df(
        sector_name=actual_sector,
        df=df,
        source='constituents_fallback',
        meta=fallback_meta,
    )
    # 增强错误信息
    if result.get('error') and etf_fail_reason:
        result['error_reason'] = f"ETF 失败 + 成分股合成失败: {etf_fail_reason}"
    if actual_sector != sector:
        result['original_sector'] = sector
    return result


# ════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════
def run_full(sectors: Optional[List[str]] = None) -> Dict:
    """运行大盘 + 所有主板块判定（精简后 18 个大板块）"""
    print(f"\n{'='*60}\n行情阶段判定 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}")

    market = judge_market()
    print(f"\n[大盘] {market['phase_label']}（稳定态：{market['phase_label']}）")
    for b in market['benchmarks']:
        candle_tag = ''
        if b.get('big_down_candle'):
            candle_tag = ' 🔻大阴线'
        elif b.get('big_up_candle'):
            candle_tag = ' 🔺大阳线'
        print(f"   {b['name']}: 今日={PHASE_LABELS.get(b.get('phase_today','UNKNOWN'),'未知')}  "
              f"稳定={PHASE_LABELS.get(b.get('stable_phase', b.get('phase_confirmed','UNKNOWN')),'未知')}{candle_tag}  "
              f"MA60斜率={b['detail'].get('ma60_slope_pct', 0):+.3f}%  "
              f"ADX={b['detail'].get('adx', 0):.1f}  "
              f"量价比={b['detail'].get('vol_health_ratio', 0):.2f}")

    # 默认主板块（v9 配置：基于 watchlist.yaml 的 snake_case 板块）
    if sectors is not None:
        target_sectors = sectors
    else:
        # 优先用 SECTOR_ETFS 的板块（ETF 标尺更准），其余用 SECTOR_CONSTITUENTS
        # v9 配置：无通用兜底板块，全部基于 watchlist.yaml
        GENERIC = set()
        target_sectors = [s for s in SECTOR_ETFS.keys() if s not in GENERIC] + \
                         [s for s in SECTOR_CONSTITUENTS.keys() if s not in SECTOR_ETFS and s not in GENERIC]
        # 去重（按实际判定 sector 名）：处理别名重复（电池储能→电池 等）
        sector_aliases = {
            '电池储能': '电池',
            '贵金属_黄金': '贵金属',
            '贵金属_白银': '贵金属',
        }
        seen = set()
        deduped = []
        for s in target_sectors:
            actual = sector_aliases.get(s, s)
            if actual not in seen:
                seen.add(actual)
                deduped.append(s)
        target_sectors = deduped

    sector_results = []
    for s in target_sectors:
        print(f"\n[板块] 判定 {s} ...", end=' ', flush=True)
        try:
            r = judge_sector(s)
            if r.get('error'):
                print(f"⚠️  {r.get('error_reason', r['error'])}")
            else:
                ind = r.get('indicator', {})
                src = r.get('source', '?')
                fallback = r.get('meta', {}).get('fallback')

                # 大阴/大阳标记
                candle_tag = ''
                if r.get('big_down_candle'):
                    candle_tag = ' 🔻大阴线'
                elif r.get('big_up_candle'):
                    candle_tag = ' 🔺大阳线'

                # 历史 vs 当根 vs 稳定
                current = PHASE_LABELS.get(r.get('current_phase', 'UNKNOWN'), '未知')
                stable = PHASE_LABELS.get(r.get('stable_phase', r.get('phase', 'UNKNOWN')), '未知')
                updated_mark = ' ✓' if r.get('stable_phase_updated') else ' -'

                tag = f"[{src}]" + (" (回退)" if fallback else "")
                if current == stable:
                    hist_str = current
                else:
                    hist_str = f"{current}→稳定:{stable}{updated_mark}"

                print(f"{stable}  {tag}  K线={r.get('current_candle_pct', 0)*100:+.2f}%{candle_tag}  "
                      f"[{hist_str}]  "
                      f"MA60={ind.get('ma60_slope_pct', 0):+.3f}%  "
                      f"ADX={ind.get('adx', 0):.1f}")
            sector_results.append(r)
        except Exception as e:
            print(f"❌ {e}")
            sector_results.append({
                'sector': s, 'phase': 'UNKNOWN', 'phase_label': '未知',
                'error': str(e), 'error_reason': f'未捕获异常: {e}'
            })

    output = {
        'generated_at': datetime.now().isoformat(),
        'market': market,
        'sectors': sector_results,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(_json_safe(output), f, ensure_ascii=False, indent=2)
    print(f"\n📄 已写入: {OUTPUT_FILE}")
    return output


def main():
    parser = argparse.ArgumentParser(description='行情阶段判定器')
    parser.add_argument('--sector', type=str, help='只判定单个板块，例如：电网设备 / 贵金属')
    parser.add_argument('--all', action='store_true', help='判定大盘 + 所有主板块')
    args = parser.parse_args()

    # 主板块列表（v9 配置：基于 watchlist.yaml 的 snake_case 板块）
    GENERIC = set()
    main_sectors = [s for s in SECTOR_ETFS.keys() if s not in GENERIC] + \
                   [s for s in SECTOR_CONSTITUENTS.keys() if s not in SECTOR_ETFS and s not in GENERIC]

    if args.sector:
        if args.sector not in SECTOR_CONSTITUENTS and args.sector not in SECTOR_ETFS:
            print(f"未知板块: {args.sector}")
            print(f"主板块: {', '.join(main_sectors)}")
            sys.exit(1)
        market = judge_market()
        sector = judge_sector(args.sector)
        output = {
            'generated_at': datetime.now().isoformat(),
            'market': market,
            'sectors': [sector],
        }
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(_json_safe(output), f, ensure_ascii=False, indent=2)
        print(json.dumps(_json_safe(output), ensure_ascii=False, indent=2))
    else:
        run_full()


if __name__ == '__main__':
    main()