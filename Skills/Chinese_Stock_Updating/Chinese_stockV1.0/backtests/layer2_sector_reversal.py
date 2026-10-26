#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 2 层 v3：板块"长期横盘 → 向上突破"识别器（两段式，判据全部触发时可得）

v1/v2 的错误（2026-10-16 修正，两次都值得记录）
----------------------------------------------
v1：用"触发后 20 日超额收益"给事件分类 → **未来函数**。
v2：要求"位置处于 250 日区间下半部" **且** "创 120 日新高" →
    两个条件**互相矛盾**（趴在低位与创新高不能同时成立），事件只剩 2~4 个。

v3 的正确模型：把"横盘 → 突破"当成**两段式过程**
------------------------------------------------
  第一段（确认箱体）：存在一个 ≥BOX_DAYS 日的窗口，其区间宽度 (max−min)/mean
      足够小，且该窗口的最高价成为"**箱体上沿**"。
  第二段（突破信号）：在箱体成立之后的首次"收盘价站上箱体上沿"。
  → 这才对应"经过长期横盘和调整之后极有可能进入上涨阶段"。

触发时可得的核心判据
--------------------
  C1 箱体宽度 ≤ 阈值（长期横盘）
  C2 箱体持续 ≥ BOX_DAYS 日
  C3 收盘价首次站上箱体上沿（向上突破）
  C4 **行业相对强度**：近 20 日 行业收益 − 大盘收益 > 阈值
       ← 这是剔除"跟着大盘涨"的核心判据，因为它在触发当日就能算；
         纯跟涨的板块，其相对强度不会为正（大盘涨它也涨，差额≈0）
  C5 量能：近 5 日均量 / 箱体均量 ≥ 阈值

