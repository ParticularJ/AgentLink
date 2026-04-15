#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大盘环境判断模块
"""

import os
import sys
from datetime import datetime
from typing import Dict

try:
    import akshare as ak
except ImportError:
    ak = None


def get_market_status() -> Dict:
    """
    获取大盘（上证/深证/创业板）当前状态
    自动判断大盘环境并输出 market_status
    """
    result = {
        'sh_index': {},
        'sz_index': {},
        'cy_index': {},
        'systematic_drop': False,
        'timestamp': datetime.now().isoformat(),
    }

    if ak is None:
        result['market_status'] = 'neutral'
        return result

    # ── 获取三大指数实时数据 ─────────────────────────────
    try:
        df_sh = ak.stock_zh_index_spot_em(symbol='000001')
        result['sh_index'] = {
            'price': float(df_sh.iloc[0]['最新价']),
            'change_pct': float(df_sh.iloc[0]['涨跌幅']),
            'volume': float(df_sh.iloc[0]['成交量']),
        }
    except Exception:
        pass

    try:
        df_sz = ak.stock_zh_index_spot_em(symbol='399001')
        result['sz_index'] = {
            'price': float(df_sz.iloc[0]['最新价']),
            'change_pct': float(df_sz.iloc[0]['涨跌幅']),
            'volume': float(df_sz.iloc[0]['成交量']),
        }
    except Exception:
        pass

    try:
        df_cy = ak.stock_zh_index_spot_em(symbol='399006')
        result['cy_index'] = {
            'price': float(df_cy.iloc[0]['最新价']),
            'change_pct': float(df_cy.iloc[0]['涨跌幅']),
            'volume': float(df_cy.iloc[0]['成交量']),
        }
    except Exception:
        pass

    # ── 计算大盘状态 ───────────────────────────────────────
    changes = []
    for key in ['sh_index', 'sz_index', 'cy_index']:
        if result[key]:
            changes.append(result[key]['change_pct'])

    if not changes:
        result['market_status'] = 'neutral'
        return result

    avg_change = sum(changes) / len(changes)
    rising_count = sum(1 for c in changes if c > 0)
    strong_drop_count = sum(1 for c in changes if c < -1.5)

    # ── 自动判断 market_status ─────────────────────────────
    # weak: 三个指数都大跌（平均<-2%）
    if avg_change < -2.0 and strong_drop_count >= 2:
        result['market_status'] = 'weak'
    # bearish: 平均跌幅明显（>-2%）但不到weak，系统性下跌
    elif strong_drop_count >= 2 or avg_change < -1.0:
        result['market_status'] = 'bearish'
    # neutral: 震荡，涨跌互现或幅度不大
    elif -1.0 <= avg_change <= 1.0:
        result['market_status'] = 'neutral'
    # bullish: 震荡偏多，平均上涨但不是全面大涨
    elif avg_change > 0.5 and rising_count >= 2:
        result['market_status'] = 'bullish'
    # strong: 三个指数都明显上涨
    elif avg_change > 1.5 and rising_count >= 2:
        result['market_status'] = 'strong'
    else:
        result['market_status'] = 'neutral'

    result['avg_change'] = round(avg_change, 2)
    result['rising_count'] = rising_count

    # 系统性下跌标记
    result['systematic_drop'] = result['market_status'] in ('bearish', 'weak')
    result['strong_market'] = result['market_status'] in ('bullish', 'strong')

    return result


def auto_market_status() -> str:
    """
    自动判断大盘状态，返回字符串
    """
    status = get_market_status()
    return status.get('market_status', 'neutral')


def is_trading_time() -> bool:
    """判断当前是否在交易时间内"""
    now = datetime.now()
    current_time = now.time()

    morning_start = now.replace(hour=9, minute=30, second=0, microsecond=0).time()
    morning_end = now.replace(hour=11, minute=30, second=0, microsecond=0).time()
    afternoon_start = now.replace(hour=13, minute=0, second=0, microsecond=0).time()
    afternoon_end = now.replace(hour=15, minute=0, second=0, microsecond=0).time()

    is_weekday = now.weekday() < 5  # 0-4 = Monday to Friday

    in_morning = morning_start <= current_time <= morning_end
    in_afternoon = afternoon_start <= current_time <= afternoon_end

    return is_weekday and (in_morning or in_afternoon)


def is_market_close() -> bool:
    """判断是否已收盘（14:55后不进行新操作）"""
    now = datetime.now()
    current_time = now.time()
    cutoff = now.replace(hour=14, minute=55, second=0, microsecond=0).time()
    return current_time > cutoff
