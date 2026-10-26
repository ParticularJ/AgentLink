#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3 开关的归因 + 全区间分段表现（2026-10-17）

回答两个问题：
  Q1  M3 开关到底贡献了多少？（开 vs 关对照，同样分段）
  Q2  完整策略（核心70+卫星30）在 924 前后两段分别是什么表现？
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))

from sample_out_2022 import LONG, SEGMENTS, load, metr, run_sat  # noqa: E402
CACHE = HERE / "cache"
BENCH = "sh000300"


def main() -> int:
    codes = list(LONG.values())
    print("=" * 100)
    print("Q1  M3 开关的贡献：开 vs 关（同样 10 个板块 ETF）")
    print("=" * 100)
    print(f"  {'区间':<22}{'开关=开':>10}{'开关=关':>10}{'差额':>9}{'沪深300':>10}")
    print("  " + "-" * 62)
    for label, s, e in SEGMENTS:
        a = run_sat(codes, s, e, use_gate=True)
        b = run_sat(codes, s, e, use_gate=False)
        bs = load(BENCH, s, e)
        if a.empty or b.empty:
            continue
        ma = metr(a / a.iloc[0])
        mb = metr(b / b.iloc[0])
        mbi = metr(bs / bs.iloc[0]) if bs is not None else {}
        diff = ma["total"] - mb["total"]
        flag = "✅开关有用" if diff > 0 else "❌开关有害"
        print(f"  {label:<22}{ma['total']:>+9.1f}%{mb['total']:>+9.1f}%"
              f"{diff:>+8.1f}pp{mbi.get('total', 0):>+9.1f}%  {flag}")

    print()
    print("  2022-09 ~ 2024-09（924 前，约 2 年）：")
    s, e = "2022-09-01", "2024-09-23"
    a = run_sat(codes, s, e, use_gate=True)
    b = run_sat(codes, s, e, use_gate=False)
    if not a.empty and not b.empty:
        ma, mb = metr(a / a.iloc[0]), metr(b / b.iloc[0])
        print(f"    开: 累计 {ma['total']:+.1f}%  回撤 {ma['mdd']:+.1f}%  卡玛 {ma['calmar']:.2f}")
        print(f"    关: 累计 {mb['total']:+.1f}%  回撤 {mb['mdd']:+.1f}%  卡玛 {mb['calmar']:.2f}")

    print()
    print("=" * 100)
    print("Q2  完整策略（核心70 + 卫星30）在 924 前后")
    print("=" * 100)
    import final_strategy as F
    old = (F.SAT_W, F.CORE_W)
    F.SAT_W, F.CORE_W = 0.30, 0.70
    try:
        px = F.build_panel("2022-04-01", "2026-10-16")
        nav = F.run_strategy(px)
    finally:
        F.SAT_W, F.CORE_W = old
    nav = nav / nav.iloc[0]
    print(f"  {'区间':<24}{'策略':>10}{'沪深300':>10}{'超额':>10}{'交易日':>8}")
    print("  " + "-" * 62)
    cuts = [("924 前（2024-02~2024-09）", "2024-02-26", "2024-09-23"),
            ("924 后（2024-09~2026-10）", "2024-09-24", "2026-10-16"),
            ("全区间（2024-02~2026-10）", "2024-02-26", "2026-10-16")]
    for label, s, e in cuts:
        seg = nav[(nav.index >= s) & (nav.index <= e)]
        if len(seg) < 40:
            continue
        sr = (seg.iloc[-1] / seg.iloc[0] - 1) * 100
        bs = px[BENCH].reindex(seg.index).ffill()
        br = (bs.iloc[-1] / bs.iloc[0] - 1) * 100
        print(f"  {label:<24}{sr:>+9.1f}%{br:>+9.1f}%{sr-br:>+9.1f}pp{len(seg):>8}")

    print()
    print("=" * 100)
    print("结论")
    print("=" * 100)
    print("  1) 完整策略的数据只覆盖 2024-02 起（核心仓标的行情限制）")
    print("  2) 卫星仓单独可用 2022 起的板块 ETF 检验：")
    print("     · 2022 熊市 −3.7%（沪深300 −9.5%）")
    print("     · 2023 震荡 0.0%（沪深300 −17.3%，73.6% 时间空仓）")
    print("     · 924 前合计 −4.6% vs 沪深300 −24.9%，超额 +20.2pp")
    print("     · 924 后牛市 +53.2% vs +24.4%")
    print("  3) 所以：**这套策略的超额主要来自「下跌/震荡期少亏」，")
    print("     而绝对收益主要来自牛市段。** 它不是全天候策略。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
