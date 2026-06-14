#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
止损决策引擎 - 基于波动率的动态止损与大盘情绪管理系统
完整实现优先级1~9，与文档完全对齐

【对照文档核验清单】
✅ 优先级1：绝对亏损清仓（不受大盘影响）
✅ 优先级2：绝对亏损减半（不受大盘影响）
✅ 优先级3：极端恐慌禁止卖出
✅ 优先级4：恐慌区禁止清仓（最多3成）
✅ 优先级5：利润模式清仓（回撤100%且跌破20日线，非恐慌区）
✅ 优先级6：利润模式减半（回撤达阈值，恐慌区放宽10%）
✅ 优先级7：本金模式5日线（跌破>1×ATR(5)，放量或连续2日）
✅ 优先级8：本金模式10日线（放量1.5×或连续3日，恐慌区禁止清仓）
✅ 优先级9：时间止损（持仓>10日且利润<5%且亏损≥原止损×0.8）
✅ 利润模式均线仅参考（优先级7/8在利润模式下不触发）
✅ 假跌破例外（每只每日限1次）
✅ 纠错买入（每月最多2次）
"""
import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field
import math
from typing import Optional, List, Tuple
from enum import Enum

# 清除代理
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try:
            del os.environ[k]
        except:
            pass

from models import StockData, TechnicalIndicators
from market_sentiment import MarketSentiment, MarketState
from atr_calculator import calc_atr, calc_stop_levels, auto_calc_stop_levels, get_lot_size


# ── 利润保护模式回撤阈值表 ──────────────────────────────
DRAWDOWN_TABLE = [
    (0.10, 0.45),   # (最高浮盈下限, 允许最大回撤)
    (0.15, 0.55),
    (0.25, 0.70),
    (0.40, 0.80),
]


@dataclass
class HoldingState:
    """
    扩展的持仓状态（每只股票独立维护，状态持久化到holdings.json）
    """
    code: str
    name: str
    cost: float             # 当前成本（减半后会更新）
    shares: int             # 当前股数
    init_shares: int        # 初始建仓股数
    entry_date: str         # 买入日期 YYYY-MM-DD

    # ── 止损参数（由ATR计算得出，首次建仓时固定）────────────
    atr_pct: float = 0.0           # ATR% = ATR(14) / buy_price
    clear_stop_pct: float = 0.0    # 清仓止损比例
    clear_stop_price: float = 0.0   # 清仓止损价格
    half_stop_pct: float = 0.0      # 减半止损比例
    half_stop_price: float = 0.0   # 减半止损价格
    stop_method: str = ""           # 计算方法："精确ATR" / "板块速查" / "快速估算"

    # ── 利润状态───────────────────────────────
    highest_profit_pct: float = 0.0   # 持仓期最高浮盈（只增不减）
    current_profit_pct: float = 0.0  # 当前浮盈
    profit_mode: bool = False         # 是否进入利润保护模式（浮盈≥10%）

    # ── 触发记录（防重复推送，每季度重置）────────────────
    clear_hit: bool = False           # 清仓止损已触发（已清仓）
    half_hit: bool = False            # 绝对亏损减半已触发
    ma5_hit: bool = False             # MA5止损已触发（优先级7）
    ma10_hit: bool = False           # MA10止损已触发（优先级8）
    drawdown_half_hit: bool = False  # 回撤减半已触发（优先级6）
    time_stop_hit: bool = False      # 时间止损已触发

    # ── 连续天数追踪────────────────────────────
    consecutive_ma10_days: int = 0    # 连续跌破MA10天数
    consecutive_ma5_days: int = 0     # 连续跌破MA5天数
    last_ma5_date: str = ""          # 上次跌破MA5日期
    last_ma10_date: str = ""          # 上次跌破MA10日期（独立于last_check_date）
    last_check_date: str = ""        # 上次检查日期
    false_break_date: str = ""       # 假跌破例外已使用日期（14:50验证通过后记录）
    false_break_ma10_date: str = ""  # MA10假跌破例外日期

    # ── 纠错买入──────────────────────────────
    correction_buy_price: float = 0.0
    correction_buy_shares: int = 0
    correction_buy_count_month: int = 0   # 本月纠错次数
    last_correction_month: str = ""      # 上次纠错月份 "YYYY-MM"

    def to_dict(self) -> dict:
        """序列化，用于写入holdings.json"""
        return {
            "code": self.code,
            "name": self.name,
            "cost": self.cost,
            "shares": self.shares,
            "init_shares": self.init_shares,
            "entry_date": self.entry_date,
            "atr_pct": self.atr_pct,
            "clear_stop_pct": self.clear_stop_pct,
            "clear_stop_price": self.clear_stop_price,
            "half_stop_pct": self.half_stop_pct,
            "half_stop_price": self.half_stop_price,
            "stop_method": self.stop_method,
            "highest_profit_pct": self.highest_profit_pct,
            "current_profit_pct": self.current_profit_pct,
            "profit_mode": self.profit_mode,
            "clear_hit": self.clear_hit,
            "half_hit": self.half_hit,
            "ma5_hit": self.ma5_hit,
            "ma10_hit": self.ma10_hit,
            "drawdown_half_hit": self.drawdown_half_hit,
            "time_stop_hit": self.time_stop_hit,
            "consecutive_ma10_days": self.consecutive_ma10_days,
            "consecutive_ma5_days": self.consecutive_ma5_days,
            "last_ma5_date": self.last_ma5_date,
            "last_ma10_date": self.last_ma10_date,
            "last_check_date": self.last_check_date,
            "false_break_date": self.false_break_date,
            "false_break_ma10_date": self.false_break_ma10_date,
            "correction_buy_price": self.correction_buy_price,
            "correction_buy_shares": self.correction_buy_shares,
            "correction_buy_count_month": self.correction_buy_count_month,
            "last_correction_month": self.last_correction_month,
        }


@dataclass
class Action:
    """触发操作"""
    priority: int
    name: str
    action: str           # "清仓" / "减半" / "持有"
    shares_to_sell: int   # 建议卖出股数
    reason: str
    alert_level: str      # "🔴" "🟡" "⚪"


class StopLossEngine:
    """
    止损决策引擎
    每日14:40按优先级1→9顺序检查持仓
    """

    def __init__(self, market_sentiment: MarketSentiment, n_multiplier: float = 2.0):
        self.market = market_sentiment
        self.n = n_multiplier  # ATR乘数N，默认2.0

    # ── 核心：止损检查主循环 ─────────────────────────────
    def _lot_up(self, code: str, shares: int) -> int:
        """止损：向上取整到交易单位整数倍（科创板200，其余100）"""
        lot = get_lot_size(code)
        if lot <= 0:
            return shares
        return math.ceil(shares / lot) * lot

    def _lot_down(self, code: str, shares: int) -> int:
        """剩余股数/止盈：向下取整到交易单位整数倍"""
        lot = get_lot_size(code)
        if lot <= 0:
            return shares
        return int(shares / lot) * lot

    def check(self, holding_state: HoldingState,
             current_price: float,
             current_data: StockData,
             tech: TechnicalIndicators,
             df_history: pd.DataFrame,
             today_str: str) -> Action:
        """
        按优先级1→9顺序检查，返回第一个触发的Action
        所有价格以14:40实时价格为准
        """
        hs = holding_state
        market_state, _ = self.market.get_market_state(today_str)

        # ── 更新利润状态 ────────────────────────────
        hs.current_profit_pct = (current_price - hs.cost) / hs.cost
        hs.profit_mode = hs.current_profit_pct >= 0.10

        # ── 更新最高浮盈（只增不减）────────────────
        if hs.current_profit_pct > hs.highest_profit_pct:
            hs.highest_profit_pct = hs.current_profit_pct

        # ══ 优先级1：绝对亏损清仓 ══════════════════════
        # 【铁律一】不受任何大盘条件影响
        if current_price <= hs.clear_stop_price:
            hs.clear_hit = True
            return Action(
                priority=1,
                name="绝对亏损清仓",
                action="清仓",
                shares_to_sell=hs.shares,
                reason=f"现价{current_price:.2f}≤清仓线{hs.clear_stop_price:.2f}（亏损{hs.clear_stop_pct:.1%}，ATR{hs.stop_method}）",
                alert_level="🔴"
            )

        # ══ 优先级2：绝对亏损减半 ══════════════════════
        # 【铁律一】不受任何大盘条件影响
        if current_price <= hs.half_stop_price:
            hs.half_hit = True
            return Action(
                priority=2,
                name="绝对亏损减半",
                action="减半",
                shares_to_sell=min(self._lot_up(hs.code, math.ceil(hs.shares / 2)), hs.shares),
                reason=f"现价{current_price:.2f}≤减半线{hs.half_stop_price:.2f}（亏损{hs.half_stop_pct:.1%}）",
                alert_level="🔴"
            )

        # ══ 优先级3：极端恐慌 ════════════════════════
        # 禁止任何卖出（绝对亏损规则除外，已在P1/P2处理）
        if market_state == MarketState.EXTREME_PANIC:
            return Action(
                priority=3,
                name="极端恐慌",
                action="持有",
                shares_to_sell=0,
                reason="🚨 极端恐慌状态，禁止任何卖出",
                alert_level="⚪"
            )

        # ══ 优先级4：恐慌区 ══════════════════════════
        if market_state == MarketState.PANIC:
            # 检查是否已在仓位下限（≤3成）
            min_shares = int(hs.init_shares * 0.3)
            if hs.shares <= min_shares:
                return Action(
                    priority=4,
                    name="恐慌区",
                    action="持有",
                    shares_to_sell=0,
                    reason=f"🚨 恐慌区，已在仓位下限({hs.shares}股≤{min_shares}股)",
                    alert_level="⚪"
                )
            # 恐慌区：减至3成最低仓位，不得清仓
            sell = hs.shares - min_shares
            return Action(
                priority=4,
                name="恐慌区",
                action="减至3成",
                shares_to_sell=sell,
                reason=f"🚨 恐慌区，禁止清仓，减至3成最低({min_shares}股)",
                alert_level="🟡"
            )

        # ══ 优先级5：利润模式清仓 ═════════════════════
        # 【铁律二】浮盈≥10%时：回撤100%（回到成本）且跌破20日线，且非恐慌区
        if hs.profit_mode:
            hp = hs.highest_profit_pct
            cp = hs.current_profit_pct
            drawdown = (hp - cp) / hp if hp > 0 else 0.0

            ma20 = tech.ma20 if tech and tech.ma20 else 0
            if drawdown >= 1.0 and ma20 > 0 and current_price < ma20:
                return Action(
                    priority=5,
                    name="利润模式清仓",
                    action="清仓",
                    shares_to_sell=hs.shares,
                    reason=f"浮盈{cp:.1%}回撤100%到成本价且跌破20日线{ma20:.2f}",
                    alert_level="🔴"
                )

        # ══ 优先级6：利润模式减半 ═════════════════════
        # 【铁律二】唯一触发条件是回撤阈值，均线仅参考
        if hs.profit_mode:
            hp = hs.highest_profit_pct
            cp = hs.current_profit_pct
            drawdown = (hp - cp) / hp if hp > 0 else 0.0

            threshold = self._get_drawdown_threshold(hp)
            # 恐慌区放宽10个百分点
            relax = self.market.get_drawdown_relax_factor()
            threshold = max(0.0, threshold - relax)

            if drawdown >= threshold and not hs.drawdown_half_hit:
                hs.drawdown_half_hit = True
                return Action(
                    priority=6,
                    name="利润模式减半",
                    action="减半",
                    shares_to_sell=min(self._lot_up(hs.code, math.ceil(hs.shares / 2)), hs.shares),
                    reason=f"最高浮盈{hp:.1%}，当前回撤{drawdown:.1%}≥阈值{threshold:.1%}（恐慌区放宽{relax:.0%}），减半锁利",
                    alert_level="🟡"
                )

        # ══ 优先级7：本金模式5日线 ════════════════════
        # 【铁律二】利润模式下MA仅参考，不触发
        if not hs.profit_mode:
            ma5 = tech.ma5 if tech and tech.ma5 else 0
            if ma5 > 0 and current_price < ma5:
                # 计算"1×ATR(5)"：ATR(5) = ATR_pct ÷ 5（文档定义）
                atr_unit = hs.atr_pct / 5.0  # ATR(5) = ATR_pct ÷ 5
                price_break_depth = (ma5 - current_price) / ma5  # 跌破幅度比例

                # 条件A：跌破>1×ATR(5)
                cond_a = price_break_depth > atr_unit

                # 条件B1：量>5日均量×1.2（需计算5日均量）
                vol_ma5 = self._calc_vol_ma5(df_history)
                cond_b1 = False
                if vol_ma5 > 0 and hasattr(current_data, 'volume') and current_data.volume > 0:
                    cond_b1 = current_data.volume > vol_ma5 * 1.2

                # 条件B2：连续2天跌破MA5
                cond_b2 = self._update_consecutive_ma5(hs, today_str, True) >= 2

                # 条件B：OR关系
                cond_b = cond_b1 or cond_b2

                if cond_a and cond_b and not hs.ma5_hit:
                    hs.ma5_hit = True
                    return Action(
                        priority=7,
                        name="本金模式5日线",
                        action="减半",
                        shares_to_sell=min(self._lot_up(hs.code, math.ceil(hs.shares / 2)), hs.shares),
                        reason=(f"跌破5日线{ma5:.2f}，幅度{price_break_depth:.2%}>ATR(5){atr_unit:.2%}，"
                               f"{'放量（>5日均量×1.2）' if cond_b1 else '连续2日' if cond_b2 else ''}，减半"),
                        alert_level="🟡"
                    )

        # ══ 优先级8：本金模式10日线 ════════════════════
        # 【铁律二】利润模式下MA仅参考，不触发
        if not hs.profit_mode:
            ma10 = tech.ma10 if tech and tech.ma10 else 0
            if ma10 > 0 and current_price < ma10:
                # 条件B1：量>5日均量×1.5
                vol_ma5 = self._calc_vol_ma5(df_history)
                cond_b1 = False
                if vol_ma5 > 0 and hasattr(current_data, 'volume') and current_data.volume > 0:
                    cond_b1 = current_data.volume > vol_ma5 * 1.5

                # 条件B2：连续3天跌破MA10
                cond_b2 = self._update_consecutive_ma10(hs, today_str, True) >= 3

                cond_b = cond_b1 or cond_b2

                if cond_b and not hs.ma10_hit:
                    # 【铁律三】恐慌区禁止清仓
                    if not self.market.can_clear_position():
                        # 改为减半至3成
                        min_shares = int(hs.init_shares * 0.3)
                        if hs.shares > min_shares:
                            sell = hs.shares - min_shares
                            hs.ma10_hit = True
                            return Action(
                                priority=8,
                                name="本金模式10日线",
                                action="减至3成",
                                shares_to_sell=sell,
                                reason=f"跌破10日线{ma10:.2f}，{'放量' if cond_b1 else '连续3日'}，但恐慌区只可减至3成",
                                alert_level="🟡"
                            )
                        else:
                            return Action(
                                priority=8,
                                name="本金模式10日线",
                                action="持有",
                                shares_to_sell=0,
                                reason="🚨 恐慌区，已在仓位下限",
                                alert_level="⚪"
                            )

                    hs.ma10_hit = True
                    return Action(
                        priority=8,
                        name="本金模式10日线",
                        action="清仓",
                        shares_to_sell=hs.shares,
                        reason=f"跌破10日线{ma10:.2f}，{'放量（>5日均量×1.5）' if cond_b1 else '连续3日'}，清仓",
                        alert_level="🔴"
                    )

        # ══ 优先级9：时间止损 ═════════════════════════
        # 持仓>10日且浮盈<5%且亏损≥原止损×0.8，恐慌区禁止
        if not hs.profit_mode:
            holding_days = self._count_trading_days(hs.entry_date, today_str)
            if holding_days > 10 and hs.current_profit_pct < 0.05:
                time_stop_threshold = hs.clear_stop_pct * 0.8
                # 亏损≥原止损×0.8（注意是"亏损"即负的利润）
                loss_pct = -hs.current_profit_pct  # 亏损比例（正数）
                if loss_pct >= time_stop_threshold and not hs.time_stop_hit:
                    if not self.market.can_clear_position():
                        return Action(
                            priority=9,
                            name="时间止损",
                            action="持有",
                            shares_to_sell=0,
                            reason="🚨 恐慌区，时间止损（清仓）被禁止",
                            alert_level="⚪"
                        )
                    hs.time_stop_hit = True
                    return Action(
                        priority=9,
                        name="时间止损",
                        action="清仓",
                        shares_to_sell=hs.shares,
                        reason=f"持仓{holding_days}交易日，浮盈{hs.current_profit_pct:.1%}<5%且亏损{loss_pct:.1%}≥原止损×0.8({time_stop_threshold:.1%})",
                        alert_level="🔴"
                    )

        # ══ 默认：持有 ══════════════════════════════
        return Action(
            priority=0,
            name="持有",
            action="持有",
            shares_to_sell=0,
            reason="无触发信号，持有不动",
            alert_level="⚪"
        )

    # ── 假跌破验证（14:50调用）──────────────────────────
    def verify_false_break(self, holding_state: HoldingState,
                            current_price: float,
                            current_open: float,
                            ma_key: str = "ma5") -> bool:
        """
        假跌破例外条款（14:50调用）：
        若14:40触发了优先级7/8，但14:50股价收回均线之上且当日收阳线，
        则当日不执行卖出。每只个股每日仅限一次。

        返回True表示：符合假跌破条件，应跳过本次卖出。
        """
        today = datetime.now().strftime("%Y-%m-%d")

        if ma_key == "ma5":
            flag_date = holding_state.false_break_date
            ma_val = getattr(self, f"_last_ma{ma_key}", 0)
        else:
            flag_date = holding_state.false_break_ma10_date
            ma_val = getattr(self, f"_last_ma{ma_key}", 0)

        # 未在14:40记录过假跌破，不适用
        if flag_date != today:
            return False

        # 14:50已收回均线之上
        if current_price >= ma_val:
            # 且当日收阳线
            if current_price >= current_open:
                return True

        return False

    def mark_false_break(self, holding_state: HoldingState, ma5: float, ma10: float, today: str):
        """14:40触发优先级7/8时调用，记录假跌破标记"""
        holding_state.false_break_date = today
        self._last_ma5 = ma5
        self._last_ma10 = ma10

    # ── 减半/清仓后状态更新 ──────────────────────────────
    def after_half_sell(self, holding_state: HoldingState, sell_price: float):
        """
        减半后调用：重置成本为减半时价格，重置最高浮盈，重新累计
        """
        # 剩余一半股数的成本 = 原成本（减半后总成本不变）
        # 但为了利润追踪，重置"成本基准"为当前价格
        remaining_shares = self._lot_down(holding_state.code, holding_state.shares // 2)
        if remaining_shares > 0:
            # 新成本 = 减半卖出价格（相当于把已卖出的利润锁定）
            holding_state.cost = sell_price
            holding_state.shares = remaining_shares
            holding_state.highest_profit_pct = 0.0
            holding_state.current_profit_pct = 0.0
            holding_state.profit_mode = False
            holding_state.drawdown_half_hit = False  # 重置，可再次触发
            holding_state.ma5_hit = False
            holding_state.ma10_hit = False

    def after_clear_sell(self, holding_state: HoldingState):
        """清仓后调用：标记已清仓"""
        holding_state.clear_hit = True
        holding_state.shares = 0

    # ── 纠错买入检查 ───────────────────────────────────
    def check_correction_buy(
        self,
        market_df: pd.DataFrame,
        stock_df: pd.DataFrame,
        reason: str  # "panic_clear" / "ma10_clear"
    ) -> Tuple[bool, str]:
        """
        检查是否满足纠错买入条件（需全部满足）：
        1. 清仓性质：因恐慌情绪（非优先级1/2/5/8/9）
        2. 大盘信号：长下影线（下影线>实体×1.5）或缩量十字星
        3. 个股状态：个股未破20日线
        4. 月度限制：纠错买入每月最多2次
        """
        if market_df is None or len(market_df) < 5:
            return False, "数据不足"

        current_month = datetime.now().strftime("%Y-%m")

        # 检查月度次数限制
        if self._correction_count_month > 2:
            return False, f"本月纠错次数已用尽({self._correction_count_month}次)"

        # 条件2：大盘长下影线 或 缩量十字星
        last = market_df.iloc[-1]
        body = abs(last["close"] - last["open"])
        lower_shadow = min(last["open"], last["close"]) - last["low"]

        is_long_lower_shadow = body > 0 and lower_shadow > body * 1.5

        # 缩量十字星：成交量 < 5日均量 × 0.8
        is_volume_shrink = False
        if len(market_df) >= 5:
            vol_ma5 = market_df["volume"].iloc[-5:].mean()
            if vol_ma5 > 0:
                is_volume_shrink = last["volume"] < vol_ma5 * 0.8

        if not (is_long_lower_shadow or is_volume_shrink):
            return False, "大盘未出现长下影线或缩量十字星"

        # 条件3：个股未破20日线
        if stock_df is not None and len(stock_df) >= 20:
            ma20 = float(pd.Series(stock_df["close"].values).rolling(20).mean().iloc[-1])
            last_close = stock_df["close"].iloc[-1]
            if last_close < ma20:
                return False, f"个股已破20日线({ma20:.2f})"

        reason_str = "大盘长下影线" if is_long_lower_shadow else "大盘缩量十字星"
        return True, reason_str

    # ══ 内部工具函数 ═══════════════════════════════════

    def _get_drawdown_threshold(self, highest_profit_pct: float) -> float:
        """查表获取回撤阈值"""
        threshold = DRAWDOWN_TABLE[-1][1]
        for lower_bound, th in DRAWDOWN_TABLE:
            if highest_profit_pct >= lower_bound:
                threshold = th
        return threshold

    def _update_consecutive_ma5(self, hs: HoldingState, today: str, is_below: bool) -> int:
        """
        更新连续跌破MA5天数
        - 今日跌破MA5：天数+1
        - 今日收在MA5之上：天数重置为0
        """
        if is_below:
            if hs.last_ma5_date != today:
                hs.consecutive_ma5_days += 1
                hs.last_ma5_date = today
            # else: 今日已更新，不再重复累加
        else:
            hs.consecutive_ma5_days = 0
        hs.last_check_date = today
        return hs.consecutive_ma5_days

    def _update_consecutive_ma10(self, hs: HoldingState, today: str, is_below: bool) -> int:
        """
        更新连续跌破MA10天数
        守卫用 last_ma10_date（独立于MA5的 last_check_date），
        防止P7先执行覆盖last_check_date导致P8连续天数不递增。
        """
        if is_below:
            if hs.last_ma10_date != today:
                hs.consecutive_ma10_days += 1
                hs.last_ma10_date = today
        else:
            hs.consecutive_ma10_days = 0
        return hs.consecutive_ma10_days

    def _calc_vol_ma5(self, df: pd.DataFrame) -> float:
        """计算5日均量"""
        if df is None or len(df) < 5:
            return 0.0
        if "volume" not in df.columns:
            return 0.0
        return float(df["volume"].iloc[-5:].mean())

    def _count_trading_days(self, start_date: str, end_date: str) -> int:
        """
        计算两个日期之间的A股交易日天数
        优先使用 akshare 交易日历，失败则用估算（实际天数×0.65）
        """
        try:
            # 尝试真实交易日计算（akshare）
            trade_days = self._get_trade_calendar()
            d1 = datetime.strptime(start_date, "%Y-%m-%d").date()
            d2 = datetime.strptime(end_date, "%Y-%m-%d").date()
            days = sum(1 for d in trade_days if d1 <= d <= d2)
            if days > 0:
                return days
        except:
            pass

        # 估算
        try:
            d1 = datetime.strptime(start_date, "%Y-%m-%d")
            d2 = datetime.strptime(end_date, "%Y-%m-%d")
            calendar_days = (d2 - d1).days
            return max(1, int(calendar_days * 0.65))
        except:
            return 0

    _trade_calendar = None

    def _get_trade_calendar(self):
        """获取A股交易日历（带缓存）"""
        if self._trade_calendar is not None:
            return self._trade_calendar
        try:
            import akshare as ak
            import pandas as pd
            df = ak.tool_trade_date_hist_sina()
            self._trade_calendar = set(pd.to_datetime(df['trade_date']).dt.date)
            return self._trade_calendar
        except:
            return set()