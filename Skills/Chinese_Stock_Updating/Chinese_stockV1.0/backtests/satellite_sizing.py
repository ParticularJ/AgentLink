#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卫星仓仓位纪律实测：核心+卫星架构下，卫星仓占比多少才不会拖垮总账户？

背景（2026-10-16）
------------------
用户提出：**用一部分资金做基本盘（沪深300 + 再平衡），另一部分抓热点
（印刷板块、涨停连板、涨停回调、打新）。**

这个结构的理论依据（外部研报）：
  - 浙商证券《凯利公式视角下的A股长期复利实现路径》（2026-07）：
    分数凯利（半凯利）是风险收益权衡的有效工具，凯利策略**更适应于作为
    中长期权益仓位管理的策略** → 支持"核心仓按凯利/波动定仓位"。
  - 华安证券《涨停板背后的Alpha：首板回调策略》（2026-03）：
    样本外年化 20.72%、夏普 1.13、最大回撤 −8.99%、与沪深300 相关 0.14
    → 事件驱动卫星仓**确实存在**，但容量仅 500万~2000万。

本节要做的事：把"核心+卫星"的**仓位比例**从直觉变成可计算。
关键问题：卫星仓的负期望/高波动会不会把核心仓的优势吃掉？

方法：
  - 核心仓 = 沪深300ETF 买入持有（我们此前实测最稳的方案：年化 +10.8% / 回撤 −17.1%）
  - 卫星仓 = 三种假想卫星，分别代入不同期望值：
      S1 打新（正期望、低波动）     年化 +5%、波动 3%
      S2 涨停回调（正期望、中波动） 年化 +20%、波动 25%
      S3 追热点（负期望、高波动）   年化 −5%、波动 35%
  - 用历史日线驱动核心仓，卫星仓用蒙特卡洛/参数化收益序列
  - 扫描卫星占比 0% → 50%，看组合的年化/回撤/连亏月
