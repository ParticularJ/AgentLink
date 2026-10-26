#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归因：为什么严格引擎（+7.4%）比宽松引擎（+20.4%）低 13 个百分点？

两种可能：
  H1 执行约束（T+1 / 涨跌停 / 整手 / 现金约束）吃掉了收益
  H2 资产池不同 —— 宽松引擎用的是 57 只行业 ETF（含半导体/黄金大牛），
     严格引擎用的是红利+宽基+黄金+债（保守组合）

做法：**用同一个资产池、同一个目标函数，分别在两个引擎里跑**，从而分离两者。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from allocation_engine import CACHE, load_prices  # noqa: E402
from allocation_engine import backtest as loose_backtest, metrics as loose_metrics  # noqa: E402
from strict_engine import Market, load_market, metrics as strict_metrics, run_strict  # noqa: E402

START, END = "2024-02-26", "2026-09-30"
POOL_A = ["sh515180", "sh563020", "sh515300", "sh510300", "sh518880", "sh511260", "sh511010"]
POOL_B = ["sh512480", "sz159995", "sh515980", "sh515880", "sh518880", "sh510300",
          "sh516150", "sz159779", "sh512660", "sh516220", "sh512690", "sz159996"]


def target_equal(codes: List[str]):
    """同一权重规则，两种签名（旧引擎传 bucket-navs，新引擎传 Market）。"""
    def _loose(i, navs, cur) -> Dict[str, float]:
        return {c: 1.0 / len(codes) for c in codes}

    def _strict(i, mkt: Market) -> Dict[str, float]:
        cs = [c for c in codes if c in mkt.close.columns]
        return {c: 1.0 / len(cs) for c in cs} if cs else {}
    return _loose, _strict


def loose_run(px, fn, rebal=20, label=""):
    """用旧引擎（宽松：无 T+1/涨跌停/整手）跑。

    注意：旧引擎的 target_fn 签名是 (i, navs, cur)，navs 按 bucket 组织；
    这里权重只按代码给，引擎里查不到的 bucket 自然为 0。
    为让代码级权重生效，这里把代码包装成单代码 bucket。
    """
    import allocation_engine as ae
    wrapped = {}
    for c in px.columns:
        wrapped[c] = {c: 1.0}
    saved = ae.BUCKETS
    ae.BUCKETS = wrapped
    try:
        r = loose_backtest(px, fn, rebal, label)
    finally:
        ae.BUCKETS = saved
    m = loose_metrics(r)
    m["调仓次数"] = r.trades
    m["被拒"] = 0
    m["成本"] = r.cost_paid
    return m


def strict_run(mkt, fn, rebal=20, label=""):
    r = run_strict(mkt, fn, rebal=rebal, label=label)
    m = strict_metrics(r.nav, label)
    m["调仓次数"] = r.trades
    m["被拒"] = sum(r.rejected.values())
    m["成本"] = r.cost_paid
    return m


def show(rows, title):
    print(f"\n{title}")
    print(f"  {'方案':<34}{'年化':>9}{'最大回撤':>10}{'月胜率':>8}{'最差月':>9}"
          f"{'调仓':>6}{'被拒':>6}{'成本':>8}")
    print("  " + "-" * 92)
    for m in rows:
        print(f"  {m['label']:<34}{m['cagr']:>+8.1f}%{m['mdd']:>+9.1f}%{m['月胜率']:>7.1f}%"
              f"{m['最差月']:>+8.1f}%{m['调仓次数']:>6}{m['被拒']:>6}{m['成本']:>8,.0f}")


def main() -> int:
    rows = []
    for pool_name, pool in (("池A 保守(红利+宽基+黄金+债)", POOL_A),
                            ("池B 进攻(行业主题+黄金+宽基)", POOL_B)):
        fl, fs = target_equal(pool)
        # 宽松引擎
        px = load_prices(pool, START, END)
        if px is not None:
            rows.append(loose_run(px, fl, 20, f"{pool_name} · 宽松引擎"))
        # 严格引擎
        mkt = load_market(pool, START, END, min_rows=200)
        if mkt is not None:
            rows.append(strict_run(mkt, fs, 20, f"{pool_name} · 严格引擎"))
    show(rows, f"同一资产池 × 两个引擎（{START} → {END}，月度再平衡）")

    print()
    print("=" * 96)
    print("结论：两处差异各自的贡献")
    print("=" * 96)
    if len(rows) == 4:
        a_l, a_s, b_l, b_s = rows
        print(f"  池A（保守）  宽松 {a_l['cagr']:+.1f}%  →  严格 {a_s['cagr']:+.1f}%"
              f"   差值 {a_s['cagr']-a_l['cagr']:+.1f}pp  ← 执行约束的影响")
        print(f"  池B（进攻）  宽松 {b_l['cagr']:+.1f}%  →  严格 {b_s['cagr']:+.1f}%"
              f"   差值 {b_s['cagr']-b_l['cagr']:+.1f}pp  ← 执行约束的影响")
        print(f"  同为宽松引擎：池A {a_l['cagr']:+.1f}%  vs  池B {b_l['cagr']:+.1f}%"
              f"   差值 {b_l['cagr']-a_l['cagr']:+.1f}pp  ← 资产池的影响")
        print(f"  同为严格引擎：池A {a_s['cagr']:+.1f}%  vs  池B {b_s['cagr']:+.1f}%"
              f"   差值 {b_s['cagr']-a_s['cagr']:+.1f}pp  ← 资产池的影响")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
