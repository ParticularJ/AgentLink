#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""热点板块能否"早发现"？—— 用你自己的股票池与真实行情实测。

背景（用户 2026-10-16 校准后的诉求）
------------------------------------
用户明确：**"追热点"（找到类似印刷/造纸这种板块，买其中的龙头与潜力股）
是我们策略的重点。** 并指出核心痛点：
  "等我们发现时可能已经有很大涨幅了。"

本脚本要回答的是一个**可证伪**的问题：
  行业内**同步信号**（广度 + 量能 + 位置 + 动量加速度）能否比
  **价格趋势确认**（现有 detector 的 MA20/MA60 规则）更早识别板块启动？

方法
----
1. 用 **股票池里的行业组**（用户自己的分类，见 my_stock_pool/watchlist.yaml）作为
   行业成分股 —— 这是真实可得的行业映射，不需要额外数据源。
2. 定义两组信号（都只用当日及以前数据，无未来函数）：
   A. 同步信号（本脚本新增）：
        breadth  = 行业内站上 MA20 的个股占比
        vratio   = 行业等权成交量 / 其 60 日均值
        pos60    = 行业等权净值在 60 日区间中的位置
        accel    = 行业 5 日涨幅 − 前 5 日涨幅（动量加速度）
   B. 趋势确认（现有 detector 的等价物）：
        close > MA20 > MA60（多头排列）
3. 对每个行业、每个交易日，记录：
        t_sync  = 同步信号首次触发的日期
        t_trend = 趋势确认首次触发的日期
        t_rise  = 行业等权净值"本轮上涨起点"（滚动 60 日最低点）
   比较同步信号是否平均早于趋势确认，以及早多少天。
4. 同时检验"早期信号之后是否真的上涨"，避免只是换了个更早的噪声。
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "common"))

CACHE = HERE / "cache"

# 用户股票池里的行业关键词 → 我们希望覆盖的"真实热点行业"
SECTOR_KEYWORDS: Dict[str, List[str]] = {
    "半导体/芯片": ["半导体", "芯片", "存储", "封测", "MLCC", "算力"],
    "光通信/PCB": ["光通信", "PCB", "光模块", "覆铜板"],
    "新能源/电池": ["电池", "储能", "光伏", "风电", "新能源"],
    "医药/创新药": ["医药", "创新药", "CDMO", "生物"],
    "军工/航天": ["军工", "航天", "卫星"],
    "造纸/包装": ["造纸", "包装", "纸业"],
    "银行/红利": ["银行", "长江电力", "核电", "中国移动", "工商银行", "农业银行"],
    "消费/食品": ["白酒", "食品", "家电", "消费"],
}


def _sina(code: str) -> str:
    """幂等转成 sh/sz 前缀格式（load_watchlist 已转过一次）。"""
    c = str(code).strip()
    if c[:2].lower() in ("sh", "sz", "bj"):
        return c.lower()
    try:
        from holdings import to_sina_code
    except ImportError:
        from common.holdings import to_sina_code
    return to_sina_code(c)


def load_watchlist() -> pd.DataFrame:
    """读用户股票池，返回 name/code/sector 映射（code 转成带 sh/sz 前缀）。"""
    from watchlist import load_watchlist_entries
    try:
        from holdings import to_sina_code
    except ImportError:
        from common.holdings import to_sina_code
    rows = load_watchlist_entries()
    for r in rows:
        r["code"] = to_sina_code(r["code"])
    return pd.DataFrame(rows)


def load_prices(codes: List[str], start: str, end: str) -> Optional[pd.DataFrame]:
    out = {}
    for c in codes:
        for cand in (c, c.lower(), c.upper()):
            p = CACHE / f"{cand}.csv"
            if p.exists():
                break
        else:
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < 200:
            continue
        out[c] = pd.Series(df["close"].astype(float).values, index=df["date"].values)
    if len(out) < 3:
        return None
    return pd.DataFrame(out).sort_index()


