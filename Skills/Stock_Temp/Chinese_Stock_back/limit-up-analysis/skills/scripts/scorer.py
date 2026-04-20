#!/usr/bin/env python3
"""
涨停板连板评分器
实现五维度量化评分算法
"""

import os
import sys
from typing import Dict, Optional

# 清除代理环境变量
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    if key in os.environ:
        del os.environ[key]

import pandas as pd
import yaml
from colorama import Fore, Style


class LimitUpScorer:
    """涨停板连板评分器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化评分器
        
        Args:
            config_path: 配置文件路径，默认使用内置配置
        """
        self.config = self._load_config(config_path)
        self.weights = self.config.get('weights', {})
        self.categories = self.config.get('categories', {})
    
    def _load_config(self, config_path: Optional[str] = None) -> Dict:
        """加载评分配置"""
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        
        # 默认配置
        default_config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'config', 'scoring_weights.yaml'
        )
        
        if os.path.exists(default_config_path):
            with open(default_config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        
        # 内置默认配置
        return {
            'weights': {
                'sealing_strength': {'weight': 30},
                'sector_effect': {'weight': 25},
                'capital_flow': {'weight': 20},
                'technical_pattern': {'weight': 15},
                'market_sentiment': {'weight': 10}
            }
        }
    
    def calc_sealing_strength(self, zt_data: pd.DataFrame, detail: Dict) -> float:
        """
        计算封板强度得分 (权重30%)
        
        评估指标：
        - 封单比（封单金额/流通市值）
        - 封板时间（开盘到首次封板的时间）
        - 炸板次数
        
        Args:
            zt_data: 涨停数据 DataFrame
            detail: 股票详细信息
            
        Returns:
            封板强度得分 (0-100)
        """
        score = 50.0  # 基础分
        
        try:
            if not zt_data.empty:
                row = zt_data.iloc[0]
                
                # 封单比评分 (40%)
                seal_amount = row.get('封板资金', 0)
                market_cap = self._get_market_cap(detail)
                
                if market_cap > 0:
                    seal_ratio = seal_amount / market_cap * 100
                    if seal_ratio >= 10:
                        score += 20  # 优秀
                    elif seal_ratio >= 5:
                        score += 15  # 良好
                    elif seal_ratio >= 2:
                        score += 10  # 一般
                    elif seal_ratio >= 1:
                        score += 5   # 较差
                
                # 封板时间评分 (35%)
                first_time = row.get('首次封板时间', '')
                if first_time:
                    minutes = self._parse_time_to_minutes(first_time)
                    if minutes <= 5:
                        score += 17.5  # 优秀
                    elif minutes <= 15:
                        score += 12.5  # 良好
                    elif minutes <= 30:
                        score += 8.75  # 一般
                    elif minutes <= 60:
                        score += 5     # 较差
                
                # 炸板次数评分 (25%)
                open_count = row.get('炸板次数', 0)
                if open_count == 0:
                    score += 12.5  # 优秀
                elif open_count == 1:
                    score += 8.75  # 良好
                elif open_count == 2:
                    score += 5     # 一般
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 封板强度计算异常: {e}{Style.RESET_ALL}")
        
        return min(100, max(0, score))
    
    def calc_sector_effect(self, code: str, all_zt_data: pd.DataFrame) -> float:
        """
        计算板块效应得分 (权重25%)
        
        评估指标：
        - 同板块涨停数量
        - 板块热度排名
        - 龙头地位
        
        Args:
            code: 股票代码
            all_zt_data: 所有涨停股票数据
            
        Returns:
            板块效应得分 (0-100)
        """
        score = 40.0  # 基础分
        
        try:
            # 统计同板块涨停数量
            if not all_zt_data.empty and '所属行业' in all_zt_data.columns:
                # 获取该股票所属行业
                stock_row = all_zt_data[all_zt_data['代码'] == code]
                if not stock_row.empty:
                    sector = stock_row.iloc[0].get('所属行业', '')
                    if sector:
                        sector_count = len(all_zt_data[all_zt_data['所属行业'] == sector])
                        
                        # 同板块涨停数量评分
                        if sector_count >= 10:
                            score += 30  # 优秀
                        elif sector_count >= 5:
                            score += 22.5  # 良好
                        elif sector_count >= 3:
                            score += 15  # 一般
                        elif sector_count >= 1:
                            score += 7.5  # 较差
                        
                        # 龙头地位评分（按封板时间排序）
                        sector_stocks = all_zt_data[all_zt_data['所属行业'] == sector]
                        if not sector_stocks.empty:
                            sector_stocks = sector_stocks.sort_values('首次封板时间')
                            first_stock = sector_stocks.iloc[0]
                            if first_stock['代码'] == code:
                                score += 20  # 板块龙头
                            elif len(sector_stocks) > 1 and sector_stocks.iloc[1]['代码'] == code:
                                score += 10  # 板块龙二
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 板块效应计算异常: {e}{Style.RESET_ALL}")
        
        return min(100, max(0, score))
    
    def calc_capital_flow(self, code: str, detail: Dict) -> float:
        """
        计算资金流向得分 (权重20%)
        
        评估指标：
        - 主力净流入占比
        - 龙虎榜席位质量
        - 散户占比
        
        Args:
            code: 股票代码
            detail: 股票详细信息
            
        Returns:
            资金流向得分 (0-100)
        """
        score = 40.0  # 基础分
        
        try:
            # 从实时数据获取资金流向
            if 'realtime' in detail and not detail['realtime'].empty:
                rt = detail['realtime'].iloc[0]
                
                # 主力净流入评分 (50%)
                main_inflow = rt.get('主力净流入', 0)
                turnover = rt.get('换手率', 0)
                
                if turnover > 0:
                    inflow_ratio = main_inflow / turnover
                    if inflow_ratio >= 20:
                        score += 25  # 优秀
                    elif inflow_ratio >= 10:
                        score += 18.75  # 良好
                    elif inflow_ratio >= 5:
                        score += 12.5  # 一般
                    elif inflow_ratio > 0:
                        score += 6.25  # 较差
                
                # 换手率评分 (正向指标，适中最好)
                if 5 <= turnover <= 20:
                    score += 15  # 理想区间
                elif 2 <= turnover < 5 or 20 < turnover <= 30:
                    score += 10  # 可接受
                elif turnover > 30:
                    score += 5   # 过高，可能有风险
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 资金流向计算异常: {e}{Style.RESET_ALL}")
        
        return min(100, max(0, score))
    
    def calc_technical_pattern(self, detail: Dict) -> float:
        """
        计算技术形态得分 (权重15%)
        
        评估指标：
        - 突破形态
        - 量价配合
        - 筹码分布
        
        Args:
            detail: 股票详细信息
            
        Returns:
            技术形态得分 (0-100)
        """
        score = 40.0  # 基础分
        
        try:
            if 'history' in detail and not detail['history'].empty:
                hist = detail['history']
                
                if len(hist) >= 20:
                    # 获取近期数据
                    recent = hist.tail(20)
                    latest_close = recent['收盘'].iloc[-1]
                    
                    # 突破形态评分 (40%)
                    max_20 = recent['最高'].max()
                    max_60 = hist.tail(60)['最高'].max() if len(hist) >= 60 else max_20
                    
                    if latest_close >= max_60 * 0.98:
                        score += 24  # 历史新高或接近
                    elif latest_close >= max_20 * 0.98:
                        score += 16  # 20日新高
                    elif latest_close > recent['收盘'].mean() * 1.05:
                        score += 8   # 趋势向上
                    
                    # 量价配合评分 (35%)
                    latest_volume = recent['成交量'].iloc[-1]
                    avg_volume = recent['成交量'].mean()
                    
                    if latest_volume >= avg_volume * 2:
                        score += 14  # 放量明显
                    elif latest_volume >= avg_volume * 1.5:
                        score += 10.5  # 温和放量
                    elif latest_volume >= avg_volume:
                        score += 7     # 正常量能
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 技术形态计算异常: {e}{Style.RESET_ALL}")
        
        return min(100, max(0, score))
    
    def calc_market_sentiment(self, all_zt_data: pd.DataFrame) -> float:
        """
        计算市场情绪得分 (权重10%)
        
        评估指标：
        - 市场连板高度
        - 昨日涨停表现
        - 整体赚钱效应
        
        Args:
            all_zt_data: 所有涨停股票数据
            
        Returns:
            市场情绪得分 (0-100)
        """
        score = 50.0  # 基础分
        
        try:
            if not all_zt_data.empty:
                # 计算平均连板数
                if '连板数' in all_zt_data.columns:
                    avg_limit = all_zt_data['连板数'].mean()
                    max_limit = all_zt_data['连板数'].max()
                    
                    # 连板高度评分
                    if max_limit >= 7:
                        score += 20  # 情绪高涨
                    elif max_limit >= 5:
                        score += 15  # 情绪良好
                    elif max_limit >= 3:
                        score += 10  # 情绪一般
                    elif max_limit >= 2:
                        score += 5   # 情绪低迷
                    
                    # 平均连板评分
                    if avg_limit >= 2:
                        score += 15
                    elif avg_limit >= 1.5:
                        score += 10
                    elif avg_limit >= 1.2:
                        score += 5
                
                # 涨停数量评分
                zt_count = len(all_zt_data)
                if zt_count >= 100:
                    score += 15  # 百股涨停，情绪极好
                elif zt_count >= 50:
                    score += 10  # 情绪良好
                elif zt_count >= 30:
                    score += 5   # 情绪一般
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 市场情绪计算异常: {e}{Style.RESET_ALL}")
        
        return min(100, max(0, score))
    
    def calc_total_score(self, sealing: float, sector: float, 
                         capital: float, technical: float, sentiment: float) -> float:
        """
        计算综合总分
        
        Args:
            sealing: 封板强度得分
            sector: 板块效应得分
            capital: 资金流向得分
            technical: 技术形态得分
            sentiment: 市场情绪得分
            
        Returns:
            综合总分 (0-100)
        """
        weights = self.weights
        
        total = (
            sealing * weights.get('sealing_strength', {}).get('weight', 30) / 100 +
            sector * weights.get('sector_effect', {}).get('weight', 25) / 100 +
            capital * weights.get('capital_flow', {}).get('weight', 20) / 100 +
            technical * weights.get('technical_pattern', {}).get('weight', 15) / 100 +
            sentiment * weights.get('market_sentiment', {}).get('weight', 10) / 100
        )
        
        return round(total, 1)
    
    def get_rating(self, score: float) -> Dict:
        """
        获取评级信息
        
        Args:
            score: 综合得分
            
        Returns:
            评级信息字典
        """
        categories = self.categories
        
        if score >= categories.get('excellent', {}).get('min_score', 85):
            return categories.get('excellent', {'label': '极高', 'description': '龙头气质'})
        elif score >= categories.get('good', {}).get('min_score', 75):
            return categories.get('good', {'label': '高', 'description': '连板可能性大'})
        elif score >= categories.get('average', {}).get('min_score', 65):
            return categories.get('average', {'label': '中等', 'description': '需结合盘面'})
        elif score >= categories.get('poor', {}).get('min_score', 55):
            return categories.get('poor', {'label': '低', 'description': '谨慎参与'})
        else:
            return categories.get('very_poor', {'label': '极低', 'description': '建议观望'})
    
    def get_recommendation(self, score: float) -> str:
        """
        获取操作建议
        
        Args:
            score: 综合得分
            
        Returns:
            操作建议字符串
        """
        if score >= 85:
            return f"{Fore.GREEN}✅ 重点关注 - 龙头气质，明日高开概率极大，可积极参与{Style.RESET_ALL}"
        elif score >= 75:
            return f"{Fore.GREEN}✅ 关注 - 连板可能性大，可考虑打板或低吸{Style.RESET_ALL}"
        elif score >= 65:
            return f"{Fore.YELLOW}⚠️ 观察 - 需结合明日开盘情况判断，谨慎参与{Style.RESET_ALL}"
        elif score >= 55:
            return f"{Fore.YELLOW}⚠️ 谨慎 - 连板概率较低，不建议追高{Style.RESET_ALL}"
        else:
            return f"{Fore.RED}❌ 观望 - 连板可能性极低，建议回避{Style.RESET_ALL}"
    
    def _get_market_cap(self, detail: Dict) -> float:
        """获取流通市值"""
        try:
            if 'info' in detail and not detail['info'].empty:
                cap = detail['info'].iloc[0].get('流通市值', 0)
                return float(cap) if cap else 0
            if 'realtime' in detail and not detail['realtime'].empty:
                cap = detail['realtime'].iloc[0].get('流通市值', 0)
                return float(cap) if cap else 0
        except:
            pass
        return 0
    
    def _parse_time_to_minutes(self, time_str: str) -> int:
        """将时间字符串转换为开盘后的分钟数"""
        try:
            # 处理格式如 "09:30:00" 或 "093000"
            time_str = time_str.replace(':', '').strip()
            if len(time_str) >= 4:
                hour = int(time_str[:2])
                minute = int(time_str[2:4])
                
                # 计算从9:30开始的分钟数
                if hour < 9 or (hour == 9 and minute < 30):
                    return 0
                if hour == 9:
                    return minute - 30
                elif hour == 10:
                    return 30 + minute
                elif hour == 11:
                    return 90 + minute
                elif hour == 13:
                    return 150 + minute
                elif hour == 14:
                    return 210 + minute
        except:
            pass
        return 240  # 默认返回收盘时间
