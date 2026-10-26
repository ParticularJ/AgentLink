#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 3 层：板块内选股 —— "龙头"的各种定义，哪个真的有效？

背景
----
造纸板块案例显示：同一个"板块判断"下，8 只个股区间收益从 −40.1% 到 +97.1%，
**首尾差 137 个百分点**。这比板块筛选（+3%/20日）和核心仓择时（无效）的贡献都大得多。

硬约束
------
缓存里**没有市值/ROE/负债率**等基本面字段，只有 OHLCV。
因此"龙头"只能用**价格与成交**的代理指标定义。本脚本把常见定义都测一遍：

  D1 动量龙头：板块启动前 60 日涨幅最高（强者恒强）
  D2 反转潜力：板块启动前 60 日涨幅最低（补涨/潜力）
  D3 流动性龙头：成交额（close×volume）最大（"大票"代理）
  D4 低波动：启动前 60 日日收益标准差最低（防守）
  D5 高弹性：启动前 60 日收益标准差最高（beta 代理）
  D6 接近高点：距 250 日高点回撤最小（趋势最顺）

方法
----
1. 用第 2 层已验证的信号选出"板块启动日"（箱体突破 + 相对强度>0）；
2. 在每个启动日，对**该板块内所有可得个股**按上述指标排序；
3. 比较：Top-1 / Top-2 / Top-3 / 板块等权 的 T+20、T+60 收益与胜率；
4. 同时给出"选股相对等权的超额"——这就是选股能力的量化。

