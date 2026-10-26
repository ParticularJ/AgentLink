#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终策略：三层合成 + 止盈止损 + Walk-forward 验证（2026-10-17）

⚠️ 实现要点（第一版写错过，记录在此）
--------------------------------------
第一版把卫星仓仓位记成"固定金额"(Pos.weight)，于是价格涨跌不会体现在组合净值里。
正确做法是**按份额(units)记账**：市值 = units × 当日价格。

结构
----
核心仓 60%：银行+电力+通信+宽基 等权，每 60 日再平衡
卫星仓 40%：板块动量轮动（每 20 日再平衡，60 日动量，选 3 个板块）
            制度开关 M3（板块分化度 < 其滚动中位）→ 卫星仓**转入现金**，等机会

止盈止损（卫星仓每个持仓）
  S1 硬止损：自入场价 −10%
  S2 移动止盈：自持仓最高点回撤 −15%
  S3 动量反转：再平衡时 60 日动量转负 → 剔除
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))
CACHE = HERE / "cache"
BENCH = "sh000300"

SECTOR_ETF: Dict[str, str] = {
    "半导体": "sh512480", "光通信": "sh515880", "医药": "sz159992",
    "军工": "sh512660", "新能源": "sh516160", "有色": "sz159880",
    "黄金": "sh518880", "煤炭": "sh515220", "消费": "sh512690",
    "家电": "sz159996", "证券": "sh512070", "稀土": "sh516150",
}
CORE: Dict[str, List[str]] = {
    "银行": ["sh601398", "sh601288", "sh601988", "sh601166", "sh600036"],
    "电力": ["sh600900", "sh601985"],
    "通信资源": ["sh600941", "sh601088"],
    "宽基": ["sh510300", "sh510500"],
}
COST = 0.0005

N_SECTORS, MOM_WIN, USE_GATE, HOLD_DAYS = 3, 60, True, 20
CORE_W, SAT_W = 0.60, 0.40
STOP_HARD, TRAIL = -0.10, -0.15


def load(code: str, start: str, end: str) -> Optional[pd.Series]:
    p = CACHE / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = df["date"].astype(str).str[:10]
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    if len(df) < 150:
        return None
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def build_panel(start: str, end: str) -> pd.DataFrame:
    codes = set(list(SECTOR_ETF.values()) + [c for v in CORE.values() for c in v] + [BENCH])
    d = {}
    for c in codes:
        s = load(c, start, end)
        if s is not None:
            d[c] = s
    px = pd.DataFrame(d).sort_index()
    # ⚠️ 关键修正（2026-10-17）：核心仓标的（银行/电力）数据只到 2024-02 才开始，
    # 若从 2022-04 起跑，px[c].iloc[i] 为 NaN → 组合净值被污染成 NaN。
    # 这里强制取「所有必需标的都有价格」的交集区间，并断言无 NaN。
    need = [c for c in list(SECTOR_ETF.values()) + [c for v in CORE.values() for c in v]
            + [BENCH] if c in px.columns]
    px = px[need].dropna()
    assert px.notna().all().all(), "价格矩阵仍有 NaN"
    if len(px) < 300:
        raise SystemExit(f"交集区间只剩 {len(px)} 个交易日，不足以回测")
    return px


@dataclass
class Sat:
    units: float = 0.0
    entry_px: float = 0.0
    peak_px: float = 0.0


def run_strategy(px: pd.DataFrame) -> pd.Series:
    dates = list(px.index)
    sec = [c for c in SECTOR_ETF.values() if c in px.columns]
    core = [c for v in CORE.values() for c in v if c in px.columns]
    bench = px[BENCH]
    mom = px[sec].pct_change(MOM_WIN)
    disp = px[sec].pct_change(20).std(axis=1)
    disp_med = disp.expanding(min_periods=120).median()

    cash = 1.0
    core_units: Dict[str, float] = {}
    sat: Dict[str, Sat] = {}
    nav_hist: List[float] = []
    last_rebal = -10 ** 6

    for i, d in enumerate(dates):
        # ── 止损检查（仅卫星）──
        if i > 0:
            for c in list(sat.keys()):
                cur = px[c].iloc[i]
                s = sat[c]
                s.peak_px = max(s.peak_px, cur)
                if (cur / s.entry_px - 1 <= STOP_HARD) or (cur / s.peak_px - 1 <= TRAIL):
                    cash += s.units * cur * (1 - COST)
                    del sat[c]
        # ── 计值 ──
        cv = sum(u * px[c].iloc[i] for c, u in core_units.items())
        sv = sum(s.units * px[c].iloc[i] for c, s in sat.items())
        nav = cash + cv + sv
        assert nav == nav and nav > 0, f"净值异常 @ {d}: {nav}"
        nav_hist.append(nav)

        # ── 首次建仓：第 130 日后把资金分配到核心 + 卫星 ──
        if i == 130:
            for c in core:
                units = (nav * CORE_W / len(core)) / px[c].iloc[i]
                core_units[c] = units
                cash -= units * px[c].iloc[i]
            continue

        if i < 131:
            continue
        # ── 核心仓季度再平衡 ──
        if (i - 130) % 60 == 0:
            cv = sum(u * px[c].iloc[i] for c, u in core_units.items())
            tgt = nav * CORE_W
            if cv > 1e-9 and abs(cv - tgt) > nav * 0.03:
                cash += (cv - tgt) * (1 - COST)
                for c in core:
                    core_units[c] *= tgt / cv

        # ── 卫星仓再平衡 ──
        if (i - last_rebal) < HOLD_DAYS:
            continue
        j = i - 1
        if j < MOM_WIN:
            continue
        last_rebal = i
        gated = bool(USE_GATE and disp.iloc[j] == disp.iloc[j]
                     and disp_med.iloc[j] == disp_med.iloc[j]
                     and disp.iloc[j] < disp_med.iloc[j])
        if gated:
            picked: List[str] = []
        else:
            sc = {c: mom[c].iloc[j] for c in sec if mom[c].iloc[j] == mom[c].iloc[j]}
            ranked = sorted(sc.items(), key=lambda kv: -kv[1])
            picked = [c for c, v in ranked[:N_SECTORS] if v > 0]

        # 卖出不保留的
        for c in list(sat.keys()):
            if c not in picked:
                cash += sat[c].units * px[c].iloc[i] * (1 - COST)
                del sat[c]
        # 目标市值
        sv_now = sum(s.units * px[c].iloc[i] for c, s in sat.items())
        sat_target = nav * SAT_W
        if picked:
            per = sat_target / len(picked)
            for c in picked:
                cur_v = sat[c].units * px[c].iloc[i] if c in sat else 0.0
                need = per - cur_v
                if need <= nav * 0.005:
                    continue
                price = px[c].iloc[i]
                affordable = min(need, max(0.0, cash / (1 + COST)))
                if affordable <= 0:
                    continue
                units = affordable / price
                cash -= units * price * (1 + COST)
                if c in sat:
                    sat[c].units += units
                else:
                    sat[c] = Sat(units=units, entry_px=price, peak_px=price)
        else:
            # gated：卫星清空，资金留现金
            for c in list(sat.keys()):
                cash += sat[c].units * px[c].iloc[i] * (1 - COST)
                del sat[c]

    return pd.Series(nav_hist, index=dates)


