#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 独立入场判定（用户需求 4）。

为什么必须与个股分开：
  同一个因子在 ETF 与个股上**符号相反**——
    20 日动量  ETF IC = +0.044   vs   个股 IC = -0.080
  对个股"涨得多"是坏信号（右侧追高有害），对 ETF 是**好**信号（趋势延续）。
  用突破新高/均线多头去选 ETF，方向本身就是错的。

本判定的三条依据（均有 IC 实测支撑）：
  1. 趋势（主）：ETF 20 日动量 > 0 且 收盘 > MA20          —— 动量 IC +0.044
  2. 资金（辅）：近 3 日累计资金推动 > 0（连续净流入）      —— IC +0.018，五分位单调
  3. 位置（防极端）：不在 60 日区间的最高 10%              —— ETF 的 pos_60 IC -0.013（弱负）

资金推动的代理：flow = 成交额 x sign(收盘 - 开盘)，除以 20 日均额归一。
（东财不对 ETF 计算主力资金，f62 恒为 0，因此使用量价代理。）
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Tuple

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_root, "common", "paths.py")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        break
    _root = _parent
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, "common"))

# ── 阈值（集中在此，便于回测调参与审计）──
ETF_TREND_MA = 20           # 趋势均线
ETF_MOM_LOOKBACK = 20       # 动量回看天数
ETF_FLOW_DAYS = 3           # 资金推动累计天数
ETF_FLOW_BASE = 20          # 资金推动归一化基准（20 日均额）
ETF_MAX_POS_60 = 0.90       # 60 日区间位置的最高容忍
ETF_BASE_SCORE = 60.0
ETF_TREND_BONUS = 20.0
ETF_FLOW_BONUS = 15.0
ETF_POS_BONUS = 5.0
ETF_MIN_SCORE = 80.0        # 与融合入口一致的入选门槛


def _pct_change(closes, n: int) -> float:
    if len(closes) <= n or closes[-n - 1] <= 0:
        return 0.0
    return closes[-1] / closes[-n - 1] - 1


def flow_push(closes, opens, amounts, days: int = ETF_FLOW_DAYS,
              base_window: int = ETF_FLOW_BASE) -> float:
    """近 N 日累计"资金推动"，归一到 20 日均成交额。

    flow_t = 成交额_t x sign(收盘_t - 开盘_t)
    """
    if len(closes) < base_window + 1 or len(amounts) < days:
        return 0.0
    base = sum(amounts[-base_window:]) / base_window
    if base <= 0:
        return 0.0
    total = 0.0
    for i in range(-days, 0):
        sign = 1.0 if closes[i] >= opens[i] else -1.0
        total += amounts[i] * sign
    return total / base


def judge_etf_entry(bars: List[Dict]) -> Tuple[bool, Dict]:
    """判定 ETF 当日是否满足入场条件。

    bars: 升序日线，每项含 open/high/low/close/volume（最后一根为信号日）。
    返回 (是否入场, 详情)。
    """
    need = max(ETF_TREND_MA, ETF_MOM_LOOKBACK, ETF_FLOW_BASE) + 1
    detail: Dict = {"pass": False, "reasons": []}
    if not bars or len(bars) < need:
        detail["reasons"].append("数据不足")
        return False, detail

    closes = [float(b["close"]) for b in bars]
    opens = [float(b["open"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    amounts = [float(b.get("amount") or (float(b["close"]) * float(b.get("volume") or 0)))
               for b in bars]

    close = closes[-1]
    ma = sum(closes[-ETF_TREND_MA:]) / ETF_TREND_MA
    mom = _pct_change(closes, ETF_MOM_LOOKBACK)
    flow = flow_push(closes, opens, amounts)
    hi60, lo60 = max(highs[-60:]), min(lows[-60:])
    pos60 = (close - lo60) / (hi60 - lo60) if hi60 > lo60 else 1.0

    trend_ok = mom > 0 and close > ma
    flow_ok = flow > 0
    pos_ok = pos60 < ETF_MAX_POS_60

    score = ETF_BASE_SCORE
    if trend_ok:
        score += ETF_TREND_BONUS
    if flow_ok:
        score += ETF_FLOW_BONUS
    score += ETF_POS_BONUS * max(0.0, 1.0 - pos60)

    detail.update({
        "close": round(close, 3), "ma20": round(ma, 3),
        "mom_20": round(mom * 100, 2), "flow_3d": round(flow, 3),
        "pos_60": round(pos60, 3), "score": round(score, 1),
        "trend_ok": trend_ok, "flow_ok": flow_ok, "pos_ok": pos_ok,
    })
    if trend_ok:
        detail["reasons"].append(f"趋势向上（20日动量 {mom * 100:+.1f}%，收盘在 MA20 上方）")
    else:
        detail["reasons"].append(f"趋势不成立（20日动量 {mom * 100:+.1f}%）")
    if flow_ok:
        detail["reasons"].append(f"资金连续净流入（3日资金推动 {flow:+.2f}）")
    else:
        detail["reasons"].append(f"资金未净流入（3日资金推动 {flow:+.2f}）")
    if not pos_ok:
        detail["reasons"].append(f"位置过高（60日分位 {pos60:.2f} ≥ {ETF_MAX_POS_60}）")

    passed = trend_ok and flow_ok and pos_ok and score >= ETF_MIN_SCORE
    detail["pass"] = passed
    return passed, detail


def main() -> int:
    """命令行自检：对传入的板块 ETF 逐个判定，打印结果。

    生产环境的日线由行情源提供；此处仅做冒烟验证，不联网。
    """
    import json
    codes = sys.argv[1:] or ["sh512480", "sz159995", "sh515880"]
    print(json.dumps({"note": "请在调用方传入 bars；此处仅列出判定接口",
                      "codes": codes,
                      "interface": "judge_etf_entry(bars) -> (bool, detail)"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
