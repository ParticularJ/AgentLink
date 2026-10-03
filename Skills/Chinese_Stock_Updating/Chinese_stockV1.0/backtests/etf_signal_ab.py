#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求4 回测：现有 ETF 入场 vs 新的 ETF 独立信号。

现有 ETF 入场 = detector 判定板块 STRONG_UP 时推荐该板块 ETF（纯 β 择时）。
新 ETF 信号   = 趋势（20日动量>0 且 收盘>MA20）+ 资金连续净流入 + 位置不过高。
两者在同一批板块 ETF、同一区间、同一出场规则下对比。
"""
from __future__ import annotations
import statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache, daily_phases
from round3_improve import sim
import etf_signal as es
import market_phase_detector as mpd

HOLD, STOP, TRAIL = 10, 0.08, 0.12
COOLDOWN = 40


def bars_of(cache, sym, upto, n=120):
    df = cache.raw.get(sym)
    if df is None:
        return []
    seg = df[df["date"] <= upto].tail(n)
    return [{"date": r["date"], "open": float(r["open"]), "high": float(r["high"]),
             "low": float(r["low"]), "close": float(r["close"]),
             "volume": float(r["volume"]), "amount": float(r["close"]) * float(r["volume"])}
            for _, r in seg.iterrows()]


def stat(rs, label):
    if not rs:
        print(f"  {label:<26}  无样本")
        return None
    w = [x for x in rs if x > 0]
    l = [x for x in rs if x <= 0]
    eq = peak = dd = 0.0
    for x in rs:
        eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
    print(f"  {label:<26}{len(rs):>6}{len(w)/len(rs)*100:>9.1f}%{statistics.mean(rs)*100:>+10.2f}%"
          f"{statistics.median(rs)*100:>+10.2f}%"
          f"{abs(statistics.mean(w)/statistics.mean(l)) if l else 0:>9.2f}{dd*100:>10.1f}")
    return statistics.mean(rs)


def main():
    cache = QuoteCache()
    days = [d for d in cache.all_dates if "2025-10-01" <= d <= "2026-09-30"]
    etfs = sorted({c for lst in mpd.SECTOR_ETFS.values() for c in lst})
    print(f"板块 ETF {len(etfs)} 只，区间 {days[0]} ~ {days[-1]}（{len(days)} 个交易日）")

    # 每天每个板块的 phase（现有策略用）
    spd = {}
    for i, d in enumerate(days):
        if i % 40 == 0:
            print(f"  计算板块 phase ... {i}/{len(days)}")
        try:
            spd[d] = daily_phases(cache, d)[1]
        except Exception:
            spd[d] = {}

    def run(mode):
        cooled, rets = {}, []
        for d in days:
            picks = []
            for sym in etfs:
                if mode == "existing":
                    # 现有：该 ETF 所属板块当日 STRONG_UP 才推荐
                    secs = [s for s, lst in mpd.SECTOR_ETFS.items() if sym in lst]
                    if not any(spd[d].get(s) == "STRONG_UP" for s in secs):
                        continue
                    picks.append(sym)
                elif mode == "signal":
                    bars = bars_of(cache, sym, d)
                    ok, _ = es.judge_etf_entry(bars)
                    if ok:
                        picks.append(sym)
                else:
                    # mode == "both": 现有板块 STRONG_UP 门控 + 资金流过滤
                    secs = [s for s, lst in mpd.SECTOR_ETFS.items() if sym in lst]
                    if not any(spd[d].get(s) == "STRONG_UP" for s in secs):
                        continue
                    bars = bars_of(cache, sym, d)
                    ok, det = es.judge_etf_entry(bars)
                    if det.get("flow_ok"):
                        picks.append(sym)
            for sym in picks[:2]:
                last = cooled.get(sym)
                idx = days.index(d)
                if last is not None and idx - last < COOLDOWN:
                    continue
                cooled[sym] = idx
                nd = cache.next_day(d)
                if nd is None:
                    continue
                b = cache.bar(sym, nd)
                fwd = cache.forward(sym, nd, HOLD + 2)[:HOLD]
                if not b or len(fwd) < HOLD:
                    continue
                bars = [{"open": float(x["open"]), "high": float(x["high"]),
                         "low": float(x["low"]), "close": float(x["close"])} for x in fwd]
                rets.append(sim(bars, float(b["open"]), STOP, TRAIL, None, None, HOLD)[0])
        return rets

    print()
    print("=" * 88)
    print("ETF 入场信号对比（同一批 ETF、同一出场 T+10/-8%/移12%、40 日冷却）")
    print("=" * 88)
    print(f"  {'方案':<26}{'笔数':>6}{'胜率':>10}{'均值':>11}{'中位':>11}{'盈亏比':>9}{'回撤':>10}")
    a = run("existing")
    b = run("signal")
    c = run("both")
    stat(a, "现有：板块 STRONG_UP")
    stat(c, "现有 STRONG_UP + 资金流过滤")
    stat(b, "新：趋势+资金流+位置")
    print()
    if a and c:
        print(f"  资金流过滤是否改善现有信号：现有 {statistics.mean(a)*100:+.2f}% → "
              f"加过滤 {statistics.mean(c)*100:+.2f}%")
    print()
    print("分半（均值）：")
    if a and b:
        print(f"  现有 {statistics.mean(a)*100:+.2f}%   新 {statistics.mean(b)*100:+.2f}%")


if __name__ == "__main__":
    main()
