#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求2 验证：把大盘 phase 从"只调仓位"提升为"交易开关"。

现状：大盘 STRONG_DOWN 只把仓位上限压到 30%，交易照做。
      → 2026-09 全月 STRONG_DOWN，仍然交易 17 笔，几乎全亏。
本脚本对比几种以大盘趋势为开关的方案。
"""
from __future__ import annotations
import pickle, random, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache
from rerank import _entry, _next, _sina
from round3_improve import sim

TOP_N, COOLDOWN = 2, 40
PROD_EXIT = (10, 0.08, 0.12)


def main():
    data = pickle.load(open(HERE / "out" / "candidates_oct_year.pkl", "rb"))
    cache = QuoteCache()
    days = sorted(data)
    di = {d: i for i, d in enumerate(days)}

    info = {}
    for d in days:
        for c in data[d]["candidates"]:
            sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
            if (sym, d) in info:
                continue
            entry, nd = _entry(cache, sym, d), _next(cache, d)
            if entry is None or nd is None:
                info[(sym, d)] = None
                continue
            bars = [{"open": float(x["open"]), "high": float(x["high"]),
                     "low": float(x["low"]), "close": float(x["close"])}
                    for x in cache.forward(sym, nd, 12)][:10]
            info[(sym, d)] = ({"bars": bars, "entry": entry,
                               "etf": bool(c.get("is_etf"))} if len(bars) >= 10 else None)

    def pipeline(mkt_rule=None, etf_only_when=None):
        """mkt_rule(market) -> False 表示当天禁止开仓；etf_only_when(market) -> True 表示当天只买 ETF"""
        cooled, per_day = {}, {}
        for d in days:
            mkt = data[d]["market"]
            if mkt_rule and not mkt_rule(mkt):
                continue
            pool = []
            for c in data[d]["candidates"]:
                sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
                v = info.get((sym, d))
                if not v:
                    continue
                if etf_only_when and etf_only_when(mkt) and not v["etf"]:
                    continue
                pool.append((c.get("combined_score", 0), sym, v))
            pool.sort(key=lambda x: -x[0])
            rets = []
            for sc, sym, v in pool:
                if len(rets) >= TOP_N:
                    break
                last = cooled.get(sym)
                if last is not None and di[d] - di[last] < COOLDOWN:
                    continue
                cooled[sym] = d
                rets.append(sim(v["bars"], v["entry"], PROD_EXIT[1], PROD_EXIT[2],
                                None, None, PROD_EXIT[0])[0])
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
        return dict(n=len(allr), win=len(w) / len(allr) * 100, avg=statistics.mean(allr) * 100,
                    med=statistics.median(allr) * 100,
                    pl=abs(statistics.mean(w) / statistics.mean(l)) if l else 0, dd=dd * 100,
                    days=len(pd_))

    def boot(a, b, iters=2000):
        rnd = random.Random(17)
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
    print(f"现状（大盘 phase 只调仓位）：{b['n']} 笔 {b['days']} 个交易日  "
          f"胜率 {b['win']:.1f}%  均值 {b['avg']:+.2f}%  中位 {b['med']:+.2f}%  "
          f"盈亏比 {b['pl']:.2f}  回撤 {b['dd']:.1f}")
    print()
    print("=" * 104)
    print("把大盘趋势升级为交易开关")
    print("=" * 104)
    print(f"  {'方案':<34}{'笔数':>6}{'交易日':>7}{'胜率':>8}{'均值':>9}{'中位':>9}{'盈亏比':>8}{'回撤':>9}   vs现状")
    schemes = [
        ("A. 大盘 STRONG_DOWN 日不开仓", dict(mkt_rule=lambda m: m != "STRONG_DOWN")),
        ("B. 大盘非 RANGE/WAVE/UP 不开仓", dict(mkt_rule=lambda m: m in ("RANGE", "WAVE_UP", "STRONG_UP"))),
        ("C. 大盘 STRONG_DOWN 日只做 ETF",
         dict(etf_only_when=lambda m: m == "STRONG_DOWN")),
        ("D. A + STRONG_DOWN 外也只做 ETF? (见 C)",
         dict(mkt_rule=lambda m: m != "STRONG_DOWN", etf_only_when=lambda m: False)),
        ("E. 大盘 STRONG_DOWN 不开仓 + 震荡只做 ETF",
         dict(mkt_rule=lambda m: m != "STRONG_DOWN",
              etf_only_when=lambda m: m in ("RANGE", "WAVE_UP"))),
    ]
    for nm, kw in schemes:
        pd_ = pipeline(**kw)
        s = rep(pd_)
        if not s:
            continue
        lo, hi, sig = boot(pd_, base)
        print(f"  {nm:<34}{s['n']:>6}{s['days']:>7}{s['win']:>7.1f}%{s['avg']:>+8.2f}%"
              f"{s['med']:>+8.2f}%{s['pl']:>8.2f}{s['dd']:>9.1f}   [{lo:+.2f},{hi:+.2f}] {sig}")

    print()
    print("=" * 104)
    print("逐月对比：现状 vs 方案 B（用户最关心 7-9 月）")
    print("=" * 104)
    print(f"  {'月份':<10}{'现状笔数':>9}{'现状均值':>10}{'B 笔数':>8}{'B 均值':>10}   变化")
    pb = pipeline(mkt_rule=lambda m: m in ("RANGE", "WAVE_UP", "STRONG_UP"))
    for m in sorted({d[:7] for d in days}):
        a = [x for d in base if d[:7] == m for x in base[d]]
        c = [x for d in pb if d[:7] == m for x in pb[d]]
        aa = f"{statistics.mean(a)*100:+.2f}%" if a else "  —  "
        cc = f"{statistics.mean(c)*100:+.2f}%" if c else "  —  "
        dd = (f"{(statistics.mean(c)-statistics.mean(a))*100:+.2f}pp"
              if a and c else ("避开亏损" if a and not c else ""))
        print(f"  {m:<10}{len(a):>9}{aa:>10}{len(c):>8}{cc:>10}   {dd}")

    print()
    print("分半稳健性：")
    _tr = lambda d: d < "2026-04-01"
    _te = lambda d: d >= "2026-04-01"
    a1, a2 = rep(base, _tr), rep(base, _te)
    print(f"  {'（现状）':<34}{a1['n']:>9}{a1['avg']:>+9.2f}%{a2['n']:>10}{a2['avg']:>+9.2f}%")
    for nm, kw in schemes:
        pd_ = pipeline(**kw)
        x1, x2 = rep(pd_, _tr), rep(pd_, _te)
        if not x1 or not x2:
            continue
        mark = "  ✅ 两半皆优" if (x1["avg"] > a1["avg"] and x2["avg"] > a2["avg"]) else ""
        print(f"  {nm:<34}{x1['n']:>9}{x1['avg']:>+9.2f}%{x2['n']:>10}{x2['avg']:>+9.2f}%{mark}")


if __name__ == "__main__":
    main()
