#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""信号去重（冷却期）实验：同一标的在 N 个交易日内只接受第一次信号。

动机：707 笔信号里有 625 笔是「重复推荐」，首次推荐均值 +3.97%，
重复推荐只有 +1.69%。重复信号既稀释统计显著性，也可能是在追同一个已经
走完的行情。
"""
from __future__ import annotations
import csv, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
from backtest_september import QuoteCache
from optimize_exit import Rule, simulate

PROD = Rule(10, 0.08, 0.0, 0.12)
BASE = Rule(5, 0.05)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "backtests/out/trades_september_gated_T5.csv"
    cache = QuoteCache()
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["variant"] != "fixed":
            continue
        fwd = cache.forward(r["symbol"], r["entry_date"], 20)
        if len(fwd) < 20:
            continue
        bars = [{"open": float(x["open"]), "high": float(x["high"]),
                 "low": float(x["low"]), "close": float(x["close"])} for x in fwd]
        rows.append({"code": r["symbol"], "date": r["signal_date"], "entry": float(r["entry_price"]),
                     "bars": bars, "score": float(r["score"])})
    rows.sort(key=lambda z: (z["code"], z["date"]))
    dates = sorted({r["date"] for r in rows})
    di = {d: i for i, d in enumerate(dates)}

    def ev(rule, cooldown, subset=None):
        last = {}
        rets = []
        for r in rows:
            if subset is not None and not subset(r["date"]):
                continue
            i = di[r["date"]]
            if r["code"] in last and i - last[r["code"]] < cooldown:
                continue
            last[r["code"]] = i
            ret, _, _ = simulate(r["bars"], r["entry"], rule)
            rets.append(ret)
        w = [x for x in rets if x > 0]
        eq = peak = dd = 0.0
        for x in rets:
            eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
        return (len(rets), len(w) / len(rets) * 100, statistics.mean(rets) * 100,
                statistics.median(rets) * 100, dd * 100)

    print("=" * 86)
    print("冷却期（同一标的 N 个交易日内只取首次信号）")
    print("=" * 86)
    print(f"  {'冷却期':<12}{'出场':<20}{'笔数':>7}{'胜率':>9}{'均值':>10}{'中位':>10}{'回撤':>10}")
    for cd in (0, 3, 5, 10, 20, 40, 9999):
        for rule, rn in ((BASE, "T+5/-5%(现状)"), (PROD, "T+10/-8%/移12%(生产)")):
            n, wr, avg, med, dd = ev(rule, cd)
            lab = "不去重" if cd == 0 else ("每个标的只买一次" if cd == 9999 else f"{cd} 日")
            print(f"  {lab:<12}{rn:<20}{n:>7}{wr:>8.1f}%{avg:>+9.2f}%{med:>+9.2f}%{dd:>10.1f}")
        print()

    print()
    print("=" * 86)
    print("分半验证（生产出场，检查冷却期是否在样本外同样有效）")
    print("=" * 86)
    print(f"  {'冷却期':<12}{'训练笔数':>9}{'训练均值':>10}{'测试笔数':>9}{'测试均值':>10}")
    for cd in (0, 5, 10, 20, 40):
        a = ev(PROD, cd, lambda d: d < "2026-04-01")
        b = ev(PROD, cd, lambda d: d >= "2026-04-01")
        print(f"  {(str(cd) + ' 日'):<12}{a[0]:>9}{a[2]:>+9.2f}%{b[0]:>9}{b[2]:>+9.2f}%")


if __name__ == "__main__":
    main()
