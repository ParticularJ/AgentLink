#!/usr/bin/env python3
"""
涨停板首次回调策略分析器
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


class LimitUpRetraceAnalyzer:
    """涨停板首次回调分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "涨停板首次回调策略"
        self.version = "v1.0.0"
        
        # 加载配置
        self.config = self._load_config()
        
        # 评分权重
        self.weights = {
            'limit_up_quality': 0.25,
            'retrace_quality': 0.20,
            'support_strength': 0.20,
            'volume_shrink': 0.20,
            'stop_signal': 0.15
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
    

    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from limit_up_retrace_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from limit_up_retrace_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)
    

    def _load_config(self) -> Dict:
        """加载策略配置"""
        config_path = '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/limit-up-retrace-strategy/config/strategy_config.yaml'
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except:
            return {}
    
    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """
        分析单只股票是否出现涨停后首次回调买入信号
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            分析结果字典
        """
        try:
            # 获取历史数据
            df = self._get_stock_data(stock_code)
            if df is None or len(df) < 30:
                return None
            
            # 计算均线
            df = self._calculate_ma(df)
            
            # 1. 识别近期涨停
            limit_up_info = self._find_recent_limit_up(df)
            if not limit_up_info:
                return None
            
            # 2. 分析回调情况
            retrace_info = self._analyze_retrace(df, limit_up_info)
            if not retrace_info['is_retracing']:
                return None
            
            # 3. 分析支撑位
            support_info = self._analyze_support(df, limit_up_info, retrace_info)
            
            # 4. 分析成交量
            volume_info = self._analyze_volume(df, retrace_info)
            
            # 5. 分析止跌信号
            stop_signal_info = self._analyze_stop_signal(df)
            
            # 6. 评估涨停质量
            limit_up_quality = self._evaluate_limit_up_quality(limit_up_info)
            
            # 计算综合得分
            total_score = self._calculate_score(
                limit_up_quality, retrace_info, support_info, 
                volume_info, stop_signal_info
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
                'limit_up_date': limit_up_info['date'],
                'limit_up_price': round(limit_up_info['price'], 2),
                'retrace_pct': round(retrace_info['retrace_pct'], 2),
                'support_level': support_info['level'],
                'support_price': round(support_info['price'], 2),
                'volume_shrink': round(volume_info['shrink_ratio'] * 100, 1),
                'stop_signal': stop_signal_info['signal_type'],
                'details': {
                    'limit_up': limit_up_quality,
                    'retrace': retrace_info,
                    'support': support_info,
                    'volume': volume_info,
                    'stop_signal': stop_signal_info
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
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['volume_ma3'] = df['volume'].rolling(window=3).mean()
        return df
    
    def _find_recent_limit_up(self, df: pd.DataFrame) -> Optional[Dict]:
        """查找近期涨停"""
        lookback = 5  # 查看5个交易日
        
        for i in range(1, min(lookback + 1, len(df))):
            idx = len(df) - i
            if idx < 1:
                continue
            
            row = df.iloc[idx]
            prev_row = df.iloc[idx - 1]
            
            # 计算涨幅
            if 'pct_change' in row:
                change_pct = row['pct_change']
            else:
                change_pct = (row['close'] - prev_row['close']) / prev_row['close'] * 100
            
            # 判断是否涨停（>=9.5%）
            if change_pct >= 9.5:
                return {
                    'date': row.get('date', idx),
                    'price': row['close'],
                    'change_pct': change_pct,
                    'volume': row['volume'],
                    'index': idx
                }
        
        return None
    
    def _analyze_retrace(self, df: pd.DataFrame, limit_up_info: Dict) -> Dict:
        """分析回调情况"""
        latest = df.iloc[-1]
        limit_up_price = limit_up_info['price']
        current_price = latest['close']
        
        # 计算回调幅度
        retrace_pct = (limit_up_price - current_price) / limit_up_price * 100
        
        # 计算回调天数
        retrace_days = len(df) - limit_up_info['index'] - 1
        
        # 判断是否在回调
        is_retracing = 0 < retrace_pct <= 15 and retrace_days >= 1
        
        # 评分
        if retrace_pct <= 5:
            score = 100
        elif retrace_pct <= 10:
            score = 85
        elif retrace_pct <= 15:
            score = 70
        else:
            score = 0
        
        return {
            'is_retracing': is_retracing,
            'retrace_pct': retrace_pct,
            'retrace_days': retrace_days,
            'limit_up_price': limit_up_price,
            'current_price': current_price,
            'score': score
        }
    
    def _analyze_support(self, df: pd.DataFrame, limit_up_info: Dict, retrace_info: Dict) -> Dict:
        """分析支撑位"""
        latest = df.iloc[-1]
        current_price = latest['close']
        
        # 可能的支撑位
        support_levels = [
            ('涨停价', limit_up_info['price']),
            ('MA5', latest['MA5']),
            ('前高', df['close'].rolling(window=20).max().iloc[-5] if len(df) >= 5 else latest['close'])
        ]
        
        # 找到最近的支撑位
        closest_support = None
        min_distance = float('inf')
        
        for level_name, level_price in support_levels:
            if pd.isna(level_price):
                continue
            distance = abs(current_price - level_price) / current_price * 100
            if distance < min_distance:
                min_distance = distance
                closest_support = (level_name, level_price)
        
        # 判断是否回踩支撑位
        is_at_support = min_distance <= 2  # 2%容忍度
        
        # 评分
        if closest_support and closest_support[0] == '涨停价' and min_distance <= 1:
            score = 100
        elif closest_support and closest_support[0] == '涨停价':
            score = 85
        elif is_at_support:
            score = 70
        else:
            score = max(0, 70 - min_distance * 10)
        
        return {
            'level': closest_support[0] if closest_support else None,
            'price': closest_support[1] if closest_support else None,
            'distance': round(min_distance, 2),
            'is_at_support': is_at_support,
            'score': score
        }
    
    def _analyze_volume(self, df: pd.DataFrame, retrace_info: Dict) -> Dict:
        """分析成交量"""
        latest = df.iloc[-1]
        volume_ma3 = latest['volume_ma3']
        
        if volume_ma3 == 0 or pd.isna(volume_ma3):
            return {'shrink_ratio': 1, 'score': 0}
        
        shrink_ratio = latest['volume'] / volume_ma3
        
        # 评分
        if shrink_ratio < 0.3:
            score = 100
        elif shrink_ratio < 0.4:
            score = 85
        elif shrink_ratio < 0.5:
            score = 70
        else:
            score = max(0, 100 - (shrink_ratio - 0.5) * 200)
        
        return {
            'shrink_ratio': shrink_ratio,
            'current_volume': latest['volume'],
            'volume_ma3': volume_ma3,
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
        
        # 判断锤子线
        is_hammer = lower_shadow > body * 2 and upper_shadow < body * 0.5
        
        # 判断十字星
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
    
    def _evaluate_limit_up_quality(self, limit_up_info: Dict) -> Dict:
        """评估涨停质量"""
        change_pct = limit_up_info['change_pct']
        
        # 根据涨停类型评分
        if change_pct >= 10:  # 一字板或T字板
            quality = 'excellent'
            score = 100
        elif change_pct >= 9.8:
            quality = 'good'
            score = 85
        elif change_pct >= 9.5:
            quality = 'fair'
            score = 70
        else:
            quality = 'poor'
            score = 50
        
        return {
            'quality': quality,
            'change_pct': change_pct,
            'score': score
        }
    
    def _calculate_score(self, limit_up_quality: Dict, retrace_info: Dict,
                        support_info: Dict, volume_info: Dict, stop_signal_info: Dict) -> float:
        """计算综合得分"""
        total_score = (
            limit_up_quality['score'] * self.weights['limit_up_quality'] +
            retrace_info['score'] * self.weights['retrace_quality'] +
            support_info['score'] * self.weights['support_strength'] +
            volume_info['score'] * self.weights['volume_shrink'] +
            stop_signal_info['score'] * self.weights['stop_signal']
        )
        return total_score


if __name__ == '__main__':
    # 测试
    analyzer = LimitUpRetraceAnalyzer(data_source='baostock')
    result = analyzer.analyze_stock('000001', '平安银行')
    if result:
        print(f"股票: {result['stock_name']}")
        print(f"信号: {result['signal']}")
        print(f"得分: {result['score']}")
        print(f"涨停日期: {result['limit_up_date']}")
        print(f"回调幅度: {result['retrace_pct']}%")
    else:
        print("不符合条件")
