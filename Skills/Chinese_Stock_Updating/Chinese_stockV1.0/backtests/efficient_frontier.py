#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""有效边界扫描：给定「回撤≤20%」约束，收益上限到底是多少？

必须回答的问题（用户目标 vs 数学）：
  用户要 月化 1.2%~1.9% 且 回撤 ≤20%
  月化 1.9% = 年化 22.8%；配 15% 波动 → 夏普 ≈ 1.5（全球顶级水平）

本脚本扫描：
  A. 风险敞口 30%→100% 的完整有效边界（年化 / 回撤 / 月化 / 达标月）
  B. 加减「趋势过滤」（用 250 日均线，检验"下行不交易"是否仍有效）
  C. 买入持有对照（纯红利 / 纯沪深300 / 60-40）
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from allocation_engine import (BUCKETS, STATIC_TARGET, Result, apply_cost,  # noqa: E402
                               bucket_nav, load_prices, metrics, position_score)

# ── 重建一个可参数化敞口的回测（引擎里 target_fn 已是可调的，这里直接复用）──


def make_target(exposure: float, tilt: float = 0.0, trend_filter: bool = False,
                ma_window: int = 250):
    """exposure: 风险资产总仓位（其余进债券）。

    tilt=0 表示各风险资产按 STATIC_TARGET 比例；tilt>0 加入估值倾斜。
    trend_filter: 沪深300 跌破 250 日均线时，风险敞口打 5 折（"下行不交易"的温和版）。
    """
    def _fn(i, navs, cur) -> Dict[str, float]:
        risky = [b for b in ("equity_dividend", "equity_broad", "gold") if b in navs]
        base = {b: STATIC_TARGET.get(b, 0.0) for b in risky}
        base_tot = sum(base.values()) or 1.0
        w = {}
        for b in risky:
            s = position_score(navs[b], i)
            w[b] = base[b] / base_tot * (1.0 + tilt * (s - 0.5) * 2.0)
        tot = sum(w.values()) or 1.0
        exp = exposure
        if trend_filter and "equity_broad" in navs:
            broad = navs["equity_broad"]
            if i >= ma_window:
                ma = broad.iloc[i - ma_window:i + 1].mean()
                if broad.iloc[i] < ma:
                    exp = exposure * 0.5
        w = {b: v / tot * exp for b, v in w.items()}
        w["bond"] = max(0.0, 1.0 - exp)
        return w
    return _fn


def run(px, target_fn, rebal=20, label=""):
    navs = {b: bucket_nav(px, b) for b in BUCKETS}
    navs = {b: v for b, v in navs.items() if v is not None}
    dates = px.index
    units = {b: 0.0 for b in navs}
    cash = 100_000.0
    curve = []
    cost = 0.0
    trades = 0
    for i, d in enumerate(dates):
        val = sum(units[b] * navs[b].iloc[i] for b in navs) + cash
        curve.append(val)
        if i == 0 or i % rebal != 0 or i < 130:
            continue
        w = target_fn(i, navs, {b: (units[b] * navs[b].iloc[i]) / val for b in navs})
        # ⚠️ 先算全部目标 → 先卖后买（修正 8 倍杠杆 bug，详见 allocation_engine）
        targets = {b: val * w.get(b, 0.0) for b in navs}
        cur_vals = {b: units[b] * navs[b].iloc[i] for b in navs}
        for b in navs:
            delta = targets[b] - cur_vals[b]
            if delta >= 0 or abs(delta) < val * 0.005:
                continue
            c = apply_cost(delta)
            cost += c
            trades += 1
            cash -= (delta + c)
            units[b] += delta / navs[b].iloc[i]
        for b in navs:
            cur_v = units[b] * navs[b].iloc[i]
            delta = targets[b] - cur_v
            if delta <= 0 or abs(delta) < val * 0.005:
                continue
            delta = min(delta, max(0.0, cash - apply_cost(delta)))
            if delta < val * 0.005:
                continue
            c = apply_cost(delta)
            cost += c
            trades += 1
            cash -= (delta + c)
            units[b] += delta / navs[b].iloc[i]
    return Result(label=label, nav=pd.Series(curve, index=dates), trades=trades, cost_paid=cost)