def rs_mean(s: pd.Series) -> float:
    return float(s.mean())


def _norm_each(px: pd.DataFrame) -> pd.DataFrame:
    """每只标的按**自身首个有效价**归一化。

    ⚠️ 2026-10-16 修正（这是本脚本最隐蔽的一个坑）：
    初版用 `px / px.iloc[0]`。但价格矩阵是"外连接"，首行只有少数标的上市，
    其余为 NaN → 除法后**所有列都变成 NaN**，整个行业净值序列被毁，
    导致同步信号与趋势确认永不触发（对本脚本而言表现为"所有行业都是 None"）。

    正确做法是按列各自的首个有效值归一化：
        s / s.dropna().iloc[0]
    """
    out = {}
    for c in px.columns:
        s = px[c].dropna()
        if s.empty:
            continue
        out[c] = px[c] / s.iloc[0]
    return pd.DataFrame(out)


def analyse_sector(px: pd.DataFrame, name: str) -> dict:
    """对一个行业做同步信号 vs 趋势确认的对比。"""
    dates = px.index
    # 行业等权净值（每只先按自身首个有效价归一化）
    norm = _norm_each(px)
    nav = norm.mean(axis=1).dropna()
    close = px
    dates = nav.index

    results = {"sector": name, "n_stocks": px.shape[1], "days": len(dates),
               "sync_first": None, "trend_first": None, "rise_start": None,
               "sync_fwd": [], "trend_fwd": []}

    # 行业本轮上涨起点 = 全区间 60 日滚动最低点
    roll_min = nav.rolling(60, min_periods=20).min()
    rise_idx = None
    for i in range(len(nav)):
        if nav.iloc[i] == roll_min.iloc[i]:
            rise_idx = i
            break
    if rise_idx is not None:
        results["rise_start"] = dates[rise_idx]

    for i in range(80, len(dates)):
        # ── A. 同步信号 ──
        # ⚠️ 2026-10-16 修正：必须对每个标的先 dropna()。
        # 价格矩阵是"外连接"，未上市期间为 NaN；不 dropna 会让
        # s.iloc[-1] > s.iloc[-20:].mean() 恒为 False（NaN 参与比较），
        # 导致同步信号永不触发——初版因此对所有行业组都返回 None。
        above = 0
        for c in close.columns:
            s = close[c].iloc[:i + 1].dropna()
            if len(s) >= 20 and s.iloc[-1] > s.iloc[-20:].mean():
                above += 1
        breadth = above / close.shape[1]
        nav_i = nav.iloc[:i + 1]
        pos60 = ((nav_i.iloc[-1] - nav_i.iloc[-60:].min()) /
                 (nav_i.iloc[-60:].max() - nav_i.iloc[-60:].min() + 1e-9))
        g5 = nav_i.iloc[-1] / nav_i.iloc[-6] - 1 if len(nav_i) > 6 else 0
        g5_prev = nav_i.iloc[-6] / nav_i.iloc[-11] - 1 if len(nav_i) > 11 else 0
        accel = g5 - g5_prev
        sync = (breadth >= 0.60) and (pos60 >= 0.50) and (g5 > 0) and (accel > 0)

        # ── B. 趋势确认（现有 detector 规则）──
        trend = False
        if len(nav_i) >= 61:
            ma20 = nav_i.iloc[-20:].mean()
            ma60 = nav_i.iloc[-60:].mean()
            trend = nav_i.iloc[-1] > ma20 > ma60

        if sync and results["sync_first"] is None:
            results["sync_first"] = dates[i]
            # 之后 20 日收益
            if i + 20 < len(nav):
                results["sync_fwd"].append(nav.iloc[i + 20] / nav.iloc[i] - 1)
        if trend and results["trend_first"] is None:
            results["trend_first"] = dates[i]
            if i + 20 < len(nav):
                results["trend_fwd"].append(nav.iloc[i + 20] / nav.iloc[i] - 1)
    return results


