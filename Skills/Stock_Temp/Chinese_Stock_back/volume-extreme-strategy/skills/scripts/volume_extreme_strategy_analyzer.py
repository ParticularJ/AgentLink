#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
成交量地量见底分析器
识别和分析成交量极度萎缩后的底部反弹机会
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

class VolumeExtremeAnalyzer:
    """成交量地量见底分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "成交量地量见底策略"
        self.version = "v1.0.0"
        self.win_rate = 0.62
        
        # 成交量参数
        self.volume_ma_period = 20
        self.extreme_ratio = 0.4
        self.significant_ratio = 0.5
        
        # 价格参数
        self.ma_period = 20
        self.min_deviation = 5
        
        # 评分权重
        self.weights = {
            'volume_extreme': 0.35,
            'price_position': 0.25,
            'stability_signal': 0.25,
            'follow_up': 0.15
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from volume_extreme_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from volume_extreme_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)
           
    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """分析单只股票是否出现地量见底信号"""
        try:
            # 获取数据
            df = self._get_stock_data(stock_code)
            if df is None or len(df) < self.volume_ma_period + 30:
                return None
            
            # 计算指标
            df = self._calculate_indicators(df)
            
            # 检查地量
            volume_analysis = self._analyze_volume_extreme(df)
            
            if volume_analysis['score'] == 0:
                return None
            
            # 分析价格位置
            price_analysis = self._analyze_price_position(df)
            
            # 分析稳定性信号
            stability_analysis = self._analyze_stability(df)
            
            # 分析后续走势
            follow_up_analysis = self._analyze_follow_up(df)
            
            # 计算综合得分
            total_score = self._calculate_score(
                volume_analysis, price_analysis, stability_analysis, follow_up_analysis
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
                'volume_ratio': round(volume_analysis['volume_ratio'], 2),
                'volume_status': volume_analysis['status'],
                'price_deviation': round(price_analysis['deviation'], 2),
                'stability_signal': stability_analysis['signal_type'],
                'follow_up': follow_up_analysis['trend'],
                'details': {
                    'volume': volume_analysis,
                    'price': price_analysis,
                    'stability': stability_analysis,
                    'follow_up': follow_up_analysis
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
        # 计算成交量均线
        df['volume_ma20'] = df['volume'].rolling(window=self.volume_ma_period).mean()
        
        # 计算价格均线
        df['MA20'] = df['close'].rolling(window=self.ma_period).mean()
        
        # 计算K线实体
        df['body'] = abs(df['close'] - df['open'])
        df['total_range'] = df['high'] - df['low']
        
        return df
    
    def _analyze_volume_extreme(self, df: pd.DataFrame) -> Dict:
        """分析成交量是否地量"""
        latest = df.iloc[-1]
        volume_ma20 = latest['volume_ma20']
        current_volume = latest['volume']
        
        if volume_ma20 == 0 or pd.isna(volume_ma20):
            return {'score': 0, 'volume_ratio': 1, 'status': '无数据'}
        
        # 计算成交量比例
        volume_ratio = current_volume / volume_ma20
        
        # 判断地量程度
        if volume_ratio <= self.extreme_ratio:
            score = 100
            status = '极度地量'
        elif volume_ratio <= self.significant_ratio:
            score = 85
            status = '显著缩量'
        elif volume_ratio <= 0.6:
            score = 70
            status = '明显缩量'
        else:
            score = 0
            status = '正常'
        
        return {
            'score': score,
            'volume_ratio': volume_ratio,
            'status': status,
            'current_volume': current_volume,
            'volume_ma20': volume_ma20
        }
    
    def _analyze_price_position(self, df: pd.DataFrame) -> Dict:
        """分析价格位置"""
        latest = df.iloc[-1]
        ma20 = latest['MA20']
        current_price = latest['close']
        
        if pd.isna(ma20) or ma20 == 0:
            return {'score': 50, 'deviation': 0}
        
        # 计算偏离度（价格低于均线的百分比）
        deviation = (ma20 - current_price) / ma20 * 100
        
        # 评分（下跌越多得分越高，但有上限）
        if deviation >= 20:
            score = 100
        elif deviation >= 15:
            score = 90
        elif deviation >= 10:
            score = 80
        elif deviation >= self.min_deviation:
            score = 70
        else:
            score = 60
        
        return {
            'score': score,
            'deviation': deviation,
            'ma20': ma20
        }
    
    def _analyze_stability(self, df: pd.DataFrame) -> Dict:
        """分析稳定性信号"""
        if len(df) < 5:
            return {'score': 50, 'signal_type': '数据不足'}
        
        recent = df.tail(5)
        
        # 检查是否止跌（连续下跌后企稳）
        price_declining = recent['close'].iloc[-2] < recent['close'].iloc[-3]
        price_stabilizing = abs(recent['close'].iloc[-1] - recent['close'].iloc[-2]) / recent['close'].iloc[-2] < 0.02
        
        # 检查是否出现小实体K线（企稳信号）
        recent_body_ratio = recent['body'].iloc[-1] / recent['total_range'].iloc[-1] if recent['total_range'].iloc[-1] > 0 else 1
        is_small_body = recent_body_ratio < 0.3
        
        # 检查长下影线
        latest = df.iloc[-1]
        lower_shadow = min(latest['open'], latest['close']) - latest['low']
        body = latest['body']
        has_long_lower_shadow = lower_shadow > body * 1.5 if body > 0 else False
        
        if price_declining and price_stabilizing and has_long_lower_shadow:
            score = 100
            signal_type = '长下影线企稳'
        elif price_declining and price_stabilizing and is_small_body:
            score = 85
            signal_type = '小实体企稳'
        elif price_stabilizing:
            score = 75
            signal_type = '价格企稳'
        elif is_small_body:
            score = 70
            signal_type = '小实体震荡'
        else:
            score = 60
            signal_type = '无明显信号'
        
        return {
            'score': score,
            'signal_type': signal_type,
            'price_stabilizing': price_stabilizing,
            'is_small_body': is_small_body,
            'has_long_lower_shadow': has_long_lower_shadow
        }
    
    def _analyze_follow_up(self, df: pd.DataFrame) -> Dict:
        """分析后续走势"""
        if len(df) < 10:
            return {'score': 50, 'trend': '数据不足'}
        
        # 检查最近10天的趋势
        recent = df.tail(10)
        price_change = (recent['close'].iloc[-1] - recent['close'].iloc[0]) / recent['close'].iloc[0] * 100
        
        # 检查是否有反弹迹象
        recent_3 = df.tail(3)
        rebounding = recent_3['close'].iloc[-1] > recent_3['close'].iloc[0]
        
        if rebounding and price_change > -5:
            score = 100
            trend = '开始反弹'
        elif rebounding:
            score = 85
            trend = '企稳回升'
        elif price_change > -10:
            score = 70
            trend = '跌幅收窄'
        else:
            score = 60
            trend = '仍在下跌'
        
        return {
            'score': score,
            'trend': trend,
            'price_change': round(price_change, 2)
        }
    
    def _calculate_score(self, volume_analysis: Dict, price_analysis: Dict,
                        stability_analysis: Dict, follow_up_analysis: Dict) -> float:
        """计算综合得分"""
        total_score = (
            volume_analysis['score'] * self.weights['volume_extreme'] +
            price_analysis['score'] * self.weights['price_position'] +
            stability_analysis['score'] * self.weights['stability_signal'] +
            follow_up_analysis['score'] * self.weights['follow_up']
        )
        return total_score


if __name__ == '__main__':
    # 测试
    analyzer = VolumeExtremeAnalyzer(data_source='baostock')
    result = analyzer.analyze_stock('000001', '平安银行')
    if result:
        print(f"股票: {result['stock_name']}")
        print(f"信号: {result['signal']}")
        print(f"得分: {result['score']}")
        print(f"成交量比: {result['volume_ratio']}")
        print(f"价格偏离: {result['price_deviation']}%")
    else:
        print("未检测到地量见底信号")
