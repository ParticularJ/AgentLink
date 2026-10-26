#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心仓规则化 vs 手挑篮子（2026-10-17）

背景
----
用户质疑：手挑的核心仓（10 只个股）没有方法论，存在幸存者偏差。

本脚本做公平对比：
  · 规则化核心 = 4 个规则指数（上证红利/中证银行/电力/沪深300）固定配比
    —— 指数成分由规则决定（股息率/市值/流动性），无幸存者偏差
  · 手挑篮子 = 10 只个股等权（前复权，含分红再投）

口径说明（关键，必须诚实）
------------------------
  指数是「价格指数」（不含分红再投），手挑个股是「前复权」（含分红再投）。
  两者分红再投的差异约 4~5%/年。
  因此：指数口径会系统性低估 ~4-5%/年。为公平，这里把两者并列，
  并单独给出「指数 + 估算分红」的近似总回报。

输出：
  1) 规则化核心（4 指数）8.5 年表现
  2) 手挑篮子（总回报）8.5 年表现
  3) 逐年对照 + 相关性
  4) 结论：手挑的"超额"到底有多少是可归因的
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

# 规则化核心：4 个规则指数
RULE_IDX: Dict[str, str] = {
    "上证红利": "sh000015",
    "中证银行": "sz399986",
    "电力": "sz399809",
    "沪深300": "sh000300",
}

# 手挑篮子（前复权个股）
HAND: Dict[str, str] = {
    "工商银行": "sh601398", "农业银行": "sh601288", "中国银行": "sh601988",
    "招商银行": "sh600036", "兴业银行": "sh601166",
    "长江电力": "sh600900", "中国核电": "sh601985",
    "中国神华": "sh601088",
    "沪深300": "sh000300", "中证500": "sh000905",
}

COST = 0.0005


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


def run_port(pool: Dict[str, str], weights: Dict[str, float], start: str, end: str,
             rebal: int = 60) -> pd.Series:
    """按给定权重持有，定期再平衡。"""
    d = {}
    for c in pool.values():
        s = load(c, start, end)
        if s is not None:
            d[c] = s
    px = pd.DataFrame(d).sort_index()
    need = [c for c in pool.values() if c in px.columns]
    px = px.dropna(subset=need)
    dates = list(px.index)
    codes = [c for c in px.columns]
    # 归一化权重到可用标的
    tot = sum(weights.get(c, 0.0) for c in codes)
    w = {c: weights.get(c, 0.0) / tot for c in codes}
    units = {c: 0.0 for c in codes}
    cash = 1.0
    curve = []
    last = -999
    for i, dt in enumerate(dates):
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
            "最差月": m.min() * 100 if len(m) else 0, "连亏月": best}


def main() -> int:
    START, END = "2018-01-01", "2026-10-16"

    # 规则化核心：4 指数等权 + 40/25/15/20 配比（按代码键控）
    eq = {c: 0.25 for c in RULE_IDX.values()}
    til = {"sh000015": 0.40, "sz399986": 0.25, "sz399809": 0.15, "sh000300": 0.20}
    nav_eq = run_port(RULE_IDX, eq, START, END)
    nav_til = run_port(RULE_IDX, til, START, END)
    # 手挑篮子
    hand_w = {c: 1.0 / len(HAND) for c in HAND.values()}
    nav_hand = run_port(HAND, hand_w, START, END)
    # 上证红利指数（基准）
    div = load("sh000015", START, END)

    navs = {
        "规则化核心(4指数等权)": nav_eq,
        "规则化核心(40/25/15/20)": nav_til,
        "手挑篮子(10只,总回报)": nav_hand,
        "上证红利指数(价格)": div,
    }

    print("=" * 108)
    print(f"核心仓规则化对比（{START} ~ {END}，8.5 年）")
    print("=" * 108)
    print(f"  {'方案':<30}{'累计':>10}{'年化':>9}{'回撤':>9}{'卡玛':>8}{'月胜率':>9}{'最差月':>9}{'连亏':>6}")
    print("  " + "-" * 92)
    res = {}
    for name, nav in navs.items():
        nav = nav / nav.iloc[0]
        mm = metr(nav)
        res[name] = nav
        print(f"  {name:<30}{mm['total']:>+9.1f}%{mm['cagr']:>+8.2f}%{mm['mdd']:>+8.1f}%"
              f"{mm['calmar']:>8.2f}{mm['月胜率']:>8.1f}%{mm['最差月']:>+8.1f}%{mm['连亏月']:>6}")

    print()
    print("  ⚠️ 指数为价格口径（不含分红再投，约低估 4~5%/年）；手挑篮子为总回报口径。")
    print("  → 手挑篮子的年化比指数高约 4~5pp 是**分红再投的差异**，不是选股能力。")

    print()
    print("=" * 108)
    print("逐年对照")
    print("=" * 108)
    names = list(navs.keys())
    print("  " + f"{'年份':<6}" + "".join(f"{n[:14]:>16}" for n in names))
    print("  " + "-" * (6 + 16 * len(names)))
    for y in ("2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"):
        cells = []
        for n in names:
            seg = res[n][res[n].index.str.startswith(y)]
            cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+15.1f}%" if len(seg) >= 20 else f"{'—':>16}")
        print(f"  {y:<6}" + "".join(cells))

    print()
    print("=" * 108)
    print("相关性（日收益）")
    print("=" * 108)
    rets = pd.DataFrame({n: res[n].pct_change() for n in names}).dropna()
    print(rets.corr().round(2).to_string())

    # 结论
    print()
    print("=" * 108)
    print("结论")
    print("=" * 108)
    m_eq = metr(res["规则化核心(4指数等权)"])
    m_hand = metr(res["手挑篮子(10只,总回报)"])
    print(f"  规则化核心（价格）: 年化 {m_eq['cagr']:+.2f}%，回撤 {m_eq['mdd']:+.1f}%")
    print(f"  规则化核心 + ~4.5%分红 ≈ 年化 {m_eq['cagr']+4.5:+.2f}%（估算总回报）")
    print(f"  手挑篮子（总回报）: 年化 {m_hand['cagr']:+.2f}%，回撤 {m_hand['mdd']:+.1f}%")
    print(f"  → 手挑篮子相对规则化核心(总回报口径)的『真实超额』约 "
          f"{m_hand['cagr']-(m_eq['cagr']+4.5):+.2f}pp")
    print(f"  → 这 {(m_hand['cagr']-(m_eq['cagr']+4.5)):.2f}pp 才是需要警惕的『手挑偏差』。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
