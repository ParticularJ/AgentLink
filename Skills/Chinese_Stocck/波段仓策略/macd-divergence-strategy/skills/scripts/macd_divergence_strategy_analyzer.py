#!/usr/bin/env python3
"""
MACD底背离策略分析器
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import yaml

# 导入数据源适配器
try:
    from data_source_adapter import DataSourceAdapter
except ImportError:
    # 尝试从 ma-bullish-strategy 导入共享的数据源适配器
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../ma-bullish-strategy/skills/scripts')
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        # 备选：从项目根目录相对导入
        sys.path.insert(0, os.path.join(os.getcwd(), 'ma-bullish-strategy/skills/scripts'))
        from data_source_adapter import DataSourceAdapter


class MarketEnvironment:
    """市场环境评估（大盘/科创板/创业板等涨跌、涨停家数、成交量）"""
    
    def __init__(self):
        self.index_data = {}
        self.zt_count = 0
        self._load()
    
    def _load(self):
        """加载市场环境数据"""
        try:
            import akshare as ak
            today = datetime.now().strftime('%Y%m%d')
            
            # 获取今日涨停股数量
            try:
                zt_df = ak.stock_zt_pool_em(date=today)
                self.zt_count = len(zt_df) if zt_df is not None and not zt_df.empty else 0
            except:
                self.zt_count = 0
            
            # 获取主要指数数据
            index_codes = [
                ('sh000300', '沪深300'),
                ('sh000001', '上证指数'),
                ('sh000688', '科创50'),
                ('sz399001', '深证成指'),
                ('sz399006', '创业板指'),
            ]
            
            end = datetime.now().strftime('%Y%m%d')
            start = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
            
            for code, name in index_codes:
                try:
                    df = ak.stock_zh_index_daily(symbol=code)
                    if df is not None and not df.empty:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df[(df['date'] >= start) & (df['date'] <= end)]
                        if not df.empty:
                            self.index_data[name] = df.tail(5)
                    time.sleep(0.1)
                except:
                    pass
                    
        except Exception as e:
            print(f"[市场环境] 加载失败: {e}")
    
    def get_market_score(self) -> float:
        """
        市场环境综合评分 (0-100)
        50分为中性，>60偏牛，<40偏弱
        维度：指数涨跌(35分) + 涨停家数(35分) + 市场广度(30分)
        """
        if not self.index_data:
            return 50
        
        best_changes = []
        for name, df in self.index_data.items():
            if len(df) < 2 or 'close' not in df.columns:
                continue
            latest_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-2]
            if prev_close > 0:
                change = (latest_close - prev_close) / prev_close * 100
                best_changes.append(change)
        
        if not best_changes:
            return 50
        
        # 1. 指数涨跌 (0-35分) — 看最强指数
        best_change = max(best_changes)
        if best_change >= 3.0:   idx = 35
        elif best_change >= 2.0: idx = 32
        elif best_change >= 1.5:  idx = 28
        elif best_change >= 1.0:  idx = 25
        elif best_change >= 0.5:  idx = 21
        elif best_change >= 0.2:  idx = 17
        elif best_change >= 0:    idx = 13
        elif best_change >= -0.5: idx = 8
        else:                     idx = 4
        
        # 2. 涨停家数 (0-35分)
        zt = self.zt_count
        if zt >= 200:   z = 35
        elif zt >= 150: z = 32
        elif zt >= 100: z = 28
        elif zt >= 80:  z = 25
        elif zt >= 60:  z = 21
        elif zt >= 40:  z = 16
        elif zt >= 20:  z = 11
        elif zt >= 10:  z = 6
        else:           z = 2
        
        # 3. 市场广度 (0-30分) — 看上涨指数占比和均值
        avg_change = sum(best_changes) / len(best_changes)
        up_count = sum(1 for c in best_changes if c > 0)
        breadth = up_count / len(best_changes) * 100
        
        if avg_change >= 1.0 and breadth >= 80:  b = 30
        elif avg_change >= 0.6 and breadth >= 60: b = 26
        elif avg_change >= 0.3 and breadth >= 50: b = 22
        elif avg_change >= 0.1 and breadth >= 50: b = 18
        elif avg_change >= 0 and breadth >= 40:   b = 14
        elif avg_change >= -0.3:                   b = 9
        else:                                     b = 4
        
        # 加权计算
        final = (35 + idx * 0.35 + z * 0.35 + b * 0.30)
        
        return round(min(max(final, 10), 85), 1)
    
    def get_summary(self) -> Dict:
        """获取市场环境摘要"""
        summary = {'涨停家数': self.zt_count, '总分': 50}
        
        index_gains = []
        for name, df in self.index_data.items():
            if 'close' in df.columns and len(df) >= 2:
                gain = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
                index_gains.append((name, round(gain, 2)))
        
        summary['指数涨跌'] = index_gains
        summary['总分'] = self.get_market_score()
        return summary


class MACDDivergenceAnalyzer:
    """MACD底背离分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "MACD底背离策略"
        self.version = "v2.0.0"
        self.win_rate = 0.58
        
        # MACD参数
        self.fast_ema = 12
        self.slow_ema = 26
        self.signal_ema = 9
        
        # 评分权重
        self.weights = {
            'divergence_strength': 0.25,
            'macd_golden_cross': 0.20,
            'volume_confirm': 0.20,
            'price_stability': 0.15,
            'market_environment': 0.20
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter()
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
     	 # 全局市场环境（只加载一次）
        self.market_env = MarketEnvironment()


    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from macd_divergence_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from macd_divergence_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)
    

    
    def _calculate_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算MACD指标"""
        df = df.copy()
        
        # 计算EMA
        df['ema_fast'] = df['close'].ewm(span=self.fast_ema, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow_ema, adjust=False).mean()
        
        # MACD线
        df['macd'] = df['ema_fast'] - df['ema_slow']
        
        # 信号线
        df['signal'] = df['macd'].ewm(span=self.signal_ema, adjust=False).mean()
        
        # MACD柱状图
        df['histogram'] = df['macd'] - df['signal']
        
        return df

    def find_divergence(self, df: pd.DataFrame, lookback: int = 35) -> List[Dict]:
        """MACD底背离 适配35根短线K线 稳定版"""
        # MACD(12,26,9) 最少需要26根
        if len(df) < 28:
            return []
        
        df = self._calculate_macd(df)
        divergences = []
        
        # 遍历起点前置，避免前期数据不足
        start_idx = 15
        compare_window = 22    # 背离对比窗口
        local_window = 15      # 局部高低点窗口
        #print(len(df))
        for i in range(start_idx, len(df)):
            # 局部价格低点
            price_win = df['low'].iloc[max(0, i - local_window): i+1]
            price_low_idx = price_win.idxmin()
           # print("price_low_idx: ", price_low_idx)
            price_low = df.loc[price_low_idx, 'low']

            # 局部MACD低点
            macd_win = df['macd'].iloc[max(0, i - local_window): i+1]
            macd_low_idx = macd_win.idxmin()
            macd_low = df.loc[macd_low_idx, 'macd']
           # print("检查日期: ", df.index[i], "价格低点: ", price_low, "MACD低点: ", macd_low)
            # 当前价格创阶段新低
            if price_low_idx == i:
                # 取对比窗口内的数据
                start_j = max(0, i - compare_window)
                prev_window = df.iloc[start_j:i]
                
                # ===================== 修复 2 =====================
                # 找到对比区间内的“价格低点”对应的 MACD，而不是直接取 min(macd)
                # 这是解决假背离的核心！
                prev_low_idx = prev_window['low'].idxmin()
                prev_low_price = prev_window.loc[prev_low_idx, 'low']
                prev_low_macd = prev_window.loc[prev_low_idx, 'macd']

                # 真正的底背离：
                # 现在价格更低 + 现在MACD更高（比前一个低点高）
                price_div = price_low < prev_low_price
                macd_div = macd_low > prev_low_macd

                # 价格新低 + MACD不新低 = 标准底背离
                if price_div and macd_div and macd_low < 0:

                        # 新增：判定二次底背离
                    is_double_div = False
                    # 区间足够且MACD逐波抬高，构成二次背离
                    if i > 25:
                        macd_early = df['macd'].iloc[i-20]
                        macd_mid = df['macd'].iloc[i-10]
                        if macd_early < macd_mid < macd_low:
                            is_double_div = True
                    
                     # ✅ 强度计算修复（使用正确的前低MACD）
                    if prev_low_macd == 0:
                        strength = 0
                    else:
                        strength = (macd_low - prev_low_macd) / abs(prev_low_macd)
                    divergences.append({
                        'index': i,
                        'date': df.index[i] if hasattr(df.index[i], 'strftime') else str(df.index[i]),
                        'price_low': price_low,
                        'macd_low': macd_low,
                        'current_price': df.iloc[i]['close'],
                        'current_macd': df.iloc[i]['macd'],
                        'divergence_strength': round(strength, 4),
                        'is_double_divergence': is_double_div,  # 新增标记字段
                        'prev_price_low': prev_low_price,   # 正确前低价格
                        'prev_macd_low': prev_low_macd       # 正确前低MACD
                    })
        
        return divergences

    def check_golden_cross(self, df: pd.DataFrame, divergence_idx: int) -> bool:
        if divergence_idx < 3:
            return False
        
        # 只要 MACD 拐头向上 或 接近金叉 都算有效
        current = df.iloc[divergence_idx]
        prev1 = df.iloc[divergence_idx - 1]
        prev2 = df.iloc[divergence_idx - 2] if divergence_idx >=2 else prev1

        # 金叉 OR 拐头向上（更实战）
        golden_cross = current['macd'] > current['signal'] and prev1['macd'] <= prev1['signal']
        macd_turn_up = current['macd'] > prev1['macd'] > prev2['macd'] and current['macd'] < -0.005
        
        return golden_cross or macd_turn_up

    def analyze_volume(self, df: pd.DataFrame, divergence_idx: int) -> float:
        """分析成交量确认信号"""
        if divergence_idx < 5:
            return 0
        
        # 检查背离后的成交量是否放大
        vol_window = df['volume'].iloc[divergence_idx-2:divergence_idx+1]
        vol_ma = df['volume'].rolling(window=20).mean().iloc[divergence_idx]
        
        if vol_ma > 0:
            avg_vol = vol_window.mean()
            return min(avg_vol / vol_ma, 2.0)  # 最多2倍
        return 0

    def calculate_score(self, df: pd.DataFrame, divergence: Dict) -> Tuple[float, str, Dict]:
        """计算评分，返回(总分, 原因, 分项得分)"""
        reasons = []
        details = {}
        
        # 1. 背离强度得分 (0-100)
        strength = divergence.get('divergence_strength', 0)
        is_double = divergence.get('is_double_divergence', False)
        if strength > 0.5:
            d_score = 100
            reasons.append("底背离信号强烈")
        elif strength > 0.3:
            d_score = 85
            reasons.append("底背离信号明显")
        elif strength > 0.1:
            d_score = 65
            reasons.append("存在底背离迹象")
        else:
            d_score = 40
            reasons.append("背离信号较弱")
        # 二次背离额外加分
        if is_double:
            d_score += 15
            d_score = min(d_score, 100)
            reasons.append("判定为二次底背离，可靠性更高")
        details['divergence'] = d_score
        
        # 2. 金叉确认得分 (0-100)
        has_gc = self.check_golden_cross(df, divergence['index'])
        gc_score = 100 if has_gc else 40
        if has_gc:
            reasons.append("MACD形成金叉确认")
        else:
            reasons.append("等待金叉确认")
        details['golden_cross'] = gc_score
        
        # 3. 量能确认得分 (0-100)
        vol_ratio = self.analyze_volume(df, divergence['index'])
        if vol_ratio > 1.5:
            v_score = 100
            reasons.append("成交量明显放大配合")
        elif vol_ratio > 1.2:
            v_score = 75
            reasons.append("成交量温和放大")
        elif vol_ratio > 1.0:
            v_score = 55
            reasons.append("量能有所恢复")
        else:
            v_score = 30
            reasons.append("量能不足")
        details['volume'] = v_score
        
        # 4. 价格稳定得分 (0-100)
        if divergence['index'] >= 5:
            price_std = df['close'].iloc[divergence['index']-5:divergence['index']].std()
            price_mean = df['close'].iloc[divergence['index']-5:divergence['index']].mean()
            cv = price_std / price_mean if price_mean > 0 else 1
            
            if cv < 0.02:
                p_score = 100
                reasons.append("价格极度稳定")
            elif cv < 0.05:
                p_score = 80
                reasons.append("价格相对稳定")
            elif cv < 0.1:
                p_score = 60
                reasons.append("价格波动适中")
            else:
                p_score = 35
                reasons.append("价格波动较大")
        else:
            p_score = 55
        details['price_stability'] = p_score
        
        # 5. 市场环境得分 (0-100)
        market_score = self.market_env.get_market_score()
        details['market_environment'] = round(market_score, 1)
        
        # 综合评分：各维度等权平均（满分100）
        total = (d_score * self.weights['divergence_strength'] +
                 gc_score * self.weights['macd_golden_cross'] +
                 v_score * self.weights['volume_confirm'] +
                 p_score * self.weights['price_stability'] +
                 market_score * self.weights['market_environment'])
        
        return round(total, 2), "; ".join(reasons), details

    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """分析单只股票"""
        try:
            # 获取数据
            df = self.data_adapter.get_stock_data(stock_code)
            if df is None or len(df) < 20:
                return None
            
           # print("df: ", df.tail())

            # 计算MACD指标（find_divergence内部也会算，这里提前算好供后续使用）
            df = self._calculate_macd(df)
            
            # 查找底背离
            divergences = self.find_divergence(df)
           #  print("divergences: ", divergences)
            if not divergences:
                return None
            
            # 取最近的底背离信号
            divergence = divergences[-1]
            div_idx = divergence['index']
            
            # 计算评分
            score, reasons, score_details = self.calculate_score(df, divergence)
            print(f"分析 {stock_name}({stock_code}): {score}分 - {reasons}")
            # 获取当前价格
            current = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 判断K线形态
            body = abs(current['close'] - current['open'])
            upper = current['high'] - max(current['close'], current['open'])
            lower = min(current['close'], current['open']) - current['low']
            full_range = current['high'] - current['low']
            
            if lower > body * 2 and upper < body * 0.5:
                candlestick = '锤子线'
            elif body < full_range * 0.1:
                candlestick = '十字星'
            elif current['close'] > current['open'] and body < full_range * 0.3:
                candlestick = '小阳线'
            elif current['close'] < current['open'] and body < full_range * 0.3:
                candlestick = '小阴线'
            else:
                candlestick = '中性K线'
            
            # 计算支撑位
            recent_lows = df['low'].iloc[max(0, div_idx-5):div_idx+1].min()
            support = round(recent_lows, 2)
            
            # 获取市场环境摘要
            market_summary = self.market_env.get_summary()
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'signal': 'MACD底背离买入' if score >= 75 else '关注',
                'score': score,
                'current_price': round(float(current['close']), 2),
                'prev_price': round(float(prev['close']), 2),
                'price_change_pct': round((float(current['close']) - float(prev['close'])) / float(prev['close']) * 100, 2),
                'current_macd': round(float(current['macd']), 4),
                'golden_cross': self.check_golden_cross(df, div_idx),
                'volume_increase': round(self.analyze_volume(df, div_idx) * 100, 1),
                'divergence_strength': round(divergence.get('divergence_strength', 0), 4),
                'price_low': round(divergence.get('price_low', 0), 2),
                'prev_price_low': round(divergence.get('prev_price_low', 0), 2),
                'macd_low': round(divergence.get('macd_low', 0), 4),
                'prev_macd_low': round(divergence.get('prev_macd_low', 0), 4),
                'candlestick': candlestick,
                'support_level': support,
                'reasons': reasons,
                'score_details': score_details,
                'market_summary': market_summary,
                'strategy': self.name
            }
            
        except Exception as e:
            return None

    def batch_analyze(self, stock_list: List[tuple], top_n: int = 10) -> List[Dict]:
        """批量分析"""
        results = []
        
        for name, code in stock_list:
            try:
                result = self.analyze_stock(code, name)
                if result and result['score'] > 0:
                    results.append(result)
            except Exception:
                continue
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_n]


if __name__ == '__main__':
    analyzer = MACDDivergenceAnalyzer()
    
    test_stocks = [
        ('平安银行', '000001'),
        ('万科A', '000002'),
    ]
    
    print("MACD底背离策略测试")
    print("-" * 60)
    
    for name, code in test_stocks:
        result = analyzer.analyze_stock(code, name)
        if result:
            print(f"{name}({code}): 评分={result['score']}, 原因={result['reasons']}")
        else:
            print(f"{name}({code}): 未发现底背离信号")
