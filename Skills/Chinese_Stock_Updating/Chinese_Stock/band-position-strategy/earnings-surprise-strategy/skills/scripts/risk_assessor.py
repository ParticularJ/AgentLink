#!/usr/bin/env python3
"""
风险评估模块
评估财报交易的风险
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime


class RiskAssessor:
    """风险评估器"""
    
    def __init__(self):
        self.name = "风险评估"
        self.risk_rules = {
            'max_single_position': 0.25,    # 单只股票最大仓位25%
            'max_daily_trades': 5,           # 每日最大交易次数
            'stop_loss_pct': 0.08,           # 止损比例8%
            'max_drawdown': 0.15             # 最大回撤15%
        }
    
    def assess(self, stock_data: Dict, market_data: Dict = None) -> Dict:
        """
        评估交易风险
        
        Args:
            stock_data: 股票数据
            market_data: 市场数据
            
        Returns:
            风险评估结果
        """
        result = {
            'risk_score': 50,
            'risk_level': 'medium',
            'suggested_position': 0.15,
            'stop_loss': 0,
            'details': {}
        }
        
        try:
            # 基础风险评估
            volatility_score = self._assess_volatility(stock_data)
            liquidity_score = self._assess_liquidity(stock_data)
            market_score = self._assess_market_condition(market_data)
            
            # 综合风险得分 (分数越高风险越低)
            total_score = (volatility_score + liquidity_score + market_score) / 3
            
            # 确定风险等级
            if total_score >= 80:
                level = 'low'
                position = 0.25
            elif total_score >= 60:
                level = 'medium'
                position = 0.15
            elif total_score >= 40:
                level = 'high'
                position = 0.10
            else:
                level = 'very_high'
                position = 0.05
            
            # 计算止损价
            current_price = stock_data.get('current_price', 0)
            stop_loss = current_price * (1 - self.risk_rules['stop_loss_pct']) if current_price > 0 else 0
            
            result['risk_score'] = round(total_score, 2)
            result['risk_level'] = level
            result['suggested_position'] = position
            result['stop_loss'] = round(stop_loss, 2)
            result['details'] = {
                'volatility_score': round(volatility_score, 2),
                'liquidity_score': round(liquidity_score, 2),
                'market_score': round(market_score, 2),
                'stop_loss_pct': self.risk_rules['stop_loss_pct']
            }
            
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def _assess_volatility(self, stock_data: Dict) -> float:
        """评估波动率风险"""
        # 根据历史波动率评分
        volatility = stock_data.get('volatility', 0.3)
        # 波动率越低得分越高
        score = max(0, 100 - volatility * 200)
        return score
    
    def _assess_liquidity(self, stock_data: Dict) -> float:
        """评估流动性风险"""
        # 根据成交量和市值评分
        market_cap = stock_data.get('market_cap', 100)
        avg_volume = stock_data.get('avg_volume', 1000000)
        
        # 市值越大、成交量越高，流动性越好
        cap_score = min(50, market_cap / 100)
        volume_score = min(50, avg_volume / 1000000)
        
        return cap_score + volume_score
    
    def _assess_market_condition(self, market_data: Dict = None) -> float:
        """评估市场环境"""
        if market_data is None:
            return 50
        
        # 根据市场趋势评分
        market_trend = market_data.get('trend', 0)
        market_volatility = market_data.get('volatility', 0.2)
        
        trend_score = 50 + market_trend * 30
        vol_score = max(0, 50 - market_volatility * 100)
        
        return (trend_score + vol_score) / 2
    
    def get_risk_level_name(self, level: str) -> str:
        """获取风险等级名称"""
        level_names = {
            'low': '低风险',
            'medium': '中等风险',
            'high': '高风险',
            'very_high': '极高风险'
        }
        return level_names.get(level, '未知')
