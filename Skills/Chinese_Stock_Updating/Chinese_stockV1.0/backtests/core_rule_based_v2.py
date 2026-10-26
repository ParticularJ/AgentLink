#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心仓规则化 v2：行业匹配的规则指数 vs 手挑篮子（2026-10-17）

修正 v1 的两处错误：
  1) sz399809 误标为「电力」，实际是「保险主题」→ 换成正确的上证公用 sh000041
  2) 手挑篮子含煤炭(中国神华)/公用(长江电力等)，规则化版需行业匹配

行业匹配设计
------------
手挑篮子 10 只的行业构成（前复权，总回报）：
  银行 50%（5 只）+ 公用 20%（长江电力/中国核电）+ 煤炭 10%（中国神华）+ 宽基 20%（沪深300/中证500）

规则化版本（指数，价格口径）：
  中证银行 sz399986 50%
  上证公用 sh000041 20%
  中证煤炭 sz399998 10%
  沪深300  sh000300  20%

这样两者行业暴露一致，差异只来自「个股挑选 vs 指数」+「分红再投 vs 价格」。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))

CACHE_LONG = HERE / "cache_long"
CACHE = HERE / "cache"
COST = 0.0005

# 规则化核心（行业匹配）
RULE: Dict[str, float] = {
    "sz399986": 0.50,  # 中证银行
    "sh000041": 0.20,  # 上证公用
    "sz399998": 0.10,  # 中证煤炭
    "sh000300": 0.20,  # 沪深300
}
RULE_NAME = "规则化核心(银行50/公用20/煤炭10/宽基20)"

# 手挑篮子
HAND: Dict[str, str] = {
    "工商银行": "sh601398", "农业银行": "sh601288", "中国银行": "sh601988",
    "招商银行": "sh600036", "兴业银行": "sh601166",
    "长江电力": "sh600900", "中国核电": "sh601985",
    "中国神华": "sh601088",
    "沪深300": "sh000300", "中证500": "sh000905",
}


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


def run_weighted(weights: Dict[str, float], start: str, end: str, rebal: int = 60) -> pd.Series:
    d = {}
    for c in weights:
        s = load(c, start, end)
        if s is not None:
            d[c] = s
    px = pd.DataFrame(d).sort_index()
    need = [c for c in weights if c in px.columns]
    px = px.dropna(subset=need)
    codes = list(px.columns)
    tot = sum(weights[c] for c in codes)
    w = {c: weights[c] / tot for c in codes}
    units = {c: 0.0 for c in codes}
    cash = 1.0
    curve = []
    last = -999
    for i, dt in enumerate(px.index):
        v = cash + sum(u * px[c].iloc[i] for c, u in units.items())
        curve.append(v)
        if i == 0 or (i - last) >= rebal:
            last = i
            for c in codes:
                tgt = v * w[c]
                cur = units[c] * px[c].iloc[i]
                delta = tgt - cur
                if abs(delta) > v * 0.02:
                    cash -= delta + abs(delta) * COST
                    units[c] += delta / px[c].iloc[i]
    return pd.Series(curve, index=px.index)


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
            "最差月": m.min() * 100 if len(m) else 0, "连亏月": best}


def main() -> int:
    START, END = "2018-01-01", "2026-10-16"
    nav_rule = run_weighted(RULE, START, END)
    hand_w = {c: 1.0 / len(HAND) for c in HAND.values()}
    nav_hand = run_weighted(hand_w, START, END)
    nav_300 = load("sh000300", START, END)

    navs = {RULE_NAME: nav_rule, "手挑篮子(10只,总回报)": nav_hand, "沪深300": nav_300}
    print("=" * 104)
    print(f"行业匹配的规则化核心 vs 手挑篮子（{START} ~ {END}）")
    print("=" * 104)
    print(f"  {'方案':<32}{'累计':>10}{'年化':>9}{'回撤':>9}{'卡玛':>8}{'月胜率':>9}{'最差月':>9}{'连亏':>6}")
    print("  " + "-" * 94)
    res = {}
    for name, nav in navs.items():
        nav = nav / nav.iloc[0]
        m = metr(nav)
        res[name] = nav
        print(f"  {name:<32}{m['total']:>+9.1f}%{m['cagr']:>+8.2f}%{m['mdd']:>+8.1f}%"
              f"{m['calmar']:>8.2f}{m['月胜率']:>8.1f}%{m['最差月']:>+8.1f}%{m['连亏月']:>6}")

    print()
    print("  ⚠️ 指数为价格口径（不含分红再投）；手挑个股为前复权（含分红再投）。")
    print("  手挑篮子的行业=银行50%+公用20%+煤炭10%+宽基20%，与规则化版一一对应。")

    print()
    print("  逐年：")
    names = list(navs.keys())
    print("  " + f"{'年份':<6}" + "".join(f"{n[:16]:>18}" for n in names))
    print("  " + "-" * (6 + 18 * len(names)))
    for y in ("2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"):
        cells = []
        for n in names:
            seg = res[n][res[n].index.str.startswith(y)]
            cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+17.1f}%" if len(seg) >= 20 else f"{'—':>18}")
        print(f"  {y:<6}" + "".join(cells))

    m_rule = metr(res[RULE_NAME])
    m_hand = metr(res["手挑篮子(10只,总回报)"])
    m_300 = metr(res["沪深300"])
    print()
    print("=" * 104)
    print("结论（关键）")
    print("=" * 104)
    print(f"  规则化核心（价格口径）: 年化 {m_rule['cagr']:+.2f}%，回撤 {m_rule['mdd']:+.1f}%")
    print(f"  + 估算分红 ~4.5%/年     : 年化 ≈ {m_rule['cagr']+4.5:+.2f}%（总回报口径）")
    print(f"  手挑篮子（总回报口径）  : 年化 {m_hand['cagr']:+.2f}%，回撤 {m_hand['mdd']:+.1f}%")
    print(f"  沪深300（价格口径）     : 年化 {m_300['cagr']:+.2f}%，回撤 {m_300['mdd']:+.1f}%")
    gap = m_hand['cagr'] - (m_rule['cagr'] + 4.5)
    print()
    print(f"  → 手挑篮子相对规则化核心的『手挑超额』≈ {gap:+.2f}pp/年")
    print(f"  → 这部分超额是幸存者偏差，不可复现，不能作为预期收益。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
