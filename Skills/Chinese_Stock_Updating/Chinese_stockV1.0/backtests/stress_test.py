#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""压力测试：把候选方案放到**多段不同行情**里检验，而不是只看一段。

背景（2026-10-16）
------------------
此前的结论都建立在 2024-02 ~ 2026-09 这一条**偏强**行情上：
半导体 +156%~182%、黄金 +86%。一个"全部 ETF 等权"方案在这段里跑出 +20.3%，
但那很可能只是"恰好持有了当年最强的两个主题"。

本脚本做三件事：
  T1 分段检验：把样本切成若干段，逐段跑，看结论是否只在某一段成立
  T2 严格引擎复算：用带 T+1/涨跌停/整手/现金约束的引擎重跑（strict_engine）
  T3 参数敏感性：债券底仓 / 单标的上限 / 再平衡频率 变化时结论是否稳定
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from allocation_engine import CACHE  # noqa: E402
from strict_engine import (Market, is_etf, load_market, metrics,  # noqa: E402
                           run_strict)

# 候选资产：红利（现金流）/ 宽基（贝塔）/ 黄金（抗通胀）/ 债券（降波动）
DIV = ["sh515180", "sh563020", "sh515300"]
BROAD = ["sh510300"]
GOLD = ["sh518880"]
BOND = ["sh511260", "sh511010"]


def position_score(s: pd.Series, i: int, lookback: int = 500) -> float:
    """0~1，越大越便宜（只用历史，无未来函数）。"""
    lo = max(0, i - lookback)
    win = s.iloc[lo:i + 1].dropna()
    if len(win) < 100:
        return 0.5
    cur = win.iloc[-1]
    hi, low = win.max(), win.min()
    rng = hi - low
    pct = (cur - low) / rng if rng > 0 else 0.5
    dd = cur / hi - 1.0
    ma = win.mean()
    dev = cur / ma - 1.0
    return max(0.0, min(1.0, (1 - pct) * 0.4 + min(1.0, abs(dd) / 0.30) * 0.35
                       + min(1.0, max(0.0, -dev) / 0.20) * 0.25))


def make_target(bond_floor: float = 0.30, risk_cap: float = 0.70,
                tilt: float = 0.8, per_asset_cap: float = 0.25):
    """估值倾斜配置：把风险预算按"便宜程度"分配，债券托底。"""
    def _fn(i: int, mkt: Market) -> Dict[str, float]:
        close = mkt.close
        groups = {}
        for name, codes in (("div", DIV), ("broad", BROAD), ("gold", GOLD)):
            cs = [c for c in codes if c in close.columns]
            if not cs:
                continue
            # 组内等权合成一条净值
            parts = []
            for c in cs:
                s = close[c].iloc[:i + 1].dropna()
                if len(s) > 100:
                    parts.append(s / s.iloc[0])
            if not parts:
                continue
            nav = parts[0]
            for p in parts[1:]:
                nav = nav + p
            nav = nav / len(parts)
            groups[name] = (nav, cs)
        if not groups:
            return {}
        scores = {k: position_score(v[0], len(v[0]) - 1) for k, v in groups.items()}
        base = {"div": 0.45, "broad": 0.25, "gold": 0.30}
        raw = {k: base[k] * (1 + tilt * (scores[k] - 0.5) * 2) for k in groups}
        tot = sum(raw.values()) or 1.0
        budget = min(risk_cap, 1.0 - bond_floor - 0.05)
        w: Dict[str, float] = {}
        for k, (nav, cs) in groups.items():
            share = raw[k] / tot * budget
            per = share / len(cs)
            for c in cs:
                w[c] = min(per, per_asset_cap)
        # 债券
        bcodes = [c for c in BOND if c in close.columns]
        if bcodes:
            for c in bcodes:
                w[c] = bond_floor / len(bcodes)
        return w
    return _fn


def make_equal(codes: List[str]):
    def _fn(i: int, mkt: Market) -> Dict[str, float]:
        cs = [c for c in codes if c in mkt.close.columns]
        return {c: 1.0 / len(cs) for c in cs} if cs else {}
    return _fn


