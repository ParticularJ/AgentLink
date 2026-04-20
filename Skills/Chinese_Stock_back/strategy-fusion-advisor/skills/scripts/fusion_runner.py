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
from typing import Dict, List, Optional
import importlib

from news_sentiment import search_stock_news, calc_news_penalty


# ── 路径设置（相对路径，基于脚本所在目录）────────────────────
# fusion_runner.py 位于 strategy-fusion-advisor/skills/scripts/
# dirname ×3 → strategy-fusion-advisor/（SKILL_DIR）
# dirname ×4 → Chinese_Stock/（BASE_DIR）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # .../skills/scripts
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # .../strategy-fusion-advisor
_BASE_DIR = os.path.dirname(_SKILL_DIR)  # .../Chinese_Stock
# 推荐文件写入位置：Chinese_Stock/recommendations/
SKILL_RECO_DIR = os.path.join(_BASE_DIR, 'recommendations')





# ── 策略分组 ────────────────────────────────────────────
EVENING_STRATEGIES = [  # 尾盘买（14:30）  
    #'gap-fill-strategy',
    #'limit-up-retrace-strategy',
    'macd-divergence-strategy',
    #'rsi-oversold-strategy',
    #'volume-extreme-strategy',
    #'volume-retrace-ma-strategy',
    #'ma-bullish-strategy'
]

MORNING_STRATEGIES = [  # 早盘买次日（16:00）
    'breakout-high-strategy',
    'limit-up-analysis',
    'earnings-surprise-strategy',
    'morning-star-strategy'
]