def main() -> int:
    print("=" * 100)
    print("热点板块能否『早发现』—— 同步信号 vs 趋势确认（用户股票池的真实行业组）")
    print("=" * 100)
    wl = load_watchlist()
    print(f"股票池条目：{len(wl)} 只，行业组 {wl['sector'].nunique()} 个\n")

    all_codes = sorted(set(wl["code"].tolist()))
    px_all = load_prices(all_codes, "2024-02-01", "2026-10-16")
    if px_all is None:
        print("价格数据不足")
        return 1
    print(f"有行情的标的：{px_all.shape[1]} 只，区间 {px_all.index[0]} → {px_all.index[-1]}\n")

    # 按用户行业组聚合（把 1-2 只的小组按主题合并，否则算不出"板块广度"）
    MERGE: Dict[str, List[str]] = {
        "科技硬件(半导体+存储+MLCC+封测)": ["ai_chip", "memory_chip", "mlcc",
                                            "advanced_packaging", "semiconductor_equipment"],
        "光通信+PCB+算力": ["optical_communication", "pcb", "compute_idc", "liquid_cooling"],
        "新能源链(电池+光伏+风电)": ["battery_energy_storage", "solid_state_battery",
                                     "photovoltaic", "wind_power"],
        "军工航天": ["military_host", "commercial_aerospace", "aero_engine"],
        "医药创新": ["innovative_drug"],
        "机器人+智驾+低空": ["humanoid_robot", "intelligent_driving", "low_altitude_economy"],
        "资源品(稀土+工业金属+油气)": ["rare_earth", "industrial_metal", "oil_gas_service"],
        "红利底仓": ["base_holding"],
    }
    results = []
    for label, sectors in MERGE.items():
        codes = [_sina(r["code"] if "code" in r else r[1])
                 for _, r in wl.iterrows() if r["sector"] in sectors]
        codes = [c for c in codes if c in px_all.columns]
        if len(codes) < 3:
            continue
        r = analyse_sector(px_all[codes], f"{label}({len(codes)}只)")
        results.append(r)

    print(f"{'行业组':<28}{'同步信号首触':>14}{'趋势确认首触':>14}{'提前天数':>10}"
          f"{'信号后20日':>12}{'趋势后20日':>12}")
    print("-" * 96)
    leads = []
    for r in sorted(results, key=lambda x: x["sector"]):
        d_sync = r["sync_first"]
        d_trend = r["trend_first"]
        lead = "—"
        if d_sync and d_trend:
            dates = list(px_all.index)
            try:
                lead_days = dates.index(d_trend) - dates.index(d_sync)
                lead = f"{lead_days:+d} 天"
                leads.append(lead_days)
            except ValueError:
                # 日期不在样本索引里（例如信号来自被 dropna 掉的区间）→ 显式降级
                lead = "—（日期缺失）"
        sf = f"{statistics.mean(r['sync_fwd'])*100:+.1f}%" if r["sync_fwd"] else "—"
        tf = f"{statistics.mean(r['trend_fwd'])*100:+.1f}%" if r["trend_fwd"] else "—"
        print(f"{r['sector']:<28}{str(d_sync):>14}{str(d_trend):>14}{lead:>10}"
              f"{sf:>12}{tf:>12}")

    print()
    if leads:
        print(f"同步信号平均比趋势确认早 {statistics.mean(leads):+.1f} 个交易日"
              f"（中位 {statistics.median(leads):+.0f} 天，n={len(leads)}）")
    print()
    print("=" * 100)
    print("判读要点")
    print("=" * 100)
    print("  · 若『提前天数』普遍为正且可观 → 同步信号确实能更早发现，值得纳入生产")
    print("  · 若『信号后20日』不显著为正 → 早发现也没有用（只是更早的噪声）")
    print("  · 两者需同时成立，才是可用的热点识别器")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