⚠️ 无未来函数：所有排序指标只用启动日及以前数据。
"""
from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))
CACHE = HERE / "cache"
BENCH = "sh000300"

# 板块 → 成分股（个股为主，确保每板块有多只可比）
SECTORS: Dict[str, List[str]] = {
    "半导体":      ["sh688012", "sh603986", "sh600584", "sh688041", "sh688256"],
    "光通信/算力": ["sz300308", "sz300502", "sz300394", "sz300620", "sh688498",
                    "sh601869", "sh600487", "sh600105", "sz000977", "sh603019"],
    "医药":        ["sh600276", "sz300760"],
    "军工/航天":   ["sh600118", "sh600150", "sh601989", "sh600963"],
    "新能源":      ["sz159755", "sh515790", "sz300274", "sz002594"],
    "有色/贵金属": ["sh518880", "sh516150", "sz159880", "sh601899"],
    "造纸/包装":   ["sz002078", "sh600963", "sh600567", "sz002511", "sh603165",
                    "sz000488", "sh600235"],
    "油气":        ["sh601857", "sh600028", "sh601088"],
    "银行":        ["sh601398", "sh601288", "sh601988", "sh601166", "sh600036"],
    "电力/公用":   ["sh600900", "sh601985", "sz159611"],
    "消费":        ["sh512690", "sz159996", "sh600887", "sh600519"],
    "基建/地产":   ["sh601668", "sh601390", "sh600019", "sh600585"],
}


def load(start: str, end: str):
    codes = {c for cs in SECTORS.values() for c in cs} | {BENCH}
    cl, vo = {}, {}
    for c in codes:
        p = CACHE / f"{c}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < 260:
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


# ── 排序指标（全部只用 idx 当日及以前）──
def score_momentum(px, vol, i, code):
    s = px[code].iloc[:i + 1].dropna()
    return s.iloc[-1] / s.iloc[-61] - 1 if len(s) > 61 else None


def score_reversal(px, vol, i, code):
    m = score_momentum(px, vol, i, code)
    return -m if m is not None else None


def score_liquidity(px, vol, i, code):
    if code not in vol.columns:
        return None
    s = px[code].iloc[:i + 1].dropna()
    v = vol[code].iloc[:i + 1].dropna()
    idx = s.index.intersection(v.index)
    if len(idx) < 20:
        return None
    turn = (s[idx] * v[idx]).iloc[-20:].mean()
    return turn if turn == turn else None


def score_lowvol(px, vol, i, code):
    s = px[code].iloc[:i + 1].dropna()
    if len(s) < 62:
        return None
    r = s.pct_change().iloc[-60:]
    return -r.std() if r.std() > 0 else None


def score_highvol(px, vol, i, code):
    s = px[code].iloc[:i + 1].dropna()
    if len(s) < 62:
        return None
    r = s.pct_change().iloc[-60:]
    return r.std() if r.std() > 0 else None


def score_near_high(px, vol, i, code):
    s = px[code].iloc[:i + 1].dropna()
    if len(s) < 60:
        return None
    w = s.iloc[-250:]
    return -(1 - s.iloc[-1] / w.max())      # 越接近高点越好（取负回撤）


SCORERS = {
    "D1 动量龙头": score_momentum,
    "D2 反转潜力": score_reversal,
    "D3 流动性龙头": score_liquidity,
    "D4 低波动": score_lowvol,
    "D5 高弹性": score_highvol,
    "D6 接近高点": score_near_high,
}


@dataclass
class Breakout:
    sector: str
    i: int
    date: str
    codes: List[str]


def find_breakouts(px: pd.DataFrame, bench: pd.Series, vol: pd.DataFrame,
                   box_days: int = 120, box_width_max: float = 0.50) -> List[Breakout]:
    """第 2 层已验证的信号：箱体突破 + 相对强度>0。"""
    idx = list(px.index)
    b = bench.reindex(px.index).ffill()
    out: List[Breakout] = []
    for sector, codes in SECTORS.items():
        cs = [c for c in codes if c in px.columns]
        if len(cs) < 2:
            continue
        nav = norm_each(px[cs]).mean(axis=1).dropna()
        dates = list(nav.index)
        armed = None
        last = -10 ** 9
        for j in range(box_days, len(nav) - 61):
            win = nav.iloc[j - box_days:j]
            if (win.max() - win.min()) / win.mean() <= box_width_max:
                armed = win.max()
            if armed is None:
                continue
            if nav.iloc[j] > armed and (j - last) > 20:
                i = idx.index(dates[j])
                rs20 = (nav.iloc[j] / nav.iloc[j - 21] - 1) - (b.iloc[i] / b.iloc[i - 20] - 1)
                if rs20 > 0:
                    out.append(Breakout(sector=sector, i=i, date=dates[j], codes=cs))
                    last = j
                    armed = None
    return out


def main() -> int:
    START, END = "2022-04-01", "2026-10-16"
    px, bench, vol = load(START, END)
    if bench is None:
        print("基准缺失")
        return 1
    print(f"区间 {px.index[0]} → {px.index[-1]}（{len(px)} 日），标的 {px.shape[1]} 只\n")
    bks = find_breakouts(px, bench, vol)
    print(f"识别到板块启动事件：{len(bks)} 个（箱体120日/宽度≤50%/相对强度>0）")
    from collections import Counter
    print("  按板块：" + "  ".join(f"{k}:{v}" for k, v in Counter(x.sector for x in bks).most_common()))
    print()

    idx = list(px.index)
    HORIZONS = (20, 60)

    # 对每个排序方式 × 每个持有期，分别统计 Top-N 与等权的收益
    print("=" * 108)
    print("各『龙头定义』的选股效果（Top-N vs 板块等权，仅取有 ≥3 只个股的板块）")
    print("=" * 108)
    # results[name][h][n] = list of returns；n=0 表示等权
    results: Dict[str, Dict[int, Dict[int, List[float]]]] = {
        name: {h: {0: [], 1: [], 2: [], 3: []} for h in HORIZONS} for name in SCORERS
    }
    for name, fn in SCORERS.items():
        for bk in bks:
            cs = [c for c in bk.codes if c in px.columns]
            if len(cs) < 3:
                continue
            scored = []
            for c in cs:
                v = fn(px, vol, bk.i, c)
                if v is not None and v == v:
                    scored.append((c, v))
            if len(scored) < 3:
                continue
            scored.sort(key=lambda x: -x[1])
            for h in HORIZONS:
                if bk.i + h >= len(idx):
                    continue
                fwd = {}
                for c in cs:
                    s = px[c].iloc[:bk.i + 1].dropna()
                    if len(s) == 0:
                        continue
                    fut = px[c].iloc[:bk.i + h + 1].dropna()
                    if len(fut) <= len(s) - 1:
                        continue
                    fwd[c] = fut.iloc[-1] / s.iloc[-1] - 1
                if len(fwd) < 3:
                    continue
                results[name][h][0].append(statistics.mean(fwd.values()))
                for n in (1, 2, 3):
                    sel = [c for c, _ in scored[:n] if c in fwd]
                    if sel:
                        results[name][h][n].append(statistics.mean([fwd[c] for c in sel]))

    for h in HORIZONS:
        print(f"\n── 持有 T+{h} ──")
        print(f"  {'定义':<16}{'Top1':>10}{'Top2':>10}{'Top3':>10}{'等权':>10}"
              f"{'Top2-等权':>12}{'样本':>7}")
        print("  " + "-" * 78)
        for name in SCORERS:
            a = results[name][h]
            if not a[0]:
                print(f"  {name:<16}{'样本不足':>10}")
                continue
            m0 = statistics.mean(a[0]) * 100
            m1 = statistics.mean(a[1]) * 100 if a[1] else float("nan")
            m2 = statistics.mean(a[2]) * 100 if a[2] else float("nan")
            m3 = statistics.mean(a[3]) * 100 if a[3] else float("nan")
            print(f"  {name:<16}{m1:>+9.2f}%{m2:>+9.2f}%{m3:>+9.2f}%{m0:>+9.2f}%"
                  f"{m2-m0:>+11.2f}pp{len(a[0]):>7}")

    print()
    print("  判读：若某定义的『Top2-等权』显著为正，说明该定义能选出跑赢板块平均的个股；")
    print("        若为负或≈0，说明『选龙头』在统计上不成立，应改用板块 ETF。")
    print("  注意：板块启动事件高度重叠（同一波行情的多个触发日），")
    print("        实际独立样本数远小于上表的『样本』列。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
