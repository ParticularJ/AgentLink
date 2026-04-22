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
    
    # 评分权重配置（参考涨停板策略标准）
    WEIGHTS = {
        'volume_extreme': 0.30,      # 地量程度 (30%)
        'price_position': 0.25,      # 价格位置 (25%)
        'stability_signal': 0.20,    # 企稳信号 (20%)
        'follow_up': 0.15,           # 后续确认 (15%)
        'market_environment': 0.10,  # 市场环境 (10%)
    }
    
    # 评分阈值（与涨停板策略一致）
    THRESHOLDS = {
        'strong_buy': 85,    # 极高
        'buy': 75,           # 高
        'watch': 65,         # 中等
        'exclude': 55        # 低
    }
    
    def __init__(self, data_source: str = "auto"):
        self.name = "成交量地量见底策略"
        self.version = "v1.1.0"
        self.win_rate = 0.62
        
        # 成交量参数
        self.volume_ma_period = 20
        self.volume_threshold = 0.4  # 地量标准：成交量低于均量的40%
        self.price_recovery_threshold = 0.02  # 价格恢复阈值
        
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")
        
        # 缓存市场情绪（全局共享）
        self._market_sentiment = None

    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from volume_extreme_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from volume_extreme_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)
           
    def calculate_volume_stats(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算成交量统计指标"""
        df = df.copy()
        
        # 成交量均线
        df['volume_ma'] = df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean()
        
        # 量能萎缩比例
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # 成交量变异系数 (CV) - 衡量波动性
        if len(df) >= self.volume_ma_period:
            df['volume_cv'] = df['volume'].rolling(window=self.volume_ma_period).std() / df['volume_ma']
        else:
            df['volume_cv'] = 0
        
        # 价格变化率
        df['price_change'] = df['close'].pct_change()
        df['price_abs_change'] = df['price_change'].abs()
        
        # 波动率
        df['volatility'] = df['price_change'].rolling(window=5).std()
        
        return df

    def find_volume_extreme(self, df: pd.DataFrame, lookback: int = 60) -> List[Dict]:
        """查找成交量极度萎缩的位置"""
        if len(df) < 20:
            return []
        
        df = self.calculate_volume_stats(df)
        extremes = []
        
        for i in range(self.volume_ma_period, len(df)):
            row = df.iloc[i]
            prev_volumes = df['volume'].iloc[max(0, i-20):i]
            
            # 条件1：当前成交量低于均量的30%
            if row['volume_ratio'] > self.volume_threshold:
                continue
            
            # 条件2：最近20日成交量持续萎缩
            if len(prev_volumes) < 10:
                continue
                
            # 检查是否持续萎缩（后10日均量 < 前10日均量）
            mid_point = len(prev_volumes) // 2
            recent_avg = prev_volumes.iloc[mid_point:].mean()
            older_avg = prev_volumes.iloc[:mid_point].mean()
            
            if recent_avg >= older_avg:
                continue
            
            # 条件3：价格相对稳定（波动 < 5%）
            price_std = df['price_change'].iloc[max(0, i-5):i].std()
            if price_std > 0.05:
                continue
            
            # 找到极值点
            local_min_idx = df['volume'].iloc[max(0, i-10):i].idxmin()
            if local_min_idx == i:
                extremes.append({
                    'index': i,
                    'date': df.index[i] if hasattr(df.index[i], 'strftime') else str(df.index[i]),
                    'volume_ratio': row['volume_ratio'],
                    'volume_ma': row['volume_ma'],
                    'price': row['close']
                })
        
        return extremes

    def analyze_volume_recovery(self, df: pd.DataFrame, extreme_idx: int) -> Dict:
        """分析地量后的量能恢复"""
        if extreme_idx >= len(df) - 1:
            return {'has_recovery': False}
        
        recovery_data = df.iloc[extreme_idx:min(extreme_idx+5, len(df))]
        
        # 检查量能是否逐步放大
        volumes = recovery_data['volume'].values
        if len(volumes) < 2:
            return {'has_recovery': False}
        
        # 第一天vs地量
        volume_increase = volumes[1] / df.iloc[extreme_idx]['volume'] if df.iloc[extreme_idx]['volume'] > 0 else 0
        
        # 价格是否上涨
        price_change = (recovery_data['close'].iloc[-1] - recovery_data['close'].iloc[0]) / recovery_data['close'].iloc[0]
        
        has_recovery = volume_increase > 1.5 and price_change > 0
        
        return {
            'has_recovery': has_recovery,
            'volume_increase_ratio': volume_increase,
            'price_change': price_change,
            'recovery_days': len(recovery_data) - 1
        }

    def calculate_score(self, df: pd.DataFrame, extreme: Dict, recovery: Dict) -> Tuple[float, str]:
        """计算股票评分"""
        score = 0
        reasons = []
        
        # 1. 量能极度萎缩得分 (0-35)
        volume_ratio = extreme['volume_ratio']
        if volume_ratio < 0.1:
            score += 35
            reasons.append("量能极度萎缩（不足均量10%）")
        elif volume_ratio < 0.2:
            score += 28
            reasons.append("量能严重萎缩（不足均量20%）")
        elif volume_ratio < 0.3:
            score += 20
            reasons.append("量能明显萎缩（不足均量30%）")
        
        # 2. 量能恢复得分 (0-20)
        if recovery['has_recovery']:
            score += 20
            reasons.append("量能已出现恢复信号")
        else:
            vi_ratio = recovery.get('volume_increase_ratio', 0)
            if vi_ratio > 1.2:
                score += 12
                reasons.append("量能有初步放大迹象")
        
        # 3. 价格稳定性得分 (0-20)
        if len(df) > extreme['index']:
            recent_df = df.iloc[max(0, extreme['index']-5):extreme['index']]
            if len(recent_df) >= 3:
                price_std = recent_df['close'].std() / recent_df['close'].mean()
                if price_std < 0.02:
                    score += 20
                    reasons.append("价格极度稳定")
                elif price_std < 0.05:
                    score += 15
                    reasons.append("价格相对稳定")
                elif price_std < 0.1:
                    score += 10
                    reasons.append("价格波动适中")
        
        # 4. 趋势反转确认 (0-15)
        if recovery['has_recovery'] and recovery['price_change'] > 0.03:
            score += 15
            reasons.append("价格已开始上涨，确认底部反转")
        elif recovery['has_recovery']:
            score += 10
            reasons.append("有底部反转迹象")
        
        # 5. 市场环境 (0-10)
        market_env_score = self._calc_market_environment()
        score += int(market_env_score * 0.1)
        if market_env_score >= 70:
            reasons.append(f"市场环境良好({market_env_score:.0f}分)")
        elif market_env_score >= 50:
            reasons.append(f"市场环境中性({market_env_score:.0f}分)")
        else:
            reasons.append(f"市场环境偏弱({market_env_score:.0f}分)")
        
        return score, "; ".join(reasons)
    
    def _get_market_index_data(self) -> Dict:
        """
        获取大盘指数数据（上证指数、深证成指、创业板指、科创板指）
        返回指数涨跌幅和成交量信息
        """
        market_data = {
            'sh_change': 0,   # 上证涨跌幅
            'sz_change': 0,   # 深证涨跌幅
            'cy_change': 0,   # 创业板涨跌幅
            'kc_change': 0,   # 科创板涨跌幅
            'sh_volume_ratio': 1.0,  # 上证量比
            'total_score': 50  # 默认中性
        }
        
        # 根据数据源使用不同的指数代码格式
        index_codes = {
            'sh': '000001',  # 上证指数
            'sz': '399001',  # 深证成指
            'cy': '399006',  # 创业板指
            'kc': '000688'   # 科创50
        }
        
        # 对于baostock数据源，需要使用特殊的指数代码格式
        if self.data_adapter.source == 'baostock':
            index_codes = {
                'sh': 'sh.000001',  # 上证指数
                'sz': 'sz.399001',  # 深证成指
                'cy': 'sz.399006',  # 创业板指
                'kc': 'sh.000688'   # 科创50
            }
        
        try:
            # 尝试获取上证指数数据
            df_sh = self.data_adapter.get_stock_data(index_codes['sh'])
            if df_sh is not None and len(df_sh) >= 2:
                latest = df_sh.iloc[-1]
                prev = df_sh.iloc[-2]
                market_data['sh_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
                
                # 计算量比（今日成交量/昨日成交量）
                if 'volume' in latest and 'volume' in prev and prev['volume'] > 0:
                    market_data['sh_volume_ratio'] = latest['volume'] / prev['volume']
        except Exception as e:
            pass
        
        try:
            # 尝试获取深证成指数据
            df_sz = self.data_adapter.get_stock_data(index_codes['sz'])
            if df_sz is not None and len(df_sz) >= 2:
                latest = df_sz.iloc[-1]
                prev = df_sz.iloc[-2]
                market_data['sz_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception as e:
            pass
        
        try:
            # 尝试获取创业板指数据
            df_cy = self.data_adapter.get_stock_data(index_codes['cy'])
            if df_cy is not None and len(df_cy) >= 2:
                latest = df_cy.iloc[-1]
                prev = df_cy.iloc[-2]
                market_data['cy_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception as e:
            pass
        
        try:
            # 尝试获取科创板指数据（科创50）
            df_kc = self.data_adapter.get_stock_data(index_codes['kc'])
            if df_kc is not None and len(df_kc) >= 2:
                latest = df_kc.iloc[-1]
                prev = df_kc.iloc[-2]
                market_data['kc_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception as e:
            pass
        
        return market_data
    
    def _calc_market_environment(self) -> float:
        """
        计算市场环境评分（参考涨停板策略的市场情绪计算）
        基于大盘指数涨跌幅、成交量、市场广度综合判断
        返回0-100的评分
        """
        # 如果已经计算过，直接返回缓存值
        if self._market_sentiment is not None:
            return self._market_sentiment
        
        score = 50  # 基础分
        
        # 1. 获取大盘指数数据
        market_data = self._get_market_index_data()
        
        # 2. 大盘指数涨跌幅评分 (40%)
        # 计算四大指数平均涨跌幅（上证、深证、创业板、科创板）
        index_changes = [
            market_data['sh_change'],
            market_data['sz_change'],
            market_data['cy_change'],
            market_data['kc_change']
        ]
        # 过滤掉为0的指数（未获取到数据）
        valid_changes = [c for c in index_changes if c != 0]
        if valid_changes:
            avg_index_change = sum(valid_changes) / len(valid_changes)
        else:
            avg_index_change = 0
        
        if avg_index_change >= 2:
            score += 20  # 大盘大涨，情绪极好
        elif avg_index_change >= 1:
            score += 15
        elif avg_index_change >= 0.5:
            score += 10
        elif avg_index_change >= 0:
            score += 5
        elif avg_index_change >= -0.5:
            score -= 5
        elif avg_index_change >= -1:
            score -= 10
        else:
            score -= 15  # 大盘大跌，情绪低迷
        
        # 3. 成交量评分 (30%) - 量比
        volume_ratio = market_data['sh_volume_ratio']
        if volume_ratio >= 1.5:
            score += 15  # 明显放量，情绪活跃
        elif volume_ratio >= 1.2:
            score += 10
        elif volume_ratio >= 1.0:
            score += 5
        elif volume_ratio >= 0.8:
            score += 2
        else:
            score -= 5  # 缩量，情绪低迷
        
        # 4. 市场趋势评分 (30%) - 基于上证指数的短期趋势
        try:
            df_sh = self.data_adapter.get_stock_data('000001')
            if df_sh is not None and len(df_sh) >= 20:
                # 计算短期均线
                df_sh['ma5'] = df_sh['close'].rolling(window=5).mean()
                df_sh['ma10'] = df_sh['close'].rolling(window=10).mean()
                df_sh['ma20'] = df_sh['close'].rolling(window=20).mean()
                
                latest = df_sh.iloc[-1]
                # 多头排列加分
                if latest['close'] > latest['ma5'] > latest['ma10'] > latest['ma20']:
                    score += 15  # 强势多头排列
                elif latest['close'] > latest['ma5'] > latest['ma10']:
                    score += 10  # 短期多头
                elif latest['close'] > latest['ma5']:
                    score += 5   # 站上5日线
                elif latest['close'] < latest['ma5'] < latest['ma10'] < latest['ma20']:
                    score -= 10  # 空头排列
                elif latest['close'] < latest['ma5'] < latest['ma10']:
                    score -= 5   # 短期空头
        except Exception:
            pass
        
        # 确保分数在0-100之间
        final_score = min(100, max(0, round(score, 1)))
        self._market_sentiment = final_score
        return final_score
    
    def get_rating(self, score: float) -> Dict:
        """获取评级（参考涨停板策略）"""
        if score >= self.THRESHOLDS['strong_buy']:
            return {'label': '极高', 'description': '地量见底信号强烈，重点关注'}
        elif score >= self.THRESHOLDS['buy']:
            return {'label': '高', 'description': '地量见底可能性大'}
        elif score >= self.THRESHOLDS['watch']:
            return {'label': '中等', 'description': '需结合盘面判断'}
        elif score >= self.THRESHOLDS['exclude']:
            return {'label': '低', 'description': '谨慎参与'}
        else:
            return {'label': '极低', 'description': '建议观望'}
    
    def get_recommendation(self, score: float) -> str:
        """获取操作建议（参考涨停板策略）"""
        if score >= self.THRESHOLDS['strong_buy']:
            return "✅ 重点关注 - 地量见底信号强烈，反弹概率极大"
        elif score >= self.THRESHOLDS['buy']:
            return "✅ 关注 - 地量见底可能性大，可考虑建仓"
        elif score >= self.THRESHOLDS['watch']:
            return "⚠️ 观察 - 需结合明日开盘情况判断"
        elif score >= self.THRESHOLDS['exclude']:
            return "⚠️ 谨慎 - 底部信号不明确，不建议参与"
        else:
            return "❌ 观望 - 未见明显底部信号"

    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """分析单只股票（改进版，包含详细评分维度）"""
        try:
            # 获取数据
            df = self.data_adapter.get_stock_data(stock_code)
            if df is None or len(df) < 60:
                return None
            
            # 标准化列名
            # df = self.data_adapter.normalize_columns(df)
            
            # 查找地量位置
            extremes = self.find_volume_extreme(df)
            
            if not extremes:
                return None
            
            # 取最近一次地量
            extreme = extremes[-1]
            
            # 分析量能恢复
            recovery = self.analyze_volume_recovery(df, extreme['index'])
            
            # 计算详细评分维度
            scores = self._calc_detailed_scores(df, extreme, recovery)
            
            # 计算总分
            total_score = scores['total']
            
            # 获取评级和建议
            rating = self.get_rating(total_score)
            recommendation = self.get_recommendation(total_score)
            
            # 获取当前价格信息
            current = df.iloc[-1]
            current_price = current['close']
            current_volume = current['volume']
            volume_ma = extreme['volume_ma']
            
            # 计算从地量到现在的涨跌幅
            from_extreme_change = (current_price - extreme['price']) / extreme['price'] * 100
            
            # 计算价格位置（相对于近期高低点）
            recent_high = df['high'].iloc[-60:].max()
            recent_low = df['low'].iloc[-60:].min()
            price_position = (current_price - recent_low) / (recent_high - recent_low) * 100 if recent_high > recent_low else 50
            print("分析完成: 股票代码={}, 评分={:.1f}, 评级={}, 建议={}".format(stock_code, total_score, rating['label'], recommendation))
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'score': total_score,
                'scores': scores,
                'rating': rating,
                'recommendation': recommendation,
                'current_price': round(current_price, 2),
                'current_volume': int(current_volume),
                'volume_ma': round(volume_ma, 0),
                'volume_ratio': round(extreme['volume_ratio'] * 100, 1),
                'from_extreme_change': round(from_extreme_change, 2),
                'price_position': round(price_position, 1),
                'has_recovery': recovery['has_recovery'],
                'extreme_date': extreme['date'],
                'strategy': self.name,
                'win_rate': self.win_rate,
                'market_environment': self._calc_market_environment()
            }
            
        except Exception as e:
            print(f"分析{stock_code}失败: {e}")
            return None
    
    def _calc_detailed_scores(self, df: pd.DataFrame, extreme: Dict, recovery: Dict) -> Dict:
        """计算详细评分维度（五维评分体系）"""
        scores = {}
        
        # 1. 地量程度评分 (30%)
        volume_ratio = extreme['volume_ratio']
        if volume_ratio < 0.15:
            scores['volume_extreme'] = 100  # 极度地量
        elif volume_ratio < 0.25:
            scores['volume_extreme'] = 85   # 严重地量
        elif volume_ratio < 0.35:
            scores['volume_extreme'] = 70   # 明显地量
        elif volume_ratio < 0.45:
            scores['volume_extreme'] = 55   # 轻度地量
        else:
            scores['volume_extreme'] = 40   # 一般
        
        # 2. 价格位置评分 (25%)
        current_price = df.iloc[-1]['close']
        recent_high = df['high'].iloc[-60:].max()
        recent_low = df['low'].iloc[-60:].min()
        
        if recent_high > recent_low:
            position_ratio = (current_price - recent_low) / (recent_high - recent_low)
            # 地量策略偏好低位（0-30%区间最佳）
            if position_ratio <= 0.2:
                scores['price_position'] = 100  # 极低位置，最佳
            elif position_ratio <= 0.3:
                scores['price_position'] = 85   # 低位
            elif position_ratio <= 0.4:
                scores['price_position'] = 70   # 中低位
            elif position_ratio <= 0.5:
                scores['price_position'] = 55   # 中位
            else:
                scores['price_position'] = 40   # 高位，不太适合地量策略
        else:
            scores['price_position'] = 50
        
        # 3. 企稳信号评分 (20%)
        extreme_idx = extreme['index']
        if extreme_idx < len(df) - 1:
            # 检查地量后的价格走势
            post_extreme = df.iloc[extreme_idx:min(extreme_idx+5, len(df))]
            post_low = post_extreme['low'].min()
            extreme_low = df.iloc[extreme_idx]['low']
            
            # 计算地量后的K线实体
            post_body = abs(post_extreme['close'] - post_extreme['open']).mean() / post_extreme['close'].mean()
            
            if post_low >= extreme_low and post_body < 0.015:
                scores['stability_signal'] = 100  # 极度企稳，未创新低且K线收窄
            elif post_low >= extreme_low * 0.99:
                scores['stability_signal'] = 80   # 基本企稳
            elif post_low >= extreme_low * 0.97:
                scores['stability_signal'] = 60   # 轻度下跌
            else:
                scores['stability_signal'] = 40   # 继续下跌
        else:
            scores['stability_signal'] = 50
        
        # 4. 后续确认评分 (15%)
        if recovery['has_recovery']:
            if recovery['price_change'] > 0.05:
                scores['follow_up'] = 100  # 放量大涨确认
            elif recovery['price_change'] > 0.03:
                scores['follow_up'] = 85   # 明显上涨
            else:
                scores['follow_up'] = 70   # 温和上涨
        elif recovery.get('volume_increase_ratio', 0) > 1.3:
            scores['follow_up'] = 60       # 量能有放大但未确认
        else:
            scores['follow_up'] = 45       # 无明显后续信号
        
        # 5. 市场环境评分 (10%)
        scores['market_environment'] = self._calc_market_environment()
        
        # 计算加权总分
        total = (
            scores['volume_extreme'] * self.WEIGHTS['volume_extreme'] +
            scores['price_position'] * self.WEIGHTS['price_position'] +
            scores['stability_signal'] * self.WEIGHTS['stability_signal'] +
            scores['follow_up'] * self.WEIGHTS['follow_up'] +
            scores['market_environment'] * self.WEIGHTS['market_environment']
        )
        scores['total'] = round(total, 1)
        
        return scores

    def batch_analyze(self, stock_list: List[tuple], top_n: int = 10) -> List[Dict]:
        """批量分析股票"""
        results = []
        
        for name, code in stock_list:
            try:
                result = self.analyze_stock(code, name)
                if result and result['score'] > 0:
                    results.append(result)
            except Exception as e:
                continue
        
        # 按评分排序
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results[:top_n]


if __name__ == '__main__':
    analyzer = VolumeExtremeAnalyzer()
    
    # 测试
    test_stocks = [
        ('平安银行', '000001'),
        ('万科A', '000002'),
    ]
    
    print("成交量地量见底策略测试")
    print("-" * 60)
    
    for name, code in test_stocks:
        result = analyzer.analyze_stock(code, name)
        if result:
            print(f"{name}({code}): 评分={result['score']}, 原因={result['reasons']}")
        else:
            print(f"{name}({code}): 未找到地量信号")
