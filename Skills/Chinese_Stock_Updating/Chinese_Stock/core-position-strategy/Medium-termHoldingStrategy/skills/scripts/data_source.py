#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据源适配层 - 替换 akshare
统一使用:
- 腾讯行情 API (qt.gtimg.cn) - 实时行情
- 新浪 K线 API - 历史日线数据
"""
import os
import sys
import json,random
import re
import requests, urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import numpy as np
import pandas as pd
from typing import Optional, Tuple, List, Dict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor


from functools import wraps
import time

def retry(max_attempts=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                result = func(*args, **kwargs)
                if result is not None:
                    return result
                if attempt < max_attempts - 1:
                    time.sleep(delay * (attempt + 1))
            return None
        return wrapper
    return decorator

# ── 代理清除 ────────────────────────────────────────────
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try:
            del os.environ[k]
        except:
            pass


# ── 腾讯实时行情（修复版） ────────────────────────────────
def _parse_tencent_line(line: str) -> Optional[dict]:
    """
    解析单行腾讯行情数据
    line: 'v_sh600105="1~永鼎股份~600105~49.94~..."'
    返回: {'code': '600105', 'name': '永鼎股份', ...} 或 None
    """
    try:
        eq = line.find('=')
        open_q = line.find('"', eq)
        close_q = line.rfind('"')
        if open_q < 0 or close_q < 0:
            return None
        inner = line[open_q + 1:close_q]
        fields = inner.split('~')
        if len(fields) < 40:
            return None
        raw_code = fields[2]  # 字段2是代码
        name = fields[1]
        price = float(fields[3]) if fields[3] not in ('', '-') else 0.0
        open_ = float(fields[4]) if fields[4] not in ('', '-') else 0.0
        # 字段33=今日最高, 34=今日最低
        high = float(fields[33]) if len(fields) > 33 and fields[33] not in ('', '-') else 0.0
        low = float(fields[34]) if len(fields) > 34 and fields[34] not in ('', '-') else 0.0
        vol = int(fields[36]) if len(fields) > 36 and fields[36] not in ('', '-') else 0
        amount = float(fields[37]) if len(fields) > 37 and fields[37] not in ('', '-') else 0.0
        chg = float(fields[31]) if len(fields) > 31 and fields[31] not in ('', '-') else 0.0
        chg_pct = float(fields[32]) if len(fields) > 32 and fields[32] not in ('', '-') else 0.0
        vol_ratio = float(fields[38]) if len(fields) > 38 and fields[38] not in ('', '-') else 1.0

        return {
            'code': raw_code,
            'name': name,
            'price': price,
            'open': open_,
            'high': high,
            'low': low,
            'volume': vol,
            'turnover': amount,
            'chg': chg,
            'chg_pct': chg_pct,
            'volume_ratio': vol_ratio,
        }
    except Exception:
        return None


def fetch_realtime_tencent(codes: List[str]) -> Dict[str, dict]:
    """
    腾讯行情 API - 批量获取实时行情
    codes: ['600105', '000001', ...] (6位纯数字代码)
    返回: {code: {...}}
    """
    if not codes:
        return {}

    # 转换为腾讯格式
    ts_codes = []
    for c in codes:
        c = c.strip().upper()
        if c.startswith('6'):
            ts_codes.append(f'sh{c}')
        elif c.startswith(('0', '3')):
            ts_codes.append(f'sz{c}')
        else:
            ts_codes.append(c)

    url = f'https://qt.gtimg.cn/q={",".join(ts_codes)}'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.qq.com'}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'GB18030'
    except Exception as e:
        print(f"[数据源] 腾讯行情请求失败: {e}")
        return {}

    results = {}
    for line in r.text.split('\n'):
        line = line.strip()
        if not line:
            continue
        parsed = _parse_tencent_line(line)
        if parsed:
            results[parsed['code']] = parsed

    return results

@retry(max_attempts=2, delay=0.5)
def fetch_single_tencent(code: str) -> Optional[dict]:
    """获取单只股票的腾讯实时行情"""
    results = fetch_realtime_tencent([code])
    return results.get(code.lstrip('sh').lstrip('sz'))


# ── 新浪历史K线 ────────────────────────────────────────
def fetch_kline_sina(symbol: str, days: int = 120) -> Optional[pd.DataFrame]:
    """
    新浪财经 K线 API
    symbol: 'sh600105' 或 'sz000001'
    返回: DataFrame with [day, open, close, high, low, volume]
    """
    url = 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
    params = {
        'symbol': symbol,
        'scale': '240',  # 日K
        'ma': 'no',
        'datalen': str(days),
    }
     # ✅ 防封核心：真实浏览器头 + 必带 Referer
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Referer': 'https://finance.sina.com/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    try:
        print("[数据源] 正在请求新浪K线数据...  ")
        r = requests.get(url, params=params, headers=headers, timeout=10)

        # ✅ 关键：检测是否被新浪拦截（返回HTML就是被封）
        if r.status_code != 200 or "<html>" in r.text[:100]:
            print("[警告] 新浪IP访问受限，自动切换腾讯备用数据源")
            return _fetch_kline_tencent_fallback(symbol, days)

        raw = json.loads(r.text)
    except Exception as e:
        print(f"[数据源] 新浪K线请求失败，尝试腾讯备用源: {e}")
        return _fetch_kline_tencent_fallback(symbol, days)

    if not raw:
        return _fetch_kline_tencent_fallback(symbol, days)

    df = pd.DataFrame(raw)
    df['day'] = pd.to_datetime(df['day'])
    # 新浪API返回字段：day, open, close, high, low, volume
    # 但部分接口字段名为 name="open" 等，需要做列名规范化
    col_map = {c: c.lower() for c in df.columns if c in ['open', 'close', 'high', 'low', 'volume', 'ma5', 'ma10', 'ma20', 'ma60']}
    df.rename(columns=col_map, inplace=True)
    for col in ['open', 'close', 'high', 'low']:
        if col in df.columns:
            df[col] = df[col].astype(float)
    if 'volume' in df.columns:
        df['volume'] = df['volume'].astype(float)

    # 计算均线
    if 'close' in df.columns:
        close = df['close'].values
        for n in [5, 10, 20, 60]:
            if f'ma{n}' not in df.columns:
                df[f'ma{n}'] = pd.Series(close).rolling(n).mean().values

    return df


def _fetch_kline_tencent_fallback(symbol: str, days: int = 120) -> Optional[pd.DataFrame]:
    """
    腾讯财经 K线备用源（新浪失败时调用）
    symbol: 'sh603728' 或 'sz000001'
    返回: DataFrame with [day, open, close, high, low, volume, ma5, ma10, ma20, ma60]
    """
    exchange = symbol[:2]
    code = symbol[2:]
    today_str = datetime.now().strftime('%Y-%m-%d')
    start_str = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    url = (f'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
           f'?_var=kline_dayqfq&param={exchange}{code},day,{start_str},{today_str},{days},qfq')
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.qq.com'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        json_str = r.text[r.text.index('=') + 1:]
        data = json.loads(json_str)
        klines = data['data'][symbol.lower()].get('qfqday', [])
        if not klines:
            print(f"[数据源] 腾讯K线也无数据: {symbol}")
            return None
        df = pd.DataFrame(klines, columns=['day', 'open', 'close', 'high', 'low',
                                            'volume', 'extra', 'chg', 'amount', 'unchanged'])
        df['day'] = pd.to_datetime(df['day'])
        for col in ['open', 'close', 'high', 'low']:
            df[col] = df[col].astype(float)
        df['volume'] = df['volume'].astype(float)
        close = df['close'].values
        for n in [5, 10, 20, 60]:
            df[f'ma{n}'] = pd.Series(close).rolling(n).mean().values
        return df
    except Exception as e:
        print(f"[数据源] 腾讯K线备用源也失败: {e}")
        return None


# ── 上证指数实时行情 ────────────────────────────────────
def fetch_index_tencent() -> Dict[str, dict]:
    """获取上证/深证/创业板实时指数"""
    url = 'https://qt.gtimg.cn/q=sh000001,sz399001,sz399006'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.qq.com'}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'GB18030'
    except Exception as e:
        print(f"[数据源] 腾讯指数请求失败: {e}")
        return {}

    results = {}
    for line in r.text.split('\n'):
        line = line.strip()
        if not line:
            continue
        # sh000001 → 000001, sz399001 → 399001, sz399006 → 399006
        m = re.search(r'v_(sh\d+|sz\d+)="(.+)"', line)
        if not m:
            continue
        raw_code = m.group(1)
        fields = m.group(2).split('~')
        if len(fields) < 35:
            continue
        std_code = raw_code[2:]
        results[std_code] = {
            'name': fields[1],
            'price': float(fields[3]) if fields[3] not in ('', '-') else 0,
            'chg_pct': float(fields[32]) if fields[32] not in ('', '-') else 0,
        }

    return results


import requests
import json
import time
from typing import Dict

import requests
import json
import time
from typing import Dict

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_market_stats_tencent() -> Dict[str, dict]:
    """
    使用腾讯财经接口获取涨跌家数
    """
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    
    # 获取三大指数数据
    indices = {
        "sh000001": "上证指数",
        "sz399001": "深证成指", 
        "sz399006": "创业板指"
    }
    
    results = {}
    
    for code, name in indices.items():
        params = {
            "param": f"{code},day,,,1",
            "_var": "kline_day"
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://gu.qq.com/",
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=5)
            if response.status_code == 200:
                # 处理JSONP响应
                text = response.text
                if "kline_day=" in text:
                    json_str = text.split("kline_day=")[1]
                    data = json.loads(json_str)
                    
                    stock_data = data.get("data", {}).get(code, {})
                    fields = stock_data.get("qt", [])
                    
                    if fields and len(fields) > 3:
                        results[code] = {
                            "name": name,
                            "price": float(fields[3]) if fields[3] else 0,
                            "change_percent": float(fields[32]) if len(fields) > 32 and fields[32] else 0,
                            "volume": float(fields[5]) if len(fields) > 5 and fields[5] else 0,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        # 腾讯接口不直接提供涨跌家数，需要从其他接口获取
                        results[code]["advance"] = 0
                        results[code]["decline"] = 0
                        results[code]["unchanged"] = 0
                        results[code]["limit_up"] = 0
                        results[code]["limit_down"] = 0
                        
        except Exception as e:
            print(f"[腾讯财经] 获取{name}数据失败: {e}")
            continue
        
        time.sleep(0.3)
    
    return results

# 全局复用Session，不反复创建连接（核心解决断开问题）
GLOBAL_SESSION = requests.Session()

# 全局配置重试 + 连接池
retry_strategy = Retry(
    total=5,           # 重试5次
    backoff_factor=2,  # 等待 2s → 4s → 8s 指数退避，防封IP
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=20)
GLOBAL_SESSION.mount("https://", adapter)
GLOBAL_SESSION.mount("http://", adapter)

def fetch_kline_eastmoney(symbol: str, days: int = 120) -> Optional[pd.DataFrame]:
    """
    东方财富K线接口（终极防断开、防反爬、工业级稳定）
    """
    # 超级防反爬延迟（必加）
    time.sleep(random.uniform(1.5, 2.8))

    # 代码格式化
    symbol = symbol.strip().upper().replace('SH', '').replace('SZ', '')

    # 判断市场
    if symbol.startswith('6'):
        secid = f'1.{symbol}'
    elif symbol.startswith(('0', '3')):
        secid = f'0.{symbol}'
    else:
        print(f"❌ 不支持代码: {symbol}")
        return None

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "lmt": str(days),
        "beg": "0",
        "end": "20500000",
    }

    # 最逼真的浏览器头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
        "Accept": "application/json, text/plain, */*",
        "Connection": "keep-alive",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    try:
        # 使用全局单例Session，不会被服务器断开
        response = GLOBAL_SESSION.get(
            url,
            params=params,
            headers=headers,
            timeout=20,
            stream=False
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("data") or not data["data"].get("klines"):
            print(f"ℹ️ 无数据: {symbol}")
            return None

        klines = data["data"]["klines"]
        records = []
        for line in klines:
            parts = line.split(",")
            if len(parts) < 6:
                continue
            records.append({
                "day": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
            })

        df = pd.DataFrame(records)
        df["day"] = pd.to_datetime(df["day"])

        # 均线
        for n in [5, 10, 20, 60]:
            df[f"ma{n}"] = df["close"].rolling(n).mean()

        print(f"✅ 成功 {symbol} | {len(df)} 条")
        return df

    except Exception as e:
        print(f"⚠️ 重试后仍失败 {symbol}: {str(e)}")
        return None

# 主函数 - 优先使用东方财富，失败则降级
def get_market_stats() -> Dict[str, dict]:
    """
    获取市场统计数据，带降级方案
    """
    # 尝试东方财富接口
    result = fetch_market_stats_tencent()
    
    if not result:
        print("[数据源] 所有接口失败，返回模拟数据")
        # 返回模拟数据作为最后的降级方案
        result = {
            "1.000001": {"name": "上证指数", "price": 0, "change_percent": 0, 
                        "advance": 0, "decline": 0, "unchanged": 0, 
                        "limit_up": 0, "limit_down": 0},
            "0.399001": {"name": "深证成指", "price": 0, "change_percent": 0,
                        "advance": 0, "decline": 0, "unchanged": 0,
                        "limit_up": 0, "limit_down": 0},
            "0.399006": {"name": "创业板指", "price": 0, "change_percent": 0,
                        "advance": 0, "decline": 0, "unchanged": 0,
                        "limit_up": 0, "limit_down": 0}
        }
    
    return result


# def get_market_stats() -> Optional[Dict[str, dict]]:
#     """
#     获取市场涨跌家数统计（东方财富API）
#     返回: {
#         'sh': {name, price, advance, decline, unchanged, limit_up, limit_down},
#         'sz': {...},
#         'cy': {...},
#     }
#     """
#     data = fetch_market_stats_em()
#     if not data:
#         print("[数据源] 获取市场涨跌家数失败")
#         return None
#     return {
#         'sh': data.get('1.000001', {}),
#         'sz': data.get('0.399001', {}),
#         'cy': data.get('0.399006', {}),
#     }