评估（事后，仅用于检验）：触发后 T+20 / T+60 的绝对与超额收益，
按 C4 是否满足分组对比。
"""
from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))
CACHE = HERE / "cache"
BENCH = "sh000300"

SECTORS: Dict[str, List[str]] = {
    "半导体":      ["sh512480", "sz159995", "sh688012", "sh603986", "sh600584"],
    "光通信/算力": ["sh515880", "sz300308", "sz000977", "sh603019", "sz002384"],
    "医药":        ["sz159992", "sh600276", "sz300760"],
    "军工/航天":   ["sh512660", "sh512670", "sh600118", "sh600150"],
    "新能源":      ["sh516160", "sz159755", "sh515790"],
    "有色/贵金属": ["sz159880", "sh518880", "sh516150"],
    "造纸/包装":   ["sz002078", "sh600963", "sh600567", "sz002511", "sh603165",
                    "sz000488", "sh600235"],
    "油气":        ["sh601857", "sh600028", "sh601088"],
    "银行":        ["sh601398", "sh601288", "sh601988", "sh601166", "sh600036"],
    "电力/公用":   ["sh600900", "sh601985", "sz159611"],
    "消费":        ["sh512690", "sz159996", "sh600887", "sh600519"],
    "基建/地产":   ["sh601668", "sh601390", "sh600019", "sh600585"],
}


def load_mat(start: str, end: str):
    codes = {c for cs in SECTORS.values() for c in cs} | {BENCH}
    cl, vo = {}, {}
    for c in codes:
        p = CACHE / f"{c}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < 250:
            continue
        cl[c] = pd.Series(df["close"].astype(float).values, index=df["date"].values)
        vo[c] = pd.Series(df["volume"].astype(float).values, index=df["date"].values)
    close = pd.DataFrame(cl).sort_index()
    vol = pd.DataFrame(vo).reindex(columns=close.columns).sort_index()
    return close, close.get(BENCH), vol


def norm_each(df: pd.DataFrame) -> pd.DataFrame:
    o = {}
    for c in df.columns:
        s = df[c].dropna()
        if not s.empty:
            o[c] = df[c] / s.iloc[0]
    return pd.DataFrame(o)


@dataclass
class Ev:
    sector: str
    date: str
    box_hi: float
    box_days: int
    box_width: float
    rs20: float
    rs60: float
    vol_ratio: float
    breadth: float
    fwd: Dict[int, Tuple[Optional[float], Optional[float]]] = field(default_factory=dict)


def scan(close: pd.DataFrame, bench: pd.Series, vol: pd.DataFrame,
         box_days: int = 120, box_width_max: float = 0.35,
         rs20_min: float = -0.99, vol_min: float = 1.0) -> List[Ev]:
    """两段式：先找箱体，再等首次突破。每个板块每个箱体只记一次突破。"""
    idx = close.index
    b = bench.reindex(idx).ffill()
    evs: List[Ev] = []

    for sector, codes in SECTORS.items():
        cs = [c for c in codes if c in close.columns]
        if len(cs) < 2:
            continue
        nav = norm_each(close[cs]).mean(axis=1)
        n = nav.dropna()
        if len(n) < box_days + 80:
            continue
        dates = list(n.index)

        armed_hi = None          # 当前有效箱体上沿
        armed_start = None
        last_break_i = -10 ** 9

        for j in range(box_days, len(n) - 61):
            # 用【前 box_days 日】判断箱体（不含当日）→ 无未来函数
            win = n.iloc[j - box_days:j]
            hi, lo = win.max(), win.min()
            width = (hi - lo) / win.mean() if win.mean() > 0 else 9.9
            tight = width <= box_width_max
            if tight:
                armed_hi, armed_start = hi, j - box_days

            if armed_hi is None:
                continue
            cur = n.iloc[j]
            # 首次突破
            if cur > armed_hi and (j - last_break_i) > 20:
                i = list(idx).index(dates[j])
                rs20 = (n.iloc[j] / n.iloc[j - 21] - 1) - (b.iloc[i] / b.iloc[i - 20] - 1)
                rs60 = (n.iloc[j] / n.iloc[j - 61] - 1) - (b.iloc[i] / b.iloc[i - 60] - 1)
                vr = 1.0
                c0 = cs[0]
                if c0 in vol.columns:
                    v = vol[c0].iloc[:i + 1].dropna()
                    if len(v) >= 60:
                        vr = v.iloc[-5:].mean() / (v.iloc[-60:].mean() + 1e-9)
                ab = sum(1 for c in cs
                         if len(close[c].iloc[:i + 1].dropna()) >= 20
                         and close[c].iloc[:i + 1].dropna().iloc[-1]
                         > close[c].iloc[:i + 1].dropna().iloc[-20:].mean())
                breadth = ab / len(cs)
                if rs20 < rs20_min or vr < vol_min:
                    continue
                e = Ev(sector=sector, date=dates[j], box_hi=armed_hi,
                       box_days=box_days, box_width=width, rs20=rs20, rs60=rs60,
                       vol_ratio=vr, breadth=breadth)
                for h in (20, 60):
                    if i + h < len(idx):
                        ra = n.iloc[j + h] / cur - 1
                        rb = b.iloc[i + h] / b.iloc[i] - 1
                        e.fwd[h] = (ra, ra - rb)
                    else:
                        e.fwd[h] = (None, None)
                evs.append(e)
                last_break_i = j
                armed_hi = None          # 突破后箱体失效，等待新箱体
    return evs


def report(evs: List[Ev], title: str):
    print("=" * 100)
    print(title)
    print("=" * 100)
    if not evs:
        print("  无事件\n")
        return
    for label, sel in (("相对强度>0（疑似自身反转）", lambda e: e.rs20 > 0),
                       ("相对强度≤0（疑似跟涨）", lambda e: e.rs20 <= 0)):
        g = [e for e in evs if sel(e)]
        if not g:
            continue
        for h in (20, 60):
            a = [e.fwd[h][0] for e in g if e.fwd.get(h) and e.fwd[h][0] is not None]
            x = [e.fwd[h][1] for e in g if e.fwd.get(h) and e.fwd[h][1] is not None]
            if not a:
                continue
            print(f"  【{label}】n={len(g)}  T+{h}: 绝对 {statistics.mean(a)*100:+.2f}%  "
                  f"胜率 {sum(1 for v in a if v>0)/len(a)*100:.0f}%  "
                  f"超额 {statistics.mean(x)*100:+.2f}%")
    print()
    by: Dict[str, List[Ev]] = {}
    for e in evs:
        by.setdefault(e.sector, []).append(e)
    print(f"  {'板块':<14}{'事件':>5}{'rs>0':>6}{'T+20绝对':>11}{'胜率':>7}{'T+60绝对':>11}")
    print("  " + "-" * 56)
    for sec, g in sorted(by.items(), key=lambda kv: -len(kv[1])):
        a20 = [e.fwd[20][0] for e in g if e.fwd.get(20) and e.fwd[20][0] is not None]
        a60 = [e.fwd[60][0] for e in g if e.fwd.get(60) and e.fwd[60][0] is not None]
        if not a20:
            continue
        print(f"  {sec:<14}{len(g):>5}{sum(1 for e in g if e.rs20>0):>6}"
              f"{statistics.mean(a20)*100:>+10.2f}%"
              f"{sum(1 for v in a20 if v>0)/len(a20)*100:>6.0f}%"
              f"{statistics.mean(a60)*100 if a60 else 0:>+10.2f}%")
    print()


def main() -> int:
    START, END = "2022-04-01", "2026-10-16"
    close, bench, vol = load_mat(START, END)
    print(f"区间 {close.index[0]} → {close.index[-1]}（{len(close)} 日），"
          f"标的 {close.shape[1]} 只\n")
    for box_days, bw in ((120, 0.35), (120, 0.50), (60, 0.30), (180, 0.45)):
        evs = scan(close, bench, vol, box_days=box_days, box_width_max=bw)
        report(evs, f"箱体 {box_days} 日 · 宽度≤{bw:.0%} → 事件 {len(evs)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
