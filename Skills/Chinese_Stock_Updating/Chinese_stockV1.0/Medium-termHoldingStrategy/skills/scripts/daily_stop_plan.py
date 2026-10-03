#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求5：持仓监控 —— 每日按大盘/板块行情动态给出条件单形式的止盈止损。

与原来的区别：
  原来 stop_loss_engine 只输出"建议动作"（文字），需要人工去下单；
  现在直接输出**可直接填入券商 APP 的条件单参数**，且参数随行情动态调整。

动态规则（核心）：
  1. 基础止损 = 成本价 x (1 - 基础比例)
  2. 按大盘/板块 phase 调整宽紧：
       单边上行/波段 → 放宽（让利润奔跑）
       震荡         → 中性
       单边下行/温和回调 → 收紧（保护本金）
  3. 已有浮盈时叠加**保本**：浮盈超过阈值后，止损上移到成本价之上
  4. 最高价回落（移动止损）只收紧不下移
  最终止损 = max(成本止损, 保本线, 最高价 x (1 - 回落比例))
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_root, "common", "paths.py")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        break
    _root = _parent
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, "common"))
sys.path.insert(0, os.path.join(_root, "strategy-fusion-advisor", "skills", "scripts"))

from holdings import load_holdings, to_pure_code  # noqa: E402

# 各 phase 下的止损/回落/保本参数（比例）
POSITION_PLAN_BY_PHASE: Dict[str, Dict[str, float]] = {
    "STRONG_UP":   {"stop": 0.10, "trail": 0.15, "breakeven_at": 0.10},
    "WAVE_UP":     {"stop": 0.09, "trail": 0.12, "breakeven_at": 0.08},
    "RANGE":       {"stop": 0.08, "trail": 0.10, "breakeven_at": 0.06},
    "STRONG_DOWN": {"stop": 0.05, "trail": 0.06, "breakeven_at": 0.03},
    "WEAK_DOWN":   {"stop": 0.05, "trail": 0.06, "breakeven_at": 0.03},
    "UNKNOWN":     {"stop": 0.06, "trail": 0.08, "breakeven_at": 0.04},
}
DEFAULT_PLAN = {"stop": 0.08, "trail": 0.12, "breakeven_at": 0.06}
BREAKEVEN_BUFFER = 0.002      # 保本止损挂在成本价上方 0.2%，覆盖手续费

# ── 是否按 phase 动态调整宽紧（回测结论：默认关闭）──
#
# 实测（131 笔，已应用大盘交易开关，T+10）：
#
#   方案                          胜率     均值     中位    盈亏比    回撤     训练     测试
#   固定 -8%/移12%                54.2%   +4.04%  +1.21%   2.07   -60.7   +5.90%  +2.21%
#   只按 phase 调止损              54.2%   +4.04%  +1.21%   2.07   -60.7      —       —     （无差异）
#   只按 phase 调回落              53.4%   +2.98%  +0.57%   1.83   -57.1      —       —
#   只加保本                       58.8%   +3.44%  +0.20%   1.67   -64.3      —       —
#   三项全开（=原动态默认）          58.8%   +2.60%  +0.20%   1.43   -65.1   +3.97%  +1.24%
#
# 两个原因：
#   1. 应用大盘交易开关后，只有 RANGE(127 笔) 和 STRONG_UP(4 笔) 能开仓，
#      "按 phase 调整"几乎没有施展空间；而 RANGE 把回落从 12% 收到 10% 是净损失。
#   2. 保本止损提高胜率（54.2%→58.8%）但降低期望（+4.04%→+3.44%）——
#      与前几轮一致的规律：保护本金会同时砍掉右尾。
#
# 因此默认使用**回测最优的固定参数**；需要"高胜率优先"时把 BREAKEVEN_ENABLED 打开。
DYNAMIC_BY_PHASE = False      # True = 按 phase 动态调整宽紧
BREAKEVEN_ENABLED = False     # True = 启用保本止损（胜率↑、期望↓）


def plan_for_phase(phase: str) -> Dict[str, float]:
    """取该 phase 的止盈止损参数。

    DYNAMIC_BY_PHASE=False（默认）时一律返回回测最优的固定参数；
    置 True 才启用「单边下行收紧、单边上行放宽」的动态逻辑。
    """
    if not DYNAMIC_BY_PHASE:
        return dict(DEFAULT_PLAN)
    return POSITION_PLAN_BY_PHASE.get((phase or "UNKNOWN").upper(), DEFAULT_PLAN)


