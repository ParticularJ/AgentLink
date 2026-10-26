#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立复算子代理的两条核心统计指控（不照抄其结论）。

指控 A：84 个下行日实际只聚成 16 段连续区间 → 有效样本远小于 84
指控 B：只取每段 episode 首日（近似独立），超额降到 +2.2%、t≈1.0 不显著
指控 C：10 日窗口高度重叠（lag-1 自相关 +0.797）
"""
import pickle
import statistics
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from backtest_september import QuoteCache  # noqa: E402
from defensive_scan import load_phase_table, fwd_ret  # noqa: E402

H = 10
DOWN = ("STRONG_DOWN", "WEAK_DOWN")
TARGET = "sh515880"


def d2(s):
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def episodes(days):
    """把连续交易日聚成区间（跨周末/假期视为连续：间隔 <= 4 自然日）。"""
    eps, cur = [], [days[0]]
    for a, b in zip(days, days[1:]):
        if (d2(b) - d2(a)).days <= 4:
            cur.append(b)
        else:
            eps.append(cur)
            cur = [b]
    eps.append(cur)
    return eps


def tstat(xs):
    if len(xs) < 2:
        return float("nan")
    sd = statistics.stdev(xs)
    return statistics.mean(xs) / (sd / len(xs) ** 0.5) if sd else float("nan")


def main() -> int:
    table = load_phase_table()
    cache = QuoteCache()
    days = sorted(table)
    down = [d for d in days if table[d]["market"] in DOWN]

    ex_pairs = []
    for d in down:
        r, b = fwd_ret(cache, TARGET, d, H), fwd_ret(cache, "sh000300", d, H)
        if r is not None and b is not None:
            ex_pairs.append((d, r - b))

    eps = episodes(down)
    print("=" * 84)
    print("指控 A：下行日聚成多少段？（有效独立样本量）")
    print("=" * 84)
    print(f"  下行交易日总数          : {len(down)}")
    print(f"  聚成的连续区间(episode)  : {len(eps)}")
    print(f"  各段长度                : {sorted((len(e) for e in eps), reverse=True)}")

    exs = [x for _, x in ex_pairs]
    print(f"\n  naive（把每日当独立）: n={len(exs)}  超额均值 {statistics.mean(exs)*100:+.3f}%  "
          f"t = {tstat(exs):.2f}   ← 高估")

    # 指控 B：每段首日
    ex_by_day = dict(ex_pairs)
    first_days = [e[0] for e in eps if e[0] in ex_by_day]
    fd = [ex_by_day[d] for d in first_days]
    print(f"  每段首日（近似独立）  : n={len(fd)}  超额均值 {statistics.mean(fd)*100:+.3f}%  "
          f"t = {tstat(fd):.2f}   ← 真实显著性")
    print(f"     其中绝对收益口径    : 均值 "
          f"{statistics.mean([fwd_ret(cache, TARGET, d, H) for d in first_days])*100:+.3f}%  "
          f"t = {tstat([fwd_ret(cache, TARGET, d, H) for d in first_days]):.2f}")

    # 指控 C：重叠导致的自相关
    print("\n" + "=" * 84)
    print("指控 C：10 日持有窗口的重叠程度（自相关）")
    print("=" * 84)
    sd = statistics.pstdev(exs)
    for lag in (1, 2, 5, 9):
        n = len(exs) - lag
        if n < 5:
            continue
        m1, m2 = statistics.mean(exs[:n]), statistics.mean(exs[lag:])
        cov = sum((exs[i] - m1) * (exs[i + lag] - m2) for i in range(n)) / n
        r = cov / (sd * sd)
        print(f"  lag-{lag}: 自相关 {r:+.3f}")

    # 每段内平均（消除段内重叠的主导影响）
    seg_means = []
    for e in eps:
        vals = [ex_by_day[d] for d in e if d in ex_by_day]
        if vals:
            seg_means.append(statistics.mean(vals))
    print("\n" + "=" * 84)
    print("按「段内先平均、再跨段统计」（消除段内重叠）")
    print("=" * 84)
    print(f"  段数 {len(seg_means)}   段均值 {statistics.mean(seg_means)*100:+.3f}%   "
          f"t = {tstat(seg_means):.2f}")

    # 择时平移敏感性（复算子代理的指控 B 表）
    print("\n" + "=" * 84)
    print("择时平移敏感性（入场日 ±N 个交易日）")
    print("=" * 84)
    all_days = days
    for shift in (-5, -3, -2, -1, 0, 1, 3, 5):
        idx = {d: i for i, d in enumerate(all_days)}
        vals = []
        for d in [x for x, _ in ex_pairs]:
            i = idx.get(d)
            if i is None:
                continue
            j = i + shift
            if 0 <= j < len(all_days):
                r, b = fwd_ret(cache, TARGET, all_days[j], H), fwd_ret(cache, "sh000300", all_days[j], H)
                if r is not None and b is not None:
                    vals.append(r - b)
        if vals:
            print(f"  平移 {shift:+d}d : 超额 {statistics.mean(vals)*100:>+7.3f}%   n={len(vals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