"""
from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path
from typing import List

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from strict_engine import CACHE  # noqa: E402


def load_close(code: str, start: str, end: str):
    p = CACHE / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = df["date"].astype(str).str[:10]
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    if len(df) < 200:
        return None
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def sat_series(core_idx, cagr: float, vol: float, seed: int = 42,
               iterations: int = 40) -> pd.Series:
    """生成一条与核心仓同长度的卫星仓日收益序列。

    ⚠️ 2026-10-16 修正：初版把日收益硬截断在 ±10%，而高波动参数下这会引入
    **正向偏差**——实测「年化 −5%、波动 35%」被模拟成 **+3.9%**（截断落点
    落在分布中心附近，等效于抬高了均值）。修正做法：**对随机项做中心化**
    （r = mu + (draw − mean(draw))），使实际均值严格等于目标 mu；
    再对极少数越界值按边界截断（数量极少，不再影响均值）。
    """
    rnd = random.Random(seed)
    n = len(core_idx)
    mu_d = (1 + cagr) ** (1 / 242) - 1
    sd_d = vol / (242 ** 0.5)

    # 多次采样取一条"实现均值最接近目标"的路径（消除单次抽样的运气）
    best_path, best_err = None, None
    for it in range(iterations):
        draws = [rnd.gauss(0.0, sd_d) for _ in range(n)]
        m = statistics.mean(draws)
        centered = [mu_d + (x - m) for x in draws]      # 中心化：均值 = mu_d
        clipped = [max(-0.10, min(0.10, x)) for x in centered]
        err = abs(statistics.mean(clipped) - mu_d)
        if best_err is None or err < best_err:
            best_err, best_path = err, clipped

    vals, nav = [], 1.0
    for r in best_path:
        nav *= (1 + r)
        vals.append(nav)
    return pd.Series(vals, index=core_idx)


def metrics(nav: pd.Series, label: str) -> dict:
    n_years = len(nav) / 242
    tot = nav.iloc[-1] / nav.iloc[0] - 1
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / n_years) - 1
    mdd = (nav / nav.cummax() - 1).min()
    m = nav.groupby(nav.index.str[:7]).last().pct_change().dropna()
    streak = best = 0
    for v in m:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    return {"label": label, "cagr": cagr * 100, "mdd": mdd * 100,
            "月胜率": (m > 0).mean() * 100, "最差月": m.min() * 100, "连亏月": best}


def main() -> int:
    START, END = "2024-02-26", "2026-10-16"
    core = load_close("sh510300", START, END)
    if core is None:
        print("核心仓数据缺失")
        return 1
    core_nav = core / core.iloc[0]
    print(f"核心仓（沪深300ETF 买入持有）：{core.index[0]} → {core.index[-1]}"
          f"（{len(core)} 日 / {len(core)/242:.2f} 年）")
    base = metrics(core_nav, "核心仓 100%")
    print(f"  年化 {base['cagr']:+.1f}%   最大回撤 {base['mdd']:+.1f}%   "
          f"最长连亏 {base['连亏月']} 个月\n")

    satellites = {
        "S1 打新（年化+5%/波动3%）":        (0.05, 0.03),
        "S2 涨停回调（年化+20%/波动25%）":  (0.20, 0.25),
        "S3 追热点（年化−5%/波动35%）":     (-0.05, 0.35),
    }

    for name, (cagr, vol) in satellites.items():
        print("=" * 96)
        print(f"{name}")
        print("=" * 96)
        sat = sat_series(core.index, cagr, vol)
        sat_nav = sat / sat.iloc[0]
        sm = metrics(sat_nav, "卫星仓单独")
        print(f"  卫星仓单独：年化 {sm['cagr']:+.1f}%  回撤 {sm['mdd']:+.1f}%  "
              f"最长连亏 {sm['连亏月']} 个月")
        print()
        print(f"  {'卫星占比':>8}{'组合年化':>10}{'组合回撤':>10}{'月胜率':>9}"
              f"{'最差月':>9}{'连亏月':>8}{'vs 纯核心':>12}")
        print("  " + "-" * 76)
        for w in (0.0, 0.10, 0.20, 0.30, 0.40, 0.50):
            combo = core_nav * (1 - w) + sat_nav * w
            m = metrics(combo, f"卫星{w:.0%}")
            delta = m["cagr"] - base["cagr"]
            flag = "✅" if delta >= 0 and m["mdd"] >= -20 else ("⚠️" if m["mdd"] >= -20 else "❌")
            print(f"  {w:>7.0%}{m['cagr']:>+9.1f}%{m['mdd']:>+9.1f}%{m['月胜率']:>8.1f}%"
                  f"{m['最差月']:>+8.1f}%{m['连亏月']:>8}{delta:>+11.1f}pp  {flag}")
        print()

    print("=" * 96)
    print("结论（按实测结果修正，勿照抄直觉）")
    print("=" * 96)
    print("  1) 卫星仓是否提升『收益』，取决于它的期望值是否超过核心仓（本核心仓 +10.8%）：")
    print("     - 打新（+5%）< 核心仓 → 提高占比会**降低**组合年化，但显著**降低回撤**")
    print("       （50% 占比：回撤 −17.1% → −8.8%）→ 它是『降波动工具』，不是『增益工具』")
    print("     - 涨停回调（+20%）> 核心仓 → 占比越大，年化越高、回撤基本不变")
    print("       （50% 占比：年化 +13.9%，回撤 −19.2%，仍在 20% 以内）")
    print("     - 负期望（追热点）→ 任何占比都在拖累，30% 起回撤突破 20%")
    print("  2) 仓位纪律的本质：**先确认期望值为正、再谈放多少**。")
    print("     对负期望的卫星，正确仓位是 0，不是『小仓位试试』——")
    print("     因为只要参与，期望值就是负的，且它会占用本可用于核心仓的资金。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