def run_segment(mkt: Market, label: str, fn, rebal: int, **kw) -> dict:
    r = run_strict(mkt, fn, rebal=rebal, label=label, **kw)
    m = metrics(r.nav, label)
    m["调仓次数"] = r.trades
    m["被拒"] = sum(r.rejected.values())
    m["成本"] = r.cost_paid
    m["最大仓位"] = r.max_leverage_seen * 100
    return m


def print_rows(rows: List[dict], title: str):
    print(f"\n{title}")
    print(f"  {'方案':<28}{'年化':>9}{'最大回撤':>10}{'月胜率':>8}{'达标≥1.2%':>11}"
          f"{'达标≥2%':>9}{'最差月':>9}{'连亏':>6}{'调仓':>6}{'被拒':>6}")
    print("  " + "-" * 100)
    for m in rows:
        print(f"  {m['label']:<28}{m['cagr']:>+8.1f}%{m['mdd']:>+9.1f}%{m['月胜率']:>7.1f}%"
              f"{m['达标月(≥1.2%)']:>10.1f}%{m['月达标(≥2%)']:>8.1f}%{m['最差月']:>+8.1f}%"
              f"{m['连亏月']:>6}{m['调仓次数']:>6}{m['被拒']:>6}")


def main() -> int:
    # 先把可用区间摸清
    probe = load_market(sorted(set(DIV + BROAD + GOLD + BOND)), "2022-01-01", "2026-10-16")
    if probe is None:
        print("数据不足")
        return 1
    best_start = None
    for c in probe.close.columns:
        s = probe.close[c].dropna()
        if len(s) > 200:
            st = s.index[0]
            best_start = st if best_start is None else max(best_start, st)
    print(f"全部候选资产都有数据的起始日：{best_start}")
    print(f"（全库最早 {probe.close.index[0]}，最晚 {probe.close.index[-1]}）\n")

    segments = [
        ("全区间", best_start, "2026-09-30"),
        ("2026 年", "2026-01-01", "2026-09-30"),
        ("2025 年", "2025-01-01", "2025-12-31"),
    ]

    for seg_name, s0, s1 in segments:
        mkt = load_market(sorted(set(DIV + BROAD + GOLD + BOND)), s0, s1, min_rows=100)
        if mkt is None or len(mkt.close) < 150:
            print(f"\n[{seg_name}] 样本不足，跳过（{0 if mkt is None else len(mkt.close)} 日）")
            continue
        print("=" * 104)
        print(f"[{seg_name}] {mkt.close.index[0]} → {mkt.close.index[-1]}（{len(mkt.close)} 个交易日）")
        print("=" * 104)
        rows = []
        for rebal, tag in ((20, "月度"), (60, "季度")):
            rows.append(run_segment(mkt, f"估值倾斜配置（{tag}）", make_target(), rebal))
            rows.append(run_segment(mkt, f"红利+宽基+黄金+债 等权（{tag}）",
                                    make_equal(sorted(set(DIV + BROAD + GOLD + BOND))), rebal))
        # 买入持有对照
        for code, name in (("sh510300", "沪深300ETF"), ("sh515180", "红利ETF"), ("sh518880", "黄金ETF")):
            if code in mkt.close.columns:
                s = mkt.close[code].dropna()
                if len(s) > 100:
                    m = metrics(s / s.iloc[0] * 100000, f"{name} 买入持有")
                    m.update({"调仓次数": 0, "被拒": 0, "成本": 0, "最大仓位": 100.0})
                    rows.append(m)
        print_rows(rows, f"[{seg_name}] 结果")

    print()
    print("=" * 104)
    print("参数敏感性（全区间，月度再平衡）")
    print("=" * 104)
    mkt = load_market(sorted(set(DIV + BROAD + GOLD + BOND)), best_start, "2026-09-30")
    rows = []
    for bf in (0.20, 0.30, 0.40):
        for cap in (0.20, 0.25, 0.35):
            rows.append(run_segment(mkt, f"债券底仓{bf:.0%}·单只上限{cap:.0%}",
                                    make_target(bond_floor=bf, per_asset_cap=cap), 20))
    print_rows(rows, "参数敏感性")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
