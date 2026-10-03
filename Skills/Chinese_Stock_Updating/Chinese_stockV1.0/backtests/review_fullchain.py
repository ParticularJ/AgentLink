#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全链路整体回测（正式版）：当前生产配置 + 训练/测试分半。

配置：DAILY_TOP_N=2、信号冷却 40 个运行日（不回填）、大盘交易开关、
      出场 T+10 / -8% 硬止损 / 自最高点回落 12% / 不设固定止盈、次日跳空 >5% 放弃。
"""
from __future__ import annotations
import csv, statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
P = HERE / "out" / "trades_gated_mktswitch_top2_cd40_2025-09-30_2026-09-30.csv"


def rep(rows, label):
    if not rows:
        print(f"  {label:<22}  无样本")
        return
    rs = [float(r["ret"]) for r in rows]
    w = [x for x in rs if x > 0]
    l = [x for x in rs if x <= 0]
    eq = peak = dd = 0.0
    for x in rs:
        eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
    stop = sum(1 for r in rows if r["reason"].startswith("stop")) / len(rows) * 100
    print(f"  {label:<22}{len(rs):>5}{len(w)/len(rs)*100:>9.1f}%{statistics.mean(rs)*100:>+9.2f}%"
          f"{statistics.median(rs)*100:>+9.2f}%"
          f"{abs(statistics.mean(w)/statistics.mean(l)) if l else 0:>8.2f}"
          f"{dd*100:>9.1f}{stop:>9.0f}%")


def main():
    rows = [r for r in csv.DictReader(open(P, encoding="utf-8")) if r["variant"] == "fixed"]
    print(f"全链路整体回测（{P.name}）")
    print(f"区间 {min(r['signal_date'] for r in rows)} ~ {max(r['signal_date'] for r in rows)}")
    print()
    print("=" * 92)
    print(f"  {'口径':<22}{'笔数':>5}{'胜率':>10}{'均值':>10}{'中位':>10}{'盈亏比':>8}{'回撤':>9}{'止损率':>10}")
    print("=" * 92)
    rep(rows, "全样本")
    rep([r for r in rows if r["signal_date"] < "2026-04-01"], "训练段(<2026-04)")
    rep([r for r in rows if r["signal_date"] >= "2026-04-01"], "测试段(>=2026-04)")
    print()
    print("分季度：")
    for q, (a, b) in enumerate([("2025-09-30", "2025-12-31"), ("2026-01-01", "2026-03-31"),
                                ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30")], 1):
        rep([r for r in rows if a <= r["signal_date"] <= b], f"  Q{q} {a[:7]}")
    print()
    print("分标的类型（按来源策略名）：")
    rep([r for r in rows if "ETF" in r["strategy"]], "  板块 ETF 路径")
    rep([r for r in rows if "ETF" not in r["strategy"]], "  个股策略路径")


if __name__ == "__main__":
    main()
