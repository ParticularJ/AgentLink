#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""完整周期 v3.1：加「大盘趋势过滤」压回撤（2026-10-17）

问题（v3 完整周期实测）
-----------------------
年化 +5.5%、最大回撤 −28.3%、最长连亏 7 个月 —— **回撤超过用户 20% 上限**。

诊断
----
2022-04 ~ 2024-09（924 前）策略累计 −14.0%。这段是真实的熊市/震荡，
核心代理（消费/家电/医药/煤炭）本身跌了 −18.7%，卫星也只做到 −5%。

修正方案：加一层**全局趋势过滤**
  G1 沪深300 收盘 > 自身 MA200  → 正常持仓（核心 70% / 卫星 30%）
  G2 沪深300 收盘 ≤ MA200       → 整体降仓：核心降到 40%，卫星停手
  G3 MA200 重新站上              → 恢复原配比

这与"个股板块止损"不同：它是**组合层的风险开关**，
用来避免"在全面熊市里持续满仓"这种最伤本金的情形。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))

import full_cycle_v3 as B  # noqa: E402

COST = B.COST
BENCH = B.BENCH


def run_trend(px: pd.DataFrame, core_w: float = 0.70, sat_w: float = 0.30,
              use_gate: bool = True, bear_core_w: float = 0.40) -> pd.Series:
    """在 v3 基础上加「沪深300 MA200」全局趋势过滤。"""
    dates = list(px.index)
    core = [c for c in B.CORE_PROXY.values() if c in px.columns]
    sec = [c for c in B.SAT_POOL.values() if c in px.columns]
    mom = px[sec].pct_change(B.MOM_WIN)
    disp = px[sec].pct_change(20).std(axis=1)
    dmed = disp.expanding(min_periods=100).median()
    bench = px[BENCH]
    ma200 = bench.rolling(200).mean()

    cash, cu, sat, peak, entry = 1.0, {}, {}, {}, {}
    curve, last = [], -10 ** 6
    WARM = 210

    for i, dt in enumerate(dates):
        if i > 0:
            for c in list(sat.keys()):
                cur = px[c].iloc[i]
                peak[c] = max(peak[c], cur)
                if (cur / entry[c] - 1) <= B.STOP or (cur / peak[c] - 1) <= B.TRAIL:
                    cash += sat[c] * cur * (1 - COST)
                    del sat[c], peak[c], entry[c]
        cv = sum(u * px[c].iloc[i] for c, u in cu.items())
        sv = sum(u * px[c].iloc[i] for c, u in sat.items())
        nav = cash + cv + sv
        assert nav == nav and nav > 0
        curve.append(nav)

        if i < WARM:
            continue
        # ⚠️ 2026-10-17 修正：v3.1 初版缺「首次建仓」，导致所有变体输出同一个数
        if i == WARM:
            for c in core:
                u = (nav * core_w / len(core)) / px[c].iloc[i]
                cu[c] = u
                cash -= u * px[c].iloc[i]
            continue
        # 全局趋势状态
        in_bull = bool(bench.iloc[i] > ma200.iloc[i]) if ma200.iloc[i] == ma200.iloc[i] else True
        tgt_core_w = core_w if in_bull else bear_core_w

        if (i - WARM) % 20 == 0:
            # 核心仓按目标权重调整
            cv = sum(u * px[c].iloc[i] for c, u in cu.items())
            tgt = nav * tgt_core_w
            if cv > 1e-9 and abs(cv - tgt) > nav * 0.03:
                delta = tgt - cv
                # 卖 → 加现金；买 → 用现金
                if delta < 0:
                    cash += (-delta) * (1 - COST)
                    for c in core:
                        cu[c] *= tgt / cv
                else:
                    add = min(delta, cash / (1 + COST))
                    if add > 0:
                        cash -= add * (1 + COST)
                        for c in core:
                            cu[c] += (add / len(core)) / px[c].iloc[i]

        if (i - last) < B.HOLD:
            continue
        j = i - 1
        gated = bool(use_gate and disp.iloc[j] == disp.iloc[j]
                     and dmed.iloc[j] == dmed.iloc[j]
                     and disp.iloc[j] < dmed.iloc[j])
        # 全局熊市 → 卫星停手
        if not in_bull:
            gated = True
        picked: List[str] = []
        if not gated:
            sc = {c: mom[c].iloc[j] for c in sec if mom[c].iloc[j] == mom[c].iloc[j]}
            picked = [c for c, v in sorted(sc.items(), key=lambda kv: -kv[1])[:B.N_SEC]
                      if v > 0]
        for c in list(sat.keys()):
            if c not in picked:
                cash += sat[c] * px[c].iloc[i] * (1 - COST)
                del sat[c], peak[c], entry[c]
        if picked:
            per = nav * sat_w / len(picked)
            for c in picked:
                cur_v = sat.get(c, 0.0) * px[c].iloc[i]
                need = per - cur_v
                if need <= nav * 0.01 or cash <= 0:
                    continue
                aff = min(need, cash / (1 + COST))
                u = aff / px[c].iloc[i]
                cash -= u * px[c].iloc[i] * (1 + COST)
                if c not in sat:
                    sat[c] = 0.0
                    entry[c] = px[c].iloc[i]
                    peak[c] = px[c].iloc[i]
                sat[c] += u
        last = i
    return pd.Series(curve, index=dates)


