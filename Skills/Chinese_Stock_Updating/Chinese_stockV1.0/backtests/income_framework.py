#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「好资产拿住 + 分红再投 + 低位加仓 + 低换手」能否量化为执行框架？

用户问题（2026-10-16）：
  Q1 这个策略可以量化为执行框架吗？
  Q2 盈利周期多久、年化多少、有效盈亏比（含胜率）多少？
  Q3 遇到 2025 这种科技大行情还有效吗（寒武纪 / 中际旭创）？

本脚本用 backtests/cache 的真实前复权数据把这三个问题量化。
不引入任何未来函数：所有再平衡只在每月最后一个交易日按当日已知信息决定。
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"

# 组合定义（全部用缓存里真实存在的标的）
DIVIDEND_BASKET = ["sh515180", "sh563020", "sh515300"]          # 红利/红利低波
GOLD = "sh518880"
BENCH = "sh000300"
TECH_SINGLE = {"sh688256": "寒武纪", "sz300308": "中际旭创"}


def load(sym: str, start="2023-01-01", end="2026-09-30"):
    p = CACHE / f"{sym}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = df["date"].astype(str).str[:10]
    df = df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)
    return df if len(df) > 30 else None


def series(sym, start="2023-01-01", end="2026-09-30"):
    df = load(sym, start, end)
    if df is None:
        return None
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def metrics(nav: pd.Series, label: str, years: float) -> dict:
    """年化 / 最大回撤 / 波动 / 卡玛。"""
    tot = nav.iloc[-1] / nav.iloc[0] - 1
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1 if years > 0 else float("nan")
    roll_max = nav.cummax()
    dd = (nav / roll_max - 1)
    rets = nav.pct_change().dropna()
    vol = rets.std() * (242 ** 0.5)
    return {
        "label": label,
        "total": tot * 100,
        "cagr": cagr * 100,
        "mdd": dd.min() * 100,
        "vol": vol * 100,
        "calmar": (cagr / abs(dd.min())) if dd.min() < 0 else float("nan"),
        "win_days": (rets > 0).mean() * 100,
    }


def equal_weight(codes, start, end):
    ss = {c: series(c, start, end) for c in codes}
    ss = {c: s for c, s in ss.items() if s is not None}
    if not ss:
        return None
    df = pd.DataFrame(ss).dropna()
    if len(df) < 30:
        return None
    norm = df / df.iloc[0]
    return (norm.mean(axis=1)).dropna()


