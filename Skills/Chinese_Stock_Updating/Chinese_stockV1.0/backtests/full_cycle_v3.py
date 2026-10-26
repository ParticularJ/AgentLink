#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""完整周期回测（2022-04 ~ 2026-10，4.5 年，**含 2022 熊市**）

数据边界与替代方案（必须先说清）
--------------------------------
原核心仓（银行/电力/宽基 ETF）行情只有 2024-02 起，**无法回溯到 2022**。
为了拿到"含熊市"的完整周期结论，本脚本用**核心仓代理**：

  核心仓代理（长历史、价值/防御属性）：
    sz159755 消费ETF     sz159996 家电ETF
    sh516510 煤炭/资源   sz159992 医药ETF   sh518880 黄金ETF

  说明：这不是原来那 11 只（银行/电力），但胜在**有 4.5 年历史**，
        可以回答"这套三层框架在完整牛熊周期里是否成立"这个更根本的问题。
        代价：代理核心的收益特征与原核心不同（消费/医药在 2022-2023 跌得更多）。

卫星仓：10 个长历史板块 ETF（动量前 3 + M3 开关 + 止损），与原方案一致。

输出：
  1) 全周期（含熊市）表现
  2) 逐年 / 逐段分解
  3) 与沪深300、纯核心、纯卫星对照
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
BENCH = "sh000300"

