#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持仓 vs 推荐 调仓分析
对持仓股和新推荐股进行四维度打分，对比输出调仓建议
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional

for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    os.environ.pop(k, None)

import pandas as pd
import numpy as np
import akshare as ak

from indicators import calculate_rsi, calculate_macd, check_volume_anomaly


# ── 路径设置（相对路径，基于脚本所在目录）────────────────────
# rebalance.py 位于 Chinese_Stock/sell-monitor/scripts/
# dirname ×2 → Chinese_Stock/
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
_BASE_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))  # Chinese_Stock/
DEFAULT_RECO_DIR = os.path.join(_BASE_DIR, 'recommendations')

# ── 辅助函数 ────────────────────────────────────────────

def _get_latest_reco_file() -> str:
    """获取最新的推荐文件"""
    import glob
    pattern = os.path.join(DEFAULT_RECO_DIR, '*_recommendation.json')
    files = glob.glob(pattern)
    if not files:
        return ''
    return max(files, key=os.path.getmtime)


def _get_latest_holdings_file() -> str:
    """获取最新的持仓文件（YYYYMMDD_holdings.json）"""
    import glob
    pattern = os.path.join(_BASE_DIR, 'my_holdings', '*_holdings.json')
    files = glob.glob(pattern)
    if files:
        return max(files, key=os.path.getmtime)
    return os.path.join(_BASE_DIR, 'my_holdings', 'holdings.json')


# ── 行情获取 ────────────────────────────────────────────

def get_quote(symbol: str) -> Optional[Dict]:
    """获取A股实时行情（新浪接口）"""
    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df['代码'] == symbol]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            'code': symbol,
            'name': r['名称'],
            'price': float(r['最新价']),
            'change_pct': float(r['涨跌幅']),
            'volume': float(r['成交量']),
            'amount': float(r['成交额']),
            'turnover': float(r['换手率']),   # 换手率%
            'high': float(r['最高']),
            'low': float(r['最低']),
            'open': float(r['今开']),
            'pre_close': float(r['昨收']),
        }
    except Exception as e:
        return None


def get_daily(symbol: str, days: int = 60) -> Optional[pd.DataFrame]:
    """获取日线数据"""
    try:
        end = datetime.now()
        start = (end - pd.Timedelta(days=days)).strftime('%Y%m%d')
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period='daily',
            start_date=start,
            end_date=end.strftime('%Y%m%d'),
            adjust='qfq'
        )
        df = df.sort_values('日期')
        return df
    except Exception:
        return None


def get_money_flow(symbol: str) -> Optional[Dict]:
    """获取主力资金流向（东方财富）"""
    try:
        df = ak.stock_individual_fund_flow(stock=symbol, market='sh')
        if df is None or df.empty:
            return None
        latest = df.iloc[-1]
        # 取最近的主力净流入字段（字段名可能有版本差异，尝试兼容）
        cols = [c for c in df.columns if '主力' in c or '超大单' in c or '大单' in c]
        if not cols:
            return None
        col = cols[0]
        val = float(latest[col]) if pd.notna(latest[col]) else 0.0
        return {'main_net': val}
    except Exception:
        return None


def get_north_money() -> Optional[Dict]:
    """获取北向资金（当天实时）"""
    try:
        df = ak.stock_em_hsgt_north_net_flow_in(indicator='北向资金')
        if df is None or df.empty:
            return None
        latest = df.iloc[-1]
        return {
            'north_net': float(latest['北向资金'] if '北向资金' in latest else latest.get('净流入', 0)),
        }
    except Exception:
        return None


# ── 均线多头/空头判断 ──────────────────────────────────

def ma_structure(df: pd.DataFrame) -> str:
    """判断均线多头/空头/纠缠"""
    if df is None or len(df) < 20:
        return 'unknown'
    ma5 = df['收盘'].iloc[-1]
    ma10 = df['收盘'].rolling(10).mean().iloc[-1]
    ma20 = df['收盘'].rolling(20).mean().iloc[-1]
    ma60 = df['收盘'].rolling(60).mean().iloc[-1] if len(df) >= 60 else ma20
    if ma5 > ma10 > ma20 > ma60:
        return 'bullish'
    elif ma5 < ma10 < ma20 < ma60:
        return 'bearish'
    else:
        return 'neutral'


# ── 趋势强度评分（技术面） ─────────────────────────────

