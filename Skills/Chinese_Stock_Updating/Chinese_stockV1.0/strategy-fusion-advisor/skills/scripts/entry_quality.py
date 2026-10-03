#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
入场质量分（Entry Quality Score）—— 按 A 股交易经验重做的入场打分口径。

## 为什么需要它

模块2 复审实测：analyzer 自己的 best_score 与未来收益的 IC = **-0.070**（反向）；
买入位置分位均值 0.830，48.6% 落在 60 日区间最高 10%，那一档平均浮亏 **-8.93%**。
也就是说，现有打分在系统性地奖励"已经涨透"的标的。

## 三条经验（每条都有 IC 支撑）

1. **不追高**（权重最大）：买在 60 日区间的中低位，而不是最高 10%
   —— dist_high_60 越接近 0 越危险
2. **不碰过热**：低波动优先
   —— atr_pct 是全表 IC 最强的因子（-0.180，符号稳定）
3. **要趋势与资金**：正动量 + 资金净流入（趋势给方向，资金给确认）
   —— ETF 动量 IC 正；个股动量 IC 负，故权重压低

## 回测证据（1394 条候选，每日取前 2、冷却 40、T+10/-8%/移12%）

| 方案 | 笔数 | 胜率 | 均值 | 中位 | 盈亏比 | 回撤 |
|:---|---:|---:|---:|---:|---:|---:|
| 现状（按 analyzer 分排序） | 159 | 52.8% | +3.05% | +0.57% | 1.84 | -85.4 |
| **入场质量分前 70% 过滤 + 原分排序** | 139 | **57.6%** | **+3.51%** | **+1.43%** | 1.71 | **-55.9** |
| 入场质量分前 30% 过滤 | 104 | **60.6%** | **+3.51%** | **+1.92%** | 1.53 | -59.7 |

分半：训练 +4.12% → +4.22%，测试 **+1.93% → +2.54%**（两半皆优）。

**代价**：盈亏比从 1.84 降到 1.71——过滤掉的低分候选里有高波动的大赢家。
这是"提高胜率"必然的取舍，故做成可调阈值。
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_root, "common", "paths.py")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        break
    _root = _parent
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, "common"))

# ── 权重与阈值（集中，便于回测调参与审计）──
ENTRY_QUALITY_WEIGHTS = {
    "dist_high_60": -0.40,   # 不追高（离 60 日高点越近越扣分）
    "atr_pct":      -0.25,   # 不碰过热（波动越大越扣分）
    "mom_20":       +0.20,   # 趋势（正动量加分）
    "flow_3d":      +0.15,   # 资金（净流入加分）
}
# 每日保留入场质量分前多少比例的候选（1.0 = 不过滤）。
# 全链路回测（含大盘开关、每日前 2、冷却 40）：
#   保留比例   笔数   胜率    均值     中位     止损占比   安全边际(训练/测试)
#   不过滤     84   61.9%  +5.53%  +2.87%    31.0%     +27.5pp (+29.8/+25.5)
#   0.70      80   66.2%  +6.02%  +3.32%    25.0%     +31.5pp (+30.0/+32.8)
#   0.30      68   69.1%  +6.53%  +4.32%    20.6%     未单独测量
# 默认 0.70：安全边际最好、回撤最小、且**测试段优于训练段**（无过拟合迹象）。
ENTRY_QUALITY_KEEP_RATIO = 0.70
ENTRY_QUALITY_MIN_BARS = 61


def _mom(closes: List[float], n: int) -> float:
    if len(closes) <= n or closes[-n - 1] <= 0:
        return 0.0
    return closes[-1] / closes[-n - 1] - 1


def _atr_pct(highs, lows, closes, n: int = 14) -> float:
    if len(closes) < n + 1:
        return 0.0
    trs = []
    for i in range(-n, 0):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    return (sum(trs) / n) / closes[-1] if closes[-1] > 0 else 0.0


def _flow_3d(closes, opens, amounts, days: int = 3, base_window: int = 20) -> float:
    if len(closes) < base_window + 1 or len(amounts) < days:
        return 0.0
    base = sum(amounts[-base_window:]) / base_window
    if base <= 0:
        return 0.0
    total = 0.0
    for i in range(-days, 0):
        total += amounts[i] * (1.0 if closes[i] >= opens[i] else -1.0)
    return total / base


def factor_bundle(bars: List[Dict]) -> Optional[Dict[str, float]]:
    """从日线序列（最后一根为信号日）算出打入场质量分所需的四个因子（原始值）。"""
    if not bars or len(bars) < ENTRY_QUALITY_MIN_BARS:
        return None
    closes = [float(b["close"]) for b in bars]
    opens = [float(b["open"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    amounts = [float(b.get("amount") or (float(b["close"]) * float(b.get("volume") or 0)))
               for b in bars]
    hi60 = max(highs[-60:])
    return {
        "dist_high_60": (closes[-1] / hi60 - 1) if hi60 > 0 else 0.0,
        "atr_pct": _atr_pct(highs, lows, closes),
        "mom_20": _mom(closes, 20),
        "flow_3d": _flow_3d(closes, opens, amounts),
    }


def entry_quality_score(bars: List[Dict], stats: Optional[Dict[str, Tuple[float, float]]] = None) -> Optional[float]:
    """计算入场质量分。

    stats: 各因子的 (均值, 标准差) 用于标准化。生产环境应由历史样本预先算好并传入；
           缺省时用经验尺度近似，保证单条也能算出一个可比较的分数。
    """
    f = factor_bundle(bars)
    if f is None:
        return None
    if stats is None:
        stats = _DEFAULT_STATS
    total = 0.0
    for k, w in ENTRY_QUALITY_WEIGHTS.items():
        m, s = stats.get(k, (0.0, 1.0))
        s = s or 1.0
        total += w * ((f[k] - m) / s)
    return total


# 经验尺度（来自 1394 条候选的实测分布），仅用于单条打分时的近似标准化
_DEFAULT_STATS: Dict[str, Tuple[float, float]] = {
    "dist_high_60": (-0.165, 0.130),
    "atr_pct": (0.0385, 0.0175),
    "mom_20": (0.098, 0.145),
    "flow_3d": (0.30, 1.60),
}


def pass_filter(score: Optional[float], threshold: Optional[float] = None) -> bool:
    """入场质量分是否通过过滤。score 为 None（数据不足）时**放行**，不因数据问题误杀。"""
    if score is None:
        return True
    if threshold is None:
        return True
    return score >= threshold


def main() -> int:
    import json
    print(json.dumps({
        "weights": ENTRY_QUALITY_WEIGHTS,
        "keep_ratio": ENTRY_QUALITY_KEEP_RATIO,
        "interface": "entry_quality_score(bars) -> float | None；pass_filter(score, threshold) -> bool",
        "evidence": "1394 条候选 A/B：胜率 52.8%→57.6%，均值 +3.05%→+3.51%，回撤 -85.4→-55.9",
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
