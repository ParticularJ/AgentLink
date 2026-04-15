#!/usr/bin/env python3
"""
缩量回踩重要均线策略分析器
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
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../ma-bullish-strategy/skills/ma_bullish/scripts')
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        # 备选：从项目根目录相对导入
        sys.path.insert(0, os.path.join(os.getcwd(), 'ma-bullish-strategy/skills/ma_bullish/scripts'))
        from data_source_adapter import DataSourceAdapter


class VolumeRetraceAnalyzer:
    """缩量回踩均线分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "缩量回踩重要均线策略"
        self.version = "v1.0.0"
        
        # 加载配置
        self.config = self._load_config()
        
        # 评分权重
        self.weights = {
            'trend_strength': 0.25,
            'retrace_quality': 0.20,
            'volume_shrink': 0.20,
            'stop_signal': 0.20,
            'support_strength': 0.15
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
        
    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from retrace_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from retrace_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)
       
    def _load_config(self) -> Dict:
        """加载策略配置"""
        config_path = '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/volume-retrace-ma-strategy/config/strategy_config.yaml'
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except:
            return {}
    
    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """
        分析单只股票是否出现缩量回踩买入信号
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            分析结果字典
        """
        try:
            # 获取历史数据
            df = self._get_stock_data(stock_code)
            if df is None or len(df) < 80:
                return None
            
            # 计算均线
            df = self._calculate_ma(df)
            
            # 获取最新数据
            latest = df.iloc[-1]
            
            # 1. 趋势判断
            trend = self._analyze_trend(df)
            if not trend['is_uptrend']:
                return None
            
            # 2. 回踩分析
            retrace = self._analyze_retrace(df)
            if not retrace['is_retracing']:
                return None
            
            # 3. 缩量分析
            volume = self._analyze_volume(df)
            if not volume['is_shrinking']:
                return None
            
            # 4. 止跌信号
            stop_signal = self._analyze_stop_signal(df)
            
            # 5. 支撑强度
            support = self._analyze_support(df, retrace['ma_type'])
            
            # 计算综合得分
            total_score = self._calculate_score(trend, retrace, volume, stop_signal, support)
            
            # 判断是否出现买入信号
            if total_score < 60:
                return None
            
            # 生成交易建议
            signal = '强烈买入' if total_score >= 80 else '买入' if total_score >= 70 else '观望'
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'signal': signal,
                'score': round(total_score, 2),
                'current_price': round(latest['close'], 2),
                'retrace_ma': retrace['ma_type'],
                'ma_price': round(retrace['ma_price'], 2),
                'retrace_pct': round(retrace['retrace_pct'], 2),
                'volume_shrink': round(volume['shrink_ratio'] * 100, 1),
                'stop_signal': stop_signal['signal_type'],
                'details': {
                    'trend': trend,
                    'retrace': retrace,
                    'volume': volume,
                    'stop_signal': stop_signal,
                    'support': support
                }
            }
            
        except Exception as e:
            print(f"分析{stock_code}失败: {e}")
            return None
    
    def _get_stock_data(self, stock_code: str) -> Optional[pd.DataFrame]:
        """获取股票历史数据"""
        try:
            df = self.data_adapter.get_stock_data(stock_code)
            if df is None or df.empty:
                return None
            return df
        except Exception as e:
            print(f"获取{stock_code}数据失败: {e}")
            return None
    
    def _calculate_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算均线"""
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA30'] = df['close'].rolling(window=30).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        return df
    
    def _analyze_trend(self, df: pd.DataFrame) -> Dict:
        """分析趋势"""
        latest = df.iloc[-1]
        
        # 判断均线多头排列
        ma20_gt_ma60 = latest['MA20'] > latest['MA60']
        
        # 计算均线斜率（简化版）
        ma20_slope = (latest['MA20'] - df.iloc[-5]['MA20']) / latest['MA20'] * 100
        
        is_uptrend = ma20_gt_ma60 and ma20_slope > 0
        
        # 评分
        if ma20_gt_ma60 and ma20_slope > 2:
            score = 100
        elif ma20_gt_ma60 and ma20_slope > 0:
            score = 85
        elif ma20_gt_ma60:
            score = 70
        else:
            score = 0
        
        return {
            'is_uptrend': is_uptrend,
            'ma20_slope': round(ma20_slope, 2),
            'ma20_gt_ma60': ma20_gt_ma60,
            'score': score
        }
    
    def _analyze_retrace(self, df: pd.DataFrame) -> Dict:
        """分析回踩情况"""
        latest = df.iloc[-1]
        prev_high = df['close'].rolling(window=20).max().iloc[-1]
        
        # 计算回调幅度
        retrace_pct = (prev_high - latest['close']) / prev_high * 100
        
        # 判断回踩哪条均线
        ma_types = [
            ('MA20', latest['MA20']),
            ('MA30', latest['MA30']),
            ('MA60', latest['MA60'])
        ]
        
        closest_ma = None
        min_distance = float('inf')
        
        for ma_name, ma_price in ma_types:
            distance = abs(latest['close'] - ma_price) / latest['close'] * 100
            if distance < min_distance:
                min_distance = distance
                closest_ma = (ma_name, ma_price)
        
        is_retracing = min_distance <= 3 and 2 <= retrace_pct <= 15
        
        # 评分
        if min_distance <= 1:
            score = 100
        elif min_distance <= 3:
            score = 85
        elif min_distance <= 5:
            score = 70
        else:
            score = 0
        
        return {
            'is_retracing': is_retracing,
            'ma_type': closest_ma[0] if closest_ma else None,
            'ma_price': closest_ma[1] if closest_ma else None,
            'retrace_pct': retrace_pct,
            'distance_to_ma': round(min_distance, 2),
            'score': score
        }
    
    def _analyze_volume(self, df: pd.DataFrame) -> Dict:
        """分析成交量"""
        latest = df.iloc[-1]
        volume_ma5 = latest['volume_ma5']
        
        if volume_ma5 == 0:
            return {'is_shrinking': False, 'score': 0}
        
        shrink_ratio = latest['volume'] / volume_ma5
        is_shrinking = shrink_ratio < 0.6
        
        # 评分
        if shrink_ratio < 0.4:
            score = 100
        elif shrink_ratio < 0.5:
            score = 85
        elif shrink_ratio < 0.6:
            score = 70
        else:
            score = max(0, 100 - (shrink_ratio - 0.6) * 200)
        
        return {
            'is_shrinking': is_shrinking,
            'shrink_ratio': shrink_ratio,
            'current_volume': latest['volume'],
            'volume_ma5': volume_ma5,
            'score': round(score, 2)
        }
    
    def _analyze_stop_signal(self, df: pd.DataFrame) -> Dict:
        """分析止跌信号"""
        latest = df.iloc[-1]
        
        # 计算K线形态
        open_price = latest['open']
        close_price = latest['close']
        high_price = latest['high']
        low_price = latest['low']
        
        body = abs(close_price - open_price)
        upper_shadow = high_price - max(open_price, close_price)
        lower_shadow = min(open_price, close_price) - low_price
        
        # 判断锤子线（下影线长，实体小）
        is_hammer = lower_shadow > body * 2 and upper_shadow < body * 0.5
        
        # 判断十字星（实体很小）
        is_doji = body < (high_price - low_price) * 0.1
        
        # 判断小阳线
        is_small_yang = close_price > open_price and body < (high_price - low_price) * 0.3
        
        if is_hammer:
            signal_type = '锤子线'
            score = 100
        elif is_doji:
            signal_type = '十字星'
            score = 85
        elif is_small_yang:
            signal_type = '小阳线'
            score = 70
        else:
            signal_type = '无明显信号'
            score = 40
        
        return {
            'signal_type': signal_type,
            'is_hammer': is_hammer,
            'is_doji': is_doji,
            'is_small_yang': is_small_yang,
            'score': score
        }
    
    def _analyze_support(self, df: pd.DataFrame, ma_type: str) -> Dict:
        """分析支撑强度"""
        if ma_type is None:
            return {'score': 0}
        
        latest = df.iloc[-1]
        ma_col = ma_type
        
        # 计算均线斜率
        ma_slope = (latest[ma_col] - df.iloc[-5][ma_col]) / latest[ma_col] * 100
        
        # 评分
        if ma_slope > 2:
            score = 100
        elif ma_slope > 1:
            score = 85
        elif ma_slope > 0:
            score = 70
        else:
            score = max(0, 70 + ma_slope * 10)
        
        return {
            'ma_slope': round(ma_slope, 2),
            'score': score
        }
    
    def _calculate_score(self, trend: Dict, retrace: Dict, volume: Dict, 
                        stop_signal: Dict, support: Dict) -> float:
        """计算综合得分"""
        total_score = (
            trend['score'] * self.weights['trend_strength'] +
            retrace['score'] * self.weights['retrace_quality'] +
            volume['score'] * self.weights['volume_shrink'] +
            stop_signal['score'] * self.weights['stop_signal'] +
            support['score'] * self.weights['support_strength']
        )
        return total_score


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