def score_technical(symbol: str) -> Dict:
    """四维度打分：技术面（30分）+ 市场热度（25分）+ 情绪（20分）+ 资金（25分）"""
    quote = get_quote(symbol)
    daily = get_daily(symbol)
    money = get_money_flow(symbol)

    total = 0
    detail = {}

    # ① 技术面（30分）
    tech_score = 0
    if daily is not None and len(daily) >= 14:
        close = daily['收盘'].values
        rsi = calculate_rsi(close, 14)
        macd_result = calculate_macd(close)
        ma_state = ma_structure(daily)

        rsi_val = rsi if rsi else 50
        macd_dif = macd_result.get('dif', 0) if macd_result else 0
        macd_dea = macd_result.get('dea', 0) if macd_result else 0

        # RSI 0-100 → 0-15分
        if rsi_val < 30:
            tech_score += 12  # 超卖，低位，看涨
        elif rsi_val < 50:
            tech_score += 10
        elif rsi_val < 65:
            tech_score += 8
        elif rsi_val < 80:
            tech_score += 5
        else:
            tech_score += 1  # 高位风险

        # MACD 0-8分
        if macd_dif > macd_dea and macd_dif > 0:
            tech_score += 6  # 上升柱
        elif macd_dif > macd_dea:
            tech_score += 3
        else:
            tech_score += 0

        # 均线 0-7分
        if ma_state == 'bullish':
            tech_score += 7
        elif ma_state == 'neutral':
            tech_score += 3
        else:
            tech_score += 0

        detail['rsi'] = round(rsi_val, 1)
        detail['macd_dif'] = round(macd_dif, 3)
        detail['ma_state'] = ma_state
    else:
        detail['rsi'] = None
        detail['macd_dif'] = None
        detail['ma_state'] = 'unknown'

    detail['tech_score'] = tech_score
    total += tech_score

    # ② 市场热度（25分）
    heat_score = 0
    if quote:
        turnover = quote.get('turnover', 0) or 0
        change = abs(quote.get('change_pct', 0) or 0)
        volume_ratio = 1.0  # 默认
        if daily is not None and len(daily) >= 5:
            vol_mean = daily['成交量'].iloc[-5:].mean()
            if vol_mean > 0:
                volume_ratio = quote['volume'] / vol_mean

        # 换手率打分
        if turnover < 1:
            heat_score += 4
        elif turnover < 3:
            heat_score += 8
        elif turnover < 8:
            heat_score += 13
        else:
            heat_score += 18  # 高换手，热度高

        # 涨幅打分（今日强度）
        if change < 0.5:
            heat_score += 2
        elif change < 2:
            heat_score += 5
        elif change < 5:
            heat_score += 7
        else:
            heat_score += 7  # 涨停或接近涨停

        detail['turnover'] = turnover
        detail['change_pct'] = quote.get('change_pct', 0)
    else:
        detail['turnover'] = None
        detail['change_pct'] = None

    detail['heat_score'] = heat_score
    total += heat_score

    # ③ 市场情绪（20分）— 用涨跌幅近似
    sentiment_score = 0
    if quote:
        change = quote.get('change_pct', 0) or 0
        if change > 5:
            sentiment_score = 18
        elif change > 2:
            sentiment_score = 14
        elif change > 0:
            sentiment_score = 10
        elif change > -2:
            sentiment_score = 7
        else:
            sentiment_score = 3
    detail['sentiment_score'] = sentiment_score
    total += sentiment_score

    # ④ 资金流向（25分）
    fund_score = 0
    if money:
        main_net = money.get('main_net', 0) or 0
        if main_net > 1e8:
            fund_score = 22
        elif main_net > 5000 * 1e4:
            fund_score = 16
        elif main_net > 0:
            fund_score = 10
        elif main_net > -5000 * 1e4:
            fund_score = 5
        else:
            fund_score = 0
        detail['main_net'] = main_net
    else:
        detail['main_net'] = None

    # 北向资金加分
    try:
        north = get_north_money()
        if north and north.get('north_net', 0) > 0:
            fund_score = min(25, fund_score + 3)
    except Exception:
        pass

    detail['fund_score'] = fund_score
    total += fund_score

    detail['total'] = total
    return detail


# ── 综合对比报告 ────────────────────────────────────────

