#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块2 复审：股票评分链的每一层是否都有预测力。

评分链（从底到顶）：
  strategy_score   各 analyzer 自己打的分
  best_score       同一标的多个策略里的最高分
  consistency_bonus 共振加分（2策略+22 / >=3策略+30）
  penalty          新闻情绪加减分
  sector_held_bonus 持仓同板块 +5
  base_score       = best + bonus + penalty + held，截断到 100
  combined_score   = base*0.8 + contribution*0.2，截断到 100
  rank_score       = 未截断版本（只用于排序）

逐一算它们与未来收益的秩相关（IC），看哪一层真的带信息。
"""
from __future__ import annotations
import math, pickle, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
from backtest_september import QuoteCache
from rerank import _entry, _next, _sina
from round3_improve import sim


def pearson(a, b):
    n = len(a)
    ma, mb = statistics.mean(a), statistics.mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a) / n)
    sb = math.sqrt(sum((x - mb) ** 2 for x in b) / n)
    if sa == 0 or sb == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n * sa * sb)


def rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    for pos, i in enumerate(o):
        r[i] = pos + 1
    return r


def main():
    data = pickle.load(open(HERE / "out" / "candidates_oct_year.pkl", "rb"))
    cache = QuoteCache()
    days = sorted(data)
    rows = []
    for d in days:
        for c in data[d]["candidates"]:
            sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
            entry, nd = _entry(cache, sym, d), _next(cache, d)
            if entry is None or nd is None:
                continue
            bars = [{"open": float(x["open"]), "high": float(x["high"]),
                     "low": float(x["low"]), "close": float(x["close"])}
                    for x in cache.forward(sym, nd, 12)][:10]
            if len(bars) < 10:
                continue
            ret, _, _ = sim(bars, entry, 0.08, 0.12, None, None, 10)
            rows.append({"ret": ret,
                         "combined": c.get("combined_score") or 0,
                         "best": c.get("best_score") or 0,
                         "rank": c.get("rank_score") or 0,
                         "nstrat": c.get("strategy_count") or 1,
                         "etf": 1 if c.get("is_etf") else 0})
    n = len(rows)
    print(f"样本 {n} 条候选（生产门控后）")
    rets = [r["ret"] for r in rows]
    print(f"收益：均值 {statistics.mean(rets)*100:+.2f}%  胜率 {sum(1 for x in rets if x>0)/n*100:.1f}%")
    print()
    print("=" * 84)
    print("评分链各层的 IC（与未来 T+10 实际收益的秩相关）")
    print("=" * 84)
    for nm, key in (("combined_score", "combined"), ("best_score", "best"),
                    ("rank_score", "rank"),
                    ("strategy_count(共振)", "nstrat"), ("is_etf", "etf")):
        v = [r[key] for r in rows]
        if len(set(v)) < 2:
            print(f"  {nm:<22} 取值恒定 = {v[0]}（无区分度）")
            continue
        print(f"  {nm:<22} IC = {pearson(rank(v), rank(rets)):+.4f}"
              f"   取值分布: min={min(v):.1f} max={max(v):.1f} 不同取值={len(set(v))}")
    print()
    print("=" * 84)
    print("评分分布（看是否挤在一小段）")
    print("=" * 84)
    for nm, key in (("combined_score", "combined"), ("best_score", "best")):
        v = sorted(r[key] for r in rows)
        print(f"  {nm}: 5%={v[n//20]:.1f}  25%={v[n//4]:.1f}  50%={v[n//2]:.1f}  "
              f"75%={v[3*n//4]:.1f}  95%={v[19*n//20]:.1f}")
        for lo, hi in ((0, 85), (85, 90), (90, 95), (95, 100.1)):
            k = sum(1 for x in v if lo <= x < hi)
            if k:
                sub = [r["ret"] for r in rows if lo <= r[key] < hi]
                print(f"      [{lo:>3},{hi:>5})  {k:>5} 条 ({k/n*100:>5.1f}%)  "
                      f"未来收益 {statistics.mean(sub)*100:>+7.2f}%  "
                      f"胜率 {sum(1 for x in sub if x>0)/len(sub)*100:>5.1f}%")
    print()
    print("=" * 84)
    print("共振机制的实际使用情况")
    print("=" * 84)
    from collections import Counter
    cc = Counter(r["nstrat"] for r in rows)
    for k in sorted(cc):
        sub = [r["ret"] for r in rows if r["nstrat"] == k]
        print(f"  {k} 个策略共振: {cc[k]:>5} 条 ({cc[k]/n*100:>5.1f}%)  "
              f"未来收益 {statistics.mean(sub)*100:>+7.2f}%")
    print(f"  → CONSISTENCY_BONUS_3(+30) 触发次数: {cc.get(3, 0) + cc.get(4, 0)}")


if __name__ == "__main__":
    main()
