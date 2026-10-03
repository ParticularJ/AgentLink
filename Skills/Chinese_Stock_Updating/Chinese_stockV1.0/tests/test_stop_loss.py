#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""止损决策引擎：优先级 1~9 的核心行为（不联网）。"""
from __future__ import annotations

import unittest
from unittest import mock

import pandas as pd

from tests import support  # noqa: F401

from market_sentiment import MarketSentiment, MarketState
from models import StockData, TechnicalIndicators
from stop_loss_engine import HoldingState, StopLossEngine


def make_tech(price: float = 30.0, **kw) -> TechnicalIndicators:
    """构造一份技术指标；默认均线在价格下方（不算跌破）。"""
    base = dict(
        ma5=price * 0.98,
        ma10=price * 0.96,
        ma20=price * 0.94,
        ma60=price * 0.90,
        atr14=1.2,
        macd=0.1,
        macd_signal=0.05,
        macd_hist=0.05,
        kdj_k=50.0,
        kdj_d=50.0,
        kdj_j=50.0,
    )
    base.update(kw)
    return TechnicalIndicators(**base)


def make_stock_data(code: str = "600584", price: float = 30.0) -> StockData:
    return StockData(
        code=code, name="长电科技", price=price, open=price, high=price, low=price,
        volume=1_000_000, turnover=1e8, change_pct=0.0, volume_ratio=1.0,
    )


def make_state(**kw) -> HoldingState:
    base = dict(
        code="600584",
        name="长电科技",
        cost=30.0,
        shares=1000,
        init_shares=1000,
        entry_date="2026-01-05",
        atr_pct=0.04,
        clear_stop_pct=-0.10,
        clear_stop_price=27.0,      # 成本 -10%
        half_stop_pct=-0.065,
        half_stop_price=28.05,      # 成本 -6.5%
        stop_method="精确ATR",
    )
    base.update(kw)
    return HoldingState(**base)


def market_at(state: MarketState):
    """构造一个固定返回指定情绪的市场判定器（各闸门默认放行）。"""
    m = mock.MagicMock(spec=MarketSentiment)
    m.get_market_state.return_value = (state, pd.DataFrame())
    m.get_drawdown_relax_factor.return_value = 0.0
    m.is_sell_allowed.return_value = True
    m.can_clear_position.return_value = True
    m.can_reduce.return_value = True
    return m


