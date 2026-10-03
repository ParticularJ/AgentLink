#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第六轮：ETF 路径 vs 个股选股。

第五轮结论是"系统没有可用的选择函数，收益来自择时"。
如果成立，那么直接买板块 ETF（纯 β 敞口）应当不输于、甚至优于在板块内挑个股。
第四轮的初步证据：仅 ETF 口径 34 笔 / 79.4% 胜率 / +5.02%。

本脚本做三方对照，并做非配对 bootstrap 与分半检验。
"""
from __future__ import annotations

import pickle, random, statistics, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache
from rerank import _entry, _next, _sina
from round3_improve import sim


def main():
    # 用**生产口径**的候选池（只含 run/run_low，不含 reserve）
    data = pickle.load(open(HERE / "out" / "candidates_oct_year.pkl", "rb"))
    cache = QuoteCache()
    days = sorted(data)
    di = {d: i for i, d in enumerate(days)}

    info = {}
    kinds = Counter()
    for d in days:
        for c in data[d]["candidates"]:
            sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
            kind = "ETF" if c.get("is_etf") else "个股"
            kinds[kind] += 1
            if (sym, d) in info:
                continue
            entry = _entry(cache, sym, d)
            nd = _next(cache, d)
            if entry is None or nd is None:
                info[(sym, d)] = None
                continue
            bars = [{"open": float(x["open"]), "high": float(x["high"]),
                     "low": float(x["low"]), "close": float(x["close"])}
                    for x in cache.forward(sym, nd, 12)][:10]
            if len(bars) < 10:
                info[(sym, d)] = None
                continue
            info[(sym, d)] = {"kind": kind, "bars": bars, "entry": entry}

    print(f"载入 {len(days)} 个交易日，候选 {sum(kinds.values())} 条  分布 {dict(kinds)}")
    for k in ("ETF", "个股"):
        rs = [sim(v["bars"], v["entry"], 0.08, 0.12, None, None, 10)[0]
              for v in info.values() if v and v["kind"] == k]
        if rs:
            w = [x for x in rs if x > 0]
            print(f"  {k:<4} 无条件单笔均值 {statistics.mean(rs)*100:+.2f}%  "
                  f"胜率 {len(w)/len(rs)*100:.1f}%  n={len(rs)}")

    def pipeline(topn=2, cooldown=40, mode="all", etf_slots=0,
                 etf_exit=(10, 0.08, 0.12), stock_exit=(10, 0.08, 0.12)):
        cooled, per_day = {}, {}
        for d in days:
            pool = []
            for c in data[d]["candidates"]:
                sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
                v = info.get((sym, d))
                if not v:
                    continue
                if mode == "etf" and v["kind"] != "ETF":
                    continue
                if mode == "stock" and v["kind"] != "个股":
                    continue
                pool.append((c.get("combined_score", 0), sym, v))
            if etf_slots > 0:
                etfs = sorted([x for x in pool if x[2]["kind"] == "ETF"], key=lambda x: -x[0])
                rest = sorted([x for x in pool if x[2]["kind"] != "ETF"], key=lambda x: -x[0])
                pool = etfs[:etf_slots] + rest + etfs[etf_slots:]
            else:
                pool.sort(key=lambda x: -x[0])
            rets = []
            for sc, sym, v in pool:
                if len(rets) >= topn:
                    break
                last = cooled.get(sym)
                if last is not None and di[d] - di[last] < cooldown:
                    continue
                cooled[sym] = d
                ex = etf_exit if v["kind"] == "ETF" else stock_exit
                rets.append(sim(v["bars"], v["entry"], ex[1], ex[2], None, None, ex[0])[0])
            if rets:
                per_day[d] = rets
        return per_day

    def rep(pd_, split=None):
        allr = [x for d in sorted(pd_) if (split is None or split(d)) for x in pd_[d]]
        if not allr:
            return None
        w = [x for x in allr if x > 0]
        l = [x for x in allr if x <= 0]
        eq = peak = dd = 0.0
        for d in sorted(pd_):
            if split is not None and not split(d):
                continue
            for x in pd_[d]:
                eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
        return dict(n=len(allr), win=len(w)/len(allr)*100, avg=statistics.mean(allr)*100,
                    med=statistics.median(allr)*100,
                    pl=abs(statistics.mean(w)/statistics.mean(l)) if l else 0, dd=dd*100)

    def boot(a, b, iters=2000):
        rnd = random.Random(13)
        da, db = sorted(a), sorted(b)
        diffs = []
        for _ in range(iters):
            ra = [x for d in [rnd.choice(da) for _ in da] for x in a[d]]
            rb = [x for d in [rnd.choice(db) for _ in db] for x in b[d]]
            if ra and rb:
                diffs.append(statistics.mean(ra) - statistics.mean(rb))
        diffs.sort()
        lo, hi = diffs[int(.025*len(diffs))]*100, diffs[int(.975*len(diffs))]*100
        return lo, hi, ("✅ 显著" if (lo > 0 or hi < 0) else "❌ 不显著")

    base = pipeline(mode="all")
    b = rep(base)
    print()
    print("=" * 100)
    print(f"现状（混合，按分数取前 2 + cd40）：{b['n']} 笔  胜率 {b['win']:.1f}%  "
          f"均值 {b['avg']:+.2f}%  中位 {b['med']:+.2f}%  盈亏比 {b['pl']:.2f}  回撤 {b['dd']:.1f}")
    print("=" * 100)
    print(f"  {'方案':<32}{'笔数':>7}{'胜率':>9}{'均值':>9}{'中位':>9}{'盈亏比':>8}{'回撤':>9}  vs现状")

    schemes = [
        ("仅 ETF（前 2）", dict(mode="etf")),
        ("仅 ETF（前 1）", dict(mode="etf", topn=1)),
        ("仅个股（前 2）", dict(mode="stock")),
        ("1 ETF + 1 个股", dict(etf_slots=1)),
        ("1 ETF + 1 个股（ETF 优先）", dict(etf_slots=1, topn=2)),
    ]
    for nm, kw in schemes:
        pd_ = pipeline(**kw)
        s = rep(pd_)
        if not s or s["n"] < 15:
            print(f"  {nm:<32}{(s or {'n':0})['n']:>7}  （样本过少）")
            continue
        lo, hi, sig = boot(pd_, base)
        print(f"  {nm:<32}{s['n']:>7}{s['win']:>8.1f}%{s['avg']:>+8.2f}%{s['med']:>+8.2f}%"
              f"{s['pl']:>8.2f}{s['dd']:>9.1f}  [{lo:+.2f},{hi:+.2f}] {sig}")

    print()
    print("=" * 100)
    print("ETF 专属出场参数扫描（个股保持 T+10/-8%/移12%，每日前 2 混合）")
    print("=" * 100)
    print(f"  {'ETF 出场':<26}{'笔数':>7}{'胜率':>9}{'均值':>9}{'中位':>9}{'盈亏比':>8}{'回撤':>9}")
    for hold in (10, 15, 20):
        for stop in (0.05, 0.08):
            for trail in (0.08, 0.12):
                s = rep(pipeline(etf_exit=(hold, stop, trail)))
                if not s:
                    continue
                print(f"  T+{hold}/-{stop:.0%}/移{trail:.0%}{'':<10}{s['n']:>7}{s['win']:>8.1f}%"
                      f"{s['avg']:>+8.2f}%{s['med']:>+8.2f}%{s['pl']:>8.2f}{s['dd']:>9.1f}")

    print()
    print("分半稳健性：")
    _tr = lambda d: d < "2026-04-01"
    _te = lambda d: d >= "2026-04-01"
    a1, a2 = rep(base, _tr), rep(base, _te)
    print(f"  {'（现状）':<32}{a1['n']:>9}{a1['avg']:>+9.2f}%{a2['n']:>10}{a2['avg']:>+9.2f}%")
    for nm, kw in schemes:
        pd_ = pipeline(**kw)
        x1, x2 = rep(pd_, _tr), rep(pd_, _te)
        if not x1 or not x2 or x1["n"] < 10 or x2["n"] < 10:
            continue
        mark = "  ✅ 两半皆优" if (x1["avg"] > a1["avg"] and x2["avg"] > a2["avg"]) else ""
        print(f"  {nm:<32}{x1['n']:>9}{x1['avg']:>+9.2f}%{x2['n']:>10}{x2['avg']:>+9.2f}%{mark}")


if __name__ == "__main__":
    main()
