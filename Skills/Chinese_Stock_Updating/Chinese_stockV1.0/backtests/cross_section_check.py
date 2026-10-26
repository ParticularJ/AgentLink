#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立复算：横截面控制（sh515880 在下行档的超额，在同批 ETF 里排第几？）

这条是驳回光通信结论的**最关键证据**：
如果同批 ETF 的超额中位数也有 +3.6%，那 +4.18% 就不是光通信强，
而是「沪深300 在这些日子偏弱」的产物。
"""
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from backtest_september import QuoteCache  # noqa: E402
from defensive_scan import load_phase_table, fwd_ret  # noqa: E402

H = 10
DOWN = ("STRONG_DOWN", "WEAK_DOWN")

CACHE = HERE / "cache"
ETF_PREFIX = ("50", "51", "56", "58", "15", "16", "18")


def main() -> int:
    table = load_phase_table()
    cache = QuoteCache()
    days = sorted(table)
    down = [d for d in days if table[d]["market"] in DOWN]
    bench = {d: fwd_ret(cache, "sh000300", d, H) for d in down}
    bvals = [v for v in bench.values() if v is not None]
    print(f"下行档 {len(down)} 日；沪深300 同期 T+{H} 均值 "
          f"{statistics.mean(bvals)*100:+.3f}% (n={len(bvals)})\n")

    # 缓存里所有 ETF 风格的标的
    codes = []
    for p in sorted(CACHE.glob("*.csv")):
        s = p.stem
        if s[:2] in ("sh", "sz") and s[2:4] in ETF_PREFIX:
            codes.append(s)

    res = []
    for c in codes:
        ex = []
        for d in down:
            r, b = fwd_ret(cache, c, d, H), bench.get(d)
            if r is not None and b is not None:
                ex.append(r - b)
        if len(ex) >= 40:
            res.append((c, statistics.mean(ex) * 100, len(ex)))

    res.sort(key=lambda x: -x[1])
    med = statistics.median([x[1] for x in res])
    avg = statistics.mean([x[1] for x in res])
    print(f"参与统计的 ETF: {len(res)} 只")
    print(f"超额 中位数 = {med:+.3f}%    等权平均 = {avg:+.3f}%")

    hit = [x for x in res if x[0] == "sh515880"]
    if hit:
        rank = res.index(hit[0]) + 1
        print(f"sh515880 超额 = {hit[0][1]:+.3f}%   排名 = {rank} / {len(res)}"
              f"   （即倒数第 {len(res) - rank + 1} 位）")

    print("\n前 8 名：")
    for i, (c, m, n) in enumerate(res[:8], 1):
        print(f"  {i:>3}. {c:<10}{m:>+8.2f}%  n={n}")
    print("\n后 8 名：")
    for i, (c, m, n) in enumerate(res[-8:], len(res) - 7):
        print(f"  {i:>3}. {c:<10}{m:>+8.2f}%  n={n}")

    # 光通信 vs 全体：分位
    if hit:
        below = sum(1 for _, m, _ in res if m < hit[0][1])
        print(f"\nsh515880 超过同批 {below}/{len(res)} 只 ETF "
              f"（分位 {below/len(res)*100:.0f}%）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
