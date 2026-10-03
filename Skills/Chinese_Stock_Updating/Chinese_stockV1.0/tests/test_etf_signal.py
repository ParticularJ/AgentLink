#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""需求4 的测试：ETF 独立入场判定。"""
from __future__ import annotations

import sys
import unittest

from tests import support

sys.path.insert(0, str(support.REPO_ROOT / "strategy-fusion-advisor" / "skills" / "scripts"))

import etf_signal as es


def make_bars(n=120, trend=0.002, flow_up=True, base=1.0):
    """构造一段真实形态的日线：上涨 → 回调 → 部分修复。

    单纯的单边上涨会永远收在 60 日区间最高点，被位置防线正确拦住，
    无法用来测试"健康上升趋势应当通过"。因此这里用三段形态：
      [0, 70%)  上涨
      [70%, 88%) 回调（制造 60 日区间高点）
      [88%, 100%) 修复但不创新高
    这样 close 在 MA20 上方、20 日动量为正，但不在区间最高点。
    flow_up 决定 (close-open) 的方向，从而控制资金推动的符号。
    """
    seg = [int(n * 0.70), int(n * 0.88)]
    bars = []
    px = base
    for i in range(n):
        if i < seg[0]:
            step = trend
        elif i < seg[1]:
            step = -trend * 1.2
        else:
            step = trend * 0.9
        o = px
        px = px * (1 + step)
        c = px
        o = c * 0.998 if flow_up else c * 1.002
        bars.append({"date": "2026-01-01", "open": o, "high": max(o, c) * 1.004,
                     "low": min(o, c) * 0.996, "close": c,
                     "volume": 1e6, "amount": c * 1e6})
    return bars


class TestEtfSignal(unittest.TestCase):

    def test_uptrend_with_inflow_passes(self):
        ok, d = es.judge_etf_entry(make_bars(trend=0.002, flow_up=True))
        self.assertTrue(ok, d)
        self.assertTrue(d["trend_ok"])
        self.assertTrue(d["flow_ok"])

    def test_downtrend_rejected(self):
        """ETF 动量 IC 为正，因此下跌趋势必须被拒绝（与个股规则相反）。"""
        ok, d = es.judge_etf_entry(make_bars(trend=-0.002, flow_up=True))
        self.assertFalse(ok)
        self.assertFalse(d["trend_ok"])

    def test_uptrend_without_inflow_rejected(self):
        """趋势在，但资金没有连续净流入 → 不通过（资金是必需项）。"""
        ok, d = es.judge_etf_entry(make_bars(trend=0.002, flow_up=False))
        self.assertFalse(ok)
        self.assertTrue(d["trend_ok"])
        self.assertFalse(d["flow_ok"])

    def test_insufficient_data(self):
        ok, d = es.judge_etf_entry(make_bars(n=10))
        self.assertFalse(ok)
        self.assertIn("数据不足", d["reasons"])

    def test_empty_input(self):
        ok, d = es.judge_etf_entry([])
        self.assertFalse(ok)

    def test_flow_push_sign(self):
        up = make_bars(trend=0.001, flow_up=True)
        dn = make_bars(trend=0.001, flow_up=False)
        cl = [b["close"] for b in up]
        op = [b["open"] for b in up]
        am = [b["amount"] for b in up]
        self.assertGreater(es.flow_push(cl, op, am), 0)
        op2 = [b["open"] for b in dn]
        self.assertLess(es.flow_push(cl, op2, am), 0)

    def test_position_guard_blocks_extreme_high(self):
        """位置过高应被拦（pos_60 >= 0.90）。

        构造一段**单边不停**的急涨：它必然收在 60 日区间最高点，
        正是"ETF 也容易买在高点"的那种形态，必须被位置防线拦下。
        """
        bars = []
        px = 1.0
        for i in range(120):
            px = px * 1.01
            bars.append({"date": "2026-01-01", "open": px * 0.999, "high": px * 1.002,
                         "low": px * 0.998, "close": px,
                         "volume": 1e6, "amount": px * 1e6})
        ok, d = es.judge_etf_entry(bars)
        self.assertFalse(d["pos_ok"])
        self.assertFalse(ok)

    def test_thresholds_are_reviewable(self):
        self.assertEqual(es.ETF_MIN_SCORE, 80.0)
        self.assertEqual(es.ETF_MAX_POS_60, 0.90)


if __name__ == "__main__":
    unittest.main()
