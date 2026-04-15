# skills/scripts/morning_star_analyzer.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
早晨之星形态分析器
识别和分析早晨之星K线组合形态
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


class MorningStarAnalyzer:
    """早晨之星形态分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "早晨之星形态策略"
        self.version = "v1.0.0"
        self.win_rate = 0.62
        
        # 形态参数
        self.first_candle_min_decline = 3.0    # 第一根阴线最小跌幅
        self.second_candle_max_body_ratio = 0.2  # 第二根十字星最大实体比例
        self.third_candle_min_advance = 3.0    # 第三根阳线最小涨幅
        
        # 评分权重
        self.weights = {
            'pattern_completeness': 0.35,
            'position_confirmation': 0.25,
            'volume_confirmation': 0.20,
            'follow_up_confirmation': 0.20
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
        
    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from morning_star_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from morning_star_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)
            
    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """分析单只股票是否出现早晨之星"""
        try:
            # 获取数据
            df = self._get_stock_data(stock_code)
            if df is None or len(df) < 20:
                return None
            
            # 计算指标
            df = self._calculate_indicators(df)
            
            # 查找早晨之星
            pattern = self._find_morning_star(df)
            if not pattern['is_morning_star']:
                return None
            
            # 计算评分
            score = self._calculate_score(pattern, df)
            
            # 生成信号
            signal = '强烈买入' if score >= 85 else '买入' if score >= 75 else '观望'
            
            latest = df.iloc[-1]
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'signal': signal,
                'score': round(score, 2),
                'current_price': round(latest['close'], 2),
                'pattern_date': pattern['date'],
                'first_candle_decline': round(pattern['first_decline'], 2),
                'third_candle_advance': round(pattern['third_advance'], 2),
                'volume_confirmation': pattern['volume_ok'],
                'position': pattern['position'],
                'details': pattern
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
        # 计算K线实体和影线
        df['body'] = abs(df['close'] - df['open'])
        df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
        df['total_range'] = df['high'] - df['low']
        
        # 计算涨跌幅
        df['change_pct'] = df['close'].pct_change() * 100
        
        # 计算成交量均线
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        
        # 计算均线
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        
        return df
    
    def _find_morning_star(self, df: pd.DataFrame) -> Dict:
        """查找早晨之星形态"""
        if len(df) < 5:
            return {'is_morning_star': False}
        
        # 检查最近3根K线
        for i in range(len(df) - 3, len(df) - 2):
            if i < 2:
                continue
            
            first = df.iloc[i - 2]   # 第一根：大阴线
            second = df.iloc[i - 1]  # 第二根：十字星
            third = df.iloc[i]       # 第三根：大阳线
            
            # 检查第一根K线（大阴线）
            first_is_bearish = first['close'] < first['open']
            first_decline = (first['open'] - first['close']) / first['open'] * 100
            first_is_large = first_decline >= self.first_candle_min_decline
            
            # 检查第二根K线（十字星）
            second_body_ratio = second['body'] / second['total_range'] if second['total_range'] > 0 else 1
            second_is_doji = second_body_ratio <= self.second_candle_max_body_ratio
            second_gaps_down = second['open'] < first['close']  # 向下跳空或低开
            
            # 检查第三根K线（大阳线）
            third_is_bullish = third['close'] > third['open']
            third_advance = (third['close'] - third['open']) / third['open'] * 100
            third_is_large = third_advance >= self.third_candle_min_advance
            third_closes_into_first = third['close'] > (first['open'] + first['close']) / 2
            
            # 综合判断
            is_morning_star = (
                first_is_bearish and first_is_large and
                second_is_doji and
                third_is_bullish and third_is_large and third_closes_into_first
            )
            
            if is_morning_star:
                # 判断位置（是否在下跌趋势末端）
                position = self._judge_position(df, i)
                
                # 判断成交量
                volume_ok = self._check_volume(first, second, third)
                
                return {
                    'is_morning_star': True,
                    'date': df.index[i] if hasattr(df.index[i], 'strftime') else str(df.index[i]),
                    'index': i,
                    'first_decline': first_decline,
                    'third_advance': third_advance,
                    'second_is_doji': second_is_doji,
                    'second_gaps_down': second_gaps_down,
                    'third_closes_into_first': third_closes_into_first,
                    'position': position,
                    'volume_ok': volume_ok
                }
        
        return {'is_morning_star': False}
    
    def _judge_position(self, df: pd.DataFrame, pattern_idx: int) -> str:
        """判断形态位置"""
        # 检查形态前的趋势
        if pattern_idx < 10:
            return '未知'
        
        pre_trend = df.iloc[pattern_idx - 10:pattern_idx]
        price_change = (pre_trend['close'].iloc[-1] - pre_trend['close'].iloc[0]) / pre_trend['close'].iloc[0] * 100
        
        if price_change < -10:
            return '下跌末端'
        elif price_change < -5:
            return '下跌中'
        elif price_change > 5:
            return '上涨中'
        else:
            return '震荡中'
    
    def _check_volume(self, first: pd.Series, second: pd.Series, third: pd.Series) -> bool:
        """检查成交量配合"""
        # 第一天下跌放量，第二天缩量，第三天上攻放量
        first_volume_ok = first['volume'] > first.get('volume_ma5', first['volume']) * 0.8
        second_volume_ok = second['volume'] < second.get('volume_ma5', second['volume']) * 0.8
        third_volume_ok = third['volume'] > third.get('volume_ma5', third['volume']) * 1.0
        
        return first_volume_ok and second_volume_ok and third_volume_ok
    
    def _calculate_score(self, pattern: Dict, df: pd.DataFrame) -> float:
        """计算综合评分"""
        score = 0
        
        # 形态完整性（35%）
        if pattern['first_decline'] >= 5:
            pattern_score = 100
        elif pattern['first_decline'] >= 3:
            pattern_score = 85
        else:
            pattern_score = 70
        score += pattern_score * self.weights['pattern_completeness']
        
        # 位置确认（25%）
        position_scores = {
            '下跌末端': 100,
            '下跌中': 85,
            '震荡中': 70,
            '上涨中': 50,
            '未知': 60
        }
        position_score = position_scores.get(pattern['position'], 60)
        score += position_score * self.weights['position_confirmation']
        
        # 成交量确认（20%）
        volume_score = 100 if pattern['volume_ok'] else 60
        score += volume_score * self.weights['volume_confirmation']
        
        # 后续确认（20%）
        # 检查形态后是否有继续上涨
        follow_up_score = 80  # 默认中等
        if pattern['index'] < len(df) - 1:
            next_day = df.iloc[pattern['index'] + 1]
            if next_day['close'] > next_day['open']:
                follow_up_score = 100
            else:
                follow_up_score = 70
        score += follow_up_score * self.weights['follow_up_confirmation']
        
        return score


if __name__ == '__main__':
    # 测试
    analyzer = MorningStarAnalyzer(data_source='baostock')
    result = analyzer.analyze_stock('000001', '平安银行')
    if result:
        print(f"股票: {result['stock_name']}")
        print(f"信号: {result['signal']}")
        print(f"得分: {result['score']}")
        print(f"第一根跌幅: {result['first_candle_decline']}%")
        print(f"第三根涨幅: {result['third_candle_advance']}%")
    else:
        print("未检测到早晨之星形态")