# ── 主数据获取函数（兼容原有接口） ──────────────────────
def get_stock_realtime(code: str) -> Tuple[Optional[pd.DataFrame], Optional[dict]]:
    """
    获取个股数据，兼容 stock_analyzer.py 的调用方式
    返回: (df_history, current_data_dict)
    current_data_dict: {code, name, price, open, high, low, volume, turnover, chg_pct, volume_ratio}
    """
    # 格式化代码
    if code.startswith('6'):
        sina_sym = f'sh{code}'
    else:
        sina_sym = f'sz{code}'

    # 并行获取实时 + 历史
    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(fetch_single_tencent, code)
        f2 = ex.submit(fetch_kline_sina, code, 120)
        tencent_data = f1.result()
        df_history = f2.result()

    # 东方财富失败时才尝试其他源
    if df_history is None:
        df_history = fetch_kline_sina(sina_sym, 120)
    if df_history is None:
        df_history = _fetch_kline_tencent_fallback(sina_sym, 120)

    current = {
        'code': code,
        'name': tencent_data['name'],
        'price': tencent_data['price'],
        'open': tencent_data['open'],
        'high': tencent_data['high'],
        'low': tencent_data['low'],
        'volume': tencent_data['volume'],
        'turnover': tencent_data['turnover'],
        'chg_pct': tencent_data['chg_pct'],
        'volume_ratio': tencent_data['volume_ratio'],
    }

    return df_history, current


