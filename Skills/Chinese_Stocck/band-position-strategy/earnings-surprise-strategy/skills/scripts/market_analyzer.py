#!/usr/bin/env python3
"""
市场反应分析模块
分析财报发布后的市场反应
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime, timedelta
import akshare as ak



class MarketReactionAnalyzer:
    """市场反应分析器"""
    
    def __init__(self):
        self.name = "市场反应分析"
        self.weights = {
            'price_reaction': 0.40,
            'volume_reaction': 0.30,
            'market_comparison': 0.30
        }
    
    def _get_stock_price(self,stock_code: str, start_date: str, end_date: str):
        """
        获取股票日K线价格数据（给 analyze 函数用）
        :param stock_code: 带前缀股票代码 如 sz002371、sh688041
        :param start_date: 开始日期 如 '20260101'
        :param end_date: 结束日期 如 '20260430'
        :return: DataFrame 日期索引 + 收盘价 + 涨跌幅 + 成交量
        """
        # 去掉前缀 sz/sh，只保留6位数字
        #code = stock_code[2:]
       
        # 获取日K线
        df = ak.stock_zh_a_daily(
            symbol=stock_code,
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"  # 前复权，必须加！
        )
        
        # 整理成 analyze 函数需要的格式
        df.index = pd.to_datetime(df["date"])
        df["pct_change"] =df["close"].pct_change() * 100  # 对应函数需要的列
        df = df[["close", "pct_change", "volume"]]
        return df


    def analyze(self, stock_code: str, earnings: str, price_data: pd.DataFrame = None) -> Dict:
        result = {'score': 50, 'level': 'neutral', 'details': {}}
        try:
            earnings_date = pd.to_datetime(earnings.get('report_date'))
            price_data = self._get_stock_price(earnings.get('stock_code'), 
                                            (earnings_date - timedelta(days=10)).strftime("%Y%m%d"), 
                                            pd.Timestamp.now().strftime("%Y%m%d"))

            mask = price_data.index >= earnings_date
            if not mask.any():
                return result

            post_earnings = price_data[mask]
            if len(post_earnings) < 1:
                return result

            # --------------------------
            # ✅ 修复 1：公告日收益如果是 NaN，用 0 代替
            # --------------------------
            announcement_return = post_earnings.iloc[0]['pct_change'] if 'pct_change' in post_earnings.columns else 0
            if pd.isna(announcement_return):
                announcement_return = 0  

            # 3日收益
            three_day_return = 0
            if len(post_earnings) >= 3:
                start_price = post_earnings.iloc[0]['close']
                end_price = post_earnings.iloc[2]['close']
                three_day_return = (end_price - start_price) / start_price * 100

            # 量能
            volume_change = 0
            if 'volume' in post_earnings.columns and len(post_earnings) > 0:
                avg_volume_pre = price_data[~mask]['volume'].mean() if len(price_data[~mask]) > 0 else 1
                volume_post = post_earnings.iloc[0]['volume']
                volume_change = (volume_post - avg_volume_pre) / avg_volume_pre * 100

            # --------------------------
            # ✅ 修复 2：价格评分更合理
            # --------------------------
            price_score = 50 + (announcement_return * 2) + (three_day_return * 2)
            price_score = min(100, max(0, price_score))

            volume_score = min(100, max(0, 50 + volume_change * 0.5))

            # --------------------------
            # ✅ 修复 3：市场对比暂时固定 50 不影响
            # --------------------------
            total_score = (
                price_score * self.weights['price_reaction'] +
                volume_score * self.weights['volume_reaction'] +
                50 * self.weights['market_comparison']
            )

            # 等级
            if total_score >= 80:
                level = '强烈看好'
            elif total_score >= 65:
                level = '看好'
            elif total_score >= 45:
                level = '中性'
            elif total_score >= 30:
                level = '谨慎'
            else:
                level = '回避'

            result['score'] = round(total_score, 2)
            result['level'] = level
            result['details'] = {
                'announcement_return': round(announcement_return, 2),
                'three_day_return': round(three_day_return, 2),
                'volume_change': round(volume_change, 2),
                'price_score': round(price_score, 2),
                'volume_score': round(volume_score, 2)
            }

        except Exception as e:
            result['error'] = str(e)

        return result
    
    def get_reaction_level_name(self, level: str) -> str:
        """获取反应等级名称"""
        level_names = {
            'strong_positive': '强烈积极',
            'positive': '积极',
            'neutral': '中性',
            'negative': '消极',
            'strong_negative': '强烈消极'
        }
        return level_names.get(level, '未知')
