#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""案例检验：造纸/印刷板块（用户 2026-10-16 提出的真实案例）

要回答的问题：
  Q1 用"价格+量能"类信号，能不能在这个板块启动**之前/之初**发现它？
  Q2 如果能，提前了多久？之后还有多少肉？
  Q3 若用"基本面"信号（纸价/库存/开工率），理论上能提前多久？
     —— 这一问本脚本无法直接回测（没有纸价/库存的日频数据），
        但可以用**价格结构**做代理：找出板块净值的"底部区域"，
        再看各种价格信号相对该底部的位置。
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))

from strict_engine import CACHE  # noqa: E402


def _sina(code: str) -> str:
    c = str(code).strip()
    if c[:2].lower() in ("sh", "sz", "bj"):
        return c.lower()
    from holdings import to_sina_code
    return to_sina_code(c)


PAPER = {
    "sz002078": "太阳纸业", "sh600963": "岳阳林纸", "sh600567": "山鹰国际",
    "sz002511": "中顺洁柔", "sh603165": "荣晟环保", "sz002599": "盛通股份",
    "sz000488": "晨鸣纸业", "sh600235": "民丰特纸",
}


def load(codes: List[str], start="2024-02-01", end="2026-10-16") -> pd.DataFrame:
    out = {}
    for c in codes:
        p = CACHE / f"{c}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < 150:
            continue
        out[c] = pd.Series(df["close"].astype(float).values, index=df["date"].values)
    return pd.DataFrame(out).sort_index()


def norm_each(px: pd.DataFrame) -> pd.DataFrame:
    o = {}
    for c in px.columns:
        s = px[c].dropna()
        if not s.empty:
            o[c] = px[c] / s.iloc[0]
    return pd.DataFrame(o)


def main() -> int:
    codes = [_sina(c) for c in PAPER]
    px = load(codes)
    if px.empty:
        print("无数据")
        return 1
    names = {_sina(k): v for k, v in PAPER.items()}
    print(f"造纸/包装代表股：{px.shape[1]} 只，区间 {px.index[0]} → {px.index[-1]}")
    print("  " + "、".join(f"{names.get(c,c)}({c})" for c in px.columns))
    print()

    # 个股区间表现
    print("=" * 92)
    print("个股区间表现（买入持有，前复权）")
    print("=" * 92)
    print(f"  {'标的':<12}{'区间收益':>11}{'最大回撤':>11}{'最好20日':>11}{'最差20日':>11}")
    print("  " + "-" * 58)
    for c in px.columns:
        s = px[c].dropna()
        if len(s) < 100:
            continue
        r20 = s.pct_change(20).dropna()
        tot = (s.iloc[-1] / s.iloc[0] - 1) * 100
        mdd = ((s / s.cummax() - 1).min()) * 100
        print(f"  {names.get(c,c):<12}{tot:>+10.1f}%{mdd:>+10.1f}%"
              f"{r20.max()*100:>+10.1f}%{r20.min()*100:>+10.1f}%")

    # 板块净值 + 底部识别
    nav = norm_each(px).mean(axis=1).dropna()
    print()
    print("=" * 92)
    print("板块等权净值：底部在哪？各类信号相对底部的位置")
    print("=" * 92)
    # 找全区间最低点（= 事后才知道的"底部"）
    low_date = nav.idxmin()
    low_idx = list(nav.index).index(low_date)
    peak_date = nav.idxmax()
    peak_idx = list(nav.index).index(peak_date)
    print(f"  区间最低点: {low_date}（净值 {nav.min():.3f}）")
    print(f"  区间最高点: {peak_date}（净值 {nav.max():.3f}）")
    print(f"  低点到高点: {(nav.max()/nav.min()-1)*100:+.1f}%，历时 {peak_idx-low_idx} 个交易日")

    # 各信号首次触发日（低点之后）
    signals = {}
    for i in range(low_idx, len(nav)):
        v = nav.iloc[:i + 1]
        d = nav.index[i]
        above = 0
        for c in px.columns:
            s = px[c].iloc[:i + 1].dropna()
            if len(s) >= 20 and s.iloc[-1] > s.iloc[-20:].mean():
                above += 1
        breadth = above / px.shape[1]
        pos60 = ((v.iloc[-1] - v.iloc[-60:].min()) /
                 (v.iloc[-60:].max() - v.iloc[-60:].min() + 1e-9)) if len(v) >= 60 else 0
        g5 = v.iloc[-1] / v.iloc[-6] - 1 if len(v) > 6 else 0
        g5p = v.iloc[-6] / v.iloc[-11] - 1 if len(v) > 11 else 0
        accel = g5 - g5p
        ma20 = v.iloc[-20:].mean() if len(v) >= 20 else v.iloc[-1]
        ma60 = v.iloc[-60:].mean() if len(v) >= 60 else v.iloc[-1]

        if "同步信号(广度+位置+加速度)" not in signals and \
           breadth >= 0.6 and pos60 >= 0.5 and g5 > 0 and accel > 0:
            signals["同步信号(广度+位置+加速度)"] = d
        if "趋势确认(close>MA20>MA60)" not in signals and v.iloc[-1] > ma20 > ma60:
            signals["趋势确认(close>MA20>MA60)"] = d
        if "广度≥60%" not in signals and breadth >= 0.6:
            signals["广度≥60%"] = d
        if "位置≥60%" not in signals and pos60 >= 0.6:
            signals["位置≥60%"] = d

    print()
    print(f"  {'信号':<30}{'首触日期':>14}{'距底部':>10}{'距高点':>10}{'触发后到高点涨幅':>18}")
    print("  " + "-" * 84)
    for k, d in signals.items():
        i = list(nav.index).index(d)
        print(f"  {k:<30}{str(d):>14}{i-low_idx:>9}天{peak_idx-i:>9}天"
              f"{(nav.max()/nav.iloc[i]-1)*100:>17.1f}%")

    print()
    print("=" * 92)
    print("判读")
    print("=" * 92)
    print("  · 『距底部』越小 = 发现越早；『触发后到高点涨幅』= 还剩多少肉")
    print("  · 若各价格信号的『距底部』都远大于 0 → 价格类信号本质滞后，")
    print("    这正好印证用户的判断：'等我们发现时可能已经有很大涨幅了'")
    print("  · 真正的领先只能来自基本面（纸价/库存/开工率），本脚本无此数据，")
    print("    因此只能给出『价格信号提前不了多少』这个结论，")
    print("    基本面能提前多少需要接入行业数据才能验证")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
