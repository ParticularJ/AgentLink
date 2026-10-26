#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置型框架回测引擎（今天的讨论落地）。

设计依据（来自 2026-10-15/16 的实测结论）
----------------------------------------
被数据否决、因此**不再使用**的：
  - 量价选股打分（IC 为负）→ 3 个策略 analyzer
  - 板块二元覆盖（15 个板块被压成 STRONG_UP/STRONG_DOWN）
  - 月度切换股票池（= 高换手 = 负和摩擦）
  - 防守通道（防守板块超额为负）
已被证明有效的、因此**保留并强化**的：
  - 不在过热位置建仓（入场质量分的思想）
  - 不在下行趋势里逆势交易（大盘开关的思想）→ 改为「估值分位 + 回撤」定仓位

新框架四条规则
--------------
  R1 核心配置：红利/宽基/黄金/债券，长期持有，收益来自 ROE+股息（正和）
  R2 估值倾斜：按 3 年分位 + 回撤 调整各资产权重（便宜多配、贵了少配）
  R3 定期再平衡：季度（对比月度/年度），把风险敞口拉回目标
  R4 现金缓冲：保留底仓现金，兼顾「1-2 个月回本」的诉求与极端机会

成本假设（此前所有回测都漏了，这里补上）
  - ETF：佣金 0.03%，最低 5 元（按 10 万本金折算为 0.005% 保底）
  - 个股：佣金 0.025% + 印花税 0.05%（卖出）+ 过户费 0.001%
  - 本框架只交易 ETF，故按 ETF 口径；另加 0.02% 冲击成本
