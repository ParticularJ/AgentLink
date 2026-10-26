#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最近两周 A 股走势 + 核心仓收益（2026-10-17）

核心仓（两个版本）：
  A 含国债：银行40 / 公用16 / 煤炭8 / 沪深300 16 / 国债20
  B 纯权益：银行50 / 公用20 / 煤炭10 / 沪深300 20
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load(code: str) -> pd.Series:
    for base in (HERE / "cache_long", HERE / "cache"):
        p = base / f"{code}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        return pd.Series(df["close"].astype(float).values, index=df["date"].values)
    return pd.Series(dtype=float)


def main() -> int:
    # 核心成分
    comp = {
        "银行": ("sz399986", 0.40),
        "公用": ("sh000041", 0.16),
        "煤炭": ("sz399998", 0.08),
        "沪深300": ("sh000300", 0.16),
        "国债": ("sh511010", 0.20),
    }
    comp_b = {
        "银行": ("sz399986", 0.50),
        "公用": ("sh000041", 0.20),
        "煤炭": ("sz399998", 0.10),
        "沪深300": ("sh000300", 0.20),
    }

    px = {}
    for name, (code, _) in comp.items():
        s = load(code)
        if len(s):
            px[name] = s

    # 对齐到共同交易日
    df = pd.DataFrame(px).sort_index().dropna()
    # 最近 10 个交易日（约两周）
    recent = df.iloc[-10:]
    print(f"最近两周交易日：{recent.index[0]} ~ {recent.index[-1]}（{len(recent)} 个交易日）")
    print()

    # 各成分区间收益（用 recent，最近10个交易日）
    print("=" * 74)
    print("各成分 + 基准 最近两周收益")
    print("=" * 74)
    print(f"  {'标的':<12}{'两周收益':>10}{'最后5日':>10}")
    print("  " + "-" * 40)
    for name in ["银行", "公用", "煤炭", "沪深300", "国债"]:
        if name not in recent:
            continue
        r2 = recent[name].iloc[-1] / recent[name].iloc[0] - 1
        r5 = recent[name].iloc[-1] / recent[name].iloc[-6] - 1
        print(f"  {name:<12}{r2*100:>+9.2f}%{r5*100:>+9.2f}%")
    # 上证指数基准
    sh = load("sh000001")
    if len(sh):
        sh = sh[(sh.index >= recent.index[0]) & (sh.index <= recent.index[-1])]
        if len(sh) >= 2:
            print(f"  {'上证指数':<12}{(sh.iloc[-1]/sh.iloc[0]-1)*100:>+9.2f}%"
                  f"{(sh.iloc[-1]/sh.iloc[-6]-1)*100:>+9.2f}%")

    # 核心仓收益（按权重，用 recent）
    print()
    print("=" * 74)
    print("核心仓最近两周收益（按目标权重）")
    print("=" * 74)

    def port_ret(cfg):
        total = 0.0
        for name, (code, w) in cfg.items():
            if name in recent:
                total += w * (recent[name].iloc[-1] / recent[name].iloc[0] - 1)
        return total

    ra = port_ret(comp)
    rb = port_ret(comp_b)
    hs300 = recent["沪深300"].iloc[-1] / recent["沪深300"].iloc[0] - 1
    print(f"  核心仓 A（含国债20%）: {ra*100:+.2f}%")
    print(f"  核心仓 B（纯权益）    : {rb*100:+.2f}%")
    print(f"  沪深300（基准）       : {hs300*100:+.2f}%")
    print(f"  → 核心仓 A 相对沪深300: {(ra-hs300)*100:+.2f}pp")
    print(f"  → 核心仓 B 相对沪深300: {(rb-hs300)*100:+.2f}pp")

    # 逐日走势
    print()
    print("=" * 74)
    print("逐日走势（归一化到两周起点 = 100）")
    print("=" * 74)
    print(f"  {'日期':<12}{'核心仓A':>10}{'核心仓B':>10}{'沪深300':>10}{'上证指数':>10}")
    print("  " + "-" * 56)
    base_a = base_b = base_h = 100.0
    sh_nav = 100.0
    sh = load("sh000001")
    sh = sh[(sh.index >= recent.index[0]) & (sh.index <= recent.index[-1])]
    for i, d in enumerate(recent.index):
        if i > 0:
            ra_i = sum(w * (recent[name].iloc[i] / recent[name].iloc[i - 1] - 1)
                       for name, (_, w) in comp.items() if name in recent)
            rb_i = sum(w * (recent[name].iloc[i] / recent[name].iloc[i - 1] - 1)
                       for name, (_, w) in comp_b.items() if name in recent)
            base_a *= (1 + ra_i)
            base_b *= (1 + rb_i)
            base_h *= (1 + (recent["沪深300"].iloc[i] / recent["沪深300"].iloc[i - 1] - 1))
        # 上证指数按各自日期对齐
        sh_val = 100.0
        if len(sh) and d in sh.index:
            pos = list(sh.index).index(d)
            if pos > 0:
                sh_nav *= sh.iloc[pos] / sh.iloc[pos - 1]
            sh_val = sh_nav
        print(f"  {d:<12}{base_a:>9.2f}{base_b:>9.2f}{base_h:>9.2f}{sh_val:>9.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
