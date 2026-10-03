#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票池买入持有基线：给定池子与区间，计算等权买入持有的表现。

用途：把「策略选出少数标的」的结果与「整池躺平」做对照，
否则无法判断策略的选股是否真的创造了价值。

用法：
    python backtests/pool_baseline.py --pool my_stock_pool/watchlist_2026-10.yaml \
        --start 2025-09-30 --end 2026-09-30
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "common"))

from backtest_september import QuoteCache


def load_pool(path: Path):
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    stocks, etfs = [], []
    wl = raw.get("watchlist") or {}
    for group, sections in wl.items():
        if not isinstance(sections, dict):
            continue
        for category in ("core", "focus"):
            for item in sections.get(category) or []:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    stocks.append((group, str(item[0]), str(item[1])))
    for group, items in (raw.get("etf_pool") or {}).items():
        for item in items or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                etfs.append((f"etf_{group}", str(item[0]), str(item[1])))
    return stocks, etfs


def buy_hold(cache: QuoteCache, code: str, start: str, end: str):
    """区间买入持有收益：首个可用交易日的收盘价 → 最后一个交易日的收盘价。"""
    df = cache.raw.get(cache._symbol(code))
    if df is None:
        return None
    seg = df[(df["date"] >= start) & (df["date"] <= end)]
    if len(seg) < 2:
        return None
    first, last = float(seg.iloc[0]["close"]), float(seg.iloc[-1]["close"])
    if first <= 0:
        return None
    return {
        "code": code,
        "first_date": str(seg.iloc[0]["date"]),
        "last_date": str(seg.iloc[-1]["date"]),
        "ret": last / first - 1,
    }


def report(cache: QuoteCache, label: str, rows, start: str, end: str, out_lines: list):
    results = []
    for group, name, code in rows:
        r = buy_hold(cache, code, start, end)
        if r is None:
            continue
        r.update({"group": group, "name": name})
        results.append(r)
    out_lines.append("")
    out_lines.append(f"── {label}   共 {len(results)}/{len(rows)} 个标的取得数据 " + "─" * 20)
    if not results:
        out_lines.append("   （无可用数据）")
        return results
    rets = [r["ret"] for r in results]
    win = sum(1 for x in rets if x > 0) / len(rets) * 100
    out_lines.append(f"   等权买入持有： 均值 {statistics.mean(rets) * 100:+.2f}%   "
                     f"中位 {statistics.median(rets) * 100:+.2f}%   "
                     f"上涨占比 {win:.1f}%   "
                     f"最好 {max(rets) * 100:+.2f}%   最差 {min(rets) * 100:+.2f}%")
    by_group = {}
    for r in results:
        by_group.setdefault(r["group"], []).append(r["ret"])
    out_lines.append("   分组表现（等权，按均值排序）：")
    for g, vals in sorted(by_group.items(), key=lambda kv: -statistics.mean(kv[1])):
        out_lines.append(f"      {g:<26}{len(vals):>3} 只   {statistics.mean(vals) * 100:>+8.2f}%   "
                         f"上涨 {sum(1 for v in vals if v > 0) / len(vals) * 100:>5.1f}%")
    return results


def main():
    ap = argparse.ArgumentParser(description="股票池买入持有基线")
    ap.add_argument("--pool", required=True)
    ap.add_argument("--start", default="2025-09-30")
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    cache = QuoteCache()
    pool_path = Path(args.pool)
    if not pool_path.is_absolute():
        pool_path = REPO / pool_path
    stocks, etfs = load_pool(pool_path)

    lines = [f"股票池: {pool_path.name}   区间: {args.start} → {args.end}",
             f"个股 {len(stocks)} 只，ETF {len(etfs)} 只"]
    report(cache, "个股池（第二层卫星 + 第一层底仓）", stocks, args.start, args.end, lines)
    report(cache, "ETF 池（窄基/宽基/低波）", etfs, args.start, args.end, lines)
    bench = buy_hold(cache, "sh000300", args.start, args.end)
    lines.append("")
    if bench:
        lines.append(f"── 基准   沪深300 买入持有： {bench['ret'] * 100:+.2f}%")

    text = "\n".join(lines)
    print(text)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
