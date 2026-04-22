#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
缺口回补分析器
识别和分析突破性缺口及回踩买入机会
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


class GapFillAnalyzer:
    """缺口回补分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "缺口回补策略"
        self.version = "v1.0.0"
        self.win_rate = 0.62
        
        # 缺口参数
        self.min_gap_pct = 3.0
        self.strong_gap_pct = 5.0
        self.lookback_days = 30
        
        # 成交量参数
        self.min_volume_ratio = 1.5
        
        # 评分权重（调整后：满分100分制）
        self.weights = {
            'gap_quality': 0.25,       # 缺口质量 25%
            'pullback_confirm': 0.25,   # 回踩确认 25%
            'trend_cooperation': 0.20,   # 趋势配合 20%
            'follow_up': 0.15,          # 后续走势 15%
            'market_environment': 0.15  # 市场环境 15%
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
        
    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from gap_fill_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from gap_fill_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)     
       
    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """分析单只股票是否出现缺口回踩机会"""
        try:
            # 获取数据
            df = self._get_stock_data(stock_code)
            if df is None or len(df) < 50:
                return None
            
            # 计算指标
            df = self._calculate_indicators(df)
            
            # 查找突破性缺口
            gap_info = self._find_breakthrough_gap(df)
            
            if not gap_info:
                return None
            
            # 分析缺口质量
            gap_analysis = self._analyze_gap_quality(df, gap_info)
            
            # 分析回踩确认
            pullback_analysis = self._analyze_pullback(df, gap_info)
            
            # 分析趋势配合
            trend_analysis = self._analyze_trend(df)
            
            # 分析后续走势
            follow_up_analysis = self._analyze_follow_up(df, gap_info)
            
            # 计算市场环境
            market_env = self._calc_market_environment()
            
            # 计算综合得分
            total_score = self._calculate_score(
                gap_analysis, pullback_analysis, trend_analysis, follow_up_analysis, market_env
            )
            
            # 判断是否出现买入信号（100分制）
            if total_score < 55:
                return None
            
            # 生成信号
            signal = '强烈买入' if total_score >= 85 else '买入' if total_score >= 70 else '观望'
            
            latest = df.iloc[-1]
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'signal': signal,
                'score': round(total_score, 2),
                'current_price': round(latest['close'], 2),
                'gap_type': gap_info['type'],
                'gap_size': round(gap_info['size'], 2),
                'gap_date': gap_info['date'],
                'gap_low': round(gap_info['gap_low'], 2),
                'gap_high': round(gap_info['gap_high'], 2),
                'pullback_confirmed': pullback_analysis['confirmed'],
                'trend_direction': trend_analysis['direction'],
                'details': {
                    'gap': gap_analysis,
                    'pullback': pullback_analysis,
                    'trend': trend_analysis,
                    'follow_up': follow_up_analysis,
                    'market': market_env
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
        # 计算跳空缺口
        df['prev_close'] = df['close'].shift(1)
        df['gap_up'] = (df['low'] - df['prev_close']) / df['prev_close'] * 100
        df['gap_down'] = (df['prev_close'] - df['high']) / df['prev_close'] * 100
        
        # 计算均线
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        
        # 计算成交量均线
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        
        return df
    
    def _find_breakthrough_gap(self, df: pd.DataFrame) -> Optional[Dict]:
        """查找突破性缺口"""
        # 检查最近10天是否有向上跳空缺口
        recent_df = df.tail(10)
        
        for i in range(len(recent_df) - 1, 0, -1):
            idx = len(df) - len(recent_df) + i
            if idx < 1:
                continue
            
            row = recent_df.iloc[i]
            gap_up = row['gap_up']
            
            # 检查是否是向上跳空缺口
            if gap_up >= self.min_gap_pct:
                # 判断缺口类型
                if gap_up >= self.strong_gap_pct:
                    gap_type = '突破性缺口'
                else:
                    gap_type = '普通缺口'
                
                return {
                    'date': df.index[idx] if hasattr(df.index[idx], 'strftime') else str(df.index[idx]),
                    'index': idx,
                    'type': gap_type,
                    'size': gap_up,
                    'gap_low': row['prev_close'],
                    'gap_high': row['low'],
                    'volume': row['volume']
                }
        
        return None
    
    def _analyze_gap_quality(self, df: pd.DataFrame, gap_info: Dict) -> Dict:
        """分析缺口质量（调整后：降低满分，增加基础分）"""
        gap_size = gap_info['size']
        gap_volume = gap_info['volume']
        
        # 获取缺口当天的成交量均线
        gap_idx = gap_info['index']
        if gap_idx < len(df):
            volume_ma5 = df.iloc[gap_idx]['volume_ma5']
            volume_ratio = gap_volume / volume_ma5 if volume_ma5 > 0 else 1
        else:
            volume_ratio = 1
        
        # 评分（满分100，基础分50）
        score = 50  # 基础分
        if gap_size >= self.strong_gap_pct and volume_ratio >= self.min_volume_ratio:
            score = 100
            quality = '强势突破'
        elif gap_size >= self.strong_gap_pct:
            score = 85
            quality = '强缺口'
        elif gap_size >= self.min_gap_pct and volume_ratio >= self.min_volume_ratio:
            score = 75
            quality = '有效突破'
        elif gap_size >= self.min_gap_pct:
            score = 60
            quality = '普通缺口'
        else:
            score = 45
            quality = '弱缺口'
        
        return {
            'score': score,
            'quality': quality,
            'gap_size': gap_size,
            'volume_ratio': volume_ratio
        }
    
    def _analyze_pullback(self, df: pd.DataFrame, gap_info: Dict) -> Dict:
        """分析回踩确认（调整后：降低满分，增加基础分）"""
        latest = df.iloc[-1]
        gap_low = gap_info['gap_low']
        gap_high = gap_info['gap_high']
        current_price = latest['close']
        
        # 检查当前价格是否回踩到缺口区域
        in_gap_zone = gap_low <= current_price <= gap_high
        above_gap = current_price > gap_high
        below_gap = current_price < gap_low
        
        # 检查是否完全回补缺口
        gap_filled = current_price <= gap_low
        
        # 评分（满分100，基础分50）
        score = 50  # 基础分
        if in_gap_zone:
            score = 100
            confirmed = True
            status = '回踩缺口中'
        elif above_gap and (current_price - gap_high) / gap_high < 0.02:
            score = 85
            confirmed = True
            status = '缺口上方企稳'
        elif above_gap:
            score = 70
            confirmed = True
            status = '缺口上方运行'
        elif gap_filled:
            score = 30
            confirmed = False
            status = '缺口已回补'
        else:
            score = 40
            confirmed = True
            status = '在缺口下方运行'
        
        return {
            'score': score,
            'confirmed': confirmed,
            'status': status,
            'in_gap_zone': in_gap_zone,
            'gap_filled': gap_filled,
            'distance_to_gap': round((current_price - gap_low) / gap_low * 100, 2)
        }
    
    def _analyze_trend(self, df: pd.DataFrame) -> Dict:
        """分析趋势配合（调整后：降低满分，增加基础分）"""
        latest = df.iloc[-1]
        
        # 判断均线多头排列
        ma_bullish = latest['MA5'] > latest['MA10'] > latest['MA20']
        
        # 判断短期趋势
        ma5_slope = (latest['MA5'] - df.iloc[-5]['MA5']) / latest['MA5'] * 100 if len(df) >= 5 else 0
        
        # 评分（满分100，基础分40）
        score = 40  # 基础分
        if ma_bullish and ma5_slope > 3:
            score = 100
            direction = '强势上涨'
        elif ma_bullish and ma5_slope > 1.5:
            score = 90
            direction = '多头排列'
        elif ma_bullish and ma5_slope > 1:
            score = 80
            direction = '多头排列'
        elif ma_bullish:
            score = 65
            direction = '均线缠绕'
        elif latest['MA5'] > latest['MA10']:
            score = 50
            direction = '短期向好'
        else:
            score = 30
            direction = '趋势不明'
        
        return {
            'score': score,
            'direction': direction,
            'ma_bullish': ma_bullish,
            'ma5_slope': round(ma5_slope, 2)
        }
    
    def _analyze_follow_up(self, df: pd.DataFrame, gap_info: Dict) -> Dict:
        """分析后续走势（调整后：降低满分，增加基础分）"""
        gap_idx = gap_info['index']
        
        if gap_idx >= len(df) - 1:
            return {'score': 30, 'trend': '刚形成缺口'}
        
        # 检查缺口后的走势
        post_gap = df.iloc[gap_idx:]
        price_change = (post_gap['close'].iloc[-1] - post_gap['close'].iloc[0]) / post_gap['close'].iloc[0] * 100
        
        # 评分（满分100，基础分50）
        score = 50  # 基础分
        if price_change > 5:
            score = 100
            trend = '强势延续'
        elif price_change > 3:
            score = 85
            trend = '稳步上涨'
        elif price_change > 0:
            score = 70
            trend = '小幅上涨'
        elif price_change > -3:
            score = 55
            trend = '横盘整理'
        else:
            score = 35
            trend = '回调中'
        
        return {
            'score': score,
            'trend': trend,
            'price_change': round(price_change, 2)
        }
    
    def _get_index_code(self, index_name: str) -> str:
        """
        获取指数代码（根据数据源自动调整格式）
        """
        # 基础代码
        codes = {
            'sh': '000001',  # 上证指数
            'sz': '399001',  # 深证成指
            'cy': '399006',  # 创业板指
            'kc': '000688'   # 科创50
        }
        
        # 对于baostock数据源，需要使用特殊的指数代码格式
        if self.data_adapter.source == 'baostock':
            codes = {
                'sh': 'sh.000001',  # 上证指数
                'sz': 'sz.399001',  # 深证成指
                'cy': 'sz.399006',  # 创业板指
                'kc': 'sh.000688'   # 科创50
            }
        
        return codes.get(index_name, '000001')
    
    def _calc_market_environment(self) -> Dict:
        """
        计算市场环境得分 (满分100，基础分50)
        参考涨停板连板策略，基于大盘指数和成交量
        """
        try:
            score = 50  # 基础分
            index_changes = []
            
            # 获取上证指数数据
            df_sh = self.data_adapter.get_stock_data(self._get_index_code('sh'))
            if df_sh is not None and len(df_sh) >= 2:
                latest = df_sh.iloc[-1]
                prev = df_sh.iloc[-2]
                sh_change = (latest['close'] - prev['close']) / prev['close'] * 100
                index_changes.append(sh_change)
                
                if sh_change >= 1:
                    score += 10
                elif sh_change >= 0.5:
                    score += 6
                elif sh_change >= 0:
                    score += 3
                elif sh_change >= -0.5:
                    score -= 3
                else:
                    score -= 8
                
                # 成交量评分
                if 'volume' in latest and 'volume' in prev and prev['volume'] > 0:
                    vol_ratio = latest['volume'] / prev['volume']
                    if vol_ratio >= 1.5:
                        score += 6
                    elif vol_ratio >= 1.2:
                        score += 3
                    elif vol_ratio < 0.8:
                        score -= 4
            
            # 获取深证成指数据
            df_sz = self.data_adapter.get_stock_data(self._get_index_code('sz'))
            if df_sz is not None and len(df_sz) >= 2:
                latest = df_sz.iloc[-1]
                prev = df_sz.iloc[-2]
                sz_change = (latest['close'] - prev['close']) / prev['close'] * 100
                index_changes.append(sz_change)
                
                if sz_change >= 1:
                    score += 8
                elif sz_change >= 0:
                    score += 4
                elif sz_change < -1:
                    score -= 5
            
            # 获取创业板指数据
            df_cy = self.data_adapter.get_stock_data(self._get_index_code('cy'))
            if df_cy is not None and len(df_cy) >= 2:
                latest = df_cy.iloc[-1]
                prev = df_cy.iloc[-2]
                cy_change = (latest['close'] - prev['close']) / prev['close'] * 100
                index_changes.append(cy_change)
                
                if cy_change >= 1.5:
                    score += 8
                elif cy_change >= 0.5:
                    score += 4
                elif cy_change < -1.5:
                    score -= 5
            
            # 获取科创板指数据
            df_kc = self.data_adapter.get_stock_data(self._get_index_code('kc'))
            if df_kc is not None and len(df_kc) >= 2:
                latest = df_kc.iloc[-1]
                prev = df_kc.iloc[-2]
                kc_change = (latest['close'] - prev['close']) / prev['close'] * 100
                index_changes.append(kc_change)
                
                if kc_change >= 1.5:
                    score += 6
                elif kc_change >= 0:
                    score += 3
                elif kc_change < -1.5:
                    score -= 6
            
            # 计算平均涨跌
            if index_changes:
                avg_change = sum(index_changes) / len(index_changes)
                if avg_change >= 1:
                    score += 5
                elif avg_change < -0.5:
                    score -= 5
            
            final_score = max(20, min(100, score))
            
            return {
                'score': final_score,
                'sh_change': sh_change if df_sh is not None else 0,
                'sz_change': sz_change if df_sz is not None else 0,
                'cy_change': cy_change if df_cy is not None else 0,
                'kc_change': kc_change if df_kc is not None else 0,
                'avg_change': sum(index_changes)/len(index_changes) if index_changes else 0
            }
        except Exception as e:
            return {'score': 50, 'sh_change': 0, 'sz_change': 0, 'cy_change': 0, 'kc_change': 0, 'avg_change': 0}
    
    def _calculate_score(self, gap_analysis: Dict, pullback_analysis: Dict,
                        trend_analysis: Dict, follow_up_analysis: Dict,
                        market_env: Dict = None) -> float:
        """计算综合得分（调整后：加入市场环境维度）"""
        market_score = market_env['score'] if market_env else 15
        
        total_score = (
            gap_analysis['score'] * self.weights['gap_quality'] +
            pullback_analysis['score'] * self.weights['pullback_confirm'] +
            trend_analysis['score'] * self.weights['trend_cooperation'] +
            follow_up_analysis['score'] * self.weights['follow_up'] +
            market_score * self.weights['market_environment']
        )
        return total_score


if __name__ == '__main__':
    # 测试
    analyzer = GapFillAnalyzer(data_source='baostock')
    result = analyzer.analyze_stock('000001', '平安银行')
    if result:
        print(f"股票: {result['stock_name']}")
        print(f"信号: {result['signal']}")
        print(f"得分: {result['score']}")
        print(f"缺口类型: {result['gap_type']}")
        print(f"缺口大小: {result['gap_size']}%")
    else:
        print("未检测到缺口回踩信号")
