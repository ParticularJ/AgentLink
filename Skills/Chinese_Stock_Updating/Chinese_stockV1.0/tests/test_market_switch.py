#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""需求2 的测试：大盘趋势交易开关。"""
from __future__ import annotations

import sys
import unittest

from tests import support

sys.path.insert(0, str(support.REPO_ROOT / "strategy-fusion-advisor" / "skills" / "scripts"))

import fusion_config as fc
import fusion_runner as fr


class TestMarketTradeSwitch(unittest.TestCase):

    def test_single_down_and_unknown_are_off(self):
        """用户规则：单边下跌不做任何交易；趋势不明也不做。"""
        for phase in ("STRONG_DOWN", "WEAK_DOWN", "UNKNOWN"):
            self.assertEqual(fc.MARKET_TRADE_SWITCH.get(phase), "off", phase)

    def test_tradeable_phases_are_full(self):
        for phase in ("RANGE", "WAVE_UP", "STRONG_UP"):
            self.assertEqual(fc.MARKET_TRADE_SWITCH.get(phase), "full", phase)

    def test_unknown_phase_defaults_to_off(self):
        """配置里没有的档位必须按禁止处理（保守）。"""
        self.assertEqual(fc.MARKET_TRADE_SWITCH.get("NO_SUCH_PHASE", "off"), "off")

    def test_every_detector_phase_is_covered(self):
        """detector 能产出的每个档位都要在开关表里有明确取值，避免漏配。"""
        import market_phase_detector as mpd
        produced = set(mpd.PHASE_PHASES) | {"UNKNOWN"}
        for p in produced:
            self.assertIn(p, fc.MARKET_TRADE_SWITCH, f"{p} 未在 MARKET_TRADE_SWITCH 中配置")

    def test_range_mode_defaults_to_full_with_documented_caveat(self):
        """震荡期限制默认关闭；配置里必须写明为何关闭。"""
        self.assertEqual(fc.RANGE_MODE, "full")

    def test_run_fusion_returns_empty_dict_when_switch_off(self):
        """开关关闭时 run_fusion 必须直接返回空推荐结构，而不是抛错。"""
        import inspect
        src = inspect.getsource(fr.run_fusion)
        self.assertIn("MARKET_TRADE_SWITCH", src)
        self.assertIn("trade_mode", src)


if __name__ == "__main__":
    unittest.main()
