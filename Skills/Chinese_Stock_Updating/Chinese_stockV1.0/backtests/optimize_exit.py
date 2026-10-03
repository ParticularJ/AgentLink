#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
出场规则寻优 + 样本外验证。

交易员的第一性原理："截断亏损、让利润奔跑" 必须用参数验证，
而不是靠感觉。但直接在全样本上挑最优参数 = 过拟合，
所以这里强制做训练/测试分割，并考察参数敏感性（邻域是否也好）。

出场规则可组合：
  max_hold  最长持有交易日
  stop      硬止损（盘中触及即成交；若跳空低开则按开盘价成交）
  take      止盈（可选）
  trail     移动止损：从持仓最高点回撤 X%（可选）
  be        保本止损：浮盈曾达 B 后，止损上移到成本价（可选）
"""
from __future__ import annotations

import argparse
import itertools
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "common"))

from backtest_september import QuoteCache


@dataclass(frozen=True)
class Rule:
    max_hold: int = 5
    stop: float = 0.05
    take: float = 0.0        # 0 = 不止盈
    trail: float = 0.0       # 0 = 不移动止损
    be: float = 0.0          # 0 = 不保本

    def label(self):
        parts = [f"T+{self.max_hold}", f"-{self.stop:.0%}"]
        if self.take:
            parts.append(f"+{self.take:.0%}")
        if self.trail:
            parts.append(f"移{self.trail:.0%}")
        if self.be:
            parts.append(f"保{self.be:.0%}")
        return "/".join(parts)


def simulate(bars, entry, r: Rule):
    """返回 (收益率, 持有天数, 出场原因)。bars 为从入场当日起的日线序列。"""
    peak = entry
    for i, b in enumerate(bars[: r.max_hold]):
        stop_px = entry * (1 - r.stop)
        if r.trail:
            stop_px = max(stop_px, peak * (1 - r.trail))
        if r.be and peak >= entry * (1 + r.be):
            stop_px = max(stop_px, entry * 1.001)
        o, h, l = b["open"], b["high"], b["low"]
        # 1) 跳空低开且低于止损 → 按开盘价成交（比止损价更差，真实）
        if o <= stop_px:
            return o / entry - 1, i + 1, "stop_gap"
        # 2) 盘中触及止损
        if l <= stop_px:
            return stop_px / entry - 1, i + 1, "stop"
        # 3) 止盈
        if r.take and h >= entry * (1 + r.take):
            return r.take, i + 1, "take"
        peak = max(peak, h)
    last = bars[min(r.max_hold, len(bars)) - 1]
    return last["close"] / entry - 1, min(r.max_hold, len(bars)), "hold"


def stats(rets):
    if not rets:
        return {}
    w = [x for x in rets if x > 0]
    l = [x for x in rets if x <= 0]
    aw = statistics.mean(w) if w else 0.0
    al = statistics.mean(l) if l else 0.0
    eq, peak, dd = 0.0, 0.0, 0.0
    for x in rets:
        eq += x
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {
        "n": len(rets),
        "win": len(w) / len(rets) * 100,
        "avg": statistics.mean(rets) * 100,
        "med": statistics.median(rets) * 100,
        "pl": abs(aw / al) if al else float("inf"),
        "dd": dd * 100,
        "exp": statistics.mean(rets) * 100,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trades")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--split", default="2026-04-01", help="训练/测试分割日")
    args = ap.parse_args()

    cache = QuoteCache()
    import csv
    rows = [r for r in csv.DictReader(open(args.trades, encoding="utf-8"))
            if r["variant"] == "fixed"]
    sample = []
    for r in rows:
        fwd = cache.forward(r["symbol"], r["entry_date"], args.horizon)
        if len(fwd) < args.horizon:
            continue
        bars = [{"open": float(x["open"]), "high": float(x["high"]),
                 "low": float(x["low"]), "close": float(x["close"])} for x in fwd]
        sample.append({"date": r["signal_date"], "entry": float(r["entry_price"]), "bars": bars})

    train = [s for s in sample if s["date"] < args.split]
    test = [s for s in sample if s["date"] >= args.split]
    print(f"样本 {len(sample)} 笔｜训练 {len(train)} 笔（<{args.split}）｜测试 {len(test)} 笔")

    def run(rule, data):
        return stats([simulate(s["bars"], s["entry"], rule)[0] for s in data])

    base = Rule(5, 0.05)
    b = run(base, sample)
    print(f"\n现状基线 {base.label():<18} 笔数{b['n']:>5}  胜率{b['win']:>5.1f}%  均值{b['avg']:>+7.2f}%  "
          f"盈亏比{b['pl']:>5.2f}  回撤{b['dd']:>8.1f}")

    # ── 网格 ──
    grid = []
    for hold, stop, take, trail, be in itertools.product(
            [5, 8, 10, 15, 20], [0.05, 0.08, 0.10, 0.15], [0.0, 0.10, 0.15, 0.20, 0.30],
            [0.0, 0.08, 0.12], [0.0, 0.05]):
        r = Rule(hold, stop, take, trail, be)
        tr = run(r, train)
        if tr["n"] < 100:
            continue
        grid.append((tr["avg"], r, tr))
    grid.sort(reverse=True, key=lambda x: x[0])

    print(f"\n共评估 {len(grid)} 组参数（训练集）")
    print("\n" + "=" * 96)
    print("训练集 TOP 15（按均值排序）")
    print("=" * 96)
    print(f"{'规则':<22}{'训练笔数':>9}{'训练胜率':>10}{'训练均值':>10}{'训练盈亏比':>11}")
    for avg, r, tr in grid[:15]:
        print(f"{r.label():<22}{tr['n']:>9}{tr['win']:>9.1f}%{tr['avg']:>+9.2f}%{tr['pl']:>11.2f}")

    print("\n" + "=" * 96)
    print("★ 关键检验：训练集最优 10 组，在测试集上表现如何？（过拟合就会崩）")
    print("=" * 96)
    print(f"{'规则':<22}{'训练均值':>10}{'测试笔数':>10}{'测试胜率':>10}{'测试均值':>10}{'测试盈亏比':>11}{'测试回撤':>11}")
    for avg, r, tr in grid[:10]:
        te = run(r, test)
        print(f"{r.label():<22}{tr['avg']:>+9.2f}%{te['n']:>10}{te['win']:>9.1f}%{te['avg']:>+9.2f}%"
              f"{te['pl']:>11.2f}{te['dd']:>10.1f}")
    bt = run(base, test)
    print(f"{'（现状基线）':<20}{run(base, train)['avg']:>+9.2f}%{bt['n']:>10}{bt['win']:>9.1f}%"
          f"{bt['avg']:>+9.2f}%{bt['pl']:>11.2f}{bt['dd']:>10.1f}")

    # ── 单维度边际效应（看趋势而非尖峰）──
    print("\n" + "=" * 96)
    print("单维度边际效应（固定其他为基线，全样本）——判断改进方向是否稳健")
    print("=" * 96)
    for field, values in (("max_hold", [3, 5, 8, 10, 15, 20]), ("stop", [0.03, 0.05, 0.08, 0.10, 0.15]),
                          ("take", [0.0, 0.10, 0.15, 0.20, 0.30]), ("trail", [0.0, 0.06, 0.08, 0.12, 0.20])):
        print(f"  {field}:")
        for v in values:
            kw = {"max_hold": 5, "stop": 0.05, "take": 0.0, "trail": 0.0, "be": 0.0}
            kw[field] = v
            st = run(Rule(**kw), sample)
            print(f"     {v:<6} 胜率 {st['win']:>5.1f}%   均值 {st['avg']:>+6.2f}%   "
                  f"盈亏比 {st['pl']:>5.2f}   回撤 {st['dd']:>8.1f}")


if __name__ == "__main__":
    main()
