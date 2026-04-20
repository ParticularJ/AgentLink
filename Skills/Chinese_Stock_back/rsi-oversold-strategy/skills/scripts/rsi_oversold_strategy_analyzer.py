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


class RSIOversoldAnalyzer:
    """RSI超卖反弹分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "RSI超卖反弹策略"
        self.version = "v1.0.0"
        self.win_rate = 0.58
        
        # RSI参数
        self.rsi_period = 14
        self.oversold_threshold = 30
        self.extreme_oversold = 20
        
        # 偏离参数
        self.ma_period = 20
        self.min_deviation = 8
        
        # 评分权重
        self.weights = {
            'rsi_oversold': 0.35,
            'price_deviation': 0.25,
            'volume_shrink': 0.20,
            'stability_signal': 0.20
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")

    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from rsi_oversold_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from rsi_oversold_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)
           
    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """分析单只股票是否出现RSI超卖"""
        try:
            # 获取数据
            df = self._get_stock_data(stock_code)
            if df is None or len(df) < self.rsi_period + 20:
                return None
            
            # 计算指标
            df = self._calculate_indicators(df)
            
            # 检查RSI超卖
            rsi_analysis = self._analyze_rsi_oversold(df)
            
            if rsi_analysis['score'] == 0:
                return None
            
            # 分析价格偏离度
            deviation_analysis = self._analyze_price_deviation(df)
            
            # 分析成交量
            volume_analysis = self._analyze_volume(df)
            
            # 分析止跌信号
            stability_analysis = self._analyze_stability(df)
            
            # 计算综合得分
            total_score = self._calculate_score(
                rsi_analysis, deviation_analysis, volume_analysis, stability_analysis
            )
            
            # 判断是否出现买入信号
            if total_score < 65:
                return None
            
            # 生成信号
            signal = '强烈买入' if total_score >= 85 else '买入' if total_score >= 75 else '观望'
            
            latest = df.iloc[-1]
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'signal': signal,
                'score': round(total_score, 2),
                'current_price': round(latest['close'], 2),
                'rsi_value': round(rsi_analysis['rsi'], 2),
                'rsi_status': rsi_analysis['status'],
                'price_deviation': round(deviation_analysis['deviation'], 2),
                'volume_shrink': round(volume_analysis['shrink_ratio'] * 100, 1),
                'stability_signal': stability_analysis['signal_type'],
                'details': {
                    'rsi': rsi_analysis,
                    'deviation': deviation_analysis,
                    'volume': volume_analysis,
                    'stability': stability_analysis
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
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        # 计算RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 计算均线
        df['MA20'] = df['close'].rolling(window=self.ma_period).mean()
        
        # 计算成交量均线
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        
        return df
    
    def _analyze_rsi_oversold(self, df: pd.DataFrame) -> Dict:
        """分析RSI超卖"""
        latest = df.iloc[-1]
        rsi = latest['RSI']
        
        if pd.isna(rsi):
            return {'score': 0, 'rsi': 0, 'status': '无数据'}
        
        # 判断超卖程度
        if rsi <= self.extreme_oversold:
            score = 100
            status = '极度超卖'
        elif rsi <= self.oversold_threshold:
            score = 85
            status = '超卖'
        elif rsi <= 35:
            score = 70
            status = '接近超卖'
        else:
            score = 0
            status = '正常'
        
        return {
            'score': score,
            'rsi': rsi,
            'status': status
        }
    
    def _analyze_price_deviation(self, df: pd.DataFrame) -> Dict:
        """分析价格偏离度"""
        latest = df.iloc[-1]
        ma20 = latest['MA20']
        current_price = latest['close']
        
        if pd.isna(ma20) or ma20 == 0:
            return {'score': 0, 'deviation': 0}
        
        # 计算偏离度（价格低于均线的百分比）
        deviation = (ma20 - current_price) / ma20 * 100
        
        # 评分（偏离越大得分越高，但有上限）
        if deviation >= 15:
            score = 100
        elif deviation >= 10:
            score = 90
        elif deviation >= self.min_deviation:
            score = 80
        elif deviation >= 5:
            score = 65
        else:
            score = 50
        
        return {
            'score': score,
            'deviation': deviation,
            'ma20': ma20
        }
    
    def _analyze_volume(self, df: pd.DataFrame) -> Dict:
        """分析成交量"""
        latest = df.iloc[-1]
        volume_ma5 = latest['volume_ma5']
        
        if volume_ma5 == 0 or pd.isna(volume_ma5):
            return {'score': 50, 'shrink_ratio': 1}
        
        # 计算缩量程度
        shrink_ratio = latest['volume'] / volume_ma5
        
        # 评分（缩量越多得分越高）
        if shrink_ratio < 0.5:
            score = 100
        elif shrink_ratio < 0.7:
            score = 85
        elif shrink_ratio < 0.9:
            score = 70
        else:
            score = 50
        
        return {
            'score': score,
            'shrink_ratio': shrink_ratio,
            'current_volume': latest['volume'],
            'volume_ma5': volume_ma5
        }
    
    def _analyze_stability(self, df: pd.DataFrame) -> Dict:
        """分析止跌信号"""
        if len(df) < 3:
            return {'score': 50, 'signal_type': '数据不足'}
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        # 检查是否止跌（连续下跌后收阳）
        prev_declining = prev['close'] < prev2['close']
        current_rising = latest['close'] > prev['close']
        
        # 检查下影线
        body = abs(latest['close'] - latest['open'])
        lower_shadow = min(latest['open'], latest['close']) - latest['low']
        has_long_lower_shadow = lower_shadow > body * 1.5
        
        if prev_declining and current_rising and has_long_lower_shadow:
            score = 100
            signal_type = '锤子线止跌'
        elif prev_declining and current_rising:
            score = 85
            signal_type = '止跌反弹'
        elif has_long_lower_shadow:
            score = 75
            signal_type = '长下影线'
        else:
            score = 60
            signal_type = '无明显信号'
        
        return {
            'score': score,
            'signal_type': signal_type,
            'prev_declining': prev_declining,
            'current_rising': current_rising,
            'has_long_lower_shadow': has_long_lower_shadow
        }
    
    def _calculate_score(self, rsi_analysis: Dict, deviation_analysis: Dict,
                        volume_analysis: Dict, stability_analysis: Dict) -> float:
        """计算综合得分"""
        total_score = (
            rsi_analysis['score'] * self.weights['rsi_oversold'] +
            deviation_analysis['score'] * self.weights['price_deviation'] +
            volume_analysis['score'] * self.weights['volume_shrink'] +
            stability_analysis['score'] * self.weights['stability_signal']
        )
        return total_score


if __name__ == '__main__':
    # 测试
    analyzer = RSIOversoldAnalyzer(data_source='baostock')
    result = analyzer.analyze_stock('000001', '平安银行')
    if result:
        print(f"股票: {result['stock_name']}")
        print(f"信号: {result['signal']}")
        print(f"得分: {result['score']}")
        print(f"RSI: {result['rsi_value']}")
        print(f"偏离度: {result['price_deviation']}%")
    else:
        print("未检测到RSI超卖信号")
