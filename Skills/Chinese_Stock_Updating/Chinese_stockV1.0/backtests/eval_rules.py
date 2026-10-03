#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""聚焦评估：推荐出场规则 × 入场过滤 的组合效果（全样本 + 分半验证）。"""
from __future__ import annotations

import csv, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
from backtest_september import QuoteCache
from optimize_exit import Rule, simulate

HORIZON = 20


def build(cache, path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["variant"] != "fixed":
            continue
        fwd = cache.forward(r["symbol"], r["entry_date"], HORIZON)
        if len(fwd) < HORIZON:
            continue
        bars = [{"open": float(x["open"]), "high": float(x["high"]),
                 "low": float(x["low"]), "close": float(x["close"])} for x in fwd]
        sb = cache.bar(r["symbol"], r["signal_date"])
        gap = float(r["entry_price"]) / float(sb["close"]) - 1 if sb else 0.0
        out.append({"date": r["signal_date"], "entry": float(r["entry_price"]),
                    "bars": bars, "gap": gap, "score": float(r["score"]),
                    "sector": r["strategy"]})
    return out


def stat(rets, days):
    w = [x for x in rets if x > 0]; l = [x for x in rets if x <= 0]
    eq = peak = dd = 0.0
    for x in rets:
        eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
    return dict(n=len(rets), win=len(w)/len(rets)*100, avg=statistics.mean(rets)*100,
                med=statistics.median(rets)*100,
                pl=abs(statistics.mean(w)/statistics.mean(l)) if l else float("inf"),
                dd=dd*100, days=statistics.mean(days))


def evaluate(sample, rule, gap_max=None, label=""):
    rets, days = [], []
    for s in sample:
        if gap_max is not None and s["gap"] > gap_max:
            continue
        r, d, _ = simulate(s["bars"], s["entry"], rule)
        rets.append(r); days.append(d)
    return stat(rets, days)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "backtests/out/trades_september_gated_T5.csv"
    cache = QuoteCache()
    sample = build(cache, path)
    train = [s for s in sample if s["date"] < "2026-04-01"]
    test = [s for s in sample if s["date"] >= "2026-04-01"]

    rules = [
        (Rule(5, 0.05), "现状 T+5/-5%"),
        (Rule(10, 0.08, 0.0, 0.12), "推荐 T+10/-8%/移12%"),
        (Rule(10, 0.10, 0.0, 0.12), "备选 T+10/-10%/移12%"),
        (Rule(10, 0.08, 0.0, 0.0), "仅放宽 T+10/-8%"),
        (Rule(10, 0.08, 0.0, 0.12, 0.05), "推荐+保本止损"),
    ]
    gaps = [None, 0.05, 0.03]

    print("=" * 104)
    print("组合对比（全样本 / 训练 / 测试）")
    print("=" * 104)
    print(f"{'方案':<26}{'跳空过滤':>9}{'笔数':>7}{'胜率':>8}{'均值':>9}{'中位':>9}{'盈亏比':>8}{'回撤':>9}{'持有':>7}")
    for rule, rname in rules:
        for g in gaps:
            st = evaluate(sample, rule, g)
            gl = "无" if g is None else f">{g:.0%}剔除"
            print(f"{rname:<26}{gl:>9}{st['n']:>7}{st['win']:>7.1f}%{st['avg']:>+8.2f}%{st['med']:>+8.2f}%"
                  f"{st['pl']:>8.2f}{st['dd']:>9.1f}{st['days']:>7.1f}")
        print()

    print("=" * 104)
    print("分半稳健性（同一方案在两半区间的表现）")
    print("=" * 104)
    print(f"{'方案':<26}{'跳空过滤':>9}{'训练笔数':>9}{'训练均值':>10}{'训练胜率':>10}{'测试笔数':>9}{'测试均值':>10}{'测试胜率':>10}")
    for rule, rname in rules:
        for g in (None, 0.05):
            a = evaluate(train, rule, g); b = evaluate(test, rule, g)
            gl = "无" if g is None else f">{g:.0%}剔除"
            print(f"{rname:<26}{gl:>9}{a['n']:>9}{a['avg']:>+9.2f}%{a['win']:>9.1f}%{b['n']:>9}{b['avg']:>+9.2f}%{b['win']:>9.1f}%")
        print()


if __name__ == "__main__":
    main()
