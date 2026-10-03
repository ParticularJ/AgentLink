#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第三轮：基于全量候选的重排序实验。

为什么必须导出全量候选：交易明细只含每日已选中的前 5 名，
在 5 个里重排序等于没排序（第一次实验六种排序结果完全相同就是这个原因）。

同时输出**日度 bootstrap 置信区间**：707 笔样本下，均值差 0.2pp 完全可能是噪音，
没有显著性就不该采纳。
"""
from __future__ import annotations

import pickle, random, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache
from factor_ic import factors_at
from round3_improve import sim

DUMP = HERE / "out" / "candidates_oct_year.pkl"


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DUMP
    data = pickle.load(open(path, "rb"))
    cache = QuoteCache()
    try:
        from market_phase_detector import SECTOR_ETFS, get_sector_by_stock
    except Exception:
        SECTOR_ETFS, get_sector_by_stock = {}, lambda c: ""

    days = sorted(data)
    di = {d: i for i, d in enumerate(days)}
    total = sum(len(v["candidates"]) for v in data.values())
    print(f"载入 {len(days)} 个交易日，候选 {total} 条")

    # 为每条候选算因子 + 未来收益
    fc = {}
    for d in days:
        for c in data[d]["candidates"]:
            code = c.get("raw_code") or None
            pure = (c.get("stock_code") or "")
            sym = code or (pure if pure[:2] in ("sh", "sz") else _sina(pure))
            key = (sym, d)
            if key in fc:
                continue
            sec = get_sector_by_stock(pure[2:] if pure[:2] in ("sh", "sz") else pure) or ""
            f = factors_at(cache, sym, d, (SECTOR_ETFS.get(sec) or [None])[0])
            fc[key] = f
    ok = sum(1 for v in fc.values() if v)
    print(f"因子可得 {ok} / {total}")

    # 复合"不过热"分
    use = ["bias_60", "atr_pct", "mom_5", "vol_ratio", "dist_low_20"]
    vals = defaultdict(list)
    for f in fc.values():
        if f:
            for nm in use:
                vals[nm].append(f[nm])
    mu = {nm: statistics.mean(vals[nm]) for nm in use}
    sd = {nm: (statistics.pstdev(vals[nm]) or 1) for nm in use}
    for f in fc.values():
        if f:
            f["_comp"] = -sum((f[nm] - mu[nm]) / sd[nm] for nm in use) / len(use)

    def pipeline(keyfn, cooldown=20, topn=5, k_atr=None, max_hold=10, trail=0.12, filt=None):
        cooled, per_day = {}, {}
        for d in days:
            pool = [(c, fc.get(((c.get("raw_code") or _sina(c.get("stock_code", ""))), d)))
                    for c in data[d]["candidates"]]
            pool = [(c, f) for c, f in pool if f]
            if filt is not None:
                pool = [(c, f) for c, f in pool if filt(c, f)]
            if not pool:
                continue
            pool.sort(key=lambda cf: keyfn(cf[0], cf[1]), reverse=True)
            picked = []
            for c, f in pool[:topn]:
                sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
                last = cooled.get(sym)
                if last is not None and di[d] - di[last] < cooldown:
                    continue
                cooled[sym] = d
                picked.append((c, f, sym))
            rets = []
            for c, f, sym in picked:
                entry = _entry(cache, sym, d)
                if entry is None:
                    continue
                bars = [{"open": float(x["open"]), "high": float(x["high"]),
                         "low": float(x["low"]), "close": float(x["close"])}
                        for x in cache.forward(sym, _next(cache, d), max_hold + 2)][:max_hold]
                if len(bars) < max_hold:
                    continue
                ret, _, _ = sim(bars, entry, 0.08, trail, f.get("atr_pct"), k_atr, max_hold)
                rets.append(ret)
            if rets:
                per_day[d] = rets
        return per_day

    def report(nm, per_day):
        allr = [x for v in per_day.values() for x in v]
        w = [x for x in allr if x > 0]
        l = [x for x in allr if x <= 0]
        eq = peak = dd = 0.0
        for d in sorted(per_day):
            for x in per_day[d]:
                eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
        return dict(name=nm, n=len(allr), win=len(w) / len(allr) * 100,
                    avg=statistics.mean(allr) * 100, med=statistics.median(allr) * 100,
                    pl=abs(statistics.mean(w) / statistics.mean(l)) if l else 0, dd=dd * 100,
                    _per_day=per_day)

    def boot(a, b, iters=2000):
        """日度 bootstrap：比较两个方案的均值差是否显著。"""
        common = sorted(set(a["_per_day"]) & set(b["_per_day"]))
        diffs = []
        rnd = random.Random(42)
        for _ in range(iters):
            samp = [rnd.choice(common) for _ in common]
            ra = [x for d in samp for x in a["_per_day"][d]]
            rb = [x for d in samp for x in b["_per_day"][d]]
            if ra and rb:
                diffs.append(statistics.mean(ra) - statistics.mean(rb))
        diffs.sort()
        lo = diffs[int(0.025 * len(diffs))] * 100
        hi = diffs[int(0.975 * len(diffs))] * 100
        sig = "✅ 显著" if (lo > 0 or hi < 0) else "❌ 不显著（含 0）"
        return lo, hi, sig

    base_fn = lambda c, f: c.get("combined_score", 0)
    base = report("原融合评分（现状）", pipeline(base_fn))
    print()
    print("=" * 100)
    print("重排序对比（每日取前 5 + 20 日冷却不回填 + 生产出场）")
    print("=" * 100)
    print(f"  {'排序方式':<26}{'笔数':>7}{'胜率':>9}{'均值':>9}{'中位':>9}{'盈亏比':>8}{'回撤':>10}")
    print(f"  {base['name']:<26}{base['n']:>7}{base['win']:>8.1f}%{base['avg']:>+8.2f}%"
          f"{base['med']:>+8.2f}%{base['pl']:>8.2f}{base['dd']:>10.1f}")

    cands = [
        ("「不过热」复合因子", lambda c, f: f["_comp"]),
        ("只用 bias_60 最小优先", lambda c, f: -f["bias_60"]),
        ("只用 atr_pct 最小优先", lambda c, f: -f["atr_pct"]),
        ("只用 mom_5 最小优先", lambda c, f: -f["mom_5"]),
        ("原评分 + 复合因子", lambda c, f: c.get("combined_score", 0) / 100 + 0.6 * f["_comp"]),
    ]
    for nm, fn in cands:
        st = report(nm, pipeline(fn))
        print(f"  {nm:<26}{st['n']:>7}{st['win']:>8.1f}%{st['avg']:>+8.2f}%"
              f"{st['med']:>+8.2f}%{st['pl']:>8.2f}{st['dd']:>10.1f}")
        if st["n"] >= 50:
            lo, hi, sig = boot(st, base)
            print(f"       vs 现状：均值差 95% CI [{lo:+.2f}pp, {hi:+.2f}pp]  {sig}")

    # ── 过滤类方案：不改变排序，只把"过热"的候选剔掉 ──
    print()
    print("  ── 过滤类（保持原评分排序，只剔除过热标的）──")
    for nm, flt in (
            ("剔除 bias_60 > 15%", lambda c, f: f["bias_60"] <= 0.15),
            ("剔除 bias_60 > 25%", lambda c, f: f["bias_60"] <= 0.25),
            ("剔除 bias_60 > 35%", lambda c, f: f["bias_60"] <= 0.35),
            ("剔除 atr_pct > 6%", lambda c, f: f["atr_pct"] <= 0.06),
            ("剔除 mom_5 > 12%", lambda c, f: f["mom_5"] <= 0.12),
            ("剔除 vol_ratio > 3", lambda c, f: f["vol_ratio"] <= 3.0),
            ("剔除 bias60>25% 且 atr>6%", lambda c, f: f["bias_60"] <= 0.25 and f["atr_pct"] <= 0.06)):
        st = report(nm, pipeline(base_fn, filt=flt))
        if st["n"] < 30:
            print(f"  {nm:<26}{st['n']:>7}  （样本过少，跳过）")
            continue
        print(f"  {nm:<26}{st['n']:>7}{st['win']:>8.1f}%{st['avg']:>+8.2f}%"
              f"{st['med']:>+8.2f}%{st['pl']:>8.2f}{st['dd']:>10.1f}")
        lo, hi, sig = boot(st, base)
        print(f"       vs 现状：均值差 95% CI [{lo:+.2f}pp, {hi:+.2f}pp]  {sig}")


def _sina(code):
    c = code.strip()
    if c[:2] in ("sh", "sz"):
        return c
    return ("sh" if c[:1] in ("6", "5", "9") else "sz") + c


def _next(cache, d):
    for x in cache.all_dates:
        if x > d:
            return x
    return None


def _entry(cache, sym, d):
    nd = _next(cache, d)
    if nd is None:
        return None
    b = cache.bar(sym, nd)
    return float(b["open"]) if b else None


if __name__ == "__main__":
    main()
