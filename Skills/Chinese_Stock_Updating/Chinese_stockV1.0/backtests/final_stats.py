#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终策略·完整统计（用于撰写架构与回测报告）

产出：
  A. 8.5 年全周期核心仓表现（含逐月分布、回撤明细）
  B. 各标的贡献拆解
  C. 4.5 年含熊市、与卫星仓/趋势过滤的对照
  D. 与用户目标的逐项对账
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))

CACHE_LONG = HERE / "cache_long"
CACHE = HERE / "cache"
BENCH = "sh000300"
COST = 0.0005

CORE18: Dict[str, str] = {
    "工商银行": "sh601398", "农业银行": "sh601288", "中国银行": "sh601988",
    "招商银行": "sh600036", "兴业银行": "sh601166",
    "长江电力": "sh600900", "中国核电": "sh601985",
    "中国神华": "sh601088",
    "沪深300": "sh000300", "中证500": "sh000905",
}
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


def core_run(pool: Dict[str, str], start: str, end: str, rebal: int = 60,
             start_after: int = 0) -> Tuple[pd.Series, pd.DataFrame]:
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
    return pd.Series(curve, index=dates), px


def metr(nav: pd.Series) -> dict:
    ny = len(nav) / 242
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / ny) - 1
    mdd = (nav / nav.cummax() - 1).min()
    m = nav.groupby(nav.index.str[:7]).last().pct_change().dropna()
    streak = best = 0
    for v in m:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    rets = nav.pct_change().dropna()
    vol = rets.std() * (242 ** 0.5) * 100
    # 回撤恢复天数
    peak = nav.cummax()
    dd = nav / peak - 1
    return {
        "total": (nav.iloc[-1] / nav.iloc[0] - 1) * 100, "cagr": cagr * 100,
        "mdd": mdd * 100, "calmar": (cagr / abs(mdd)) if mdd < 0 else float("nan"),
        "vol": vol, "sharpe_rf0": cagr * 100 / vol if vol else float("nan"),
        "月胜率": (m > 0).mean() * 100, "达标月": (m >= 0.012).mean() * 100,
        "m2": (m >= 0.02).mean() * 100,
        "最差月": m.min() * 100, "最好月": m.max() * 100,
        "月均": m.mean() * 100, "月中位": m.median() * 100,
        "月标准差": m.std() * 100, "连亏月": best, "月数": len(m),
        "days": len(nav),
    }


def show_m(nav: pd.Series):
    """打印关键月度分布。"""
    m = nav.groupby(nav.index.str[:7]).last().pct_change().dropna()
    print(f"    月度：{len(m)} 个月 | 正收益 {(m>0).sum()} | ≥1.2% {(m>=0.012).sum()}"
          f" | ≥2% {(m>=0.02).sum()} | ≥5% {(m>=0.05).sum()}")
    print(f"    月均 {m.mean()*100:+.2f}%  中位 {m.median()*100:+.2f}%  "
          f"标准差 {m.std()*100:.2f}%  最好 {m.max()*100:+.1f}%  最差 {m.min()*100:+.1f}%")
    print(f"    最好 3 月：{', '.join(f'{k}({v*100:+.1f}%)' for k,v in m.nlargest(3).items())}")
    print(f"    最差 3 月：{', '.join(f'{k}({v*100:+.1f}%)' for k,v in m.nsmallest(3).items())}")


