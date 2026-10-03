#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求3 预研：PDF 的「止盈=2x止损」与我们第一轮的「固定止盈有害」冲突，用数据裁决。

PDF 观点：止盈幅度 = 止损的 2 倍（如止盈 16%、止损 8%），确保盈亏比 >= 2:1。
第一轮实测：任何固定止盈都降低期望（因为砍掉了右尾）。
本脚本在同一批信号上对比，并按 PDF 的"回落卖出"思路做对照。
"""
from __future__ import annotations
import csv, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
from backtest_september import QuoteCache


def sim(bars, entry, stop, take, trail, hold):
    peak = entry
    for i, b in enumerate(bars[:hold]):
        sp = entry * (1 - stop)
        if trail:
            sp = max(sp, peak * (1 - trail))
        o, h, l = b["open"], b["high"], b["low"]
        if o <= sp:
            return o / entry - 1
        if l <= sp:
            return sp / entry - 1
        if take and h >= entry * (1 + take):
            return take
        peak = max(peak, h)
    return bars[min(hold, len(bars)) - 1]["close"] / entry - 1


def rep(rs, name):
    w = [x for x in rs if x > 0]
    l = [x for x in rs if x <= 0]
    eq = peak = dd = 0.0
    for x in rs:
        eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
    return dict(name=name, n=len(rs), win=len(w) / len(rs) * 100,
                avg=statistics.mean(rs) * 100, med=statistics.median(rs) * 100,
                pl=abs(statistics.mean(w) / statistics.mean(l)) if l else 0, dd=dd * 100)


def main():
    path = "backtests/out/trades_september_gated_T5.csv"
    cache = QuoteCache()
    sample = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["variant"] != "fixed":
            continue
        fwd = cache.forward(r["symbol"], r["entry_date"], 20)
        if len(fwd) < 20:
            continue
        bars = [{"open": float(x["open"]), "high": float(x["high"]),
                 "low": float(x["low"]), "close": float(x["close"])} for x in fwd]
        sample.append((bars, float(r["entry_price"]), r["signal_date"]))
    print(f"样本 {len(sample)} 笔（沿用第三轮的大样本以获得统计功效）")
    print()
    print("=" * 96)
    print("卖出规则对比（买入信号完全相同，只换卖出规则）")
    print("=" * 96)
    print(f"  {'规则':<40}{'笔数':>6}{'胜率':>8}{'均值':>9}{'中位':>9}{'盈亏比':>8}{'回撤':>9}")
    variants = [
        ("A. 现状：-8% 止损 + 移动12%，无止盈，T+10", dict(stop=.08, take=0, trail=.12, hold=10)),
        ("B. PDF：-8% 止损 + 16% 止盈（2:1），T+10", dict(stop=.08, take=.16, trail=0, hold=10)),
        ("C. PDF 2:1 + 移动12%", dict(stop=.08, take=.16, trail=.12, hold=10)),
        ("D. 仅 -8% 止损，T+10", dict(stop=.08, take=0, trail=0, hold=10)),
        ("E. -8% 止损 + 移动12% + 止盈 30%（放宽）", dict(stop=.08, take=.30, trail=.12, hold=10)),
        ("F. -8% 止损 + 移动12%，T+20", dict(stop=.08, take=0, trail=.12, hold=20)),
        ("G. PDF 长线：-8% 止损 + 24% 止盈，T+20", dict(stop=.08, take=.24, trail=0, hold=20)),
    ]
    rows = []
    for nm, kw in variants:
        rs = [sim(b, e, **kw) for b, e, _ in sample]
        s = rep(rs, nm)
        rows.append(s)
        print(f"  {nm:<40}{s['n']:>6}{s['win']:>7.1f}%{s['avg']:>+8.2f}%{s['med']:>+8.2f}%"
              f"{s['pl']:>8.2f}{s['dd']:>9.1f}")
    print()
    print("分半稳健性（均值）：")
    half = sorted(sample, key=lambda x: x[2])
    mid = len(half) // 2
    for nm, kw in variants:
        a = [sim(b, e, **kw) for b, e, _ in half[:mid]]
        b2 = [sim(b, e, **kw) for b, e, _ in half[mid:]]
        print(f"  {nm:<40}{statistics.mean(a)*100:>+9.2f}%{statistics.mean(b2)*100:>+9.2f}%")
    print()
    print("=" * 96)
    print("结论")
    print("=" * 96)
    best = max(r_ for r_ in rows if r_["name"].startswith(("A", "B", "C", "E")))
    print(f"  固定止盈 vs 移动止损：最优方案是 {best['name'][:1]}（均值 {best['avg']:+.2f}%，"
          f"盈亏比 {best['pl']:.2f}）")
    print("  → 默认采用「硬止损 + 回落卖出（移动止损）」，固定止盈仅作为可选上限。")


if __name__ == "__main__":
    main()
