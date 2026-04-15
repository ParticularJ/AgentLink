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
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../ma-bullish-strategy/skills/ma_bullish/scripts')
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        # 备选：从项目根目录相对导入
        sys.path.insert(0, os.path.join(os.getcwd(), 'ma-bullish-strategy/skills/ma_bullish/scripts'))
        from data_source_adapter import DataSourceAdapter


class MACDDivergenceAnalyzer:
    """MACD底背离分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "MACD底背离策略"
        self.version = "v1.0.0"
        
        # 加载配置
        self.config = self._load_config()
        
        # 评分权重
        self.weights = {
            'divergence_strength': 0.25,
            'macd_golden_cross': 0.20,
            'volume_confirmation': 0.20,
            'candlestick_pattern': 0.20,
            'support_level': 0.15
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
    
    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from macd_divergence_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from macd_divergence_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)
    
    def _load_config(self) -> Dict:
        """加载策略配置"""
        config_path = '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/macd-divergence-strategy/config/strategy_config.yaml'
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except:
            return {}
    
    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """
        分析单只股票是否出现MACD底背离买入信号
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            分析结果字典
        """
        try:
            # 获取历史数据
            df = self._get_stock_data(stock_code)
            if df is None or len(df) < 60:
                return None
            
            # 计算MACD
            df = self._calculate_macd(df)
            
            # 1. 检测底背离
            divergence = self._detect_divergence(df)
            if not divergence['is_divergence']:
                return None
            
            # 2. 分析MACD金叉
            golden_cross = self._analyze_golden_cross(df)
            
            # 3. 分析成交量
            volume = self._analyze_volume(df)
            
            # 4. 分析K线形态
            candlestick = self._analyze_candlestick(df)
            
            # 5. 分析支撑位置
            support = self._analyze_support(df, divergence)
            
            # 计算综合得分
            total_score = self._calculate_score(
                divergence, golden_cross, volume, candlestick, support
            )
            
            # 判断是否出现买入信号
            if total_score < 65:
                return None
            
            # 生成交易建议
            signal = '强烈买入' if total_score >= 85 else '买入' if total_score >= 75 else '观望'
            
            latest = df.iloc[-1]
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'signal': signal,
                'score': round(total_score, 2),
                'current_price': round(latest['close'], 2),
                'divergence_type': divergence['type'],
                'price_low': round(divergence['price_low'], 2),
                'macd_low': round(divergence['macd_low'], 4),
                'prev_price_low': round(divergence['prev_price_low'], 2),
                'prev_macd_low': round(divergence['prev_macd_low'], 4),
                'golden_cross': golden_cross['has_crossed'],
                'volume_increase': round(volume['increase_ratio'] * 100, 1),
                'candlestick': candlestick['pattern'],
                'support_level': support['level'],
                'details': {
                    'divergence': divergence,
                    'golden_cross': golden_cross,
                    'volume': volume,
                    'candlestick': candlestick,
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
    
    def _calculate_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算MACD指标"""
        # 计算EMA
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        
        # 计算DIF和DEA
        df['DIF'] = ema12 - ema26
        df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['MACD'] = 2 * (df['DIF'] - df['DEA'])
        
        # 计算成交量均线
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        
        return df
    
    def _detect_divergence(self, df: pd.DataFrame) -> Dict:
        """检测MACD底背离"""
        lookback = 20  # 查看20日内的低点
        
        if len(df) < lookback + 10:
            return {'is_divergence': False}
        
        # 获取近期数据
        recent_df = df.tail(lookback).reset_index(drop=True)
        
        # 找到价格低点
        price_low_idx = recent_df['close'].idxmin()
        price_low = recent_df.loc[price_low_idx, 'close']
        macd_at_price_low = recent_df.loc[price_low_idx, 'MACD']
        
        # 找到之前的低点（10-20日前）
        if price_low_idx < 10:
            return {'is_divergence': False}
        
        prev_df = recent_df.iloc[:price_low_idx]
        prev_price_low_idx = prev_df['close'].idxmin()
        prev_price_low = prev_df.loc[prev_price_low_idx, 'close']
        prev_macd_low = prev_df.loc[prev_price_low_idx, 'MACD']
        
        # 判断背离
        price_lower = price_low < prev_price_low
        macd_not_lower = macd_at_price_low > prev_macd_low
        
        is_divergence = price_lower and macd_not_lower
        
        # 计算背离强度
        if is_divergence:
            price_decline = (prev_price_low - price_low) / prev_price_low * 100
            macd_improvement = (macd_at_price_low - prev_macd_low) / abs(prev_macd_low) * 100 if prev_macd_low != 0 else 0
            
            # 判断背离类型
            if macd_improvement > 50:
                div_type = '强背离'
                score = 100
            elif macd_improvement > 30:
                div_type = '中等背离'
                score = 85
            else:
                div_type = '轻微背离'
                score = 70
        else:
            div_type = '无背离'
            score = 0
        
        return {
            'is_divergence': is_divergence,
            'type': div_type,
            'score': score,
            'price_low': price_low,
            'macd_low': macd_at_price_low,
            'prev_price_low': prev_price_low,
            'prev_macd_low': prev_macd_low,
            'price_decline': price_decline if is_divergence else 0,
            'macd_improvement': macd_improvement if is_divergence else 0
        }
    
    def _analyze_golden_cross(self, df: pd.DataFrame) -> Dict:
        """分析MACD金叉"""
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        # 判断金叉
        prev_dif_lt_dea = prev['DIF'] < prev['DEA']
        curr_dif_gt_dea = latest['DIF'] > latest['DEA']
        
        has_crossed = prev_dif_lt_dea and curr_dif_gt_dea
        
        # 判断柱状线
        macd_positive = latest['MACD'] > 0
        macd_turning_positive = prev['MACD'] < 0 and latest['MACD'] > 0
        
        # 评分
        if has_crossed and macd_positive:
            score = 100
            status = '已金叉+柱状线转正'
        elif has_crossed:
            score = 85
            status = '刚金叉'
        elif latest['DIF'] < latest['DEA'] and latest['DIF'] > latest['DEA'] * 0.9:
            score = 70
            status = '即将金叉'
        else:
            score = 40
            status = '无金叉'
        
        return {
            'has_crossed': has_crossed,
            'macd_positive': macd_positive,
            'macd_turning_positive': macd_turning_positive,
            'status': status,
            'score': score,
            'dif': round(latest['DIF'], 4),
            'dea': round(latest['DEA'], 4),
            'macd': round(latest['MACD'], 4)
        }
    
    def _analyze_volume(self, df: pd.DataFrame) -> Dict:
        """分析成交量"""
        latest = df.iloc[-1]
        volume_ma5 = latest['volume_ma5']
        
        if volume_ma5 == 0 or pd.isna(volume_ma5):
            return {'increase_ratio': 1, 'score': 0}
        
        increase_ratio = latest['volume'] / volume_ma5
        
        # 评分
        if increase_ratio >= 1.5:
            score = 100
        elif increase_ratio >= 1.2:
            score = 85
        elif increase_ratio >= 1.0:
            score = 70
        else:
            score = max(0, 100 - (1.0 - increase_ratio) * 200)
        
        return {
            'increase_ratio': increase_ratio,
            'current_volume': latest['volume'],
            'volume_ma5': volume_ma5,
            'score': round(score, 2)
        }
    
    def _analyze_candlestick(self, df: pd.DataFrame) -> Dict:
        """分析K线形态"""
        latest = df.iloc[-1]
        
        open_price = latest['open']
        close_price = latest['close']
        high_price = latest['high']
        low_price = latest['low']
        
        body = abs(close_price - open_price)
        upper_shadow = high_price - max(open_price, close_price)
        lower_shadow = min(open_price, close_price) - low_price
        total_range = high_price - low_price
        
        # 判断锤子线
        is_hammer = (lower_shadow > body * 2 and 
                     upper_shadow < body * 0.5 and
                     close_price > open_price)
        
        # 判断启明星（需要3天数据）
        is_morning_star = False
        if len(df) >= 3:
            prev2 = df.iloc[-3]
            prev1 = df.iloc[-2]
            # 第一天大跌，第二天十字星，第三天上涨
            if (prev2['close'] < prev2['open'] * 0.97 and
                abs(prev1['close'] - prev1['open']) < (prev1['high'] - prev1['low']) * 0.1 and
                close_price > open_price):
                is_morning_star = True
        
        # 判断小阳线
        is_small_yang = (close_price > open_price and 
                        body < total_range * 0.3)
        
        if is_morning_star:
            pattern = '启明星'
            score = 100
        elif is_hammer:
            pattern = '锤子线'
            score = 85
        elif is_small_yang:
            pattern = '小阳线'
            score = 70
        else:
            pattern = '无明显形态'
            score = 40
        
        return {
            'pattern': pattern,
            'is_hammer': is_hammer,
            'is_morning_star': is_morning_star,
            'is_small_yang': is_small_yang,
            'score': score
        }
    
    def _analyze_support(self, df: pd.DataFrame, divergence: Dict) -> Dict:
        """分析支撑位置"""
        latest = df.iloc[-1]
        current_price = latest['close']
        
        # 获取前期低点
        prev_lows = df['low'].rolling(window=60).min().dropna()
        if len(prev_lows) > 0:
            recent_low = prev_lows.iloc[-1]
        else:
            recent_low = current_price
        
        # 判断整数关口
        round_levels = [int(current_price / 10) * 10, int(current_price / 5) * 5]
        nearest_round = min(round_levels, key=lambda x: abs(x - current_price))
        distance_to_round = abs(current_price - nearest_round) / current_price * 100
        
        # 判断是否在前低附近
        at_prev_low = abs(current_price - recent_low) / current_price * 100 <= 2
        at_round_level = distance_to_round <= 1
        
        # 评分
        if at_prev_low and at_round_level:
            level = '前期低点+整数关口'
            score = 100
        elif at_prev_low:
            level = '前期低点'
            score = 85
        elif at_round_level:
            level = '整数关口'
            score = 70
        else:
            level = '无明确支撑'
            score = 50
        
        return {
            'level': level,
            'recent_low': round(recent_low, 2),
            'nearest_round': nearest_round,
            'at_prev_low': at_prev_low,
            'at_round_level': at_round_level,
            'score': score
        }
    
    def _calculate_score(self, divergence: Dict, golden_cross: Dict,
                        volume: Dict, candlestick: Dict, support: Dict) -> float:
        """计算综合得分"""
        total_score = (
            divergence['score'] * self.weights['divergence_strength'] +
            golden_cross['score'] * self.weights['macd_golden_cross'] +
            volume['score'] * self.weights['volume_confirmation'] +
            candlestick['score'] * self.weights['candlestick_pattern'] +
            support['score'] * self.weights['support_level']
        )
        return total_score


if __name__ == '__main__':
    # 测试
    analyzer = MACDDivergenceAnalyzer(data_source='baostock')
    result = analyzer.analyze_stock('000001', '平安银行')
    if result:
        print(f"股票: {result['stock_name']}")
        print(f"信号: {result['signal']}")
        print(f"得分: {result['score']}")
        print(f"背离类型: {result['divergence_type']}")
        print(f"MACD金叉: {result['golden_cross']}")
    else:
        print("不符合条件")
