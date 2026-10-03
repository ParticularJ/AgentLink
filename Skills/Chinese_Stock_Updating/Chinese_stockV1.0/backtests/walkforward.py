#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第六轮：滚动前推（walk-forward）验证 —— 我们选的参数到底是不是过拟合？

第一~四轮的参数都是用同一年的数据选的。单个训练/测试分割只能验证一次，
无法回答"反复在同一数据上调参是否已经过拟合"。

做法：滚动窗口，每个窗口内只用训练段挑最优参数，再拿到紧接的测试段验证，
最后把各测试段的真实结果串起来，与固定使用生产参数对比。
"""
from __future__ import annotations

import itertools, pickle, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache
from rerank import _entry, _next, _sina
from round3_improve import sim


def build(cache, data, days):
    info = {}
    for d in days:
        for c in data[d]["candidates"]:
            sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
            if (sym, d) in info:
                continue
            entry = _entry(cache, sym, d)
            nd = _next(cache, d)
            if entry is None or nd is None:
                info[(sym, d)] = None
                continue
            bars = [{"open": float(x["open"]), "high": float(x["high"]),
                     "low": float(x["low"]), "close": float(x["close"])}
                    for x in cache.forward(sym, nd, 25)]
            info[(sym, d)] = {"bars": bars, "entry": entry} if len(bars) >= 25 else None
    return info


def run_window(data, info, di, seg, topn, cooldown, hold, stop, trail):
    cooled, rets = {}, []
    for d in seg:
        if d not in data:
            continue
        pool = []
        for c in data[d]["candidates"]:
            sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
            v = info.get((sym, d))
            if v:
                pool.append((c.get("combined_score", 0), sym, v))
        pool.sort(key=lambda x: -x[0])
        got = 0
        for sc, sym, v in pool:
            if got >= topn:
                break
            last = cooled.get(sym)
            if last is not None and di[d] - di[last] < cooldown:
                continue
            cooled[sym] = d
            got += 1
            rets.append(sim(v["bars"], v["entry"], stop, trail, None, None, hold)[0])
    return rets


def stat(rs):
    if not rs:
        return None
    w = [x for x in rs if x > 0]
    l = [x for x in rs if x <= 0]
    return dict(n=len(rs), win=len(w) / len(rs) * 100, avg=statistics.mean(rs) * 100,
                pl=abs(statistics.mean(w) / statistics.mean(l)) if l else 0)


def main():
    data = pickle.load(open(HERE / "out" / "candidates_oct_year.pkl", "rb"))
    cache = QuoteCache()
    days = sorted(data)
    di = {d: i for i, d in enumerate(days)}
    info = build(cache, data, days)

    PROD = dict(topn=2, cooldown=40, hold=10, stop=0.08, trail=0.12)
    grid = [dict(topn=t, cooldown=c, hold=10, stop=0.08, trail=0.12)
            for t, c in itertools.product((1, 2, 3, 5), (0, 10, 20, 40))]
    grid += [dict(topn=2, cooldown=40, hold=h, stop=s, trail=tr)
             for h, s, tr in itertools.product((5, 10, 20), (0.05, 0.08), (0.0, 0.12))]

    bounds = [("2025-09-30", "2026-03-31", "2026-04-01", "2026-06-30"),
              ("2026-01-01", "2026-06-30", "2026-07-01", "2026-09-30")]

    print("=" * 96)
    print("滚动前推验证：每个窗口只用训练段选参数，在测试段验证")
    print("=" * 96)
    tests = []
    for t0, t1, s0, s1 in bounds:
        tr = [d for d in days if t0 <= d <= t1]
        te = [d for d in days if s0 <= d <= s1]
        best, bestv = None, None
        for g in grid:
            st = stat(run_window(data, info, di, tr, **g))
            if st and st["n"] >= 20 and (bestv is None or st["avg"] > bestv["avg"]):
                best, bestv = g, st
        prod_te = stat(run_window(data, info, di, te, **PROD))
        best_te = stat(run_window(data, info, di, te, **best))
        print()
        print(f"窗口 {s0} ~ {s1}（测试段）")
        print(f"  训练段最优   : topn={best['topn']} 冷却={best['cooldown']} "
              f"持有={best['hold']} 止损={best['stop']:.0%} 移动={best['trail']:.0%}"
              f"   训练均值 {bestv['avg']:+.2f}% ({bestv['n']} 笔)")
        print(f"  → 该参数测试 : {best_te['n']} 笔  胜率 {best_te['win']:.1f}%  均值 {best_te['avg']:+.2f}%")
        print(f"  → 生产固定   : {prod_te['n']} 笔  胜率 {prod_te['win']:.1f}%  均值 {prod_te['avg']:+.2f}%")
        tests.append((best_te, prod_te))

    print()
    print("=" * 96)
    print("汇总：把所有测试段拼起来（这才是样本外的真实表现）")
    print("=" * 96)
    bw = [x for x, _ in tests]
    pw = [y for _, y in tests]
    tot_b = sum(x["n"] for x in bw)
    tot_p = sum(x["n"] for x in pw)
    avg_b = sum(x["avg"] * x["n"] for x in bw) / tot_b
    avg_p = sum(x["avg"] * x["n"] for x in pw) / tot_p
    win_b = sum(x["win"] * x["n"] for x in bw) / tot_b
    win_p = sum(x["win"] * x["n"] for x in pw) / tot_p
    print(f"  窗口内择优后拼接 : {tot_b:>4} 笔  胜率 {win_b:.1f}%  均值 {avg_b:+.2f}%")
    print(f"  生产固定参数     : {tot_p:>4} 笔  胜率 {win_p:.1f}%  均值 {avg_p:+.2f}%")
    verdict = ("择优并未胜过固定参数 → 固定参数没有明显过拟合"
               if avg_b <= avg_p else
               "择优在样本外更好 → 固定参数可能不是最优")
    print()
    print(f"  结论：{verdict}")


if __name__ == "__main__":
    main()
