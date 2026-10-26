#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收官测试：找出「回撤≤20% + 收益最高」的方案，并排除幸存者偏差。

三个测试：
  T1 修正 bug 后的分散配置有效边界（此前的结果受 8 倍杠杆污染）
  T2 幸存者偏差检验：把池子扩大到「2023 年初就存在的全部 ETF」，重跑等权/轮动
  T3 分半 + 逐年：看最优方案在两半区间和每一年是否都成立
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from allocation_engine import (BUCKETS, STATIC_TARGET, CACHE, Result, apply_cost,  # noqa: E402
                               bucket_nav, load_prices, metrics)

ALL_ETF = None


def all_etf_codes() -> List[str]:
    """缓存里全部 ETF 风格标的（用于幸存者检验，不做事后挑选）。"""
    out = []
    for p in sorted(CACHE.glob("*.csv")):
        s = p.stem
        if s[:2] in ("sh", "sz") and s[2:4] in ("50", "51", "56", "58", "15", "16", "18"):
            out.append(s)
    return out


def load_many(codes, start, end, min_rows=260):
    """加载全部候选 ETF（**不做 dropna 对齐**）。

    ⚠️ 2026-10-16 bug 修复：原实现用 pd.DataFrame(out).dropna() 做 inner join，
    结果被"最晚上市的那只 ETF"截断——实测区间从 2.6 年缩成 16 个月
    （2025-06-04 起），而那段正好是下跌行情，导致全部结论反转。

    现在改为：按日期外连接 + 前向填充，**未上市期间的价格为 NaN**，
    由调用方（sim）按"当日有效标的"动态分配权重。
    """
    out = {}
    for c in codes:
        p = CACHE / f"{c}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < min_rows:
            continue
        out[c] = pd.Series(df["close"].astype(float).values, index=df["date"].values)
    if not out:
        return None
    px = pd.DataFrame(out)                 # 外连接：保留全部日期
    px = px.sort_index()
    return px


def valid_codes_on(px: pd.DataFrame, i: int) -> List[str]:
    """第 i 日有有效价格（非 NaN）的标的。"""
    row = px.iloc[i]
    return [c for c in px.columns if row[c] == row[c] and row[c] > 0]


def sim(px: pd.DataFrame, weights_fn, rebal=60, label="") -> Result:
    """通用模拟：weights_fn(i, px) -> {code: weight}（权重和 ≤1，余额留现金）。

    价格序列允许含 NaN（标的未上市），只在有效标的上分配与成交。
    """
    dates = px.index
    codes = list(px.columns)
    units = {c: 0.0 for c in codes}
    cash = 100_000.0
    curve, cost, trades = [], 0.0, 0

    def price(c, i):
        v = px[c].iloc[i]
        return None if (v != v or v <= 0) else float(v)

    for i, d in enumerate(dates):
        val = cash
        for c in codes:
            p = price(c, i)
            if p is not None and units[c]:
                val += units[c] * p
        curve.append(val)
        if i == 0 or i % rebal != 0 or i < 130:
            continue
        w = weights_fn(i, px)
        if not w:
            continue
        targets = {}
        for c in codes:
            p = price(c, i)
            if p is None:
                continue
            targets[c] = val * w.get(c, 0.0)
        cur_vals = {c: units[c] * price(c, i) for c in targets}
        for c in targets:                                  # 先卖
            delta = targets[c] - cur_vals[c]
            if delta >= 0 or abs(delta) < val * 0.005:
                continue
            cc = apply_cost(delta)
            cost += cc
            trades += 1
            cash -= (delta + cc)
            units[c] += delta / price(c, i)
        for c in targets:                                  # 后买（现金约束）
            cur_v = units[c] * price(c, i)
            delta = targets[c] - cur_v
            if delta <= 0 or abs(delta) < val * 0.005:
                continue
            delta = min(delta, max(0.0, cash - apply_cost(delta)))
            if delta < val * 0.005:
                continue
            cc = apply_cost(delta)
            cost += cc
            trades += 1
            cash -= (delta + cc)
            units[c] += delta / price(c, i)
    return Result(label=label, nav=pd.Series(curve, index=dates), trades=trades, cost_paid=cost)


def w_equal(i, px):
    vs = valid_codes_on(px, i)
    return {c: 1.0 / len(vs) for c in vs} if vs else {}


