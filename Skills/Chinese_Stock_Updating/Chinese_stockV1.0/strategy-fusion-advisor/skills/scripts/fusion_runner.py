#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
融合交易策略运行器
- 14:30 运行尾盘买策略 → 输出 top5 推荐
- 16:00 运行早盘买策略 → 输出 top5 推荐
结果写入 <repo>/recommendations/YYYYMMDD_{MORNING,EVENING}_buy_recommendation.json
（<repo> 由 common/paths.py 自动推导，也可用 STOCK_ROOT 覆盖）
"""

import os
import sys
import json
import argparse
import importlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ── 路径设置：统一由 common/paths.py 推导，不再硬编码绝对路径 ──
# fusion_runner.py 位于 <repo>/strategy-fusion-advisor/skills/scripts/
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))    # .../skills/scripts
_SKILL_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))  # .../strategy-fusion-advisor
_BASE_DIR = os.path.dirname(_SKILL_DIR)                     # 仓库根目录
sys.path.insert(0, _SCRIPT_DIR)

_root = _BASE_DIR
while not os.path.exists(os.path.join(_root, "common", "paths.py")) and _root != os.path.dirname(_root):
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "common"))
from paths import MARKET_PHASE_FILE, RECO_DIR                # noqa: E402
from holdings import load_holdings                            # noqa: E402
from watchlist import load_watchlist_entries                  # noqa: E402

# 推荐文件写入位置（<repo>/recommendations/）
SKILL_RECO_DIR = str(RECO_DIR)


# ── 重依赖延迟加载 ─────────────────────────────────────────
# 新闻情绪 / 财报黑名单 / 板块映射都依赖 akshare、LLM 等外部资源。
# 改成按需导入后：既能在离线环境 import 本模块做单元测试，
# 单个依赖缺失也不会让整个融合流程崩掉。
_detector = None


def get_sector_by_stock(code: str) -> str:
    """个股 → 板块（映射表由 market_phase_detector 从 watchlist.yaml 构建）。"""
    global _detector
    if _detector is None:
        try:
            import market_phase_detector as _mod
            _detector = _mod
        except Exception as e:  # noqa: BLE001 - 缺依赖时要能降级运行
            print(f"[WARN] get_sector_by_stock 加载失败: {e}")
            _detector = False
    if not _detector:
        return "UNKNOWN"
    return _detector.get_sector_by_stock(code)


def news_penalty(code: str, name: str):
    """新闻多空扣分；新闻模块不可用时返回中性值。"""
    try:
        from test_news import recommendations_penalty
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 新闻情绪模块不可用，跳过新闻扣分: {e}")
        return 0, []
    return recommendations_penalty(code, name)


def dangerous_stocks() -> List[Dict]:
    """财报不及预期黑名单；模块不可用时返回空名单。"""
    try:
        from earnings_caculate import get_dangerous_stocks
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 财报黑名单模块不可用: {e}")
        return []
    return get_dangerous_stocks()


# ========== 强制关闭代理，解决 akshare 连接失败 ==========
# 清空系统代理
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["FTP_PROXY"] = ""
os.environ["ALL_PROXY"] = ""
os.environ["SOCKS_PROXY"] = ""


# ── 配置层（策略分组 / 权重 / 板块门控 / 阈值）──────────────
from fusion_config import (
    build_exit_plan,
    build_conditional_orders,
    CLOSE_STRATEGIES,
    SIGNAL_COOLDOWN_DAYS,
    DAILY_TOP_N,
    MARKET_TRADE_SWITCH,
    RANGE_MODE,
    ETF_TRADABLE_PHASES,
    EVENING_STRATEGIES,
    MORNING_STRATEGIES,
    STRATEGY_META,
    ANALYZER_CLASS,
    PHASE_POSITION_CAP,
    PHASE_SECTOR_FILTER_ETF,
    PHASE_SECTOR_FILTER_STOCK,
    PHASE_LABELS_CN,
    HELD_SECTOR_BONUS,
    _is_etf_code,
    MIN_STRATEGY_SCORE,
    MIN_COMBINED_SCORE,
    RUN_LOW_MIN_SCORE,
    ETF_BASE_SCORE,
    CONSISTENCY_BONUS_2,
    CONSISTENCY_BONUS_3,
    MORNING_BONUS_CAP,
    PENALTY_BONUS_CAP,
    BASE_SCORE_WEIGHT,
    CONTRIBUTION_WEIGHT,
    POSITION_BASE,
    POSITION_STEP,
    POSITION_SCORE_GAIN,
    POSITION_MIN,
    POSITION_MAX,
    ETF_POSITION_BY_MARKET_PHASE,
    ETF_POSITION_DEFAULT,
)


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
    try:
        holdings = load_holdings()
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
            if res.get('score', 0) < MIN_STRATEGY_SCORE:
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
    except Exception as e:
        # 绝不静默吞异常：以前这里是 "except Exception: pass"，
        # 策略报错只表现为「无结果」，排查时完全没有线索。
        import traceback
        print(f"❌ 策略 {strategy_name} 执行失败: {e}", file=sys.stderr)
        traceback.print_exc()
        stats.setdefault('errors', []).append({
            'strategy': strategy_name,
            'error': f"{type(e).__name__}: {e}",
        })

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

def _entry_quality_keep_ratio() -> float:
    """读取入场质量分的保留比例（模块不可用时返回 1.0 = 不过滤）。"""
    try:
        import entry_quality as eq
        return eq.ENTRY_QUALITY_KEEP_RATIO
    except Exception:
        return 1.0


def _daily_bars_for(code: str):
    """取标的日线序列（供入场质量分使用）。任何失败都返回 None，不阻断主流程。"""
    try:
        from data_source import get_stock_realtime  # 延迟导入，离线环境也能 import 本模块
        df, _ = get_stock_realtime(code)
        if df is None or len(df) == 0:
            return None
        rows = []
        for _, r in df.iterrows():
            rows.append({"open": float(r["open"]), "high": float(r["high"]),
                         "low": float(r["low"]), "close": float(r["close"]),
                         "volume": float(r.get("volume") or 0)})
        return rows
    except Exception:
        return None


def apply_entry_quality_filter(recs: List[Dict], keep_ratio: float = None) -> List[Dict]:
    """按入场质量分过滤候选（保留前 keep_ratio 比例）。

    入场质量分衡量"这个入场点位好不好"：不追高、不过热、有趋势、有资金。
    它只做**过滤**不做排序——每日候选通常只有 3 条左右，排序没有施展空间。

    数据取不到时**放行**（返回 None），避免因数据问题误杀候选。
    """
    try:
        import entry_quality as eq
    except Exception as e:
        print(f'[WARN] 入场质量分模块不可用，按不过滤处理: {e}')
        return recs
    ratio = eq.ENTRY_QUALITY_KEEP_RATIO if keep_ratio is None else keep_ratio
    if ratio >= 1.0 or not recs:
        return recs
    scored = []
    for r in recs:
        code = r.get('stock_code', '')
        bars = _daily_bars_for(code) if code else None
        r['entry_quality'] = eq.entry_quality_score(bars) if bars else None
        scored.append(r)
    vals = sorted(x['entry_quality'] for x in scored if x.get('entry_quality') is not None)
    if not vals:
        print('⚠️  入场质量分：所有候选都取不到日线，本次不过滤')
        return scored
    idx = max(0, min(int(len(vals) * (1.0 - ratio)), len(vals) - 1))
    thr = vals[idx]
    kept = [x for x in scored
            if x.get('entry_quality') is None or x['entry_quality'] >= thr]
    if len(kept) != len(scored):
        print(f'🎯 入场质量分过滤：{len(scored)} → {len(kept)} 条'
              f'（保留前 {ratio:.0%}，阈值 {thr:.3f}）')
    return kept


def _dominant_action(actions) -> str:
    """把同一标的的多个板块动作归并成一个，取最保守的那个（供展示/审计）。"""
    for a in ('block', 'reserve', 'run_low', 'run'):
        if a in actions:
            return a
    return 'run'


# ── 信号冷却期：推荐历史（第二轮优化）──────────────────────
# 记录「哪天推荐了哪些标的」，下次运行时据此跳过冷却期内重复出现的标的。
# 之所以要在推荐层去重：回测显示同一标的重复推荐的均值只有首次推荐的 43%。
COOLDOWN_HISTORY_FILE = os.path.join(SKILL_RECO_DIR, 'cache', 'recent_picks.json')
COOLDOWN_HISTORY_MAX = 120      # 只保留最近 120 个运行日的记录


def _load_cooldown_history() -> Dict:
    """读取推荐历史；文件缺失或损坏时退回空历史（不阻断主流程）。"""
    data = None
    try:
        with open(COOLDOWN_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = None                      # 首次运行，属正常情况
    except Exception as e:
        print(f"[WARN] 推荐历史读取失败，按空历史处理: {e}")
    if isinstance(data, dict) and isinstance(data.get('runs'), list):
        return data
    return {'runs': []}


def load_recent_picks() -> Dict[str, str]:
    """返回 {标的代码: 最近一次被推荐的日期}。"""
    hist = _load_cooldown_history()
    last: Dict[str, str] = {}
    for run in hist['runs']:
        for code in run.get('codes', []):
            last[code] = run.get('date', '')
    return last


def trading_days_since(date_str: str) -> int:
    """该日期距「最近一次记录」相隔多少个运行日（用运行日近似交易日）。

    返回 None 表示没有历史记录。
    """
    if not date_str:
        return None
    runs = [r.get('date', '') for r in _load_cooldown_history()['runs']]
    if date_str not in runs:
        return None          # 不在历史里 → 无从判断，按"未推荐过"处理
    return len([d for d in runs if d > date_str])


def record_recent_picks(codes: List[str], date_str: str) -> None:
    """把本次推荐写入历史（同日重复运行则覆盖）。"""
    hist = _load_cooldown_history()
    runs = [r for r in hist['runs'] if r.get('date') != date_str]
    runs.append({'date': date_str, 'codes': sorted(set(codes))})
    runs.sort(key=lambda r: r.get('date', ''))
    hist['runs'] = runs[-COOLDOWN_HISTORY_MAX:]
    os.makedirs(os.path.dirname(COOLDOWN_HISTORY_FILE), exist_ok=True)
    with open(COOLDOWN_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)


def fuse_recommendations(recommendations: List[Dict], top_n: int = 5,
                         session: str = 'EVENING',
                         cooldown_days: int = SIGNAL_COOLDOWN_DAYS) -> List[Dict]:
    """融合多策略推荐。

    cooldown_days: 同一标的在 N 个运行日内只接受首次信号；0 = 关闭。
    """
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
        penalty, reason = news_penalty(code, rec.get('stock_name', ''))
       
        dangerous_stock = dangerous_stocks()
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
                'price': 0.0,          # 信号日参考价，用于生成出场计划
                'sector_action_set': set(),
            }
        e = stock_map[code]
        e['stock_name'] = rec.get('stock_name', e['stock_name'])
        if not e['price']:
            for _k in ('current_price', 'price', 'close', 'latest_price'):
                _v = rec.get(_k)
                if isinstance(_v, (int, float)) and _v > 0:
                    e['price'] = float(_v)
                    break
        sector = rec.get('sector', '')
        sector_phase = rec.get('sector_phase', 'UNKNOWN')
        if sector and sector not in e['sectors']:
            e['sectors'].append(sector)
        if sector_phase and sector_phase not in e['sector_phases']:
            e['sector_phases'].append(sector_phase)
        e['strategies'].append(rec.get('strategy_display', ''))
        _act = rec.get('sector_action')
        if _act:
            e['sector_action_set'].add(_act)
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
      
        if e['best_score'] < MIN_STRATEGY_SCORE:
            continue
        # best_score 阈值与策略入口保持一致（MIN_STRATEGY_SCORE）
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
            penalty = min(penalty, PENALTY_BONUS_CAP)  # 利好加分封顶
        # ------------------------------
        # 策略共振加分（实战核心）
        # ------------------------------
        if n == 1:
            consistency_bonus = 0
        elif n == 2:
            consistency_bonus = CONSISTENCY_BONUS_2
        elif n >= 3:
            consistency_bonus = CONSISTENCY_BONUS_3
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

        # ── 截断策略（重要修正）─────────────────────────────
        # 入选门槛本身就是 80 分，再叠加 +22/+30 的共振加分必然 >= 102。
        # 原实现在这里直接 min(100, ...)，导致：
        #   1) 「2 个策略共振」与「3 个策略共振」得到完全相同的 base_score，
        #      共振加分形同虚设；
        #   2) 大量候选并列 100 分，top-N 退化为按字典插入顺序截取。
        # 现在分两个口径：
        #   base_score        —— 对外契约用的 0~100 分（保持不变，供门槛判定与展示）
        #   base_score_raw    —— 未截断的原始分，只用于排序（rank_score）
        base_score_raw = base_score
        base_score = min(100, max(0, base_score))

        # v4.1: run_low 板块 (STRONG_DOWN) 要求 base_score >= 85 (高门槛)
        if data.get('recs'):
            actions = set(r.get('sector_action', 'run') for r in data['recs'])
            is_run_low = 'run_low' in actions
            threshold = RUN_LOW_MIN_SCORE if is_run_low else MIN_COMBINED_SCORE
            if base_score < threshold:
                print(f"股票 {data['stock_name']}({code}) 基础得分 {base_score:.1f} 低于{threshold}分 (STRONG_DOWN板块高门槛)，剔除推荐")
                continue
        elif base_score < MIN_COMBINED_SCORE:
            print(f"股票 {data['stock_name']}({code}) 基础得分 {base_score:.1f} 低于80分，剔除推荐")
            continue

        # ------------------------------
        # 最终综合得分
        # ------------------------------
        combined = base_score * BASE_SCORE_WEIGHT + (data['total_contribution'] * CONTRIBUTION_WEIGHT)
        combined = min(100, max(0, combined))

        # 未截断的排序分：保留共振与贡献的全部区分度
        rank_score = base_score_raw * BASE_SCORE_WEIGHT + (data['total_contribution'] * CONTRIBUTION_WEIGHT)

        # ------------------------------
        # 早盘谨慎加分（只给真强势）
        # ------------------------------
        if session == 'MORNING' and final_best >= RUN_LOW_MIN_SCORE:
            morning_bonus = min(final_best - MIN_COMBINED_SCORE, MORNING_BONUS_CAP)
            combined = min(combined + morning_bonus, 100)
            rank_score += morning_bonus

        # 过滤低分
        if combined < MIN_COMBINED_SCORE:
            print(f"股票 {data['stock_name']}({code}) 综合得分 {combined:.1f} 低于80分，剔除推荐")
            continue

        scored.append({
            'stock_code': code,
            'stock_name': data['stock_name'],
            'combined_score': round(combined, 2),
            'best_score': round(final_best, 1),
            # 中间量也落盘，便于事后核对"为什么是这一分"
            'base_score': round(base_score, 2),
            'base_score_raw': round(base_score_raw, 2),
            'rank_score': round(rank_score, 2),
            'consistency_bonus': consistency_bonus,
            'total_contribution': round(data['total_contribution'], 2),
            'strategy_count': n,
            'penalty': penalty,
            'penalty_reason': reasons,
            'reasons': data['reasons'],
            'strategies': list(set(data['strategies'])),
            'sectors': data['sectors'],
            'sector_phases': data['sector_phases'],
            'sector_held_bonus': sector_held_bonus,
            'recommendations': data['recs'],
            'price': round(data.get('price', 0.0), 3),
            'exit_plan': build_exit_plan(data.get('price', 0.0)),
            # 真实板块动作：此前 scored 从不携带该字段，
            # 导致输出 JSON 里 sector_action 恒为默认值 'run'，
            # run_low（STRONG_DOWN 板块的 ETF）被错误标注成 run。
            'sector_actions': sorted(data.get('sector_action_set') or []),
            'sector_action': _dominant_action(data.get('sector_action_set') or set()),
        })

    # 排序键（2026-10 复审决定）：
    #   原先用未截断的 rank_score，理由是"combined_score 会在 100 分处并列"。
    #   复审实测 rank_score 的 IC = -0.084，比 combined_score 的 -0.052 更差，
    #   且回测显示两者选出的标的完全相同（并列在实际数据里几乎不出现）。
    #   因此回退为文档 3.9 描述的 combined_score，去掉一层负 IC 的中间量。
    scored.sort(key=lambda x: (x['combined_score'], x['strategy_count']), reverse=True)
    print("The all recommendations are: ", scored)
    top = scored[:top_n]

    # ── 信号冷却期（在选出 top-N 之后再剔除）──
    # 关键：**不回填**。回测对比显示，冷却后让次优候选补位会把收益优势吃回去
    # （回填 +1.92% vs 不回填 +2.75%），因为补上来的名字本身没有 alpha。
    # 宁缺毋滥：某天没有满足条件的新信号，就空仓。
    if cooldown_days > 0 and top:
        try:
            _last = load_recent_picks()
            _kept, _cooled = [], []
            for _s in top:
                _gap = trading_days_since(_last.get(_s['stock_code']))
                if _gap is not None and _gap < cooldown_days:
                    _cooled.append((_s['stock_code'], _s['stock_name'], _gap))
                    continue
                _kept.append(_s)
            if _cooled:
                _names = "、".join(f"{n}({g}日前)" for _, n, g in _cooled[:5])
                print(f"❄️  冷却期剔除：{len(top)} → {len(_kept)} 只（{cooldown_days} 个运行日内已推荐过：{_names}）")
            top = _kept
        except Exception as _e:
            print(f"[WARN] 冷却期过滤失败，按不启用处理: {_e}")
   #  print("The all recommendations are: ", scored)
    #top = scored[:top_n]
    # print("top: ", top)
    for i, s in enumerate(top):
        base = POSITION_BASE - i * POSITION_STEP
        adj = (s['combined_score'] - MIN_COMBINED_SCORE) / 100 * POSITION_SCORE_GAIN
        position = max(POSITION_MIN, min(POSITION_MAX, base + adj))
        # 先定稿展示用的百分数，再由它推导小数权重，
        # 否则 position_pct 与 position_value 四舍五入后会互相矛盾。
        s['position_pct'] = round(position * 100, 1)
        s['position_value'] = round(s['position_pct'] / 100, 4)

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
        _ep = s.get('exit_plan') or {}
        if _ep:
            _sp = _ep.get('stop_price')
            _mx = _ep.get('entry_max_price')
            _bits = [f'持有 ≤{_ep.get("max_hold_days", 10)} 日']
            if _sp:
                _bits.append(f'止损 {_sp}(-{_ep.get("stop_pct", 8):.0f}%)')
            _bits.append(f'最高点回撤 {_ep.get("trail_pct", 12):.0f}% 离场')
            lines.append(f'   出场计划: {" | ".join(_bits)}')
            if _mx:
                lines.append(f'   ⚠️ 次日开盘高于 {_mx} 则放弃（不追高）')
        if s.get('sector_held_bonus', 0) > 0:
            lines.append(f'   🔁 持仓板块加成: +{s["sector_held_bonus"]:.0f}分（持仓同板块）')
        if s.get('is_etf_phase_recommendation'):
            lines.append('   🏷️ 来源: 板块 ETF - detector STRONG_UP 信号（不参与个股策略评分）')

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
            'entry_price': s.get('price', 0.0),
            'entry_ref_price': s.get('price', 0.0),
            'exit_plan': s.get('exit_plan') or build_exit_plan(s.get('price', 0.0)),
            # 可直接填入券商 APP 的智能条件单参数（用户需求 3）
            'conditional_orders': build_conditional_orders(s.get('price', 0.0),
                                                           s.get('stock_name', '')),
            # 入场质量分（模块2 修复）：衡量该入场点位的好坏，供审计与过滤
            'entry_quality': s.get('entry_quality'),
            'entry_quality_keep_ratio': _entry_quality_keep_ratio(),
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

    # 记录本次推荐，供下次运行的冷却期查询
    if SIGNAL_COOLDOWN_DAYS > 0 and top:
        try:
            record_recent_picks([(s.get('code') or s.get('stock_code', '')) for s in top], date_str)
        except Exception as _e:
            print(f"[WARN] 推荐历史写入失败: {_e}")

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
        'combined_score': ETF_BASE_SCORE,
        'best_score': ETF_BASE_SCORE,
        'position_pct': 12.0,  # 默认 12%（比个股低，因为是板块而非个股）
        'strategies': ['板块ETF-单边上行'],
        'reasons': '板块 STRONG_UP（连续 3 日单边上行，gain_20=5.2%, slope=2.81%）, 推荐板块ETF',
        'is_etf_phase_recommendation': True,
        'source': 'etf_phase_detector',
    }, ...]
    """
    sectors_detail = market_info.get('sectors_detail') or []
    recs = []

    # 大盘 phase 决定 ETF 仓位上限（分档表见 fusion_config）
    market_phase = market_info.get('phase', 'UNKNOWN')
    default_pos = ETF_POSITION_BY_MARKET_PHASE.get(market_phase, ETF_POSITION_DEFAULT)

    for sec in sectors_detail:
        phase = sec.get('stable_phase') or sec.get('phase') or 'UNKNOWN'
        # 模块1 复审：RANGE 的 ETF 未来表现优于 STRONG_UP，原先只推 STRONG_UP
        # 等于把最好的档位闲置（见 fusion_config.ETF_TRADABLE_PHASES 的实测数据）。
        if phase not in ETF_TRADABLE_PHASES:
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

        _label = 'STRONG_UP（连续 3 日单边上行）' if phase == 'STRONG_UP' else f'{phase}（震荡）'
        reasons = (
            f'板块【{sector_name}】{_label}，'
            f'gain_20={gain_20*100:.1f}%, slope={slope:.2f}%, '
            f'站上 MA60 {n_above} 日；推荐买入板块ETF'
        )

        recs.append({
            'stock_code': etf_code,
            'stock_name': etf_name,
            'sector': sector_name,
            'sector_phase': phase,
            'sector_action': 'run',
            'is_etf': True,
            'is_etf_phase_recommendation': True,
            'source': 'etf_phase_detector',
            'combined_score': ETF_BASE_SCORE,
            'best_score': ETF_BASE_SCORE,
            'strategy_score': ETF_BASE_SCORE,
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
    """按代码从股票池查名称（找不到返回空串，由调用方用板块名兜底）。

    改动说明：原实现遍历 `data.items()` 找 `xxx.etfs` 字段，
    但现行 watchlist.yaml 的结构是 `watchlist.<sector>.<core|focus>`，
    两者对不上，导致该函数**从未真正命中过**，ETF 名称一直是兜底值。
    现在统一走 common/watchlist 的解析结果。
    """
    pure = etf_code[2:] if etf_code.startswith(("sh", "sz")) else etf_code
    for entry in load_watchlist_entries():
        code = entry["code"]
        if code == etf_code or (code[2:] if code[:2].lower() in ("sh", "sz") else code) == pure:
            return entry["name"]
    return ""

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
        print('🔄 实时调用 market_phase_detector 刷新板块状态...')
        # 用相同 Python 解释器，subprocess 隔离 sys.argv
        result = subprocess.run(
            [sys.executable, detector_path, '--all'],
            cwd=_SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode == 0:
            print('✅ market_phase.json 已刷新')
            return True
        else:
            print(f'⚠️  detector 退出码 {result.returncode}: {result.stderr[-300:]}')
            return False
    except subprocess.TimeoutExpired:
        print('⚠️  detector 超时 (>180s)')
        return False
    except Exception as e:
        print(f'⚠️  detector 调用失败: {e}')
        return False


# ── 主运行 ──────────────────────────────────────────────

def run_fusion(session: str, top_n: int = DAILY_TOP_N):
    print(session)
    _SESSION_MAP = {
        'CLOSE': (CLOSE_STRATEGIES, '收盘后策略融合（15:00 后统一运行）'),
        'EVENING': (EVENING_STRATEGIES, '尾盘买策略融合'),
        'MORNING': (MORNING_STRATEGIES, '早盘买策略融合'),
    }
    _ALIAS = {'15:05': 'CLOSE', '14:30': 'EVENING', '16:00': 'MORNING'}
    session = _ALIAS.get(session, session)
    strategies, label = _SESSION_MAP.get(session, _SESSION_MAP['EVENING'])

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

    # ── 大盘趋势交易开关（用户需求 2）──
    # 现状：大盘 phase 只调仓位上限，不阻止开仓 → 单边下跌月仍在交易。
    # 改为：STRONG_DOWN / WEAK_DOWN / UNKNOWN 直接禁止当日开仓。
    trade_mode = MARKET_TRADE_SWITCH.get(market_phase, "off")
    if trade_mode == "off":
        print(f'\n🛑 大盘趋势禁止开仓：{phase_label}（{market_phase}）')
        print('   规则：仅在 RANGE / WAVE_UP / STRONG_UP 三种大盘状态下开仓；')
        print('         单边下行、温和回调、趋势不明时一律空仓等待。')
        empty = {
            'date': datetime.now().strftime('%Y%m%d'),
            'session': {'CLOSE': 'CLOSE_BUY', 'EVENING': 'EVENING_BUY'}.get(session, 'MORNING_BUY'),
            'generated_at': datetime.now().isoformat(),
            'market_phase': market_phase,
            'market_phase_label': phase_label,
            'position_cap': position_cap,
            'trade_switch': 'off',
            'sector_filter': {'sector_phases': market_info.get('sector_phases', {}) or {}, 'reserve': [],
                              'block': [], 'unknown_sector': [],
                              'reserve_count': 0, 'block_count': 0, 'unknown_sector_count': 0},
            'recommendations': [],
            'total_position': 0,
            'stock_count': 0,
            'strategy_count': 0,
            'no_result_count': 0,
            'error_count': 0,
        }
        os.makedirs(SKILL_RECO_DIR, exist_ok=True)
        _sess_tag = {'CLOSE': 'CLOSE', 'EVENING': 'EVENING'}.get(session, 'MORNING')
        path = os.path.join(SKILL_RECO_DIR,
                            f'{datetime.now().strftime("%Y%m%d")}_{_sess_tag}_BUY_recommendation.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(empty, f, ensure_ascii=False, indent=2)
        print(f'   已写入空推荐：{path}')
        return empty

    print(f'\n✅ 大盘趋势允许开仓：{phase_label}（{market_phase}，模式 {trade_mode}）')

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
        print('   ⚠️  大盘出现大阴线（≤-3%）')
    if market_info.get('big_up_candle'):
        print('   🔺 大盘出现大阳线（≥+3%）')
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

    # 震荡期是否只允许 ETF / 稳健股（用户需求 2，默认关闭，见 fusion_config 说明）
    if RANGE_MODE != "full" and market_phase in ("RANGE", "WAVE_UP"):
        before = len(all_recs)
        all_recs = [r for r in all_recs if _is_etf_code(r.get('stock_code', ''))]
        print(f'🟡 震荡期限制（{RANGE_MODE}）：策略推荐 {before} → {len(all_recs)} 条'
              f'（仅保留 ETF）')

    # ── 入场质量分过滤（模块2 修复：现有 analyzer 打分与未来收益 IC 为负）──
    all_recs = apply_entry_quality_filter(all_recs)

    top = fuse_recommendations(all_recs, top_n=top_n, session=session)

    # ── 追加：板块 ETF 推荐（消费 detector 的 STRONG_UP 板块）──
    etf_recs = collect_strong_up_etf_recommendations(market_info)
    if etf_recs:
        print(f'\n📈 板块 ETF 推荐（STRONG_UP）: {len(etf_recs)} 个')
        for r in etf_recs:
            print(f'   • {r["stock_name"]}({r["stock_code"]}) [{r["sector"]}] reasons={r["reasons"][:60]}')
        # 追加到 top（按 combined_score 排序，ETF 固定 85.0）
        top = sorted(top + etf_recs, key=lambda x: x.get('combined_score', 0), reverse=True)

        # ETF 推荐同样受冷却期约束：回测里单只 ETF 一年被重复推荐最多 72 次，
        # 是重复信号的主要来源，不去重会让同一波行情被反复计数。
        if SIGNAL_COOLDOWN_DAYS > 0:
            try:
                _last = load_recent_picks()
                _kept = []
                for _s in top:
                    _code = _s.get('code') or _s.get('stock_code', '')
                    _gap = trading_days_since(_last.get(_code))
                    if _gap is not None and _gap < SIGNAL_COOLDOWN_DAYS:
                        continue
                    _kept.append(_s)
                if len(_kept) != len(top):
                    print(f'❄️  冷却期过滤ETF: {len(top)} → {len(_kept)}')
                top = _kept
            except Exception as _e:
                print(f'[WARN] ETF 冷却期过滤失败: {_e}')

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
                       choices=['CLOSE', 'EVENING', 'MORNING', '15:05', '14:30', '16:00'],
                       help='EVENING/14:30=尾盘买, MORNING/16:00=早盘买(次日)')
    parser.add_argument('--top', type=int, default=DAILY_TOP_N,
                        help=f'每日推荐数量（默认 {DAILY_TOP_N}，由回测确定）')
    args = parser.parse_args()

    session_map = {'14:30': 'EVENING', '16:00': 'MORNING'}
    session = session_map.get(args.session, args.session)

    run_fusion(session, top_n=args.top)


if __name__ == '__main__':
    main()
