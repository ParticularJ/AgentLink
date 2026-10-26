#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 2 层 C4 判据的**分半验证**（防过拟合，P0 必做项）

要检验的问题：第 2 层发现的"相对强度 > 0 能剔除跟涨"是真的规律，
还是 2022-2026 这段样本的偶然？

方法：把样本按时间切成两半
  训练段：2022-04 ~ 2024-07
  测试段：2024-08 ~ 2026-10
分别在两段上跑同一个判据，看方向是否一致。

同时给出**事件级去重**版本：同一板块 20 个交易日内只保留首个事件
（否则同一波行情的多个触发日会把样本量虚高）。
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))
sys.path.insert(0, str(HERE))

from layer2_sector_reversal import SECTORS, load_mat, norm_each, report, scan  # noqa: E402


def dedupe(evs, gap_days: int = 20):
    """同一板块内的相邻事件，若间隔 < gap_days 个交易日只保留首个。

    事件里没有索引，这里用日期近似：把日期转成序号比较。
    """
    by: Dict[str, List] = {}
    for e in evs:
        by.setdefault(e.sector, []).append(e)
    out = []
    for sec, g in by.items():
        g.sort(key=lambda x: x.date)
        keep, last_d = [], None
        for e in g:
            if last_d is not None:
                d0 = pd.Timestamp(last_d)
                d1 = pd.Timestamp(e.date)
                # 交易日近似：自然日 × 0.7
                if (d1 - d0).days * 0.7 < gap_days:
                    continue
            keep.append(e)
            last_d = e.date
        out.extend(keep)
    return out


def summarise(evs, label: str) -> Dict:
    def grp(sel):
        return [e for e in evs if sel(e)]

    def fwd_of(e, h):
        """Ev.fwd[h] = (绝对收益, 超额收益)，可能为 (None, None)。"""
        try:
            return e.fwd.get(h, (None, None))
        except Exception:
            return (None, None)

    res = {"label": label, "n": len(evs)}
    for tag, sel in (("rs_pos", lambda e: e.rs20 > 0), ("rs_neg", lambda e: e.rs20 <= 0)):
        g = grp(sel)
        a20 = [fwd_of(e, 20)[0] for e in g if fwd_of(e, 20)[0] is not None]
        x20 = [fwd_of(e, 20)[1] for e in g if fwd_of(e, 20)[1] is not None]
        a60 = [fwd_of(e, 60)[0] for e in g if fwd_of(e, 60)[0] is not None]
        res[tag] = {
            "n": len(g),
            "a20": statistics.mean(a20) * 100 if a20 else None,
            "x20": statistics.mean(x20) * 100 if x20 else None,
            "a60": statistics.mean(a60) * 100 if a60 else None,
            "up20": sum(1 for x in a20 if x > 0) / len(a20) * 100 if a20 else None,
        }
    return res


def show(rows: List[Dict], title: str):
    print("=" * 104)
    print(title)
    print("=" * 104)
    print(f"  {'区间':<22}{'分组':<10}{'n':>5}{'T+20绝对':>11}{'T+20胜率':>10}"
          f"{'T+20超额':>11}{'T+60绝对':>11}")
    print("  " + "-" * 78)
    for r in rows:
        for tag, name in (("rs_pos", "相对强度>0"), ("rs_neg", "相对强度≤0")):
            d = r[tag]
            if not d["n"]:
                continue
            print(f"  {r['label']:<22}{name:<10}{d['n']:>5}"
                  f"{d['a20']:>+10.2f}%{d['up20']:>9.0f}%"
                  f"{d['x20']:>+10.2f}%"
                  f"{(d['a60'] if d['a60'] is not None else 0):>+10.2f}%")
    print()


