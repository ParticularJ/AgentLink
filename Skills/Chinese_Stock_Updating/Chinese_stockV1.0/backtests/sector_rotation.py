#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路线 B：行业 ETF 趋势轮动 —— 能否在「回撤≤20%」下拿到 15%+ 年化？

⚠️ 结论（2026-10-16）：**失败，本脚本仅留作对照，不要引用其收益数字。**
   - 动量前 5/10/20 只：年化 +6.8%~+8.7%，但最大回撤 −23%~−38%（超出 20% 上限）
   - 失效原因：MA200 出场太慢，A 股主题 ETF 可在数周内回撤 30~40%
   - 本脚本的 SECTOR_ETFS 是**按 2026-10 行业分类手挑的 18 只**，
     存在明显幸存者偏差；不带事后挑选的版本见 final_tests.py 的 T2
     （扩到 57 只后动量轮动年化 +6.8%~+8.7%、回撤 −23%~−38%，同样失败）

逻辑（这是用户"板块门控"思路的正确版本，且避开了已被否决的量价个股选股）：
  1. 候选池 = 行业/主题 ETF（不选个股 → 规避 IC 为负的打分）
  2. 每月末按**动量**排序，只买排名靠前的 N 只
  3. 硬性趋势过滤：只保留收盘价 > 自身 MA200 的标的（"下行不交易"）
  4. 等权持有，月度再平衡；含真实交易成本

对照：沪深300 买入持有 / 分散配置（路线 A）/ 全行业 ETF 等权
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from allocation_engine import CACHE, apply_cost, metrics  # noqa: E402

# 行业/主题 ETF 候选池（全部来自缓存，覆盖 2024-02-07 起）
SECTOR_ETFS = [
    "sh512480",  # 半导体
    "sz159995",  # 芯片
    "sh515980",  # AI应用
    "sz159992",  # 创新药
    "sh515880",  # 通信/光模块
    "sh512660",  # 军工
    "sh562500",  # 人形机器人
    "sz159872",  # 智能驾驶
    "sz159779",  # 消费电子
    "sh516220",  # 化工
    "sz159611",  # 电力
    "sh516160",  # 新能源
    "sh518880",  # 黄金
    "sz159880",  # 有色金属
    "sz159886",  # 工程机械
    "sh512690",  # 白酒
    "sz159996",  # 家电
    "sh516150",  # 稀土
    "sh515220",  # 煤炭
    "sh512070",  # 券商非银
]


def load(px_codes, start, end):
    out = {}
    for c in px_codes:
        p = CACHE / f"{c}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < 260:
            continue
        out[c] = pd.Series(df["close"].astype(float).values, index=df["date"].values)
    return pd.DataFrame(out).dropna()


def momentum(s: pd.Series, i: int, lookback: int = 120) -> float:
    if i < lookback:
        return float("nan")
    return s.iloc[i] / s.iloc[i - lookback] - 1.0


def above_ma(s: pd.Series, i: int, win: int = 200) -> bool:
    if i < win:
        return False
    return s.iloc[i] > s.iloc[i - win:i + 1].mean()


def backtest_rotation(px: pd.DataFrame, top_n: int = 3, lookback: int = 120,
                      ma_win: int = 200, rebal: int = 20,
                      label: str = "", cash_when_empty: bool = True) -> "object":
    dates = px.index
    codes = list(px.columns)
    cash = 100_000.0
    units = {c: 0.0 for c in codes}
    curve = []
    cost = 0.0
    trades = 0
    hold_hist: List[List[str]] = []

    for i, d in enumerate(dates):
        val = sum(units[c] * px[c].iloc[i] for c in codes) + cash
        curve.append(val)
        if i < max(lookback, ma_win) + 30 or i % rebal != 0:
            continue
        # 选股：动量排序 + 趋势过滤
        cands = []
        for c in codes:
            if not above_ma(px[c], i, ma_win):
                continue
            m = momentum(px[c], i, lookback)
            if m == m:  # not nan
                cands.append((c, m))
        cands.sort(key=lambda x: -x[1])
        picked = [c for c, _ in cands[:top_n]]
        hold_hist.append(picked)
        w = {c: (1.0 / len(picked) if picked else 0.0) for c in codes}

        # ⚠️ 关键修正（2026-10-16）：必须「先算全部目标 → 先卖后买」。
        # 原实现按 codes 顺序边算目标边成交，先卖出的标的还没释放现金，
        # 后面的标的却已按「全组合价值」的目标买入 → 现金变负 → 实质加杠杆
        # （实测现金 -800,450，等于 8 倍杠杆，这才是 -92.6% 回撤的真正原因）。
        targets = {c: val * w.get(c, 0.0) for c in codes}
        cur_vals = {c: units[c] * px[c].iloc[i] for c in codes}
        # 第一轮：先卖（delta < 0）
        for c in codes:
            delta = targets[c] - cur_vals[c]
            if delta >= 0 or abs(delta) < val * 0.005:
                continue
            cc = apply_cost(delta)
            cost += cc
            trades += 1
            cash -= (delta + cc)
            units[c] += delta / px[c].iloc[i]
        # 第二轮：再买（delta > 0），且不得超出可用现金
        for c in codes:
            cur_v = units[c] * px[c].iloc[i]
            delta = targets[c] - cur_v
            if delta <= 0 or abs(delta) < val * 0.005:
                continue
            delta = min(delta, max(0.0, cash - apply_cost(delta)))   # 现金约束
            if delta < val * 0.005:
                continue
            cc = apply_cost(delta)
            cost += cc
            trades += 1
            cash -= (delta + cc)
            units[c] += delta / px[c].iloc[i]
    from allocation_engine import Result
    return Result(label=label, nav=pd.Series(curve, index=dates), trades=trades,
                  cost_paid=cost), hold_hist