# 策略元数据
STRATEGY_META = {
    'ma-bullish-strategy':        {'display': '均线多头排列',  'win_rate': 0.65, 'weight': 1.0},
    'breakout-high-strategy':     {'display': '突破新高',      'win_rate': 0.60, 'weight': 0.9},
    'gap-fill-strategy':          {'display': '缺口填充',      'win_rate': 0.62, 'weight': 0.8},
    'limit-up-retrace-strategy': {'display': '涨停回踩',      'win_rate': 0.60, 'weight': 0.9},
    'limit-up-analysis':          {'display': '涨停分析/打板', 'win_rate': 0.65, 'weight': 1.0},
    'macd-divergence-strategy':   {'display': 'MACD底背离',    'win_rate': 0.58, 'weight': 0.8},
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


# ── 策略扫描 ────────────────────────────────────────────

def scan_strategy(strategy_name: str, top_n: int = 5) -> List[Dict]:
    """运行单个策略，返回推荐列表"""
    meta = STRATEGY_META.get(strategy_name, {})
    print("meta: ", meta)
    analyzer = get_analyzer(strategy_name)
    if analyzer is None:
        return []

    results = []
    #for name, code, sector in all_stocks:
    try:
        result = None
        if(strategy_name == 'limit-up-analysis'):
            result = analyzer.analyze_all_limit_up()
        
        elif(strategy_name == 'earnings-surprise-strategy'):
            result = analyzer.scan_daily_earnings(datetime.now())
        else:
            result = analyzer.scan_all_stocks(top_n=top_n)
            # print(result)
        print(f"✅ 策略 {strategy_name} 运行完成，结果：")
       # print(result)
        
        for res in result:
            # print(res)
            if res.get('score', 0) >= 70:     
                result_sig = {}      
                # result['sector'] = res.get('sector')
                result_sig['stock_code'] = res.get('stock_code')
                result_sig['stock_name'] = res.get('stock_name')
                result_sig['strategy_name'] = strategy_name
                result_sig['strategy_display'] = meta.get('display', strategy_name)
                result_sig['strategy_win_rate'] = meta.get('win_rate', 0.60)
                result_sig['strategy_weight'] = meta.get('weight', 1.0)
                result_sig['strategy_score'] = res.get('score', 70)
                results.append(result_sig)
    except Exception:
        pass
    # print("results: ", results)
    results.sort(key=lambda x: x.get('score', 0), reverse=True)
    return results[:top_n]


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



def recommendations_penalty(stock_code: str, stock_name: str) -> int:
   # ——— 新闻情绪检测（仅对前10名候选股）——
    try:
        news = search_stock_news(stock_code,stock_name, days=7)
        penalty = calc_news_penalty(
            news['sentiment'],
            news['sentiment_score'],
            1
        )
        print(news)
        return penalty
    except Exception as e:
        print("Error: ", e)


# ── 融合评分 ────────────────────────────────────────────

def fuse_recommendations(recommendations: List[Dict], top_n: int = 5,
                         session: str = 'EVENING') -> List[Dict]:
    """融合多策略推荐"""
    if not recommendations:
        return []

    stock_map: Dict[str, Dict] = {}
    for rec in recommendations:
        code = rec.get('stock_code', '')
        if not code:
            continue

        ## 添加惩罚策略
        penalty=recommendations_penalty(rec.get('stock_code', ''), rec.get('stock_name', ''))

        print(penalty)

        if code not in stock_map:
            stock_map[code] = {
                'stock_code': code,
                'stock_name': rec.get('stock_name', ''),
                'sectors': [],
                'strategies': [],
                'total_contribution': 0.0,
                'best_score': 0.0,
                'recs': [],
            }
        e = stock_map[code]
        e['stock_name'] = rec.get('stock_name', e['stock_name'])
        # e['sectors'].append(rec.get('sector', ''))
        e['strategies'].append(rec.get('strategy_display', ''))

        weight = rec.get('strategy_weight', 1.0)
        win_rate = rec.get('strategy_win_rate', 0.60)
        score = rec.get('strategy_score', rec.get('score', 70))

        contribution = (score * 0.6 + win_rate * 100 * 0.4) * weight
        e['total_contribution'] += contribution
        e['best_score'] = max(e['best_score'], score)
        e['best_score'] = max(e['best_score'] + penalty, 0)  # 扣除新闻情绪惩罚
        if  e['best_score'] < 70:
            continue
        e['recs'].append(rec)

    scored = []
    for code, data in stock_map.items():
        n = len(data['recs'])
        consistency_bonus = min(n * 10, 30)
        combined = (data['total_contribution'] / max(n, 1)) * 0.5 + \
                   min(data['best_score'] + consistency_bonus, 100) * 0.5

        if session == 'MORNING' and data['best_score'] > 70:
            combined = min(combined + min(data['best_score'] - 70, 20), 100)


        scored.append({
            'stock_code': code,
            'stock_name': data['stock_name'],
            'combined_score': round(combined, 2),
            'best_score': data['best_score'],
            'strategy_count': n,
            'strategies': list(set(data['strategies'])),
            'sectors': [s for s in set(data['sectors']) if s],
            'recommendations': data['recs'],
        })

    scored.sort(key=lambda x: x['combined_score'], reverse=True)
    print("The all recommendations are: ", scored)
    top = scored[:top_n]
    # print("top: ", top)
    for i, s in enumerate(top):
        base = 0.20 - i * 0.03
        adj = (s['combined_score'] - 70) / 100 * 0.10
        position = max(0.08, min(0.25, base + adj))
        s['position_pct'] = round(position * 100, 1)
        s['position_value'] = round(position, 4)

    return top


# ── 报告生成 ────────────────────────────────────────────

def generate_buy_reason(stock: Dict, session: str) -> str:
    """生成买入理由"""
    reasons = []
    strategies = stock.get('strategies', [])
    score = stock.get('combined_score', 0)
    best = stock.get('best_score', 0)
    sectors = stock.get('sectors', [])

    if session == 'EVENING':
        if best >= 85:
            reasons.append(f"技术面强烈看涨，综合得分{score:.0f}")
        if len(strategies) >= 2:
            reasons.append(f"{strategies[0]}、{strategies[1]}双信号共振")
        elif strategies:
            reasons.append(f"{strategies[0]}信号确认")
        if sectors and sectors[0]:
            reasons.append(f"所属板块：{sectors[0]}")
        if score >= 80:
            reasons.append("尾盘低位吸纳，次日冲高概率大")
        elif score >= 70:
            reasons.append("趋势确认，尾盘买入博反弹")
    else:  # MORNING
        if best >= 85:
            reasons.append(f"突破动量强劲，早盘追涨，综合得分{score:.0f}")
        if len(strategies) >= 2:
            reasons.append(f"{strategies[0]}、{strategies[1]}信号共振")
        elif strategies:
            reasons.append(f"{strategies[0]}信号确认")
        if sectors and sectors[0]:
            reasons.append(f"所属板块：{sectors[0]}")
        if score >= 80:
            reasons.append("早盘确认动量，开盘即买入")
        elif score >= 70:
            reasons.append("趋势确认，逢低买入博新高")

    return '；'.join(reasons) if reasons else f"综合得分{score:.0f}，趋势向好"


def build_report(top: List[Dict], session: str, total_recs: int) -> str:
    label = '14:30 尾盘买' if session == 'EVENING' else '16:00 早盘买（次日）'
    date = datetime.now().strftime('%Y-%m-%d')

    lines = []
    lines.append('=' * 60)
    lines.append(f'融合策略推荐报告  [{label}]')
    lines.append(f'生成时间: {date} {datetime.now().strftime("%H:%M:%S")}')
    lines.append('=' * 60)
    lines.append(f'策略推荐总数: {total_recs}')
    lines.append(f'融合推荐数: {len(top)}')
    lines.append(f'总仓位建议: {sum(s["position_pct"] for s in top):.0f}%')
    lines.append('')

    if not top:
        lines.append('⚠️  未找到符合条件的推荐股票')
        lines.append('建议：当前市场无明确机会，控制仓位等待')
        return '\n'.join(lines)

    for i, s in enumerate(top, 1):
        tag = '🔥' if i == 1 else '✅' if i == 2 else '📌'
        lines.append(f'{tag} {i}. {s["stock_name"]}({s["stock_code"]})')
        lines.append(f'   综合得分: {s["combined_score"]:.1f}  |  最高单策略: {s["best_score"]:.1f}')
        lines.append(f'   确认策略: {", ".join(s["strategies"][:3])}')
        lines.append(f'   买入理由: {generate_buy_reason(s, session)}')
        lines.append(f'   买入仓位: {s["position_pct"]:.0f}%')
        if s.get('sectors'):
            lines.append(f'   所属板块: {", ".join(s["sectors"][:2])}')
        lines.append('')

    lines.append('=' * 60)
    lines.append('⚠️  仅供参考，不构成投资建议')
    return '\n'.join(lines)


def write_recommendations(top: List[Dict], session: str):
    """写入推荐文件：skill目录 + 统一入口"""
    date_str = datetime.now().strftime('%Y%m%d')
    session_str = 'EVENING_BUY' if session == 'EVENING' else 'MORNING_BUY'

    rec_list = []
    for s in top:
        rec_list.append({
            'code': s['stock_code'],
            'name': s['stock_name'],
            'source': s['strategies'][0] if s['strategies'] else 'fusion',
            'recommend_date': datetime.now().strftime('%Y-%m-%d'),
            'entry_price': 0.0,
            'target_reason': generate_buy_reason(s, session),
            'combined_score': s['combined_score'],
            'best_score': s['best_score'],
            'strategies': s['strategies'],
            'position_pct': s['position_pct'],
            'sectors': s.get('sectors', []),
            'session': session_str,
            'weight': s.get('position_value', 0),
        })

    data = {
        'date': date_str,
        'session': session_str,
        'generated_at': datetime.now().isoformat(),
        'recommendations': rec_list,
        'total_position': round(sum(s['position_pct'] for s in top), 1),
        'stock_count': len(top),
    }

    # 写入 ./recommendations/
    os.makedirs(SKILL_RECO_DIR, exist_ok=True)
    skill_file = os.path.join(SKILL_RECO_DIR, f'{date_str}_{session_str.lower()}_recommendation.json')
    with open(skill_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'\n📄 推荐已写入: {skill_file}')


# ── 主运行 ──────────────────────────────────────────────

def run_fusion(session: str, top_n: int = 5):
    print(session)
    strategies = EVENING_STRATEGIES if session == 'EVENING' else MORNING_STRATEGIES
    label = '尾盘买策略融合' if session == 'EVENING' else '早盘买策略融合'

    print(f'\n{"="*60}')
    print(f'融合策略运行器  [{label}]')
    print(f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'{"="*60}')

    # all_stocks = get_watchlist_stocks()
    # print(f'📋 自选股池共 {len(all_stocks)} 只股票')
    # print()

    all_recs = []
    success = 0

    for strategy in strategies:
        meta = STRATEGY_META.get(strategy, {})
        display = meta.get('display', strategy)
        print(f'▶️  运行 {display}...', end=' ', flush=True)

        try:
            recs = scan_strategy(strategy, top_n=top_n)
            print(strategy,": ", recs )
            if recs:
                all_recs.extend(recs)
                success += 1
                print(f'✅ {len(recs)} 条推荐')
            else:
                print('⚠️  无结果')
        except Exception as e:
            print(f'❌ {e}')

    print(f'\n{"="*60}')
    print(f'共运行 {len(strategies)} 个策略，成功 {success} 个')
    print(f'共收集 {len(all_recs)} 条推荐')

    top = fuse_recommendations(all_recs, top_n=top_n, session=session)
    report = build_report(top, session, len(all_recs))
    print('\n' + report)

    write_recommendations(top, session)
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
