#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易员视角诊断：不看"策略对不对"，只看"这笔交易怎么做才赚钱"。

对每一笔信号，从缓存里重新取出完整的未来价格路径，计算：
  - MFE / MAE：买入后最大浮盈 / 最大浮亏（决定止盈止损该放哪）
  - R(N)：固定持有 N 日的收益曲线（决定该持有几天）
  - 入场跳空：次日开盘相对信号日收盘的涨幅（决定是否在追高）
  - 盈亏比 / 期望值
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "common"))

from backtest_september import QuoteCache

HORIZON = 20


def load_trades(path: Path, variant: str = "fixed"):
    import csv
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["variant"] != variant:
                continue
            rows.append(r)
    return rows


def path_of(cache: QuoteCache, row):
    """返回该笔交易的未来路径：入场价、跳空、每日收盘/最高/最低。"""
    sym = row["symbol"]
    sig = row["signal_date"]
    entry_day = row["entry_date"]
    entry = float(row["entry_price"])
    sig_bar = cache.bar(sym, sig)
    fwd = cache.forward(sym, entry_day, HORIZON)
    if len(fwd) < HORIZON:
        return None                      # 未来数据不足，剔除
    gap = None
    if sig_bar:
        gap = entry / float(sig_bar["close"]) - 1
    closes = [float(x["close"]) for x in fwd]
    highs = [float(x["high"]) for x in fwd]
    lows = [float(x["low"]) for x in fwd]
    return {
        "symbol": sym, "entry": entry, "gap": gap,
        "closes": closes, "highs": highs, "lows": lows,
        "mfe": max(highs) / entry - 1,
        "mae": min(lows) / entry - 1,
    }


