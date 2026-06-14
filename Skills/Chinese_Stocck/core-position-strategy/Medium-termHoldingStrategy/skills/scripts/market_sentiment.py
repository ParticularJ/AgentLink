#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大盘情绪判定模块
基于沪深300指数，每日14:40判定收盘状态
"""
import os
import sys
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from enum import Enum
from typing import Tuple, Optional

# 清除代理
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try:
            del os.environ[k]
        except:
            pass


class MarketState(Enum):
    NORMAL = "正常"        # 收盘价在5日均线上方
    WEAK = "偏弱"           # 收盘价在5日线下方，未达恐慌区
    PANIC = "恐慌区"        # 5日线下且连续3天至少2天跌幅≥1.5%
    EXTREME_PANIC = "极端恐慌"  # 恐慌区且当日跌幅≥2%


class MarketSentiment:
    """大盘情绪判定器"""

    def __init__(self):
        self.index_code = "sh000001"  # 沪深300
        self._df_history: Optional[pd.DataFrame] = None
        self._state: Optional[MarketState] = None
        self._state_date: Optional[str] = None  # 缓存日期

    def fetch_index_kline(self, days: int = 120) -> Optional[pd.DataFrame]:
        """获取沪深300指数K线数据（东方财富）"""
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": "1.000001",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "lmt": str(days),
            "beg": "0",
            "end": "20500000",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "application/json, text/plain, */*",
        }

        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            data = r.json()
            if not data.get("data") or not data["data"].get("klines"):
                return None

            klines = data["data"]["klines"]
            records = []
            for line in klines:
                parts = line.split(",")
                if len(parts) < 6:
                    continue
                records.append({
                    "day": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                })

            df = pd.DataFrame(records)
            df["day"] = pd.to_datetime(df["day"])
            for col in ["open", "close", "high", "low"]:
                df[col] = df[col].astype(float)
            df["volume"] = df["volume"].astype(float)

            # 计算均线
            close = df["close"].values
            for n in [5, 10, 20, 60]:
                df[f"ma{n}"] = pd.Series(close).rolling(n).mean().values

            # 计算每日涨跌幅
            df["chg_pct"] = df["close"].pct_change() * 100

            return df

        except Exception as e:
            print(f"[大盘情绪] 获取K线失败: {e}")
            return None

    def get_market_state(self, date: str = None) -> Tuple[MarketState, pd.DataFrame]:
        """
        判定大盘状态（每日14:40调用一次即可，内部缓存）
        date: 可选，指定日期字符串 YYYY-MM-DD，默认今日
        """
        today = date or datetime.now().strftime("%Y-%m-%d")

        # 缓存：同一天不重复请求
        if self._state is not None and self._state_date == today:
            return self._state, self._df_history

        df = self.fetch_index_kline(120)
        if df is None or len(df) < 20:
            self._state = MarketState.WEAK
            self._state_date = today
            return self._state, df

        self._df_history = df

        closes = df["close"].values
        ma5_current = float(pd.Series(closes).rolling(5).mean().iloc[-1])
        current_price = closes[-1]
        current_chg = df["chg_pct"].iloc[-1] if not pd.isna(df["chg_pct"].iloc[-1]) else 0.0

        # === 1. 正常：收盘价在5日均线上方 ===
        if current_price > ma5_current:
            state = MarketState.NORMAL
        else:
            # === 2. 计算近3日跌幅情况 ===
            chg_series = df["chg_pct"].dropna().iloc[-3:]
            days_with_big_drop = sum(1 for c in chg_series if c <= -1.5)

            if current_price < ma5_current and days_with_big_drop >= 2:
                # === 3. 极端恐慌：恐慌区且当日跌幅≥2% ===
                if current_chg <= -2.0:
                    state = MarketState.EXTREME_PANIC
                else:
                    state = MarketState.PANIC
            else:
                state = MarketState.WEAK

        self._state = state
        self._state_date = today
        return state, df

    def is_sell_allowed(self, priority: int) -> bool:
        """
        根据大盘状态和止损优先级判断是否允许卖出
        priority: 止损优先级（1=绝对亏损清仓, 2=绝对亏损减半, 其他）
        """
        state = self._state or MarketState.NORMAL

        # 优先级1/2 绝对亏损规则：永远允许
        if priority in (1, 2):
            return True

        if state == MarketState.EXTREME_PANIC:
            return False  # 极端恐慌：禁止任何卖出
        if state == MarketState.PANIC:
            return True   # 恐慌区：允许减半（清仓需额外检查）

        return True

    def can_clear_position(self) -> bool:
        """恐慌区是否允许清仓"""
        state = self._state or MarketState.NORMAL
        return state not in (MarketState.PANIC, MarketState.EXTREME_PANIC)

    def can_reduce(self) -> bool:
        """是否允许减仓（恐慌区允许减半，但有下限）"""
        state = self._state or MarketState.NORMAL
        return state != MarketState.EXTREME_PANIC

    def get_drawdown_relax_factor(self) -> float:
        """
        获取回撤阈值放宽系数
        恐慌区/极端恐慌：放宽10个百分点（即减少10%的回撤容忍度）
        正常/偏弱：不放宽
        """
        state = self._state or MarketState.NORMAL
        if state in (MarketState.PANIC, MarketState.EXTREME_PANIC):
            return 0.10  # 放宽10个百分点
        return 0.0

    def get_state_description(self) -> str:
        state = self._state or MarketState.NORMAL
        desc = {
            MarketState.NORMAL: "✅ 正常",
            MarketState.WEAK: "⚠️ 偏弱",
            MarketState.PANIC: "🚨 恐慌区",
            MarketState.EXTREME_PANIC: "🔴 极端恐慌",
        }
        return desc.get(state, "未知")