#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""光通信（sh515880）那条 +4.18% 超额的**口径与归因**核查（复用 phase_table，秒级）。

要点：
1. 之前的 fwd_ret 用「信号日收盘价」入场，而生产/回测是「**次日开盘价**」入场。
   这里两种口径都算，看结论是否幸存。
2. +4.18% 可能只是**高波动板块的 Beta 补偿**。用三种归一化检验：
   - 单位波动超额（超额 / 该标的 T+10 收益标准差）
   - 同波动对照：把每个标的的超额除以自身波动后排名
   - 剔除极端日（|超额| 最大的 3/5/10 天）后是否幸存
3. 全档位对照：光通信在**非下行档**的超额是多少？
   若各档都为正，说明这是"长期跑赢"而不是"下行保护"——与防守命题无关。
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from backtest_september import QuoteCache  # noqa: E402
from defensive_scan import load_phase_table, fwd_ret, boot_ci, stats  # noqa: E402

H = 10
DOWN = ("STRONG_DOWN", "WEAK_DOWN")
BENCH = "sh000300"
TARGET = ("光通信", "sh515880")


def ret_from_next_open(cache: QuoteCache, code: str, day: str, n: int):
    """生产口径：信号日**次日开盘**买入，持有 n 个交易日后收盘卖出。"""
    rows = cache.forward(code, day, n + 1)
    if len(rows) < n + 1:
        return None
    entry = float(rows[0]["open"])
    if entry <= 0:
        return None
    # 持有 n 日（含入场日）：第 1..n 根，卖出用第 n 根的收盘
    exit_px = float(rows[n - 1]["close"])
    return exit_px / entry - 1.0


def main() -> int:
    table = load_phase_table()
    cache = QuoteCache()
    days = sorted(table)
    down_days = [d for d in days if table[d]["market"] in DOWN]
    up_days = [d for d in days if table[d]["market"] not in DOWN]

    print("=" * 96)
    print("1. 口径对比：收盘入场 vs 次日开盘入场（光通信 sh515880，下行档）")
    print("=" * 96)
    for label, fn in (("信号日收盘入场（旧口径）", lambda c, d: fwd_ret(cache, c, d, H)),
                      ("次日开盘入场（生产口径）", lambda c, d: ret_from_next_open(cache, c, d, H))):
        xs, ex = [], []
        for d in down_days:
            r = fn(TARGET[1], d)
            b = fn(BENCH, d)
            if r is None:
                continue
            xs.append(r)
            if b is not None:
                ex.append(r - b)
        s = stats(xs)
        ci = boot_ci(ex)
        print(f"  {label:<26} 绝对 {s['mean']:>+7.2f}% / 上涨 {s['up']:>5.1f}% / n={s['n']:<4}"
              f"  超额 {statistics.mean(ex)*100:>+7.2f}%  CI "
              f"{'[' + format(ci[0], '+.2f') + '%, ' + format(ci[1], '+.2f') + '%]' if ci else '—'}")

    print()
    print("=" * 96)
    print("2. 全档位对照：这是「下行保护」还是「长期跑赢」？")
    print("=" * 96)
    print(f"  {'档位':<16}{'光通信绝对':>12}{'沪深300':>12}{'超额':>12}{'超额胜率':>12}{'n':>6}")
    print("  " + "-" * 72)
    for label, ds in (("下行档", down_days), ("非下行档", up_days)):
        for hz in (H,):
            xs, ex, bench = [], [], []
            for d in ds:
                r, b = fwd_ret(cache, TARGET[1], d, hz), fwd_ret(cache, BENCH, d, hz)
                if r is None:
                    continue
                xs.append(r)
                if b is not None:
                    ex.append(r - b)
                    bench.append(b)
            if xs:
                print(f"  {label:<16}{statistics.mean(xs)*100:>+11.2f}%"
                      f"{statistics.mean(bench)*100:>+11.2f}%"
                      f"{statistics.mean(ex)*100:>+11.2f}%"
                      f"{sum(1 for x in ex if x>0)/len(ex)*100:>11.1f}%{len(xs):>6}")

    print()
    print("=" * 96)
    print("3. 是 Alpha 还是 Beta 补偿？—— 单位波动超额 + 极端日剔除")
    print("=" * 96)
    ex_all = []
    for d in down_days:
        r, b = fwd_ret(cache, TARGET[1], d, H), fwd_ret(cache, BENCH, d, H)
        if r is not None and b is not None:
            ex_all.append(r - b)
    sd_g, sd_b = statistics.pstdev(ex_all), statistics.pstdev(
        [fwd_ret(cache, BENCH, d, H) for d in down_days if fwd_ret(cache, BENCH, d, H) is not None])
    print(f"  光通信 T+{H} 收益标准差 {statistics.pstdev([fwd_ret(cache, TARGET[1], d, H) for d in down_days if fwd_ret(cache, TARGET[1], d, H) is not None])*100:.2f}%")
    print(f"  沪深300 T+{H} 收益标准差 {sd_b*100:.2f}%  → 光通信波动是基准的 "
          f"{statistics.pstdev([fwd_ret(cache, TARGET[1], d, H) for d in down_days if fwd_ret(cache, TARGET[1], d, H) is not None])/sd_b:.2f} 倍")
    print(f"  超额均值 {statistics.mean(ex_all)*100:+.2f}%   超额标准差 {sd_g*100:.2f}%   "
          f"单位波动超额 {statistics.mean(ex_all)/sd_g:+.3f}")

    print(f"\n  剔除极端盈利日后的超额均值：")
    srt = sorted(ex_all, reverse=True)
    for k in (0, 1, 3, 5, 10):
        kept = srt[k:]
        print(f"    去掉最好 {k:>2} 天（剩 {len(kept):>3}）：{statistics.mean(kept)*100:>+7.2f}%"
              + ("   ← 转负！" if statistics.mean(kept) < 0 else ""))

    print()
    print("=" * 96)
    print("4. 横向对照：同样口径下，其他板块的「单位波动超额」排名（下行档）")
    print("=" * 96)
    rows = []
    for sec in table[days[0]]["sectors"]:
        code = table[days[0]]["etf_of"].get(sec)
        if not code:
            continue
        ex, ab = [], []
        for d in down_days:
            r, b = fwd_ret(cache, code, d, H), fwd_ret(cache, BENCH, d, H)
            if r is not None and b is not None:
                ex.append(r - b)
                ab.append(r)
        if len(ex) >= 20:
            sd = statistics.pstdev(ex) or 1e-9
            rows.append((sec, code, statistics.mean(ab) * 100, statistics.mean(ex) * 100,
                         statistics.mean(ex) / sd, len(ex)))
    rows.sort(key=lambda x: -x[4])
    print(f"  {'板块':<12}{'ETF':<11}{'绝对':>9}{'超额':>9}{'单位波动超额':>14}{'n':>6}")
    print("  " + "-" * 64)
    for sec, code, ab, ex, ratio, n in rows:
        star = " ★防守" if sec in ("底仓", "贵金属", "券商") else ""
        print(f"  {sec:<12}{code:<11}{ab:>+8.2f}%{ex:>+8.2f}%{ratio:>+13.3f}{n:>6}{star}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
