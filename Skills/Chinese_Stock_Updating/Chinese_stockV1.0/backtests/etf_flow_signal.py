#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求4 预研：ETF 资金流信号的可实现性。

结论先行：
  东财的"主力资金流"接口**不覆盖 ETF**（f62 恒为 0），
  板块资金流有历史数据但接口极易限流（连续 3 轮 5 次重试全部被拒），
  不适合作为每日生产依赖。

因此先验证一个**不依赖外部接口**的替代：用 ETF 自身的量价推算"资金连续净流入"：
  flow_t   = 成交额_t x sign(收盘_t - 开盘_t)      （当日资金推动方向）
  cum3_t   = 近 3 日 flow 之和 / 近 20 日平均成交额  （归一到"天"）
然后看它能否预测 ETF 未来 T+10 收益（IC）。
"""
from __future__ import annotations
import math, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache
import market_phase_detector as mpd


def pearson(a, b):
    n = len(a)
    ma, mb = statistics.mean(a), statistics.mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a) / n)
    sb = math.sqrt(sum((x - mb) ** 2 for x in b) / n)
    if sa == 0 or sb == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n * sa * sb)


def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    for pos, i in enumerate(order):
        r[i] = pos + 1
    return r


def main():
    cache = QuoteCache()
    etfs = sorted({c for lst in mpd.SECTOR_ETFS.values() for c in lst})
    print(f"板块 ETF 数量: {len(etfs)}")
    rows = []
    for sym in etfs:
        df = cache.raw.get(sym)
        if df is None or len(df) < 120:
            continue
        c = df["close"].astype(float).values
        o = df["open"].astype(float).values
        v = df["volume"].astype(float).values
        amt = c * v                                  # 成交额代理
        for i in range(60, len(c) - 10):
            base = amt[i - 19:i + 1].mean()
            if base <= 0:
                continue
            flow = amt[i] * (1 if c[i] >= o[i] else -1)
            flow3 = (amt[i] * (1 if c[i] >= o[i] else -1)
                     + amt[i - 1] * (1 if c[i - 1] >= o[i - 1] else -1)
                     + amt[i - 2] * (1 if c[i - 2] >= o[i - 2] else -1))
            fwd = c[i + 10] / c[i] - 1
            mom20 = c[i] / c[i - 20] - 1
            pos60 = ((c[i] - c[i - 60:i + 1].min()) /
                     max(c[i - 60:i + 1].max() - c[i - 60:i + 1].min(), 1e-9))
            rows.append(dict(f1=flow / base, f3=flow3 / base, fwd=fwd,
                             mom20=mom20, pos60=pos60))
    n = len(rows)
    print(f"样本 {n} 个 (ETF x 交易日)")
    if n < 50:
        return
    fwd = [r["fwd"] for r in rows]
    print()
    print("=" * 78)
    print("因子 IC（与 ETF 未来 T+10 收益的秩相关）")
    print("=" * 78)
    for nm, key, desc in (("flow_1d", "f1", "当日资金推动（成交额x方向）/20日均额"),
                          ("flow_3d", "f3", "近3日累计资金推动 /20日均额"),
                          ("mom_20", "mom20", "ETF 20 日涨幅（现有策略的核心因子）"),
                          ("pos_60", "pos60", "ETF 在 60 日区间中的位置")):
        v = [r[key] for r in rows]
        ic = pearson(v, fwd)
        ric = pearson(rank(v), rank(fwd))
        print(f"  {nm:<10} IC={ic:+.4f}  秩IC={ric:+.4f}   {desc}")
    print()
    print("=" * 78)
    print("资金流因子的分位表现（flow_3d）")
    print("=" * 78)
    idx = sorted(range(n), key=lambda i: rows[i]["f3"])
    k = n // 5
    print(f"  {'分位':<8}{'样本':>7}{'未来T+10均值':>14}{'胜率':>9}")
    for q in range(5):
        part = idx[q * k:(q + 1) * k] if q < 4 else idx[4 * k:]
        rr = [rows[i]["fwd"] for i in part]
        print(f"  Q{q+1:<7}{len(rr):>7}{statistics.mean(rr)*100:>+13.2f}%"
              f"{sum(1 for x in rr if x > 0)/len(rr)*100:>8.1f}%")


if __name__ == "__main__":
    main()
