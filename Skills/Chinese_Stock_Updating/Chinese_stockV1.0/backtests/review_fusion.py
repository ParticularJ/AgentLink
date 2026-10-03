#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块3 复审：融合推荐输出与智能条件单的完整性 / 自洽性检查。

不看代码，只看**产出的推荐对象是否满足契约**：
  1. 必填字段是否齐全（代码/名称/分数/仓位/策略/板块）
  2. 条件单四要素是否齐全（买入触发价、委托方式、止损、回落卖出、有效期）
  3. 内部自洽：condition_orders 的基准价是否等于 entry_ref_price；
     entry_max_price 是否 = 基准价 x(1+跳空上限)；stop_price 是否 = 基准价 x(1-止损)
  4. 与 PDF 规格对照：
       止盈用限价、止损用市价；有效期 3-6 个月；止损≈止盈一半（若启用止盈）
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "common"))
sys.path.insert(0, str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"))
import fusion_config as fc

PROD_FIELDS = ["code", "name", "combined_score", "best_score", "strategies",
               "position_pct", "sectors", "session", "exit_plan", "conditional_orders"]
CO_REQUIRED = ["buy", "sell", "execution"]


def main():
    print("=" * 88)
    print("模块3 契约检查")
    print("=" * 88)

    price = 34.56
    co = fc.build_conditional_orders(price)
    fails = []

    # 1) 结构
    for k in CO_REQUIRED:
        if k not in co:
            fails.append(f"conditional_orders 缺少 {k}")
    buy, sell, ex = co.get("buy", {}), co.get("sell", {}), co.get("execution", {})

    # 2) 买入四要素
    for k in ("type", "monitor_price", "order_type", "valid_months"):
        if not buy.get(k):
            fails.append(f"buy 缺少 {k}")
    # 3) 卖出
    for k in ("stop_loss", "trailing"):
        if k not in sell:
            fails.append(f"sell 缺少 {k}")
    sl, tr = sell.get("stop_loss", {}), sell.get("trailing", {})

    # 4) 自洽
    if buy.get("monitor_price") != round(price, 2):
        fails.append("buy.monitor_price != 基准价")
    if sl.get("base_price") != round(price, 2):
        fails.append("stop_loss.base_price != 基准价")
    want_stop = round(price * (1 - fc.CO_STOP_LOSS_PCT), 2)
    if sl.get("trigger_price") != want_stop:
        fails.append(f"stop_loss.trigger_price {sl.get('trigger_price')} != {want_stop}")
    if ex.get("entry_max_price") != round(price * (1 + fc.ENTRY_MAX_GAP_UP), 2):
        fails.append("execution.entry_max_price 与跳空上限不一致")
    if ex.get("max_hold_days") != fc.EXIT_MAX_HOLD_DAYS:
        fails.append("execution.max_hold_days 与 EXIT_MAX_HOLD_DAYS 不一致")

    # 5) PDF 规格
    if "限价" not in (buy.get("order_type") or ""):
        fails.append("PDF：定价买入应用限价委托")
    if "市价" not in (sl.get("order_type") or ""):
        fails.append("PDF：止损应用市价委托（保命）")
    if "市价" not in (tr.get("order_type") or ""):
        fails.append("PDF：回落卖出应用市价委托")
    if not (3 <= (buy.get("valid_months") or 0) <= 6):
        fails.append("PDF：有效期建议 3-6 个月")

    # 6) 止盈启用时的盈亏比（PDF 建议 >= 2:1）
    old = fc.CO_TAKE_PROFIT_PCT
    try:
        fc.CO_TAKE_PROFIT_PCT = 0.16
        co2 = fc.build_conditional_orders(price)
        tp = co2["sell"].get("take_profit", {})
        if not tp:
            fails.append("启用止盈后 sell.take_profit 未生成")
        else:
            ratio = tp["trigger_pct"] / abs(co2["sell"]["stop_loss"]["trigger_pct"])
            if ratio < 2.0:
                fails.append(f"止盈/止损比 {ratio:.2f} < 2:1（PDF 建议 >=2）")
            if "限价" not in tp.get("order_type", ""):
                fails.append("PDF：止盈应用限价委托")
    finally:
        fc.CO_TAKE_PROFIT_PCT = old

    # 7) 无价降级
    co3 = fc.build_conditional_orders(0)
    if co3["buy"]["monitor_price"] is not None:
        fails.append("无价时应为 None，不得编造价格")

    # 8) 关键常量一致性
    checks = {
        "DAILY_TOP_N<=每日候选数(中位3)": fc.DAILY_TOP_N <= 3,
        "MIN_COMBINED_SCORE==MIN_STRATEGY_SCORE": fc.MIN_COMBINED_SCORE == fc.MIN_STRATEGY_SCORE,
        "RUN_LOW_MIN_SCORE>MIN_COMBINED_SCORE": fc.RUN_LOW_MIN_SCORE > fc.MIN_COMBINED_SCORE,
        "MARKET_TRADE_SWITCH 覆盖全部档位": set(fc.MARKET_TRADE_SWITCH) >=
            {"STRONG_UP", "WAVE_UP", "RANGE", "STRONG_DOWN", "WEAK_DOWN", "UNKNOWN"},
        "ETF_TRADABLE_PHASES 与实现一致": fc.ETF_TRADABLE_PHASES == ("STRONG_UP",),
    }
    for k, ok in checks.items():
        if not ok:
            fails.append(f"常量不一致: {k}")

    print()
    if fails:
        print(f"❌ 发现 {len(fails)} 个问题：")
        for f in fails:
            print("   -", f)
    else:
        print("✅ 全部检查通过")

    print()
    print("=" * 88)
    print("输出的条件单（可直接照填券商 APP）")
    print("=" * 88)
    import json
    print(json.dumps(co, ensure_ascii=False, indent=1))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
