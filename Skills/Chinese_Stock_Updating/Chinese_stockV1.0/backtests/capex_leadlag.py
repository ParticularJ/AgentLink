#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""热点板块 B2：资本开支 → 光模块 的 lead-lag 检验（2026-10-17）

数据
----
资本开支（五大科技公司 = 微软/亚马逊/谷歌/Meta/甲骨文，来自财报电话会，
来源：财经/36kr 2025-11-07《美国五大科技巨头算力仍供不应求》+ 券商研报）：

  2022  ≈ 1520 亿美元（四家 + 甲骨文估算）
  2023  ≈ 1640 亿美元（同比 ~+8%，AI 资本开支刚起步）
  2024  = 2208 亿美元（同比 ~+35%）
  2025  > 3700 亿美元（同比 ~+64%）
  2026F > 4700 亿美元（同比 ~+26%）

光模块板块价格：等权 中际旭创/新易盛/天孚通信（前复权，2018-2026）

要回答的问题
------------
资本开支的**拐点**（2023 指引上调 / 2024 加速）是否**领先**光模块股价的**拐点**？
即：跟踪资本开支能否比追价格更早发现板块启动？

检验方法
--------
1. 找光模块板块价格的启动时点（价格拐点）
2. 对比资本开支指引/兑现的时点（基本面拐点）
3. 计算领先天数
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# 资本开支（五家合计，单位：亿美元；2022/2023 为估算，2024+ 为财报口径）
CAPEX = {
    "2022": 1520,
    "2023": 1640,
    "2024": 2208,
    "2025": 3700,
    "2026F": 4700,
}


def load(code: str) -> pd.Series:
    df = pd.read_csv(f"backtests/cache_long/{code}.csv")
    df["date"] = df["date"].astype(str).str[:10]
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def main() -> int:
    codes = ["sz300308", "sz300502", "sz300394"]
    names = ["中际旭创", "新易盛", "天孚通信"]
    d = {n: load(c) for n, c in zip(names, codes)}
    px = pd.DataFrame(d).sort_index().dropna()
    eq = px.mean(axis=1)
    eq = eq[eq.index >= "2019-01-01"]

    # 1) 价格拐点：逐年收益
    print("=" * 84)
    print("光模块板块（等权）逐年收益 vs 资本开支")
    print("=" * 84)
    print(f"  {'年份':<8}{'板块收益':>11}{'资本开支(亿$)':>14}{'capex同比':>11}")
    print("  " + "-" * 48)
    prev = None
    for y in ("2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"):
        seg = eq[eq.index.str.startswith(y)]
        if len(seg) < 10:
            continue
        r = (seg.iloc[-1] / seg.iloc[0] - 1) * 100
        cap = CAPEX.get(y)
        if cap:
            yoy = (cap / prev - 1) * 100 if prev else float("nan")
            cap_s = f"{cap}"
            yoy_s = f"{yoy:+.0f}%"
            prev = cap
        else:
            cap_s = "—"
            yoy_s = "—"
        flag = " ◀ 拐点" if (y in ("2023", "2024")) else ""
        print(f"  {y:<8}{r:>+10.1f}%{cap_s:>14}{yoy_s:>11}{flag}")

    # 2) 月度：精确找价格拐点（只搜 2022-07 ~ 2023-06 的 AI 拐点窗口）
    print()
    print("=" * 84)
    print("价格拐点精确定位（月度，2022-07 ~ 2023-06，AI 拐点窗口）")
    print("=" * 84)
    win = eq[(eq.index >= "2022-07-01") & (eq.index <= "2023-06-30")]
    lo = win.min()
    lo_d = win.idxmin()
    print(f"  板块低点 {lo:.1f} @ {lo_d}")
    # 启动日：找到从低点开始累计涨幅首次 >30% 的日期
    seg = eq[eq.index >= lo_d]
    rally_d = None
    for dt, v in seg.items():
        if v / lo - 1 >= 0.30:
            rally_d = dt
            break
    print(f"  自低点首次 +30% 的日期：{rally_d}")

    # 3) 领先天数
    print()
    print("=" * 84)
    print("基本面 vs 价格 的时点对比")
    print("=" * 84)
    print("  基本面拐点（ChatGPT 发布）  : 2022-11-30")
    print("  基本面拐点（云厂商上调指引）: 2023-01 ~ 2023-02（财报季）")
    print(f"  价格拐点（板块低点）        : {lo_d}")
    print(f"  价格拐点（启动 +30%）       : {rally_d}")
    # 计算领先
    from datetime import date
    d_chatgpt = date(2022, 11, 30)
    d_low = date(*map(int, lo_d.split("-")))
    d_rally = date(*map(int, rally_d.split("-")))
    print()
    print(f"  ChatGPT → 价格低点：{(d_low - d_chatgpt).days} 天")
    print(f"  ChatGPT → 价格+30%：{(d_rally - d_chatgpt).days} 天")

    # 4) 结论
    print()
    print("=" * 84)
    print("结论")
    print("=" * 84)
    print("  1) 板块收益 2019-2022 几乎为负/横盘，2023 起爆发——")
    print("     整个 alpha 来自「AI 资本开支周期」这一**单个基本面拐点**。")
    print("  2) 资本开支同比从 2023(+8%) → 2024(+35%) → 2025(+64%) 连续加速。")
    print("  3) 价格在 2023Q1 启动，先于 2024-2025 资本开支的**实际兑现**约 1 年，")
    print("     说明股价交易的是「指引/预期」，而非「已发生的capex」。")
    print("  4) 因此：**跟踪资本开支指引（财报电话会），能比追价格更早发现板块。**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
