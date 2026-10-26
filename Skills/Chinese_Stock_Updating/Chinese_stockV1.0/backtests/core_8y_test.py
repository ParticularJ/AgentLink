#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心仓 8.5 年全周期检验（2018-01 ~ 2026-10）

为什么单独测核心仓
------------------
上一轮发现：**纯核心仓（+14.5%，卡玛 1.48）优于 70/30 组合（+12.0%，卡玛 1.32）**，
即卫星仓在稀释收益。

而卫星 ETF 的数据最早只到 2022-03，无法回溯到 2018。
但核心仓（个股）有 2018 年起的前复权数据。

因此本脚本只测核心仓，区间 **2018-01 ~ 2026-10（8.5 年）**，
跨越：
  2018 熊市（沪指 −24.6%）
  2019-2020 牛市
  2021 震荡（核心资产杀估值）
  2022 熊市（沪指 −21.6%）
  2023 震荡下行
  2024-2025 牛市
  2026 回调

这是判断"核心仓股票池"是否真正稳健的最强证据。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))

CACHE_LONG = HERE / "cache_long"
CACHE = HERE / "cache"
BENCH = "sh000300"
COST = 0.0005

# 2018 年起就有数据的核心标的（剔除 2022 上市的中国移动）
CORE18: Dict[str, str] = {
    "工商银行": "sh601398", "农业银行": "sh601288", "中国银行": "sh601988",
    "招商银行": "sh600036", "兴业银行": "sh601166",
    "长江电力": "sh600900", "中国核电": "sh601985",
    "中国神华": "sh601088",
    "沪深300": "sh000300", "中证500": "sh000905",
}
# 扩展：加入中国移动（2022 起）做 2022-2026 对照
CORE_ALL: Dict[str, str] = dict(CORE18, **{"中国移动": "sh600941"})


def load(code: str, start: str, end: str) -> Optional[pd.Series]:
    for base in (CACHE_LONG, CACHE):
        p = base / f"{code}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < 100:
            continue
        return pd.Series(df["close"].astype(float).values, index=df["date"].values)
    return None


def core_nav(pool: Dict[str, str], start: str, end: str,
             rebal: int = 60, start_after: int = 0) -> pd.Series:
    """等权核心仓，定期再平衡。"""
    d = {}
    for c in pool.values():
        s = load(c, start, end)
        if s is not None:
            d[c] = s
    px = pd.DataFrame(d).sort_index()
    need = [c for c in pool.values() if c in px.columns]
    px = px[need].dropna()
    dates = list(px.index)
    units = {c: 0.0 for c in px.columns}
    cash = 1.0
    curve = []
    for i, dt in enumerate(dates):
        v = cash + sum(u * px[c].iloc[i] for c, u in units.items())
        curve.append(v)
        if i == start_after:
            for c in px.columns:
                u = (v / len(px.columns)) / px[c].iloc[i]
                units[c] = u
                cash -= u * px[c].iloc[i]
            continue
        if i < start_after:
            continue
        if (i - start_after) % rebal == 0:
            v = cash + sum(u * px[c].iloc[i] for c, u in units.items())
            for c in px.columns:
                tgt = v / len(px.columns)
                cur = units[c] * px[c].iloc[i]
                delta = tgt - cur
                if abs(delta) > v * 0.03:
                    cash -= (delta + abs(delta) * COST)
                    units[c] += delta / px[c].iloc[i]
    return pd.Series(curve, index=dates)


def metr(nav: pd.Series) -> dict:
    if len(nav) < 40:
        return {}
    ny = len(nav) / 242
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / ny) - 1
    mdd = (nav / nav.cummax() - 1).min()
    m = nav.groupby(nav.index.str[:7]).last().pct_change().dropna()
    streak = best = 0
    for v in m:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    return {"total": (nav.iloc[-1] / nav.iloc[0] - 1) * 100, "cagr": cagr * 100,
            "mdd": mdd * 100, "calmar": (cagr / abs(mdd)) if mdd < 0 else float("nan"),
            "月胜率": (m > 0).mean() * 100 if len(m) else 0,
            "达标月": (m >= 0.012).mean() * 100 if len(m) else 0,
            "最差月": m.min() * 100 if len(m) else 0, "连亏月": best, "days": len(nav)}


