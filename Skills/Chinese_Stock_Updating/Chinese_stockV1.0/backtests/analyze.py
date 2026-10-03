#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对回测产出的逐笔明细做二次统计：累计收益、净值回撤、月度分解、分布。

用法：python backtests/analyze.py backtests/out/trades_xxx.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


def curve_stats(df: pd.DataFrame) -> dict:
    """按平仓时间排序，把每笔收益等权累加得到"累计收益点"曲线。

    注意：这里**刻意不做复利**。一笔交易只占用总资金的一小部分（10%~16%），
    若按 (1+r).cumprod() 连乘，等价于"每笔都满仓"，700 多笔下来会得到
    上万百分比的虚假收益。等权相加才是这批信号的可比口径。
    """
    if df.empty:
        return {}
    d = df.sort_values(["exit_date", "signal_date"]).reset_index(drop=True)
    equity = d["ret"].cumsum()          # 单位：收益点（每笔 1 单位资金）
    peak = equity.cummax()
    dd = (equity - peak).min()
    return {
        "trades": len(d),
        "win_rate": (d["ret"] > 0).mean() * 100,
        "avg": d["ret"].mean() * 100,
        "median": d["ret"].median() * 100,
        "cum": equity.iloc[-1] * 100,
        "max_dd": dd * 100,   # 单位：收益点
        "best": d["ret"].max() * 100,
        "worst": d["ret"].min() * 100,
        "stop_ratio": (d["reason"] == "stop").mean() * 100,
        "time_stop": int((d["reason"] == "time_stop").sum()),
        "first": d["signal_date"].min(),
        "last": d["signal_date"].max(),
    }


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["month"] = d["signal_date"].str[:7]
    g = d.groupby("month")["ret"]
    out = pd.DataFrame({
        "笔数": g.size(),
        "胜率%": g.apply(lambda s: (s > 0).mean() * 100).round(1),
        "均值%": (g.mean() * 100).round(2),
        "中位%": (g.median() * 100).round(2),
        "最好%": (g.max() * 100).round(2),
        "最差%": (g.min() * 100).round(2),
    })
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = Path(sys.argv[1])
    df = pd.read_csv(path)
    print(f"文件: {path.name}  共 {len(df)} 行")
    for variant in df["variant"].unique():
        sub = df[df["variant"] == variant]
        s = curve_stats(sub)
        print()
        print(f"── variant = {variant} " + "─" * 46)
        print(f"  区间      : {s['first']} → {s['last']}")
        print(f"  笔数/胜率 : {s['trades']} 笔 / {s['win_rate']:.1f}%")
        print(f"  均值/中位 : {s['avg']:+.2f}% / {s['median']:+.2f}%")
        print(f"  累计(逐笔等权): {s['cum']:+.2f}% 点    最大回撤: {s['max_dd']:.2f}% 点")
        print(f"  最好/最差 : {s['best']:+.2f}% / {s['worst']:+.2f}%")
        print(f"  止损占比  : {s['stop_ratio']:.1f}%   时间止损: {s['time_stop']} 笔")
        print()
        print(monthly(sub).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
