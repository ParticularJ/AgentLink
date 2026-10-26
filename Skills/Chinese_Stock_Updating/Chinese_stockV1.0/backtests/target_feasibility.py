#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户的收益/回撤目标是否可达？—— 用数学 + 你们自己的数据检验。

用户目标（2026-10-16）：
  T1 可承受个股或账户 10%~20% 回撤，但**希望 1~2 个月内回本或盈利**
  T2 希望**每月 2%~5% 盈利**，每月可切换股票池
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"


def series(sym, start="2024-02-07", end="2026-09-30"):
    p = CACHE / f"{sym}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = df["date"].astype(str).str[:10]
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    if len(df) < 30:
        return None
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def monthly(s: pd.Series) -> pd.Series:
    return s.groupby(s.index.str[:7]).last().pct_change().dropna()


def main() -> int:
    print("=" * 92)
    print("第 1 部分：目标换算 —— 『每月 2%~5%』在数学上等于什么")
    print("=" * 92)
    print(f"  {'月收益':>8}{'年化(复利)':>14}{'3年后(1万)':>14}{'10年后(1万)':>16}{'20年后(1万)':>18}")
    print("  " + "-" * 70)
    for m in (0.02, 0.03, 0.05):
        ann = (1 + m) ** 12 - 1
        v3 = 10000 * (1 + m) ** 36
        v10 = 10000 * (1 + m) ** 120
        v20 = 10000 * (1 + m) ** 240
        print(f"  {m*100:>7.0f}%{ann*100:>13.1f}%{v3:>14,.0f}{v10:>16,.0f}{v20:>18,.0f}")

    print()
    print("  对照（长期可实现水平）：")
    print(f"  {'标的':<24}{'年化':>10}{'月化(几何)':>14}")
    print("  " + "-" * 50)
    for name, sym in (("沪深300", "sh000300"), ("红利篮子 sh515180", "sh515180"),
                      ("黄金 sh518880", "sh518880")):
        s = series(sym)
        if s is None:
            continue
        n_years = len(s) / 242
        cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / n_years) - 1
        print(f"  {name:<24}{cagr*100:>+9.1f}%{((1+cagr)**(1/12)-1)*100:>13.2f}%")

    print()
    print("=" * 92)
    print("第 2 部分：回撤回本数学 —— 『20% 回撤 1~2 个月回本』需要多快")
    print("=" * 92)
    print(f"  {'回撤':>8}{'需涨回本':>12}{'1个月需月收益':>16}{'2个月需月收益':>16}")
    print("  " + "-" * 56)
    for dd in (0.10, 0.15, 0.20):
        need = 1 / (1 - dd) - 1
        m1 = (1 + need) ** 1 - 1
        m2 = (1 + need) ** 0.5 - 1
        print(f"  {dd*100:>7.0f}%{need*100:>11.1f}%{m1*100:>15.1f}%{m2*100:>15.1f}%")
    print("\n  → 20% 回撤要在 2 个月内回本，等于要求连续两个月各赚 11.8% ——")
    print("     这本身就是『月化 11.8%』的目标，比 T2 的 5% 还高一倍多。")

    print()
    print("=" * 92)
    print("第 3 部分：A 股实际的月度收益分布（你们自己的数据，2024-02 ~ 2026-09）")
    print("=" * 92)
    print(f"  {'标的':<22}{'月数':>6}{'月均':>9}{'月胜率':>9}{'最好月':>9}{'最差月':>9}"
          f"{'连亏最长':>10}{'月度标准差':>11}")
    print("  " + "-" * 88)
    all_months = {}
    for name, sym in (("沪深300", "sh000300"), ("红利篮子", "sh515180"),
                      ("黄金", "sh518880"), ("寒武纪", "sh688256"),
                      ("中际旭创", "sz300308")):
        s = series(sym)
        if s is None:
            continue
        m = monthly(s)
        all_months[name] = m
        # 最长连亏
        streak = best = 0
        for v in m:
            streak = streak + 1 if v < 0 else 0
            best = max(best, streak)
        print(f"  {name:<22}{len(m):>6}{m.mean()*100:>+8.2f}%{(m>0).mean()*100:>8.1f}%"
              f"{m.max()*100:>+8.1f}%{m.min()*100:>+8.1f}%{best:>9}{m.std()*100:>10.1f}%")

    print()
    print("=" * 92)
    print("第 4 部分：关键检验 —— 有没有月化 2%~5% 且回撤可控的组合？")
    print("=" * 92)
    # 构造几个候选：单标的 / 等权 / 带现金的保守组合
    div = series("sh515180")
    gold = series("sh518880")
    hs = series("sh000300")
    if div is not None and gold is not None and hs is not None:
        df = pd.DataFrame({"div": div, "gold": gold, "hs": hs}).dropna()
        portfolios = {
            "全红利": df["div"],
            "全黄金": df["gold"],
            "全沪深300": df["hs"],
            "红利70%+黄金30%": df["div"] * 0.7 + df["gold"] * 0.3,
            "红利50%+黄金20%+现金30%": df["div"] * 0.5 + df["gold"] * 0.2 + 0.3,
            "沪深300_50%+红利50%": df["hs"] * 0.5 + df["div"] * 0.5,
        }
        print(f"  {'组合':<26}{'年化':>9}{'月化':>8}{'最大回撤':>10}{'月胜率':>9}"
              f"{'达标月份(≥2%)':>14}")
        print("  " + "-" * 78)
        for name, nav in portfolios.items():
            nav = nav / nav.iloc[0]
            n_years = len(nav) / 242
            cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / n_years) - 1
            m = monthly(nav)
            mdd = (nav / nav.cummax() - 1).min()
            hit = (m >= 0.02).mean() * 100
            print(f"  {name:<26}{cagr*100:>+8.1f}%{m.mean()*100:>+7.2f}%{mdd*100:>+9.1f}%"
                  f"{(m>0).mean()*100:>8.1f}%{hit:>13.1f}%")

    print()
    print("=" * 92)
    print("第 5 部分：你们自己策略的月度表现（生产配置，README 记录）")
    print("=" * 92)
    rows = [("2025-11", 2, 0.0, -8.00), ("2025-12", 9, 77.8, 8.66), ("2026-01", 18, 72.2, 6.63),
            ("2026-02", 4, 75.0, 5.12), ("2026-03", 3, 33.3, -4.71), ("2026-04", 12, 100.0, 13.18),
            ("2026-05", 9, 55.6, 4.54), ("2026-06", 7, 28.6, -4.21), ("2026-07", 5, 60.0, 1.53),
            ("2026-08", 5, 80.0, 0.72)]
    print(f"  {'月份':<10}{'笔数':>6}{'胜率':>9}{'单笔均值':>11}{'账户口径(2只×等权)':>20}")
    print("  " + "-" * 58)
    acct = []
    for mo, n, wr, avg in rows:
        # 账户口径近似：当月交易的每笔都是独立仓位，取当月均值作为账户月收益近似
        a = avg
        acct.append(a)
        print(f"  {mo:<10}{n:>6}{wr:>8.1f}%{avg:>+10.2f}%{a:>+19.2f}%")
    print(f"\n  → 10 个月里 ≥2% 的月份：{sum(1 for x in acct if x>=2)}/10；"
          f"负收益月份：{sum(1 for x in acct if x<0)}/10")
    print(f"  → 月均值 {statistics.mean(acct):+.2f}%，月度标准差 {statistics.pstdev(acct):.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
