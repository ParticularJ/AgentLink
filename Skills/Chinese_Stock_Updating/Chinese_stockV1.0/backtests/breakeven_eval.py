#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
以「盈亏平衡胜率」为核心指标评估回测结果。

盈亏平衡胜率 = 1 / (1 + 盈亏比)
  盈亏比 = 平均盈利 / |平均亏损|
安全边际 = 实际胜率 - 盈亏平衡胜率（>0 才是有正期望的策略）

为什么用这个而不是单看胜率或单看盈亏比：
  两者此消彼长，单独优化任一个都会得出相反结论；
  盈亏平衡胜率把两者合成一个可比较的量，直接回答"这笔生意划不划算"。
"""
from __future__ import annotations
import csv, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def metrics(rows, label):
    if not rows:
        return None
    rs = [float(r["ret"]) for r in rows]
    w = [x for x in rs if x > 0]
    l = [x for x in rs if x <= 0]
    if not w or not l:
        return None
    aw, al = statistics.mean(w), abs(statistics.mean(l))
    pl = aw / al
    be = 1.0 / (1.0 + pl)
    win = len(w) / len(rs)
    eq = peak = dd = 0.0
    for x in rs:
        eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
    return dict(label=label, n=len(rs), win=win * 100, pl=pl, be=be * 100,
                margin=(win - be) * 100, avg=statistics.mean(rs) * 100,
                med=statistics.median(rs) * 100, dd=dd * 100,
                exp_per_risk=(statistics.mean(rs) / al) if al else 0)


def show(m, indent="  "):
    if not m:
        print(f"{indent}（样本不足）")
        return
    flag = "✅" if m["margin"] > 0 else "❌"
    print(f"{indent}{m['label']:<26}{m['n']:>5}{m['win']:>9.1f}%{m['pl']:>8.2f}"
          f"{m['be']:>12.1f}%{m['margin']:>+11.1f}pp  {flag}  "
          f"均值{m['avg']:>+7.2f}%  回撤{m['dd']:>7.1f}")


def main():
    files = sys.argv[1:] or [
        "backtests/out/trades_gated_mktswitch_top2_cd40_2025-09-30_2026-09-30.csv"]
    print("=" * 108)
    print("以盈亏平衡胜率为核心指标")
    print("=" * 108)
    print(f"  {'方案':<26}{'笔数':>5}{'胜率':>10}{'盈亏比':>8}{'盈亏平衡胜率':>13}"
          f"{'安全边际':>12}      均值      回撤")
    for path in files:
        p = Path(path)
        if not p.exists():
            print(f"  {p.name}: 文件不存在")
            continue
        rows = [r for r in csv.DictReader(open(p, encoding="utf-8")) if r["variant"] == "fixed"]
        if not rows:
            continue
        show(metrics(rows, p.stem[:26]))
        tr = [r for r in rows if r["signal_date"] < "2026-04-01"]
        te = [r for r in rows if r["signal_date"] >= "2026-04-01"]
        show(metrics(tr, "  └ 训练段"), "    ")
        show(metrics(te, "  └ 测试段"), "    ")
        print()


if __name__ == "__main__":
    main()
