#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黄金第四案例：现货 vs 黄金股 lead-lag（2026-10-17）

目的
----
用黄金验证「商品价格 → 商品股」这条信号路径，
并检验「幅度过滤」的阈值是否合理。

黄金的基本面 = 实际利率/央行购金/避险，但可观测的直接指标是金价本身。
黄金股（矿企）利润主要由金价决定 → 金价领先黄金股。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load(code: str) -> pd.Series:
    df = pd.read_csv(f"backtests/cache_long/{code}.csv")
    df["date"] = df["date"].astype(str).str[:10]
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def main() -> int:
    gold = load("au9999")  # 黄金现货
    stocks = {"山东黄金": "sh600547", "中金黄金": "sh600489",
              "紫金矿业": "sh601899", "赤峰黄金": "sh600988"}
    eq = pd.DataFrame({n: load(c) for n, c in stocks.items()}).sort_index().dropna().mean(axis=1)

    # 对齐
    j = pd.DataFrame({"金价": gold, "黄金股等权": eq}).dropna()
    print(f"样本 {j.index[0]} ~ {j.index[-1]}（{len(j)} 日）")

    # 逐年
    print()
    print(f"  {'年份':<8}{'金价':>10}{'黄金股等权':>12}")
    print("  " + "-" * 34)
    for y in ("2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"):
        cells = []
        for col in ("金价", "黄金股等权"):
            seg = j[col][j.index.str.startswith(y)]
            cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+10.1f}%" if len(seg) >= 20 else f"{'—':>11}")
        print(f"  {y:<8}" + "".join(cells))

    # 金价大幅上涨的年份 → 黄金股是否跟随？
    print()
    print("=" * 80)
    print("幅度过滤检验：金价涨幅 vs 黄金股涨幅")
    print("=" * 80)
    for y in ("2019", "2020", "2023", "2024", "2025"):
        g = j["金价"][j.index.str.startswith(y)]
        s = j["黄金股等权"][j.index.str.startswith(y)]
        if len(g) < 20:
            continue
        gr = g.iloc[-1] / g.iloc[0] - 1
        sr = s.iloc[-1] / s.iloc[0] - 1
        tag = "✅ 金价大涨→股涨" if gr > 0.20 and sr > 0.20 else ("✅ 金价小涨→股平" if gr < 0.20 else "⚠️")
        print(f"  {y}: 金价 {gr*100:+.1f}% → 黄金股 {sr*100:+.1f}%  {tag}")

    # 相关性 + 领先
    print()
    print("=" * 80)
    print("金价 vs 黄金股：相关性")
    print("=" * 80)
    ret = j.pct_change().dropna()
    print(f"  日收益相关系数：{ret.corr().iloc[0,1]:.3f}")
    # 金价是否领先？（滞后相关）
    for lag in (1, 5, 20):
        c = ret["黄金股等权"].corr(ret["金价"].shift(lag))
        print(f"  金价领先 {lag:>2} 日的相关：{c:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