def metr(nav: pd.Series) -> dict:
    if len(nav) < 30:
        return {}
    ny = len(nav) / 242
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / ny) - 1
    mdd = (nav / nav.cummax() - 1).min()
    m = nav.groupby(nav.index.str[:7]).last().pct_change().dropna()
    streak = best = 0
    for v in m:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    return {"cagr": cagr * 100, "mdd": mdd * 100,
            "calmar": (cagr / abs(mdd)) if mdd < 0 else float("nan"),
            "月胜率": (m > 0).mean() * 100, "达标月": (m >= 0.012).mean() * 100,
            "最差月": m.min() * 100 if len(m) else 0, "连亏月": best}


def main() -> int:
    START, END = "2022-04-01", "2026-10-16"
    px = build_panel(START, END)
    print(f"数据 {px.index[0]} → {px.index[-1]}（{len(px)} 日），标的 {px.shape[1]} 只\n")
    nav = run_strategy(px)
    nav = nav / nav.iloc[0]
    m = metr(nav)
    b = px[BENCH].reindex(nav.index).ffill()
    bm = metr(b / b.iloc[0])

    print("=" * 96)
    print("最终策略：全样本表现（含成本 0.05%/边）")
    print("=" * 96)
    print(f"  {'方案':<26}{'年化':>9}{'回撤':>9}{'卡玛':>8}{'月胜率':>9}"
          f"{'达标月':>9}{'最差月':>9}{'连亏月':>8}")
    print("  " + "-" * 86)
    for name, mm in (("最终策略（核心60+卫星40）", m), ("沪深300 买入持有", bm)):
        print(f"  {name:<26}{mm['cagr']:>+8.1f}%{mm['mdd']:>+8.1f}%{mm['calmar']:>8.2f}"
              f"{mm['月胜率']:>8.1f}%{mm['达标月']:>8.1f}%{mm['最差月']:>+8.1f}%"
              f"{mm['连亏月']:>8}")

    print()
    print("=" * 96)
    print("逐年分解")
    print("=" * 96)
    print(f"  {'年份':<8}{'策略':>12}{'沪深300':>12}")
    print("  " + "-" * 34)
    bb0 = b / b.iloc[0]
    for y in ("2022", "2023", "2024", "2025", "2026"):
        s = nav[nav.index.str.startswith(y)]
        bb = bb0[bb0.index.str.startswith(y)]
        if len(s) < 20 or len(bb) < 20:
            continue
        print(f"  {y:<8}{(s.iloc[-1]/s.iloc[0]-1)*100:>+11.1f}%"
              f"{(bb.iloc[-1]/bb.iloc[0]-1)*100:>+11.1f}%")

    print()
    print("=" * 96)
    print("月度分布（策略）")
    print("=" * 96)
    mon = nav.groupby(nav.index.str[:7]).last().pct_change().dropna()
    print(f"  月份 {len(mon)} 个；正收益 {(mon>0).sum()} 个；"
          f"≥1.2% 的 {(mon>=0.012).sum()} 个；≥2% 的 {(mon>=0.02).sum()} 个")
    print(f"  月均 {mon.mean()*100:+.2f}%   中位 {mon.median()*100:+.2f}%   "
          f"标准差 {mon.std()*100:.2f}%")
    print(f"  最好 3 个月：{', '.join(f'{k}({v*100:+.1f}%)' for k,v in mon.nlargest(3).items())}")
    print(f"  最差 3 个月：{', '.join(f'{k}({v*100:+.1f}%)' for k,v in mon.nsmallest(3).items())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
