#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按"交易大师"思路重做打分口径，并用数据裁决是否采用。

诊断（模块2）：analyzer 自己的 best_score 与未来收益 IC = -0.070（反向）；
买入位置分位均值 0.830，48.6% 落在 60 日区间最高 10%（那档平均浮亏 -8.93%）。

大师思路（三条，都有 IC 支撑）：
  1. 不追高：买在 60 日区间的中低位，而不是最高 10%
  2. 不碰过热：低波动优先（atr_pct 是 IC 最强的因子，-0.180）
  3. 要趋势与资金：正动量 + 资金净流入（趋势是方向，资金是确认）

大师分 = 0.40*(-pos60归一) + 0.25*(-atr归一) + 0.20*(mom20归一) + 0.15*(flow3归一)
分别检验：① 只用它排序 ② 只用它做硬过滤 ③ 过滤+排序
"""
from __future__ import annotations
import pickle, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache
from factor_ic import factors_at
from rerank import _entry, _next, _sina
from round3_improve import sim
import market_phase_detector as mpd

TOP_N, COOLDOWN, HOLD = 2, 40, 10
W = {"pos60": -0.40, "atr_pct": -0.25, "mom_20": 0.20, "flow3": 0.15}


def zscores(rows, keys):
    out = {}
    for k in keys:
        v = [r[k] for r in rows]
        m = statistics.mean(v); s = statistics.pstdev(v) or 1
        out[k] = ((m, s))
    return out


def main():
    data = pickle.load(open(HERE / "out" / "candidates_oct_year.pkl", "rb"))
    cache = QuoteCache()
    days = sorted(data)
    di = {d: i for i, d in enumerate(days)}

    rows = []
    for d in days:
        for c in data[d]["candidates"]:
            sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
            entry, nd = _entry(cache, sym, d), _next(cache, d)
            if entry is None or nd is None:
                continue
            bars = [{"open": float(x["open"]), "high": float(x["high"]),
                     "low": float(x["low"]), "close": float(x["close"])}
                    for x in cache.forward(sym, nd, HOLD + 2)][:HOLD]
            if len(bars) < HOLD:
                continue
            secs = c.get("sectors") or []
            f = factors_at(cache, sym, d, (mpd.SECTOR_ETFS.get(secs[0] if secs else "") or [None])[0])
            if not f:
                continue
            rows.append({"day": d, "sym": sym, "entry": entry, "bars": bars,
                         "score": c.get("combined_score") or 0,
                         "pos60": f["dist_high_60"], "atr_pct": f["atr_pct"],
                         "mom_20": f["mom_20"], "flow3": f.get("rs_20", 0.0)})
    print(f"候选 {len(rows)} 条")

    # 归一化并合成大师分
    keys = ["pos60", "atr_pct", "mom_20", "flow3"]
    mu = {k: statistics.mean(r[k] for r in rows) for k in keys}
    sd = {k: (statistics.pstdev([r[k] for r in rows]) or 1) for k in keys}
    for r in rows:
        r["master"] = sum(W[k] * ((r[k] - mu[k]) / sd[k]) for k in keys)
    ms = sorted(r["master"] for r in rows)
    thr = {p: ms[int(len(ms) * p)] for p in (0.3, 0.5, 0.7)}
    print("大师分分位阈值:", {k: round(v, 3) for k, v in thr.items()})

    by_day = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)

    def run(order_key, filt=None, label=""):
        cooled, rets, days_used = {}, [], 0
        for d in days:
            pool = [r for r in by_day.get(d, []) if (filt is None or filt(r))]
            if not pool:
                continue
            pool.sort(key=order_key, reverse=True)
            picked = 0
            for r in pool:
                if picked >= TOP_N:
                    break
                last = cooled.get(r["sym"])
                if last is not None and di[d] - di[last] < COOLDOWN:
                    continue
                cooled[r["sym"]] = d
                picked += 1
                rets.append(sim(r["bars"], r["entry"], 0.08, 0.12, None, None, HOLD)[0])
            if picked:
                days_used += 1
        return rets, days_used

    def rep(rets, days_used, label=""):
        if not rets:
            print(f"  {label:<34}  无样本"); return None
        w = [x for x in rets if x > 0]; l = [x for x in rets if x <= 0]
        eq = peak = dd = 0.0
        for x in rets:
            eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
        print(f"  {label:<34}{len(rets):>6}{len(w)/len(rets)*100:>9.1f}%"
              f"{statistics.mean(rets)*100:>+9.2f}%{statistics.median(rets)*100:>+9.2f}%"
              f"{abs(statistics.mean(w)/statistics.mean(l)) if l else 0:>8.2f}{dd*100:>9.1f}")
        return statistics.mean(rets)

    print()
    print("=" * 96)
    print("方案对比（每日取前 2、冷却 40、T+10/-8%/移12%）")
    print("=" * 96)
    print(f"  {'方案':<34}{'笔数':>6}{'胜率':>10}{'均值':>10}{'中位':>10}{'盈亏比':>8}{'回撤':>9}")
    rep(*run(lambda r: r["score"]), label="A. 现状（按 analyzer 分排序）")
    rep(*run(lambda r: r["master"]), label="B. 按大师分排序")
    for p in (0.3, 0.5, 0.7):
        t = thr[p]
        rep(*run(lambda r: r["score"], filt=lambda r, t=t: r["master"] >= t),
            label=f"C{p}. 大师分前 {int((1-p)*100)}% 过滤 + 按原分排序")
    for p in (0.3, 0.5):
        t = thr[p]
        rep(*run(lambda r: r["master"], filt=lambda r, t=t: r["master"] >= t),
            label=f"D{p}. 大师分前 {int((1-p)*100)}% 过滤 + 按大师分排序")


    print()
    print("分半（均值）：")
    half = len(days) // 2
    def half_run(order_key, filt, seg):
        cooled, rets = {}, []
        for d in days[:half] if seg == "tr" else days[half:]:
            pool = [r for r in by_day.get(d, []) if (filt is None or filt(r))]
            if not pool:
                continue
            pool.sort(key=order_key, reverse=True)
            picked = 0
            for r in pool:
                if picked >= TOP_N:
                    break
                last = cooled.get(r["sym"])
                if last is not None and di[d] - di[last] < COOLDOWN:
                    continue
                cooled[r["sym"]] = d
                picked += 1
                rets.append(sim(r["bars"], r["entry"], 0.08, 0.12, None, None, HOLD)[0])
        return rets

    t50 = thr[0.5]
    for lbl, k, fl in (("A. 现状", lambda r: r["score"], None),
                       ("B. 大师分", lambda r: r["master"], None),
                       ("C50. 过滤50%+原分", lambda r: r["score"], lambda r: r["master"] >= t50)):
        a = half_run(k, fl, "tr"); b = half_run(k, fl, "te")
        sa = statistics.mean(a) * 100 if a else 0
        sb = statistics.mean(b) * 100 if b else 0
        print(f"  {lbl:<26}训练 {sa:>+7.2f}% ({len(a):>3} 笔)   测试 {sb:>+7.2f}% ({len(b):>3} 笔)")


if __name__ == "__main__":
    main()
