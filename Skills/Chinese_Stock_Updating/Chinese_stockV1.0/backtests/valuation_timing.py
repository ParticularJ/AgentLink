#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""估值分位择时测试（2026-10-17）

问题：价值投资的「低估值买、高估值卖」择时，能否跑赢「一直持有」？

方法（用上证红利指数，2005-2026 共 21 年，代表性足够）：
  · 滚动 5 年 PE 分位：当前 PE 在过去 5 年的百分位
  · 策略 A（一直持有）：买入持有，基准
  · 策略 B（估值择时）：PE 分位 < X 时持有，否则持现金（0 收益）
  · 比较不同 X 阈值下的年化收益与回撤

⚠️ 口径：上证红利是价格指数（不含分红再投），但 A/B 对比用的是同一价格序列，
   分红差异在两者相减时抵消，不影响「择时是否有效」的结论。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load_pe(name: str) -> pd.Series:
    df = pd.read_csv(f"backtests/cache_long/pe_{name}.csv")
    df["日期"] = df["日期"].astype(str).str[:10]
    s = pd.Series(df["滚动市盈率"].astype(float).values, index=pd.to_datetime(df["日期"]))
    return s.sort_index()


def load_price(code: str) -> pd.Series:
    df = pd.read_csv(f"backtests/cache_long/{code}.csv")
    df["date"] = df["date"].astype(str).str[:10]
    s = pd.Series(df["close"].astype(float).values, index=pd.to_datetime(df["date"]))
    return s.sort_index()


def metr(nav: pd.Series) -> dict:
    ny = len(nav) / 12          # 月度数据，12 个月/年
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / ny) - 1
    mdd = (nav / nav.cummax() - 1).min()
    return {"cagr": cagr * 100, "mdd": mdd * 100,
            "total": (nav.iloc[-1] / nav.iloc[0] - 1) * 100,
            "calmar": (cagr / abs(mdd)) if mdd < 0 else float("nan")}


def main() -> int:
    pe = load_pe("上证红利")
    px = load_price("sh000015")

    # 对齐到共同日期（按月）
    pe_m = pe.resample("MS").last().dropna()
    px_m = px.resample("MS").last().dropna()
    j = pd.DataFrame({"pe": pe_m, "px": px_m}).dropna()
    print(f"样本 {j.index[0].date()} ~ {j.index[-1].date()}（{len(j)} 个月）")
    print(f"当前 PE = {j['pe'].iloc[-1]:.2f}")

    # 滚动 5 年 PE 分位（估值分位 = 历史 PE ≤ 当前 PE 的比例，越高越贵）
    j["pe_pct"] = j["pe"].rolling(60, min_periods=36).apply(
        lambda w: (w <= w.iloc[-1]).mean(), raw=False)

    # 基准：一直持有（从第一天起，不受 PE 分位影响）
    base = j["px"] / j["px"].iloc[0]

    print()
    print("=" * 88)
    print("估值分位择时 vs 一直持有（上证红利，2005-2026）")
    print("=" * 88)
    print(f"  {'PE分位阈值':>10}{'年化':>9}{'累计':>9}{'回撤':>9}{'卡玛':>8}{'持有时长':>9}")
    print("  " + "-" * 60)
    rows = []
    for thresh in (1.01, 0.80, 0.60, 0.50, 0.40, 0.20):
        # PE 分位 < thresh 时持有，否则现金；预热期(NaN)填 -1 → 默认持有
        hold = j["pe_pct"].fillna(-1.0) < thresh
        nav = 1.0
        curve = [1.0]
        for i in range(1, len(j)):
            if hold.iloc[i - 1]:
                nav *= j["px"].iloc[i] / j["px"].iloc[i - 1]
            curve.append(nav)
        nav_s = pd.Series(curve, index=j.index)
        m = metr(nav_s)
        rows.append((thresh, m, hold.mean()))
        label = "100%(一直持有)" if thresh > 1 else f"< {thresh*100:.0f}%"
        print(f"  {label:>10}{m['cagr']:>+7.2f}%{m['total']:>+8.1f}%{m['mdd']:>+8.1f}%"
              f"{m['calmar']:>8.2f}{hold.mean()*100:>8.1f}%")

    bm = metr(base)
    print(f"  {'纯买入持有':>10}{bm['cagr']:>+7.2f}%{bm['total']:>+8.1f}%{bm['mdd']:>+8.1f}%"
          f"{bm['calmar']:>8.2f}{'100.0%':>9}")

    print()
    print("  判读：若『一直持有(100%)』年化最高且回撤可接受 → 估值择时无效，应长期持有。")
    print("        若某个低分位阈值的卡玛显著更高 → 估值择时有效。")

    # 当前分位提示
    cur_pct = j["pe_pct"].iloc[-1]
    print()
    print(f"  当前上证红利 PE 分位（5年）：{cur_pct*100:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
