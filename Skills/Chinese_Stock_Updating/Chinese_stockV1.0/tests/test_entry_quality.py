#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""入场质量分（模块2 修复）的测试。"""
from __future__ import annotations

import sys
import unittest

from tests import support

sys.path.insert(0, str(support.REPO_ROOT / "strategy-fusion-advisor" / "skills" / "scripts"))

import entry_quality as ms


def bars(n=90, trend=0.002, vol=1e6, pullback=0.0):
    """三段形态：上涨 → 回调（制造 60 日区间高点）→ 修复。

    单纯的单调上涨会让"当前价"永远等于 60 日最高点，dist_high_60 恒为 0，
    无法用来区分"高位"与"低位"。pullback 控制末尾回调深度。
    """
    out, px = [], 1.0
    seg = int(n * 0.8)
    for i in range(n):
        step = trend if i < seg else (-pullback if pullback else trend)
        px *= (1 + step)
        out.append({"open": px * 0.998, "high": px * 1.004, "low": px * 0.996,
                    "close": px, "volume": vol, "amount": px * vol})
    return out


class TestEntryQuality(unittest.TestCase):

    def test_low_position_beats_high_position(self):
        """不追高：同样上涨，但末尾回调过的（离 60 日高点更远）应得更高分。"""
        at_high = ms.entry_quality_score(bars(trend=0.004, pullback=0.0))
        pulled_back = ms.entry_quality_score(bars(trend=0.004, pullback=0.01))
        self.assertIsNotNone(at_high)
        self.assertIsNotNone(pulled_back)
        self.assertGreater(pulled_back, at_high)

    def test_high_volatility_is_penalised(self):
        """不碰过热：波动大的应被扣分（构造高低价差大的序列）。"""
        calm = bars()
        wild = [dict(b, high=b["close"] * 1.08, low=b["close"] * 0.92) for b in bars()]
        self.assertGreater(ms.entry_quality_score(calm), ms.entry_quality_score(wild))

    def test_weights_match_documented_evidence(self):
        self.assertEqual(ms.ENTRY_QUALITY_WEIGHTS["dist_high_60"], -0.40)
        self.assertEqual(ms.ENTRY_QUALITY_WEIGHTS["atr_pct"], -0.25)
        self.assertEqual(ms.ENTRY_QUALITY_KEEP_RATIO, 0.70)

    def test_insufficient_data_returns_none(self):
        self.assertIsNone(ms.entry_quality_score(bars(n=10)))

    def test_none_score_passes_filter(self):
        """数据不足时放行，不因缺数据误杀候选。"""
        self.assertTrue(ms.pass_filter(None, threshold=0.5))

    def test_filter_threshold_works(self):
        self.assertTrue(ms.pass_filter(1.0, threshold=0.5))
        self.assertFalse(ms.pass_filter(0.0, threshold=0.5))
        self.assertTrue(ms.pass_filter(0.0, threshold=None))


if __name__ == "__main__":
    unittest.main()