def main() -> int:
    START, END = "2022-04-01", "2026-10-16"
    close, bench, vol = load_mat(START, END)
    print(f"全样本 {close.index[0]} → {close.index[-1]}（{len(close)} 日）\n")

    evs_all = scan(close, bench, vol, box_days=120, box_width_max=0.50)
    evs_dd = dedupe(evs_all, 20)

    # ── 1) 全样本 ──
    rows = [summarise(evs_all, "全样本")]
    show(rows, "全样本（参照）")

    # ── 2) 多分割点复验（防止"单一分割点"造成假象）──
    print("=" * 104)
    print("多分割点复验：『相对强度>0 优于 ≤0』的差距是否稳定为正？")
    print("=" * 104)
    print(f"  {'分割点':<14}{'训练(n+ / n−)':>16}{'训练差距':>11}"
          f"{'测试(n+ / n−)':>16}{'测试差距':>11}{'一致?':>8}")
    print("  " + "-" * 78)
    splits = ["2023-07-01", "2024-01-01", "2024-08-01", "2025-01-01", "2025-07-01"]
    consistent = 0
    valid = 0
    for sp in splits:
        tr = [e for e in evs_dd if e.date < sp]
        te = [e for e in evs_dd if e.date >= sp]
        if not tr or not te:
            continue

        def gap(g):
            p = [e.fwd.get(20, (None, None))[0] for e in g if e.rs20 > 0]
            q = [e.fwd.get(20, (None, None))[0] for e in g if e.rs20 <= 0]
            p = [x for x in p if x is not None]
            q = [x for x in q if x is not None]
            if not p or not q:
                return None, len(p), len(q)
            return statistics.mean(p) * 100 - statistics.mean(q) * 100, len(p), len(q)

        g_tr, p1, q1 = gap(tr)
        g_te, p2, q2 = gap(te)
        if g_tr is None or g_te is None:
            print(f"  {sp:<14}{f'{p1}/{q1}':>16}{'组内样本不足':>11}")
            continue
        valid += 1
        same = (g_tr > 0) == (g_te > 0)
        if same:
            consistent += 1
        print(f"  {sp:<14}{f'{p1}/{q1}':>16}{g_tr:>+10.2f}pp"
              f"{f'{p2}/{q2}':>16}{g_te:>+10.2f}pp"
              f"{'✅' if same else '❌':>8}")

    print()
    print(f"  有效分割点 {valid} 个，其中『两段方向一致』的 {consistent} 个"
          f"（{consistent/valid*100 if valid else 0:.0f}%）")
    if valid and consistent == valid:
        print("  → 判据稳健，可采纳")
    elif valid and consistent >= valid * 0.6:
        print("  → 多数分割点一致，判据有一定稳健性，但需更多样本确认")
    else:
        print("  → 判据不稳定，**不建议采纳**")

    # ── 3) 按年拆解，看收益集中在哪一年 ──
    print()
    print("=" * 104)
    print("按年拆解（看优势是否集中在某一年 = 样本期依赖）")
    print("=" * 104)
    print(f"  {'年份':<8}{'n+':>5}{'n−':>5}{'rs>0 绝对':>12}{'rs≤0 绝对':>12}{'差距':>10}")
    print("  " + "-" * 56)
    for y in ("2022", "2023", "2024", "2025", "2026"):
        g = [e for e in evs_dd if e.date.startswith(y)]
        if not g:
            continue
        p = [e.fwd.get(20, (None, None))[0] for e in g if e.rs20 > 0]
        q = [e.fwd.get(20, (None, None))[0] for e in g if e.rs20 <= 0]
        p = [x for x in p if x is not None]
        q = [x for x in q if x is not None]
        sp_ = f"{statistics.mean(p)*100:>+11.2f}%" if p else f"{'—':>12}"
        sq_ = f"{statistics.mean(q)*100:>+11.2f}%" if q else f"{'—':>12}"
        dgap = f"{statistics.mean(p)*100-statistics.mean(q)*100:>+9.2f}pp" if (p and q) else f"{'—':>10}"
        print(f"  {y:<8}{len(p):>5}{len(q):>5}{sp_}{sq_}{dgap}")
    print()
    print(f"  事件数：全样本 {len(evs_all)} → 20日去重 {len(evs_dd)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
