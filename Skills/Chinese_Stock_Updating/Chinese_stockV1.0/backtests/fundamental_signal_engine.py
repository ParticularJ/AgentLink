#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""热点板块基本面信号引擎（2026-10-17）

把「产业基本面驱动选板块」框架落地为可运行代码。

核心逻辑（来自两层框架 v5 的实证）：
  1. 只做「需求驱动的量价齐升」，不做「供给收缩的温和提价」
  2. 拐点检测 = 指标同比增速 由负转正 / 连续加速（二阶导>0）
  3. 领先性来自「前瞻指标」（指引/订单），不是「滞后指标」（已实现营收）

数据模型
--------
FundamentalSeries:
  name     指标名
  dates    日期序列
  values   数值序列
  freq     'annual' | 'quarterly' | 'monthly' | 'weekly'
  kind     'demand'（需求量/开支，如资本开支、销量）
           'price'（价格，如纸价、煤价、存储价）
           'guidance'（前瞻指引，如资本开支指引）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class FundamentalSeries:
    name: str
    dates: List[str]
    values: List[float]
    freq: str = "quarterly"
    kind: str = "price"          # demand / price / guidance
    unit: str = ""

    def to_series(self) -> pd.Series:
        s = pd.Series(self.values, index=pd.to_datetime(self.dates))
        return s.sort_index()


def yoy(s: pd.Series, periods: int) -> pd.Series:
    """同比增速（按周期数对齐）。"""
    return s.pct_change(periods)


def detect_inflection(s: pd.Series, periods: int = 4,
                      min_accel: float = 0.05,
                      confirm: int = 2) -> List[pd.Timestamp]:
    """检测「同比增速加速」的拐点。

    返回触发拐点的日期列表。
    - 计算同比增速 y = s.pct_change(periods)
    - 拐点 = y 连续 confirm 期为正、且相对前 confirm 期在加速（二阶导>0）
    """
    y = s.pct_change(periods).dropna()
    if len(y) < confirm * 2:
        return []
    idx = list(y.index)
    hits = []
    for i in range(confirm, len(y) - confirm):
        recent = y.iloc[i - confirm + 1: i + 1]
        prior = y.iloc[i - 2 * confirm + 1: i - confirm + 1]
        # 连续为正 + 加速
        if (recent > 0).all() and (prior == prior).all():
            accel = recent.mean() - prior.mean()
            if accel > min_accel:
                hits.append(idx[i])
    return hits


def classify_demand(price_s: pd.Series, quant_s: Optional[pd.Series],
                    periods: int = 4) -> str:
    """需求/供给分类。

    有数量序列时：
      价格 YoY>0 且 数量 YoY>0 → demand（量价齐升）
      价格 YoY>0 且 数量 YoY≤0 → supply（供给收缩提价）
    无数量序列时：返回 unknown（需人工/额外数据判断）
    """
    if quant_s is None:
        return "unknown"
    p = price_s.pct_change(periods).iloc[-1]
    q = quant_s.pct_change(periods).iloc[-1]
    if pd.isna(p) or pd.isna(q):
        return "unknown"
    if p > 0 and q > 0:
        return "demand"
    if p > 0 and q <= 0:
        return "supply"
    return "none"


@dataclass
class Signal:
    date: pd.Timestamp
    indicator: str
    classification: str          # demand / supply / guidance / unknown
    yoy_at_signal: float
    message: str


def run_engine(series: FundamentalSeries,
               quant_series: Optional[FundamentalSeries] = None,
               periods: int = 4, min_accel: float = 0.05,
               confirm: int = 2, min_magnitude: float = 0.30) -> List[Signal]:
    """运行信号引擎，返回信号列表。

    过滤条件（2026-10-17 修正，来自煤炭/造纸两案例）：
      初版「只做需求驱动」过严（漏掉煤炭 2021 供给冲击大行情）。
      正确过滤 = 「基本面变化幅度 + 利润弹性」：
        - 幅度大（> min_magnitude，如 30%）→ 无论需求/供给都触发
        - 幅度小 → 排除（如造纸 +11%）
    规则：
      - kind='guidance'/'demand'：幅度达标 + 拐点检测 → 买入信号
      - kind='price'：幅度达标 → 买入；幅度小 → 排除（并标注 demand/supply 供参考）
    """
    s = series.to_series()
    signals: List[Signal] = []
    y = s.pct_change(periods)

    # 拐点候选：同比增速加速的点
    hits = detect_inflection(s, periods, min_accel, confirm)

    def emit(d: pd.Timestamp, cls: str) -> Signal:
        v = float(y.loc[d]) if d in y.index and pd.notna(y.loc[d]) else 0.0
        if abs(v) >= min_magnitude:
            verb = "改善" if series.kind in ("demand", "guidance") else "涨价"
            return Signal(date=d, indicator=series.name, classification=cls, yoy_at_signal=v,
                          message=f"{series.name} {verb} {v*100:+.0f}%，幅度达标(≥{min_magnitude*100:.0f}%)，触发买入信号")
        return Signal(date=d, indicator=series.name, classification="weak", yoy_at_signal=v,
                      message=f"{series.name} {v*100:+.0f}%，幅度不足(<{min_magnitude*100:.0f}%)，排除")

    qs = quant_series.to_series() if quant_series else None
    for d in hits:
        cls = series.kind
        if series.kind == "price":
            # 在拐点处做需求/供给标注
            seg = s.loc[:d]
            qseg = qs.loc[:d] if qs is not None else None
            cls = classify_demand(seg, qseg, periods)
        signals.append(emit(d, cls))

    # 若历史无拐点，但当前状态达标/不达标，给出当前信号
    if not hits and len(y) and pd.notna(y.iloc[-1]):
        v = float(y.iloc[-1])
        cls = series.kind if series.kind != "price" else classify_demand(s, qs, periods)
        signals.append(emit(s.index[-1], cls))
    return signals
