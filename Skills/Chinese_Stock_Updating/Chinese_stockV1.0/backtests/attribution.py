#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号质量归因：融合评分到底有没有预测力？

如果 combined_score 与未来收益无关，那整套打分/共振/加权就是噪音，
优化出场规则只是在给一个随机信号做美容。这是比出场规则更根本的问题。
"""
from __future__ import annotations

import csv, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
from backtest_september import QuoteCache
from optimize_exit import Rule, simulate

PROD = Rule(10, 0.08, 0.0, 0.12)


def load(cache, path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["variant"] != "fixed":
            continue
        fwd = cache.forward(r["symbol"], r["entry_date"], 20)
        if len(fwd) < 20:
            continue
        bars = [{"open": float(x["open"]), "high": float(x["high"]),
                 "low": float(x["low"]), "close": float(x["close"])} for x in fwd]
        ret, _, _ = simulate(bars, float(r["entry_price"]), PROD)
        out.append({"date": r["signal_date"], "code": r["symbol"], "name": r["name"],
                    "score": float(r["score"]), "strategy": r["strategy"], "ret": ret,
                    "raw": r["ret"]})
    return out


def line(label, vals):
    if not vals:
        return f"  {label:<22}  (无样本)"
    w = [v for v in vals if v > 0]
    return (f"  {label:<22}{len(vals):>6}{len(w)/len(vals)*100:>9.1f}%"
            f"{statistics.mean(vals)*100:>+10.2f}%{statistics.median(vals)*100:>+10.2f}%")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "backtests/out/trades_september_gated_T5.csv"
    cache = QuoteCache()
    s = load(cache, path)
    print(f"样本 {len(s)} 笔（出场口径：生产配置 T+10/-8%/移12%）")
    hdr = f"  {'分组':<22}{'笔数':>6}{'胜率':>10}{'均值':>11}{'中位':>11}"

    print("\n" + "=" * 78)
    print("① 融合评分 vs 未来收益 —— 打分有预测力吗？")
    print("=" * 78)
    print(hdr)
    for lo, hi in [(0, 85), (85, 90), (90, 95), (95, 100), (100, 999)]:
        print(line(f"分数 [{lo},{hi})", [x["ret"] for x in s if lo <= x["score"] < hi]))
    xs = [x["score"] for x in s]; ys = [x["ret"] for x in s]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((a-mx)*(b-my) for a, b in zip(xs, ys)) / len(s)
    sx = statistics.pstdev(xs); sy = statistics.pstdev(ys)
    print(f"\n  Pearson 相关系数 corr(score, ret) = {cov/(sx*sy):+.4f}" if sx and sy else "")

    print("\n" + "=" * 78)
    print("② 每日排名位置 vs 收益 —— 排名有区分度吗？")
    print("=" * 78)
    by_day = defaultdict(list)
    for x in s:
        by_day[x["date"]].append(x)
    ranks = defaultdict(list)
    for day, items in by_day.items():
        items.sort(key=lambda z: -z["score"])
        for i, it in enumerate(items):
            ranks[min(i + 1, 5)].append(it["ret"])
    print(hdr)
    for k in sorted(ranks):
        print(line(f"当日第 {k} 名", ranks[k]))

    print("\n" + "=" * 78)
    print("③ 策略来源 vs 收益")
    print("=" * 78)
    print(hdr)
    by_st = defaultdict(list)
    for x in s:
        by_st[x["strategy"] or "(空)"].append(x["ret"])
    for k, v in sorted(by_st.items(), key=lambda kv: -len(kv[1]))[:8]:
        print(line(k[:22], v))

    print("\n" + "=" * 78)
    print("④ 同一只票被重复推荐 —— 该只买第一次吗？")
    print("=" * 78)
    seq = defaultdict(list)
    for x in s:
        seq[x["code"]].append(x)
    first, later = [], []
    for code, items in seq.items():
        items.sort(key=lambda z: z["date"])
        first.append(items[0]["ret"])
        later += [i["ret"] for i in items[1:]]
    print(hdr)
    print(line("首次推荐", first))
    print(line("重复推荐(第2次起)", later))
    rep = {c: len(v) for c, v in seq.items() if len(v) > 1}
    print(f"\n  被重复推荐的标的数: {len(rep)} / {len(seq)}"
          f"（最多 {max(rep.values()) if rep else 0} 次）")

    print("\n" + "=" * 78)
    print("⑤ 每日推荐数量 vs 收益 —— 信号越多是不是越差？")
    print("=" * 78)
    print(hdr)
    for k in range(1, 8):
        v = [x["ret"] for day, items in by_day.items() if len(items) == k for x in items]
        if v:
            print(line(f"当日 {k} 只", v))


if __name__ == "__main__":
    main()
