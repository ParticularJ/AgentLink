#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""防守/进攻扫描的稳健性验证（复用 phase_table.pkl，秒级）。

上一轮（defensive_scan.py）发现两件事，都需要独立验证：
  1. 下行档表现最好的其实是**高弹性板块**（光通信/油气/半导体/消费电子），
     而"防守"板块（底仓/券商）排在最后 —— 与直觉相反；
  2. 窄A（300红利低波+黄金）分半验证**失败**（训练 +1.95% → 测试 -0.82%）。

本脚本做三件事：
  A. 排序稳健性：不同抽样密度（stride 5/10/20）+ 时间分半，看排名是否稳定；
  B. 候选窄版的完整分半 + bootstrap；
  C. 归因：这些标的是"下行档抗跌"，还是仅仅"波动更大"？
     （用同期市场基准做参照，而不是看绝对收益）
"""
from __future__ import annotations

import random
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from backtest_september import QuoteCache  # noqa: E402
from defensive_scan import load_phase_table, fwd_ret, boot_ci, stats  # noqa: E402

H = 10
DOWN = ("STRONG_DOWN", "WEAK_DOWN")
BENCH = "sh000300"


def mean_pct(xs):
    return statistics.mean(xs) * 100 if xs else float("nan")


def main() -> int:
    table = load_phase_table()
    cache = QuoteCache()
    days = sorted(table)
    mid = days[len(days) // 2]

    # 所有板块的 ETF（跳过无数据的）
    sectors = list(table[days[0]]["sectors"])
    etf_of = table[days[0]]["etf_of"]

    print(f"{'='*100}")
    print(f"A. 排序稳健性：不同抽样密度下「下行档均值」的排名（T+{H}）")
    print(f"{'='*100}")

    rank_tables = {}
    for stride in (5, 10, 20):
        ds = [d for d in days[::stride] if table[d]["market"] in DOWN]
        scored = []
        for sec in sectors:
            code = etf_of.get(sec)
            if not code:
                continue
            xs = [r for d in ds if (r := fwd_ret(cache, code, d, H)) is not None]
            if len(xs) >= 5:
                scored.append((sec, code, mean_pct(xs), len(xs)))
        scored.sort(key=lambda x: -x[2])
        rank_tables[stride] = {s: i + 1 for i, (s, _, _, _) in enumerate(scored)}
        print(f"\n  stride={stride}（{len(ds)} 个下行日）前 8 名：")
        for i, (sec, code, m, n) in enumerate(scored[:8], 1):
            print(f"    {i:>2}. {sec:<10}{code:<11}{m:>+7.2f}%  n={n}")
        print(f"     末 5 名：" + "、".join(f"{s}({m:+.2f}%)" for s, _, m, _ in scored[-5:]))

    # 排名一致性（spearman 近似：取共同板块的名次差）
    common = set(rank_tables[5]) & set(rank_tables[10]) & set(rank_tables[20])
    print(f"\n  三个密度的共同板块 {len(common)} 个，名次变化：")
    moved = [(s, rank_tables[5][s], rank_tables[10][s], rank_tables[20][s]) for s in common]
    moved.sort(key=lambda x: abs(x[1] - x[3]), reverse=True)
    for s, a, b, c in moved[:8]:
        print(f"    {s:<10} stride5={a:>2}  stride10={b:>2}  stride20={c:>2}   Δ={abs(a-c)}")

    # ── B. 冠军候选的分半验证 ──────────────────────────────
    print(f"\n{'='*100}")
    print(f"B. 下行档「领先板块」的分半验证（防止从 20 个样本里挑冠军 = 过拟合）")
    print(f"{'='*100}")
    print(f"  分割点 {mid}")
    top_sectors = [s for s, _ in sorted(rank_tables[5].items(), key=lambda kv: kv[1])[:5]]
    train_down = [d for d in days if table[d]["market"] in DOWN and d < mid]
    test_down = [d for d in days if table[d]["market"] in DOWN and d >= mid]
    print(f"\n  {'板块':<12}{'训练段(前半)':>28}{'测试段(后半)':>28}")
    print("  " + "-" * 68)
    for sec in top_sectors:
        code = etf_of.get(sec)
        if not code:
            continue
        cells = []
        for seg in (train_down, test_down):
            xs = [r for d in seg if (r := fwd_ret(cache, code, d, H)) is not None]
            st = stats(xs)
            cells.append(f"{st['mean']:>+7.2f}% / {st['up']:>5.1f}% / n={st['n']:<3}" if st else "—")
        print(f"  {sec:<12}{cells[0]:>28}{cells[1]:>28}")

    # 参照：同期基准（沪深300）在下行档的表现
    print(f"\n  参照 —— 沪深300 自身在下行档：")
    for label, seg in (("训练段", train_down), ("测试段", test_down)):
        xs = [r for d in seg if (r := fwd_ret(cache, BENCH, d, H)) is not None]
        st = stats(xs)
        print(f"    {label:<8}{st['mean']:>+7.2f}% / {st['up']:>5.1f}% / n={st['n']}" if st else f"    {label} —")

    # ── C. 相对基准的超额（区分"抗跌"与"波动大"）──────────
    print(f"\n{'='*100}")
    print("C. 归因：下行档相对沪深300 的**超额**（排除大盘涨跌本身）")
    print(f"{'='*100}")
    ds_all = [d for d in days if table[d]["market"] in DOWN]
    bench_by_day = {d: fwd_ret(cache, BENCH, d, H) for d in ds_all}
    bench_vals = [v for v in bench_by_day.values() if v is not None]
    bench_mean = mean_pct(bench_vals)
    print(f"  下行档共 {len(ds_all)} 日，沪深300 T+{H} 均值 {bench_mean:+.2f}% (n={len(bench_vals)})")
    print(f"\n  {'板块':<12}{'绝对':>10}{'超额(vs基准)':>14}{'超额胜率':>12}{'n':>6}")
    print("  " + "-" * 56)
    rows = []
    for sec in sectors:
        code = etf_of.get(sec)
        if not code:
            continue
        abs_xs, ex = [], []
        for d in ds_all:
            r, b = fwd_ret(cache, code, d, H), bench_by_day.get(d)
            if r is None:
                continue
            abs_xs.append(r)
            if b is not None:
                ex.append(r - b)
        if len(abs_xs) >= 10:
            rows.append((sec, mean_pct(abs_xs), mean_pct(ex),
                         sum(1 for x in ex if x > 0) / len(ex) * 100 if ex else 0.0,
                         len(abs_xs)))
    rows.sort(key=lambda x: -x[2])
    for sec, ab, ex, up, n in rows:
        star = " ★" if sec in ("底仓", "贵金属", "券商") else ""
        print(f"  {sec:<12}{ab:>+9.2f}%{ex:>+13.2f}%{up:>11.1f}%{n:>6}{star}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