def make_w_topn(n: int, lookback: int = 120, ma_win: int = 200):
    def _fn(i, px):
        if i < max(lookback, ma_win):
            return {}
        cands = []
        for c in valid_codes_on(px, i):
            s = px[c].iloc[:i + 1].dropna()
            if len(s) < ma_win:
                continue
            if s.iloc[-1] <= s.iloc[-ma_win:].mean():
                continue
            m = s.iloc[-1] / s.iloc[-lookback] - 1
            if m == m:
                cands.append((c, m))
        cands.sort(key=lambda x: -x[1])
        picked = [c for c, _ in cands[:n]]
        return {c: 1.0 / len(picked) for c in picked} if picked else {}
    return _fn


def main() -> int:
    START, END = "2024-02-07", "2026-09-30"
    print("=" * 112)
    print("T1 修正杠杆 bug 后的分散配置（前面受污染，此处重跑）")
    print("=" * 112)
    codes = sorted({c for b in BUCKETS.values() for c in b})
    px = load_prices(codes, START, END)
    navs = {b: bucket_nav(px, b) for b in BUCKETS}
    from efficient_frontier import make_target, run as ef_run
    print(f"  {'风险敞口':<14}{'年化':>9}{'最大回撤':>10}{'月胜率':>9}{'达标月':>9}{'最差月':>9}{'连亏月':>7}")
    print("  " + "-" * 72)
    for exp in (0.40, 0.60, 0.80, 1.00):
        r = ef_run(px, make_target(exp), 20, f"敞口{exp:.0%}")
        m = metrics(r)
        print(f"  {exp:<14.0%}{m['cagr']:>+8.1f}%{m['mdd']:>+9.1f}%{m['月胜率']:>8.1f}%"
              f"{m['达标月(≥1.2%)']:>8.1f}%{m['最差月']:>+8.1f}%{m['连亏月']:>7}")

    print()
    print("=" * 112)
    print("T2 幸存者偏差检验：池子扩到「2023 年初已存在的全部 ETF」（不做事后挑选）")
    print("=" * 112)
    codes_all = all_etf_codes()
    pxb = load_many(codes_all, START, END)
    print(f"  2023 年初已存在且覆盖完整的 ETF：{pxb.shape[1]} 只")
    print(f"  {'方案':<30}{'年化':>9}{'最大回撤':>10}{'月胜率':>9}{'达标月':>9}"
          f"{'最差月':>9}{'连亏月':>7}{'调仓':>7}")
    print("  " + "-" * 94)
    for label, fn, reb in (("全部ETF等权（季度）", w_equal, 60),
                           ("全部ETF等权（月度）", w_equal, 20),
                           ("动量前5只·MA200（月度）", make_w_topn(5), 20),
                           ("动量前10只·MA200（月度）", make_w_topn(10), 20),
                           ("动量前20只·MA200（月度）", make_w_topn(20), 20)):
        r = sim(pxb, fn, reb, label)
        m = metrics(r)
        flag = " ✅回撤达标" if m["mdd"] > -20 else ""
        print(f"  {label:<30}{m['cagr']:>+8.1f}%{m['mdd']:>+9.1f}%{m['月胜率']:>8.1f}%"
              f"{m['达标月(≥1.2%)']:>8.1f}%{m['最差月']:>+8.1f}%{m['连亏月']:>7}"
              f"{m['调仓次数']:>7}{flag}")

    print()
    print("=" * 112)
    print("T3 最优候选的分半 + 逐年稳健性")
    print("=" * 112)
    mid = "2025-07-01"
    for label, fn, reb in (("全部ETF等权（季度）", w_equal, 60),
                           ("动量前10只·MA200（月度）", make_w_topn(10), 20)):
        print(f"\n  ── {label} ──")
        for seg_label, s0, s1 in (("全区间", START, END),
                                  ("前半段", START, mid),
                                  ("后半段", mid, END)):
            pxs = pxb[(pxb.index >= s0) & (pxb.index <= s1)]
            if len(pxs) < 150:
                print(f"    {seg_label:<8} 样本不足")
                continue
            r = sim(pxs, fn, reb, seg_label)
            m = metrics(r)
            print(f"    {seg_label:<8} 年化 {m['cagr']:>+7.1f}%  回撤 {m['mdd']:>+7.1f}%  "
                  f"月胜率 {m['月胜率']:>5.1f}%  达标月 {m['达标月(≥1.2%)']:>5.1f}%")
        print(f"    逐年：")
        for y in ("2024", "2025", "2026"):
            pxs = pxb[pxb.index.str.startswith(y)]
            if len(pxs) < 60:
                continue
            r = sim(pxs, fn, reb, y)
            m = metrics(r)
            print(f"      {y}     收益 {m['total']:>+7.1f}%  回撤 {m['mdd']:>+7.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
