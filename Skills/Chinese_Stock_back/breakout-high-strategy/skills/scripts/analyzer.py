#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
突破前期高点分析器
识别和分析股价突破前期重要高点的买入机会
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
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../ma-bullish-strategy/skills/ma_bullish/scripts')
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        # 备选：从项目根目录相对导入
        sys.path.insert(0, os.path.join(os.getcwd(), 'ma-bullish-strategy/skills/ma_bullish/scripts'))
        from data_source_adapter import DataSourceAdapter


class BreakoutHighAnalyzer:
    """突破前期高点分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "突破前期高点策略"
        self.version = "v1.0.0"
        self.win_rate = 0.68
        
        # 突破参数
        self.lookback_days = 60        # 回看天数
        self.min_breakout_pct = 3.0    # 最小突破幅度
        self.min_volume_ratio = 1.5    # 最小放量倍数
        
        # 评分权重
        self.weights = {
            'breakout_quality': 0.35,
            'volume_confirmation': 0.25,
            'trend_cooperation': 0.25,
            'pullback_confirmation': 0.15
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from scanner import scan_all_stocks as scanner
            #print("使用 scanner 模块进行扫描")
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            print("使用 scanner 模块进行扫描:",sys.path)
            from scanner import scan_all_stocks as scanner
        return scanner(self, top_n)
           
    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """分析单只股票是否出现突破"""
        try:
            # 获取数据

            df = self._get_stock_data(stock_code)
            if df is None or len(df) < self.lookback_days + 10:
                return None
            
            # 计算指标
            df = self._calculate_indicators(df)
            
            # 查找突破
            breakout = self._find_breakout(df)
            
            if not breakout:
                return None
            
            # 分析突破质量
            breakout_analysis = self._analyze_breakout_quality(df, breakout)
            
            # 分析成交量
            volume_analysis = self._analyze_volume(df, breakout)
            
            # 分析趋势配合
            trend_analysis = self._analyze_trend(df, breakout)
            
            # 分析回踩确认
            pullback_analysis = self._analyze_pullback(df, breakout)
            
            # 计算综合得分
            total_score = self._calculate_score(
                breakout_analysis, volume_analysis, trend_analysis, pullback_analysis
            )
            
            # 判断是否出现买入信号
            if total_score < 70:
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
                'breakout_price': round(breakout['price'], 2),
                'previous_high': round(breakout['previous_high'], 2),
                'breakout_pct': round(breakout['breakout_pct'], 2),
                'volume_ratio': round(volume_analysis['volume_ratio'], 2),
                'trend_direction': trend_analysis['direction'],
                'pullback_confirmed': pullback_analysis['confirmed'],
                'details': {
                    'breakout': breakout_analysis,
                    'volume': volume_analysis,
                    'trend': trend_analysis,
                    'pullback': pullback_analysis
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
        # 计算均线
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        
        # 计算成交量均线
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        df['volume_ma20'] = df['volume'].rolling(window=20).mean()
        
        # 计算前期高点
        df['previous_high'] = df['high'].rolling(window=self.lookback_days).max().shift(1)
        
        return df
    
    def _find_breakout(self, df: pd.DataFrame) -> Optional[Dict]:
        """查找突破"""
        latest = df.iloc[-1]
        
        # 检查是否突破前期高点
        if pd.isna(latest['previous_high']) or latest['previous_high'] == 0:
            return None
        
        breakout_pct = (latest['close'] - latest['previous_high']) / latest['previous_high'] * 100
        
        # 检查突破幅度
        if breakout_pct < self.min_breakout_pct:
            return None
        
        # 检查是否创了新高
        is_new_high = latest['close'] == df['close'].tail(self.lookback_days).max()
        
        return {
            'price': latest['close'],
            'previous_high': latest['previous_high'],
            'breakout_pct': breakout_pct,
            'is_new_high': is_new_high,
            'date': latest.get('date', df.index[-1])
        }
    
    def _analyze_breakout_quality(self, df: pd.DataFrame, breakout: Dict) -> Dict:
        """分析突破质量"""
        breakout_pct = breakout['breakout_pct']
        is_new_high = breakout['is_new_high']
        
        # 评分
        if breakout_pct >= 5 and is_new_high:
            score = 100
            quality = '强势突破'
        elif breakout_pct >= 3 and is_new_high:
            score = 85
            quality = '有效突破'
        elif breakout_pct >= 3:
            score = 70
            quality = '一般突破'
        else:
            score = 50
            quality = '弱势突破'
        
        return {
            'score': score,
            'quality': quality,
            'breakout_pct': breakout_pct,
            'is_new_high': is_new_high
        }
    
    def _analyze_volume(self, df: pd.DataFrame, breakout: Dict) -> Dict:
        """分析成交量"""
        latest = df.iloc[-1]
        volume_ma20 = latest['volume_ma20']
        
        if volume_ma20 == 0 or pd.isna(volume_ma20):
            return {'score': 0, 'volume_ratio': 1}
        
        volume_ratio = latest['volume'] / volume_ma20
        
        # 评分
        if volume_ratio >= 2.0:
            score = 100
        elif volume_ratio >= 1.5:
            score = 85
        elif volume_ratio >= 1.2:
            score = 70
        else:
            score = max(0, 100 - (1.2 - volume_ratio) * 200)
        
        return {
            'score': score,
            'volume_ratio': volume_ratio,
            'current_volume': latest['volume'],
            'volume_ma20': volume_ma20
        }
    
    def _analyze_trend(self, df: pd.DataFrame, breakout: Dict) -> Dict:
        """分析趋势配合"""
        latest = df.iloc[-1]
        
        # 判断均线多头排列
        ma_bullish = latest['MA5'] > latest['MA10'] > latest['MA20']
        
        # 判断均线斜率
        ma5_slope = (latest['MA5'] - df.iloc[-5]['MA5']) / latest['MA5'] * 100 if len(df) >= 5 else 0
        
        # 评分
        if ma_bullish and ma5_slope > 1:
            score = 100
            direction = '强势上涨'
        elif ma_bullish:
            score = 85
            direction = '多头排列'
        elif latest['MA5'] > latest['MA10']:
            score = 70
            direction = '短期向好'
        else:
            score = 50
            direction = '趋势不明'
        
        return {
            'score': score,
            'direction': direction,
            'ma_bullish': ma_bullish,
            'ma5_slope': round(ma5_slope, 2)
        }
    
    def _analyze_pullback(self, df: pd.DataFrame, breakout: Dict) -> Dict:
        """分析回踩确认"""
        # 检查突破后是否回踩前期高点（现在变成支撑）
        previous_high = breakout['previous_high']
        latest = df.iloc[-1]
        
        # 简单判断：如果当前价格仍在突破价附近或之上，认为确认有效
        pullback_pct = (latest['close'] - previous_high) / previous_high * 100
        
        if pullback_pct >= breakout['breakout_pct'] * 0.5:
            confirmed = True
            score = 100
        elif pullback_pct > 0:
            confirmed = True
            score = 80
        else:
            confirmed = False
            score = 50
        
        return {
            'score': score,
            'confirmed': confirmed,
            'pullback_pct': round(pullback_pct, 2)
        }
    
    def _calculate_score(self, breakout_analysis: Dict, volume_analysis: Dict,
                        trend_analysis: Dict, pullback_analysis: Dict) -> float:
        """计算综合得分"""
        total_score = (
            breakout_analysis['score'] * self.weights['breakout_quality'] +
            volume_analysis['score'] * self.weights['volume_confirmation'] +
            trend_analysis['score'] * self.weights['trend_cooperation'] +
            pullback_analysis['score'] * self.weights['pullback_confirmation']
        )
        return total_score


if __name__ == '__main__':
    # 测试
    analyzer = BreakoutHighAnalyzer(data_source='baostock')
    result = analyzer.scan_all_stocks(top_n=5)
    if result:
        print(f"股票: {result['stock_name']}")
        print(f"信号: {result['signal']}")
        print(f"得分: {result['score']}")
        print(f"突破幅度: {result['breakout_pct']}%")
        print(f"成交量比: {result['volume_ratio']}")
    else:
        print("未检测到突破信号")
