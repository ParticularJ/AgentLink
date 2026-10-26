#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全周期压力测试：把候选方案放到 2022-03 ~ 2026-10（含 2022 下跌年）检验。

回应批评（2026-10-16）
----------------------
用户指出：**"回测的大问题是股票池必须非常全面，否则回测只是池内标的的收益；
下个月换池子，策略可能水土不服。"**

这个批评是对的，而且此前几轮的结论（+25.1%）正是它说的病症。
本脚本用两种办法把它降到最低：

  方法 1（构成中立）：候选池 = **缓存里所有能回溯到 2022 年上半年的 ETF**，
          不做任何行业/风格挑选 —— 池子的构成方式本身与"未来哪只涨"无关。
  方法 2（基准对照）：同时跑 4 个**宽基**（沪深300/中证500/中证1000/创业板），
          宽基的构成由指数公司规则决定，不存在选股偏差。

样本区间 2022-03 ~ 2026-10 覆盖：
  - 2022 年熊市（沪深300 全年 -21.6%）
  - 2023 年震荡下行
  - 2024 年 9 月前低迷 + 924 行情暴涨
  - 2025~2026 结构市
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from strict_engine import Market, load_market, metrics, run_strict  # noqa: E402

START, END = "2022-04-01", "2026-10-16"

# 构成中立池：缓存里所有 >=1000 根（可回溯 2022 上半年）的 ETF/LOF
NEUTRAL_POOL = [
    "sh512660", "sh515400", "sh515790", "sh516150", "sh516220", "sh516320",
    "sh516510", "sh516910", "sh562500", "sz159611", "sz159755", "sz159779",
    "sz159795", "sz159872", "sz159883", "sz159886", "sz159949", "sz159981",
    "sz159992", "sz159996", "sz161226",
]
# 宽基对照（构成由指数规则决定）
BROAD = ["sh510300", "sh510500", "sh512100", "sz159915"]   # 沪深300/中证500/中证1000/创业板
DIVIDEND = ["sh515180", "sh563020", "sh515300"]
GOLD = ["sh518880"]
BOND = ["sh511260", "sh511010"]


def ma_filtered(i: int, mkt: Market, codes: List[str], ma_win: int = 200,
                max_n: int = 0) -> Dict[str, float]:
    """只保留 close > MA200 的标的（等权）。max_n>0 时按动量取前 max_n。"""
    picked = []
    for c in codes:
        if c not in mkt.close.columns:
            continue
        s = mkt.close[c].iloc[:i + 1].dropna()
        if len(s) < ma_win + 5:
            continue
        if s.iloc[-1] > s.iloc[-ma_win:].mean():
            mom = s.iloc[-1] / s.iloc[-min(len(s) - 1, 120)] - 1
            picked.append((c, mom))
    if max_n:
        picked.sort(key=lambda x: -x[1])
        picked = picked[:max_n]
    return {c: 1.0 / len(picked) for c, _ in picked} if picked else {}


def equal(codes: List[str]):
    def _fn(i: int, mkt: Market) -> Dict[str, float]:
        cs = [c for c in codes if c in mkt.close.columns]
        return {c: 1.0 / len(cs) for c in cs} if cs else {}
    return _fn


def ma_equal(codes: List[str], ma_win: int = 200, max_n: int = 0):
    def _fn(i: int, mkt: Market) -> Dict[str, float]:
        return ma_filtered(i, mkt, codes, ma_win, max_n)
    return _fn


def buyhold(mkt: Market, code: str, label: str) -> dict:
    s = mkt.close[code].dropna()
    m = metrics(s / s.iloc[0], label)
    m.update({"调仓次数": 0, "被拒": 0, "成本": 0})
    return m


def run_one(mkt: Market, fn, rebal: int, label: str, max_weight=0.25) -> dict:
    r = run_strict(mkt, fn, rebal=rebal, label=label, max_weight=max_weight)
    m = metrics(r.nav, label)
    m["调仓次数"] = r.trades
    m["被拒"] = sum(r.rejected.values())
    m["成本"] = r.cost_paid
    m["最大仓位"] = r.max_leverage_seen * 100
    return m


def show(rows: List[dict], title: str):
    print(f"\n{title}")
    print(f"  {'方案':<34}{'年化':>9}{'最大回撤':>10}{'月胜率':>8}{'达标≥1.2%':>11}"
          f"{'最差月':>9}{'连亏':>6}{'调仓':>6}")
    print("  " + "-" * 96)
    for m in rows:
        print(f"  {m['label']:<34}{m['cagr']:>+8.1f}%{m['mdd']:>+9.1f}%{m['月胜率']:>7.1f}%"
              f"{m['达标月(≥1.2%)']:>10.1f}%{m['最差月']:>+8.1f}%{m['连亏月']:>6}"
              f"{m['调仓次数']:>6}")


