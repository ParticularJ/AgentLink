#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心仓再平衡计算器（2026-10-17）

输入当前各 ETF 市值，输出该买卖多少，阈值 3 个百分点。

用法：
  python backtests/rebalance_calculator.py \
      --holdings sh512800=460000,sz159611=150000,sh515220=85000,sh510300=130000,sh511010=175000

或直接运行（会引导输入）。
"""
from __future__ import annotations

import argparse
import sys

# 目标权重（版本 A：含国债 30%）
TARGET_A = {
    "sh512800": ("银行ETF华宝", 0.35),
    "sz159611": ("电力ETF广发", 0.14),
    "sh515220": ("煤炭ETF国泰", 0.07),
    "sh510300": ("沪深300ETF华泰柏瑞", 0.14),
    "sh511010": ("国债ETF国泰", 0.30),
}
# 版本 B：纯权益
TARGET_B = {
    "sh512800": ("银行ETF华宝", 0.50),
    "sz159611": ("电力ETF广发", 0.20),
    "sh515220": ("煤炭ETF国泰", 0.10),
    "sh510300": ("沪深300ETF华泰柏瑞", 0.20),
}

THRESHOLD = 0.03  # 偏离 3 个百分点才动


def calc(holdings: dict, target: dict, threshold: float = THRESHOLD):
    total = sum(holdings.values())
    lines = []
    trades = 0
    print(f"总市值：{total:,.0f} 元\n")
    print(f"  {'ETF':<12}{'名称':<16}{'目标权重':>8}{'目标金额':>12}"
          f"{'当前金额':>12}{'当前占比':>8}{'偏离':>8}  动作")
    print("  " + "-" * 92)
    for code, (name, w) in target.items():
        cur = holdings.get(code, 0.0)
        tgt_amt = total * w
        cur_pct = cur / total if total else 0
        dev = cur_pct - w
        if dev > threshold:
            action = f"卖出 {cur - tgt_amt:,.0f} 元"
            trades += 1
        elif dev < -threshold:
            action = f"买入 {tgt_amt - cur:,.0f} 元"
            trades += 1
        else:
            action = "不动"
        print(f"  {code:<12}{name:<16}{w*100:>7.1f}%{tgt_amt:>12,.0f}"
              f"{cur:>12,.0f}{cur_pct*100:>7.1f}%{dev*100:>+7.1f}%  {action}")
    print()
    print(f"  共需操作 {trades} 笔（其余偏离 <{threshold*100:.0f}% 不动）。")
    if trades == 0:
        print("  ✅ 无需再平衡，下个季度再看。")
    # 校验卖出总金额 ≈ 买入总金额
    sell = sum((holdings.get(c, 0) - total * w) for c, (_, w) in target.items()
               if holdings.get(c, 0) / total - w > threshold if total)
    buy = sum((total * w - holdings.get(c, 0)) for c, (_, w) in target.items()
              if total * w - holdings.get(c, 0) > 0 and total and w - holdings.get(c, 0) / total > threshold)
    if trades:
        print(f"  卖出合计约 {sell:,.0f} 元，买入合计约 {buy:,.0f} 元（差额留现金）。")


def main() -> int:
    ap = argparse.ArgumentParser(description="核心仓再平衡计算器")
    ap.add_argument("--holdings", type=str, default="",
                    help="当前市值，格式 code=金额,code=金额，如 sh512800=460000,sz159611=150000")
    ap.add_argument("--version", choices=["A", "B"], default="A",
                    help="A=含国债(默认)，B=纯权益")
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    args = ap.parse_args()

    target = TARGET_A if args.version == "A" else TARGET_B

    holdings = {}
    if args.holdings:
        for kv in args.holdings.split(","):
            if "=" in kv:
                k, v = kv.split("=")
                holdings[k.strip()] = float(v)
    else:
        print("输入各 ETF 当前市值（元），直接回车跳过该项：")
        for code, (name, w) in target.items():
            s = input(f"  {name}({code}) 目标 {w*100:.0f}% 的当前市值: ").strip()
            if s:
                holdings[code] = float(s)

    if not holdings:
        print("未输入任何持仓。")
        return 1
    calc(holdings, target, args.threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
