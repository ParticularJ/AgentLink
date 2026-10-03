#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求5 回测：按大盘 phase 动态调整的止盈止损，是否优于固定参数？

现状（固定）：-8% 止损 + 自最高点回落 12%，无止盈，T+10
动态（需求5）：按大盘 phase 取 stop/trail/breakeven
    STRONG_UP 10%/15%/保本10%   WAVE_UP 9%/12%/保本8%
    RANGE     8%/10%/保本6%     STRONG_DOWN 5%/6%/保本3%
动态规则含**保本**：持仓期最高浮盈达阈值后，止损抬到成本之上。
"""
from __future__ import annotations
import pickle, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
sys.path.insert(0, str(REPO / "Medium-termHoldingStrategy" / "skills" / "scripts"))
from backtest_september import QuoteCache
from rerank import _entry, _next, _sina
from daily_stop_plan import plan_for_phase

TOP_N, COOLDOWN, HOLD = 2, 40, 10
BREAKEVEN_BUFFER = 0.002


def sim_dyn(bars, entry, stop, trail, breakeven_at, hold=HOLD):
    """支持保本的出场模拟：曾达保本线后止损抬到成本之上。"""
    peak, armed = entry, False
    for i, b in enumerate(bars[:hold]):
        if (peak / entry - 1) >= breakeven_at:
            armed = True
        sp = entry * (1 - stop)
        if armed:
            sp = max(sp, entry * (1 + BREAKEVEN_BUFFER))
        if trail:
            sp = max(sp, peak * (1 - trail))
        o, h, l = b["open"], b["high"], b["low"]
        if o <= sp:
            return o / entry - 1
        if l <= sp:
            return sp / entry - 1
        peak = max(peak, h)
    return bars[min(hold, len(bars)) - 1]["close"] / entry - 1


def rep(rs, label):
    w = [x for x in rs if x > 0]
    l = [x for x in rs if x <= 0]
    eq = peak = dd = 0.0
    for x in rs:
        eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
    print(f"  {label:<30}{len(rs):>6}{len(w)/len(rs)*100:>9.1f}%{statistics.mean(rs)*100:>+10.2f}%"
          f"{statistics.median(rs)*100:>+10.2f}%"
          f"{abs(statistics.mean(w)/statistics.mean(l)) if l else 0:>9.2f}{dd*100:>10.1f}")
    return statistics.mean(rs)


def main():
    data = pickle.load(open(HERE / "out" / "candidates_oct_year.pkl", "rb"))
    cache = QuoteCache()
    import fusion_config as fc
    days = sorted(data)
    di = {d: i for i, d in enumerate(days)}

    trades = []
    cooled = {}
    for d in days:
        mkt = data[d]["market"]
        if fc.MARKET_TRADE_SWITCH.get(mkt, "off") == "off":
            continue
        pool = []
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
            pool.append((c.get("combined_score", 0), sym, entry, bars))
        pool.sort(key=lambda x: -x[0])
        got = 0
        for sc, sym, entry, bars in pool:
            if got >= TOP_N:
                break
            last = cooled.get(sym)
            if last is not None and di[d] - di[last] < COOLDOWN:
                continue
            cooled[sym] = d
            got += 1
            trades.append({"date": d, "phase": mkt, "entry": entry, "bars": bars})

    print(f"样本 {len(trades)} 笔（已应用大盘交易开关，只在 RANGE/WAVE_UP/STRONG_UP 开仓）")
    from collections import Counter
    print("  入场时大盘 phase 分布:", dict(Counter(t["phase"] for t in trades)))
    print()
    print("=" * 96)
    print("固定止盈止损 vs 按 phase 动态调整")
    print("=" * 96)
    print(f"  {'方案':<30}{'笔数':>6}{'胜率':>10}{'均值':>11}{'中位':>11}{'盈亏比':>9}{'回撤':>10}")

    fixed = [sim_dyn(t["bars"], t["entry"], 0.08, 0.12, 9.9) for t in trades]
    dyn = []
    for t in trades:
        p = plan_for_phase(t["phase"])
        dyn.append(sim_dyn(t["bars"], t["entry"], p["stop"], p["trail"], p["breakeven_at"]))
    a = rep(fixed, "固定 -8%/移12%/无止盈")
    b = rep(dyn, "动态（按 phase + 保本）")

    print()
    # 只动止损、只动回落、只加保本 —— 看是哪一项起作用
    print("单项拆解（相对固定参数）：")
    for label, kw in (
        ("只按 phase 调止损", dict(stop_by_phase=True, trail=None, be=None)),
        ("只按 phase 调回落", dict(stop_by_phase=False, trail=1, be=None)),
        ("只加保本（固定 8%/12%）", dict(stop_by_phase=False, trail=None, be=1)),
        ("三项全开（=动态）", dict(stop_by_phase=True, trail=1, be=1)),
    ):
        rs = []
        for t in trades:
            p = plan_for_phase(t["phase"])
            stop = p["stop"] if kw["stop_by_phase"] else 0.08
            trail = p["trail"] if kw["trail"] else 0.12
            be = p["breakeven_at"] if kw["be"] else 9.9
            rs.append(sim_dyn(t["bars"], t["entry"], stop, trail, be))
        rep(rs, label)

    print()
    print("分半稳健性（均值）：")
    half = len(trades) // 2
    for label, fn in (("固定", lambda t: sim_dyn(t["bars"], t["entry"], 0.08, 0.12, 9.9)),
                      ("动态", lambda t: (lambda p: sim_dyn(t["bars"], t["entry"], p["stop"], p["trail"], p["breakeven_at"]))(plan_for_phase(t["phase"])))):
        f = [fn(t) for t in trades[:half]]
        s = [fn(t) for t in trades[half:]]
        print(f"  {label:<8}{statistics.mean(f)*100:>+10.2f}%{statistics.mean(s)*100:>+10.2f}%")
    print()
    print(f"  结论：动态 {b:+.2f}%  vs  固定 {a:+.2f}%  →  "
          f"{'动态更优' if b > a else '固定更优，动态规则应调整或不启用'}")


if __name__ == "__main__":
    main()
