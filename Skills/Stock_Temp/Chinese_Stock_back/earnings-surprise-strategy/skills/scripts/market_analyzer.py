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
        # print(df)
        # 整理成 analyze 函数需要的格式
        df.index = pd.to_datetime(df["date"])
        df["pct_change"] =df["close"].pct_change() * 100  # 对应函数需要的列
        df = df[["close", "pct_change", "volume"]]
       
        return df


    def analyze(self, stock_code: str, earnings: str, price_data: pd.DataFrame = None) -> Dict:
        """
        分析市场对财报的反应
        
        Args:
            stock_code: 股票代码
            earnings: 财报信息
            price_data: 价格数据
            
        Returns:
            分析结果
        """
        result = {
            'score': 50,
            'level': 'neutral',
            'details': {}
        }
        
        # 如果没有价格数据，返回中性评分

        
        try:
            # 找到财报发布日期后的数据
            earnings_date = pd.to_datetime(earnings.get('report_date'))
            price_data = self._get_stock_price(earnings.get('stock_code'), earnings_date.strftime("%Y%m%d"), pd.Timestamp.now().strftime("%Y%m%d"))
            # 计算公告日涨跌幅
            # print("price_data: ", price_data.index, earnings_date)
            mask = price_data.index >= earnings_date
            if not mask.any():
                return result
            
            post_earnings = price_data[mask]
            if len(post_earnings) < 2:
                return result
            
            # 公告日涨跌幅
            announcement_return = post_earnings.iloc[0]['pct_change'] if 'pct_change' in post_earnings.columns else 0
            
            # 公告后3日累计涨跌幅
            three_day_return = 0
            if len(post_earnings) >= 3:
                start_price = post_earnings.iloc[0]['close']
                end_price = post_earnings.iloc[2]['close']
                three_day_return = (end_price - start_price) / start_price * 100
            
            # 成交量变化
            volume_change = 0
            if 'volume' in post_earnings.columns and len(post_earnings) > 0:
                avg_volume_pre = price_data[~mask]['volume'].mean() if len(price_data[~mask]) > 0 else 1
                volume_post = post_earnings.iloc[0]['volume']
                volume_change = (volume_post - avg_volume_pre) / avg_volume_pre * 100
            
            # 计算市场反应得分
            price_score = min(100, max(0, 50 + announcement_return * 3 + three_day_return * 2))
            volume_score = min(100, max(0, 50 + volume_change * 0.5))
            
            # 综合得分
            total_score = (
                price_score * self.weights['price_reaction'] +
                volume_score * self.weights['volume_reaction'] +
                50 * self.weights['market_comparison']
            )
            
            # 判断反应等级
            if total_score >= 80:
                level = 'strong_positive'
            elif total_score >= 65:
                level = 'positive'
            elif total_score >= 45:
                level = 'neutral'
            elif total_score >= 30:
                level = 'negative'
            else:
                level = 'strong_negative'
            
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
