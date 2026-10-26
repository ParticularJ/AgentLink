#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心仓每日监控（2026-10-17）

每天跑一次，输出：
  1. 各 ETF 最新价、当前市值占比 vs 目标权重
  2. 是否需要再平衡（偏离 >3 个百分点）
  3. 当前估值分位（上证红利/沪深300 PE）

用法：
  python backtests/core_monitor.py --holdings sh512800=460000,sz159611=150000,sh515220=85000,sh510300=130000,sh511010=175000

  或把持仓写进 core_holdings.json 后直接运行：
  python backtests/core_monitor.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

for _k in ("NO_PROXY", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
           "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)

import pandas as pd

HERE = Path(__file__).resolve().parent
HOLDINGS_FILE = HERE / "core_holdings.json"

TARGET_A = {
    "sh512800": ("银行ETF华宝", 0.35),
    "sz159611": ("电力ETF广发", 0.14),
    "sh515220": ("煤炭ETF国泰", 0.07),
    "sh510300": ("沪深300ETF华泰柏瑞", 0.14),
    "sh511010": ("国债ETF国泰", 0.30),
}
TARGET_B = {
    "sh512800": ("银行ETF华宝", 0.50),
    "sz159611": ("电力ETF广发", 0.20),
    "sh515220": ("煤炭ETF国泰", 0.10),
    "sh510300": ("沪深300ETF华泰柏瑞", 0.20),
}
THRESHOLD = 0.03


def fetch_prices(codes: list) -> dict:
    """抓最新收盘价（sina，逐只）。"""
    import akshare as ak
    prices = {}
    for c in codes:
        try:
            df = ak.fund_etf_hist_sina(symbol=c)
            df["date"] = pd.to_datetime(df["date"])
            df = df.dropna(subset=["close"])
            prices[c] = (float(df["close"].iloc[-1]), df["date"].iloc[-1].strftime("%Y-%m-%d"))
        except Exception as e:
            prices[c] = (None, f"抓取失败:{type(e).__name__}")
    return prices


def pe_percentile() -> dict:
    """上证红利/沪深300 当前 PE 及 5 年分位。"""
    out = {}
    for name in ("上证红利", "沪深300"):
        p = HERE / "cache_long" / f"pe_{name}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["日期"] = df["日期"].astype(str).str[:10]
        pe = df["滚动市盈率"].astype(float)
        cur = pe.iloc[-1]
        win = pe.iloc[-60:]  # 5 年（月频）
        pct = (win <= cur).mean() * 100
        out[name] = (cur, pct)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="核心仓每日监控")
    ap.add_argument("--holdings", type=str, default="", help="code=金额,...")
    ap.add_argument("--version", choices=["A", "B"], default="A")
    args = ap.parse_args()

    target = TARGET_A if args.version == "A" else TARGET_B

    # 读取持仓
    holdings = {}
    if args.holdings:
        for kv in args.holdings.split(","):
            if "=" in kv:
                k, v = kv.split("=")
                holdings[k.strip()] = float(v)
    elif HOLDINGS_FILE.exists():
        holdings = json.loads(HOLDINGS_FILE.read_text(encoding="utf-8"))
    else:
        # 生成模板
        template = {c: 0 for c in target}
        HOLDINGS_FILE.write_text(json.dumps(template, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        print(f"已生成持仓模板 {HOLDINGS_FILE}，请填入各 ETF 当前市值后重跑。")
        return 0

    # 抓价格
    codes = list(target.keys())
    prices = fetch_prices(codes)

    print("=" * 88)
    print("核心仓每日监控")
    print("=" * 88)
    # 先算当前市值（用输入持仓）
    total = sum(holdings.values())
    print(f"持仓总市值（按你输入）：{total:,.0f} 元\n")

    print(f"  {'ETF':<12}{'名称':<16}{'最新价':>10}{'目标权重':>8}{'当前占比':>8}{'偏离':>8}  状态")
    print("  " + "-" * 84)
    need_rebalance = False
    for code, (name, w) in target.items():
        cur = holdings.get(code, 0.0)
        cur_pct = cur / total if total else 0
        dev = cur_pct - w
        px, pdate = prices.get(code, (None, ""))
        px_s = f"{px:.3f}" if px else "—"
        if dev > THRESHOLD:
            status = f"⚠️ 超配，建议卖出 {(cur - total*w):,.0f} 元"
            need_rebalance = True
        elif dev < -THRESHOLD:
            status = f"⚠️ 低配，建议买入 {(total*w - cur):,.0f} 元"
            need_rebalance = True
        else:
            status = "✅ 正常"
        print(f"  {code:<12}{name:<16}{px_s:>10}{w*100:>7.1f}%{cur_pct*100:>7.1f}%"
              f"{dev*100:>+7.1f}%  {status}")

    print()
    if need_rebalance:
        print("  📌 存在偏离 >3% 的持仓，建议按上面提示再平衡。")
    else:
        print("  ✅ 所有持仓偏离 <3%，无需再平衡。")

    # 估值分位
    print()
    print("  估值分位（估值分位 = 历史PE≤当前PE的比例，越高越贵）：")
    for name, (cur, pct) in pe_percentile().items():
        if pct < 20:
            flag = " ← 低估（分位<20%），持有/加仓"
        elif pct > 80:
            flag = " ← 高估（分位>80%），可考虑减仓"
        else:
            flag = "（中性）"
        print(f"    {name}: PE {cur:.2f}，5年分位 {pct:.0f}%{flag}")

    print()
    print("  提示：本监控只做「偏离>3% 再平衡」，不做任何择时/波段。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
