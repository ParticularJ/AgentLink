#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追踪动量轮动的月度状态，找出 -92.6% 回撤的机制。

数据已排除异常（18 只 ETF 单日极值均 ±10% 内），所以是策略问题。
重点怀疑：
  (a) 频繁切换的复合成本（316 次调仓）
  (b) 动量追高 → 买在顶部 → MA200 出场太慢
  (c) 限价/涨跌停导致无法成交的模拟失真（本回测按收盘价成交，乐观）
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from allocation_engine import CACHE, apply_cost  # noqa: E402
from sector_rotation import SECTOR_ETFS, load, momentum, above_ma  # noqa: E402


def trace(px, top_n=2, lookback=120, ma_win=200, rebal=20):
    dates = px.index
    codes = list(px.columns)
    cash = 100_000.0
    units = {c: 0.0 for c in codes}
    log = []
    last_pick = None
    for i, d in enumerate(dates):
        val = sum(units[c] * px[c].iloc[i] for c in codes) + cash
        if i < max(lookback, ma_win) + 30 or i % rebal != 0:
            continue
        cands = []
        for c in codes:
            if not above_ma(px[c], i, ma_win):
                continue
            m = momentum(px[c], i, lookback)
            if m == m:
                cands.append((c, m))
        cands.sort(key=lambda x: -x[1])
        picked = [c for c, _ in cands[:top_n]]
        cost = 0.0
        for c in codes:
            tgt = val * (1.0 / len(picked) if picked else 0.0)
            cur = units[c] * px[c].iloc[i]
            delta = tgt - cur
            if abs(delta) < val * 0.005:
                continue
            cc = apply_cost(delta)
            cost += cc
            cash -= (delta + cc)
            units[c] += delta / px[c].iloc[i]
        log.append({
            "date": d, "val": val, "cash": cash, "cost": cost,
            "picks": picked, "turnover": None if last_pick is None else
            len(set(picked) ^ set(last_pick)) / max(1, len(set(picked) | set(last_pick))),
        })
        last_pick = picked
    return pd.DataFrame(log)


def main() -> int:
    START, END = "2024-02-07", "2026-09-30"
    px = load(SECTOR_ETFS, START, END)
    df = trace(px, top_n=2, rebal=20)
    print("=" * 108)
    print("动量前2只·月度再平衡：逐次调仓追踪（前 20 次）")
    print("=" * 108)
    print(f"  {'日期':<12}{'组合市值':>12}{'现金':>12}{'本次成本':>10}{'换手':>8}  持仓")
    print("  " + "-" * 88)
    for _, r in df.head(20).iterrows():
        to = f"{r['turnover']*100:.0f}%" if r["turnover"] is not None else "—"
        print(f"  {r['date']:<12}{r['val']:>12,.0f}{r['cash']:>12,.0f}{r['cost']:>10,.0f}"
              f"{to:>8}  {', '.join(r['picks'])}")

    print()
    print("=" * 108)
    print("关键统计")
    print("=" * 108)
    print(f"  调仓次数            : {len(df)}")
    print(f"  期末市值            : {df['val'].iloc[-1]:,.0f}")
    print(f"  累计成本            : {df['cost'].sum():,.0f}  "
          f"（占初始本金 {df['cost'].sum()/1000:.1f}%）")
    print(f"  平均单次成本        : {df['cost'].mean():,.0f}")
    print(f"  平均换手率          : {df['turnover'].dropna().mean()*100:.1f}%")
    # 市值曲线
    vals = df.set_index("date")["val"]
    dd = (vals / vals.cummax() - 1)
    print(f"  市值序列最大回撤    : {dd.min()*100:+.1f}%")
    print(f"  市值序列最高 / 最低 : {vals.max():,.0f} / {vals.min():,.0f}")
    print()
    print("  市值曲线（每 4 次调仓取 1）：")
    for i in range(0, len(vals), 4):
        bar = "█" * max(0, int(vals.iloc[i] / 100000 * 30))
        print(f"    {vals.index[i]}  {vals.iloc[i]:>10,.0f}  {bar}")

    print()
    print("  最差的 5 次调仓（市值环比跌幅最大）：")
    chg = vals.pct_change()
    for d in chg.nsmallest(5).index:
        i = list(vals.index).index(d)
        prev_picks = df['picks'].iloc[i-1] if i > 0 else []
        print(f"    {d}  环比 {chg[d]*100:+.1f}%   上次持仓 {prev_picks}"
              f" → 本次 {df['picks'].iloc[i]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
