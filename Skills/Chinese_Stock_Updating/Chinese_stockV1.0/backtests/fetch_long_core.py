#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 akshare(sina) 拉核心仓个股的**前复权**长历史（2026-10-17）

为什么这样做
------------
数据源对比（本轮实测）：
  · 腾讯 K 线接口：**硬上限 640 根**（约 2.6 年），无法覆盖 2022 熊市
  · 东财 fund_etf_hist_em：能拿长历史且带 hfq，但**当前网络不可达**
  · sina fund_etf_hist_sina：能拿 2007 年起长历史，但**未复权**，
      且遇到"基金份额折算"的 ETF 会完全失真
      （实测 sh515880 光通信：腾讯 +200% vs sina −50%）
  · **sina stock_zh_a_daily(adjust='hfq')：能拿 2018 年起、已复权、无折算问题** ✅

因此：
  核心仓（银行/电力/通信是**个股**）→ 用 sina 前复权个股数据，拿到长历史
  卫星仓（行业 ETF）→ 复用已有腾讯前复权数据（选无折算问题的标的）

输出：backtests/cache_long/<code>.csv（独立目录，不污染原 cache）
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

# 清代理变量（东财/sina 在代理下不稳定）
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
           "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)

import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "cache_long"
OUT.mkdir(exist_ok=True)

# 核心仓个股（sh/sz 前缀 → sina 代码）
CORE_STOCKS = {
    "sh601398": "工商银行", "sh601288": "农业银行", "sh601988": "中国银行",
    "sh600036": "招商银行", "sh601166": "兴业银行",
    "sh600900": "长江电力", "sh601985": "中国核电",
    "sh600941": "中国移动", "sh601088": "中国神华",
}
# 备用：宽基用指数（避免 ETF 未复权与折算问题）
CORE_INDEX = {"sh000300": "沪深300指数", "sh000905": "中证500指数"}

START, END = "20180101", "20261016"


def fetch_stock(code: str) -> Optional[pd.DataFrame]:
    import akshare as ak
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_daily(symbol=code, start_date=START,
                                     end_date=END, adjust="hfq")
            if df is None or len(df) < 200:
                return None
            d = pd.DataFrame({
                "date": pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"),
                "open": df["open"].astype(float),
                "high": df["high"].astype(float),
                "low": df["low"].astype(float),
                "close": df["close"].astype(float),
                "volume": df["volume"].astype(float),
            })
            return d
        except Exception as e:
            if attempt == 2:
                print(f"    ❌ {code}: {type(e).__name__}: {str(e)[:60]}")
                return None
            time.sleep(1.5)
    return None


def fetch_index(code: str) -> Optional[pd.DataFrame]:
    import akshare as ak
    for attempt in range(3):
        try:
            df = ak.stock_zh_index_daily(symbol=code)
            if df is None or len(df) < 200:
                return None
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df = df[(df["date"] >= "2018-01-01") & (df["date"] <= "2026-10-16")]
            return df[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
        except Exception as e:
            if attempt == 2:
                print(f"    ❌ {code}: {type(e).__name__}: {str(e)[:60]}")
                return None
            time.sleep(1.5)
    return None


def main() -> int:
    ok = fail = 0
    print(f"输出目录：{OUT}\n")
    print("=== 核心仓个股（sina 前复权）===")
    for code, name in CORE_STOCKS.items():
        p = OUT / f"{code}.csv"
        if p.exists():
            df = pd.read_csv(p)
            print(f"  {name:<8}{code:<10} 已存在 {len(df):>5} 行  {df['date'].iloc[0]} 起")
            ok += 1
            continue
        df = fetch_stock(code)
        if df is None:
            fail += 1
            continue
        df.to_csv(p, index=False)
        print(f"  {name:<8}{code:<10} ✅ {len(df):>5} 行  {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
        ok += 1
        time.sleep(0.4)

    print("\n=== 宽基指数（价格指数，无折算问题）===")
    for code, name in CORE_INDEX.items():
        p = OUT / f"{code}.csv"
        if p.exists():
            df = pd.read_csv(p)
            print(f"  {name:<10}{code:<10} 已存在 {len(df):>5} 行  {df['date'].iloc[0]} 起")
            ok += 1
            continue
        df = fetch_index(code)
        if df is None:
            fail += 1
            continue
        df.to_csv(p, index=False)
        print(f"  {name:<10}{code:<10} ✅ {len(df):>5} 行  {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
        ok += 1
        time.sleep(0.4)

    print(f"\n完成：成功 {ok}，失败 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
