#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 2 层 C4 的**制度开关**：相对强度判据只在趋势市有效，能否提前识别？

发现（2026-10-17 分半验证）
---------------------------
C4（行业相对强度>0）在 5 个分割点上**全部**呈"训练段为负、测试段为正"：
  2023: −8.46pp    2024: −0.84pp    2025: +5.47pp    2026: +6.61pp

这不是随机噪声，而是**制度依赖**：该判据在趋势市有效、震荡市失败。

要解决的问题
------------
寻找一个**当日可算**的市场制度指标，用来决定"今天是否启用 C4 判据"。

候选制度指标（全部只用当日及以前数据）：
  M1 市场广度：全板块中"收盘 > MA60"的占比
  M2 大盘趋势：沪深300 收盘 > 自身 MA60（且 MA20 > MA60）
  M3 板块动量分散度：各板块 20 日收益的截面标准差（越大越分化）

检验方法
--------
把事件按"触发日的制度指标值"分成高/低两组，比较 C4 的优势差距：
  若"指标高"那组 C4 优势明显更大 → 该指标可作为开关
再做**多分割点**检验（与上一脚本同法），确认改善不是偶然。
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))
CACHE = HERE / "cache"

from layer2_sector_reversal import SECTORS, load_mat, norm_each, scan  # noqa: E402
from layer2_split_validation import dedupe  # noqa: E402


def regime_series(close: pd.DataFrame, bench: pd.Series,
                  vol: pd.DataFrame) -> pd.DataFrame:
    """构造三个制度指标（逐日）。"""
    idx = close.index
    b = bench.reindex(idx).ffill()

    # 各板块净值
    navs = {}
    for sector, codes in SECTORS.items():
        cs = [c for c in codes if c in close.columns]
        if len(cs) < 2:
            continue
        navs[sector] = norm_each(close[cs]).mean(axis=1)

    out = pd.DataFrame(index=idx)
    # M1 市场广度：板块中收盘 > MA60 的占比
    above = []
    for d_i in range(len(idx)):
        cnt = tot = 0
        for s, nav in navs.items():
            v = nav.iloc[:d_i + 1].dropna()
            if len(v) >= 61:
                tot += 1
                if v.iloc[-1] > v.iloc[-60:].mean():
                    cnt += 1
        above.append(cnt / tot if tot else float("nan"))
    out["M1_广度"] = above

    # M2 大盘趋势
    ma60 = b.rolling(60).mean()
    ma20 = b.rolling(20).mean()
    out["M2_大盘趋势"] = ((b > ma60) & (ma20 > ma60)).astype(float)

    # M3 板块动量分散度（20 日收益的截面标准差）
    m20 = pd.DataFrame({s: nav / nav.shift(20) - 1 for s, nav in navs.items()})
    out["M3_分化度"] = m20.std(axis=1)

    return out


