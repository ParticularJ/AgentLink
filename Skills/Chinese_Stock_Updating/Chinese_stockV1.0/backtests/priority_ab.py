#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案B：止损引擎逐条 A/B（以盈亏平衡胜率的安全边际判定）。"""
from __future__ import annotations
import pickle, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
from backtest_september import QuoteCache
from rerank import _entry, _next, _sina

TOP_N, COOLDOWN, HOLD = 2, 40, 10
STOP, TRAIL = 0.08, 0.12


def ma(closes, n, i):
    if i + 1 < n:
        return None
    return sum(closes[i + 1 - n:i + 1]) / n


def simulate(bars, entry, use_p2=False, use_p7=False, use_p8=False,
             use_p9=False, ts_days=10, ts_min=0.05, closes=None):
    """返回该笔的收益率（含半仓分次卖出的加权）。"""
    shares = 1.0
    realized = 0.0
    peak = entry
    half_done = False
    for i, b in enumerate(bars[:HOLD]):
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        # P2：绝对亏损减半（-4% 减半）
        if use_p2 and not half_done and l <= entry * 0.96:
            px = min(o, entry * 0.96) if o <= entry * 0.96 else entry * 0.96
            realized += 0.5 * (px / entry - 1); shares -= 0.5; half_done = True
        # P7：本金模式 MA5 跌破 → 减半
        if use_p7 and not half_done and closes is not None:
            m5 = ma(closes, 5, i)
            if m5 and c < m5:
                realized += 0.5 * (c / entry - 1); shares -= 0.5; half_done = True
        # P8：本金模式 MA10 跌破 → 清仓
        if use_p8 and closes is not None:
            m10 = ma(closes, 10, i)
            if m10 and c < m10:
                realized += shares * (c / entry - 1)
                return realized
        # 生产出场：-8% 硬止损
        sp = entry * (1 - STOP)
        if TRAIL:
            sp = max(sp, peak * (1 - TRAIL))
        if o <= sp:
            realized += shares * (o / entry - 1); return realized
        if l <= sp:
            realized += shares * (sp / entry - 1); return realized
        peak = max(peak, h)
    # P9：时间止损
    last = bars[min(HOLD, len(bars)) - 1]["close"]
    if use_p9 and shares > 0:
        prof = last / entry - 1
        if prof < ts_min:
            realized += shares * prof
            return realized
    realized += shares * (last / entry - 1)
    return realized


def metrics(rs):
    w = [x for x in rs if x > 0]; l = [x for x in rs if x <= 0]
    if not w or not l:
        return None
    pl = statistics.mean(w) / abs(statistics.mean(l))
    win = len(w) / len(rs); be = 1 / (1 + pl)
    eq = peak = dd = 0.0
    for x in rs:
        eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
    return dict(n=len(rs), win=win*100, pl=pl, be=be*100, margin=(win-be)*100,
                avg=statistics.mean(rs)*100, dd=dd*100)


def show(m, label):
    if not m:
        print(f"  {label:<30}  样本不足"); return
    print(f"  {label:<30}{m['n']:>5}{m['win']:>9.1f}%{m['pl']:>8.2f}{m['be']:>12.1f}%"
          f"{m['margin']:>+11.1f}pp  均值{m['avg']:>+7.2f}%  回撤{m['dd']:>8.1f}")


def main():
    data = pickle.load(open(HERE / "out" / "candidates_oct_year.pkl", "rb"))
    cache = QuoteCache()
    days = sorted(data); di = {d: i for i, d in enumerate(days)}
    trades, cooled = [], {}
    for d in days:
        mkt = data[d]["market"]
        if mkt not in ("RANGE", "WAVE_UP", "STRONG_UP"):
            continue
        pool = []
        for c in data[d]["candidates"]:
            sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
            e, nd = _entry(cache, sym, d), _next(cache, d)
            if e is None or nd is None: continue
            bars = [{"open": float(x["open"]), "high": float(x["high"]),
                     "low": float(x["low"]), "close": float(x["close"])}
                    for x in cache.forward(sym, nd, HOLD + 2)][:HOLD]
            if len(bars) < HOLD: continue
            pool.append((c.get("combined_score", 0), sym, e, bars))
        pool.sort(key=lambda x: -x[0]); got = 0
        for sc, sym, e, bars in pool:
            if got >= TOP_N: break
            last = cooled.get(sym)
            if last is not None and di[d] - di[last] < COOLDOWN: continue
            cooled[sym] = d; got += 1
            closes = [b["close"] for b in bars]
            trades.append({"bars": bars, "entry": e, "closes": closes, "day": d})
    print(f"样本 {len(trades)} 笔（大盘开关 + 每日前2 + 冷却40）")
    print()
    print("=" * 104)
    print("逐条增量规则的 A/B（基线 = -8%止损 / 回落12% / T+10）")
    print("=" * 104)
    print(f"  {'变体':<30}{'笔数':>5}{'胜率':>10}{'盈亏比':>8}{'盈亏平衡胜率':>13}{'安全边际':>12}")
    variants = [
        ("基线（生产）", {}),
        ("+P2 绝对亏损减半(-4%)", {"use_p2": True}),
        ("+P7 本金模式MA5跌破减半", {"use_p7": True}),
        ("+P8 本金模式MA10跌破清仓", {"use_p8": True}),
        ("+P9 时间止损", {"use_p9": True}),
    ]
    for label, kw in variants:
        rs = [simulate(t["bars"], t["entry"], closes=t["closes"], **kw) for t in trades]
        show(metrics(rs), label)
    print()
    print("分半（安全边际）：")
    half = len(trades) // 2
    for label, kw in variants:
        a = metrics([simulate(t["bars"], t["entry"], closes=t["closes"], **kw) for t in trades[:half]])
        b = metrics([simulate(t["bars"], t["entry"], closes=t["closes"], **kw) for t in trades[half:]])
        if a and b:
            print(f"  {label:<30}训练 {a['margin']:>+7.1f}pp    测试 {b['margin']:>+7.1f}pp")


if __name__ == "__main__":
    main()