def main() -> int:
    px = B.build("2022-04-01", "2026-10-16")
    print(f"完整周期 {px.index[0]} → {px.index[-1]}（{len(px)} 日）\n")
    b = px[BENCH] / px[BENCH].iloc[0]
    bm = B.metr(b)

    print("=" * 100)
    print("全局趋势过滤（沪深300 MA200）压回撤")
    print("=" * 100)
    print(f"  {'方案':<26}{'累计':>10}{'年化':>9}{'回撤':>9}{'卡玛':>8}"
          f"{'月胜率':>9}{'最差月':>9}{'连亏':>6}")
    print("  " + "-" * 82)
    rows = []
    for label, kw in (
        ("v3 无趋势过滤", dict(bear_core_w=0.70)),
        ("v3.1 熊市核心降至50%", dict(bear_core_w=0.50)),
        ("v3.1 熊市核心降至40%", dict(bear_core_w=0.40)),
        ("v3.1 熊市核心降至30%", dict(bear_core_w=0.30)),
        ("v3.1 熊市核心0%（全空）", dict(bear_core_w=0.0)),
    ):
        nav = run_trend(px, **kw)
        nav = nav / nav.iloc[0]
        m = B.metr(nav)
        rows.append((label, nav, m))
        print(f"  {label:<26}{m['total']:>+9.1f}%{m['cagr']:>+8.1f}%{m['mdd']:>+8.1f}%"
              f"{m['calmar']:>8.2f}{m['月胜率']:>8.1f}%{m['最差月']:>+8.1f}%"
              f"{m['连亏月']:>6}")
    print(f"  {'沪深300':<26}{bm['total']:>+9.1f}%{bm['cagr']:>+8.1f}%{bm['mdd']:>+8.1f}%"
          f"{bm['calmar']:>8.2f}{bm['月胜率']:>8.1f}%{bm['最差月']:>+8.1f}%"
          f"{bm['连亏月']:>6}")

    # 选出回撤 ≤20% 且卡玛最高者
    ok = [(lbl, m) for lbl, _, m in rows if m["mdd"] >= -20]
    print()
    if ok:
        best = max(ok, key=lambda x: x[1]["calmar"])
        print(f"  ★ 回撤 ≤20% 的方案中卡玛最高：{best[0]}")
        print(f"     累计 {best[1]['total']:+.1f}%  年化 {best[1]['cagr']:+.1f}%  "
              f"回撤 {best[1]['mdd']:+.1f}%  卡玛 {best[1]['calmar']:.2f}")
        # 逐年
        nav = dict((lbl, n) for lbl, n, _ in rows)
        print()
        print(f"  {'年份':<8}" + "".join(f"{lbl[:14]:>16}" for lbl, _, _ in rows))
        print("  " + "-" * (8 + 16 * len(rows)))
        for y in ("2022", "2023", "2024", "2025", "2026"):
            cells = []
            for lbl, n, _ in rows:
                seg = n[n.index.str.startswith(y)]
                cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+15.1f}%" if len(seg) >= 20 else f"{'—':>16}")
            print(f"  {y:<8}" + "".join(cells))
    else:
        print("  ❌ 所有方案回撤仍超 20%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