class StopLossPriorityTest(unittest.TestCase):

    def setUp(self):
        self.df = support.make_kline(support.linear_closes(60, 30.0, 0.1))
        self.today = "2026-02-10"

    def engine(self, state=MarketState.NORMAL):
        return StopLossEngine(market_at(state))

    # ── 优先级 1：绝对亏损清仓（不受大盘影响）──────────────
    def test_priority1_clear_on_absolute_loss(self):
        hs = make_state()
        action = self.engine(MarketState.EXTREME_PANIC).check(hs, 26.0, make_stock_data(price=26.0), make_tech(26.0), self.df, self.today)
        self.assertEqual(action.priority, 1)
        self.assertEqual(action.action, "清仓")
        self.assertEqual(action.shares_to_sell, hs.shares)
        self.assertTrue(hs.clear_hit)

    def test_priority1_ignores_panic_state(self):
        """极端恐慌也不能阻止绝对亏损清仓（铁律一）。"""
        hs = make_state()
        action = self.engine(MarketState.EXTREME_PANIC).check(hs, 20.0, make_stock_data(price=20.0), make_tech(20.0), self.df, self.today)
        self.assertEqual(action.priority, 1)

    # ── 优先级 2：绝对亏损减半 ────────────────────────────
    def test_priority2_half_on_medium_loss(self):
        hs = make_state()
        action = self.engine().check(hs, 28.0, make_stock_data(price=28.0), make_tech(28.0), self.df, self.today)
        self.assertEqual(action.priority, 2)
        self.assertEqual(action.action, "减半")
        self.assertGreater(action.shares_to_sell, 0)
        self.assertLessEqual(action.shares_to_sell, hs.shares)
        self.assertTrue(hs.half_hit)

    # ── 优先级 3 / 4：恐慌区禁止卖出 ──────────────────────
    def test_priority3_extreme_panic_blocks_selling(self):
        hs = make_state()
        action = self.engine(MarketState.EXTREME_PANIC).check(hs, 33.0, make_stock_data(price=33.0), make_tech(33.0), self.df, self.today)
        self.assertEqual(action.priority, 3)
        self.assertEqual(action.action, "持有")
        self.assertEqual(action.shares_to_sell, 0)

    def test_priority4_panic_blocks_clearing(self):
        hs = make_state(shares=1000, init_shares=1000)  # 100% 仓位，远高于 3 成下限
        action = self.engine(MarketState.PANIC).check(hs, 33.0, make_stock_data(price=33.0), make_tech(33.0), self.df, self.today)
        self.assertEqual(action.priority, 4)
        self.assertNotEqual(action.action, "清仓")

    # ── 无触发 ──────────────────────────────────────────
    def test_no_stop_returns_hold_for_recent_flat_position(self):
        """刚建仓不久、微幅浮盈：不应触发任何止损。"""
        hs = make_state(entry_date="2026-02-06")   # 与 today 相隔 2 个交易日
        action = self.engine().check(hs, 30.2, make_stock_data(price=30.2), make_tech(30.2), self.df, self.today)
        self.assertEqual(action.action, "持有")
        self.assertEqual(action.shares_to_sell, 0)

    def test_priority9_time_stop_current_behaviour(self):
        """特征化测试：记录优先级 9「时间止损」的**现网行为**，而非期望行为。

        代码实现（stop_loss_engine.py 优先级 9）：
            loss_pct = -hs.current_profit_pct        # 浮盈 +0.7% -> loss_pct = -0.007
            time_stop_threshold = hs.clear_stop_pct * 0.8   # -0.10*0.8 = -0.08
            if loss_pct >= time_stop_threshold: ...  # -0.007 >= -0.08 -> True

        而模块文档对优先级 9 的定义是「持仓>10日 且 利润<5% 且 **亏损**≥原止损×0.8」。
        两者的差别是实质性的：按现实现，任何持仓超过 10 个交易日、
        浮盈不足 5% 的股票（哪怕是小幅盈利）都会被直接清仓，
        并不要求真的出现亏损。

        这属于策略口径问题而不是编码问题，故此处固化现状、不做修改，
        待策略负责人确认后再决定是「按文档修正」还是「保留现状并修订文档」。
        """
        hs = make_state(entry_date="2026-01-05")   # 23 个交易日前
        action = self.engine().check(hs, 30.2, make_stock_data(price=30.2), make_tech(30.2), self.df, self.today)
        self.assertEqual(action.priority, 9)
        self.assertEqual(action.action, "清仓")
        self.assertIn("时间止损", action.name)

    # ── 状态更新 ────────────────────────────────────────
    def test_profit_mode_switches_at_10_percent(self):
        hs = make_state()
        self.engine().check(hs, 33.5, make_stock_data(price=33.5), make_tech(33.5), self.df, self.today)   # +11.7%
        self.assertTrue(hs.profit_mode)
        self.assertAlmostEqual(hs.highest_profit_pct, (33.5 - 30.0) / 30.0, places=6)

    def test_highest_profit_only_increases(self):
        hs = make_state()
        engine = self.engine()
        engine.check(hs, 36.0, make_stock_data(price=36.0), make_tech(36.0), self.df, self.today)   # +20%
        peak = hs.highest_profit_pct
        engine.check(hs, 32.0, make_stock_data(price=32.0), make_tech(32.0), self.df, self.today)   # 回落到 +6.7%
        self.assertEqual(hs.highest_profit_pct, peak)

    def test_current_profit_pct_and_profit_mode_reset(self):
        hs = make_state()
        self.engine().check(hs, 31.5, make_stock_data(price=31.5), make_tech(31.5), self.df, self.today)  # +5%
        self.assertAlmostEqual(hs.current_profit_pct, 0.05, places=6)
        self.assertFalse(hs.profit_mode)


class HoldingStateSerialisationTest(unittest.TestCase):

    def test_to_dict_round_trips_all_fields(self):
        hs = make_state()
        d = hs.to_dict()
        for key in ("code", "name", "cost", "shares", "init_shares", "entry_date",
                    "clear_stop_price", "half_stop_price", "profit_mode",
                    "consecutive_ma5_days", "correction_buy_count_month"):
            self.assertIn(key, d, key)
        self.assertEqual(d["code"], "600584")
        self.assertIsInstance(d["profit_mode"], bool)

    def test_action_dataclass_fields(self):
        hs = make_state()
        df = support.make_kline(support.linear_closes(60, 30.0, 0.1))
        action = StopLossEngine(market_at(MarketState.NORMAL)).check(
            hs, 26.0, make_stock_data(price=26.0), make_tech(26.0), df, "2026-02-10")
        for field in ("priority", "name", "action", "shares_to_sell", "reason", "alert_level"):
            self.assertTrue(hasattr(action, field), field)


class LotSizeTest(unittest.TestCase):

    def test_lot_helpers_respect_100_share_lots(self):
        engine = StopLossEngine(market_at(MarketState.NORMAL))
        self.assertEqual(engine._lot_down("600584", 150), 100)
        self.assertEqual(engine._lot_up("600584", 150), 200)
        self.assertEqual(engine._lot_down("600584", 100), 100)


if __name__ == "__main__":
    unittest.main()
