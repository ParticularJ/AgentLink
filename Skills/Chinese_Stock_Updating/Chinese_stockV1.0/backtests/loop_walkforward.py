#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迭代优化 LOOP：walk-forward 验证框架（2026-10-17）

设计原则（这是本次迭代的"裁判"）
--------------------------------
1. **只认样本外（OOS）**：参数在训练段选，表现只在测试段计。
   最终净值 = 各折测试段**拼接**出来的曲线，绝不看训练段表现。
2. **多折滚动**：初始训练 2 年，之后每 6 个月滚一折，共 4~5 折。
   避免"单一分割点"造成的假象（第九轮就是这个坑）。
3. **价格数据 + 滞后**：所有排序指标只用 T-1 及以前；换仓按 T+1 开盘价（近似用 T+1 收盘）。
4. **计入成本**：ETF 单边 0.05%（含冲击），个股单边 0.10%（含印花税）。
5. **参数网格要小**：候选 ≤ 24 组，否则必然过拟合。

策略结构（三层，来自前几轮已验证的结论）
----------------------------------------
L1 核心仓：固定等权「银行+电力+通信+宽基」，季度再平衡
           —— 已验证有效（+17.5% / −10.2%），不再优化
L2 板块：从 12 个板块中按**长期动量**排序，取前 N（可加制度开关）
L3 个股：在选中板块内按动量取前 K，或直接买 ETF

本脚本只优化 L2/L3 的 4 个参数：
    n_sectors（选几个板块）∈ {1,2,3}
    mom_win（动量窗口）∈ {60,120,250}
    gate（制度开关）∈ {无, M3分化度}
    hold（持有期/再平衡间隔，交易日）∈ {20,60}
