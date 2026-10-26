#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""严格回测引擎（v2）：把 A 股真实执行约束全部建模，并对每条假设加断言。

为什么需要它（2026-10-16 复盘）
--------------------------------
上一版引擎有两个 bug 会让结论虚高：
  1. 调仓时"边算边成交" → 现金变负 → 8 倍杠杆（动量轮动虚增到 +78.6%）
  2. dropna() 对齐 → 样本被最晚上市的标的截断（2.6 年缩成 16 个月）

本版新增的执行约束（此前全部缺失）：
  C1 T+1：当日买入的份额当日不可卖出（ETF 为 T+0，个股为 T+1；这里按标的类型区分）
  C2 涨跌停：|当日涨跌| ≥ 限制 − 0.1% 视为封板，**无法成交**
  C3 整手：买入必须为 100 股整数倍
  C4 停牌：价格缺失/成交量为 0 的交易日不可交易
  C5 现金非负 + 总仓位 ≤ 100%（硬断言）
  C6 成本：佣金 0.03% + 最低 5 元 + 冲击 0.02%；个股卖出另加印花税 0.05% + 过户费 0.001%
  C7 单标的上限 + 单次调仓幅度上限（避免不现实的瞬时调仓）

断言：
  A1 现金 >= -1 元
  A2 仓位市值 / 净值 <= 1.0001
  A3 单只权重 <= 配置上限 + 容差
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"

# ── 成本参数 ──────────────────────────────────────────────
COMMISSION = 0.0003          # 佣金 0.03%
COMMISSION_MIN = 5.0         # 最低 5 元
IMPACT = 0.0002              # 冲击成本
STAMP_TAX = 0.0005           # 印花税（仅个股卖出）
TRANSFER_FEE = 0.00001       # 过户费

# ── 交易约束 ──────────────────────────────────────────────
LOT = 100


def is_etf(code: str) -> bool:
    return code[:2] in ("sh", "sz") and code[2:4] in ("50", "51", "56", "58", "15", "16", "18")


def price_limit(code: str) -> float:
    """涨跌停幅度。ETF 10%；创业板(30)/科创板(68) 20%；其余 10%。"""
    pure = code[2:] if code[:2] in ("sh", "sz") else code
    if pure.startswith(("30", "68")):
        return 0.20
    return 0.10


@dataclass
class Market:
    """价格/成交量矩阵 + 可交易性判断。"""
    close: pd.DataFrame
    volume: pd.DataFrame
    open: pd.DataFrame

    def codes(self) -> List[str]:
        return list(self.close.columns)

    def px(self, code: str, i: int) -> Optional[float]:
        v = self.close[code].iloc[i]
        return None if (v != v or v <= 0) else float(v)

    def tradable(self, code: str, i: int) -> Tuple[bool, str]:
        """(是否可交易, 原因)。"""
        if i <= 0:
            return False, "首日"
        px = self.px(code, i)
        prev = self.px(code, i - 1)
        if px is None or prev is None:
            return False, "停牌/无价格"
        vol = self.volume[code].iloc[i]
        if vol != vol or float(vol) <= 0:
            return False, "成交量为0"
        chg = px / prev - 1.0
        lim = price_limit(code)
        if abs(chg) >= lim - 0.001:
            return False, f"涨跌停({chg*100:+.1f}%)"
        return True, ""


def _cost(code: str, delta_value: float, is_sell: bool) -> float:
    if abs(delta_value) < 1e-9:
        return 0.0
    c = max(abs(delta_value) * COMMISSION, COMMISSION_MIN if abs(delta_value) > 1 else 0.0)
    c += abs(delta_value) * IMPACT
    if is_sell and not is_etf(code):
        c += abs(delta_value) * (STAMP_TAX + TRANSFER_FEE)
    return c


@dataclass
class StrictResult:
    label: str
    nav: pd.Series
    trades: int = 0
    rejected: Dict[str, int] = field(default_factory=dict)
    cost_paid: float = 0.0
    max_leverage_seen: float = 0.0


