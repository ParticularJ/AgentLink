#!/usr/bin/env python3
"""
缩量回踩重要均线策略分析器
"""

import sys
import os
# sys.path.insert(0, os.path.dirname(__file__))

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


class VolumeRetraceAnalyzer:
    """缩量回踩均线分析器"""
    
    # 评分权重配置（参考涨停板策略标准）
    WEIGHTS = {
        'retrace_quality': 0.25,     # 回踩质量 (25%)
        'volume_shrink': 0.20,       # 缩量程度 (20%)
        'trend_strength': 0.20,      # 趋势强度 (20%)
        'stop_signal': 0.15,         # 止跌信号 (15%)
        'support_strength': 0.15,    # 支撑强度 (15%)
        'market_environment': 0.05,  # 市场环境 (5%)
    }
    
    # 评分阈值（与涨停板策略一致）
    THRESHOLDS = {
        'strong_buy': 85,    # 极高
        'buy': 75,           # 高
        'watch': 65,         # 中等
        'exclude': 55        # 低
    }
    
    def __init__(self, data_source: str = "auto"):
        self.name = "缩量回踩均线策略"
        self.version = "v1.1.0"
        self.win_rate = 0.62
        
        # 均线参数
        self.ma_periods = [5, 10, 20, 60]
        self.volume_ma_period = 20
        self.volume_shrink_ratio = 0.5  # 缩量标准：低于均量50%
        
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
        
        # 缓存市场情绪
        self._market_sentiment = None
    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from retrace_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from retrace_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)

    def calculate_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算均线"""
        df = df.copy()
        
        for period in self.ma_periods:
            df[f'ma{period}'] = df['close'].rolling(window=period, min_periods=1).mean()
        
        return df

    def calculate_volume_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算成交量均线"""
        df = df.copy()
        df['volume_ma'] = df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        return df

    def find_retrace_signals(self, df: pd.DataFrame, lookback: int = 60) -> List[Dict]:
        """查找缩量回踩均线信号"""
        if len(df) < 30:
            return []
        
        df = self.calculate_ma(df)
        df = self.calculate_volume_ma(df)
        
        signals = []
        
        for i in range(20, len(df)):
            current = df.iloc[i]
            
            # 检查是否回踩均线
            for period in [10, 20]:
                ma_col = f'ma{period}'
                if ma_col not in current.index or pd.isna(current[ma_col]):
                    continue
                
                ma_value = current[ma_col]
                price = current['close']
                
                # 价格回踩均线（下影线触及或接近均线）
                retrace_ratio = abs(price - ma_value) / ma_value
                
                if retrace_ratio < 0.02:  # 价格在均线2%以内
                    # 检查成交量是否萎缩
                    volume_ratio = current['volume_ratio']
                    
                    if volume_ratio < self.volume_shrink_ratio:
                        # 确认是缩量回踩
                        # 检查之前是否是上涨趋势
                        prev_closes = df['close'].iloc[max(0, i-10):i]
                        ma_alignment = all(prev_closes > df[f'ma{period}'].iloc[max(0, i-10):i])
                        
                        signals.append({
                            'index': i,
                            'date': df.index[i] if hasattr(df.index[i], 'strftime') else str(df.index[i]),
                            'price': price,
                            'ma_value': ma_value,
                            'ma_period': period,
                            'volume_ratio': volume_ratio,
                            'trend_aligned': ma_alignment,
                            'retrace_ratio': retrace_ratio
                        })
                        break
        
        return signals

    def calculate_score(self, df: pd.DataFrame, signal: Dict) -> Tuple[float, str]:
        """计算评分"""
        score = 0
        reasons = []
        
        # 1. 均线支撑得分 (0-30)
        retrace_ratio = signal['retrace_ratio']
        if retrace_ratio < 0.005:
            score += 30
            reasons.append(f"价格精确回踩MA{signal['ma_period']}")
        elif retrace_ratio < 0.01:
            score += 25
            reasons.append(f"价格接近回踩MA{signal['ma_period']}")
        else:
            score += 20
            reasons.append(f"价格回踩MA{signal['ma_period']}")
        
        # 2. 缩量程度得分 (0-25)
        vol_ratio = signal['volume_ratio']
        if vol_ratio < 0.3:
            score += 25
            reasons.append("成交量极度萎缩(<30%均量)")
        elif vol_ratio < 0.4:
            score += 20
            reasons.append("成交量大幅萎缩(<40%均量)")
        elif vol_ratio < 0.5:
            score += 15
            reasons.append("成交量明显萎缩(<50%均量)")
        
        # 3. 价格稳定性得分 (0-20)
        if signal['index'] >= 5:
            recent_volatility = df['close'].iloc[signal['index']-5:signal['index']].std() / df['close'].iloc[signal['index']-5:signal['index']].mean()
            if recent_volatility < 0.02:
                score += 20
                reasons.append("价格极度稳定")
            elif recent_volatility < 0.05:
                score += 15
                reasons.append("价格相对稳定")
            elif recent_volatility < 0.1:
                score += 10
                reasons.append("价格波动正常")
        
        # 4. 趋势对齐得分 (0-15)
        if signal['trend_aligned']:
            score += 15
            reasons.append("回踩在上涨趋势中")
        else:
            score += 5
            reasons.append("等待趋势确认")
        
        # 5. 市场环境得分 (0-10) - 实际计算
        market_env_score = self._calc_market_environment()
        score += int(market_env_score * 0.1)
        if market_env_score >= 70:
            reasons.append(f"市场环境良好({market_env_score:.0f}分)")
        elif market_env_score >= 50:
            reasons.append(f"市场环境中性({market_env_score:.0f}分)")
        else:
            reasons.append(f"市场环境偏弱({market_env_score:.0f}分)")
        
        return score, "; ".join(reasons)
    
    def _get_index_code(self, index_name: str) -> str:
        """
        获取指数代码（根据数据源自动调整格式）
        """
        codes = {
            'sh': '000001', 'sz': '399001', 'cy': '399006', 'kc': '000688'
        }
        if self.data_adapter.source == 'baostock':
            codes = {
                'sh': 'sh.000001', 'sz': 'sz.399001', 'cy': 'sz.399006', 'kc': 'sh.000688'
            }
        return codes.get(index_name, '000001')
    
    def _get_market_index_data(self) -> Dict:
        """
        获取大盘指数数据（上证指数、深证成指、创业板指、科创板指）
        返回指数涨跌幅和成交量信息
        """
        market_data = {
            'sh_change': 0, 'sz_change': 0, 'cy_change': 0, 'kc_change': 0,
            'sh_volume_ratio': 1.0, 'total_score': 50
        }
        
        try:
            df_sh = self.data_adapter.get_stock_data(self._get_index_code('sh'))
            if df_sh is not None and len(df_sh) >= 2:
                latest = df_sh.iloc[-1]
                prev = df_sh.iloc[-2]
                market_data['sh_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
                if 'volume' in latest and 'volume' in prev and prev['volume'] > 0:
                    market_data['sh_volume_ratio'] = latest['volume'] / prev['volume']
        except Exception:
            pass
        
        try:
            df_sz = self.data_adapter.get_stock_data(self._get_index_code('sz'))
            if df_sz is not None and len(df_sz) >= 2:
                latest = df_sz.iloc[-1]
                prev = df_sz.iloc[-2]
                market_data['sz_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception:
            pass
        
        try:
            df_cy = self.data_adapter.get_stock_data(self._get_index_code('cy'))
            if df_cy is not None and len(df_cy) >= 2:
                latest = df_cy.iloc[-1]
                prev = df_cy.iloc[-2]
                market_data['cy_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception:
            pass
        
        try:
            df_kc = self.data_adapter.get_stock_data(self._get_index_code('kc'))
            if df_kc is not None and len(df_kc) >= 2:
                latest = df_kc.iloc[-1]
                prev = df_kc.iloc[-2]
                market_data['kc_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception:
            pass
        
        return market_data
    
    def _calc_market_environment(self) -> float:
        """
        计算市场环境评分（参考涨停板策略）
        基于大盘指数涨跌幅、成交量、趋势综合判断
        返回0-100的评分
        """
        if self._market_sentiment is not None:
            return self._market_sentiment
        
        score = 50  # 基础分
        market_data = self._get_market_index_data()
        
        # 大盘指数涨跌幅评分 (40%)
        index_changes = [market_data['sh_change'], market_data['sz_change'], 
                        market_data['cy_change'], market_data['kc_change']]
        valid_changes = [c for c in index_changes if c != 0]
        if valid_changes:
            avg_index_change = sum(valid_changes) / len(valid_changes)
        else:
            avg_index_change = 0
        
        if avg_index_change >= 2:
            score += 20
        elif avg_index_change >= 1:
            score += 15
        elif avg_index_change >= 0.5:
            score += 10
        elif avg_index_change >= 0:
            score += 5
        elif avg_index_change >= -0.5:
            score -= 5
        elif avg_index_change >= -1:
            score -= 10
        else:
            score -= 15
        
        # 成交量评分 (30%)
        volume_ratio = market_data['sh_volume_ratio']
        if volume_ratio >= 1.5:
            score += 15
        elif volume_ratio >= 1.2:
            score += 10
        elif volume_ratio >= 1.0:
            score += 5
        elif volume_ratio >= 0.8:
            score += 2
        else:
            score -= 5
        
        # 市场趋势评分 (30%)
        try:
            df_sh = self.data_adapter.get_stock_data(self._get_index_code('sh'))
            if df_sh is not None and len(df_sh) >= 20:
                df_sh['ma5'] = df_sh['close'].rolling(window=5).mean()
                df_sh['ma10'] = df_sh['close'].rolling(window=10).mean()
                df_sh['ma20'] = df_sh['close'].rolling(window=20).mean()
                latest = df_sh.iloc[-1]
                if latest['close'] > latest['ma5'] > latest['ma10'] > latest['ma20']:
                    score += 15
                elif latest['close'] > latest['ma5'] > latest['ma10']:
                    score += 10
                elif latest['close'] > latest['ma5']:
                    score += 5
                elif latest['close'] < latest['ma5'] < latest['ma10'] < latest['ma20']:
                    score -= 10
                elif latest['close'] < latest['ma5'] < latest['ma10']:
                    score -= 5
        except Exception:
            pass
        
        final_score = min(100, max(0, round(score, 1)))
        self._market_sentiment = final_score
        return final_score
    
    def get_rating(self, score: float) -> Dict:
        """获取评级（参考涨停板策略）"""
        if score >= self.THRESHOLDS['strong_buy']:
            return {'label': '极高', 'description': '缩量回踩信号强烈，重点关注'}
        elif score >= self.THRESHOLDS['buy']:
            return {'label': '高', 'description': '缩量回踩可能性大'}
        elif score >= self.THRESHOLDS['watch']:
            return {'label': '中等', 'description': '需结合盘面判断'}
        elif score >= self.THRESHOLDS['exclude']:
            return {'label': '低', 'description': '谨慎参与'}
        else:
            return {'label': '极低', 'description': '建议观望'}
    
    def get_recommendation(self, score: float) -> str:
        """获取操作建议（参考涨停板策略）"""
        if score >= self.THRESHOLDS['strong_buy']:
            return "✅ 重点关注 - 缩量回踩信号强烈，反弹概率极大"
        elif score >= self.THRESHOLDS['buy']:
            return "✅ 关注 - 缩量回踩可能性大，可考虑建仓"
        elif score >= self.THRESHOLDS['watch']:
            return "⚠️ 观察 - 需结合明日开盘情况判断"
        elif score >= self.THRESHOLDS['exclude']:
            return "⚠️ 谨慎 - 回踩信号不明确，不建议参与"
        else:
            return "❌ 观望 - 未见明显回踩信号"

    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """分析单只股票（改进版，包含详细评分维度）"""
        try:
            df = self.data_adapter.get_stock_data(stock_code)
            if df is None or len(df) < 30:
                return None
            
           # df = self.data_adapter.normalize_columns(df)
            
            signals = self.find_retrace_signals(df)
            
            if not signals:
                return None
            
            signal = signals[-1]
            score, reasons = self.calculate_score(df, signal)
            
            # 获取评级和建议
            rating = self.get_rating(score)
            recommendation = self.get_recommendation(score)
            
            current = df.iloc[-1]
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'score': score,
                'rating': rating,
                'recommendation': recommendation,
                'reasons': reasons,
                'current_price': round(current['close'], 2),
                'ma_value': round(signal['ma_value'], 2),
                'ma_period': signal['ma_period'],
                'volume_ratio': round(signal['volume_ratio'] * 100, 1),
                'trend_aligned': signal['trend_aligned'],
                'strategy': self.name,
                'win_rate': self.win_rate,
                'market_environment': self._calc_market_environment()
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
    # 测试
    analyzer = VolumeRetraceAnalyzer(data_source='baostock')
    result = analyzer.analyze_stock('000001', '平安银行')
    if result:
        print(f"股票: {result['stock_name']}")
        print(f"信号: {result['signal']}")
        print(f"得分: {result['score']}")
        print(f"回踩均线: {result['retrace_ma']}")
        print(f"缩量: {result['volume_shrink']}%")
        print(f"止跌信号: {result['stop_signal']}")
    else:
        print("不符合条件")