def main() -> int:
    START, END = "2023-01-01", "2026-09-30"
    # 交易日数以沪深300为基准
    base = series(BENCH, START, END)
    if base is None:
        print("基准数据缺失")
        return 1
    days = len(base)
    years = days / 242.0
    print(f"区间 {base.index[0]} → {base.index[-1]}，{days} 个交易日（{years:.2f} 年）\n")

    rows = []

    # 1) 基准与红利篮子
    rows.append(metrics(base / base.iloc[0], "沪深300（基准）", years))
    div = equal_weight(DIVIDEND_BASKET, START, END)
    if div is not None:
        rows.append(metrics(div, "红利篮子等权（3只）", years))
    for c in DIVIDEND_BASKET:
        s = series(c, START, END)
        if s is not None:
            rows.append(metrics(s / s.iloc[0], f"  {c}", years))

    # 2) 防守/黄金
    for c in (GOLD,):
        s = series(c, START, END)
        if s is not None:
            rows.append(metrics(s / s.iloc[0], f"黄金 {c}", years))

    # 3) 科技个股（回答 Q3）
    for c, name in TECH_SINGLE.items():
        s = series(c, START, END)
        if s is not None:
            rows.append(metrics(s / s.iloc[0], f"科技个股 {name}", years))

    print("=" * 96)
    print("表 1：各标的/组合的长期表现（前复权，买入持有）")
    print("=" * 96)
    print(f"  {'标的':<26}{'累计':>10}{'年化':>9}{'最大回撤':>10}{'年化波动':>10}{'卡玛':>8}{'日胜率':>8}")
    print("  " + "-" * 84)
    for r in rows:
        print(f"  {r['label']:<26}{r['total']:>+9.1f}%{r['cagr']:>+8.1f}%{r['mdd']:>+9.1f}%"
              f"{r['vol']:>9.1f}%{r['calmar']:>8.2f}{r['win_days']:>7.1f}%")

    # 4) 逐年分解（回答 Q1/Q2：周期多久）
    print()
    print("=" * 96)
    print("表 2：逐年收益分解（判断「多久见效」与「哪一年会失效」）")
    print("=" * 96)
    targets = {"沪深300": BENCH, "红利篮子": DIVIDEND_BASKET, "黄金": GOLD,
               "寒武纪": "sh688256", "中际旭创": "sz300308"}
    years_list = ["2023", "2024", "2025", "2026"]
    print(f"  {'组合':<14}" + "".join(f"{y:>12}" for y in years_list))
    print("  " + "-" * 62)
    for name, tgt in targets.items():
        if isinstance(tgt, list):
            nav = equal_weight(tgt, START, END)
        else:
            s = series(tgt, START, END)
            nav = s / s.iloc[0] if s is not None else None
        if nav is None:
            continue
        cells = []
        for y in years_list:
            seg = nav[nav.index.str.startswith(y)]
            if len(seg) < 5:
                cells.append(f"{'—':>12}")
            else:
                cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+11.1f}%")
        print(f"  {name:<14}" + "".join(cells))

    # 5) 「低位加仓」纪律的量化：按回撤分档加仓
    print()
    print("=" * 96)
    print("表 3：【低位加仓】的量化规则 —— 按自身回撤分档定投（月频，无未来函数）")
    print("=" * 96)

    def dd_dca(nav: pd.Series, label: str):
        """每月末看 NAV 相对其历史最高点的回撤，按档位决定当月投入权重。"""
        month_ends = nav.groupby(nav.index.str[:7]).last()
        weights, shares, cash_in, investing = [], 0.0, 0.0, 0.0
        peak = nav.iloc[0]
        # 逐月：把当月 1 单位资金按回撤档位投入
        for i, (m, px) in enumerate(month_ends.items()):
            peak = max(peak, px)
            dd = px / peak - 1
            w = 1.0 if dd > -0.10 else (2.0 if dd > -0.20 else (3.0 if dd > -0.30 else 4.0))
            weights.append(w)
        # 复利模拟：每月投入 w 单位，价格用月末
        total_units, total_invested, nav_units = 0.0, 0.0, 0.0
        peak = month_ends.iloc[0]
        curve, invested_curve = [], []
        for m, px in month_ends.items():
            peak = max(peak, px)
            dd = px / peak - 1
            w = 1.0 if dd > -0.10 else (2.0 if dd > -0.20 else (3.0 if dd > -0.30 else 4.0))
            total_units += w / px
            total_invested += w
            curve.append(total_units * px)
            invested_curve.append(total_invested)
        value = pd.Series(curve, index=month_ends.index)
        invested = pd.Series(invested_curve, index=month_ends.index)
        profit = value.iloc[-1] / invested.iloc[-1] - 1
        # 最大回撤（按市值/成本比）
        ratio = value / invested
        mdd = (ratio / ratio.cummax() - 1).min()
        avg_w = statistics.mean(weights)
        return {
            "label": label,
            "invested": invested.iloc[-1],
            "value": value.iloc[-1],
            "profit": profit * 100,
            "mdd": mdd * 100,
            "avg_w": avg_w,
            "curve": ratio,
        }

    for name, tgt in (("红利篮子", DIVIDEND_BASKET), ("沪深300", BENCH)):
        nav = equal_weight(tgt, START, END) if isinstance(tgt, list) else series(tgt, START, END)
        if isinstance(tgt, str):
            nav = nav / nav.iloc[0]
        if nav is None:
            continue
        r = dd_dca(nav, name)
        print(f"  {r['label']:<12} 累计投入 {r['invested']:.0f} 单位 → 市值 {r['value']:.1f}"
              f"   收益率 {r['profit']:>+7.1f}%   市值/成本最大回撤 {r['mdd']:>+6.1f}%"
              f"   平均加码倍数 {r['avg_w']:.2f}x")

    # 6) 与「均匀定投」对照（说明低位加仓到底有没有用）
    print()
    print("  【对照】每月等额定投（不看回撤）：")
    for name, tgt in (("红利篮子", DIVIDEND_BASKET), ("沪深300", BENCH)):
        nav = equal_weight(tgt, START, END) if isinstance(tgt, list) else series(tgt, START, END)
        if isinstance(tgt, str):
            nav = nav / nav.iloc[0]
        if nav is None:
            continue
        me = nav.groupby(nav.index.str[:7]).last()
        units = sum(1.0 / px for px in me)
        profit = (units * me.iloc[-1]) / len(me) - 1
        ratio = pd.Series([sum(1.0 / p for p in me.iloc[:i + 1]) * me.iloc[i] / (i + 1)
                           for i in range(len(me))], index=me.index)
        mdd = (ratio / ratio.cummax() - 1).min()
        print(f"    {name:<12} 收益率 {profit*100:>+7.1f}%   市值/成本最大回撤 {mdd*100:>+6.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
