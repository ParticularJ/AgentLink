#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第三轮实验：两个由因子 IC 推出的改进。

因子 IC 显示所有因子都是负 IC —— 策略在系统性买入"过度延伸"的股票：
  bias_60    -0.17   离 MA60 越远，未来越差
  atr_pct    -0.18   波动越大，未来越差（但可能只是被固定止损机械性打掉）
  mom_5      -0.11   5 日涨得越多，未来越差（短期反转）
  vol_ratio  -0.08   放量越猛，未来越差
  dist_low_20-0.10   离 20 日低点越远，未来越差

实验 1（B）：把固定 -8% 止损换成 k×ATR 自适应止损，检验 atr_pct 的负 IC
             究竟是"预测力"还是"固定止损的机械产物"。
实验 2（A）：用"不过热"复合因子对当日候选重新排序，替代无预测力的融合评分。
"""
from __future__ import annotations

import csv, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache
from factor_ic import factors_at


def sim(bars, entry, stop_pct, trail, atr_pct=None, atr_k=None, max_hold=10, take=0.0):
    """出场模拟。给了 atr_k 就用 k×ATR 当止损，否则用固定 stop_pct。"""
    sl = atr_pct * atr_k if (atr_k and atr_pct) else stop_pct
    sl = max(0.02, min(0.25, sl))          # 夹在 2%~25%，避免异常 ATR
    peak = entry
    for i, b in enumerate(bars[:max_hold]):
        sp = entry * (1 - sl)
        if trail:
            sp = max(sp, peak * (1 - trail))
        o, h, l = b["open"], b["high"], b["low"]
        if o <= sp:
            return o / entry - 1, i + 1, "stop_gap"
        if l <= sp:
            return sp / entry - 1, i + 1, "stop"
        if take and h >= entry * (1 + take):
            return take, i + 1, "take"
        peak = max(peak, h)
    last = bars[min(max_hold, len(bars)) - 1]
    return last["close"] / entry - 1, min(max_hold, len(bars)), "hold"


def stat(rets):
    w = [x for x in rets if x > 0]; l = [x for x in rets if x <= 0]
    eq = peak = dd = 0.0
    for x in rets:
        eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
    return dict(n=len(rets), win=len(w) / len(rets) * 100, avg=statistics.mean(rets) * 100,
                med=statistics.median(rets) * 100, pl=abs(statistics.mean(w) / statistics.mean(l)) if l else 0,
                dd=dd * 100)


def build(cache):
    try:
        from market_phase_detector import SECTOR_ETFS, get_sector_by_stock
    except Exception:
        SECTOR_ETFS, get_sector_by_stock = {}, lambda c: ""
    rows = []
    for r in csv.DictReader(open("backtests/out/trades_september_gated_T5.csv", encoding="utf-8")):
        if r["variant"] != "fixed":
            continue
        fwd = cache.forward(r["symbol"], r["entry_date"], 20)
        if len(fwd) < 20:
            continue
        bars = [{"open": float(x["open"]), "high": float(x["high"]),
                 "low": float(x["low"]), "close": float(x["close"])} for x in fwd]
        pure = r["symbol"][2:] if r["symbol"][:2] in ("sh", "sz") else r["symbol"]
        sec = get_sector_by_stock(pure) or ""
        fs = factors_at(cache, r["symbol"], r["signal_date"], (SECTOR_ETFS.get(sec) or [None])[0])
        if not fs:
            continue
        row = dict(fs, _code=r["symbol"], _date=r["signal_date"], _entry=float(r["entry_price"]),
                   _bars=bars, _score=float(r["score"]), _name=r["name"])
        rows.append(row)
    return rows


def main():
    cache = QuoteCache()
    rows = build(cache)
    print(f"样本 {len(rows)} 笔")

    print()
    print("=" * 92)
    print("实验 1：固定 -8% 止损 vs k×ATR 自适应止损（移动 12%，T+10）")
    print("=" * 92)
    print(f"  {'止损方式':<20}{'笔数':>7}{'胜率':>9}{'均值':>9}{'中位':>9}{'盈亏比':>8}{'回撤':>10}")
    variants = [("固定 -8%", None, 0.08), ("固定 -5%", None, 0.05)]
    for k in (1.5, 2.0, 2.5, 3.0, 3.5):
        variants.append((f"{k}×ATR", k, 0.08))
    for nm, k, sp in variants:
        rets, stops = [], []
        for r in rows:
            ret, _, why = sim(r["_bars"], r["_entry"], sp, 0.12, r.get("atr_pct"), k)
            rets.append(ret)
            stops.append(1 if why.startswith("stop") else 0)
        s = stat(rets)
        print(f"  {nm:<20}{s['n']:>7}{s['win']:>8.1f}%{s['avg']:>+8.2f}%{s['med']:>+8.2f}%"
              f"{s['pl']:>8.2f}{s['dd']:>10.1f}  止损占比 {sum(stops)/len(stops)*100:.0f}%")

    print()
    print("=" * 92)
    print("实验 2：「不过热」复合因子重排（每日取前 5，20 日冷却，不回填）")
    print("=" * 92)
    # 复合分：对所有负 IC 因子取负号后标准化求和
    use = ["bias_60", "atr_pct", "mom_5", "vol_ratio", "dist_low_20"]
    for nm in use:
        v = [r[nm] for r in rows]
        m = statistics.mean(v); sd = statistics.pstdev(v) or 1
        for r in rows:
            r["_z_" + nm] = (r[nm] - m) / sd
    for r in rows:
        r["_comp"] = -sum(r["_z_" + nm] for nm in use) / len(use)

    by_day = defaultdict(list)
    for r in rows:
        by_day[r["_date"]].append(r)
    days = sorted(by_day)
    di = {d: i for i, d in enumerate(days)}

    def pipeline(keyfn, cooldown=20, topn=5, k_atr=2.0):
        cooled, out = {}, []
        for d in days:
            cand = sorted(by_day[d], key=keyfn, reverse=True)[:topn]
            for c in cand:
                last = cooled.get(c["_code"])
                if last is not None and di[d] - di[last] < cooldown:
                    continue
                cooled[c["_code"]] = d
                ret, _, _ = sim(c["_bars"], c["_entry"], 0.08, 0.12, c.get("atr_pct"), k_atr)
                out.append(ret)
        return out

    print(f"  {'排序方式':<28}{'笔数':>7}{'胜率':>9}{'均值':>9}{'中位':>9}{'盈亏比':>8}{'回撤':>10}")
    for nm, fn in (("原融合评分（现状）", lambda c: c["_score"]),
                   ("「不过热」复合因子", lambda c: c["_comp"]),
                   ("只用 bias_60（最小优先）", lambda c: -c["bias_60"]),
                   ("只用 atr_pct（最小优先）", lambda c: -c["atr_pct"]),
                   ("只用 mom_5（最小优先）", lambda c: -c["mom_5"]),
                   ("原评分 + 复合因子", lambda c: c["_score"] / 100 + 0.5 * c["_comp"])):
        rets = pipeline(fn)
        s = stat(rets)
        print(f"  {nm:<28}{s['n']:>7}{s['win']:>8.1f}%{s['avg']:>+8.2f}%{s['med']:>+8.2f}%"
              f"{s['pl']:>8.2f}{s['dd']:>10.1f}")


if __name__ == "__main__":
    main()