def buyhold(px, code, label):
    s = px[code]
    return Result(label=label, nav=s / s.iloc[0] * 100_000.0)


def main() -> int:
    START, END = "2024-02-07", "2026-09-30"
    codes = sorted({c for b in BUCKETS.values() for c in b})
    px = load_prices(codes, START, END)
    print(f"区间 {px.index[0]} → {px.index[-1]}，{len(px)} 个交易日 "
          f"（{len(px)/242:.2f} 年）\n")

    print("=" * 118)
    print("A. 有效边界：风险敞口 vs 收益/回撤（月度再平衡，含成本）")
    print("=" * 118)
    print(f"  {'风险敞口':<12}{'年化':>9}{'月化':>8}{'最大回撤':>10}{'月胜率':>9}"
          f"{'达标月≥1.2%':>13}{'最差月':>9}{'连亏月':>8}{'夏普(近似)':>12}")
    print("  " + "-" * 108)
    for exp in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00):
        r = run(px, make_target(exp), 20, f"敞口{exp:.0%}")
        m = metrics(r)
        # 夏普近似：年化 / 年化波动
        rets = r.nav.pct_change().dropna()
        vol = rets.std() * (242 ** 0.5) * 100
        sharpe = m["cagr"] / vol if vol > 0 else 0
        flag = "  ← 回撤达标" if m["mdd"] > -20 else "  ← 超回撤上限"
        print(f"  {exp:<12.0%}{m['cagr']:>+8.1f}%{m['月化']:>+7.2f}%{m['mdd']:>+9.1f}%"
              f"{m['月胜率']:>8.1f}%{m['达标月(≥1.2%)']:>12.1f}%{m['最差月']:>+8.1f}%"
              f"{m['连亏月']:>8}{sharpe:>11.2f}{flag}")

    print()
    print("=" * 118)
    print("B. 加「趋势过滤」（沪深300 跌破 250 日线时敞口减半）")
    print("=" * 118)
    print(f"  {'方案':<24}{'年化':>9}{'月化':>8}{'最大回撤':>10}{'月胜率':>9}"
          f"{'达标月':>9}{'最差月':>9}{'调仓':>7}")
    print("  " + "-" * 96)
    for exp in (0.60, 0.80, 1.00):
        for tf in (False, True):
            r = run(px, make_target(exp, trend_filter=tf), 20,
                    f"敞口{exp:.0%}{'+趋势过滤' if tf else ''}")
            m = metrics(r)
            print(f"  {r.label:<24}{m['cagr']:>+8.1f}%{m['月化']:>+7.2f}%{m['mdd']:>+9.1f}%"
                  f"{m['月胜率']:>8.1f}%{m['达标月(≥1.2%)']:>8.1f}%{m['最差月']:>+8.1f}%"
                  f"{m['调仓次数']:>7}")

    print()
    print("=" * 118)
    print("C. 买入持有对照")
    print("=" * 118)
    print(f"  {'标的':<22}{'累计':>10}{'年化':>9}{'月化':>8}{'最大回撤':>10}"
          f"{'月胜率':>9}{'达标月':>9}{'连亏月':>8}")
    print("  " + "-" * 92)
    for code, name in (("sh515180", "红利ETF易方达"), ("sh510300", "沪深300ETF"),
                       ("sh518880", "黄金ETF"), ("sh511260", "十年国债ETF")):
        if code not in px.columns:
            continue
        r = buyhold(px, code, name)
        m = metrics(r)
        print(f"  {name:<22}{m['total']:>+9.1f}%{m['cagr']:>+8.1f}%{m['月化']:>+7.2f}%"
              f"{m['mdd']:>+9.1f}%{m['月胜率']:>8.1f}%{m['达标月(≥1.2%)']:>8.1f}%"
              f"{m['连亏月']:>8}")

    print()
    print("=" * 118)
    print("D. 结论校验：用户目标 vs 实际可达")
    print("=" * 118)
    print("  用户目标：月化 1.2%~1.9%（年化 15.4%~25.4%），最大回撤 ≤20%")
    print("  上表中「回撤达标」且年化最高的方案，即为该约束下的收益上限。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
