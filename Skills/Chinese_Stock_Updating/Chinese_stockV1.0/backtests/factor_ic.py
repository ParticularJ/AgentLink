#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因子 IC 分析：找出真正能区分赢家与输家的因子。

背景：当前融合评分与未来收益的相关性只有 +0.0498（等于没有信息），
排名第 5 名反而比第 1 名更赚。所以要重建打分，但**不能凭经验猜因子**，
必须先用数据筛：每个因子算 IC（与未来收益的秩相关），并检查分半稳定性。

所有因子只用「信号日及之前」的数据计算，与生产在 14:20 运行时看到的一致。
"""
from __future__ import annotations

import csv, math, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache
from optimize_exit import Rule, simulate

PROD = Rule(10, 0.08, 0.0, 0.12)


def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def pearson(a, b):
    n = len(a)
    ma, mb = statistics.mean(a), statistics.mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a) / n)
    sb = math.sqrt(sum((x - mb) ** 2 for x in b) / n)
    if sa == 0 or sb == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n * sa * sb)


def factors_at(cache, code, day, sector_etf):
    df = cache.raw.get(cache._symbol(code))
    if df is None:
        return None
    seg = df[df["date"] <= day]
    if len(seg) < 61:
        return None
    c = seg["close"].astype(float).values
    h = seg["high"].astype(float).values
    l = seg["low"].astype(float).values
    v = seg["volume"].astype(float).values
    close = c[-1]
    ma = lambda n: c[-n:].mean()
    out = {}
    out["mom_5"] = close / c[-6] - 1 if len(c) > 6 else 0.0
    out["mom_10"] = close / c[-11] - 1 if len(c) > 11 else 0.0
    out["mom_20"] = close / c[-21] - 1 if len(c) > 21 else 0.0
    out["bias_20"] = close / ma(20) - 1
    out["bias_60"] = close / ma(60) - 1
    out["ma_align"] = ma(5) / ma(20) - 1
    out["vol_ratio"] = v[-1] / (v[-21:-1].mean() or 1)
    out["dist_high_60"] = close / h[-60:].max() - 1
    out["dist_low_20"] = close / l[-20:].min() - 1
    tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(-14, 0)]
    out["atr_pct"] = (sum(tr) / 14) / close
    streak = 0
    for i in range(-1, -20, -1):
        if c[i] > c[i - 1]:
            streak += 1
        else:
            break
    out["up_streak"] = float(streak)
    # 板块相对强度
    # ── 板块相对强度（第三轮因 names 只取首行键而被整体漏掉）──
    out["rs_5"] = 0.0
    out["rs_20"] = 0.0
    out["sector_mom_20"] = 0.0
    out["sector_mom_5"] = 0.0
    out["excess_bias_20"] = 0.0
    if sector_etf:
        edf = cache.raw.get(cache._symbol(sector_etf))
        if edf is not None:
            es = edf[edf["date"] <= day]["close"].astype(float).values
            if len(es) > 21:
                sec20 = es[-1] / es[-21] - 1
                sec5 = es[-1] / es[-6] - 1 if len(es) > 6 else 0.0
                sec_ma20 = es[-20:].mean()
                out["sector_mom_20"] = sec20
                out["sector_mom_5"] = sec5
                out["rs_20"] = out["mom_20"] - sec20
                out["rs_5"] = out["mom_5"] - sec5
                out["excess_bias_20"] = out["bias_20"] - (es[-1] / sec_ma20 - 1)
    return out


def quintiles(vals, rets):
    idx = sorted(range(len(vals)), key=lambda i: vals[i])
    k = len(idx) // 5
    if k < 3:
        return []
    res = []
    for q in range(5):
        part = idx[q * k:(q + 1) * k] if q < 4 else idx[4 * k:]
        rr = [rets[i] for i in part]
        res.append((len(rr), sum(1 for x in rr if x > 0) / len(rr) * 100, statistics.mean(rr) * 100))
    return res


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "backtests/out/trades_september_gated_T5.csv"
    cache = QuoteCache()
    try:
        from market_phase_detector import SECTOR_ETFS, get_sector_by_stock
    except Exception:
        SECTOR_ETFS, get_sector_by_stock = {}, lambda c: ""

    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["variant"] != "fixed":
            continue
        fwd = cache.forward(r["symbol"], r["entry_date"], 20)
        if len(fwd) < 20:
            continue
        bars = [{"open": float(x["open"]), "high": float(x["high"]),
                 "low": float(x["low"]), "close": float(x["close"])} for x in fwd]
        ret, _, _ = simulate(bars, float(r["entry_price"]), PROD)
        pure = r["symbol"][2:] if r["symbol"][:2] in ("sh", "sz") else r["symbol"]
        sec = get_sector_by_stock(pure) or ""
        etf = (SECTOR_ETFS.get(sec) or [None])[0]
        fs = factors_at(cache, r["symbol"], r["signal_date"], etf)
        if not fs:
            continue
        fs["_ret"] = ret; fs["_date"] = r["signal_date"]; fs["_code"] = r["symbol"]
        rows.append(fs)

    # 原来只取 rows[0] 的键：只要首行缺少某个因子（例如缺板块 ETF 数据），
    # 该因子就会被整体跳过。改为取所有行的键的并集。
    names = sorted({k for row in rows for k in row if not k.startswith("_")})
    rets = [r["_ret"] for r in rows]
    print(f"样本 {len(rows)} 笔  目标：生产出场（T+10/-8%/移12%）收益")
    print(f"收益：均值 {statistics.mean(rets)*100:+.2f}%  胜率 {sum(1 for x in rets if x>0)/len(rets)*100:.1f}%")
    print(f"因子数 {len(names)}；板块相对强度可用样本："
          f"{sum(1 for r in rows if r.get('sector_mom_20'))} / {len(rows)}")

    print()
    print("=" * 100)
    print("因子 IC（与未来收益的秩相关）—— 全样本 / 训练 / 测试")
    print("=" * 100)
    print(f"  {'因子':<16}{'IC':>9}{'训练IC':>10}{'测试IC':>10}{'符号稳定':>10}   Q1→Q5 均值(%)")
    results = []
    for nm in names:
        vals = [r[nm] for r in rows]
        ic = pearson(rank(vals), rank(rets))
        tr = [i for i, r in enumerate(rows) if r["_date"] < "2026-04-01"]
        te = [i for i, r in enumerate(rows) if r["_date"] >= "2026-04-01"]
        ic_tr = pearson(rank([vals[i] for i in tr]), rank([rets[i] for i in tr]))
        ic_te = pearson(rank([vals[i] for i in te]), rank([rets[i] for i in te]))
        stable = "✅" if (ic_tr > 0) == (ic_te > 0) and min(abs(ic_tr), abs(ic_te)) > 0.05 else "❌"
        q = quintiles(vals, rets)
        qs = "  ".join(f"{x[2]:+6.2f}" for x in q)
        print(f"  {nm:<16}{ic:>+9.4f}{ic_tr:>+10.4f}{ic_te:>+10.4f}{stable:>10}   {qs}")
        results.append((abs(ic), nm, ic, ic_tr, ic_te, stable))

    print()
    print("=" * 100)
    print("按 |IC| 排序")
    print("=" * 100)
    for a, nm, ic, a1, a2, st in sorted(results, reverse=True):
        print(f"  {nm:<16} |IC|={a:.4f}  符号稳定={st}")


if __name__ == "__main__":
    main()