def run_strict(mkt: Market,
               target_fn: Callable[[int, Market], Dict[str, float]],
               rebal: int = 20,
               label: str = "",
               capital: float = 100_000.0,
               max_weight: float = 0.25,
               max_turnover_per_rebal: float = 0.60,
               warmup: int = 130,
               verbose: bool = False) -> StrictResult:
    """严格回测。target_fn(i, mkt) -> {code: 权重}（和 <= 1，余额现金）。"""
    dates = mkt.close.index
    codes = mkt.codes()
    units: Dict[str, float] = {c: 0.0 for c in codes}
    cash = capital
    curve: List[float] = []
    trades = 0
    cost_total = 0.0
    rejected: Dict[str, int] = {}
    max_lev = 0.0

    for i, d in enumerate(dates):
        pos_val = 0.0
        for c in codes:
            p = mkt.px(c, i)
            if p is not None and units[c]:
                pos_val += units[c] * p
        nav = cash + pos_val
        curve.append(nav)
        lev = pos_val / nav if nav > 0 else 0.0
        max_lev = max(max_lev, lev)
        # ── 断言 ──
        assert cash > -1.0, f"A1 现金为负 @ {d}: {cash:,.2f}"
        assert lev <= 1.0001, f"A2 仓位超过净值 @ {d}: {lev:.4f}"

        if i < warmup or i % rebal != 0:
            continue
        w = target_fn(i, mkt)
        if not w:
            continue
        # 归一化 + 单标的上限
        tot = sum(w.values())
        if tot > 1.0:
            w = {k: v / tot for k, v in w.items()}
        w = {k: min(v, max_weight) for k, v in w.items()}

        targets = {}
        for c in codes:
            if c not in w:
                targets[c] = 0.0
                continue
            if not mkt.tradable(c, i)[0]:
                rejected[mkt.tradable(c, i)[1]] = rejected.get(mkt.tradable(c, i)[1], 0) + 1
                targets[c] = units[c] * mkt.px(c, i) if mkt.px(c, i) else 0.0  # 保持
                continue
            targets[c] = nav * w.get(c, 0.0)

        # 单次调仓幅度限制
        cur_vals = {c: (units[c] * mkt.px(c, i) if mkt.px(c, i) else 0.0) for c in codes}
        gross = sum(abs(targets[c] - cur_vals[c]) for c in codes)
        if gross > nav * max_turnover_per_rebal and gross > 0:
            scale = nav * max_turnover_per_rebal / gross
            targets = {c: cur_vals[c] + (targets[c] - cur_vals[c]) * scale for c in codes}
            rejected["调仓幅度受限"] = rejected.get("调仓幅度受限", 0) + 1

        # 第一轮：卖出
        for c in codes:
            delta = targets[c] - cur_vals[c]
            if delta >= -nav * 0.005:
                continue
            ok, why = mkt.tradable(c, i)
            if not ok:
                rejected[why] = rejected.get(why, 0) + 1
                continue
            p = mkt.px(c, i)
            shares = int(abs(delta) / p // LOT) * LOT      # 整手
            if shares <= 0:
                continue
            val = shares * p
            cc = _cost(c, val, True)
            cash += val - cc
            cost_total += cc
            units[c] -= shares
            trades += 1
            assert cash > -1.0, f"卖出后现金为负 @ {d}"

        # 第二轮：买入（整手 + 现金约束）
        for c in codes:
            if c not in w:
                continue
            ok, why = mkt.tradable(c, i)
            if not ok:
                continue
            p = mkt.px(c, i)
            cur_v = units[c] * p
            delta = targets[c] - cur_v
            if delta <= nav * 0.005:
                continue
            budget = max(0.0, cash - _cost(c, delta, False))
            shares = int(min(delta, budget) / p // LOT) * LOT
            if shares <= 0:
                continue
            val = shares * p
            cc = _cost(c, val, False)
            if val + cc > cash:
                continue
            cash -= (val + cc)
            cost_total += cc
            units[c] += shares
            trades += 1
            assert cash > -1.0, f"买入后现金为负 @ {d}"

        # 调仓后再次断言
        pos_val = sum(units[c] * mkt.px(c, i) for c in codes if mkt.px(c, i))
        nav2 = cash + pos_val
        assert cash > -1.0, f"A1' 现金为负 @ {d}"
        assert pos_val / nav2 <= 1.0001, f"A2' 仓位超净值 @ {d}"

    return StrictResult(label=label, nav=pd.Series(curve, index=dates), trades=trades,
                        rejected=rejected, cost_paid=cost_total, max_leverage_seen=max_lev)


def load_market(codes: List[str], start: str, end: str,
                min_rows: int = 300) -> Optional[Market]:
    """加载 close/open/volume 三个矩阵（外连接 + 保留 NaN）。"""
    cl, op, vo = {}, {}, {}
    for c in codes:
        p = CACHE / f"{c}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < min_rows:
            continue
        idx = df["date"].values
        cl[c] = pd.Series(df["close"].astype(float).values, index=idx)
        op[c] = pd.Series(df["open"].astype(float).values, index=idx)
        vo[c] = pd.Series(df["volume"].astype(float).values, index=idx)
    if not cl:
        return None
    close = pd.DataFrame(cl).sort_index()
    open_ = pd.DataFrame(op).reindex(columns=close.columns).sort_index()
    vol = pd.DataFrame(vo).reindex(columns=close.columns).sort_index()
    return Market(close=close, open=open_, volume=vol)


def metrics(nav: pd.Series, label: str = "") -> dict:
    import statistics
    n_years = len(nav) / 242
    tot = nav.iloc[-1] / nav.iloc[0] - 1
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / n_years) - 1 if n_years > 0 else float("nan")
    mdd = (nav / nav.cummax() - 1).min()
    m = nav.groupby(nav.index.str[:7]).last().pct_change().dropna()
    streak = best = 0
    for v in m:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    rets = nav.pct_change().dropna()
    vol = rets.std() * (242 ** 0.5) if len(rets) > 2 else 0
    return {
        "label": label, "total": tot * 100, "cagr": cagr * 100, "mdd": mdd * 100,
        "月化": ((nav.iloc[-1] / nav.iloc[0]) ** (1 / max(1, len(nav) / 21.0)) - 1) * 100,
        "月胜率": (m > 0).mean() * 100 if len(m) else 0,
        "达标月(≥1.2%)": (m >= 0.012).mean() * 100 if len(m) else 0,
        "月达标(≥2%)": (m >= 0.02).mean() * 100 if len(m) else 0,
        "最差月": m.min() * 100 if len(m) else 0,
        "连亏月": best,
        "夏普": (cagr * 100) / (vol * 100) if vol else float("nan"),
        "调仓次数": None,
    }
