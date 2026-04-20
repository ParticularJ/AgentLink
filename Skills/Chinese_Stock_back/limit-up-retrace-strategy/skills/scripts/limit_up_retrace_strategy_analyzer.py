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
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../ma-bullish-strategy/skills/scripts')
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        # 备选：从项目根目录相对导入
        sys.path.insert(0, os.path.join(os.getcwd(), 'ma-bullish-strategy/skills/scripts'))
        from data_source_adapter import DataSourceAdapter


class LimitUpRetraceAnalyzer:
    """涨停板首次回调分析器"""
    
    # 涨停回调综合评分体系（满分100）
    # 回调幅度(35) + 缩量整理(25) + 止跌信号(20) + 近期强度(20)
    # 评分维度:
    #   1. 回调幅度得分 (35分) - 回调8%-15%最佳，过深过浅都不好
    #   2. 缩量得分 (25分) - 缩量30%-70%最佳
    #   3. 止跌信号得分 (20分) - 小阳线/锤子线/十字星
    #   4. 近期强度得分 (20分) - 回调浅+距涨停近
    # 信号阈值: >=85分=强烈买入, >=75分=买入, >=65分=关注

    def __init__(self, data_source: str = "auto"):
        self.name = "涨停板首次回调策略"
        self.version = "v2.0.0"

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
    
    def _calculate_retrace_score(self, retrace_pct: float) -> float:
        """回调幅度得分 (0-35分) 回调8%-15%最佳"""
        if 8 <= retrace_pct <= 15:
            return 35
        elif retrace_pct > 15:
            return max(20, 35 - (retrace_pct - 15) * 1.5)
        elif 5 <= retrace_pct < 8:
            return 20 + (retrace_pct - 5) * 2  # 20-26
        else:
            return max(0, retrace_pct * 3)  # 0-15

    def _calculate_shrink_score(self, shrink_pct: float) -> float:
        """缩量得分 (0-25分) 缩量30%-70%最佳"""
        if 30 <= shrink_pct <= 70:
            return 25
        elif shrink_pct > 70:
            return min(30, 25 + (shrink_pct - 70) * 0.1)
        elif 0 <= shrink_pct < 30:
            return shrink_pct * 0.7  # 0-21
        else:  # 放量为负分
            return max(-10, shrink_pct * 0.3)

    def _calculate_stop_signal_score(self, stop_signal_info: Dict) -> float:
        """止跌信号得分 (0-20分)"""
        signal_type = stop_signal_info.get('signal_type', '无明显信号')
        if signal_type == '锤子线':
            return 20
        elif signal_type == '十字星':
            return 17
        elif signal_type == '小阳线':
            return 15
        else:
            return 8

    def _calculate_recent_strength_score(self, retrace_pct: float, days_since_zt: int) -> float:
        """近期强度得分 (0-20分) 回调浅+距涨停近的更好"""
        if retrace_pct <= 10 and days_since_zt <= 3:
            return 20
        elif retrace_pct <= 15 and days_since_zt <= 5:
            return 15
        elif retrace_pct <= 20 and days_since_zt <= 7:
            return 10
        else:
            return 5
    
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
            
            # 3. 分析成交量（缩量程度）
            volume_info = self._analyze_volume(df, limit_up_info, retrace_info)
            
            # 4. 分析止跌信号
            stop_signal_info = self._analyze_stop_signal(df)
            
            # 5. 新评分体系计算综合得分
            retrace_score = self._calculate_retrace_score(retrace_info['retrace_pct'])
            shrink_score = self._calculate_shrink_score(volume_info['shrink_pct'])
            stop_signal_score = self._calculate_stop_signal_score(stop_signal_info)
            recent_strength_score = self._calculate_recent_strength_score(
                retrace_info['retrace_pct'], retrace_info['days_since_zt']
            )
            
            total_score = retrace_score + shrink_score + stop_signal_score + recent_strength_score
            
            # 判断是否出现买入信号
            if total_score < 65:
                return None
            
            # 生成交易建议
            signal = '强烈买入' if total_score >= 85 else '买入' if total_score >= 75 else '关注'
            
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
                'support_level': retrace_info.get('support_level', '涨停价'),
                'support_price': round(limit_up_info['price'], 2),
                'volume_shrink': round(volume_info['shrink_pct'], 1),
                'stop_signal': stop_signal_info['signal_type'],
                'days_since_zt': retrace_info['days_since_zt'],
                'details': {
                    'retrace_score': round(retrace_score, 1),
                    'shrink_score': round(shrink_score, 1),
                    'stop_signal_score': round(stop_signal_score, 1),
                    'recent_strength_score': round(recent_strength_score, 1),
                    'retrace': retrace_info,
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
        lookback = 10  # 查看10个交易日
        
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
        
        # 计算距涨停天数
        days_since_zt = len(df) - limit_up_info['index'] - 1
        
        # 判断是否在回调
        is_retracing = 0 < retrace_pct <= 25 and days_since_zt >= 1
        
        return {
            'is_retracing': is_retracing,
            'retrace_pct': retrace_pct,
            'days_since_zt': days_since_zt,
            'limit_up_price': limit_up_price,
            'current_price': current_price,
            'support_level': '涨停价'
        }
    
    def _analyze_volume(self, df: pd.DataFrame, limit_up_info: Dict, retrace_info: Dict) -> Dict:
        """分析成交量 - 计算回调期间相对涨停日的缩量程度"""
        latest = df.iloc[-1]
        zt_idx = limit_up_info['index']
        
        # 计算涨停后回调期间的成交量均值
        post_zt = df.iloc[zt_idx+1:].copy()
        if len(post_zt) == 0:
            return {'shrink_pct': 0, 'current_vol': latest['volume'], 'avg_post_vol': 0}
        
        avg_post_vol = post_zt['volume'].mean()
        zt_vol = limit_up_info['volume']
        
        # 缩量程度: (1 - 回调均量/涨停量) * 100
        # 正数=缩量，负数=放量
        shrink_pct = (1 - avg_post_vol / zt_vol) * 100 if zt_vol > 0 else 0
        
        return {
            'shrink_pct': shrink_pct,
            'current_vol': latest['volume'],
            'avg_post_vol': avg_post_vol,
            'zt_vol': zt_vol
        }
    
    def _analyze_support(self, df: pd.DataFrame, limit_up_info: Dict, retrace_info: Dict) -> Dict:
        """分析支撑位（保留兼容）"""
        return {
            'level': '涨停价',
            'price': limit_up_info['price'],
            'distance': round(retrace_info['retrace_pct'], 2),
            'is_at_support': True,
            'score': 0
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