def get_index_realtime() -> Optional[dict]:
    """获取三大指数实时数据"""
    data = fetch_index_tencent()
    if not data:
        return None
    return {
        'sh': data.get('000001', {}),
        'sz': data.get('399001', {}),
        'cy': data.get('399006', {}),
    }


# ── 测试入口 ────────────────────────────────────────────
if __name__ == '__main__':
    print("=== 数据源测试 ===")

    code = '600105'
    df, cur = get_stock_realtime(code)
    if cur:
        print(f"\n实时行情: {cur['name']}({code})")
        print(f"  现价: {cur['price']} | 今开: {cur['open']} | 最高: {cur['high']} | 最低: {cur['low']}")
        print(f"  涨跌: {cur['chg_pct']:+.2f}% | 量比: {cur['volume_ratio']}")
    if df is not None and len(df) > 0:
        print(f"\n历史K线: {len(df)} 条, 最新: {df['day'].iloc[-1].date()}")
        print(f"  MA5: {df['ma5'].iloc[-1]:.2f} | MA10: {df['ma10'].iloc[-1]:.2f} | MA20: {df['ma20'].iloc[-1]:.2f}")

    idx = get_index_realtime()
    if idx:
        print(f"\n大盘指数:")
        for k, v in idx.items():
            if v:
                print(f"  {v['name']}: {v['price']} ({v['chg_pct']:+.2f}%)")

    # 测试涨跌家数
    stats = get_market_stats()
    if stats:
        print(f"\n涨跌家数统计:")
        for k, v in stats.items():
            if v:
                total = v.get('advance', 0) + v.get('decline', 0) + v.get('unchanged', 0)
                print(f"  {v['name']}: 涨{v.get('advance',0)} 跌{v.get('decline',0)} 平{v.get('unchanged',0)} (涨停{v.get('limit_up',0)} 跌停{v.get('limit_down',0)})")
