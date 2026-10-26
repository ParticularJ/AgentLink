#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 1 层：核心仓择时回测（用户明确要求："核心仓也需要股票池和择时"）

核心仓候选池（用户指定 + 其同类）：
  银行：工商银行、农业银行、中国银行、招商银行、兴业银行
  电力/公用：长江电力、中国核电
  通信/资源：中国移动、中国神华
  宽基：沪深300ETF、中证500ETF

要检验的三个择时规则（只用价格数据，无未来函数）：
  T0 纯买入持有（对照，等权、不再平衡）
  T1 位置择时：pos250 ≤ 40% 时加仓到满仓，pos250 ≥ 80% 时降到半仓
  T2 相对强度：rs60 > 0 时持有，rs60 ≤ 0 时半仓
  T3 两者结合

评估：年化 / 最大回撤 / 卡玛 / 月胜率 / 最长连亏月
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))
CACHE = HERE / "cache"
BENCH = "sh000300"

CORE_POOL = {
    "银行": ["sh601398", "sh601288", "sh601988", "sh600036", "sh601166"],
    "电力/公用": ["sh600900", "sh601985"],
    "通信/资源": ["sh600941", "sh601088"],
    "宽基": ["sh510300", "sh510500"],
}


def load(start: str, end: str):
    codes = sorted({c for cs in CORE_POOL.values() for c in cs}) + [BENCH]
    out = {}
    for c in codes:
        p = CACHE / f"{c}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < 200:
            continue
        out[c] = pd.Series(df["close"].astype(float).values, index=df["date"].values)
    px = pd.DataFrame(out).sort_index()
    return px


def norm_each(df: pd.DataFrame) -> pd.DataFrame:
    o = {}
    for c in df.columns:
        s = df[c].dropna()
        if not s.empty:
            o[c] = df[c] / s.iloc[0]
    return pd.DataFrame(o)


def run(px: pd.DataFrame, exposure_fn: Optional[Callable], label: str) -> dict:
    """按 exposure_fn(i, nav, bench) → 目标仓位（0~1）逐日调仓；None = 买入持有。"""
    codes = [c for c in px.columns if c != BENCH]
    sub = norm_each(px[codes])
    nav = sub.mean(axis=1).dropna()
    idx = list(nav.index)
    bench = px[BENCH].reindex(nav.index).ffill()

    if exposure_fn is None:
        curve = nav / nav.iloc[0]
    else:
        units = 1.0        # 持有份额
        cash = 0.0
        curve_vals = []
        for i, d in enumerate(idx):
            v = nav.iloc[i]
            total = units * v + cash
            curve_vals.append(total)
            if i < 250 or i >= len(idx) - 1:
                continue
            exp = exposure_fn(i, nav, bench)
            exp = max(0.0, min(1.0, exp))
            tgt = total * exp
            # 一次调仓，成本 0.03%
            delta = tgt - units * v
            if abs(delta) > total * 0.01:
                units += delta / v
                cash -= delta + abs(delta) * 0.0003
        curve = pd.Series(curve_vals, index=idx)
        curve = curve / curve.iloc[0]

    n_years = len(curve) / 242
    cagr = (curve.iloc[-1] / curve.iloc[0]) ** (1 / n_years) - 1
    mdd = (curve / curve.cummax() - 1).min()
    m = curve.groupby(curve.index.str[:7]).last().pct_change().dropna()
    streak = best = 0
    for v in m:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    return {
        "label": label, "cagr": cagr * 100, "mdd": mdd * 100,
        "calmar": (cagr / abs(mdd)) if mdd < 0 else float("nan"),
        "月胜率": (m > 0).mean() * 100, "达标月": (m >= 0.012).mean() * 100,
        "最差月": m.min() * 100, "连亏月": best,
    }


def pos250(nav: pd.Series, i: int) -> float:
    w = nav.iloc[max(0, i - 250):i + 1]
    lo, hi = w.min(), w.max()
    return (nav.iloc[i] - lo) / (hi - lo + 1e-9)


def main() -> int:
    START, END = "2024-02-26", "2026-10-16"
    px = load(START, END)
    print(f"核心仓池标的 {px.shape[1]-1} 只，区间 {px.index[0]} → {px.index[-1]}\n")

    def t1(i, nav, bench):
        p = pos250(nav, i)
        return 1.0 if p <= 0.40 else (0.5 if p >= 0.80 else 0.8)

    def t2(i, nav, bench):
        rs = (nav.iloc[i] / nav.iloc[i - 60] - 1) - (bench.iloc[i] / bench.iloc[i - 60] - 1)
        return 1.0 if rs > 0 else 0.5

    def t3(i, nav, bench):
        p = pos250(nav, i)
        rs = (nav.iloc[i] / nav.iloc[i - 60] - 1) - (bench.iloc[i] / bench.iloc[i - 60] - 1)
        base = 1.0 if p <= 0.40 else (0.5 if p >= 0.80 else 0.8)
        return base * (1.0 if rs > 0 else 0.6)

    rows = [run(px, None, "T0 纯买入持有（等权）"),
            run(px, t1, "T1 位置择时"),
            run(px, t2, "T2 相对强度择时"),
            run(px, t3, "T3 位置+相对强度")]
    print(f"  {'方案':<24}{'年化':>9}{'最大回撤':>10}{'卡玛':>8}{'月胜率':>9}"
          f"{'达标月':>9}{'最差月':>9}{'连亏月':>8}")
    print("  " + "-" * 84)
    for r in rows:
        print(f"  {r['label']:<24}{r['cagr']:>+8.1f}%{r['mdd']:>+9.1f}%{r['calmar']:>8.2f}"
              f"{r['月胜率']:>8.1f}%{r['达标月']:>8.1f}%{r['最差月']:>+8.1f}%{r['连亏月']:>8}")
    print()
    best = max(rows, key=lambda r: r["calmar"])
    base = rows[0]
    print(f"  卡玛最优：{best['label']}（{best['calmar']:.2f} vs 买入持有 {base['calmar']:.2f}）")
    print("  判读：若择时方案的卡玛未明显优于买入持有，则『核心仓择时』不成立，")
    print("        应回归『买入持有 + 定期再平衡』。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
