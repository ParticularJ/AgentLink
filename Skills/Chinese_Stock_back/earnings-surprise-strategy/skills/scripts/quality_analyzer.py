# earnings-surprise-strategy/skills/scripts/quality_analyzer.py

import akshare as ak
import pandas as pd
from typing import Dict, Optional

class QualityAnalyzer:
    """增长质量分析器"""
    
    def __init__(self):
        self.sustainability_weights = {
            'continuous_growth': 0.4,
            'accelerating': 0.3,
            'cash_flow_quality': 0.3
        }
        
    def analyze(self, stock_code: str, earnings: Dict) -> Dict:
        """分析增长质量"""
        # 1. 增长可持续性
        sustainability = self._analyze_sustainability(stock_code, earnings)
        ##print("sustainability: ", sustainability)
    
        # 2. 现金流质量
        cash_flow_quality = self._analyze_cash_flow(stock_code, earnings)
        #print("cash_flow_quality: ", cash_flow_quality)
        # 3. 毛利率趋势
        margin_trend = self._analyze_margin_trend(stock_code, earnings)
        # print("margin_trend: ", margin_trend)
        # 计算总分
        total_score = (
            sustainability['score'] * self.sustainability_weights['continuous_growth'] +
            cash_flow_quality['score'] * self.sustainability_weights['cash_flow_quality'] +
            margin_trend['score'] * 0.3
        )
        
        # 评级
        if total_score >= 85:
            level = "高质量增长"
        elif total_score >= 70:
            level = "良好增长"
        elif total_score >= 60:
            level = "一般增长"
        else:
            level = "增长质量存疑"
        
        return {
            'score': round(total_score, 2),
            'level': level,
            'sustainability': sustainability,
            'cash_flow_quality': cash_flow_quality,
            'margin_trend': margin_trend
        }
    
    def _analyze_sustainability(self, stock_code: str, earnings: Dict) -> Dict:
        """分析增长可持续性"""
        try:
            # 获取历史财报数据
            profit_df = ak.stock_profit_sheet_by_report_em(symbol=stock_code)
            if profit_df is None or len(profit_df) < 4:
                return {'score': 60, 'level': '数据不足'}
         
            # 计算连续增长季度数
            growth_quarters = 0
            accelerating = False
            
            recent_profits = []
            for _, row in profit_df.head(8).iterrows():
                profit = self._parse_number(row.get('DEDUCT_PARENT_NETPROFIT', 0))
                #print("profit: ", profit)
                if profit > 0:
                    recent_profits.append(profit)
            
            # 判断连续增长
            if len(recent_profits) >= 4:
                is_increasing = all(recent_profits[i] > recent_profits[i+1] 
                                   for i in range(len(recent_profits)-1))
                if is_increasing:
                    growth_quarters = len(recent_profits)
            
            # 判断是否加速增长
            if len(recent_profits) >= 6:
                recent_avg = sum(recent_profits[:3]) / 3
                older_avg = sum(recent_profits[3:6]) / 3
                accelerating = recent_avg > older_avg
            
            # 评分
            if growth_quarters >= 6:
                score = 100
                level = "持续高速增长"
            elif growth_quarters >= 4:
                score = 85
                level = "连续增长"
            elif growth_quarters >= 2:
                score = 70
                level = "开始增长"
            else:
                score = 50
                level = "增长不稳定"
            
            if accelerating:
                score = min(100, score + 10)
                level += "，加速增长"
            
            return {
                'score': score,
                'level': level,
                'growth_quarters': growth_quarters,
                'accelerating': accelerating
            }
            
        except Exception as e:
            return {'score': 60, 'level': '无法评估', 'error': str(e)}
    
    def _analyze_cash_flow(self, stock_code: str, earnings: Dict) -> Dict:
        """分析现金流质量"""
        try:
            # 获取现金流数据
            cash_flow_df = ak.stock_cash_flow_sheet_by_report_em(symbol=stock_code)
            # print("cash_flow_df: ", cash_flow_df)
            if cash_flow_df is None or len(cash_flow_df) == 0:
                return {'score': 60, 'level': '数据不足'}
            
            latest = cash_flow_df.iloc[0]
            operating_cf = self._parse_number(latest.get('NETCASH_OPERATE', 0))
            net_profit = earnings.get('net_profit', 0)
           # print("operating_cf: ", operating_cf)
           # print("net_profit: ", net_profit)

            # 现金流/净利润比率
            if net_profit > 0:
                ratio = operating_cf / net_profit
            else:
                ratio = 0
            
            # 评分
            if ratio >= 1:
                score = 100
                level = "现金流充裕"
            elif ratio >= 0.8:
                score = 85
                level = "现金流良好"
            elif ratio >= 0.5:
                score = 70
                level = "现金流正常"
            elif ratio > 0:
                score = 50
                level = "现金流偏紧"
            else:
                score = 30
                level = "现金流为负"
            
            return {
                'score': score,
                'level': level,
                'operating_cf': round(operating_cf, 2),
                'net_profit': round(net_profit, 2),
                'cash_flow_ratio': round(ratio, 2)
            }
            
        except Exception as e:
            return {'score': 60, 'level': '无法评估', 'error': str(e)}
    
    def _analyze_margin_trend(self, stock_code: str, earnings: Dict) -> Dict:
        """分析毛利率趋势"""
        try:
            # 获取利润表数据
            profit_df = ak.stock_profit_sheet_by_report_em(symbol=stock_code)
            # print("profit_df",profit_df)
            if profit_df is None or len(profit_df) < 2:
                return {'score': 60, 'level': '数据不足'}
        
            # 计算毛利率
            margins = []
            for _, row in profit_df.head(4).iterrows():
                revenue = self._parse_number(row.get('TOTAL_OPERATE_INCOME', 0))
                cost = self._parse_number(row.get('TOTAL_OPERATE_COST', 0))
                if revenue > 0:
                    margin = (revenue - cost) / revenue * 100
                    margins.append(margin)
            
            if len(margins) >= 2:
                margin_change = margins[0] - margins[1]
                
                if margin_change > 2:
                    score = 100
                    level = "毛利率提升"
                elif margin_change > 0:
                    score = 85
                    level = "毛利率稳定"
                elif margin_change > -2:
                    score = 70
                    level = "毛利率微降"
                else:
                    score = 50
                    level = "毛利率下降"
            else:
                score = 60
                level = "数据不足"
            
            return {
                'score': score,
                'level': level,
                'current_margin': round(margins[0], 2) if margins else None,
                'margin_change': round(margin_change, 2) if len(margins) >= 2 else None
            }
            
        except Exception as e:
            return {'score': 60, 'level': '无法评估', 'error': str(e)}
    
    def _parse_number(self, value) -> float:
        """解析数值"""
        if value is None or value == '-':
            return 0
        try:
            if isinstance(value, str):
                value = value.replace('亿', '').replace('万', '').replace(',', '')
                return float(value)
            return float(value)
        except:
            return 0