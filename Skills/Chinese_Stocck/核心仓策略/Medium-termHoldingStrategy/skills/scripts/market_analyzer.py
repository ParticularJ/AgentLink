import pandas as pd
import numpy as np
from typing import Tuple

from config import POSITION_CONFIG, DATA_CONFIG
from models import MarketState, PositionAdvice

# ── 代理清除 + 加载数据源 ────────────────────────────────
import os
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try: del os.environ[k]
        except: pass

from data_source import get_index_realtime, fetch_kline_sina, get_market_stats


class MarketAnalyzer:
    """大盘行情分析器（使用腾讯+新浪数据源，替代 akshare）"""

    def __init__(self):
        self.index_data = None
        self.last_update = None

    def fetch_index_data(self) -> pd.DataFrame:
        """获取上证指数历史数据"""
        try:
            df = fetch_kline_sina('sh000001', 120)
            if df is None or df.empty:
                return None
            self.index_data = df
            self.last_update = pd.Timestamp.now()
            return self.index_data
        except Exception as e:
            print(f"获取指数数据失败: {e}")
            return None

    def calculate_macd(self, data: pd.Series, fast=12, slow=26, signal=9) -> Tuple[float, float, float]:
        """计算MACD指标"""
        ema_fast = data.ewm(span=fast, adjust=False).mean()
        ema_slow = data.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_hist = macd - macd_signal
        return float(macd.iloc[-1]), float(macd_signal.iloc[-1]), float(macd_hist.iloc[-1])

    def get_market_state(self) -> Tuple[MarketState, float]:
        """判断大盘状态和趋势系数"""
        if self.index_data is None or len(self.index_data) < 60:
            self.fetch_index_data()

        if self.index_data is None or len(self.index_data) < 60:
            return MarketState.RANGE_WEAK, POSITION_CONFIG["弱势震荡"]["trend_coef"]

        df = self.index_data
        closes = df['close'].values
        ma5 = float(pd.Series(closes).rolling(5).mean().iloc[-1])
        ma10 = float(pd.Series(closes).rolling(10).mean().iloc[-1])
        ma20 = float(pd.Series(closes).rolling(20).mean().iloc[-1])
        ma60 = float(pd.Series(closes).rolling(60).mean().iloc[-1])

        current_price = closes[-1]

        macd, macd_signal, macd_hist = self.calculate_macd(df['close'])

        # === 优化1：MA20 趋势判断更稳健（5日斜率）===
        ma20_5 = float(pd.Series(closes).rolling(20).mean().iloc[-6])
        ma20_slope = (ma20 - ma20_5) / (ma20_5 if ma20_5 != 0 else 1)
        if ma20_slope > 0.005:
            ma20_trend = "up"
        elif ma20_slope < -0.005:
            ma20_trend = "down"
        else:
            ma20_trend = "flat"

        vol_avg = float(df['volume'].rolling(20).mean().iloc[-1])
        current_vol = float(df['volume'].iloc[-1])
     
        # 系统性风险
        if current_price < ma60 and current_vol > vol_avg * 1.5:
            return MarketState.SYSTEM_RISK, POSITION_CONFIG["系统性风险"]["trend_coef"]

        # 下跌补充：连续两日跌破MA20
        close_prev = closes[-2]
        ma20_prev = float(pd.Series(closes).rolling(20).mean().iloc[-2])
        # 下跌趋势
        if (current_price < ma20 and close_prev < ma20_prev) and (macd_hist < 0 and macd < macd_signal):
            return MarketState.DOWN_TREND, POSITION_CONFIG["下跌趋势"]["trend_coef"]

        # === 震荡判断 ===
        # 优化2：均线粘合度更标准
        ma_spread = (abs(ma5 - ma10) + abs(ma10 - ma20)) / ma20
        if ma_spread < 0.015:  # 粘合
            return MarketState.RANGE_WEAK, POSITION_CONFIG["弱势震荡"]["trend_coef"]

        # 强势主升
        if current_price > ma20 and ma20_trend == "up" and macd_hist > 0 and macd > macd_signal:
            return MarketState.STRONG_UP, POSITION_CONFIG["强势主升"]["trend_coef"]

        # 震荡偏多
        if current_price > ma20*0.98 and current_price > ma10 and ma20_trend == "flat":
            return MarketState.RANGE_UP, POSITION_CONFIG["震荡偏多"]["trend_coef"]

        return MarketState.RANGE_WEAK, POSITION_CONFIG["弱势震荡"]["trend_coef"]

    def get_market_sentiment(self) ->  Tuple[float,str]:
        """获取市场情绪修正系数"""
        try:
            market_info = ""
            # 获取主要指数的实时变化
            idx = get_index_realtime()
            if not idx:
                return 0.0, "中性"  
            
            sh = idx.get('sh', {})
            sz = idx.get('sz', {})
            cy = idx.get('cy', {})

            avg_chg = 0.0
            count = 0
            for v in [sh, sz, cy]:
                if v and 'chg_pct' in v:
                    avg_chg += v['chg_pct']
                    count += 1

            if count > 0:
                avg_chg /= count
            
          #  print(f"市场情绪修正计算: 平均变化 {avg_chg:.2f}% ")
           


            # 获取涨停数量和跌停数量
            up_down = get_market_stats()

            up_down_sh = up_down.get('sh', {})
            up_down_sz = up_down.get('sz', {})
            up_down_cy = up_down.get('cy', {})

            # ── 涨跌家数 ─────────────────────────
            total_advance = sum([
                up_down_sh.get('advance', 0),
                up_down_sz.get('advance', 0),
                up_down_cy.get('advance', 0)
            ])
            total_decline = sum([
                up_down_sh.get('decline', 0),
                up_down_sz.get('decline', 0),
                up_down_cy.get('decline', 0)
            ])
            total_stocks = total_advance + total_decline
            up_ratio = total_advance / total_stocks if total_stocks > 0 else 0.5   
            total_limit_up = up_down.get('limit_up', 0) if up_down else 0
            total_limit_down = up_down.get('limit_down', 0) if up_down else 0         
            # print(f"涨跌家数: 上证 {up_down_sh.get('advance', 0)}/{up_down_sh.get('decline', 0)}, 深证 {up_down_sz.get('advance', 0)}/{up_down_sz.get('decline', 0)}, 创业板 {up_down_cy.get('advance', 0)}/{up_down_cy.get('decline', 0)}, 总体上涨率: {up_ratio:.2%}" )



            # ── 情绪乘数计算 ─────────────────────
            multiplier = 1.0
            breadth_mood = "中性"

            # ============ 第一层：市场宽度定性 ============
            if up_ratio >= 0.70:
                breadth_mood = "乐观"
            elif up_ratio >= 0.50:
                breadth_mood = "偏多"
            elif up_ratio >= 0.30:
                breadth_mood = "中性偏弱"
            elif up_ratio >= 0.15:
                breadth_mood = "悲观"
            else:
                breadth_mood = "恐慌"

            # ============ 第二层：宽度 × 涨跌幅 → 乘数 ============
            if breadth_mood == "乐观":
                if avg_chg > 1.5:
                    multiplier = 1.10
                elif avg_chg > 0.3:
                    multiplier = 1.05
                else:
                    multiplier = 1.0

            elif breadth_mood == "偏多":
                if avg_chg > 1.0:
                    multiplier = 1.08
                elif avg_chg > 0.3:
                    multiplier = 1.03
                elif avg_chg > -0.5:
                    multiplier = 0.98
                else:
                    multiplier = 0.95

            elif breadth_mood == "中性偏弱":
                if avg_chg > 0.5:
                    multiplier = 1.00    # 指数涨但个股弱，保持中性警惕
                elif avg_chg > -0.5:
                    multiplier = 0.95
                elif avg_chg > -1.5:
                    multiplier = 0.90
                else:
                    multiplier = 0.85

            elif breadth_mood == "悲观":
                if avg_chg > -0.5:
                    multiplier = 0.90    # 护盘型微跌但大面积普跌
                elif avg_chg > -1.0:
                    multiplier = 0.85
                elif avg_chg > -2.0:
                    multiplier = 0.80
                else:
                    multiplier = 0.75

            elif breadth_mood == "恐慌":
                multiplier = 0.70         # 极端普跌，强力降仓
            else:
                multiplier = 0.75

            # ============ 第三层：涨跌停极端修正 ============
            if total_limit_down > 50:
                multiplier = min(multiplier, 0.70)
            elif total_limit_down > 20:
                multiplier = min(multiplier, 0.80)

            if total_limit_up > 100 and up_ratio > 0.6:
                multiplier = max(multiplier, 1.05)

            # ============ 第四层：边界保护 ============
            multiplier = max(0.50, min(1.20, multiplier))

            # # ── 日志 ────────────────────────────
            # print(f"\n{'='*50}")
            # print(f"📊 市场情绪诊断")

            # print(f"上证指数变化: {sh.get('chg_pct', 0):.2f}%, 深证成指变化: {sz.get('chg_pct', 0):.2f}%, 创业板指变化: {cy.get('chg_pct', 0):.2f}%, 平均变化: {avg_chg:.2f}%")
            # print(f"  上涨: {total_advance}  下跌: {total_decline}  上涨占比: {up_ratio:.1%}")
            # print(f"  涨停: {total_limit_up}  跌停: {total_limit_down}")
            # print(f"  宽度定性: {breadth_mood}")
            # print(f"  情绪乘数: {multiplier:.2f}")
            # print(f"{'='*50}\n")
           # market_info += f"上证指数变化: {sh.get('chg_pct', 0):.2f}%, 深证成指变化: {sz.get('chg_pct', 0):.2f}%, 创业板指变化: {cy.get('chg_pct', 0):.2f}%, 平均变化: {avg_chg:.2f}%\n大盘上涨占比： {up_ratio:.1%}\n市场情绪： {breadth_mood}"
            market_info += f"上证指数变化: {sh.get('chg_pct', 0):.2f}%, 深证成指变化: {sz.get('chg_pct', 0):.2f}%, 创业板指变化: {cy.get('chg_pct', 0):.2f}%\n 平均变化: {avg_chg:.2f}%\n"

            return multiplier, market_info
        except Exception as e:
            print(f"获取市场情绪失败: {e}")
            return 0.0, "获取失败"

    def calculate_position_limit(self) -> PositionAdvice:
        """计算最高仓位建议"""
        market_state, trend_coef = self.get_market_state()
        #print(f"大盘状态: {market_state.value}, 趋势系数: {trend_coef:.2f}")
        sentiment_correction, market_info = self.get_market_sentiment()
        print(  f"市场情绪修正: {sentiment_correction:.2f}")
        config = POSITION_CONFIG[market_state.value]
        base_position = config["base_position"]
        max_position = config["max_position"]

        suggested = base_position * trend_coef * sentiment_correction
       # 趋势底线：防止情绪过度打压强势市场
        if trend_coef >= 0.8:
            suggested = max(suggested, 0.40)
        elif trend_coef >= 0.5:
            suggested = max(suggested, 0.20)

        suggested = min(suggested, max_position)
        suggested = max(suggested, 0.0)  # 下跌趋势可空仓

        return PositionAdvice(
            market_state=market_state,
            suggested_position=suggested,
            current_position=0,
            available_position=0,
            trend_coef=trend_coef,
            #reason=f" \n趋势系数(0-1):{trend_coef:.2f}\n情绪修正(0.7-1.1):{sentiment_correction:.2f}\n详情: {market_info}"
            reason=f" \n详情: {market_info}"

        )