def analyze_rebalance() -> str:
    """对比持仓股 vs 推荐股，输出调仓建议"""
    holdings = []
    recs = []

    try:
        holdings_file = _get_latest_holdings_file()
        with open(holdings_file, 'r', encoding='utf-8') as f:
            holdings = json.load(f)
    except Exception:
        return '❌ 持仓列表读取失败，请检查 ../my_holdings/ 目录'

    try:
        reco_file = _get_latest_reco_file()
        if not reco_file or not os.path.exists(reco_file):
            return '❌ 推荐列表读取失败，recommendations/ 目录为空或不存在'
        with open(reco_file, 'r', encoding='utf-8') as f:
            reco_data = json.load(f)
            recs = reco_data.get('recommendations', [])
    except Exception:
        return f'❌ 推荐列表读取失败，请检查 recommendations/ 目录'

    if not holdings:
        return '📋 持仓列表为空，无需调仓'
    if not recs:
        return '📋 推荐列表为空，请先添加推荐股票'

    lines = []
    lines.append('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    lines.append('🔄 调仓分析报告')
    lines.append(f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    lines.append('')

    # 持仓股打分
    hold_scores = {}
    for h in holdings:
        code = h['code']
        s = score_technical(code)
        s['name'] = h.get('name', code)
        s['buy_reason'] = h.get('buy_reason', 'unknown')
        hold_scores[code] = s
        print(f"[DEBUG] 持仓 {code} 打分: {s['total']}")

    # 推荐股打分
    reco_scores = {}
    for r in recs:
        code = r['code']
        s = score_technical(code)
        s['name'] = r.get('name', code)
        s['source'] = r.get('source', 'unknown')
        reco_scores[code] = s
        print(f"[DEBUG] 推荐 {code} 打分: {s['total']}")

    lines.append('📊 持仓股得分：')
    for code, s in sorted(hold_scores.items(), key=lambda x: x[1]['total'], reverse=True):
        lines.append(f'   {s["name"]}({code})  得分: {s["total"]}/100  '
                     f'[RSI:{s.get("rsi","?")} | 均线:{s.get("ma_state","?")}]')
    lines.append('')

    lines.append('📊 推荐股得分：')
    for code, s in sorted(reco_scores.items(), key=lambda x: x[1]['total'], reverse=True):
        lines.append(f'   {s["name"]}({code})  得分: {s["total"]}/100  '
                     f'[换手:{s.get("turnover","?")}% | 主力净流入:{_fmt_money(s.get("main_net"))}]')
    lines.append('')

    # 找最优新股 vs 最差持仓股
    best_reco = max(reco_scores.items(), key=lambda x: x[1]['total'])
    worst_hold = min(hold_scores.items(), key=lambda x: x[1]['total'])

    best_code, best_s = best_reco
    worst_code, worst_s = worst_hold

    gap = best_s['total'] - worst_s['total']

    lines.append('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    if gap >= 10:
        lines.append(f'✅ 调仓信号：推荐 {best_s["name"]}({best_code}) 优于 持仓 {worst_s["name"]}({worst_code})')
        lines.append(f'   得分差：{best_s["total"]} - {worst_s["total"]} = {gap} 分')
        lines.append('')
        lines.append(f'▶️ 操作建议：卖出 {worst_s["name"]}({worst_code}) → 买入 {best_s["name"]}({best_code})')
        lines.append(f'   卖出理由：得分偏低({worst_s["total"]})，{worst_s.get("ma_state","均线")}，RSI={worst_s.get("rsi","?")}')
        lines.append(f'   买入理由：得分较高({best_s["total"]})，{best_s.get("ma_state","均线")}，换手率{best_s.get("turnover","?")}%，主力{_fmt_money(best_s.get("main_net"))}')
        if gap >= 20:
            lines.append('   ⚡ 强调仓信号：得分差超过20分，强烈建议执行')
    elif gap >= 5:
        lines.append(f'⚠️ 观察信号：推荐 {best_s["name"]} 微优 {worst_s["name"]}，暂不强制调仓')
        lines.append(f'   得分差：{gap} 分，可持续观察')
    else:
        lines.append('✅ 暂无调仓必要：持仓股与推荐股得分接近')
    lines.append('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')

    return '\n'.join(lines)


def _fmt_money(val) -> str:
    if val is None:
        return '?'
    if abs(val) >= 1e8:
        return f'{val/1e8:.2f}亿'
    elif abs(val) >= 1e4:
        return f'{val/1e4:.0f}万'
    else:
        return f'{val:.0f}'


# ── 命令行入口 ────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='持仓 vs 推荐 调仓分析')
    parser.add_argument('--holdings', default=None, help='持仓文件路径')
    parser.add_argument('--recommendations', default=None, help='推荐股票文件路径')
    args = parser.parse_args()

    # 允许通过命令行覆盖文件路径
    holdings_file = args.holdings or _get_latest_holdings_file()
    reco_file = args.recommendations or _get_latest_reco_file()

    report = analyze_rebalance()
    print(report)