def main() -> int:
    START, END = "2024-02-07", "2026-09-30"
    px = load(SECTOR_ETFS, START, END)
    print(f"行业 ETF 候选池：{px.shape[1]} 只，区间 {px.index[0]} → {px.index[-1]}"
          f"（{len(px)} 个交易日 / {len(px)/242:.2f} 年）\n")

    print("=" * 116)
    print("A. 趋势轮动：不同持仓数与再平衡频率（含成本）")
    print("=" * 116)
    print(f"  {'方案':<30}{'年化':>9}{'月化':>8}{'最大回撤':>10}{'月胜率':>9}"
          f"{'达标月≥1.2%':>13}{'最差月':>9}{'连亏月':>8}{'调仓':>7}{'成本':>8}")
    print("  " + "-" * 106)
    rows = []
    for top_n in (2, 3, 5):
        for rebal, tag in ((20, "月度"), (60, "季度")):
            r, _ = backtest_rotation(px, top_n, 120, 200, rebal,
                                     f"动量前{top_n}只·MA200过滤·{tag}")
            m = metrics(r)
            rows.append((r.label, m, r.cost_paid))
            print(f"  {r.label:<30}{m['cagr']:>+8.1f}%{m['月化']:>+7.2f}%{m['mdd']:>+9.1f}%"
                  f"{m['月胜率']:>8.1f}%{m['达标月(≥1.2%)']:>12.1f}%{m['最差月']:>+8.1f}%"
                  f"{m['连亏月']:>8}{m['调仓次数']:>7}{r.cost_paid:>8,.0f}")

    print()
    print("=" * 116)
    print("B. 对照：买入持有 / 等权")
    print("=" * 116)
    print(f"  {'方案':<30}{'年化':>9}{'月化':>8}{'最大回撤':>10}{'月胜率':>9}"
          f"{'达标月':>9}{'最差月':>9}{'连亏月':>8}")
    print("  " + "-" * 96)
    from allocation_engine import Result
    # 沪深300
    hs = px["sh512070"] if "sh512070" in px else None
    hs_p = CACHE / "sh510300.csv"
    if hs_p.exists():
        df = pd.read_csv(hs_p); df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= START) & (df["date"] <= END)]
        s = pd.Series(df["close"].astype(float).values, index=df["date"].values)
        m = metrics(Result(label="沪深300ETF 买入持有", nav=s / s.iloc[0] * 100000))
        print(f"  {'沪深300ETF 买入持有':<30}{m['cagr']:>+8.1f}%{m['月化']:>+7.2f}%"
              f"{m['mdd']:>+9.1f}%{m['月胜率']:>8.1f}%{m['达标月(≥1.2%)']:>8.1f}%"
              f"{m['最差月']:>+8.1f}%{m['连亏月']:>8}")
    # 行业 ETF 等权
    norm = px / px.iloc[0]
    eq = norm.mean(axis=1) * 100000
    m = metrics(Result(label="行业ETF等权持有", nav=eq))
    print(f"  {'行业ETF等权持有（20只）':<30}{m['cagr']:>+8.1f}%{m['月化']:>+7.2f}%"
          f"{m['mdd']:>+9.1f}%{m['月胜率']:>8.1f}%{m['达标月(≥1.2%)']:>8.1f}%"
          f"{m['最差月']:>+8.1f}%{m['连亏月']:>8}")
    # 单只最强（黄金）作参照
    if "sh518880" in px.columns:
        s = px["sh518880"]
        m = metrics(Result(label="黄金ETF 买入持有", nav=s / s.iloc[0] * 100000))
        print(f"  {'黄金ETF 买入持有':<30}{m['cagr']:>+8.1f}%{m['月化']:>+7.2f}%"
              f"{m['mdd']:>+9.1f}%{m['月胜率']:>8.1f}%{m['达标月(≥1.2%)']:>8.1f}%"
              f"{m['最差月']:>+8.1f}%{m['连亏月']:>8}")

    print()
    print("=" * 116)
    print("C. 判定")
    print("=" * 116)
    ok = [(lbl, m) for lbl, m, _ in rows if m["mdd"] > -20]
    if ok:
        best = max(ok, key=lambda x: x[1]["cagr"])
        print(f"  回撤≤20% 的方案中年化最高：{best[0]}  → 年化 {best[1]['cagr']:+.1f}%"
              f"（月化 {best[1]['月化']:+.2f}%），最大回撤 {best[1]['mdd']:+.1f}%")
    else:
        print("  ❌ 所有轮动方案的月度再平衡版本都突破了 -20% 回撤")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
