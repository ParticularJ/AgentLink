#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""防守标的系统扫描（复用落盘的 phase 表，秒级完成）。

为什么重做而不是沿用 defensive_diag.py
--------------------------------------
defensive_diag.py 用 stride=10 抽样，大盘下行档只剩 **13 个独立日期**，
任何结论都建在 13 个样本上——置信区间必然包含 0，不足以采纳或否决。

本脚本分两步：
  1. `--build` 把 phase 表**只算一次**落盘（daily_phases 对 28 个板块重算很贵，
     而它此前在每次实验里都被重复调用——这是回测慢的真正原因）；
  2. 之后在内存里做扫描，可以做全量样本、分半验证、bootstrap 置信区间。

分析内容：
  A. 大盘下行档 vs 其他档：全部板块 ETF 的 T+N 表现（找谁真的抗跌）
  B. 候选窄名单（300红利低波 / 黄金）的分半验证 + bootstrap CI
  C. 与诊断脚本旧结论（stride=10）的一致性核对
"""
from __future__ import annotations

import argparse
import json
import pickle
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from backtest_september import QuoteCache, daily_phases  # noqa: E402

START, END = "2025-09-30", "2026-09-30"
PHASE_TABLE = HERE / "out" / "phase_table.pkl"

# 防守白名单（来自 fusion_config.DEFENSIVE_ETFS 对应的板块）
DEFENSIVE_SECTORS = ('底仓', '贵金属', '券商')
DOWN_PHASES = ("STRONG_DOWN", "WEAK_DOWN")


# ═══════════════════════════════════════════════════════════
# 1) phase 表：算一次，落盘
# ═══════════════════════════════════════════════════════════

def build_phase_table(end: str = END):
    cache = QuoteCache()
    days = cache.days_between(START, end)
    table = {}
    print(f"预计算 phase 表：{len(days)} 个交易日 × 28 个板块（约需 1 分钟）...")
    for i, d in enumerate(days, 1):
        market, sectors, detail = daily_phases(cache, d)
        # 每个板块只留第一只 ETF（与生产 collect_*_etf_recommendations 的取法一致）
        etf_of = {}
        for sec in detail:
            codes = (sec.get("meta") or {}).get("etf_codes") or []
            if codes:
                etf_of[sec["sector"]] = codes[0]
        table[d] = {"market": market, "sectors": sectors, "etf_of": etf_of}
        if i % 40 == 0:
            print(f"  {i}/{len(days)} ...")
    PHASE_TABLE.parent.mkdir(parents=True, exist_ok=True)
    with open(PHASE_TABLE, "wb") as f:
        pickle.dump({"start": START, "end": end, "table": table}, f)
    print(f"✅ 已写入 {PHASE_TABLE}（{len(table)} 日）")
    return table


def load_phase_table():
    if not PHASE_TABLE.exists():
        return build_phase_table()
    with open(PHASE_TABLE, "rb") as f:
        obj = pickle.load(f)
    print(f"（复用已落盘的 phase 表：{PHASE_TABLE.name}，"
          f"{len(obj['table'])} 日，{obj['start']} → {obj['end']}）")
    return obj["table"]


# ═══════════════════════════════════════════════════════════
# 2) 工具
# ═══════════════════════════════════════════════════════════

def fwd_ret(cache: QuoteCache, code: str, day: str, n: int):
    rows = cache.forward(code, day, n)
    if len(rows) < n:
        return None
    b = cache.bar(code, day)
    if not b or float(b["close"]) <= 0:
        return None
    return float(rows[-1]["close"]) / float(b["close"]) - 1.0


def stats(xs):
    if not xs:
        return None
    return {
        "n": len(xs),
        "mean": statistics.mean(xs) * 100,
        "median": statistics.median(xs) * 100,
        "up": sum(1 for x in xs if x > 0) / len(xs) * 100,
    }


def boot_ci(xs, iters=5000, alpha=0.05, seed=42):
    """bootstrap 均值置信区间（不假设分布）。"""
    if len(xs) < 3:
        return None
    rnd = random.Random(seed)
    n = len(xs)
    means = []
    for _ in range(iters):
        means.append(sum(xs[rnd.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int(iters * alpha / 2)]
    hi = means[int(iters * (1 - alpha / 2))]
    return lo * 100, hi * 100


def fmt(s):
    if not s:
        return f"{'—':>30}"
    return f"{s['mean']:>+7.2f}% / {s['up']:>5.1f}% / n={s['n']:<4}"


# ═══════════════════════════════════════════════════════════
# 3) 分析
# ═══════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="强制重建 phase 表")
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--stride", type=int, default=5,
                    help="抽样间隔（1=全量；5=降低重叠）")
    args = ap.parse_args()

    if args.build and PHASE_TABLE.exists():
        PHASE_TABLE.unlink()
    table = load_phase_table()
    cache = QuoteCache()
    H = args.horizon
    S = args.stride

    days = sorted(table)
    sampled = days[::S]
    dist = Counter(table[d]["market"] for d in days)
    print(f"\n区间 {START} → {END}：{len(days)} 个交易日，抽样 {len(sampled)} 个（stride={S}）")
    print("大盘档位分布（全量）: " + "  ".join(f"{k}={v}" for k, v in dist.most_common()))
    down_days = [d for d in sampled if table[d]["market"] in DOWN_PHASES]
    print(f"抽样中下行档: {len(down_days)} 日")

    # ── A. 逐板块：下行档 vs 其他档 ───────────────────────
    print(f"\n{'='*96}")
    print(f"A. 各板块 ETF 的未来 T+{H} 表现（stride={S}）")
    print(f"{'='*96}")
    print(f"  {'板块':<12}{'ETF':<11}{'下行档 均值/上涨率/n':>30}{'其他档 均值/上涨率/n':>30}")
    print("  " + "-" * 92)

    rows = []
    for sector in table[days[0]]["sectors"]:
        dn, ot = [], []
        for d in sampled:
            code = table[d]["etf_of"].get(sector)
            if not code:
                continue
            r = fwd_ret(cache, code, d, H)
            if r is None:
                continue
            (dn if table[d]["market"] in DOWN_PHASES else ot).append(r)
        sd, so = stats(dn), stats(ot)
        rows.append((sector, table[days[0]]["etf_of"].get(sector, "?"), sd, so))
    # 按下行档均值排序
    rows.sort(key=lambda x: -(x[2]["mean"] if x[2] else -99))
    for sector, code, sd, so in rows:
        mark = " ★" if sector in DEFENSIVE_SECTORS else ""
        print(f"  {sector:<12}{code:<11}{fmt(sd):>30}{fmt(so):>30}{mark}")

    # ── B. 窄名单验证 ─────────────────────────────────────
    print(f"\n{'='*96}")
    print(f"B. 候选窄名单验证（T+{H}，下行档建仓）")
    print(f"{'='*96}")
    NARROW = {"300红利低波ETF嘉实": None, "黄金ETF华安": None}
    # 从板块反查 ETF
    etf_by_name = {}
    for sector, code, sd, so in rows:
        etf_by_name[(sector, code)] = (sd, so)

    candidates = {
        "宽（底仓+贵金属+券商）": ["sh515180", "sh563020", "sh515300", "sh518880", "sh512070"],
        "窄A（300红利低波+黄金）": ["sh515300", "sh518880"],
        "窄B（仅300红利低波）": ["sh515300"],
        "窄C（仅黄金）": ["sh518880"],
    }
    print(f"  {'方案':<26}{'全样本 均值/上涨率/n':>30}{'bootstrap 95% CI':>26}")
    print("  " + "-" * 82)
    for label, codes in candidates.items():
        xs = []
        for d in down_days:
            for c in codes:
                r = fwd_ret(cache, c, d, H)
                if r is not None:
                    xs.append(r)
        s = stats(xs)
        ci = boot_ci(xs)
        ci_s = f"[{ci[0]:+.2f}%, {ci[1]:+.2f}%]" if ci else "—"
        flag = "✅" if ci and ci[0] > 0 else ("❌" if ci and ci[1] < 0 else "⚠️含0")
        print(f"  {label:<26}{fmt(s):>30}{ci_s:>26}  {flag}")

    # ── C. 分半验证（窄 A）────────────────────────────────
    print(f"\n{'='*96}")
    print(f"C. 分半验证（窄A：300红利低波 + 黄金）")
    print(f"{'='*96}")
    mid = days[len(days) // 2]
    print(f"  分割点: {mid}")
    for label, sel in (("训练段（前半）", lambda d: d < mid),
                       ("测试段（后半）", lambda d: d >= mid)):
        xs = []
        for d in down_days:
            if not sel(d):
                continue
            for c in ("sh515300", "sh518880"):
                r = fwd_ret(cache, c, d, H)
                if r is not None:
                    xs.append(r)
        s = stats(xs)
        ci = boot_ci(xs)
        ci_s = f"[{ci[0]:+.2f}%, {ci[1]:+.2f}%]" if ci else "—"
        print(f"  {label:<16}{fmt(s):>30}   CI {ci_s}")

    # ── D. 与旧诊断（stride=10）核对 ──────────────────────
    print(f"\n{'='*96}")
    print("D. 与 defensive_diag.py（stride=10）的一致性核对")
    print(f"{'='*96}")
    days10 = days[::10]
    down10 = [d for d in days10 if table[d]["market"] in DOWN_PHASES]
    for label, codes in (("防守 ETF 汇总（5 只）", ["sh515180", "sh563020", "sh515300", "sh518880", "sh512070"]),):
        for tag, ds in (("stride=10", down10), ("stride=5", down_days)):
            xs = []
            for d in ds:
                for c in codes:
                    r = fwd_ret(cache, c, d, H)
                    if r is not None:
                        xs.append(r)
            print(f"  {label:<24}{tag:<10}{fmt(stats(xs))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
