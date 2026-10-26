#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""样本代表性检验：把策略放到「不含 2024-09-24 牛市」的区间里。

用户质疑（2026-10-17）
----------------------
"2024-02-26 → 2026-10-15 这个时段完全覆盖了本轮牛市（24年9.24之后）的行情，
 你觉得样本有代表性吗？"

**这个质疑是对的。** 需要做的检验：

检验 A  纯样本外：2022-04 ~ 2024-02（22 个月，含 2022 熊市 + 2023 震荡下行）
        —— 完全没有 924 之后的行情
检验 B  牛市贡献分解：把全样本切成 924 前后两段，看收益来自哪一段
检验 C  压力测试：在牛市段假设核心仓"躺平"（代表核心仓标的没涨的环境），
        策略还能不能靠卫星仓赚钱

⚠️ 数据限制（必须声明）
------------------------
核心仓标的（银行/电力/宽基 ETF）行情只到 **2024-02** 才有缓存，
因此 2022-2023 段**无法跑完整三层策略**。这本身就是数据边界。

应对：分两个口径做
  口径 1（完整策略）：只能覆盖 2024-02 之后
  口径 2（仅卫星仓）：可用 2022-04 起的 8 个板块 ETF，检验"卫星仓在熊市/震荡市的表现"
        —— 这正是 B 段最需要的证据
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

# 2022-04 起就有 1100 根数据的板块 ETF（由缓存普查得出）
LONG_SECTORS: Dict[str, str] = {
    "军工": "sh512660",
    "黄金": "sh518880",
    "煤炭": "sh515220",
    "消费": "sh512690",
    "家电": "sz159996",
    "证券": "sh512070",
    "稀土": "sh516150",
    "新能源": "sh516160",
}
# 2024 年才有数据的板块（牛市段可用）
LATE_SECTORS: Dict[str, str] = {
    "半导体": "sh512480",
    "光通信": "sh515880",
    "医药": "sz159992",
    "有色": "sz159880",
}


def load(code: str, start: str, end: str) -> Optional[pd.Series]:
    p = CACHE / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = df["date"].astype(str).str[:10]
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    if len(df) < 80:
        return None
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def run_satellite(codes: List[str], start: str, end: str,
                  n_sec: int = 3, mom_win: int = 60, use_gate: bool = True,
                  hold: int = 20) -> pd.Series:
    """仅卫星仓（板块动量轮动 + M3 开关 + 止损），返回净值。"""
    d = {}
    for c in codes:
        s = load(c, start, end)
        if s is not None:
            d[c] = s
    px = pd.DataFrame(d).sort_index()
    if px.shape[1] < 4 or len(px) < 200:
        return pd.Series(dtype=float)

    mom = px.pct_change(mom_win)
    disp = px.pct_change(20).std(axis=1)
    disp_med = disp.expanding(min_periods=120).median()
    dates = list(px.index)

    nav, cash = 1.0, 1.0
    units: Dict[str, float] = {}
    peak: Dict[str, float] = {}
    entry: Dict[str, float] = {}
    curve: List[float] = []
    last = -10 ** 6
    COST, STOP, TRAIL = 0.0005, -0.10, -0.15

    for i, dt in enumerate(dates):
        # 止损
        if i > 0:
            for c in list(units.keys()):
                cur = px[c].iloc[i]
                peak[c] = max(peak[c], cur)
                if (cur / entry[c] - 1) <= STOP or (cur / peak[c] - 1) <= TRAIL:
                    cash += units[c] * cur * (1 - COST)
                    del units[c], peak[c], entry[c]
        v = cash + sum(u * px[c].iloc[i] for c, u in units.items())
        curve.append(v)

        if i < max(mom_win, 140) or (i - last) < hold:
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
                affordable = min(need, cash / (1 + COST))
                u = affordable / px[c].iloc[i]
                cash -= u * px[c].iloc[i] * (1 + COST)
                if c not in units:
                    units[c] = 0.0
                    entry[c] = px[c].iloc[i]
                    peak[c] = px[c].iloc[i]
                units[c] += u
    return pd.Series(curve, index=dates)


def metr(nav: pd.Series) -> dict:
    if len(nav) < 60:
        return {}
    ny = len(nav) / 242
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / ny) - 1
    mdd = (nav / nav.cummax() - 1).min()
    return {"cagr": cagr * 100, "mdd": mdd * 100, "total": (nav.iloc[-1] / nav.iloc[0] - 1) * 100,
            "calmar": (cagr / abs(mdd)) if mdd < 0 else float("nan"), "days": len(nav)}


