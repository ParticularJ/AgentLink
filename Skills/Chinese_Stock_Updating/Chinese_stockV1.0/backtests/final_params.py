#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终参数定型：核心/卫星配比扫描 + 交易级胜率/盈亏比（2026-10-17）

回答用户两个问题所需的最后数据：
  1. 核心仓与卫星仓的最优配比是多少？
  2. 卫星仓的**交易级**胜率与盈亏比是多少（不是月度）？
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))

import final_strategy as F  # noqa: E402


def run_ratio(px, sat_w: float) -> pd.Series:
    old = (F.SAT_W, F.CORE_W)
    F.SAT_W, F.CORE_W = sat_w, 1.0 - sat_w
    try:
        nav = F.run_strategy(px)
    finally:
        F.SAT_W, F.CORE_W = old
    return nav / nav.iloc[0] if len(nav) else nav


def trade_stats(px) -> Dict[str, float]:
    """按"卫星仓每次建仓→平仓"统计交易级胜率/盈亏比。

    平仓条件与 final_strategy.run_strategy **完全一致**：
      · 硬止损 −10%
      · 移动止盈 −15%（自持仓最高点回撤）
      · 再平衡时该板块不再排进前 3 → 剔除
    """
    sec = [c for c in F.SECTOR_ETF.values() if c in px.columns]
    mom = px[sec].pct_change(F.MOM_WIN)
    disp = px[sec].pct_change(20).std(axis=1)
    disp_med = disp.expanding(min_periods=120).median()
    dates = list(px.index)

    # code -> (entry_px, entry_i, peak_px)
    open_pos: Dict[str, Tuple[float, int, float]] = {}
    trades: List[Tuple[str, float]] = []
    last = -10 ** 6

    for i, d in enumerate(dates):
        if i < max(F.MOM_WIN, 140):
            continue
        # 止损 / 移动止盈
        for c in list(open_pos.keys()):
            entry_px, entry_i, peak_px = open_pos[c]
            cur = px[c].iloc[i]
            peak_px = max(peak_px, cur)
            open_pos[c] = (entry_px, entry_i, peak_px)
            ret = cur / entry_px - 1
            if ret <= F.STOP_HARD or (cur / peak_px - 1) <= F.TRAIL:
                trades.append((c, ret))
                del open_pos[c]
        if (i - last) < F.HOLD_DAYS:
            continue
        last = i
        j = i - 1
        gated = bool(F.USE_GATE and disp.iloc[j] == disp.iloc[j]
                     and disp_med.iloc[j] == disp_med.iloc[j]
                     and disp.iloc[j] < disp_med.iloc[j])
        picked: List[str] = []
        if not gated:
            sc = {c: mom[c].iloc[j] for c in sec if mom[c].iloc[j] == mom[c].iloc[j]}
            picked = [c for c, v in sorted(sc.items(), key=lambda kv: -kv[1])[:F.N_SECTORS]
                      if v > 0]
        for c in list(open_pos.keys()):
            if c not in picked:
                trades.append((c, px[c].iloc[i] / open_pos[c][0] - 1))
                del open_pos[c]
        for c in picked:
            if c not in open_pos:
                px0 = px[c].iloc[i]
                open_pos[c] = (px0, i, px0)
    for c, (entry_px, _, peak_px) in open_pos.items():
        trades.append((c, px[c].iloc[-1] / entry_px - 1))
    rets = [r for _, r in trades]
    if not rets:
        return {}
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    aw = statistics.mean(wins) if wins else 0
    al = abs(statistics.mean(losses)) if losses else 0
    return {
        "n": len(rets),
        "win_rate": len(wins) / len(rets) * 100,
        "avg_win": aw * 100,
        "avg_loss": -al * 100,
        "pl_ratio": (aw / al) if al > 0 else float("inf"),
        "expectancy": statistics.mean(rets) * 100,
        "median": statistics.median(rets) * 100,
        "best": max(rets) * 100,
        "worst": min(rets) * 100,
    }


def main() -> int:
    px = F.build_panel("2022-04-01", "2026-10-16")
    print(f"数据 {px.index[0]} → {px.index[-1]}（{len(px)} 日）\n")

    print("=" * 92)
    print("核心/卫星配比扫描")
    print("=" * 92)
    print(f"  {'卫星占比':>8}{'年化':>9}{'回撤':>9}{'卡玛':>8}{'月胜率':>9}"
          f"{'达标月≥1.2%':>13}{'最差月':>9}{'连亏月':>8}")
    print("  " + "-" * 74)
    best = None
    for sw in (0.0, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70):
        nav = run_ratio(px, sw)
        if nav.empty:
            continue
        mm = F.metr(nav)
        flag = ""
        if best is None or mm["calmar"] > best[1]["calmar"]:
            best = (sw, mm)
        if abs(sw - 0.40) < 1e-9:
            flag = " ← 当前采用"
        print(f"  {sw:>7.0%}{mm['cagr']:>+8.1f}%{mm['mdd']:>+8.1f}%{mm['calmar']:>8.2f}"
              f"{mm['月胜率']:>8.1f}%{mm['达标月']:>12.1f}%{mm['最差月']:>+8.1f}%"
              f"{mm['连亏月']:>8}{flag}")
    if best:
        print()
        print(f"  卡玛最优配比：卫星 {best[0]:.0%}（年化 {best[1]['cagr']:+.1f}%，"
              f"回撤 {best[1]['mdd']:+.1f}%，卡玛 {best[1]['calmar']:.2f}）")

    print()
    print("=" * 92)
    print("卫星仓交易级统计（每笔建仓→平仓）")
    print("=" * 92)
    ts = trade_stats(px)
    if ts:
        print(f"  交易笔数        : {ts['n']}")
        print(f"  胜率            : {ts['win_rate']:.1f}%")
        print(f"  平均盈利        : {ts['avg_win']:+.2f}%")
        print(f"  平均亏损        : {ts['avg_loss']:+.2f}%")
        print(f"  **盈亏比**      : {ts['pl_ratio']:.2f}")
        print(f"  单笔期望        : {ts['expectancy']:+.2f}%")
        print(f"  中位数          : {ts['median']:+.2f}%")
        print(f"  最好 / 最差     : {ts['best']:+.1f}% / {ts['worst']:+.1f}%")
        # 盈亏平衡胜率
        if ts["pl_ratio"] not in (0, float("inf")):
            be = 1 / (1 + ts["pl_ratio"]) * 100
            print(f"  盈亏平衡胜率    : {be:.1f}%")
            print(f"  安全边际        : {ts['win_rate']-be:+.1f}pp "
                  f"{'✅ 正期望' if ts['win_rate'] > be else '❌ 负期望'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