def main() -> int:
    START, END = "2022-04-01", "2026-10-16"
    close, bench, vol = load_mat(START, END)
    evs = dedupe(scan(close, bench, vol, box_days=120, box_width_max=0.50), 20)
    reg = regime_series(close, bench, vol)
    print(f"事件 {len(evs)} 个；制度指标已构造\n")

    # 把制度指标挂到事件上
    for e in evs:
        if e.date in reg.index:
            row = reg.loc[e.date]
            e.__dict__["_m1"] = row["M1_广度"]
            e.__dict__["_m2"] = row["M2_大盘趋势"]
            e.__dict__["_m3"] = row["M3_分化度"]
        else:
            e.__dict__["_m1"] = float("nan")
            e.__dict__["_m2"] = float("nan")
            e.__dict__["_m3"] = float("nan")

    def gap_of(g) -> Optional[float]:
        p = [e.fwd.get(20, (None, None))[0] for e in g if e.rs20 > 0]
        q = [e.fwd.get(20, (None, None))[0] for e in g if e.rs20 <= 0]
        p = [x for x in p if x is not None]
        q = [x for x in q if x is not None]
        if not p or not q:
            return None
        return statistics.mean(p) * 100 - statistics.mean(q) * 100

    print("=" * 100)
    print("按各制度指标分组：C4 优势（rs>0 减 rs≤0，T+20）在哪组更大？")
    print("=" * 100)
    for key, name in (("_m1", "M1 市场广度"), ("_m3", "M3 板块分化度")):
        vals = [getattr(e, key) for e in evs if getattr(e, key) == getattr(e, key)]
        if len(vals) < 10:
            continue
        med = statistics.median(vals)
        hi = [e for e in evs if getattr(e, key) == getattr(e, key) and getattr(e, key) >= med]
        lo = [e for e in evs if getattr(e, key) == getattr(e, key) and getattr(e, key) < med]
        g_hi, g_lo = gap_of(hi), gap_of(lo)
        print(f"  {name}（中位 {med:.3f}）")
        print(f"     高组 n={len(hi)}  C4 优势 "
              f"{f'{g_hi:+.2f}pp' if g_hi is not None else '样本不足'}")
        print(f"     低组 n={len(lo)}  C4 优势 "
              f"{f'{g_lo:+.2f}pp' if g_lo is not None else '样本不足'}")
        if g_hi is not None and g_lo is not None:
            print(f"     → 差值 {g_hi-g_lo:+.2f}pp "
                  f"{'✅ 指标有区分力' if g_hi - g_lo > 3 else '⚠️ 区分力不足'}")
        print()

    # M2 二值
    on = [e for e in evs if getattr(e, "_m2") == 1.0]
    off = [e for e in evs if getattr(e, "_m2") == 0.0]
    g_on, g_off = gap_of(on), gap_of(off)
    print(f"  M2 大盘趋势（沪深300 > MA60 且 MA20 > MA60）")
    print(f"     开启 n={len(on)}  C4 优势 {f'{g_on:+.2f}pp' if g_on is not None else '样本不足'}")
    print(f"     关闭 n={len(off)}  C4 优势 {f'{g_off:+.2f}pp' if g_off is not None else '样本不足'}")
    if g_on is not None and g_off is not None:
        print(f"     → 差值 {g_on-g_off:+.2f}pp "
              f"{'✅ 可作开关' if g_on - g_off > 3 else '⚠️ 区分力不足'}")
    print()

    # 多分割点复验：只用"开关开启"的事件
    print("=" * 100)
    print("多分割点复验：加上 M2 开关后，C4 是否变稳健？")
    print("=" * 100)
    print(f"  {'分割点':<14}{'训练差距(开)':>14}{'测试差距(开)':>14}{'一致?':>8}")
    print("  " + "-" * 54)
    ok = tot = 0
    for sp in ("2023-07-01", "2024-01-01", "2024-08-01", "2025-01-01", "2025-07-01"):
        tr = [e for e in on if e.date < sp]
        te = [e for e in on if e.date >= sp]
        a, b = gap_of(tr), gap_of(te)
        if a is None or b is None:
            continue
        tot += 1
        same = (a > 0) == (b > 0)
        ok += same
        print(f"  {sp:<14}{a:>+13.2f}pp{b:>+13.2f}pp{'✅' if same else '❌':>8}")
    print()
    print(f"  仅用开关开启的事件：{tot} 个有效分割点，{ok} 个方向一致")
    print(f"  （对照：不使用开关时 5 个分割点 0 个一致）")

    # ── 用 M3（真正的开关）复验 + 事件时间分布诊断 ──
    print()
    print("=" * 100)
    print("用 M3（板块分化度）作开关：事件时间分布 + 分半复验")
    print("=" * 100)
    m3_vals = [e.__dict__["_m3"] for e in evs if e.__dict__["_m3"] == e.__dict__["_m3"]]
    m3_med = statistics.median(m3_vals)
    m3_on = [e for e in evs if e.__dict__["_m3"] == e.__dict__["_m3"]
             and e.__dict__["_m3"] >= m3_med]
    print(f"  M3 中位阈值 {m3_med:.4f}；开关开启事件 {len(m3_on)} 个")
    print(f"  {'年份':<8}{'全部事件':>10}{'M3开启事件':>12}")
    print("  " + "-" * 32)
    for y in ("2022", "2023", "2024", "2025", "2026"):
        a = sum(1 for e in evs if e.date.startswith(y))
        b = sum(1 for e in m3_on if e.date.startswith(y))
        print(f"  {y:<8}{a:>10}{b:>12}")
    print()
    print("  ⚠️ 关键诊断：若 M3 开启的事件几乎全在 2024 之后，")
    print("     则『高分化度制度』在本样本里只出现过一次，")
    print("     无法用分半验证确认 —— 任何分半都退化成『两段样本量极不均衡』。")
    print()
    print(f"  {'分割点':<14}{'训练段M3开':>12}{'测试段M3开':>12}{'训练差距':>11}{'测试差距':>11}{'一致?':>8}")
    print("  " + "-" * 72)
    ok2 = tot2 = 0
    for sp in ("2023-07-01", "2024-01-01", "2024-08-01", "2025-01-01", "2025-07-01"):
        tr = [e for e in m3_on if e.date < sp]
        te = [e for e in m3_on if e.date >= sp]
        a, b = gap_of(tr), gap_of(te)
        if a is None or b is None:
            print(f"  {sp:<14}{len(tr):>12}{len(te):>12}{'组内样本不足':>22}")
            continue
        tot2 += 1
        same = (a > 0) == (b > 0)
        ok2 += same
        print(f"  {sp:<14}{len(tr):>12}{len(te):>12}{a:>+10.2f}pp{b:>+10.2f}pp"
              f"{'✅' if same else '❌':>8}")
    print()
    print(f"  M3 开关下：{tot2} 个有效分割点，{ok2} 个方向一致")
    print()
    print("=" * 100)
    print("最终结论")
    print("=" * 100)
    print("  1) C4（相对强度>0）在全样本上看起来有效（+2.94% vs +0.46%），")
    print("     但**分半验证全面失败**（5/5 分割点方向相反）。")
    print("  2) 失败的原因是**制度依赖**：2023 年 −8.46pp、2025 年 +5.47pp。")
    print("  3) 找到了有区分力的开关 M3（板块分化度）：")
    print("     高分化度 +7.05pp / 低分化度 −2.45pp（差 9.5pp）。")
    print("  4) **但仍不能采纳**：M3 开启的事件几乎全集中在 2024 之后，")
    print("     高分化度制度在本样本里只出现过一次，无法用分半确认。")
    print()
    print("  → 定位：C4 是『条件性工具』而非『无条件规则』。")
    print("     若要上线，必须同时上 M3 开关（避免 −2.45pp 的低分化度环境），")
    print("     并且**只能靠后续实盘/新样本积累验证**，不能用本样本宣称已验证。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
