#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
融合交易策略运行器
- 14:30 运行尾盘买策略 → 输出 top5 推荐
- 16:00 运行早盘买策略 → 输出 top5 推荐
结果写入 ~/.openclaw/stock/recommendations.json
"""

import os
import sys
import json
from unittest import result
import yaml
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import importlib
import pandas as pd

from earnings_caculate import get_dangerous_stocks
from test_news import recommendations_penalty

# 复用 detector 的板块映射（自动从 watchlist.yaml 构建）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from market_phase_detector import get_sector_by_stock
except Exception as _e:
    print(f"[WARN] get_sector_by_stock 加载失败: {_e}")
    def get_sector_by_stock(code):  # type: ignore
        return 'UNKNOWN'


# ── 路径设置（相对路径，基于脚本所在目录）────────────────────
# fusion_runner.py 位于 strategy-fusion-advisor/skills/scripts/
# dirname ×3 → strategy-fusion-advisor/（SKILL_DIR）
# dirname ×4 → Chinese_Stock/（BASE_DIR）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # .../skills/scripts
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # .../strategy-fusion-advisor
_BASE_DIR = os.path.dirname(_SKILL_DIR)  # .../Chinese_Stock
# 推荐文件写入位置：Chinese_Stock/recommendations/
SKILL_RECO_DIR = os.path.join(_BASE_DIR, 'recommendations')

# ========== 强制关闭代理，解决 akshare 连接失败 ==========
import os
import socket

# 清空系统代理
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["FTP_PROXY"] = ""
os.environ["ALL_PROXY"] = ""
os.environ["SOCKS_PROXY"] = ""



# ── 策略分组 ────────────────────────────────────────────
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

# market_phase_detector.py 输出的 JSON 路径
MARKET_PHASE_FILE = os.path.join(
    _BASE_DIR, 'strategy-fusion-advisor', 'recommendations', 'market_phase.json'
)

# 持仓文件路径（my_holdings/holdings.json）
HOLDINGS_FILE = os.path.join(_BASE_DIR, 'my_holdings', 'holdings.json')
# 持仓板块加分（同一板块再次推荐时，在基础分上加分）
HELD_SECTOR_BONUS = 5.0


def load_market_phase() -> Dict:
    """读取 market_phase_detector 写入的大盘状态 JSON（含大盘 phase + 各板块 phase）"""
    if not os.path.exists(MARKET_PHASE_FILE):
        return {
            'phase': 'UNKNOWN',
            'phase_label': '未知',
            'stable_phase': 'UNKNOWN',
            'merge_strategy': '',
            'benchmarks': [],
            'big_down_candle': False,
            'big_up_candle': False,
            'sector_phases': {},          # {sector_name: phase_code}
            'sectors_detail': [],         # market_phase.json 中的 sectors 列表
            'has_sector_data': False,
            'generated_at': None,
            'error': f'market_phase.json 不存在（{MARKET_PHASE_FILE}）',
        }
    try:
        with open(MARKET_PHASE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        market = data.get('market', {}) or {}
        benchmarks = market.get('benchmarks', []) or []
        sectors_detail = data.get('sectors', []) or []

        # 构造 sector_phases: {板块名: 板块 phase}
        sector_phases = {}
        for sec in sectors_detail:
            name = sec.get('sector')
            if not name:
                continue
            # 优先 stable_phase，回退 phase
            phase = sec.get('stable_phase') or sec.get('phase') or 'UNKNOWN'
            sector_phases[name] = phase

        return {
            'phase': market.get('phase', 'UNKNOWN'),
            'phase_label': market.get('phase_label', '未知'),
            'stable_phase': market.get('stable_phase', market.get('phase', 'UNKNOWN')),
            'merge_strategy': market.get('merge_strategy', ''),
            'benchmarks': benchmarks,
            'big_down_candle': any(b.get('big_down_candle', False) for b in benchmarks),
            'big_up_candle': any(b.get('big_up_candle', False) for b in benchmarks),
            'sector_phases': sector_phases,
            'sectors_detail': sectors_detail,
            'has_sector_data': bool(sector_phases),
            'generated_at': data.get('generated_at'),
        }
    except Exception as e:
        return {
            'phase': 'UNKNOWN',
            'phase_label': '未知',
            'stable_phase': 'UNKNOWN',
            'merge_strategy': '',
            'benchmarks': [],
            'big_down_candle': False,
            'big_up_candle': False,
            'sector_phases': {},
            'sectors_detail': [],
            'has_sector_data': False,
            'generated_at': None,
            'error': f'读取失败: {e}',
        }


def load_holded_sectors() -> set:
    """
    从 my_holdings/holdings.json 读取持仓股票，返回其所属板块集合
    用于"同一板块持仓后，下次推荐加分"策略
    """
    if not os.path.exists(HOLDINGS_FILE):
        return set()
    try:
        with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
            holdings = json.load(f)
        if not isinstance(holdings, list):
            return set()
        sectors = set()
        for h in holdings:
            code = str(h.get('code', '')).strip()
            shares = h.get('shares', 0)
            if not code or shares <= 0:
                continue
            sector = get_sector_by_stock(code)
            if sector and sector != 'UNKNOWN':
                sectors.add(sector)
        if sectors:
            print(f'[持仓] 持仓板块: {sorted(sectors)}（共 {len(sectors)} 个）')
        return sectors
    except Exception as e:
        print(f'[WARN] 读取持仓板块失败: {e}')
        return set()


# ── 策略扫描 ────────────────────────────────────────────

def scan_strategy(strategy_name: str, top_n: int = 5,
                  sector_phases: Optional[Dict] = None,
                  filter_enabled: bool = True) -> Tuple[List[Dict], Dict]:
    """
    运行单个策略，按板块 phase 过滤，返回 (通过的推荐, 过滤统计)

    sector_phases: {板块名: phase_code}，None 表示不过滤
    filter_enabled: False 时强制不过滤板块（向后兼容）

    过滤统计结构:
      {
        'reserve': [{stock_code, stock_name, sector, sector_phase}, ...],
        'block':   [{stock_code, stock_name, sector, sector_phase}, ...],
        'unknown_sector': [...]   # 板块为空或不在 sector_phases 中
      }
    """
    meta = STRATEGY_META.get(strategy_name, {})
    print("meta: ", meta)
    analyzer = get_analyzer(strategy_name)
    if analyzer is None:
        return [], {'reserve': [], 'block': [], 'unknown_sector': []}

    results = []
    stats = {'reserve': [], 'block': [], 'unknown_sector': []}
    try:
        result = None
        if(strategy_name == 'limit-up-analysis'):
            result = analyzer.analyze_all_limit_up()

        elif(strategy_name == 'earnings-surprise-strategy'):
            result = analyzer.scan_daily_earnings(datetime.now())

        else:
            result = analyzer.scan_all_stocks(top_n=top_n)
        print(f"✅ 策略 {strategy_name} 运行完成，结果：")

        for res in result:
            if res.get('score', 0) < 80:
                continue

            stock_code_raw = res.get('stock_code', '')
            result_sig = {}
            result_sig['stock_code'] = stock_code_raw
            result_sig['stock_name'] = res.get('stock_name', '')
            result_sig['strategy_name'] = strategy_name
            result_sig['reasons'] = res.get('reasons')
            result_sig['strategy_display'] = meta.get('display', strategy_name)
            result_sig['strategy_win_rate'] = meta.get('win_rate', 0.60)
            result_sig['strategy_weight'] = meta.get('weight', 1.0)
            result_sig['strategy_score'] = res.get('score', 70)
            if len(stock_code_raw) > 6:
                result_sig['stock_code'] = stock_code_raw[2:]

            # ── 板块过滤 ──
            # 优先用 analyzer 返回的 sector；若为空，从 watchlist 自动查表补齐
            sector = res.get('sector', '')
            if not sector:
                sector = get_sector_by_stock(stock_code_raw)
            result_sig['sector'] = sector

            if not filter_enabled or sector_phases is None:
                # 不启用过滤
                result_sig['sector_phase'] = 'UNKNOWN'
                result_sig['sector_action'] = 'run'
                results.append(result_sig)
                continue

            sector_phase = sector_phases.get(sector, 'UNKNOWN')
            # v4.2: 按 ETF vs 个股选不同过滤表
            is_etf = _is_etf_code(stock_code_raw)
            filter_table = PHASE_SECTOR_FILTER_ETF if is_etf else PHASE_SECTOR_FILTER_STOCK
            sector_action = filter_table.get(sector_phase, 'block')
            result_sig['sector_phase'] = sector_phase
            result_sig['sector_action'] = sector_action
            result_sig['is_etf'] = is_etf

            filter_record = {
                'stock_code': result_sig['stock_code'],
                'stock_name': result_sig['stock_name'],
                'sector': sector,
                'sector_phase': sector_phase,
                'strategy': strategy_name,
            }

            if sector_action in ['run', 'run_low']:
                # run_low: 大盘/板块 STRONG_DOWN 时进入融合评分，但 fusion 中要求高分
                result_sig['sector_action'] = sector_action
                results.append(result_sig)
            elif sector_action == 'reserve':
                stats['reserve'].append(filter_record)
                if not sector:
                    stats['unknown_sector'].append(filter_record)
            elif sector_action == 'block':
                stats['block'].append(filter_record)
                if not sector:
                    stats['unknown_sector'].append(filter_record)
    except Exception:
        pass

    results.sort(key=lambda x: x.get('strategy_score', 0), reverse=True)
    return results, stats


def get_analyzer(strategy_name: str):
    """获取策略分析器实例"""
    cls_name = ANALYZER_CLASS.get(strategy_name)
    #print("cls_name: ", cls_name)
    if not cls_name:
        return None

    # 添加策略根目录（包含 skills/ 的那一层）
    strategy_root = os.path.join(_BASE_DIR, strategy_name)
    if strategy_root in sys.path:
        sys.path.remove(strategy_root)
    # 追加到末尾，不影响主项目路径优先级
    sys.path.append(strategy_root)
    # 动态导入
    try:
      
        import_module = "skills.scripts." +strategy_name.replace('-', '_') + "_analyzer"
        print("import_module: ", import_module)
        if import_module in sys.modules:
            del sys.modules[import_module]
        # 清理污染
        if 'skills' in sys.modules:
            del sys.modules['skills']
        if 'skills.scripts' in sys.modules:
            del sys.modules['skills.scripts']

        mod = importlib.import_module(import_module)
        AnalyzerCls = getattr(mod, cls_name, None)
        if AnalyzerCls is None:
            return None
        analyzer = AnalyzerCls()
        return analyzer
    except Exception as e:
        print("error: ", e)
        return None


# ── 融合评分 ────────────────────────────────────────────

def fuse_recommendations(recommendations: List[Dict], top_n: int = 5,
                         session: str = 'EVENING') -> List[Dict]:
    """融合多策略推荐"""
    if not recommendations:
        return []

    # 持仓板块加分：同一板块持仓后，下次推荐分数加 HELD_SECTOR_BONUS
    holded_sectors = load_holded_sectors()

    stock_map: Dict[str, Dict] = {}
    for rec in recommendations:
        code = rec.get('stock_code', '')
        if not code:
            continue
        #penalty = 0
        #reason = ''
        penalty, reason = recommendations_penalty(code, rec.get('stock_name', ''))
       
        dangerous_stock = get_dangerous_stocks()
        is_dangerous = False
        for s in dangerous_stock:
            if code in s['stock_code']:
                is_dangerous = True
                continue   
        if is_dangerous:
            continue
       # print("Is the stock dangerous? ", is_dangerous)
       # print("stock_code: ", code, "penalty: ", penalty, "reason: ", reason)
        ## 添加惩罚策略
       # penalty = 0  # 新闻情绪惩罚已禁用
        if code not in stock_map:
            stock_map[code] = {
                'stock_code': code,
                'stock_name': rec.get('stock_name', ''),
                'reasons': '',  # 买入理由（后续生成）
                'penalty_reason': reason,  # 新闻惩罚原因
                'sectors': [],
                'sector_phases': [],
                'strategies': [],
                'total_contribution': 0.0,
                'best_score': 0.0,
                'recs': [],
                'penalty': penalty,
            }
        e = stock_map[code]
        e['stock_name'] = rec.get('stock_name', e['stock_name'])
        sector = rec.get('sector', '')
        sector_phase = rec.get('sector_phase', 'UNKNOWN')
        if sector and sector not in e['sectors']:
            e['sectors'].append(sector)
        if sector_phase and sector_phase not in e['sector_phases']:
            e['sector_phases'].append(sector_phase)
        e['strategies'].append(rec.get('strategy_display', ''))
        e['reasons'] = rec.get('reasons', '')
        print("the penalty is : ", penalty)
        if penalty < 0:
            e['penalty_reason'] = reason
        weight = rec.get('strategy_weight', 1.0)
        win_rate = rec.get('strategy_win_rate', 0.60)
        score = rec.get('strategy_score', rec.get('score', 70))

        contribution = (score * 0.5 + win_rate * 100 * 0.5) * weight
        e['total_contribution'] += contribution
        e['best_score'] = max(e['best_score'], score)
      
        if  e['best_score'] < 80:
            continue
        # best_score 阈值已统一为 80（策略入口同此阈值）
        e['recs'].append(rec)
    # print("the sock_map is: ", stock_map)
    scored = []
    for code, data in stock_map.items():
        n = len(data['recs'])           # 策略命中数量
        final_best = data['best_score'] # 扣除惩罚后的最佳分数
        penalty = data.get('penalty', 0)
        print("=data['penalty_reason']: ", data['penalty_reason'])
        print("penalty: ", penalty)

        reasons = []  # 记录具体原因，方便后续输出分析细节
        # 1. 只要 penalty 是负数（利空扣分），直接判定风险，不进入推荐
        if penalty < 0:  # 轻微利空就开始警惕
            reasons+=data['penalty_reason']
            #print(f"🚫 {code} 存在利空新闻，直接淘汰")
            #continue

        # 2. 利好小幅度加分，不夸张
        if penalty > 0:
            penalty = min(penalty, 8)  # 利好最多+8
        # ------------------------------
        # 策略共振加分（实战核心）
        # ------------------------------
        if n == 1:
            consistency_bonus = 0
        elif n == 2:
            consistency_bonus = 22
        elif n >= 3:
            consistency_bonus = 30
        else:
            consistency_bonus = 0

        # ------------------------------
        # 正确综合得分（不平均，共振优先）
        # ------------------------------
        base_score = final_best + consistency_bonus + penalty

        # 持仓板块加分：同一板块持仓后，下次推荐分数加 HELD_SECTOR_BONUS
        sector_held_bonus = 0.0
        if holded_sectors:
            for sec in data['sectors']:
                if sec in holded_sectors:
                    sector_held_bonus = HELD_SECTOR_BONUS
                    break
        if sector_held_bonus > 0:
            data['sector_held_bonus'] = sector_held_bonus

        base_score = base_score + sector_held_bonus
        base_score = min(100, max(0, base_score))

        # v4.1: run_low 板块 (STRONG_DOWN) 要求 base_score >= 85 (高门槛)
        if data.get('recs'):
            actions = set(r.get('sector_action', 'run') for r in data['recs'])
            is_run_low = 'run_low' in actions
            threshold = 85 if is_run_low else 80
            if base_score < threshold:
                print(f"股票 {data['stock_name']}({code}) 基础得分 {base_score:.1f} 低于{threshold}分 (STRONG_DOWN板块高门槛)，剔除推荐")
                continue
        elif base_score < 80:
            print(f"股票 {data['stock_name']}({code}) 基础得分 {base_score:.1f} 低于80分，剔除推荐")
            continue

        # ------------------------------
        # 最终综合得分
        # ------------------------------
        combined = base_score * 0.8 + (data['total_contribution'] * 0.2)
        combined = min(100, max(0, combined))

        # ------------------------------
        # 早盘谨慎加分（只给真强势）
        # ------------------------------
        if session == 'MORNING' and final_best >= 85:
            morning_bonus = min(final_best - 80, 5)
            combined = min(combined + morning_bonus, 100)

        # 过滤低分
        if combined < 80:
            print(f"股票 {data['stock_name']}({code}) 综合得分 {combined:.1f} 低于80分，剔除推荐")
            continue

        scored.append({
            'stock_code': code,
            'stock_name': data['stock_name'],
            'combined_score': round(combined, 2),
            'best_score': round(final_best, 1),
            'strategy_count': n,
            'penalty': penalty,
            'penalty_reason': reasons,
            'reasons': data['reasons'],
            'strategies': list(set(data['strategies'])),
            'sectors': data['sectors'],
            'sector_phases': data['sector_phases'],
            'sector_held_bonus': sector_held_bonus,
            'recommendations': data['recs'],
        })

    scored.sort(key=lambda x: x['combined_score'], reverse=True)
    print("The all recommendations are: ", scored)
    top = scored[:top_n]
   #  print("The all recommendations are: ", scored)
    #top = scored[:top_n]
    # print("top: ", top)
    for i, s in enumerate(top):
        base = 0.20 - i * 0.03
        adj = (s['combined_score'] - 80) / 100 * 0.10
        position = max(0.08, min(0.25, base + adj))
        s['position_pct'] = round(position * 100, 1)
        s['position_value'] = round(position, 4)

    return top


# ── 报告生成 ────────────────────────────────────────────

def generate_buy_reason(stock: Dict, session: str) -> str:
    """生成买入理由"""
    reasons = stock.get('reasons', '')
    # strategies = stock.get('strategies', [])
    # score = stock.get('combined_score', 0)
    # best = stock.get('best_score', 0)
    # sectors = stock.get('sectors', [])

    # if session == 'EVENING':
    #     if best >= 85:
    #         reasons.append(f"技术面强烈看涨，综合得分{score:.0f}")
    #     if len(strategies) >= 2:
    #         reasons.append(f"{strategies[0]}、{strategies[1]}双信号共振")
    #     elif strategies:
    #         reasons.append(f"{strategies[0]}信号确认")
    #     if sectors and sectors[0]:
    #         reasons.append(f"所属板块：{sectors[0]}")
    #     if score >= 80:
    #         reasons.append("尾盘低位吸纳，次日冲高概率大")
    #     elif score >= 70:
    #         reasons.append("趋势确认，尾盘买入博反弹")
    # else:  # MORNING
    #     if best >= 85:
    #         reasons.append(f"突破动量强劲，早盘追涨，综合得分{score:.0f}")
    #     if len(strategies) >= 2:
    #         reasons.append(f"{strategies[0]}、{strategies[1]}信号共振")
    #     elif strategies:
    #         reasons.append(f"{strategies[0]}信号确认")
    #     if sectors and sectors[0]:
    #         reasons.append(f"所属板块：{sectors[0]}")
    #     if score >= 80:
    #         reasons.append("早盘确认动量，开盘即买入")
    #     elif score >= 70:
    #         reasons.append("趋势确认，逢低买入博新高")

    return reasons


def build_report(top: List[Dict], session: str, total_recs: int,
                 market_phase: str = 'UNKNOWN', phase_label: str = '未知',
                 position_cap: float = 0.30,
                 sector_filter_stats: Optional[Dict] = None,
                 sector_phases: Optional[Dict] = None) -> str:
    label = '14:30 尾盘买' if session == 'EVENING' else '16:00 早盘买（次日）'
    date = datetime.now().strftime('%Y-%m-%d')
    sector_filter_stats = sector_filter_stats or {}

    lines = []
    lines.append('=' * 60)
    lines.append(f'融合策略推荐报告  [{label}]')
    lines.append(f'生成时间: {date} {datetime.now().strftime("%H:%M:%S")}')
    lines.append(f'大盘状态: {phase_label}（{market_phase}）')
    lines.append(f'仓位上限: {position_cap * 100:.0f}%')
    lines.append('=' * 60)
    lines.append(f'策略推荐总数: {total_recs}')
    lines.append(f'融合推荐数: {len(top)}')
    lines.append(f'总仓位建议: {sum(s["position_pct"] for s in top):.0f}%')

    # 板块过滤摘要
    n_reserve = len(sector_filter_stats.get('reserve', []))
    n_block = len(sector_filter_stats.get('block', []))
    n_unknown = len(sector_filter_stats.get('unknown_sector', []))
    if n_reserve or n_block or n_unknown:
        lines.append(f'板块过滤: 预留 {n_reserve} 只 | 禁止 {n_block} 只 | 无板块 {n_unknown} 只')

    lines.append('')

    if not top:
        lines.append('⚠️  未找到符合条件的推荐股票')
        lines.append('建议：当前市场无明确机会，控制仓位等待')
        if n_block:
            lines.append(f'   其中 {n_block} 只因所属板块【下行】或不明被禁止买入')
        if n_reserve:
            lines.append(f'   其中 {n_reserve} 只因所属板块【波段/震荡】预留（策略设计中）')
        return '\n'.join(lines)

    for i, s in enumerate(top, 1):
        tag = '🔥' if i == 1 else '✅' if i == 2 else '📌'
        if s.get('is_etf_phase_recommendation'):
            tag = '📈'
        lines.append(f'{tag} {i}. {s["stock_name"]}({s["stock_code"]})')
        lines.append(f'   综合得分: {s["combined_score"]:.1f}  |  最高单策略: {s["best_score"]:.1f}')
        strategies = s.get('strategies') or []
        lines.append(f'   确认策略: {", ".join(strategies[:3])}')
        penalty = s.get('penalty', 0) or 0
        lines.append(f'   新闻损失: {penalty:.0f}分')
        if penalty < 0:
            lines.append(f'   新闻原因: {", ".join(s.get("penalty_reason", []))}')

        lines.append(f'   买入理由: {generate_buy_reason(s, session)}')
        lines.append(f'   买入仓位: {s["position_pct"]:.0f}%')
        if s.get('sector_held_bonus', 0) > 0:
            lines.append(f'   🔁 持仓板块加成: +{s["sector_held_bonus"]:.0f}分（持仓同板块）')
        if s.get('is_etf_phase_recommendation'):
            lines.append(f'   🏷️ 来源: 板块 ETF - detector STRONG_UP 信号（不参与个股策略评分）')

        if s.get('sectors'):
            sec_phases_map = s.get('sector_phases') or []
            sector_phase_labels = []
            for sec in s['sectors']:
                # 优先用 s 自身 sector_phases，回退用全量 sector_phases
                sp = sec_phases_map[0] if sec_phases_map else (sector_phases or {}).get(sec, 'UNKNOWN')
                sector_phase_labels.append(f"{sec}({PHASE_LABELS_CN.get(sp, '未知')})")
            if sector_phase_labels:
                lines.append(f'   所属板块: {", ".join(sector_phase_labels[:2])}')
            else:
                lines.append(f'   所属板块: {", ".join(s["sectors"][:2])}')
        lines.append('')

    lines.append('=' * 60)
    lines.append('⚠️  仅供参考，不构成投资建议')
    return '\n'.join(lines)


def write_recommendations(top: List[Dict], session: str, success: int, no_result: int, err_count: int,
                          market_phase: str = 'UNKNOWN', phase_label: str = '未知',
                          position_cap: float = 0.30,
                          sector_filter_stats: Optional[Dict] = None,
                          sector_phases: Optional[Dict] = None):
    """写入推荐文件：skill目录 + 统一入口"""
    date_str = datetime.now().strftime('%Y%m%d')
    session_str = 'EVENING_BUY' if session == 'EVENING' else 'MORNING_BUY'
    sector_filter_stats = sector_filter_stats or {}

    rec_list = []
    for s in top:
        # 给板块附带 phase 标签
        sectors_with_phase = []
        for sec in s.get('sectors', []):
            sp = (sector_phases or {}).get(sec, 'UNKNOWN')
            sectors_with_phase.append({
                'name': sec,
                'phase': sp,
                'phase_label': PHASE_LABELS_CN.get(sp, '未知'),
            })

        strategies = s.get('strategies') or []
        rec_list.append({
            'code': s['stock_code'],
            'name': s['stock_name'],
            'penalty': s.get('penalty', 0),
            'penalty_reason': s.get('penalty_reason', []),
            'source': s.get('source') or (strategies[0] if strategies else 'fusion'),
            'recommend_date': datetime.now().strftime('%Y-%m-%d'),
            'entry_price': 0.0,
            'target_reason': generate_buy_reason(s, session),
            'combined_score': s['combined_score'],
            'best_score': s['best_score'],
            'strategies': strategies,
            'position_pct': s['position_pct'],
            'sectors': s.get('sectors', []),
            'sectors_detail': sectors_with_phase,
            'sector_held_bonus': s.get('sector_held_bonus', 0),
            'session': session_str,
            'weight': s.get('position_value', 0),
            'is_etf': s.get('is_etf', False),
            'is_etf_phase_recommendation': s.get('is_etf_phase_recommendation', False),
            'sector_action': s.get('sector_action', 'run'),
        })

    data = {
        'date': date_str,
        'session': session_str,
        'generated_at': datetime.now().isoformat(),
        'market_phase': market_phase,
        'market_phase_label': phase_label,
        'position_cap': position_cap,
        # ── 板块过滤统计 ──
        'sector_filter': {
            'sector_phases': sector_phases or {},
            'reserve': sector_filter_stats.get('reserve', []),
            'block': sector_filter_stats.get('block', []),
            'unknown_sector': sector_filter_stats.get('unknown_sector', []),
            'reserve_count': len(sector_filter_stats.get('reserve', [])),
            'block_count': len(sector_filter_stats.get('block', [])),
            'unknown_sector_count': len(sector_filter_stats.get('unknown_sector', [])),
        },
        'recommendations': rec_list,
        'total_position': round(sum(s['position_pct'] for s in top), 1),
        'stock_count': len(top),
        'strategy_count': success,
        'no_result_count': no_result,
        'error_count': err_count
    }

    # 写入 ./recommendations/
    os.makedirs(SKILL_RECO_DIR, exist_ok=True)
    skill_file = os.path.join(SKILL_RECO_DIR, f'{date_str}_{session_str.lower()}_recommendation.json')
    with open(skill_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'\n📄 推荐已写入: {skill_file}')


# ── ETF 推荐（消费 detector 的 STRONG_UP 板块 ETF）──

def collect_strong_up_etf_recommendations(market_info: Dict) -> List[Dict]:
    """
    从 market_phase.json 中提取 phase=STRONG_UP 的板块 ETF 推荐。
    用户原则："个股在板块下降根本不碰，可以考虑ETF"（v4.2）。
    STRONG_UP 时 ETF 是板块整体上行，可作为板块层面的 BUY 信号。

    返回: [{
        'stock_code': 'sh561760',
        'stock_name': '油气ETF华泰柏瑞',
        'sector': '油气',
        'sector_phase': 'STRONG_UP',
        'sector_action': 'run',
        'is_etf': True,
        'combined_score': 85.0,
        'best_score': 85.0,
        'position_pct': 12.0,  # 默认 12%（比个股低，因为是板块而非个股）
        'strategies': ['板块ETF-单边上行'],
        'reasons': '板块 STRONG_UP（连续 3 日单边上行，gain_20=5.2%, slope=2.81%）, 推荐板块ETF',
        'is_etf_phase_recommendation': True,
        'source': 'etf_phase_detector',
    }, ...]
    """
    sectors_detail = market_info.get('sectors_detail') or []
    recs = []

    # 大盘 phase 决定 ETF 仓位上限
    market_phase = market_info.get('phase', 'UNKNOWN')
    if market_phase == 'STRONG_UP':
        default_pos = 12.0  # 单边上行，给 12%
    elif market_phase == 'WAVE_UP':
        default_pos = 10.0  # 波段上行，给 10%
    elif market_phase == 'RANGE':
        default_pos = 8.0
    elif market_phase == 'STRONG_DOWN':
        default_pos = 8.0  # 大盘下行也要谨慎，但 STRONG_UP 板块仍可独立行情
    else:
        default_pos = 5.0

    for sec in sectors_detail:
        phase = sec.get('stable_phase') or sec.get('phase') or 'UNKNOWN'
        if phase != 'STRONG_UP':
            continue
        sector_name = sec.get('sector', '')
        if not sector_name:
            continue
        meta = sec.get('meta') or {}
        etf_codes = meta.get('etf_codes') or []
        # 排除 overheating 板块（detector 已降级为 NO_BUY）
        # 这里 detector 已写 phase=STRONG_UP，说明通过 v9 验证
        # 同一板块只推第一个 ETF（避免 sz159309/sh561760 同时出现导致仓位叠加）
        etf_code = None
        for c in etf_codes:
            if _is_etf_code(c):
                etf_code = c
                break
        if not etf_code:
            continue

        # 从 watchlist.yaml 查 ETF 名称（支持 sh/sz 前缀多种写法）
        etf_name = _lookup_etf_name(etf_code)
        if not etf_name:
            etf_name = f'{sector_name}ETF'

        indicator = sec.get('indicator') or {}
        gain_20 = indicator.get('gain_20d', 0) or 0
        slope = indicator.get('ma20_slope_5d_pct', 0) or 0
        n_above = indicator.get('n_above_ma60', 0) or 0

        reasons = (
            f'板块【{sector_name}】STRONG_UP（连续 3 日单边上行），'
            f'gain_20={gain_20*100:.1f}%, slope={slope:.2f}%, '
            f'站上 MA60 {n_above} 日；推荐买入板块ETF'
        )

        recs.append({
            'stock_code': etf_code,
            'stock_name': etf_name,
            'sector': sector_name,
            'sector_phase': 'STRONG_UP',
            'sector_action': 'run',
            'is_etf': True,
            'is_etf_phase_recommendation': True,
            'source': 'etf_phase_detector',
            'combined_score': 85.0,
            'best_score': 85.0,
            'strategy_score': 85.0,
            'strategy_win_rate': 0.65,
            'strategy_weight': 0.9,
            'position_pct': default_pos,
            'position_value': default_pos / 100.0,
            'strategies': ['板块ETF-单边上行'],
            'reasons': reasons,
            'penalty': 0.0,
            'penalty_reason': [],
            'sectors': [sector_name],
            'sector_phases': ['STRONG_UP'],
            'strategy_count': 1,
            'sector_held_bonus': 0.0,
            'recommendations': [],
        })

    return recs


def _lookup_etf_name(etf_code: str) -> str:
    """从 watchlist.yaml 查 ETF 名称。
    支持两种格式：
      - etfs: [{name: ..., code: ...}, ...]
      - etfs: [["name", "code"], ...]  ← 当前 watchlist.yaml 用这种
    """
    raw = etf_code[2:] if etf_code.startswith(('sh', 'sz')) else etf_code
    watchlist_paths = [
        os.path.join(_BASE_DIR, 'my_stock_pool', 'watchlist.yaml'),
        os.path.join(_BASE_DIR, 'my_stock_pool', 'watchlist_core.yaml'),
    ]
    for path in watchlist_paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            # 遍历所有 sector
            for sector_name, sector_data in data.items():
                if not isinstance(sector_data, dict):
                    continue
                etfs = sector_data.get('etfs') or []
                if not isinstance(etfs, list):
                    continue
                for etf in etfs:
                    code = ''
                    name = ''
                    if isinstance(etf, dict):
                        code = str(etf.get('code', '')).strip()
                        name = str(etf.get('name', '')).strip()
                    elif isinstance(etf, (list, tuple)) and len(etf) >= 2:
                        name = str(etf[0]).strip()
                        code = str(etf[1]).strip()
                    if code == raw or code == etf_code:
                        return name
        except Exception:
            continue
    return ''


def refresh_market_phase() -> bool:
    """
    实时调用 market_phase_detector.py 重新生成 market_phase.json，
    保证 fusion_runner 用的是最新板块状态（不依赖外部定时任务）。
    使用 subprocess 独立进程，避免 sys.argv 冲突。
    返回 True 表示成功刷新；False 表示失败（将回退到现有 JSON）。
    """
    import subprocess
    detector_path = os.path.join(_SCRIPT_DIR, 'market_phase_detector.py')
    if not os.path.exists(detector_path):
        print(f'⚠️  detector 脚本不存在: {detector_path}')
        return False
    try:
        print(f'🔄 实时调用 market_phase_detector 刷新板块状态...')
        # 用相同 Python 解释器，subprocess 隔离 sys.argv
        result = subprocess.run(
            [sys.executable, detector_path, '--all'],
            cwd=_SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode == 0:
            print(f'✅ market_phase.json 已刷新')
            return True
        else:
            print(f'⚠️  detector 退出码 {result.returncode}: {result.stderr[-300:]}')
            return False
    except subprocess.TimeoutExpired:
        print(f'⚠️  detector 超时 (>180s)')
        return False
    except Exception as e:
        print(f'⚠️  detector 调用失败: {e}')
        return False


# ── 主运行 ──────────────────────────────────────────────

def run_fusion(session: str, top_n: int = 5):
    print(session)
    strategies = EVENING_STRATEGIES if session == 'EVENING' else MORNING_STRATEGIES
    label = '尾盘买策略融合' if session == 'EVENING' else '早盘买策略融合'

    print(f'\n{"="*60}')
    print(f'融合策略运行器  [{label}]')
    print(f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'{"="*60}')

    # ── 实时刷新板块状态（保证数据新鲜）──
    # refresh_market_phase()

    # ── 读取大盘状态（仅用于仓位上限）──
    market_info = load_market_phase()
    market_phase = market_info.get('phase', 'UNKNOWN')
    phase_label = market_info.get('phase_label', '未知')
    position_cap = PHASE_POSITION_CAP.get(market_phase, 0.30)

    # 板块 phase 映射（用于个股过滤）
    sector_phases = market_info.get('sector_phases', {})
    has_sector_data = market_info.get('has_sector_data', False)

    print(f'\n📊 大盘状态: {phase_label}（{market_phase}）')
    print(f'   仓位上限: {position_cap * 100:.0f}%')
    if has_sector_data:
        # 按 phase 统计板块
        phase_count = {}
        for sec, p in sector_phases.items():
            phase_count[p] = phase_count.get(p, 0) + 1
        print(f'   板块 phase 分布: {phase_count}（共 {len(sector_phases)} 个板块）')
    if market_info.get('big_down_candle'):
        print(f'   ⚠️  大盘出现大阴线（≤-3%）')
    if market_info.get('big_up_candle'):
        print(f'   🔺 大盘出现大阳线（≥+3%）')
    if market_info.get('generated_at'):
        print(f'   数据时间: {market_info["generated_at"]}')
    if market_info.get('error'):
        print(f'   ⚠️  {market_info["error"]}')

    all_recs = []
    sector_filter_stats = {'reserve': [], 'block': [], 'unknown_sector': []}
    success = 0
    no_result = 0
    err_count = 0

    # ── 始终运行所有策略（板块级过滤在 scan_strategy 内做）──
    for strategy in strategies:
        meta = STRATEGY_META.get(strategy, {})
        display = meta.get('display', strategy)
        print(f'▶️  运行 {display}...', end=' ', flush=True)

        try:
            recs, fstats = scan_strategy(
                strategy, top_n=top_n,
                sector_phases=sector_phases,
                filter_enabled=has_sector_data,
            )
            print(strategy, ": ", recs)
            for k in sector_filter_stats:
                sector_filter_stats[k].extend(fstats.get(k, []))
            if recs:
                all_recs.extend(recs)
                success += 1
                print(f'✅ {len(recs)} 条推荐')
            else:
                no_result += 1
                print('⚠️  无结果')
        except Exception as e:
            err_count += 1
            print(f'❌ {e}')

    print(f'\n{"="*60}')
    print(f'共运行 {len(strategies)} 个策略，成功 {success} 个，无结果 {no_result} 个，错误 {err_count} 个')
    print(f'共收集 {len(all_recs)} 条推荐（板块过滤后）')
    if has_sector_data:
        print(f'板块过滤：预留 {len(sector_filter_stats["reserve"])} 只，'
              f'禁止 {len(sector_filter_stats["block"])} 只，'
              f'无板块 {len(sector_filter_stats["unknown_sector"])} 只')

    top = fuse_recommendations(all_recs, top_n=top_n, session=session)

    # ── 追加：板块 ETF 推荐（消费 detector 的 STRONG_UP 板块）──
    etf_recs = collect_strong_up_etf_recommendations(market_info)
    if etf_recs:
        print(f'\n📈 板块 ETF 推荐（STRONG_UP）: {len(etf_recs)} 个')
        for r in etf_recs:
            print(f'   • {r["stock_name"]}({r["stock_code"]}) [{r["sector"]}] reasons={r["reasons"][:60]}')
        # 追加到 top（按 combined_score 排序，ETF 固定 85.0）
        top = sorted(top + etf_recs, key=lambda x: x.get('combined_score', 0), reverse=True)

    # ── 应用大盘仓位上限（等比缩放）──
    original_total = sum(s.get('position_pct', 0) for s in top)
    if original_total > position_cap * 100:
        scale = (position_cap * 100) / original_total
        for s in top:
            s['position_pct'] = round(s['position_pct'] * scale, 1)
            s['position_value'] = round(s['position_pct'] / 100, 4)
            s['position_capped'] = True
            s['position_cap'] = position_cap
        print(f'⚠️  仓位超限 {original_total:.1f}% → 按 {position_cap*100:.0f}% 等比缩放（×{scale:.3f}）')

    report = build_report(top, session, len(all_recs) + len(etf_recs),
                          market_phase=market_phase, phase_label=phase_label,
                          position_cap=position_cap,
                          sector_filter_stats=sector_filter_stats,
                          sector_phases=sector_phases)
    print('\n' + report)

    write_recommendations(top, session, success, no_result, err_count,
                          market_phase=market_phase, phase_label=phase_label,
                          position_cap=position_cap,
                          sector_filter_stats=sector_filter_stats,
                          sector_phases=sector_phases)
    return top


def main():
    parser = argparse.ArgumentParser(description='融合交易策略运行器')
    parser.add_argument('--session', type=str, required=True,
                       choices=['EVENING', 'MORNING', '14:30', '16:00'],
                       help='EVENING/14:30=尾盘买, MORNING/16:00=早盘买(次日)')
    parser.add_argument('--top', type=int, default=5, help='推荐数量（默认5）')
    args = parser.parse_args()

    session_map = {'14:30': 'EVENING', '16:00': 'MORNING'}
    session = session_map.get(args.session, args.session)

    run_fusion(session, top_n=args.top)


if __name__ == '__main__':
    main()