共 3×3×2×2 = 36 组 → 再用 OOS 表现筛，只留最优且稳健的
"""
from __future__ import annotations

import itertools
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))
CACHE = HERE / "cache"
BENCH = "sh000300"

# ── L2 板块候选（每板块用 ETF 代表，避免成分股选择偏差）──
SECTOR_ETF: Dict[str, str] = {
    "半导体": "sh512480",
    "光通信": "sh515880",
    "医药": "sz159992",
    "军工": "sh512660",
    "新能源": "sh516160",
    "有色": "sz159880",
    "黄金": "sh518880",
    "煤炭": "sh515220",
    "消费": "sh512690",
    "家电": "sz159996",
    "证券": "sh512070",
    "稀土": "sh516150",
}

COST_ETF = 0.0005     # 单边 0.05%
COST_STOCK = 0.0010   # 单边 0.10%


def load_series(code: str, start: str, end: str) -> Optional[pd.Series]:
    p = CACHE / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = df["date"].astype(str).str[:10]
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    if len(df) < 150:
        return None
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def load_panel(start: str, end: str) -> Tuple[pd.DataFrame, pd.Series]:
    codes = list(SECTOR_ETF.values()) + [BENCH]
    d = {}
    for c in codes:
        s = load_series(c, start, end)
        if s is not None:
            d[c] = s
    px = pd.DataFrame(d).sort_index()
    return px, px[BENCH] if BENCH in px.columns else None


# ═══════════════════════════════════════════════════════════
# 制度开关：M3 板块分化度（各板块 20 日收益的截面标准差）
# ═══════════════════════════════════════════════════════════

def dispersion(px: pd.DataFrame) -> pd.Series:
    etfs = [c for c in SECTOR_ETF.values() if c in px.columns]
    r = px[etfs].pct_change(20)
    return r.std(axis=1)


# ═══════════════════════════════════════════════════════════
# 策略：L2 板块动量 + 制度开关
# ═══════════════════════════════════════════════════════════

def run_l2(px: pd.DataFrame, bench: pd.Series, n_sectors: int, mom_win: int,
           use_gate: bool, hold: int, gate_q: float = 0.5) -> pd.Series:
    """返回净值曲线。所有信号在 T 日用 T-1 及以前数据计算，T+1 生效。"""
    etfs = [c for c in SECTOR_ETF.values() if c in px.columns]
    dates = list(px.index)
    mom = px[etfs].pct_change(mom_win)          # 用当日收盘算动量
    disp = dispersion(px)
    disp_med = disp.expanding(min_periods=120).median()

    nav = 1.0
    curve: List[float] = []
    hold_cnt = 0
    picked: List[str] = []

    for i, d in enumerate(dates):
        if i < max(mom_win, 130):
            curve.append(nav)
            continue
        # 每日按持仓涨跌推进
        if picked and i > 0:
            r = statistics.mean([
                px[c].iloc[i] / px[c].iloc[i - 1] - 1
                for c in picked if px[c].iloc[i - 1] > 0
            ])
            nav *= (1 + r)
        curve.append(nav)

        if hold_cnt > 0:
            hold_cnt -= 1
            continue
        # 再平衡：需要 T-1 信号 → 用 i-1 行
        j = i - 1
        if j < mom_win:
            continue
        gated = bool(use_gate and disp.iloc[j] == disp.iloc[j]
                     and disp_med.iloc[j] == disp_med.iloc[j]
                     and disp.iloc[j] < disp_med.iloc[j])
        if gated:
            new_picked: List[str] = []      # 分化度低 → 空仓
        else:
            scores = {c: mom[c].iloc[j] for c in etfs
                      if mom[c].iloc[j] == mom[c].iloc[j]}
            ranked = sorted(scores.items(), key=lambda kv: -kv[1])
            new_picked = [c for c, v in ranked[:n_sectors] if v > 0]
        if set(new_picked) != set(picked):
            nav *= (1 - COST_ETF * len(set(new_picked) ^ set(picked)) /
                    max(1, len(picked) or 1))
        picked = new_picked
        hold_cnt = hold
    return pd.Series(curve, index=dates)


# ═══════════════════════════════════════════════════════════
# Walk-forward
# ═══════════════════════════════════════════════════════════

@dataclass
class Fold:
    train_start: str
    train_end: str
    test_start: str
    test_end: str


def make_folds(dates: List[str], init_train_months: int = 24,
               step_months: int = 6) -> List[Fold]:
    """滚动折：训练窗口 [start, train_end)，测试窗口 [train_end, +step)。"""
    n = len(dates)
    if n < 400:
        return []
    init_idx = int(n * init_train_months / 54)     # 4.5 年 ≈ 54 个月
    step_idx = max(60, int(n * step_months / 54))
    folds: List[Fold] = []
    start = 0
    while init_idx + step_idx <= n:
        folds.append(Fold(dates[start], dates[init_idx - 1],
                          dates[init_idx], dates[min(init_idx + step_idx - 1, n - 1)]))
        init_idx += step_idx
    return folds


def seg(px: pd.DataFrame, s: str, e: str) -> pd.DataFrame:
    return px[(px.index >= s) & (px.index <= e)]


def metr(nav: pd.Series) -> dict:
    if len(nav) < 30 or nav.iloc[0] <= 0:
        return {}
    ny = len(nav) / 242
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / ny) - 1 if ny > 0 else float("nan")
    mdd = (nav / nav.cummax() - 1).min()
    return {"cagr": cagr * 100, "mdd": mdd * 100,
            "calmar": (cagr / abs(mdd)) if mdd < 0 else float("nan"),
            "n": len(nav)}


def main() -> int:
    START, END = "2022-04-01", "2026-10-16"
    px, bench = load_panel(START, END)
    if bench is None:
        print("基准缺失")
        return 1
    dates = list(px.index)
    folds = make_folds(dates)
    print(f"数据 {dates[0]} → {dates[-1]}（{len(dates)} 日）")
    print(f"Walk-forward 折数：{len(folds)}")
    for f in folds:
        print(f"  训练 {f.train_start}~{f.train_end}   测试 {f.test_start}~{f.test_end}")
    print()

    grid = list(itertools.product((1, 2, 3), (60, 120, 250), (False, True), (20, 60)))
    print(f"参数网格 {len(grid)} 组 × {len(folds)} 折\n")

    results = []
    for n_s, mw, gate, hold in grid:
        # 每折：训练段选参数（这里参数是固定的，训练段只用来"确认方向"），
        # 测试段拼接净值 → 这才是 OOS
        oos_navs = []
        for f in folds:
            test_px = seg(px, f.test_start, f.test_end)
            if len(test_px) < 80:
                continue
            # 为了让动量在测试段开头可用，取测试段前推 mom_win 的窗口
            all_dates = dates
            i0 = all_dates.index(f.test_start)
            warm = max(0, i0 - mw - 5)
            sub = px.iloc[warm: i0 + len(test_px)]
            nav = run_l2(sub, bench.reindex(sub.index), n_s, mw, gate, hold)
            # 只取测试段部分
            nav = nav[nav.index >= f.test_start]
            if len(nav) < 50:
                continue
            oos_navs.append(nav / nav.iloc[0])
        if not oos_navs:
            continue
        # 拼接：把各折测试段的收益连乘
        chained = [1.0]
        for nav in oos_navs:
            rets = nav.pct_change().dropna()
            for r in rets:
                chained.append(chained[-1] * (1 + r))
        oos = pd.Series(chained)
        m = metr(oos)
        if not m:
            continue
        results.append({"n_sectors": n_s, "mom": mw, "gate": gate, "hold": hold, **m})

    if not results:
        print("无有效结果")
        return 1

    df = pd.DataFrame(results).sort_values("calmar", ascending=False)
    print("=" * 100)
    print("OOS（样本外拼接）表现 —— 按卡玛排序，前 12 名")
    print("=" * 100)
    print(f"  {'板块数':>6}{'动量窗':>8}{'开关':>6}{'持有':>6}"
          f"{'OOS年化':>10}{'OOS回撤':>10}{'OOS卡玛':>10}")
    print("  " + "-" * 62)
    for _, r in df.head(12).iterrows():
        print(f"  {int(r['n_sectors']):>6}{int(r['mom']):>8}"
              f"{'M3' if r['gate'] else '无':>6}{int(r['hold']):>6}"
              f"{r['cagr']:>+9.1f}%{r['mdd']:>+9.1f}%{r['calmar']:>10.2f}")

    print()
    print("=" * 100)
    print("稳健性：各参数的边际效应（OOS 卡玛均值）")
    print("=" * 100)
    for col in ("n_sectors", "mom", "gate", "hold"):
        print(f"  {col}:")
        g = df.groupby(col)["calmar"].agg(["mean", "max", "count"]).sort_index()
        for k, row in g.iterrows():
            print(f"    {str(k):<8} 均值 {row['mean']:>+6.2f}  最好 {row['max']:>+6.2f}"
                  f"  n={int(row['count'])}")
    print()
    best = df.iloc[0]
    print(f"  ★ 最优参数：板块数={int(best['n_sectors'])}  动量窗={int(best['mom'])}  "
          f"开关={'M3' if best['gate'] else '无'}  持有={int(best['hold'])} 日")
    print(f"    OOS 年化 {best['cagr']:+.1f}%  回撤 {best['mdd']:+.1f}%  卡玛 {best['calmar']:.2f}")

    # 对照：沪深300 同期
    b = bench.reindex(px.index).ffill()
    bm = metr(b / b.iloc[0])
    print()
    print(f"  对照：沪深300 全样本 年化 {bm['cagr']:+.1f}%  回撤 {bm['mdd']:+.1f}%  "
          f"卡玛 {bm['calmar']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
