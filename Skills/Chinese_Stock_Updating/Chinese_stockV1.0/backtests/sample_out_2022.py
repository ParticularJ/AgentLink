#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""样本代表性检验 v2：用「覆盖 2022 的 10 个板块 ETF」做真正的样本外

用户质疑（2026-10-17）
----------------------
"2024-02-26 → 2026-10-15 这个时段完全覆盖了本轮牛市（24年9.24之后）的行情，
 你觉得样本有代表性吗？"

**质疑成立。本脚本用能覆盖 2022 熊市的板块 ETF 做对照。**

细分区间（避免"一整段"掩盖差异）
  段1  2022-03 ~ 2022-12   2022 熊市（沪指全年 −21.6%）
  段2  2023-01 ~ 2024-01   2023 震荡下行
  段3  2024-02 ~ 2024-09   924 前夕（阴跌）
  段4  2024-09 ~ 2026-10   924 之后（牛市）
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))
CACHE = HERE / "cache"
BENCH = "sh000300"

# 覆盖 2022 的 10 个板块 ETF
LONG: Dict[str, str] = {
    "军工": "sh512660",
    "新能源": "sh515790",
    "稀土": "sh516150",
    "化工": "sh516220",
    "高端装备": "sh516320",
    "基建": "sh516510",
    "消费": "sz159755",
    "消费电子": "sz159779",
    "低空经济": "sz159795",
    "医药": "sz159992",
    "家电": "sz159996",
    "创业板": "sz159949",
    "白银": "sz161226",
}

SEGMENTS = [
    ("段1 2022熊市", "2022-04-01", "2022-12-30"),
    ("段2 2023震荡下行", "2023-01-03", "2024-01-31"),
    ("段3 924前夕阴跌", "2024-02-01", "2024-09-23"),
    ("段4 924后牛市", "2024-09-24", "2026-10-16"),
]


def load(code: str, start: str, end: str) -> Optional[pd.Series]:
    p = CACHE / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = df["date"].astype(str).str[:10]
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    if len(df) < 60:
        return None
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def run_sat(codes: List[str], start: str, end: str, n_sec: int = 3,
            mom_win: int = 60, use_gate: bool = True, hold: int = 20) -> pd.Series:
    d = {}
    for c in codes:
        s = load(c, start, end)
        if s is not None:
            d[c] = s
    px = pd.DataFrame(d).sort_index().dropna()
    if px.shape[1] < 4 or len(px) < 150:
        return pd.Series(dtype=float)
    mom = px.pct_change(mom_win)
    disp = px.pct_change(20).std(axis=1)
    disp_med = disp.expanding(min_periods=100).median()
    dates = list(px.index)

    cash, units, peak, entry = 1.0, {}, {}, {}
    curve, last = [], -10 ** 6
    COST, STOP, TRAIL = 0.0005, -0.10, -0.15

    for i, dt in enumerate(dates):
        if i > 0:
            for c in list(units.keys()):
                cur = px[c].iloc[i]
                peak[c] = max(peak[c], cur)
                if (cur / entry[c] - 1) <= STOP or (cur / peak[c] - 1) <= TRAIL:
                    cash += units[c] * cur * (1 - COST)
                    del units[c], peak[c], entry[c]
        v = cash + sum(u * px[c].iloc[i] for c, u in units.items())
        curve.append(v)
        if i < max(mom_win, 120) or (i - last) < hold:
            continue
        last = i
        j = i - 1
        gated = bool(use_gate and disp.iloc[j] == disp.iloc[j]
                     and disp_med.iloc[j] == disp_med.iloc[j]
                     and disp.iloc[j] < disp_med.iloc[j])
        picked: List[str] = []
        if not gated:
            sc = {c: mom[c].iloc[j] for c in px.columns if mom[c].iloc[j] == mom[c].iloc[j]}
            picked = [c for c, vv in sorted(sc.items(), key=lambda kv: -kv[1])[:n_sec]
                      if vv > 0]
        for c in list(units.keys()):
            if c not in picked:
                cash += units[c] * px[c].iloc[i] * (1 - COST)
                del units[c], peak[c], entry[c]
        if picked:
            per = v / len(picked)
            for c in picked:
                cur_v = units.get(c, 0.0) * px[c].iloc[i]
                need = per - cur_v
                if need <= v * 0.01 or cash <= 0:
                    continue
                aff = min(need, cash / (1 + COST))
                u = aff / px[c].iloc[i]
                cash -= u * px[c].iloc[i] * (1 + COST)
                if c not in units:
                    units[c] = 0.0
                    entry[c] = px[c].iloc[i]
                    peak[c] = px[c].iloc[i]
                units[c] += u
    return pd.Series(curve, index=dates)