def main() -> int:
    print("=" * 108)
    print("A. 8.5 年全周期（2018-01 ~ 2026-10）核心仓 10 只等权")
    print("=" * 108)
    nav8, px8 = core_run(CORE18, "2018-01-01", "2026-10-16", 60, start_after=250)
    nav8 = nav8 / nav8.iloc[0]
    b = load(BENCH, "2018-01-01", "2026-10-16")
    b = (b / b.iloc[0]).reindex(nav8.index).ffill()
    m8, bm8 = metr(nav8), metr(b)
    print(f"  {'指标':<20}{'核心仓':>16}{'沪深300':>16}")
    print("  " + "-" * 52)
    for k, lbl, fmt in (("total", "累计收益", "{:+.1f}%"),
                        ("cagr", "年化收益", "{:+.2f}%"),
                        ("mdd", "最大回撤", "{:+.1f}%"),
                        ("calmar", "卡玛比率", "{:.2f}"),
                        ("vol", "年化波动率", "{:.1f}%"),
                        ("sharpe_rf0", "夏普(无风险=0)", "{:.2f}"),
                        ("月胜率", "月胜率", "{:.1f}%"),
                        ("月均", "月均收益", "{:+.2f}%"),
                        ("月中位", "月收益中位", "{:+.2f}%"),
                        ("月标准差", "月收益标准差", "{:.2f}%"),
                        ("达标月", "月≥1.2% 占比", "{:.1f}%"),
                        ("m2", "月≥2% 占比", "{:.1f}%"),
                        ("最好月", "最好月", "{:+.1f}%"),
                        ("最差月", "最差月", "{:+.1f}%"),
                        ("连亏月", "最长连亏", "{} 个月")):
        print(f"  {lbl:<20}{fmt.format(m8[k]):>16}{fmt.format(bm8[k]):>16}")
    print()
    print("  核心仓月度分布：")
    show_m(nav8)

    # 逐年
    print()
    print("  逐年（含回撤）：")
    print(f"    {'年份':<8}{'核心仓':>11}{'年内回撤':>11}{'沪深300':>11}{'指数回撤':>11}")
    print("    " + "-" * 54)
    for y in ("2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"):
        seg = nav8[nav8.index.str.startswith(y)]
        segb = b[b.index.str.startswith(y)]
        if len(seg) < 20:
            continue
        ddm = ((seg / seg.cummax() - 1).min()) * 100
        ddb = ((segb / segb.cummax() - 1).min()) * 100
        print(f"    {y:<8}{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+10.1f}%{ddm:>+10.1f}%"
              f"{(segb.iloc[-1]/segb.iloc[0]-1)*100:>+10.1f}%{ddb:>+10.1f}%")

    # ── B. 各标的贡献 ──
    print()
    print("=" * 108)
    print("B. 各标的 8.5 年区间表现（买入持有）")
    print("=" * 108)
    print(f"  {'标的':<10}{'代码':<10}{'累计':>10}{'年化':>9}{'最大回撤':>10}{'年化波动':>10}")
    print("  " + "-" * 62)
    rows = []
    for name, code in CORE18.items():
        s = load(code, "2018-01-01", "2026-10-16")
        if s is None:
            continue
        mm = metr(s / s.iloc[0])
        rows.append((mm["total"], name, code, mm))
    for total, name, code, mm in sorted(rows, reverse=True):
        print(f"  {name:<10}{code:<10}{mm['total']:>+9.1f}%{mm['cagr']:>+8.2f}%"
              f"{mm['mdd']:>+9.1f}%{mm['vol']:>9.1f}%")

    # ── C. 4.5 年含熊市对照 ──
    print()
    print("=" * 108)
    print("C. 4.5 年（2022-04 ~ 2026-10，含 2022 熊市）核心 11 只")
    print("=" * 108)
    nav45, px45 = core_run(CORE_ALL, "2022-04-01", "2026-10-16", 60, start_after=60)
    nav45 = nav45 / nav45.iloc[0]
    m45 = metr(nav45)
    b45 = load(BENCH, "2022-04-01", "2026-10-16")
    b45 = (b45 / b45.iloc[0]).reindex(nav45.index).ffill()
    bm45 = metr(b45)
    print(f"  {'指标':<20}{'核心11只':>16}{'沪深300':>16}")
    print("  " + "-" * 52)
    for k, lbl, fmt in (("total", "累计收益", "{:+.1f}%"), ("cagr", "年化收益", "{:+.2f}%"),
                        ("mdd", "最大回撤", "{:+.1f}%"), ("calmar", "卡玛", "{:.2f}"),
                        ("月胜率", "月胜率", "{:.1f}%"), ("达标月", "月≥1.2%", "{:.1f}%"),
                        ("最差月", "最差月", "{:+.1f}%"), ("连亏月", "最长连亏", "{} 个月")):
        print(f"  {lbl:<20}{fmt.format(m45[k]):>16}{fmt.format(bm45[k]):>16}")
    print()
    print("  逐年：")
    print(f"    {'年份':<8}{'核心11只':>12}{'沪深300':>12}")
    print("    " + "-" * 34)
    for y in ("2022", "2023", "2024", "2025", "2026"):
        seg = nav45[nav45.index.str.startswith(y)]
        segb = b45[b45.index.str.startswith(y)]
        if len(seg) < 20:
            continue
        print(f"    {y:<8}{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+11.1f}%"
              f"{(segb.iloc[-1]/segb.iloc[0]-1)*100:>+11.1f}%")

    # ── D. 目标对账 ──
    print()
    print("=" * 108)
    print("D. 与用户目标对账（以 8.5 年为准）")
    print("=" * 108)
    checks = [
        ("最大回撤 ≤20%", f"{m8['mdd']:+.1f}%", m8["mdd"] >= -20),
        ("年化 15~25%", f"{m8['cagr']:+.1f}%", 15 <= m8["cagr"] <= 25),
        ("月化 1.2%~1.9%", f"月均 {m8['月均']:+.2f}%", 1.2 <= m8["月均"] <= 1.9),
        ("多数月份 ≥1.2%", f"{m8['达标月']:.0f}% 的月份", m8["达标月"] >= 50),
        ("1~2 个月内回本", f"最长连亏 {m8['连亏月']} 个月", m8["连亏月"] <= 2),
    ]
    for lbl, val, ok in checks:
        print(f"  {'✅' if ok else '❌'}  {lbl:<24}实测 {val}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