def main() -> int:
    # ── A. 核心仓 8.5 年（10 只，2018 起）──
    nav = core_nav(CORE18, "2018-01-01", "2026-10-16", 60, start_after=250)
    nav = nav / nav.iloc[0]
    b = load(BENCH, "2018-01-01", "2026-10-16")
    b = b / b.iloc[0]
    b = b.reindex(nav.index).ffill()
    m, bm = metr(nav), metr(b)

    print("=" * 100)
    print(f"核心仓 8.5 年全周期（{nav.index[0]} → {nav.index[-1]}，{len(nav)} 日）")
    print(f"标的：{'、'.join(CORE18)}")
    print("=" * 100)
    print(f"  {'方案':<22}{'累计':>10}{'年化':>9}{'回撤':>9}{'卡玛':>8}"
          f"{'月胜率':>9}{'达标月':>9}{'最差月':>9}{'连亏':>6}")
    print("  " + "-" * 86)
    for name, mm in (("核心仓 10 只等权", m), ("沪深300", bm)):
        print(f"  {name:<22}{mm['total']:>+9.1f}%{mm['cagr']:>+8.1f}%{mm['mdd']:>+8.1f}%"
              f"{mm['calmar']:>8.2f}{mm['月胜率']:>8.1f}%{mm['达标月']:>8.1f}%"
              f"{mm['最差月']:>+8.1f}%{mm['连亏月']:>6}")

    print()
    print("=" * 100)
    print("逐年（跨越 2018 熊 / 2019-20 牛 / 2021 震荡 / 2022 熊 / 2023 / 2024-25 牛 / 2026）")
    print("=" * 100)
    print(f"  {'年份':<8}{'核心仓':>12}{'沪深300':>12}{'超额':>10}")
    print("  " + "-" * 44)
    for y in ("2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"):
        seg = nav[nav.index.str.startswith(y)]
        segb = b[b.index.str.startswith(y)]
        if len(seg) < 20:
            continue
        sr = (seg.iloc[-1] / seg.iloc[0] - 1) * 100
        br = (segb.iloc[-1] / segb.iloc[0] - 1) * 100
        print(f"  {y:<8}{sr:>+11.1f}%{br:>+11.1f}%{sr-br:>+9.1f}pp")

    # ── B. 与 2022-2026（含中国移动 11 只）对照 ──
    print()
    nav2 = core_nav(CORE_ALL, "2022-04-01", "2026-10-16", 60, start_after=60)
    nav2 = nav2 / nav2.iloc[0]
    m2 = metr(nav2)
    seg = nav[(nav.index >= "2022-04-01")]
    seg = seg / seg.iloc[0]
    m1 = metr(seg)
    segb = b[(b.index >= "2022-04-01")]
    segb = segb / segb.iloc[0]
    mb = metr(segb)
    print("=" * 100)
    print("2022-04 ~ 2026-10（4.5 年含熊市）：10 只 vs 11 只（含中国移动）")
    print("=" * 100)
    print(f"  {'方案':<24}{'累计':>10}{'年化':>9}{'回撤':>9}{'卡玛':>8}{'连亏':>6}")
    print("  " + "-" * 60)
    for name, mm in (("核心 10 只", m1), ("核心 11 只（含移动）", m2), ("沪深300", mb)):
        print(f"  {name:<24}{mm['total']:>+9.1f}%{mm['cagr']:>+8.1f}%{mm['mdd']:>+8.1f}%"
              f"{mm['calmar']:>8.2f}{mm['连亏月']:>6}")

    # ── C. 最终定论 ──
    print()
    print("=" * 100)
    print("定论")
    print("=" * 100)
    print(f"  核心仓 8.5 年：年化 {m['cagr']:+.1f}%，最大回撤 {m['mdd']:+.1f}%，"
          f"卡玛 {m['calmar']:.2f}，最长连亏 {m['连亏月']} 个月")
    print(f"  沪深300 同区间：年化 {bm['cagr']:+.1f}%，最大回撤 {bm['mdd']:+.1f}%，"
          f"卡玛 {bm['calmar']:.2f}，最长连亏 {bm['连亏月']} 个月")
    print(f"  → 年化高 {m['cagr']-bm['cagr']:+.1f}pp，回撤 {m['mdd']-bm['mdd']:+.1f}pp，"
          f"卡玛 {m['calmar']-bm['calmar']:+.2f}")
    print()
    print(f"  【对用户目标的检验】")
    print(f"    回撤 ≤20%：{'✅' if m['mdd'] >= -20 else '❌'} ({m['mdd']:+.1f}%)")
    print(f"    年化 15~25%：{'✅' if m['cagr'] >= 15 else '❌'} ({m['cagr']:+.1f}%)")
    print(f"    月化 ≥1.2% 的月份占比：{m['达标月']:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
