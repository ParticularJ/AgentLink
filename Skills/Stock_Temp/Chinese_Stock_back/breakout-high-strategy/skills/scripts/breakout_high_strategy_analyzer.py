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
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../ma-bullish-strategy/skills/scripts')
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        # 备选：从项目根目录相对导入
        sys.path.insert(0, os.path.join(os.getcwd(), 'ma-bullish-strategy/skills/scripts'))
        from data_source_adapter import DataSourceAdapter


class BreakoutHighAnalyzer:
    """突破前期高点分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "突破前期高点策略"
        self.version = "v1.1.1"
        self.win_rate = 0.68
        
        # 突破参数
        self.lookback_days = 60
        self.breakout_threshold = 0.02  # 突破确认阈值 2%
        self.volume_multiplier = 1.5  # 成交量放大倍数
        
        # 评分权重 (整合后)
        self.weights = {
            'breakout_strength': 0.25,    # 突破强度
            'volume_confirm': 0.20,       # 量能确认
            'trend_cooperation': 0.20,    # 趋势配合
            'pattern_quality': 0.15,      # 形态质量
            'pullback_confirmation': 0.10, # 回踩确认
            'market_environment': 0.10    # 市场环境
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")

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
    
    def _analyze_trend(self, df: pd.DataFrame, idx: int) -> Dict:
        """分析趋势配合 - 均线多头排列"""
        if idx < 20:
            return {'score': 0, 'direction': '数据不足', 'ma_bullish': False, 'ma5_slope': 0}
        
        current = df.iloc[idx]
        
        # 判断均线多头排列
        ma_bullish = current['MA5'] > current['MA10'] > current['MA20']
        
        # 判断均线斜率 (5日变化率)
        ma5_5days_ago = df.iloc[idx-5]['MA5'] if idx >= 5 else current['MA5']
        if pd.notna(current['MA5']) and current['MA5'] > 0 and pd.notna(ma5_5days_ago):
            ma5_slope = (current['MA5'] - ma5_5days_ago) / current['MA5'] * 100
        else:
            ma5_slope = 0
        
        # 评分
        if ma_bullish and ma5_slope > 1:
            score = 100
            direction = '强势上涨'
        elif ma_bullish:
            score = 85
            direction = '多头排列'
        elif current['MA5'] > current['MA10']:
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
    
    def _analyze_pullback(self, df: pd.DataFrame, breakout: Dict, idx: int) -> Dict:
        """
        分析回踩确认 - 检查突破后是否回踩前期高点并获得支撑
        """
        previous_high = breakout['highest_price']
        breakout_pct = breakout['breakout_ratio'] * 100
        
        # 检查突破后是否有回踩行为
        days_after_breakout = len(df) - idx - 1
        
        if days_after_breakout >= 2:
            # 有后续数据，检查回踩情况
            subsequent_low = df.iloc[idx+1:]['low'].min()
            pullback_to_support = (subsequent_low - previous_high) / previous_high * 100
            
            if pullback_to_support >= 0:
                confirmed = True
                score = 100
                status = '强势站稳'
            elif pullback_to_support > -2:
                confirmed = True
                score = 90
                status = '回踩支撑'
            elif pullback_to_support > -breakout_pct * 0.5:
                confirmed = True
                score = 70
                status = '部分回踩'
            else:
                confirmed = False
                score = 40
                status = '回踩过深'
        else:
            # 刚突破，还没有足够数据
            if breakout_pct >= 5:
                confirmed = True
                score = 80
                status = '强势突破待确认'
            elif breakout_pct >= 3:
                confirmed = True
                score = 65
                status = '有效突破待确认'
            else:
                confirmed = False
                score = 50
                status = '突破较弱待观察'
        
        return {
            'score': score,
            'confirmed': confirmed,
            'pullback_pct': round(breakout_pct, 2),
            'status': status
        }

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
           

    def find_breakout(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        检查最新交易日是否突破前期高点
        """
        if len(df) < self.lookback_days + 5:
            return None
        
        df = self._calculate_indicators(df)
        
        i = len(df) - 1
        current = df.iloc[i]
        current_price = current['close']
        
        high_window = df['high'].iloc[max(0, i-self.lookback_days):i]
        highest_price = high_window.max()
        
        if current_price <= highest_price * (1 + self.breakout_threshold):
            return None
        
        breakout_ratio = (current_price - highest_price) / highest_price
        
        vol_window = df['volume'].iloc[max(0, i-20):i]
        avg_volume = vol_window.mean()
        current_volume = current['volume']
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        momentum_5d = (current_price - df['close'].iloc[i-5]) / df['close'].iloc[i-5] if i >= 5 else 0
        
        trend_analysis = self._analyze_trend(df, i)
        
        breakout_info = {
            'breakout_price': current_price,
            'highest_price': highest_price,
            'breakout_ratio': breakout_ratio
        }
        pullback_analysis = self._analyze_pullback(df, breakout_info, i)
        
        return {
            'index': i,
            'date': df.index[i] if hasattr(df.index[i], 'strftime') else str(df.index[i]),
            'breakout_price': current_price,
            'highest_price': highest_price,
            'breakout_ratio': breakout_ratio,
            'volume_ratio': volume_ratio,
            'momentum_5d': momentum_5d,
            'volume': current_volume,
            'avg_volume': avg_volume,
            'ma_bullish': trend_analysis['ma_bullish'],
            'ma5_slope': trend_analysis['ma5_slope'],
            'trend_direction': trend_analysis['direction'],
            'pullback_confirmed': pullback_analysis['confirmed'],
            'pullback_status': pullback_analysis['status']
        }

    def calculate_score(self, breakout: Dict, market_data: Dict = None) -> Tuple[float, str]:
        """计算综合评分 - 六维评分系统（使用权重）"""
        reasons = []
        ratio = breakout['breakout_ratio']
        vol_ratio = breakout['volume_ratio']
        
        # 1. 突破强度得分 (权重25%)
        if ratio > 0.08:
            breakout_raw = 100
            reasons.append("突破力度极强(>8%)")
        elif ratio > 0.05:
            breakout_raw = 88
            reasons.append("突破力度较强(>5%)")
        elif ratio > 0.03:
            breakout_raw = 72
            reasons.append("突破力度良好(>3%)")
        else:
            breakout_raw = 48
            reasons.append("突破力度一般")
        breakout_score = breakout_raw * self.weights['breakout_strength']
        
        # 2. 量能确认得分 (权重20%)
        if vol_ratio > 2.0:
            volume_raw = 100
            reasons.append("成交量大幅放大(>2倍)")
        elif vol_ratio > 1.5:
            volume_raw = 85
            reasons.append("成交量明显放大(>1.5倍)")
        elif vol_ratio > 1.2:
            volume_raw = 60
            reasons.append("成交量温和放大")
        else:
            volume_raw = 30
            reasons.append("成交量未明显放大")
        volume_score = volume_raw * self.weights['volume_confirm']
        
        # 3. 趋势配合得分 (权重20%)
        ma_bullish = breakout.get('ma_bullish', False)
        ma5_slope = breakout.get('ma5_slope', 0)
        trend_direction = breakout.get('trend_direction', '趋势不明')
        
        if ma_bullish and ma5_slope > 1:
            trend_raw = 100
        elif ma_bullish:
            trend_raw = 85
        elif breakout.get('momentum_5d', 0) > 0:
            trend_raw = 60
        else:
            trend_raw = 40
        reasons.append(f"趋势{trend_direction}")
        trend_score = trend_raw * self.weights['trend_cooperation']
        
        # 4. 形态质量得分 (权重15%)
        if ratio > 0.05 and vol_ratio > 1.5:
            pattern_raw = 100
            reasons.append("突破形态标准")
        elif ratio > 0.03 and vol_ratio > 1.2:
            pattern_raw = 73
            reasons.append("突破形态尚可")
        else:
            pattern_raw = 40
            reasons.append("突破形态较弱")
        pattern_score = pattern_raw * self.weights['pattern_quality']
        
        # 5. 回踩确认得分 (权重10%)
        pullback_confirmed = breakout.get('pullback_confirmed', False)
        pullback_status = breakout.get('pullback_status', '未知')
        
        if pullback_confirmed:
            if pullback_status in ['强势站稳', '回踩支撑']:
                pullback_raw = 100
            elif pullback_status in ['有效突破', '强势突破待确认']:
                pullback_raw = 80
            else:
                pullback_raw = 65
            reasons.append(f"回踩{pullback_status}")
        else:
            pullback_raw = 30
            reasons.append(f"回踩{pullback_status}")
        pullback_score = pullback_raw * self.weights['pullback_confirmation']
        
        # 6. 市场环境得分 (权重10%)
        market_result = self._calculate_market_environment_score(breakout, market_data)
        market_score = market_result['score'] * 10 * self.weights['market_environment']
        if market_result['reason']:
            reasons.append(market_result['reason'])
        
        total_score = (breakout_score + volume_score + trend_score + 
                      pattern_score + pullback_score + market_score)
        
        return round(total_score, 1), "; ".join(reasons)
    
    def _calculate_market_environment_score(self, breakout: Dict, market_data: Dict = None) -> Dict:
        """计算市场环境得分"""
        score = 0
        reason_parts = []
        
        # 指标1: 突破时的市场整体趋势 (0-4分)
        # 使用5日动量作为市场趋势代理指标
        momentum = breakout.get('momentum_5d', 0)
        if momentum > 0.08:
            score += 4
            reason_parts.append("趋势极强")
        elif momentum > 0.05:
            score += 3
            reason_parts.append("趋势强劲")
        elif momentum > 0.02:
            score += 2
            reason_parts.append("趋势向上")
        elif momentum > 0:
            score += 1
            reason_parts.append("趋势偏弱")
        
        # 指标2: 成交量配合度 (0-3分)
        vol_ratio = breakout.get('volume_ratio', 1)
        if vol_ratio > 2.5:
            score += 3
            reason_parts.append("量能充沛")
        elif vol_ratio > 1.8:
            score += 2
            reason_parts.append("量能充足")
        elif vol_ratio > 1.2:
            score += 1
            reason_parts.append("量能一般")
        
        # 指标3: 突破有效性 (0-3分)
        # 突破幅度与量能的配合度
        breakout_ratio = breakout.get('breakout_ratio', 0)
        if breakout_ratio > 0.05 and vol_ratio > 1.5:
            score += 3
            reason_parts.append("突破有效")
        elif breakout_ratio > 0.03 and vol_ratio > 1.2:
            score += 2
            reason_parts.append("突破较有效")
        elif breakout_ratio > 0.02:
            score += 1
            reason_parts.append("突破较弱")
        
        # 构建原因字符串
        if reason_parts:
            reason = f"市场环境({'/'.join(reason_parts)})"
        else:
            reason = "市场环境不佳"
        
        return {'score': score, 'reason': reason}

    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """分析单只股票"""
        try:
            df = self.data_adapter.get_stock_data(stock_code)
            if df is None or len(df) < self.lookback_days + 5:
                return None
            
            # 标准化列名
            for old_col, new_col in [('收盘价', 'close'), ('Close', 'close'), ('CLOSE', 'close')]:
                if old_col in df.columns and 'close' not in df.columns:
                    df['close'] = df[old_col]
            
            for old_col, new_col in [('最高价', 'high'), ('High', 'high'), ('HIGH', 'high')]:
                if old_col in df.columns and 'high' not in df.columns:
                    df['high'] = df[old_col]
            
            for old_col, new_col in [('成交量', 'volume'), ('Volume', 'volume'), ('vol', 'volume')]:
                if old_col in df.columns and 'volume' not in df.columns:
                    df['volume'] = df[old_col]
            
            breakout = self.find_breakout(df)
            
            if breakout is None:
                return None
            
            score, reasons = self.calculate_score(breakout, None)
            
            current = df.iloc[-1]
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'score': score,
                'reasons': reasons,
                'current_price': round(current['close'], 2),
                'breakout_price': round(breakout['breakout_price'], 2),
                'highest_60d': round(breakout['highest_price'], 2),
                'breakout_ratio': round(breakout['breakout_ratio'] * 100, 2),
                'volume_ratio': round(breakout['volume_ratio'], 2),
                'ma_bullish': breakout.get('ma_bullish', False),
                'trend_direction': breakout.get('trend_direction', '未知'),
                'pullback_confirmed': breakout.get('pullback_confirmed', False),
                'pullback_status': breakout.get('pullback_status', '未知'),
                'strategy': self.name,
                'win_rate': self.win_rate
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
    analyzer = BreakoutHighAnalyzer()
    
    test_stocks = [('平安银行', '000001'), ('东山精密', '002384')]
    
    print(f"{analyzer.name} {analyzer.version} 测试")
    print("=" * 70)
    
    for name, code in test_stocks:
        result = analyzer.analyze_stock(code, name)
        if result:
            print(f"\n【{name}({code})】")
            print(f"  评分: {result['score']:.1f}分")
            print(f"  突破: {result['breakout_ratio']:.2f}% | 量比: {result['volume_ratio']:.2f}")
            print(f"  趋势: {result['trend_direction']} | 均线多头: {'是' if result['ma_bullish'] else '否'}")
            print(f"  回踩: {result['pullback_status']} | 确认: {'是' if result['pullback_confirmed'] else '否'}")
            print(f"  详情: {result['reasons']}")
        else:
            print(f"\n【{name}({code})】: 未发现突破信号")
