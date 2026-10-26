#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""信号引擎测试 + 煤炭第三案例（2026-10-17）

1) 用资本开支（光模块）验证引擎能复现信号
2) 用煤炭期货 + 中证煤炭指数，检验「需求/供给」过滤条件

煤炭案例的价值：
  2021 年煤价暴涨是「供给冲击」（限产+缺电），不是「需求爆发」。
  若按「只做需求驱动」的过滤条件，煤炭 2021 应被排除。
  但实际煤炭股 2021 年大涨 → 检验过滤条件是否过严。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fundamental_signal_engine import (  # noqa: E402
    FundamentalSeries, run_engine, yoy, detect_inflection,
)


def load_csv(path: str) -> pd.Series:
    df = pd.read_csv(path)
    df["date"] = df["date"].astype(str).str[:10]
    return pd.Series(df["close"].astype(float).values, index=df["date"].values)


def main() -> int:
    # ═══ 1) 资本开支（光模块）═══
    print("=" * 88)
    print("1) 信号引擎测试：资本开支（光模块）")
    print("=" * 88)
    capex = FundamentalSeries(
        name="五大云厂商资本开支", kind="demand", freq="annual", unit="亿美元",
        dates=["2021", "2022", "2023", "2024", "2025", "2026"],
        values=[1450, 1520, 1640, 2208, 3700, 4700],
    )
    s = capex.to_series()
    yy = yoy(s, 1)  # 年度同比
    print("  资本开支同比增速：")
    for d, v in yy.items():
        print(f"    {d.year}: {v*100:+.0f}%")
    hits = detect_inflection(s, periods=1, min_accel=0.03, confirm=1)
    print(f"  拐点检测（加速>3%）：{', '.join(str(h.year) for h in hits)}")
    print("  → 拐点 2024（+35%）与光模块 2023 启动相比，**已实现capex 滞后价格约 1 年**")
    print("    说明引擎必须用「指引」而非「已实现」数据才有领先性。")

    # ═══ 2) 煤炭期货 + 中证煤炭 ═══
    print()
    print("=" * 88)
    print("2) 煤炭第三案例：焦煤期货 vs 中证煤炭指数")
    print("=" * 88)
    # 焦煤期货（基本面价格）
    jm = pd.read_csv("backtests/cache_long/jm_daily.csv") if False else None
    # 直接抓
    import os
    for k in ("NO_PROXY", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
              "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(k, None)
    import akshare as ak
    jm_df = ak.futures_zh_daily_sina(symbol="JM0")
    jm_df["date"] = jm_df["date"].astype(str).str[:10]
    jm = pd.Series(jm_df["close"].astype(float).values, index=jm_df["date"].values)

    coal = load_csv("backtests/cache_long/sz399998.csv")  # 中证煤炭

    # 逐年：焦煤价格 vs 煤炭股
    print(f"  {'年份':<8}{'焦煤期货':>11}{'中证煤炭':>11}")
    print("  " + "-" * 34)
    for y in ("2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"):
        cells = []
        for s0 in (jm, coal):
            seg = s0[s0.index.str.startswith(y)]
            cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+10.1f}%" if len(seg) >= 20 else f"{'—':>11}")
        print(f"  {y:<8}" + "".join(cells))

    # 焦煤 2021 是供给冲击还是需求爆发？
    print()
    print("  关键检验：2021 年煤价暴涨的性质")
    seg = jm[(jm.index >= "2020-06") & (jm.index <= "2021-12")]
    print(f"    焦煤 2020-06 至 2021-12 累计：{(seg.iloc[-1]/seg.iloc[0]-1)*100:+.0f}%")
    print("    已知事实：2021 煤价暴涨主因是「供给冲击」（澳煤禁运+煤矿安全限产+缺电），")
    print("    需求（火电发电量）并未同步爆发 → 这是『供给收缩提价』，不是『量价齐升』。")
    segc = coal[(coal.index >= "2020-06") & (coal.index <= "2021-12")]
    print(f"    同期中证煤炭：{(segc.iloc[-1]/segc.iloc[0]-1)*100:+.0f}%")
    print()
    print("  → 若煤炭股 2021 大涨，说明「供给驱动的涨价」也能带动股价，")
    print("    与造纸案例（供给涨价但股价不涨）矛盾 → 过滤条件需要进一步区分。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
