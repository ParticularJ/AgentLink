#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求1 诊断：我们的右侧策略到底有没有"买在高点"？

对每笔推荐，在信号日（不含未来信息）计算：
  pos_60   信号日收盘价在近 60 日 [最低,最高] 区间中的分位（1.0 = 60日最高点）
  bias_20  相对 MA20 乖离
  bias_60  相对 MA60 乖离
再把买入后的路径拿来做 MFE / MAE 分析，并按月聚合。
"""
from __future__ import annotations
import csv, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
from backtest_september import QuoteCache


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "backtests/out/trades_gated_top2_cd40_2025-09-30_2026-09-30.csv"
    cache = QuoteCache()
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["variant"] != "fixed":
            continue
        sym, sig = r["symbol"], r["signal_date"]
        df = cache.raw.get(cache._symbol(sym))
        if df is None:
            continue
        seg = df[df["date"] <= sig]
        if len(seg) < 61:
            continue
        c = seg["close"].astype(float).values
        h = seg["high"].astype(float).values
        l = seg["low"].astype(float).values
        close = c[-1]
        lo60, hi60 = l[-60:].min(), h[-60:].max()
        pos60 = (close - lo60) / (hi60 - lo60) if hi60 > lo60 else 1.0
        ma20, ma60 = c[-20:].mean(), c[-60:].mean()
        fwd = cache.forward(sym, r["entry_date"], 10)
        if len(fwd) < 10:
            continue
        entry = float(r["entry_price"])
        mfe = max(float(x["high"]) for x in fwd) / entry - 1
        mae = min(float(x["low"]) for x in fwd) / entry - 1
        rows.append(dict(date=sig, sym=sym, name=r["name"], ret=float(r["ret"]),
                         reason=r["reason"], pos60=pos60, bias20=close/ma20-1,
                         bias60=close/ma60-1, mfe=mfe, mae=mae,
                         etf=("ETF" in r["strategy"])))

    n = len(rows)
    print(f"样本 {n} 笔（{path.split('/')[-1]}）")
    print()
    print("=" * 88)
    print("一、买入位置：信号日收盘价在近 60 日区间中的分位")
    print("=" * 88)
    p = [r["pos60"] for r in rows]
    print(f"  均值 {statistics.mean(p):.3f}   中位 {statistics.median(p):.3f}")
    print(f"  {'分位区间':<14}{'笔数':>6}{'占比':>9}{'单笔均值':>11}{'平均最大浮亏':>13}")
    for lo, hi, nm in ((0.0, 0.3, "低位 0-30%"), (0.3, 0.5, "中低 30-50%"),
                       (0.5, 0.7, "中高 50-70%"), (0.7, 0.9, "高位 70-90%"),
                       (0.9, 1.01, "极高位 90-100%")):
        sel = [r for r in rows if lo <= r["pos60"] < hi]
        if not sel:
            continue
        print(f"  {nm:<14}{len(sel):>6}{len(sel)/n*100:>8.1f}%"
              f"{statistics.mean([x['ret'] for x in sel])*100:>+10.2f}%"
              f"{statistics.mean([x['mae'] for x in sel])*100:>+12.2f}%")
    print()
    for nm, key in (("相对 MA20 乖离", "bias20"), ("相对 MA60 乖离", "bias60")):
        v = [r[key] for r in rows]
        print(f"  {nm:<14} 均值 {statistics.mean(v)*100:+.2f}%  中位 {statistics.median(v)*100:+.2f}%"
              f"  为正的比例 {sum(1 for x in v if x>0)/n*100:.1f}%")

    print()
    print("=" * 88)
    print("二、2026 年 7-8 月专项")
    print("=" * 88)
    jul = [r for r in rows if r["date"][:7] in ("2026-07", "2026-08")]
    print(f"  7-8 月推荐 {len(jul)} 笔，占全年 {len(jul)/n*100:.1f}%")
    if jul:
        print(f"  买入位置分位 均值 {statistics.mean([r['pos60'] for r in jul]):.3f}"
              f"  （全年 {statistics.mean(p):.3f}）")
        print(f"  单笔均值 {statistics.mean([r['ret'] for r in jul])*100:+.2f}%"
              f"   平均最大浮亏 {statistics.mean([r['mae'] for r in jul])*100:+.2f}%")
        print(f"  止损离场 {sum(1 for r in jul if r['reason'].startswith('stop'))}/{len(jul)} 笔")
        print()
        print(f"  {'日期':<12}{'名称':<12}{'分位':>7}{'bias60':>9}{'最大浮亏':>10}{'实际收益':>10}  离场")
        for r in sorted(jul, key=lambda x: x["date"]):
            print(f"  {r['date']:<12}{r['name'][:10]:<12}{r['pos60']:>7.2f}"
                  f"{r['bias60']*100:>8.1f}%{r['mae']*100:>9.1f}%{r['ret']*100:>9.1f}%  {r['reason']}")

    print()
    print("=" * 88)
    print("三、按月：买入位置 vs 结果")
    print("=" * 88)
    by = defaultdict(list)
    for r in rows:
        by[r["date"][:7]].append(r)
    print(f"  {'月份':<10}{'笔数':>6}{'分位均值':>10}{'bias60':>9}{'单笔均值':>10}{'止损占比':>10}")
    for m in sorted(by):
        v = by[m]
        st = sum(1 for r in v if r["reason"].startswith("stop")) / len(v) * 100
        print(f"  {m:<10}{len(v):>6}{statistics.mean([r['pos60'] for r in v]):>10.2f}"
              f"{statistics.mean([r['bias60'] for r in v])*100:>8.1f}%"
              f"{statistics.mean([r['ret'] for r in v])*100:>+9.2f}%{st:>9.0f}%")


if __name__ == "__main__":
    main()
