#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块1 复审：板块与趋势判断的准确度检验。

不看代码写了什么，只看它判出来的档位**是否真的预测了未来**：
  大盘：detector 的 market phase  vs  沪深300 未来 T+10 收益
  板块：detector 的 sector phase  vs  该板块 ETF 未来 T+10 收益
再附上档位完整性（文档说 5 档，代码是几档）与 UNKNOWN 占比。
"""
from __future__ import annotations
import statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
from backtest_september import QuoteCache, daily_phases
import market_phase_detector as mpd

FWD = 10


def fwd_ret(cache, sym, day, n=FWD):
    df = cache.raw.get(sym)
    if df is None:
        return None
    seg = df[df["date"] > day].head(n)
    cur = df[df["date"] == day]
    if len(seg) < n or cur.empty:
        return None
    return float(seg.iloc[-1]["close"]) / float(cur.iloc[0]["close"]) - 1


def report(rows, title):
    print()
    print("=" * 90)
    print(title)
    print("=" * 90)
    print(f"  {'档位':<14}{'样本':>7}{'占比':>9}{'未来T+10均值':>15}{'中位':>10}{'上涨率':>10}")
    tot = sum(len(v) for v in rows.values())
    for ph in ("STRONG_UP", "WAVE_UP", "RANGE", "WEAK_DOWN", "STRONG_DOWN", "UNKNOWN"):
        v = rows.get(ph) or []
        if not v:
            continue
        print(f"  {ph:<14}{len(v):>7}{len(v)/tot*100:>8.1f}%{statistics.mean(v)*100:>+14.2f}%"
              f"{statistics.median(v)*100:>+9.2f}%{sum(1 for x in v if x>0)/len(v)*100:>9.1f}%")


def non_overlap(rows):
    """非重叠抽样：每隔 FWD 个交易日取一个，避免重叠窗口夸大显著性。"""
    out = {}
    for ph, v in rows.items():
        out[ph] = v[::FWD]
    return out


def main():
    cache = QuoteCache()
    days = [d for d in cache.all_dates if "2025-10-01" <= d <= "2026-09-10"]
    print(f"区间 {days[0]} ~ {days[-1]}（{len(days)} 个交易日），前瞻窗口 T+{FWD}")

    mkt_rows = defaultdict(list)
    sec_rows = defaultdict(list)
    detail = {}
    for d in days:
        market, sectors, _ = daily_phases(cache, d)
        detail[d] = (market, sectors)
        r = fwd_ret(cache, "sh000300", d)
        if r is not None:
            mkt_rows[market].append(r)
        for sec, ph in sectors.items():
            etf = (mpd.SECTOR_ETFS.get(sec) or [None])[0]
            if not etf:
                continue
            rr = fwd_ret(cache, etf, d)
            if rr is not None:
                sec_rows[ph].append(rr)

    report(mkt_rows, "大盘趋势判断的准确度（vs 沪深300 未来 T+10）")
    print("  -- 非重叠抽样（每 10 个交易日取 1 个）--")
    report(non_overlap(mkt_rows), "大盘（非重叠）")
    report(sec_rows, "板块趋势判断的准确度（vs 该板块 ETF 未来 T+10）")
    report(non_overlap(sec_rows), "板块（非重叠）")

    print()
    print("=" * 90)
    print("档位完整性")
    print("=" * 90)
    print(f"  代码 PHASE_PHASES      : {mpd.PHASE_PHASES}")
    print(f"  是否含 WEAK_DOWN       : {'WEAK_DOWN' in mpd.PHASE_PHASES}")
    print(f"  judge_single 实际产出  : {sorted(set(detail[d][0] for d in days))}")
    print(f"  板块数量 SECTOR_ETFS   : {len(mpd.SECTOR_ETFS)}")
    print(f"  MARKET_TRADE_SWITCH 覆盖: {sorted(mpd.PHASE_SCORE)}")

    # 档位跳变频率（趋势判断是否稳定）
    seq = [detail[d][0] for d in days]
    flips = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
    print()
    print(f"  大盘档位日间跳变次数: {flips} / {len(seq)-1}（{flips/(len(seq)-1)*100:.0f}% 的日子换档）")
    print(f"  连续同档平均天数: {len(seq)/max(flips,1):.1f}")


if __name__ == "__main__":
    main()