def metr(nav: pd.Series) -> dict:
    if len(nav) < 40:
        return {}
    ny = len(nav) / 242
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / ny) - 1
    mdd = (nav / nav.cummax() - 1).min()
    return {"total": (nav.iloc[-1] / nav.iloc[0] - 1) * 100, "cagr": cagr * 100,
            "mdd": mdd * 100, "days": len(nav),
            "calmar": (cagr / abs(mdd)) if mdd < 0 else float("nan")}


def main() -> int:
    codes = list(LONG.values())
    print("=" * 104)
    print("分段检验：卫星仓（10 个板块 ETF，动量前3 + M3开关 + 止损）")
    print("=" * 104)
    print(f"  {'区间':<22}{'策略累计':>10}{'策略回撤':>10}{'沪深300':>10}"
          f"{'超额(pp)':>10}{'交易日':>8}")
    print("  " + "-" * 74)
    for label, s, e in SEGMENTS:
        nav = run_sat(codes, s, e)
        b = load(BENCH, s, e)
        if nav.empty:
            print(f"  {label:<22}{'数据不足':>10}")
            continue
        nav = nav / nav.iloc[0]
        m = metr(nav)
        bm = metr(b / b.iloc[0]) if b is not None else {}
        bt = bm.get("total", float("nan"))
        print(f"  {label:<22}{m['total']:>+9.1f}%{m['mdd']:>+9.1f}%"
              f"{bt:>+9.1f}%{m['total']-bt:>+9.1f}{m['days']:>8}")

    print()
    print("=" * 104)
    print("对照：各段「板块等权买入持有」与「沪深300」")
    print("=" * 104)
    print(f"  {'区间':<22}{'板块等权':>10}{'沪深300':>10}{'卫星策略':>10}")
    print("  " + "-" * 54)
    for label, s, e in SEGMENTS:
        d = {}
        for c in codes:
            ser = load(c, s, e)
            if ser is not None:
                d[c] = ser
        px = pd.DataFrame(d).sort_index().dropna()
        if px.shape[1] < 4 or len(px) < 40:
            continue
        eq = (px / px.iloc[0]).mean(axis=1)
        em = metr(eq)
        b = load(BENCH, s, e)
        bm = metr(b / b.iloc[0]) if b is not None else {}
        nav = run_sat(codes, s, e)
        st = metr(nav / nav.iloc[0]) if not nav.empty else {}
        print(f"  {label:<22}{em['total']:>+9.1f}%{bm.get('total', 0):>+9.1f}%"
              f"{st.get('total', float('nan')):>+9.1f}%")

    print()
    print("=" * 104)
    print("三段合并（2022-04 ~ 2024-09，即 924 前，共约 2.4 年）")
    print("=" * 104)
    nav = run_sat(codes, "2022-04-01", "2024-09-23")
    if not nav.empty:
        nav = nav / nav.iloc[0]
        m = metr(nav)
        b = load(BENCH, "2022-04-01", "2024-09-23")
        bm = metr(b / b.iloc[0])
        print(f"  卫星策略: 累计 {m['total']:+.1f}%  年化 {m['cagr']:+.1f}%  "
              f"回撤 {m['mdd']:+.1f}%  卡玛 {m['calmar']:.2f}")
        print(f"  沪深300 : 累计 {bm['total']:+.1f}%  年化 {bm['cagr']:+.1f}%  "
              f"回撤 {bm['mdd']:+.1f}%  卡玛 {bm['calmar']:.2f}")
        print(f"  超额    : {m['total']-bm['total']:+.1f}pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