# 核心仓代理（长历史；注：黄金 sh518880 只有 2024-02 起，为保住 4.5 年周期剔除）
CORE_PROXY: Dict[str, str] = {
    "消费": "sz159755",
    "家电": "sz159996",
    "煤炭资源": "sh516510",
    "医药": "sz159992",
}
# 卫星仓板块池（长历史）
SAT_POOL: Dict[str, str] = {
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
COST = 0.0005
CORE_W, SAT_W = 0.70, 0.30
N_SEC, MOM_WIN, USE_GATE, HOLD = 3, 60, True, 20
STOP, TRAIL = -0.10, -0.15


def load(code: str, start: str, end: str) -> Optional[pd.Series]:
    p = CACHE / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = df["date"].astype(str).str[:10]
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    if len(df) < 100:
        return None
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def build(start: str, end: str) -> pd.DataFrame:
    """构造价格矩阵。

    ⚠️ 2026-10-17 修正（同类 bug 第二次）：pd.DataFrame(...).dropna() 会被
    **最短历史的标的**截断。第一次是 final_strategy.py（黄金/银行只有 2024-02
    起 → 整个回测从 2024-02 开始），这次是煤炭/黄金混进来。
    修正：显式声明**只有长历史标的**进入完整周期回测，并断言起点足够早。
    """
    codes = set(list(CORE_PROXY.values()) + list(SAT_POOL.values()) + [BENCH])
    d = {}
    for c in codes:
        s = load(c, start, end)
        if s is not None:
            d[c] = s
    px = pd.DataFrame(d).sort_index()
    need = [c for c in codes if c in px.columns]
    px = px[need].dropna()
    assert px.notna().all().all()
    if px.index[0] > "2022-06-01":
        raise SystemExit(
            f"❌ 起点被截断到 {px.index[0]}（要求 ≤2022-06-01）："
            f"请检查哪些标的没有长历史")
    return px


def run(px: pd.DataFrame, core_w: float = CORE_W, sat_w: float = SAT_W,
        use_gate: bool = USE_GATE) -> pd.Series:
    dates = list(px.index)
    core = [c for c in CORE_PROXY.values() if c in px.columns]
    sec = [c for c in SAT_POOL.values() if c in px.columns]
    mom = px[sec].pct_change(MOM_WIN)
    disp = px[sec].pct_change(20).std(axis=1)
    dmed = disp.expanding(min_periods=100).median()

    cash, cu, sat, peak, entry = 1.0, {}, {}, {}, {}
    curve, last = [], -10 ** 6
    WARM = 140

    for i, dt in enumerate(dates):
        if i > 0:
            for c in list(sat.keys()):
                cur = px[c].iloc[i]
                peak[c] = max(peak[c], cur)
                if (cur / entry[c] - 1) <= STOP or (cur / peak[c] - 1) <= TRAIL:
                    cash += sat[c] * cur * (1 - COST)
                    del sat[c], peak[c], entry[c]
        cv = sum(u * px[c].iloc[i] for c, u in cu.items())
        sv = sum(u * px[c].iloc[i] for c, u in sat.items())
        nav = cash + cv + sv
        assert nav == nav and nav > 0
        curve.append(nav)

        if i == WARM:
            for c in core:
                u = (nav * core_w / len(core)) / px[c].iloc[i]
                cu[c] = u
                cash -= u * px[c].iloc[i]
            continue
        if i < WARM:
            continue
        # 核心季度再平衡
        if (i - WARM) % 60 == 0:
            cv = sum(u * px[c].iloc[i] for c, u in cu.items())
            tgt = nav * core_w
            if cv > 1e-9 and abs(cv - tgt) > nav * 0.03:
                cash += (cv - tgt) * (1 - COST)
                for c in core:
                    cu[c] *= tgt / cv
        if (i - last) < HOLD:
            continue
        j = i - 1
        gated = bool(use_gate and disp.iloc[j] == disp.iloc[j]
                     and dmed.iloc[j] == dmed.iloc[j]
                     and disp.iloc[j] < dmed.iloc[j])
        picked: List[str] = []
        if not gated:
            sc = {c: mom[c].iloc[j] for c in sec if mom[c].iloc[j] == mom[c].iloc[j]}
            picked = [c for c, v in sorted(sc.items(), key=lambda kv: -kv[1])[:N_SEC]
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


def metr(nav: pd.Series) -> dict:
    if len(nav) < 40:
        return {}
    ny = len(nav) / 242
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / ny) - 1
    mdd = (nav / nav.cummax() - 1).min()
    m = nav.groupby(nav.index.str[:7]).last().pct_change().dropna()
    streak = best = 0
    for v in m:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    return {"total": (nav.iloc[-1] / nav.iloc[0] - 1) * 100, "cagr": cagr * 100,
            "mdd": mdd * 100, "calmar": (cagr / abs(mdd)) if mdd < 0 else float("nan"),
            "月胜率": (m > 0).mean() * 100 if len(m) else 0,
            "达标月": (m >= 0.012).mean() * 100 if len(m) else 0,
            "最差月": m.min() * 100 if len(m) else 0, "连亏月": best,
            "days": len(nav)}


def main() -> int:
    START, END = "2022-04-01", "2026-10-16"
    px = build(START, END)
    print(f"完整周期 {px.index[0]} → {px.index[-1]}（{len(px)} 日 / "
          f"{len(px)/242:.2f} 年）")
    print(f"核心代理 {len(CORE_PROXY)} 只：{'、'.join(CORE_PROXY)}")
    print(f"卫星池 {len(SAT_POOL)} 个板块\n")

    nav = run(px)
    nav = nav / nav.iloc[0]
    m = metr(nav)
    b = px[BENCH] / px[BENCH].iloc[0]
    bm = metr(b)

    # 纯核心 / 纯卫星对照
    core_only = run(px, 1.0, 0.0)
    core_only = core_only / core_only.iloc[0]
    cm = metr(core_only)
    sat_only = run(px, 0.0, 1.0)
    sat_only = sat_only / sat_only.iloc[0]
    sm = metr(sat_only)

    print("=" * 100)
    print("完整周期表现（2022-04 ~ 2026-10，含 2022 熊市，含成本）")
    print("=" * 100)
    print(f"  {'方案':<24}{'累计':>10}{'年化':>9}{'回撤':>9}{'卡玛':>8}"
          f"{'月胜率':>9}{'达标月':>9}{'最差月':>9}{'连亏':>6}")
    print("  " + "-" * 90)
    for name, mm in (("最终策略 70/30", m), ("纯核心 100%", cm),
                     ("纯卫星 100%", sm), ("沪深300", bm)):
        print(f"  {name:<24}{mm['total']:>+9.1f}%{mm['cagr']:>+8.1f}%{mm['mdd']:>+8.1f}%"
              f"{mm['calmar']:>8.2f}{mm['月胜率']:>8.1f}%{mm['达标月']:>8.1f}%"
              f"{mm['最差月']:>+8.1f}%{mm['连亏月']:>6}")

    print()
    print("=" * 100)
    print("逐年分解（关键：2022 熊市与 2023 震荡）")
    print("=" * 100)
    print(f"  {'年份':<8}{'最终策略':>11}{'纯核心':>11}{'纯卫星':>11}{'沪深300':>11}")
    print("  " + "-" * 54)
    for y in ("2022", "2023", "2024", "2025", "2026"):
        cells = []
        for s in (nav, core_only, sat_only, b):
            seg = s[s.index.str.startswith(y)]
            cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+10.1f}%" if len(seg) >= 20 else f"{'—':>11}")
        print(f"  {y:<8}" + "".join(cells))

    print()
    print("=" * 100)
    print("分段：924 前 vs 924 后")
    print("=" * 100)
    print(f"  {'区间':<26}{'最终策略':>11}{'纯核心':>11}{'沪深300':>11}")
    print("  " + "-" * 62)
    for label, s0, s1 in (("924 前（2022-04~2024-09）", "2022-04-01", "2024-09-23"),
                          ("924 后（2024-09~2026-10）", "2024-09-24", "2026-10-16")):
        cells = []
        for s in (nav, core_only, b):
            seg = s[(s.index >= s0) & (s.index <= s1)]
            cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+10.1f}%" if len(seg) > 30 else f"{'—':>11}")
        print(f"  {label:<26}" + "".join(cells))

    print()
    print("=" * 100)
    print("M3 开关在完整周期的作用（开 vs 关）")
    print("=" * 100)
    no_gate = run(px, CORE_W, SAT_W, use_gate=False)
    no_gate = no_gate / no_gate.iloc[0]
    gm = metr(no_gate)
    print(f"  开: 累计 {m['total']:+.1f}%  年化 {m['cagr']:+.1f}%  回撤 {m['mdd']:+.1f}%  卡玛 {m['calmar']:.2f}")
    print(f"  关: 累计 {gm['total']:+.1f}%  年化 {gm['cagr']:+.1f}%  回撤 {gm['mdd']:+.1f}%  卡玛 {gm['calmar']:.2f}")
    print(f"  差额: {m['total']-gm['total']:+.1f}pp  "
          f"{'✅ 开关有用' if m['total'] > gm['total'] else '❌ 开关有害'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
