#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查清两个异常：
  1. 动量轮动出现 -92.6% 最大回撤 —— 是数据问题还是策略问题？
  2. 行业 ETF 等权 +22.7% / -22.3% 是不是"幸存者偏差"（池子含退市/合并标的）？
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from allocation_engine import CACHE  # noqa: E402
from sector_rotation import SECTOR_ETFS  # noqa: E402


def load_one(code, start="2024-02-07", end="2026-09-30"):
    p = CACHE / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = df["date"].astype(str).str[:10]
    df = df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)
    return df if len(df) > 30 else None


def main() -> int:
    print("=" * 104)
    print("1. 逐只 ETF 的区间表现 + 单日异常扫描（找 -92% 回撤的元凶）")
    print("=" * 104)
    print(f"  {'代码':<10}{'区间收益':>10}{'最大回撤':>10}{'最大单日':>10}{'最小单日':>10}"
          f"{'>21%异常天数':>12}  {'备注'}")
    print("  " + "-" * 92)
    offenders = []
    for c in SECTOR_ETFS:
        df = load_one(c)
        if df is None:
            continue
        s = df["close"].astype(float)
        tot = (s.iloc[-1] / s.iloc[0] - 1) * 100
        mdd = ((s / s.cummax() - 1).min()) * 100
        r = s.pct_change()
        anom = int((r.abs() > 0.21).sum())
        note = ""
        if anom > 0:
            bad = df.loc[r.abs() > 0.21, "date"].tolist()
            note = f"⚠️ {bad[:3]}"
            offenders.append(c)
        if mdd < -50:
            note = (note + " ★深回撤").strip()
        print(f"  {c:<10}{tot:>+9.1f}%{mdd:>+9.1f}%{r.max()*100:>+9.2f}%{r.min()*100:>+9.2f}%"
              f"{anom:>12}  {note}")

    print()
    print("=" * 104)
    print("2. 异常标的的逐笔明细（确认是复权问题还是真实暴雷）")
    print("=" * 104)
    for c in offenders:
        df = load_one(c)
        if df is None:
            continue
        s = df["close"].astype(float)
        r = s.pct_change()
        idx = r.abs() > 0.21
        print(f"\n  ── {c} 的异常日 ──")
        for i in df.index[idx]:
            if i == 0:
                continue
            print(f"    {df.loc[i,'date']}  前收 {s.iloc[i-1]:.3f} → 收 {s.iloc[i]:.3f}"
                  f"  ({r.iloc[i]*100:+.1f}%)   开 {df.loc[i,'open']:.3f} 高 {df.loc[i,'high']:.3f}"
                  f" 低 {df.loc[i,'low']:.3f}")
        # 看前后 5 天
        for i in df.index[idx]:
            lo, hi = max(0, i - 3), min(len(df), i + 4)
            print(f"    前后序列：")
            for j in range(lo, hi):
                tag = " ← 异常" if j == i else ""
                print(f"      {df.loc[j,'date']}  {s.iloc[j]:.3f}{tag}")
        break  # 只看第一个即可

    print()
    print("=" * 104)
    print("3. 幸存者偏差检查：池子里这些 ETF 是否都活到了今天？")
    print("=" * 104)
    live, dead = [], []
    for c in SECTOR_ETFS:
        df = load_one(c)
        if df is None:
            dead.append(c)
            continue
        last = df["date"].iloc[-1]
        (live if last >= "2026-09-20" else dead).append(c)
    print(f"  活到今天（2026-09 末）: {len(live)} 只")
    print(f"  中途无数据/已退: {len(dead)} 只 → {dead}")
    print("  注：本池是**按 2026-10 的行业分类手工挑的**，")
    print("      没有纳入 2024-2026 期间表现极差或清盘的 ETF → 存在幸存者偏差。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
