#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第四轮：选择性研究（候选供给与门控）。

第三轮证明改排序函数没用，因为候选太少。这一轮量化"到底少到什么程度"
并测试各种"更严/更宽"的取法：
  A. topn 扫描（每天只买 1/2/3/5 只）
  B. 要求多策略共振
  C. 按大盘 phase 择时
  D. 板块集中度上限
全部用日度 bootstrap 与现状对比，并做训练/测试分半。
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
    data = pickle.load(open(HERE / "out" / "candidates_oct_year.pkl", "rb"))
    cache = QuoteCache()
    days = sorted(data)
    di = {d: i for i, d in enumerate(days)}

    # 预取每个 (sym, day) 的未来收益与板块
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
                    for x in cache.forward(sym, nd, 12)][:10]
            if len(bars) < 10:
                info[(sym, d)] = None
                continue
            ret, _, _ = sim(bars, entry, 0.08, 0.12, None, None, 10)
            secs = c.get("sectors") or []
            info[(sym, d)] = {"ret": ret, "sector": secs[0] if secs else "",
                              "mkt": data[d]["market"], "nstrat": c.get("strategy_count", 1)}

    def pipeline(topn=5, cooldown=20, need_reson=0, mkt_ok=None, sector_cap=None):
        cooled, per_day = {}, {}
        for d in days:
            mkt = data[d]["market"]
            if mkt_ok is not None and not mkt_ok(mkt):
                continue
            pool = []
            for c in data[d]["candidates"]:
                sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
                v = info.get((sym, d))
                if not v:
                    continue
                if need_reson and (c.get("strategy_count", 1) < need_reson):
                    continue
                pool.append((c.get("combined_score", 0), sym, v))
            pool.sort(key=lambda x: -x[0])
            sec_count, rets = Counter(), []
            for sc, sym, v in pool:
                if len(rets) >= topn:
                    break
                last = cooled.get(sym)
                if last is not None and di[d] - di[last] < cooldown:
                    continue
                if sector_cap and v["sector"] and sec_count[v["sector"]] >= sector_cap:
                    continue
                cooled[sym] = d
                sec_count[v["sector"]] += 1
                rets.append(v["ret"])
            if rets:
                per_day[d] = rets
        return per_day

    def rep(per_day, split=None):
        allr = [x for d in sorted(per_day) if (split is None or split(d))
                for x in per_day[d]]
        if not allr:
            return None
        w = [x for x in allr if x > 0]
        l = [x for x in allr if x <= 0]
        eq = peak = dd = 0.0
        for d in sorted(per_day):
            if split is not None and not split(d):
                continue
            for x in per_day[d]:
                eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
        return dict(n=len(allr), win=len(w) / len(allr) * 100, avg=statistics.mean(allr) * 100,
                    med=statistics.median(allr) * 100,
                    pl=abs(statistics.mean(w) / statistics.mean(l)) if l else 0, dd=dd * 100)

    def boot(a, b, iters=2000):
        """非配对日度 bootstrap：两个方案各自重抽样自己的交易日。

        配对 bootstrap 只适用于"同一天换股票"的方案；对"改变交易日集合"的方案
        （如只在大盘 RANGE 时交易），配对会把这个方案要利用的效应正好剔除掉，
        得出与池化均值相反的结论。这里统一用非配对，两类方案都适用。
        """
        rnd = random.Random(7)
        da, db = sorted(a), sorted(b)
        diffs = []
        for _ in range(iters):
            ra = [x for d in [rnd.choice(da) for _ in da] for x in a[d]]
            rb = [x for d in [rnd.choice(db) for _ in db] for x in b[d]]
            if ra and rb:
                diffs.append(statistics.mean(ra) - statistics.mean(rb))
        diffs.sort()
        lo, hi = diffs[int(.025 * len(diffs))] * 100, diffs[int(.975 * len(diffs))] * 100
        return lo, hi, ("✅ 显著" if (lo > 0 or hi < 0) else "❌ 不显著")

    base = pipeline()
    b = rep(base)
    print("=" * 104)
    print("现状：每日取前 5 + 20 日冷却不回填 + 生产出场")
    print(f"  笔数 {b['n']}  胜率 {b['win']:.1f}%  均值 {b['avg']:+.2f}%  中位 {b['med']:+.2f}%  "
          f"盈亏比 {b['pl']:.2f}  回撤 {b['dd']:.1f}")
    print("=" * 104)
    print(f"  {'方案':<30}{'笔数':>7}{'胜率':>9}{'均值':>9}{'中位':>9}{'盈亏比':>8}{'回撤':>9}   vs 现状")

    schemes = []
    for n in (1, 2, 3, 4, 5):
        schemes.append((f"A. 每日只买前 {n} 名", dict(topn=n)))
    schemes += [
        ("B. 要求 2 策略共振", dict(need_reson=2)),
        ("C. 只在大盘 RANGE 时交易", dict(mkt_ok=lambda m: m == "RANGE")),
        ("C. 避开 STRONG_DOWN", dict(mkt_ok=lambda m: m != "STRONG_DOWN")),
        ("D. 同板块最多 1 只", dict(sector_cap=1)),
        ("D. 同板块最多 2 只", dict(sector_cap=2)),
        ("A+C. 前 2 名 + 避开 STRONG_DOWN", dict(topn=2, mkt_ok=lambda m: m != "STRONG_DOWN")),
        ("A+D. 前 2 名 + 同板块≤1", dict(topn=2, sector_cap=1)),
    ]
    for nm, kw in schemes:
        pd_ = pipeline(**kw)
        s = rep(pd_)
        if s is None or s["n"] < 20:
            print(f"  {nm:<30}{(s or {'n': 0})['n']:>7}  （样本过少）")
            continue
        lo, hi, sig = boot(pd_, base)
        print(f"  {nm:<30}{s['n']:>7}{s['win']:>8.1f}%{s['avg']:>+8.2f}%{s['med']:>+8.2f}%"
              f"{s['pl']:>8.2f}{s['dd']:>9.1f}   [{lo:+.2f},{hi:+.2f}] {sig}")

    print()
    print("topn × 冷却期 网格（均值 / 笔数）—— 检验「买得越少越好」是否单调")
    print(f"  {'冷却\\topn':<10}" + "".join(f"{'前 '+str(n)+' 名':>14}" for n in (1, 2, 3, 5)))
    for cd in (0, 10, 20, 40):
        cells = []
        for n in (1, 2, 3, 5):
            s = rep(pipeline(topn=n, cooldown=cd))
            cells.append(f"{s['avg']:+.2f}%({s['n']})" if s else "-")
        print(f"  {cd:>2} 日    " + "".join(f"{c:>14}" for c in cells))

    print()
    _tr = lambda d: d < "2026-04-01"
    _te = lambda d: d >= "2026-04-01"
    print("聚焦检验：单变量改动 vs 现状（非配对 bootstrap + 分半）")
    print(f"  {'对比':<34}{'均值':>9}{'笔数':>7}   {'95% CI':<22}{'训练':>9}{'测试':>9}")
    focus = [
        ("现状 top5/cd20", dict(topn=5, cooldown=20)),
        ("top5/cd40（只加长冷却）", dict(topn=5, cooldown=40)),
        ("top2/cd20（只减少买入数）", dict(topn=2, cooldown=20)),
        ("top2/cd40（两项都改）", dict(topn=2, cooldown=40)),
        ("top1/cd40", dict(topn=1, cooldown=40)),
    ]
    ref = pipeline(**focus[0][1])
    for nm, kw in focus:
        pd_ = pipeline(**kw)
        s, x1, x2 = rep(pd_), rep(pd_, _tr), rep(pd_, _te)
        if not s:
            continue
        if nm == focus[0][0]:
            ci = "—"
        else:
            lo, hi, sig = boot(pd_, ref)
            ci = f"[{lo:+.2f},{hi:+.2f}] {sig[:2]}"
        print(f"  {nm:<34}{s['avg']:>+8.2f}%{s['n']:>7}   {ci:<22}"
              f"{x1['avg'] if x1 else 0:>+8.2f}%{x2['avg'] if x2 else 0:>+8.2f}%")

    # 分半稳健性：只看在两个半区都不差于现状的方案
    print()
    print("分半稳健性（均值）—— 只有两半都不差才值得采纳")
    print(f"  {'方案':<30}{'训练笔数':>9}{'训练均值':>10}{'测试笔数':>10}{'测试均值':>10}")
    tr = lambda d: d < "2026-04-01"
    te = lambda d: d >= "2026-04-01"
    a1, a2 = rep(base, tr), rep(base, te)
    print(f"  {'（现状）':<30}{a1['n']:>9}{a1['avg']:>+9.2f}%{a2['n']:>10}{a2['avg']:>+9.2f}%")
    for nm, kw in schemes:
        pd_ = pipeline(**kw)
        x1, x2 = rep(pd_, tr), rep(pd_, te)
        if not x1 or not x2 or x1["n"] < 15 or x2["n"] < 15:
            continue
        mark = "  ✅ 两半皆优" if (x1["avg"] > a1["avg"] and x2["avg"] > a2["avg"]) else ""
        print(f"  {nm:<30}{x1['n']:>9}{x1['avg']:>+9.2f}%{x2['n']:>10}{x2['avg']:>+9.2f}%{mark}")


if __name__ == "__main__":
    main()
