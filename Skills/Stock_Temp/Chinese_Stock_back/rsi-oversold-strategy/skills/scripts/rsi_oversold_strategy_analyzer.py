#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RSI超卖反弹分析器
识别和分析RSI超卖后的技术性反弹机会
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

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
    """市场环境评估（与ma-bullish-strategy一致）"""
    
    def __init__(self):
        self.index_data = {}
        self.zt_count = 0
        self._load()
    
    def _load(self):
        """加载市场环境数据"""
        try:
            import akshare as ak
            today = datetime.now().strftime('%Y%m%d')
            
            try:
                zt_df = ak.stock_zt_pool_em(date=today)
                self.zt_count = len(zt_df) if zt_df is not None and not zt_df.empty else 0
            except:
                self.zt_count = 0
            
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
        """市场环境综合评分 (0-100)"""
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
    

class RSIOversoldAnalyzer:
    """RSI超卖反弹分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "RSI超卖反弹策略"
        self.version = "v2.0.0"
        self.win_rate = 0.58
        
        # RSI参数
        self.rsi_period = 14
        self.oversold_level = 30
        self.overbought_level = 70
        
        # 评分权重
        self.weights = {
            'rsi_oversold': 0.25,
            'price_recovery': 0.20,
            'volume_confirm': 0.20,
            'trend_reversal': 0.15,
            'market_environment': 0.20
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
        
        self.market_env = MarketEnvironment()

    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from rsi_oversold_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from rsi_oversold_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)



    def calculate_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算RSI指标"""
        df = df.copy()
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi'] = df['rsi'].fillna(50)
        
        return df

    def find_oversold(self, df: pd.DataFrame, lookback: int = 60) -> List[Dict]:
        """查找RSI超卖信号（假设RSI已计算）"""
        if len(df) < 20 or 'rsi' not in df.columns:
            return []
        
        oversold_signals = []
        
        for i in range(self.rsi_period, len(df)):
            rsi = df.iloc[i]['rsi']
            
            # 检查是否超卖
            if rsi < self.oversold_level:
                # 检查之前是否处于正常或超买状态
                prev_rsi = df['rsi'].iloc[max(0, i-10):i].mean()
                
                if prev_rsi > self.oversold_level:
                    # 确认从高位进入超卖区域
                    oversold_signals.append({
                        'index': i,
                        'date': df.index[i] if hasattr(df.index[i], 'strftime') else str(df.index[i]),
                        'rsi': rsi,
                        'price': df.iloc[i]['close'],
                        'prev_rsi': prev_rsi
                    })
        
        return oversold_signals

    def analyze_recovery(self, df: pd.DataFrame, signal_idx: int) -> Dict:
        """分析反弹情况"""
        if signal_idx >= len(df) - 1:
            return {'has_recovery': False, 'price_change': 0, 'rsi_recovery': 0, 'days_since': 999}
        
        recovery_window = df.iloc[signal_idx:min(signal_idx+5, len(df))]
        
        # 计算价格变化
        price_start = df.iloc[signal_idx]['close']
        price_end = recovery_window.iloc[-1]['close']
        price_change = (price_end - price_start) / price_start * 100
        
        # RSI恢复程度
        rsi_start = df.iloc[signal_idx]['rsi']
        rsi_end = recovery_window.iloc[-1]['rsi']
        rsi_recovery = rsi_end - rsi_start
        
        # 距超卖天数
        days_since = len(df) - 1 - signal_idx
        
        has_recovery = rsi_recovery > 10 and price_change > 0
        
        return {
            'has_recovery': has_recovery,
            'price_change': price_change,
            'rsi_recovery': rsi_recovery,
            'days_since': days_since
        }

    def calculate_score(self, df: pd.DataFrame, signal: Dict, recovery: Dict) -> Tuple[float, str, Dict]:
        """计算评分，返回(总分, 原因, 分项得分)"""
        reasons = []
        details = {}
        
        # 1. RSI综合得分 (0-100)
        # 双重参考：信号时RSI超卖深度 + 当前RSI（当前RSI 30-50是最佳区间）
        sig_rsi = signal['rsi']
        curr_rsi = df.iloc[-1]['rsi']
        
        # 信号时RSI评分
        if sig_rsi < 15:
            sig_score = 100
        elif sig_rsi < 20:
            sig_score = 90
        elif sig_rsi < 25:
            sig_score = 75
        elif sig_rsi < 30:
            sig_score = 60
        else:
            sig_score = max(0, 60 - (sig_rsi - 30) * 3)
        
        # 当前RSI评分（30-50最佳，过高过低都扣分）
        if 30 <= curr_rsi <= 50:
            curr_score = 100
            reasons.append("当前RSI处于最佳区间(30-50)")
        elif curr_rsi < 30:
            curr_score = 80
            reasons.append("当前RSI仍偏弱")
        elif curr_rsi <= 60:
            curr_score = 70
            reasons.append("当前RSI偏中性")
        elif curr_rsi <= 70:
            curr_score = 50
            reasons.append("当前RSI偏高")
        else:
            curr_score = max(0, 50 - (curr_rsi - 70) * 2)
            reasons.append("当前RSI偏高(警惕)")
        
        # 信号时RSI权重60%，当前RSI权重40%
        r_score = sig_score * 0.6 + curr_score * 0.4
        details['rsi'] = round(r_score, 1)
        details['current_rsi_score'] = curr_score
        
        # 2. 反弹强度得分 (0-100)
        days_since = recovery.get('days_since', 999)
        if recovery['has_recovery']:
            p_score = 100
            reasons.append("已出现明显反弹")
        elif recovery['price_change'] > 3:
            p_score = 75
            reasons.append("价格开始回升")
        elif recovery['price_change'] > 0:
            p_score = 50
            reasons.append("价格企稳")
        else:
            p_score = 20
            reasons.append("价格尚未反弹")
        details['price_recovery'] = p_score
        details['days_since'] = days_since
        
        # 3. 量能确认得分 (0-100)
        vol_score = 50
        if signal['index'] < len(df) - 1:
            vol_ratio = df.iloc[signal['index'] + 1]['volume'] / df.iloc[signal['index']]['volume'] if df.iloc[signal['index']]['volume'] > 0 else 1
            if vol_ratio > 1.5:
                vol_score = 100
                reasons.append("成交量大幅放大")
            elif vol_ratio > 1.2:
                vol_score = 75
                reasons.append("成交量温和放大")
            elif vol_ratio > 1.0:
                vol_score = 55
                reasons.append("成交量有所放大")
            else:
                vol_score = 30
                reasons.append("成交量萎缩")
        details['volume'] = vol_score
        
        # 4. 趋势反转确认 (0-100)
        t_score = 50
        if signal['index'] >= 3:
            recent_prices = df['close'].iloc[signal['index']-3:signal['index']].values
            current_price = df.iloc[signal['index']]['close']
            if all(current_price > p for p in recent_prices):
                t_score = 100
                reasons.append("价格连涨，确认反转")
            elif current_price > recent_prices[-1]:
                t_score = 65
                reasons.append("价格有所反弹")
            else:
                t_score = 30
                reasons.append("价格仍在下跌")
        details['trend_reversal'] = t_score
        
        # 5. 市场环境得分 (0-100)
        mkt_score = self.market_env.get_market_score()
        details['market_environment'] = round(mkt_score, 1)
        
        # 加权综合
        total = (r_score * self.weights['rsi_oversold'] +
                 p_score * self.weights['price_recovery'] +
                 vol_score * self.weights['volume_confirm'] +
                 t_score * self.weights['trend_reversal'] +
                 mkt_score * self.weights['market_environment'])
        
        return round(total, 2), "; ".join(reasons), details

    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """分析单只股票"""
        try:
            df = self.data_adapter.get_stock_data(stock_code)
            if df is None or len(df) < 30:
                return None
            
            # 计算RSI
            df = self.calculate_rsi(df)
            signals = self.find_oversold(df)  # 这里find_oversold会再算一次RSI，但data已经有了
            
            if not signals:
                return None
            
            signal = signals[-1]
            recovery = self.analyze_recovery(df, signal['index'])
            
            score, reasons, score_details = self.calculate_score(df, signal, recovery)
            
            current = df.iloc[-1]
            prev = df.iloc[-2]
            
            # RSI状态描述
            rsi_val = current['rsi']
            if rsi_val < 20:
                rsi_status = '严重超卖'
            elif rsi_val < 30:
                rsi_status = '超卖'
            elif rsi_val < 40:
                rsi_status = '偏弱'
            else:
                rsi_status = '正常'
            
            # 计算RSI超卖时的价格偏离MA20
            sig_idx = signal['index']
            if sig_idx >= 20:
                ma20_at_signal = df['close'].iloc[sig_idx-20:sig_idx].mean()
                price_dev = (signal['price'] - ma20_at_signal) / ma20_at_signal * 100
            else:
                price_dev = 0
            
            # 量能变化
            vol_now = float(current['volume'])
            vol_prev = float(prev['volume'])
            vol_change = (vol_now - vol_prev) / vol_prev * 100 if vol_prev > 0 else 0
            
            # 止跌信号
            body = abs(float(current['close']) - float(current['open']))
            upper = float(current['high']) - max(float(current['close']), float(current['open']))
            lower = min(float(current['close']), float(current['open'])) - float(current['low'])
            full = float(current['high']) - float(current['low'])
            if lower > body * 2 and upper < body * 0.5:
                stability = '锤子线（止跌）'
            elif body < full * 0.1:
                stability = '十字星（观望）'
            elif float(current['close']) > float(current['open']) and body < full * 0.3:
                stability = '小阳线（企稳）'
            else:
                stability = '无明显信号'
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'signal': '曾RSI超卖' if score >= 70 else '曾RSI超卖(关注)',
                'score': score,
                'current_price': round(float(current['close']), 2),
                'price_change_pct': round((float(current['close']) - float(prev['close'])) / float(prev['close']) * 100, 2),
                'current_rsi': round(rsi_val, 2),
                'rsi_status': rsi_status,
                'price_deviation': round(abs(price_dev), 1),
                'volume_shrink': round(vol_change, 1),
                'stability_signal': stability,
                'reasons': reasons,
                'score_details': score_details,
                'market_summary': self.market_env.get_summary(),
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
    analyzer = RSIOversoldAnalyzer()
    
    test_stocks = [('平安银行', '000001'), ('万科A', '000002')]
    
    print("RSI超卖策略测试")
    print("-" * 60)
    
    for name, code in test_stocks:
        result = analyzer.analyze_stock(code, name)
        if result:
            print(f"{name}({code}): 评分={result['score']}, RSI={result['current_rsi']}")
        else:
            print(f"{name}({code}): 未发现超卖信号")