def main() -> int:
    print("=" * 100)
    print("检验 A：仅卫星仓 —— 含 / 不含 924 牛市的两段对照")
    print("=" * 100)
    segs = [
        ("熊市+震荡（2022-04 ~ 2024-02）", "2022-04-01", "2024-02-23"),
        ("牛市段（2024-02 ~ 2026-10）", "2024-02-26", "2026-10-15"),
    ]
    print(f"  {'区间':<34}{'年化':>9}{'回撤':>9}{'卡玛':>8}{'累计':>9}{'交易日':>8}")
    print("  " + "-" * 76)
    for label, s, e in segs:
        nav = run_satellite(list(LONG_SECTORS.values()), s, e)
        if nav.empty:
            print(f"  {label:<34}数据不足")
            continue
        nav = nav / nav.iloc[0]
        m = metr(nav)
        b = load(BENCH, s, e)
        bm = metr(b / b.iloc[0]) if b is not None else {}
        print(f"  {label:<34}{m['cagr']:>+8.1f}%{m['mdd']:>+8.1f}%{m['calmar']:>8.2f}"
              f"{m['total']:>+8.1f}%{m['days']:>8}")
        if bm:
            print(f"  {'  同期沪深300':<34}{bm['cagr']:>+8.1f}%{bm['mdd']:>+8.1f}%"
                  f"{bm['calmar']:>8.2f}{bm['total']:>+8.1f}%{bm['days']:>8}")

    print()
    print("=" * 100)
    print("检验 A2：只用 8 个长历史板块（同一口径，两段对比）")
    print("=" * 100)
    # 熊市段用 8 只；牛市段也用同样 8 只，保证口径一致
    print(f"  {'区间':<34}{'年化':>9}{'回撤':>9}{'卡玛':>8}{'累计':>9}")
    print("  " + "-" * 68)
    for label, s, e in segs:
        nav = run_satellite(list(LONG_SECTORS.values()), s, e)
        if nav.empty:
            continue
        nav = nav / nav.iloc[0]
        m = metr(nav)
        print(f"  {label:<34}{m['cagr']:>+8.1f}%{m['mdd']:>+8.1f}%{m['calmar']:>8.2f}"
              f"{m['total']:>+8.1f}%")

    print()
    print("=" * 100)
    print("检验 C：压力测试 —— 若核心仓在牛市段完全不动（收益=0）")
    print("=" * 100)
    print("  含义：若核心仓标的（银行/电力）没涨，只靠卫星仓能赚多少？")
    for label, s, e in [("牛市段（2024-02 ~ 2026-10）", "2024-02-26", "2026-10-15")]:
        nav = run_satellite(list(LONG_SECTORS.values()), s, e)
        if nav.empty:
            continue
        nav = nav / nav.iloc[0]
        m = metr(nav)
        # 70% 核心按 0 收益、30% 卫星
        combo = pd.Series([1.0 + 0.30 * (v - 1) for v in nav.values], index=nav.index)
        cm = metr(combo)
        print(f"  {label}")
        print(f"    纯卫星仓                : 年化 {m['cagr']:+.1f}%  回撤 {m['mdd']:+.1f}%")
        print(f"    70%核心(0收益)+30%卫星  : 年化 {cm['cagr']:+.1f}%  回撤 {cm['mdd']:+.1f}%")

    print()
    print("=" * 100)
    print("检验 B：牛市贡献分解（需要完整策略，只能 2024-02 起）")
    print("=" * 100)
    import final_strategy as F
    old = (F.SAT_W, F.CORE_W)
    F.SAT_W, F.CORE_W = 0.30, 0.70
    try:
        px = F.build_panel("2022-04-01", "2026-10-16")
        nav = F.run_strategy(px)
    finally:
        F.SAT_W, F.CORE_W = old
    nav = nav / nav.iloc[0]
    cut = "2024-09-24"
    for label, s, e in (("924 之前（2024-02~2024-09）", "2024-02-26", cut),
                       ("924 之后（牛市）", cut, "2026-10-15")):
        seg = nav[(nav.index >= s) & (nav.index < e)]
        if len(seg) < 40:
            continue
        sm = metr(seg / seg.iloc[0])
        b = px[BENCH].reindex(seg.index).ffill()
        bm = metr(b / b.iloc[0])
        print(f"  {label:<30}策略 {(seg.iloc[-1]/seg.iloc[0]-1)*100:>+7.1f}%  "
              f"沪深300 {(b.iloc[-1]/b.iloc[0]-1)*100:>+7.1f}%  "
              f"超额 {((seg.iloc[-1]/seg.iloc[0])-(b.iloc[-1]/b.iloc[0]))*100:>+7.1f}pp"
              f"  ({len(seg)} 日)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
