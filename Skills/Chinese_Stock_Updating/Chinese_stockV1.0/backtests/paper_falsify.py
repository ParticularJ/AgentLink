#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""热点板块 B3：造纸「反内卷」证伪案例（2026-10-17）

目的
----
框架声称：基本面拐点（如 capex 指引）领先板块价格。
光模块是正例（capex → 价格 +1~2 月领先）。

现在做**证伪**：造纸行业有一个明确的基本面论点——「反内卷」
（2025-07 起，箱板纸价 4230→4700 元/吨，产能扩张结束，37-43 月周期）。
如果框架正确，造纸板块应在基本面信号（2025-07 后）上涨；
如果没涨（或涨了但原因无关），框架在此案例上失效，需找出缺了什么过滤条件。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PAPER = {
    "太阳纸业": "sz002078", "山鹰国际": "sh600567", "晨鸣纸业": "sz000488",
    "岳阳林纸": "sh600963", "中顺洁柔": "sz002511", "荣晟环保": "sh603165",
    "博汇纸业": "sh600966", "华泰股份": "sh600308",
}
OPTIC = {"中际旭创": "sz300308", "新易盛": "sz300502", "天孚通信": "sz300394"}
BENCH = "sh000300"


def load(code: str) -> pd.Series:
    df = pd.read_csv(f"backtests/cache_long/{code}.csv")
    df["date"] = df["date"].astype(str).str[:10]
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def panel(codes: dict) -> pd.Series:
    d = {n: load(c) for n, c in codes.items()}
    px = pd.DataFrame(d).sort_index().dropna()
    return px.mean(axis=1)


def main() -> int:
    paper = panel(PAPER)
    optic = panel(OPTIC)
    bench = load(BENCH)

    # 反内卷信号时点（基本面）
    SIGNAL = "2025-07-01"

    print("=" * 88)
    print("造纸「反内卷」证伪：基本面信号 vs 板块价格")
    print("=" * 88)
    print(f"  反内卷信号时点：{SIGNAL}（箱板纸 4230→4700 元/吨，产能出清）")
    print()

    # 逐年（2023-2026）
    print(f"  {'年份':<8}{'造纸':>10}{'光模块':>10}{'沪深300':>10}")
    print("  " + "-" * 42)
    for y in ("2022", "2023", "2024", "2025", "2026"):
        cells = []
        for s in (paper, optic, bench):
            seg = s[s.index.str.startswith(y)]
            cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+9.1f}%" if len(seg) >= 20 else f"{'—':>10}")
        print(f"  {y:<8}" + "".join(cells))

    # 反内卷信号前后的表现
    print()
    print("=" * 88)
    print(f"「反内卷」信号（{SIGNAL}）前后的累计表现")
    print("=" * 88)
    print(f"  {'区间':<26}{'造纸':>10}{'光模块':>10}{'沪深300':>10}")
    print("  " + "-" * 60)
    for label, s0, s1 in (
        ("信号前 1 年（2024-07~2025-06）", "2024-07-01", "2025-06-30"),
        ("信号后 3 个月（2025-07~09）", "2025-07-01", "2025-09-30"),
        ("信号后 6 个月（2025-07~12）", "2025-07-01", "2025-12-31"),
        ("信号后 1 年（2025-07~2026-06）", "2025-07-01", "2026-06-30"),
    ):
        cells = []
        for s in (paper, optic, bench):
            seg = s[(s.index >= s0) & (s.index <= s1)]
            cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+9.1f}%" if len(seg) > 20 else f"{'—':>10}")
        print(f"  {label:<26}" + "".join(cells))

    # 反内卷信号后：造纸有没有相对收益？
    print()
    print("=" * 88)
    print("核心证伪问题：反内卷信号后，造纸是否产生了相对收益？")
    print("=" * 88)
    sp = paper[(paper.index >= SIGNAL) & (paper.index <= "2026-06-30")]
    sb = bench[(bench.index >= SIGNAL) & (bench.index <= "2026-06-30")]
    so = optic[(optic.index >= SIGNAL) & (optic.index <= "2026-06-30")]
    rp = sp.iloc[-1] / sp.iloc[0] - 1
    rb = sb.iloc[-1] / sb.iloc[0] - 1
    ro = so.iloc[-1] / so.iloc[0] - 1
    print(f"  反内卷后 1 年：造纸 {rp*100:+.1f}%  vs  沪深300 {rb*100:+.1f}%  相对 {((rp-rb)*100):+.1f}pp")
    print(f"  同期光模块 {ro*100:+.1f}%（对照组）")
    print()

    # 个股分化
    print("=" * 88)
    print("造纸个股在反内卷信号后 1 年的分化")
    print("=" * 88)
    rows = []
    for n, c in PAPER.items():
        s = load(c)
        seg = s[(s.index >= SIGNAL) & (s.index <= "2026-06-30")]
        if len(seg) > 20:
            rows.append((seg.iloc[-1] / seg.iloc[0] - 1, n))
    for r, n in sorted(rows, reverse=True):
        print(f"  {n:<10}{r*100:>+8.1f}%")
    pos = sum(1 for r, _ in rows if r > 0)
    print(f"  → {pos}/{len(rows)} 只上涨（若基本面有效，应大部分上涨）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
