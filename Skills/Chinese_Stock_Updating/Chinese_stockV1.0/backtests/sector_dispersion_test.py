#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检验用户的观察：光模块/光通信板块内，"选对板块后个股差别不大"是真的吗？

检验思路
--------
用户观点（2026-10-17）：
  "参考下光模块和光通信板块，只要选对板块，个股差别不是那么大"

这与我上一轮的结论（"个股首尾差 137pp，选股很重要"）看似矛盾。
本脚本用**正确的相对视角**来判断谁对：

  若「板块内最差个股的收益」仍然显著为正，
  且「板块内个股离散度」相对于「板块涨幅」较小，
  那么用户的观察成立 —— 选对板块后，选股的边际影响确实不大。

  反之，若最差个股亏损严重、离散度与板块涨幅同量级，
  则选股不可忽略。

关键指标
--------
1. 板块等权收益（"选对板块"的基准回报）
2. 板块内个股收益分布（min / 中位 / max / 标准差 / 极差）
3. **最差个股 vs 沪深300**：若最差个股也跑赢大盘 → 选股不重要
4. **离散度 / 板块收益**：比值小 → 板块贡献为主
5. 跨板块对比：光通信 vs 造纸 / 医药（用户举的失败案例）
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
CACHE = HERE / "cache"

# 用户股票池里的真实分组（名称来自 watchlist）
GROUPS: Dict[str, Dict[str, str]] = {
    "光通信": {
        "sz300308": "中际旭创", "sz300502": "新易盛", "sz300394": "天孚通信",
        "sz300620": "光库科技", "sh688498": "源杰科技", "sh601869": "长飞光纤",
        "sh600487": "亨通光电", "sh600105": "永鼎股份",
    },
    "PCB": {"sz002384": "东山精密", "sh688183": "生益电子"},
    "算力/IDC": {"sz000977": "浪潮信息", "sh603019": "中科曙光"},
    "液冷": {"sz002837": "英维克", "sz300499": "高澜股份"},
    "造纸/包装": {
        "sz002078": "太阳纸业", "sh600963": "岳阳林纸", "sh600567": "山鹰国际",
        "sz002511": "中顺洁柔", "sh603165": "荣晟环保", "sz002599": "盛通股份",
        "sz000488": "晨鸣纸业", "sh600235": "民丰特纸",
    },
    "半导体": {"sh688012": "中微公司", "sh603986": "兆易创新", "sh600584": "长电科技",
               "sh688041": "海光信息", "sh688256": "寒武纪"},
    "银行": {"sh601398": "工商银行", "sh601288": "农业银行", "sh601988": "中国银行",
             "sh601166": "兴业银行", "sh600036": "招商银行"},
}

BENCH = "sh000300"
WINDOWS = [("2024-02-26", "2026-10-16"), ("2025-01-01", "2026-10-16"),
           ("2026-01-01", "2026-10-16")]


def load(code: str, start: str, end: str):
    p = CACHE / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = df["date"].astype(str).str[:10]
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    if len(df) < 60:
        return None
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def analyse(group: str, members: Dict[str, str], start: str, end: str) -> dict:
    rets, mdd = {}, {}
    for c, name in members.items():
        s = load(c, start, end)
        if s is None or len(s) < 20:
            continue
        rets[name] = (s.iloc[-1] / s.iloc[0] - 1) * 100
        mdd[name] = ((s / s.cummax() - 1).min()) * 100
    b = load(BENCH, start, end)
    bret = (b.iloc[-1] / b.iloc[0] - 1) * 100 if b is not None else None
    if len(rets) < 2:
        return {}
    vals = list(rets.values())
    return {
        "group": group, "n": len(vals),
        "eq": statistics.mean(vals),
        "med": statistics.median(vals),
        "min": min(vals), "max": max(vals),
        "sd": statistics.pstdev(vals),
        "range": max(vals) - min(vals),
        "bench": bret,
        "worst_vs_bench": (min(vals) - bret) if bret is not None else None,
        "best": max(rets, key=rets.get), "worst": min(rets, key=rets.get),
        "rets": rets, "mdd": mdd,
    }


def main() -> int:
    for (start, end) in WINDOWS:
        print("=" * 104)
        print(f"区间 {start} → {end}")
        print("=" * 104)
        rows = [analyse(g, m, start, end) for g, m in GROUPS.items()]
        rows = [r for r in rows if r]
        print(f"  {'板块':<12}{'只数':>5}{'等权':>10}{'中位':>10}{'最差':>10}{'最好':>10}"
              f"{'极差':>10}{'离散度':>9}{'最差-基准':>12}")
        print("  " + "-" * 92)
        for r in rows:
            print(f"  {r['group']:<12}{r['n']:>5}{r['eq']:>+9.1f}%{r['med']:>+9.1f}%"
                  f"{r['min']:>+9.1f}%{r['max']:>+9.1f}%{r['range']:>+9.1f}%"
                  f"{r['sd']:>+8.1f}%{r['worst_vs_bench']:>+11.1f}%")
        print()
        # 关键：离散度 / 板块收益
        print(f"  {'板块':<12}{'板块等权':>10}{'离散度/板块收益':>18}  判定")
        print("  " + "-" * 60)
        for r in rows:
            if abs(r["eq"]) > 1e-6:
                ratio = r["sd"] / abs(r["eq"])
                verdict = ("✅ 板块主导（选股影响小）" if ratio < 0.35
                           else "⚠️ 选股影响较大" if ratio < 0.8
                           else "❌ 选股主导")
                print(f"  {r['group']:<12}{r['eq']:>+9.1f}%{ratio:>17.2f}  {verdict}")
        print()
        # 明细（只对光通信与造纸展开）
        for g in ("光通信", "造纸/包装"):
            r = next((x for x in rows if x["group"] == g), None)
            if not r:
                continue
            print(f"  【{g}】逐只明细（区间收益 / 最大回撤）：")
            for name, v in sorted(r["rets"].items(), key=lambda kv: -kv[1]):
                print(f"    {name:<10}{v:>+9.1f}%   {r['mdd'][name]:>+8.1f}%")
            print()
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