def pct(x):
    return f"{x * 100:+.2f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trades")
    ap.add_argument("--variant", default="fixed")
    ap.add_argument("--horizon", type=int, default=20)
    args = ap.parse_args()
    global HORIZON
    HORIZON = args.horizon

    cache = QuoteCache()
    rows = load_trades(Path(args.trades), args.variant)
    paths = [p for p in (path_of(cache, r) for r in rows) if p]
    n = len(paths)
    print(f"样本：{n} 笔（原始 {len(rows)} 笔，剔除未来数据不足的）")
    print(f"文件：{Path(args.trades).name}   变体：{args.variant}   观察窗口：T+{HORIZON}")

    rets = [c / p["entry"] - 1 for p in paths for c in [p["closes"][-1]]]
    mfes = [p["mfe"] for p in paths]
    maes = [p["mae"] for p in paths]

    print()
    print("=" * 78)
    print("1. 盈亏比与期望（当前 T+N 固定持有口径）")
    print("=" * 78)
    wins = [r for r in rets if r > 0]
    loss = [r for r in rets if r <= 0]
    avg_w = statistics.mean(wins) if wins else 0
    avg_l = statistics.mean(loss) if loss else 0
    print(f"  胜率        : {len(wins) / n * 100:.1f}%")
    print(f"  平均盈利    : {pct(avg_w)}      平均亏损 : {pct(avg_l)}")
    print(f"  盈亏比      : {abs(avg_w / avg_l):.2f}  （盈亏比 × 胜率 需 > 亏损率才为正期望）")
    print(f"  期望/笔     : {pct(statistics.mean(rets))}")
    print(f"  最大浮盈均值: {pct(statistics.mean(mfes))}   最大浮亏均值: {pct(statistics.mean(maes))}")
    print(f"  浮盈曾 >5% 的比例: {sum(1 for m in mfes if m > 0.05) / n * 100:.1f}%")
    print(f"  浮亏曾 <-5% 的比例: {sum(1 for m in maes if m < -0.05) / n * 100:.1f}%")

    print()
    print("=" * 78)
    print("2. 持有期扫描：固定持有 N 日（不止损）")
    print("=" * 78)
    print(f"  {'N':>3} {'胜率':>8} {'均值':>9} {'中位':>9} {'盈亏比':>8} {'期望':>9}")
    for k in list(range(1, 11)) + [15, 20]:
        rs = [p["closes"][k - 1] / p["entry"] - 1 for p in paths]
        w = [r for r in rs if r > 0]
        l = [r for r in rs if r <= 0]
        pr = abs(statistics.mean(w) / statistics.mean(l)) if w and l and statistics.mean(l) != 0 else float("nan")
        print(f"  {k:>3} {len(w) / n * 100:>7.1f}% {pct(statistics.mean(rs)):>9} "
              f"{pct(statistics.median(rs)):>9} {pr:>8.2f} {pct(statistics.mean(rs)):>9}")

    print()
    print("=" * 78)
    print("3. 入场跳空分布（次日开盘 vs 信号日收盘）——是否在追高？")
    print("=" * 78)
    gaps = [p["gap"] for p in paths if p["gap"] is not None]
    if gaps:
        buckets = [(-9, -0.02, "低开 >2%"), (-0.02, 0, "小低开"), (0, 0.02, "小高开"),
                   (0.02, 0.05, "高开 2-5%"), (0.05, 9, "高开 >5%")]
        print(f"  {'跳空区间':<12}{'笔数':>7}{'占比':>8}{'T+5 胜率':>11}{'T+5 均值':>11}{'T+20 均值':>11}")
        for lo, hi, name in buckets:
            sel = [p for p in paths if p["gap"] is not None and lo <= p["gap"] < hi]
            if not sel:
                continue
            r5 = [p["closes"][4] / p["entry"] - 1 for p in sel]
            r20 = [p["closes"][19] / p["entry"] - 1 for p in sel]
            wr = sum(1 for r in r5 if r > 0) / len(sel) * 100
            print(f"  {name:<12}{len(sel):>7}{len(sel) / len(gaps) * 100:>7.1f}%{wr:>10.1f}%"
                  f"{pct(statistics.mean(r5)):>11}{pct(statistics.mean(r20)):>11}")

    print()
    print("=" * 78)
    print("4. MFE 分布——浮盈到过哪里？（决定止盈位）")
    print("=" * 78)
    for th in (0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20):
        hit = sum(1 for m in mfes if m >= th)
        print(f"  曾浮盈 ≥ {th * 100:>4.0f}% 的比例: {hit / n * 100:>5.1f}%  ({hit} 笔)")
    print()
    for th in (-0.03, -0.05, -0.08, -0.10, -0.15):
        hit = sum(1 for m in maes if m <= th)
        print(f"  曾浮亏 ≤ {th * 100:>4.0f}% 的比例: {hit / n * 100:>5.1f}%  ({hit} 笔)")

    print()
    print("=" * 78)
    print("5. 「先到止盈还是先到止损」——盈亏比设计的核心")
    print("=" * 78)
    print(f"  {'止盈/止损':<14}{'先止盈':>9}{'先止损':>9}{'止盈占比':>11}{'该组合期望':>13}")
    for tp in (0.05, 0.08, 0.10, 0.15, 0.20):
        for sl in (0.05, 0.08):
            if tp / sl < 1.2:
                continue
            first_tp = first_sl = 0
            pnl = []
            for p in paths:
                e = p["entry"]
                hit_tp = hit_sl = None
                for i in range(HORIZON):
                    if hit_sl is None and p["lows"][i] <= e * (1 - sl):
                        hit_sl = i; break
                    if hit_tp is None and p["highs"][i] >= e * (1 + tp):
                        hit_tp = i; break
                if hit_tp is not None and (hit_sl is None or hit_tp < hit_sl):
                    first_tp += 1; pnl.append(tp)
                elif hit_sl is not None:
                    first_sl += 1; pnl.append(-sl)
                else:
                    pnl.append(p["closes"][HORIZON - 1] / e - 1)
            tot = first_tp + first_sl
            ratio = first_tp / tot * 100 if tot else 0
            print(f"  +{tp * 100:.0f}%/-{sl * 100:.0f}%{' ':<6}{first_tp:>9}{first_sl:>9}{ratio:>10.1f}%"
                  f"{pct(statistics.mean(pnl)):>13}")


if __name__ == "__main__":
    main()
