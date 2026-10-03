#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第七轮：仓位管理（volatility targeting）。

发现两个此前被忽略的东西：

1. 前七轮全部是"换标的"（重排序 / 过滤 / 放开 reserve），从未试过"换权重"。
2. 我此前所有指标都是**单笔等权均值**，而不是**组合收益**——
   在每日买入 2 只、且波动差异巨大的情况下，这两个数并不等价。

因子 IC 显示 atr_pct 是最强的单一因子（-0.18，符号稳定）：
波动越大，未来收益越差。既然排序选不出更好的标的（第三轮已证），
那就**给高波动标的更少的钱**——同样的信号，不同的权重。

本脚本按日构建真实组合，比较等权与波动率倒数加权。
注意：这里评价的是**日度组合收益**（含现金日），而不是单笔均值。
"""
from __future__ import annotations

import pickle, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache
from factor_ic import factors_at
from rerank import _entry, _next, _sina
from round3_improve import sim

TOP_N = 2
COOLDOWN = 40


def main():
    data = pickle.load(open(HERE / "out" / "candidates_oct_year.pkl", "rb"))
    cache = QuoteCache()
    try:
        from market_phase_detector import SECTOR_ETFS, get_sector_by_stock
    except Exception:
        SECTOR_ETFS, get_sector_by_stock = {}, lambda c: ""

    days = sorted(data)
    di = {d: i for i, d in enumerate(days)}

    info = {}
    for d in days:
        for c in data[d]["candidates"]:
            sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
            if (sym, d) in info:
                continue
            entry = _entry(cache, sym, d)
            nd = _next(cache, d)
            if entry is None or nd is None:
                info[(sym, d)] = None
                continue
            bars = [{"open": float(x["open"]), "high": float(x["high"]),
                     "low": float(x["low"]), "close": float(x["close"])}
                    for x in cache.forward(sym, nd, 12)][:10]
            if len(bars) < 10:
                info[(sym, d)] = None
                continue
            secs = c.get("sectors") or []
            sec = (secs[0] if secs else "") or get_sector_by_stock(c.get("stock_code", ""))
            f = factors_at(cache, sym, d, (SECTOR_ETFS.get(sec) or [None])[0]) or {}
            ret, _, _ = sim(bars, entry, 0.08, 0.12, None, None, 10)
            info[(sym, d)] = {"ret": ret, "atr": f.get("atr_pct") or 0.0,
                              "kind": "ETF" if c.get("is_etf") else "个股"}

    # 重建每日持仓（生产口径：按分数取前 2 + 40 日冷却不回填）
    cooled, held = {}, {}
    for d in days:
        pool = []
        for c in data[d]["candidates"]:
            sym = c.get("raw_code") or _sina(c.get("stock_code", ""))
            v = info.get((sym, d))
            if v:
                pool.append((c.get("combined_score", 0), sym, v))
        pool.sort(key=lambda x: -x[0])
        picks = []
        for sc, sym, v in pool:
            if len(picks) >= TOP_N:
                break
            last = cooled.get(sym)
            if last is not None and di[d] - di[last] < COOLDOWN:
                continue
            cooled[sym] = d
            picks.append(v)
        if picks:
            held[d] = picks

    atrs = [p["atr"] for v in held.values() for p in v if p["atr"] > 0]
    med_atr = statistics.median(atrs) if atrs else 0.04
    print(f"有持仓的交易日 {len(held)} / {len(days)}；持仓笔数 {sum(len(v) for v in held.values())}")
    print(f"ATR 中位数 {med_atr*100:.2f}%  范围 {min(atrs)*100:.2f}%~{max(atrs)*100:.2f}%")

    def weights(picks, scheme):
        if scheme == "equal":
            return [1.0 / len(picks)] * len(picks)
        raw = []
        for p in picks:
            a = p["atr"] or med_atr
            if scheme == "inv_atr":
                raw.append(1.0 / max(a, 0.01))
            elif scheme == "inv_atr_capped":      # 单只权重上限 3 倍等权
                raw.append(min(1.0 / max(a, 0.01), 3.0 / med_atr / len(picks) * len(picks)))
            elif scheme == "inv_sqrt_atr":
                raw.append(1.0 / max(a, 0.01) ** 0.5)
        s = sum(raw)
        return [x / s for x in raw]

    def equity(scheme):
        """返回 (日度组合收益率序列, 逐日标号)。空仓日收益为 0。"""
        series = []
        for d in days:
            picks = held.get(d)
            if not picks:
                series.append(0.0)
                continue
            w = weights(picks, scheme)
            series.append(sum(wi * p["ret"] for wi, p in zip(w, picks)))
        return series

    def rep(series, name, scheme):
        eq = peak = dd = 0.0
        for x in series:
            eq += x
            peak = max(peak, eq)
            dd = min(dd, eq - peak)
        active = [x for x in series if x != 0.0]
        w = [x for x in active if x > 0]
        l = [x for x in active if x <= 0]
        return dict(name=name, scheme=scheme, n_active=len(active),
                    day_win=len(w) / len(active) * 100 if active else 0,
                    day_avg=statistics.mean(active) * 100 if active else 0,
                    pf=abs(statistics.mean(w) / statistics.mean(l)) if l else 0,
                    total=eq * 100, dd=dd * 100,
                    ratio=(eq / abs(dd)) if dd else 0)

    schemes = [("等权（现状）", "equal"),
               ("ATR 倒数加权", "inv_atr"),
               ("1/sqrt(ATR) 加权", "inv_sqrt_atr"),
               ("ATR 倒数 + 3 倍上限", "inv_atr_capped")]

    print()
    print("=" * 100)
    print("组合层面：不同权重方案的日度表现（含空仓日，空仓收益记 0）")
    print("=" * 100)
    print(f"  {'方案':<22}{'持仓日':>7}{'日胜率':>9}{'日均':>9}{'日盈亏比':>10}"
          f"{'累计':>10}{'最大回撤':>10}{'收益/回撤':>10}")
    rows = []
    for nm, sc in schemes:
        s = rep(equity(sc), nm, sc)
        rows.append(s)
        print(f"  {nm:<22}{s['n_active']:>7}{s['day_win']:>8.1f}%{s['day_avg']:>+8.3f}%"
              f"{s['pf']:>10.2f}{s['total']:>+9.1f}%{s['dd']:>10.1f}%{s['ratio']:>10.2f}")

    print()
    print("分半稳健性（日均收益）：")
    half = len(days) // 2
    d1, d2 = days[:half], days[half:]
    print(f"  {'方案':<22}{'前半日均':>12}{'后半日均':>12}")
    for nm, sc in schemes:
        ser = equity(sc)
        a = [x for x, d in zip(ser, days) if d in set(d1) and x != 0.0]
        b = [x for x, d in zip(ser, days) if d in set(d2) and x != 0.0]
        print(f"  {nm:<22}{statistics.mean(a)*100 if a else 0:>+11.3f}%"
              f"{statistics.mean(b)*100 if b else 0:>+11.3f}%")


if __name__ == "__main__":
    main()
