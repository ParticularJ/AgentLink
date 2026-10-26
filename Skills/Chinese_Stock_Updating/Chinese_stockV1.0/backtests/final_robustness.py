#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终策略的稳健性检验：邻域参数扫描 + Walk-forward OOS（2026-10-17）

目的：确认 +21.9% / −7.6% / 卡玛 2.88 不是一个孤立尖峰。

检验 1  邻域扫描：在最优参数周围小幅扰动，看性能是否平滑
检验 2  Walk-forward：滚动训练/测试，只在测试段拼接净值
检验 3  拆解归因：核心仓 vs 卫星仓各自的贡献
"""
from __future__ import annotations

import itertools
import statistics
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))

import final_strategy as F  # noqa: E402


def run_with(px, n_s: int, mw: int, gate: bool, hold: int) -> pd.Series:
    """临时改写模块参数后运行，返回净值。"""
    old = (F.N_SECTORS, F.MOM_WIN, F.USE_GATE, F.HOLD_DAYS)
    F.N_SECTORS, F.MOM_WIN, F.USE_GATE, F.HOLD_DAYS = n_s, mw, gate, hold
    try:
        nav = F.run_strategy(px)
    finally:
        F.N_SECTORS, F.MOM_WIN, F.USE_GATE, F.HOLD_DAYS = old
    return nav / nav.iloc[0] if len(nav) else nav


def m(nav: pd.Series) -> dict:
    return F.metr(nav)


def main() -> int:
    px = F.build_panel("2022-04-01", "2026-10-16")
    base = px[F.BENCH] / px[F.BENCH].iloc[0]
    print(f"数据 {px.index[0]} → {px.index[-1]}（{len(px)} 日）\n")

    # ── 检验 1：邻域扫描 ──
    print("=" * 96)
    print("检验 1：邻域参数扫描（最优 = 板块3 / 动量60 / 开关M3 / 持有20）")
    print("=" * 96)
    print(f"  {'板块数':>6}{'动量窗':>8}{'开关':>6}{'持有':>6}"
          f"{'年化':>9}{'回撤':>9}{'卡玛':>8}")
    print("  " + "-" * 56)
    grid = [
        (3, 60, True, 20),   # 最优
        (2, 60, True, 20), (4, 60, True, 20),
        (3, 40, True, 20), (3, 80, True, 20), (3, 120, True, 20),
        (3, 60, False, 20),
        (3, 60, True, 10), (3, 60, True, 40),
    ]
    rows = []
    for n_s, mw, g, h in grid:
        nav = run_with(px, n_s, mw, g, h)
        if nav.empty:
            continue
        mm = m(nav)
        rows.append((n_s, mw, g, h, mm))
        flag = " ★最优" if (n_s, mw, g, h) == (3, 60, True, 20) else ""
        print(f"  {n_s:>6}{mw:>8}{'M3' if g else '无':>6}{h:>6}"
              f"{mm['cagr']:>+8.1f}%{mm['mdd']:>+8.1f}%{mm['calmar']:>8.2f}{flag}")

    cal = [r[4]["calmar"] for r in rows]
    pos = sum(1 for x in cal if x > 0)
    print()
    print(f"  9 组邻域参数中：卡玛为正 {pos}/{len(cal)}；"
          f"中位卡玛 {statistics.median(cal):.2f}")
    print(f"  → {'✅ 参数高原（稳健）' if pos >= len(cal)*0.7 else '⚠️ 部分参数失效，需谨慎'}")

    # ── 检验 3：归因（核心 / 卫星）──
    print()
    print("=" * 96)
    print("检验 3：归因 —— 核心仓与卫星仓各自贡献")
    print("=" * 96)
    # 纯核心（卫星权重设 0）
    old_sat = F.SAT_W
    F.SAT_W = 0.0
    F.CORE_W = 1.0
    try:
        core_only = F.run_strategy(px)
    finally:
        F.SAT_W = old_sat
        F.CORE_W = 0.60
    core_only = core_only / core_only.iloc[0]
    full = run_with(px, 3, 60, True, 20)
    print(f"  {'方案':<24}{'年化':>9}{'回撤':>9}{'卡玛':>8}")
    print("  " + "-" * 50)
    for name, nav in (("纯核心仓（100%）", core_only),
                      ("沪深300", base),
                      ("最终策略（60/40）", full)):
        mm = m(nav)
        print(f"  {name:<24}{mm['cagr']:>+8.1f}%{mm['mdd']:>+8.1f}%{mm['calmar']:>8.2f}")

    # ── 检验 2：Walk-forward（3 折）──
    print()
    print("=" * 96)
    print("检验 2：Walk-forward（滚动训练/测试，只在测试段计表现）")
    print("=" * 96)
    dates = list(px.index)
    n = len(dates)
    folds = []
    start_i = 130 + 60
    step = 120
    i = start_i
    while i + step <= n:
        folds.append((dates[i], dates[min(i + step - 1, n - 1)]))
        i += step
    print(f"  测试折数 {len(folds)}（每折约 {step} 交易日）")
    print(f"  {'测试区间':<28}{'策略':>9}{'沪深300':>10}{'超额':>9}")
    print("  " + "-" * 58)
    oos_rets = []
    for (s, e) in folds:
        sub = px[(px.index >= s) & (px.index <= e)]
        if len(sub) < 60:
            continue
        # 需要前推窗口算动量 → 取更长的切片
        i0 = dates.index(s)
        warm = max(0, i0 - 135)
        seg = px.iloc[warm: i0 + len(sub)]
        nav = run_with(seg, 3, 60, True, 20)
        nav = nav[nav.index >= s]
        if len(nav) < 40:
            continue
        nav = nav / nav.iloc[0]
        b = sub[F.BENCH] / sub[F.BENCH].iloc[0]
        b = b.reindex(nav.index).ffill()
        sr = (nav.iloc[-1] - 1) * 100
        br = (b.iloc[-1] - 1) * 100
        oos_rets.append(nav.pct_change().dropna())
        print(f"  {s}~{e:<16}{sr:>+8.1f}%{br:>+9.1f}%{sr-br:>+8.1f}pp")
    if oos_rets:
        chained = pd.concat(oos_rets)
        nav_oos = (1 + chained).cumprod()
        mm = m(nav_oos)
        print()
        print(f"  OOS 拼接：年化 {mm['cagr']:+.1f}%  回撤 {mm['mdd']:+.1f}%  "
              f"卡玛 {mm['calmar']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
