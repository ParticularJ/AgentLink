#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""防守通道诊断：大盘 STRONG_DOWN / WEAK_DOWN 期间，防守 ETF 是否真的抗跌？

为什么需要这个诊断
------------------
`collect_defensive_etf_recommendations()` 在 STRONG_DOWN 日的候选集几乎是**常数**
（只要底仓/贵金属/券商三个板块存在，就固定推出它们的 ETF）。
也就是说这条通道**没有日内区分度**——它唯一的价值来自一个无条件命题：

    "大盘下行期间，防守型 ETF（红利/黄金）的远期表现优于其他标的"

所以必须先把这个问题量化清楚，再看组合层面的效果。
若这个无条件命题不成立，组合层面大概率也不会成立（这正是 backtests/README
反复记录的规律：「某个群体的无条件表现更好」推不出「加进组合会更好」）。

方法：非重叠抽样（每 10 个交易日取 1 个），避免重叠窗口高估样本量
（backtests/README §2.4 记录过这个坑）。
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from backtest_september import QuoteCache, daily_phases  # noqa: E402

DEFENSIVE = {
    'sh515180': '红利ETF易方达',
    'sh563020': '红利低波ETF易方达',
    'sh515300': '300红利低波ETF嘉实',
    'sh518880': '黄金ETF华安',
    'sh512070': '沪深300非银ETF',
}
OTHER_ETFS = ['sh512480', 'sz159995', 'sh515980', 'sz159992', 'sh512660',
              'sh516160', 'sh512690', 'sh516150', 'sh515220']
START, END = "2025-09-30", "2026-09-30"
STRIDE = 10          # 非重叠抽样间隔
HORIZON = 10         # 远期收益窗口（与生产 EXIT_MAX_HOLD_DAYS 一致）


def fwd_return(cache: QuoteCache, code: str, day: str, n: int):
    rows = cache.forward(code, day, n)
    if len(rows) < n:
        return None
    base = cache.bar(code, day)
    if not base or float(base["close"]) <= 0:
        return None
    return float(rows[-1]["close"]) / float(base["close"]) - 1.0


def main() -> int:
    cache = QuoteCache()
    days = cache.days_between(START, END)
    sampled = days[::STRIDE]
    print(f"区间 {START} → {END}：{len(days)} 个交易日，非重叠抽样 {len(sampled)} 个（每 {STRIDE} 日取 1）\n")

    # 大盘档位分布（全量 + 抽样）
    dist_all, dist_smp = defaultdict(int), defaultdict(int)
    for d in days:
        dist_all[daily_phases(cache, d)[0]] += 1
    print("大盘档位分布（全量 / 抽样）：")
    for ph in ("STRONG_UP", "WAVE_UP", "RANGE", "WEAK_DOWN", "STRONG_DOWN", "UNKNOWN"):
        if dist_all.get(ph):
            print(f"  {ph:12s} {dist_all[ph]:>4} 日")

    # 下行档 vs 其他档 的远期收益
    print(f"\n未来 T+{HORIZON} 收益（非重叠抽样，均值 / 上涨率 / 样本）：")
    print(f"  {'标的':<22}{'下行档':>26}{'其他档':>26}")
    print("  " + "-" * 74)

    for group, codes in (("防守 ETF", DEFENSIVE), ("对照：其他 ETF", {c: c for c in OTHER_ETFS})):
        print(f"  ── {group} ──")
        for code, name in codes.items():
            dn, ot = [], []
            for d in sampled:
                r = fwd_return(cache, code, d, HORIZON)
                if r is None:
                    continue
                ph = daily_phases(cache, d)[0]
                (dn if ph in ("STRONG_DOWN", "WEAK_DOWN") else ot).append(r)
            def fmt(xs):
                if not xs:
                    return f"{'—':>26}"
                up = sum(1 for x in xs if x > 0) / len(xs) * 100
                return f"{statistics.mean(xs)*100:>+8.2f}% / {up:>5.1f}% / n={len(xs):<3}"
            print(f"  {name:<22}{fmt(dn)}{fmt(ot)}")

    # 汇总
    print("\n  ── 汇总 ──")
    for label, codes in (("防守 ETF", list(DEFENSIVE)), ("其他 ETF", OTHER_ETFS)):
        dn, ot = [], []
        for d in sampled:
            ph = daily_phases(cache, d)[0]
            for code in codes:
                r = fwd_return(cache, code, d, HORIZON)
                if r is None:
                    continue
                (dn if ph in ("STRONG_DOWN", "WEAK_DOWN") else ot).append(r)
        if dn:
            up_dn = sum(1 for x in dn if x > 0) / len(dn) * 100
            up_ot = sum(1 for x in ot if x > 0) / len(ot) * 100 if ot else 0
            print(f"  {label:<12} 下行档 T+{HORIZON} 均值 {statistics.mean(dn)*100:>+7.2f}%  "
                  f"上涨率 {up_dn:>5.1f}%  n={len(dn)}")
            print(f"  {'':<12} 其他档 T+{HORIZON} 均值 {statistics.mean(ot)*100:>+7.2f}%  "
                  f"上涨率 {up_ot:>5.1f}%  n={len(ot)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
