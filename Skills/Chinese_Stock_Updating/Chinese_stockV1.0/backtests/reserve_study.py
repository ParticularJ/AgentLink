#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第五轮：reserve 路径实验。

发现：RANGE 评分 90、WAVE_UP 评分 85（都高于 STRONG_UP 的 80），
文档也写明操作方式（"仅超跌企稳小仓" / "回踩 MA20/MA60 低吸"），
但门控把它们统统标成 reserve = **从不交易**。
系统只交易自己评分最低的那个状态。

本脚本量化：如果按文档语义放开 reserve，收益与风险如何变化。
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
from factor_ic import factors_at
from rerank import _entry, _next, _sina
from round3_improve import sim


def main():
    path = HERE / "out" / "candidates_with_reserve.pkl"
    data = pickle.load(open(path, "rb"))
    cache = QuoteCache()
    try:
        from market_phase_detector import SECTOR_ETFS, get_sector_by_stock
    except Exception:
        SECTOR_ETFS, get_sector_by_stock = {}, lambda c: ""

    import fusion_config as fc
    from backtest_september import daily_phases

    days = sorted(data)
    di = {d: i for i, d in enumerate(days)}

    # 离线重算每日板块 phase，从而还原每个候选的真实 sector_action
    # （scored 里此前不含该字段，现已在 fusion_runner 修复，但旧 dump 需要重算）
    print("重算每日板块 phase ...")
    spd = {}
    for d in days:
        try:
            spd[d] = daily_phases(cache, d)[1]
        except Exception:
            spd[d] = {}

    acts = Counter()
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
            secs = c.get("sectors") or []
            pure = c.get("stock_code", "")
            sec = (secs[0] if secs else "") or get_sector_by_stock(pure)
            phase = spd[d].get(sec, "UNKNOWN")
            is_etf = bool(c.get("is_etf"))
            table = fc.PHASE_SECTOR_FILTER_ETF if is_etf else fc.PHASE_SECTOR_FILTER_STOCK
            act = table.get(phase, "block")
            acts[act] += 1
            f = factors_at(cache, sym, d, (SECTOR_ETFS.get(sec) or [None])[0])
            ret, _, _ = sim(bars, entry, 0.08, 0.12, None, None, 10)
            info[(sym, d)] = {"ret": ret, "sector": sec, "phase": phase, "act": act, "f": f or {}}

    print(f"载入 {len(days)} 个交易日，候选 {sum(acts.values())} 条")
    print("  按 sector_action 分布:", dict(acts))

    # reserve 候选的单独表现（不做任何筛选）
    for a in ("run", "run_low", "reserve"):
        rs = [v["ret"] for v in info.values() if v and v["act"] == a]
        if rs:
            w = [x for x in rs if x > 0]
            print(f"  {a:<9} 单笔均值 {statistics.mean(rs)*100:+.2f}%  胜率 {len(w)/len(rs)*100:.1f}%  n={len(rs)}")

    def pipeline(topn=2, cooldown=40, allow=None, extra=None, reserve_quota=0):
        """allow: 允许的 action 集合；extra: 针对 reserve 的额外入场过滤。

        reserve_quota>0 时，每天**优先**用 reserve 候选占满该名额，再取 run 补足。
        这是"按组优先"而不是"按分数优先"——检验 reserve 的组效应是否可用。
        """
        cooled, per_day = {}, {}
        for d in days:
            pool = []
            for c in data[d]["candidates"]:
                sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
                v = info.get((sym, d))
                if not v:
                    continue
                if allow and v["act"] not in allow:
                    continue
                if v["act"] == "reserve" and extra and not extra(v["f"], c):
                    continue
                pool.append((c.get("combined_score", 0), sym, v))
            if reserve_quota > 0:
                res = [x for x in pool if x[2]["act"] == "reserve"]
                run = [x for x in pool if x[2]["act"] != "reserve"]
                res.sort(key=lambda x: -x[0]); run.sort(key=lambda x: -x[0])
                pool = res[:reserve_quota] + run + res[reserve_quota:]
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
                rets.append(v["ret"])
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
        rnd = random.Random(11)
        da, db = sorted(a), sorted(b)
        diffs = []
        for _ in range(iters):
            ra = [x for d in [rnd.choice(da) for _ in da] for x in a[d]]
            rb = [x for d in [rnd.choice(db) for _ in db] for x in b[d]]
            if ra and rb:
                diffs.append(statistics.mean(ra) - statistics.mean(rb))
        diffs.sort()
        lo, hi = diffs[int(.025*len(diffs))]*100, diffs[int(.975*len(diffs))]*100
        return lo, hi, ("✅" if (lo > 0 or hi < 0) else "❌")

    near = lambda f, tol: abs(f.get("bias_20", 9)) <= tol
    base = pipeline(allow={"run", "run_low"})
    b = rep(base)
    print()
    print("=" * 100)
    print(f"现状（只用 run/run_low + top2 + cd40）：{b['n']} 笔  胜率 {b['win']:.1f}%  "
          f"均值 {b['avg']:+.2f}%  中位 {b['med']:+.2f}%  盈亏比 {b['pl']:.2f}  回撤 {b['dd']:.1f}")
    print("=" * 100)
    print(f"  {'方案':<38}{'笔数':>7}{'胜率':>9}{'均值':>9}{'中位':>9}{'盈亏比':>8}{'回撤':>9}  vs现状")

    schemes = [
        ("+ 全部 reserve", dict(allow={"run", "run_low", "reserve"})),
        ("+ reserve 且 |bias20|≤5%（回踩）", dict(allow={"run", "run_low", "reserve"},
                                            extra=lambda f, c: near(f, 0.05))),
        ("+ reserve 且 |bias20|≤3%", dict(allow={"run", "run_low", "reserve"},
                                        extra=lambda f, c: near(f, 0.03))),
        ("+ reserve 且 bias60<0（超跌）", dict(allow={"run", "run_low", "reserve"},
                                          extra=lambda f, c: f.get("bias_60", 1) < 0)),
        ("+ 仅 RANGE 的 reserve", dict(allow={"run", "run_low", "reserve"},
                                    extra=lambda f, c: c.get("sector_phase") == "RANGE")),
        ("+ 仅 WAVE_UP 的 reserve", dict(allow={"run", "run_low", "reserve"},
                                      extra=lambda f, c: c.get("sector_phase") == "WAVE_UP")),
    ]
    schemes += [
        ("★ 每天优先 1 只 reserve", dict(allow={"run", "run_low", "reserve"}, reserve_quota=1)),
        ("★ 每天优先 2 只 reserve", dict(allow={"run", "run_low", "reserve"}, reserve_quota=2)),
    ]
    for nm, kw in schemes:
        pd_ = pipeline(**kw)
        s = rep(pd_)
        if not s or s["n"] < 20:
            print(f"  {nm:<38}{(s or {'n':0})['n']:>7}  （样本过少）")
            continue
        lo, hi, sig = boot(pd_, base)
        print(f"  {nm:<38}{s['n']:>7}{s['win']:>8.1f}%{s['avg']:>+8.2f}%{s['med']:>+8.2f}%"
              f"{s['pl']:>8.2f}{s['dd']:>9.1f}  [{lo:+.2f},{hi:+.2f}] {sig}")

    print()
    print("分半稳健性：")
    _tr = lambda d: d < "2026-04-01"
    _te = lambda d: d >= "2026-04-01"
    a1, a2 = rep(base, _tr), rep(base, _te)
    print(f"  {'（现状）':<38}{a1['n']:>9}{a1['avg']:>+9.2f}%{a2['n']:>10}{a2['avg']:>+9.2f}%")
    for nm, kw in schemes:
        pd_ = pipeline(**kw)
        x1, x2 = rep(pd_, _tr), rep(pd_, _te)
        if not x1 or not x2 or x1["n"] < 15 or x2["n"] < 15:
            continue
        mark = "  ✅ 两半皆优" if (x1["avg"] > a1["avg"] and x2["avg"] > a2["avg"]) else ""
        print(f"  {nm:<38}{x1['n']:>9}{x1['avg']:>+9.2f}%{x2['n']:>10}{x2['avg']:>+9.2f}%{mark}")


if __name__ == "__main__":
    main()