def main() -> int:
    all_codes = sorted(set(NEUTRAL_POOL + BROAD + DIVIDEND + GOLD + BOND))
    mkt = load_market(all_codes, START, END, min_rows=200)
    if mkt is None:
        print("数据不足")
        return 1
    print(f"全周期 {mkt.close.index[0]} → {mkt.close.index[-1]}"
          f"（{len(mkt.close)} 个交易日 / {len(mkt.close)/242:.2f} 年）")
    print(f"构成中立池 {len(NEUTRAL_POOL)} 只 · 宽基 {len(BROAD)} 只 · 红利 {len(DIVIDEND)}"
          f" · 黄金 1 · 债券 {len(BOND)}")

    rows = []
    # ── 基准：宽基买入持有（最重要，因为它不可被挑选）──
    for c, n in (("sh510300", "沪深300ETF"), ("sh510500", "中证500ETF"),
                 ("sh512100", "中证1000ETF"), ("sz159915", "创业板ETF"),
                 ("sh511260", "十年国债ETF")):
        if c in mkt.close.columns:
            rows.append(buyhold(mkt, c, f"基准·{n} 买入持有"))
    print_rows = rows
    show(print_rows, "A. 基准（宽基/债券买入持有，构成由指数规则决定）")

    # ── 核心候选：中性池等权 / MA200 过滤 ──
    rows = []
    for rebal, tag in ((20, "月度"), (60, "季度")):
        rows.append(run_one(mkt, equal(NEUTRAL_POOL), rebal,
                            f"中性池等权（{tag}）"))
    rows.append(run_one(mkt, ma_equal(NEUTRAL_POOL, 200, 0), 20,
                        "中性池·MA200过滤·等权（月度）"))
    rows.append(run_one(mkt, ma_equal(NEUTRAL_POOL, 200, 5), 20,
                        "中性池·MA200+动量前5（月度）"))
    rows.append(run_one(mkt, ma_equal(NEUTRAL_POOL, 200, 10), 20,
                        "中性池·MA200+动量前10（月度）"))
    rows.append(run_one(mkt, equal(BROAD), 20, "宽基等权（月度）"))
    rows.append(run_one(mkt, ma_equal(BROAD, 200, 0), 20, "宽基·MA200过滤（月度）"))
    show(rows, "B. 构成中立池 / 宽基（不挑选标的）")

    # ── 静态配置（保守）──
    rows = []
    cons = DIVIDEND + BROAD[:2] + GOLD + BOND
    rows.append(run_one(mkt, equal(cons), 20, "红利+宽基+黄金+债 等权（月度）"))
    rows.append(run_one(mkt, equal(cons), 60, "红利+宽基+黄金+债 等权（季度）"))
    show(rows, "C. 保守配置")

    # ── 逐年分解（关键：看 2022 年）──
    print()
    print("=" * 96)
    print("D. 逐年分解（重点看 2022 下跌年）")
    print("=" * 96)
    combos = [("中性池等权", equal(NEUTRAL_POOL), 20),
              ("中性池·MA200过滤", ma_equal(NEUTRAL_POOL, 200, 0), 20),
              ("宽基等权", equal(BROAD), 20),
              ("宽基·MA200过滤", ma_equal(BROAD, 200, 0), 20),
              ("保守配置等权", equal(cons), 20)]
    years = ["2022", "2023", "2024", "2025", "2026"]
    print(f"  {'方案':<22}" + "".join(f"{y:>13}" for y in years))
    print("  " + "-" * 90)
    for name, fn, reb in combos:
        cells = []
        for y in years:
            seg = mkt.close.index.str.startswith(y)
            # 逐年重建 Market，保留该年**有数据**的标的（避免空转）
            sub = mkt.close.loc[seg]
            keep = [c for c in sub.columns if sub[c].notna().sum() >= 60]
            if len(sub) < 80 or not keep:
                cells.append(f"{'—':>13}")
                continue
            msub = Market(close=sub[keep], open=mkt.open.loc[seg, keep],
                          volume=mkt.volume.loc[seg, keep])
            r = run_strict(msub, fn, rebal=reb, warmup=20, max_weight=0.25)
            mm = metrics(r.nav)
            cells.append(f"{mm['total']:>+12.1f}%")
        print(f"  {name:<22}" + "".join(cells))
    # 宽基基准逐年
    for code, nm in (("sh510300", "沪深300"), ("sh510500", "中证500"),
                     ("sz159915", "创业板")):
        if code not in mkt.close.columns:
            continue
        cells = []
        for y in years:
            s = mkt.close[code]
            seg = s[s.index.str.startswith(y)].dropna()
            if len(seg) < 30:
                cells.append(f"{'—':>13}")
            else:
                cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+12.1f}%")
        print(f"  {nm:<22}" + "".join(cells))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