"""
from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"

# ── 资产池 ────────────────────────────────────────────────
BUCKETS: Dict[str, Dict[str, float]] = {
    "equity_dividend": {"sh515180": 0.5, "sh563020": 0.3, "sh515300": 0.2},
    "equity_broad":    {"sh510300": 1.0},
    "gold":            {"sh518880": 1.0},
    "bond":            {"sh511260": 0.6, "sh511010": 0.4},
}

# 静态基准权重（长期中枢）
STATIC_TARGET = {
    "equity_dividend": 0.30,
    "equity_broad":    0.20,
    "gold":            0.15,
    "bond":            0.25,
    "cash":            0.10,
}

# 成本
COST_RATE = 0.0003      # 佣金 0.03%
COST_MIN = 5.0          # 最低 5 元
IMPACT = 0.0002         # 冲击成本 0.02%
CAPITAL = 100_000.0


# ═══════════════════════════════════════════════════════════
# 数据
# ═══════════════════════════════════════════════════════════

def load_prices(codes: List[str], start: str, end: str) -> Optional[pd.DataFrame]:
    out = {}
    for c in codes:
        p = CACHE / f"{c}.csv"
        if not p.exists():
            return None
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < 60:
            return None
        out[c] = pd.Series(df["close"].astype(float).values, index=df["date"].values)
    px = pd.DataFrame(out).dropna()
    return px if len(px) > 60 else None


def bucket_nav(px: pd.DataFrame, bucket: str) -> pd.Series:
    """把一个 bucket 内的多只 ETF 等权/按比例合成为一条净值。"""
    w = BUCKETS[bucket]
    total = sum(w.values())
    parts = []
    for code, wt in w.items():
        if code in px.columns:
            s = px[code]
            parts.append((s / s.iloc[0]) * (wt / total))
    if not parts:
        return None
    out = parts[0]
    for p in parts[1:]:
        out = out + p
    return out


# ═══════════════════════════════════════════════════════════
# 估值/位置指标（只用历史数据，无未来函数）
# ═══════════════════════════════════════════════════════════

def position_score(s: pd.Series, i: int, lookback: int = 750) -> float:
    """0~1，越大越"便宜"（越值得配置）。

    三个成分各占 1/3：
      1. 价格在 lookback 窗口中的分位（越低越好）
      2. 距窗口高点的回撤（越深越好）
      3. 相对自身均线的偏离（越低越好）
    """
    lo = max(0, i - lookback)
    win = s.iloc[lo:i + 1]
    if len(win) < 120:
        return 0.5
    cur = s.iloc[i]
    hi, low = win.max(), win.min()
    rng = hi - low
    pct = (cur - low) / rng if rng > 0 else 0.5      # 0=最低 1=最高
    dd = cur / hi - 1.0                               # <=0
    ma = win.mean()
    dev = cur / ma - 1.0
    # 归一化到 0~1，越大越便宜
    score = (1 - pct) * 0.4 + min(1.0, abs(dd) / 0.30) * 0.35 + min(1.0, max(0.0, -dev) / 0.20) * 0.25
    return max(0.0, min(1.0, score))


# ═══════════════════════════════════════════════════════════
# 回测
# ═══════════════════════════════════════════════════════════

@dataclass
class Result:
    label: str
    nav: pd.Series
    monthly: pd.Series = field(default=None)
    metrics: dict = field(default_factory=dict)
    trades: int = 0
    cost_paid: float = 0.0


def apply_cost(delta_value: float) -> float:
    """按成交金额算成本。"""
    if abs(delta_value) < 1e-9:
        return 0.0
    return max(abs(delta_value) * COST_RATE, COST_MIN if abs(delta_value) > 1 else 0.0) \
        + abs(delta_value) * IMPACT


def assert_no_leverage(cash: float, positions_value: float, where: str = "") -> None:
    """防杠杆断言（2026-10-16 新增）。

    背景：本引擎第一版用「按顺序边算目标边成交」，先卖出的仓位还没释放现金，
    后面的仓位却已按全组合价值下单 → 现金变负（实测 -800,450，8 倍杠杆），
    使动量轮动虚增到 +78.6% 年化 / -92.6% 回撤。

    任何回测引擎都该有这条检查：**现金不得为负、总仓位不得超过净值**。
    """
    if cash < -1.0:
        raise AssertionError(
            f"现金余额为负 ({cash:,.2f})，说明调仓逻辑在透支——{where}")
    if positions_value > (cash + positions_value) * 1.0001:
        raise AssertionError(
            f"总仓位 ({positions_value:,.2f}) 超过净值——{where}")


def backtest(px: pd.DataFrame, target_fn, rebal_days: int = 60,
             label: str = "", start_cash: float = CAPITAL) -> Result:
    """通用回测：target_fn(i, bucket_navs, current_weights) -> {bucket: weight}。

    每日按各 bucket 净值涨跌推动组合，每 rebal_days 个交易日再平衡到目标权重。
    """
    navs = {b: bucket_nav(px, b) for b in BUCKETS}
    navs = {b: v for b, v in navs.items() if v is not None}
    dates = px.index
    capital = start_cash
    units = {b: 0.0 for b in navs}
    cash = capital
    curve = []
    total_cost = 0.0
    trades = 0

    for i, d in enumerate(dates):
        # 估值
        val = sum(units[b] * navs[b].iloc[i] for b in navs) + cash
        curve.append(val)
        if i == 0 or i % rebal_days != 0 or i < 130:
            continue
        w = target_fn(i, navs, {b: (units[b] * navs[b].iloc[i]) / val for b in navs})
        if not w:
            continue
        # ⚠️ 关键修正（2026-10-16）：先算全部目标 → 先卖后买，且买入受现金约束。
        # 原实现按顺序边算边成交，先卖出的仓位还没释放现金，后面的仓位却已按
        # 全组合价值下目标单 → 现金变负（实测 -800,450，等于 8 倍杠杆）。
        targets = {b: val * w.get(b, 0.0) for b in navs}
        cur_vals = {b: units[b] * navs[b].iloc[i] for b in navs}
        for b in navs:                                  # 第一轮：卖出
            delta = targets[b] - cur_vals[b]
            if delta >= 0 or abs(delta) < val * 0.005:
                continue
            c = apply_cost(delta)
            total_cost += c
            trades += 1
            cash -= (delta + c)
            units[b] += delta / navs[b].iloc[i]
        for b in navs:                                  # 第二轮：买入（受现金约束）
            cur_v = units[b] * navs[b].iloc[i]
            delta = targets[b] - cur_v
            if delta <= 0 or abs(delta) < val * 0.005:
                continue
            delta = min(delta, max(0.0, cash - apply_cost(delta)))
            if delta < val * 0.005:
                continue
            c = apply_cost(delta)
            total_cost += c
            trades += 1
            cash -= (delta + c)
            units[b] += delta / navs[b].iloc[i]
        # 防杠杆断言：每次调仓后校验
        _pos = sum(units[b] * navs[b].iloc[i] for b in navs)
        assert_no_leverage(cash, _pos, f"allocation_engine @ {d}")

    nav = pd.Series(curve, index=dates)
    return Result(label=label, nav=nav, trades=trades, cost_paid=total_cost)


def metrics(res: Result, bench: Optional[pd.Series] = None) -> dict:
    nav = res.nav
    n_years = len(nav) / 242
    tot = nav.iloc[-1] / nav.iloc[0] - 1
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / n_years) - 1
    mdd = (nav / nav.cummax() - 1).min()
    m = nav.groupby(nav.index.str[:7]).last().pct_change().dropna()
    # 连亏月
    streak = best = 0
    for v in m:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    # 回撤恢复时间（最长）
    dd = nav / nav.cummax() - 1
    worst_recovery = 0
    peak_i = 0
    in_dd = False
    for i, v in enumerate(dd.values):
        if v < -0.001 and not in_dd:
            in_dd, peak_i = True, i
        elif v >= -0.001 and in_dd:
            worst_recovery = max(worst_recovery, i - peak_i)
            in_dd = False
    return {
        "label": res.label,
        "total": tot * 100,
        "cagr": cagr * 100,
        "mdd": mdd * 100,
        "月度均值": m.mean() * 100,
        "月胜率": (m > 0).mean() * 100,
        "达标月(≥1.2%)": (m >= 0.012).mean() * 100,
        "最差月": m.min() * 100,
        "连亏月": best,
        "最长回撤(交易日)": worst_recovery,
        "调仓次数": res.trades,
        "累计成本": res.cost_paid,
        "月化": ((nav.iloc[-1] / nav.iloc[0]) ** (1 / (len(nav) / 21.0)) - 1) * 100,
    }


# ═══════════════════════════════════════════════════════════
# 目标权重函数
# ═══════════════════════════════════════════════════════════

def w_static(i, navs, cur) -> Dict[str, float]:
    return dict(STATIC_TARGET)


def make_w_tilt(bond_floor: float = 0.25, risk_cap: float = 0.80,
                tilt_strength: float = 0.6):
    """估值倾斜版：把风险资产预算按 position_score 分配，债券托底。"""
    def _fn(i, navs, cur) -> Dict[str, float]:
        risky = [b for b in ("equity_dividend", "equity_broad", "gold") if b in navs]
        scores = {b: position_score(navs[b], i) for b in risky}
        # 风险预算 = 1 - 债券底仓 - 现金；用分数做倾斜，但保留基准权重作为锚
        base = {b: STATIC_TARGET.get(b, 0.0) for b in risky}
        base_tot = sum(base.values()) or 1.0
        raw = {b: base[b] * (1.0 + tilt_strength * (scores[b] - 0.5) * 2.0) for b in risky}
        raw_tot = sum(raw.values()) or 1.0
        budget = min(risk_cap, 1.0 - bond_floor - 0.05)
        w = {b: raw[b] / raw_tot * budget for b in risky}
        w["bond"] = bond_floor
        return w
    return _fn


def make_w_defensive(i, navs, cur) -> Dict[str, float]:
    """防守优先：整体位置偏贵时降风险敞口（强化"不在下行/过热时交易"）。"""
    risky = [b for b in ("equity_dividend", "equity_broad", "gold") if b in navs]
    scores = [position_score(navs[b], i) for b in risky]
    avg = statistics.mean(scores) if scores else 0.5
    # 平均分位越低（越贵）→ 越降敞口
    budget = 0.30 + 0.45 * min(1.0, max(0.0, (avg - 0.25) / 0.5))   # 0.30 ~ 0.75
    base = {b: STATIC_TARGET.get(b, 0.0) for b in risky}
    base_tot = sum(base.values()) or 1.0
    w = {}
    for b in risky:
        s = position_score(navs[b], i)
        w[b] = base[b] / base_tot * budget * (1.0 + 0.5 * (s - 0.5) * 2.0)
    tot = sum(w.values()) or 1.0
    w = {b: v / tot * budget for b, v in w.items()}
    w["bond"] = min(0.40, 1.0 - budget)
    return w


if __name__ == "__main__":
    START, END = "2024-02-07", "2026-09-30"
    codes = sorted({c for b in BUCKETS.values() for c in b})
    px = load_prices(codes, START, END)
    if px is None:
        print("数据不足")
        raise SystemExit(1)
    print(f"区间 {px.index[0]} → {px.index[-1]}，{len(px)} 个交易日\n")

    results = [
        backtest(px, w_static, 60, "静态配置（季度再平衡）"),
        backtest(px, w_static, 20, "静态配置（月度再平衡）"),
        backtest(px, make_w_tilt(), 60, "估值倾斜（季度）"),
        backtest(px, make_w_tilt(), 20, "估值倾斜（月度）"),
        backtest(px, make_w_defensive, 60, "估值倾斜+防守敞口（季度）"),
    ]
    rows = [metrics(r) for r in results]
    print("=" * 120)
    print("表 1：配置型框架回测结果（含真实交易成本）")
    print("=" * 120)
    hdr = (f"{'方案':<26}{'累计':>9}{'年化':>8}{'月化':>7}{'最大回撤':>10}"
           f"{'月胜率':>8}{'达标月':>8}{'最差月':>8}{'连亏月':>7}{'调仓':>6}{'成本':>9}")
    print(hdr)
    print("-" * 120)
    for r in rows:
        print(f"{r['label']:<26}{r['total']:>+8.1f}%{r['cagr']:>+7.1f}%{r['月化']:>+6.2f}%"
              f"{r['mdd']:>+9.1f}%{r['月胜率']:>7.1f}%{r['达标月(≥1.2%)']:>7.1f}%"
              f"{r['最差月']:>+7.1f}%{r['连亏月']:>7}{r['调仓次数']:>6}{r['累计成本']:>9,.0f}")