def build_position_order(cost: float, current: float, highest: Optional[float],
                         phase: str, code: str = "", name: str = "") -> Dict[str, Any]:
    """为单个持仓生成当日条件单参数。"""
    plan = plan_for_phase(phase)
    cost = float(cost or 0)
    current = float(current or cost)
    high = float(highest or max(cost, current))

    profit = (current / cost - 1) if cost > 0 else 0.0
    peak_profit = (high / cost - 1) if cost > 0 and high > 0 else 0.0

    candidates = []
    if cost > 0:
        candidates.append(("成本止损", cost * (1 - plan["stop"])))
    # 保本触发看"持仓期最高浮盈"而不是当前浮盈：
    # 只要曾经到过保本线，止损就必须抬到成本之上，
    # 否则会出现"浮盈 10% 却以 -3.6% 离场"这种荒谬结果。
    if BREAKEVEN_ENABLED and cost > 0 and peak_profit >= plan["breakeven_at"]:
        candidates.append(("保本止损", cost * (1 + BREAKEVEN_BUFFER)))
    if high > 0:
        candidates.append(("回落卖出", high * (1 - plan["trail"])))

    reason, stop_price = max(candidates, key=lambda x: x[1]) if candidates else ("缺少成本价", None)
    out = {
        "code": to_pure_code(code),
        "name": name,
        "market_phase": (phase or "UNKNOWN").upper(),
        "plan": {k: round(v * 100, 1) for k, v in plan.items()},
        "cost": round(cost, 2),
        "current_price": round(current, 2),
        "highest_price": round(high, 2),
        "profit_pct": round(profit * 100, 2),
        "peak_profit_pct": round(peak_profit * 100, 2),
        "breakeven_armed": bool(cost > 0 and peak_profit >= plan["breakeven_at"]),
        "sell_order": {
            "type": "止盈止损" if reason != "回落卖出" else "回落卖出",
            "trigger_price": round(stop_price, 2) if stop_price else None,
            "trigger_reason": reason,
            "order_type": "市价委托(最优五档)",
            "note": "保命：能卖掉比卖得高重要；跳空低开按开盘价成交",
        },
        "trailing": {
            "activate_above_pct": round(plan["breakeven_at"] * 100, 1),
            "giveback_pct": round(plan["trail"] * 100, 1),
            "order_type": "市价委托(最优五档)",
            "note": "回落卖出：自持仓最高点回落即卖，只收紧不下移",
        },
    }
    if stop_price:
        out["sell_order"]["pnl_at_trigger_pct"] = (
            round((stop_price / cost - 1) * 100, 2) if cost > 0 else None)
    return out


def build_daily_plan(holdings: Optional[List[Dict]] = None,
                     prices: Optional[Dict[str, float]] = None,
                     highs: Optional[Dict[str, float]] = None,
                     phase_of=None) -> Dict[str, Any]:
    """为全部持仓生成当日条件单计划。

    holdings: 持仓列表（默认从 holdings.json 读）
    prices/highs: {纯代码: 现价/持仓期最高价}，生产环境由行情源提供
    phase_of:  callable(code) -> 该标的所属板块的 phase（默认用大盘 phase）
    """
    holdings = load_holdings() if holdings is None else holdings
    prices = prices or {}
    highs = highs or {}
    orders = []
    for h in holdings:
        code = to_pure_code(h.get("code", ""))
        if not code:
            continue
        phase = phase_of(code) if callable(phase_of) else (phase_of or "UNKNOWN")
        cost = h.get("cost") or h.get("cost_price") or 0
        cur = prices.get(code) or h.get("current_price") or cost
        hi = highs.get(code) or h.get("highest_price") or max(float(cur or 0), float(cost or 0))
        orders.append(build_position_order(cost, cur, hi, phase, code, h.get("name", "")))
    return {"date": __import__("datetime").datetime.now().strftime("%Y%m%d"),
            "position_count": len(orders), "orders": orders}


def main() -> int:
    import json
    plan = build_daily_plan()
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
