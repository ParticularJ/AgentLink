# earnings-surprise-strategy/skills/scripts/earnings_scanner.py

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import warnings
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

warnings.filterwarnings('ignore')

try:
    from .data_fetcher import EarningsDataFetcher
    from .surprise_analyzer import SurpriseAnalyzer
    from .quality_analyzer import QualityAnalyzer
    from .market_analyzer import MarketReactionAnalyzer
    from .risk_assessor import RiskAssessor
    from .report_generator import EarningsReportGenerator
except ImportError:
    # 直接运行时
    from data_fetcher import EarningsDataFetcher
    from surprise_analyzer import SurpriseAnalyzer
    from quality_analyzer import QualityAnalyzer
    from market_analyzer import MarketReactionAnalyzer
    from risk_assessor import RiskAssessor
    from report_generator import EarningsReportGenerator

class EarningsSurpriseScanner:
    """财报超预期扫描器"""
    
    def __init__(self):
        self.name = "财报超预期策略"
        self.data_fetcher = EarningsDataFetcher()
        self.surprise_analyzer = SurpriseAnalyzer()
        self.quality_analyzer = QualityAnalyzer()
        self.market_analyzer = MarketReactionAnalyzer()
        self.risk_assessor = RiskAssessor()
        self.report_generator = EarningsReportGenerator()
        
        # 评分权重
        self.weights = {
            'surprise_magnitude': 0.30,
            'growth_quality': 0.25,
            'market_reaction': 0.20,
            'institutional_attitude': 0.15,
            'industry_prosperity': 0.10
        }
        


    def get_full_dual_track_financial_data(self, current_time: datetime = None) -> dict:
        """
        🔥 全时段双轨并行：无死角获取所有已披露财报，杜绝任何遗漏
        返回格式：{"主财报类型": DataFrame, "前瞻财报类型": DataFrame}
        主财报 = 当前时段最完整、最全面的财报
        前瞻财报 = 下一季度已披露的最新增量数据
        """
        if current_time is None:
            current_time = datetime.now()
        y = current_time.year
        m = current_time.month
        today_str = current_time.strftime("%Y-%m-%d")

        # 定义全年季度映射表（主财报 + 前瞻财报）
        quarter_mapping = {
            # 月份范围: (主财报日期, 主财报名称, 前瞻财报日期, 前瞻财报名称)
            "1-3": (f"{y-1}1231", "去年年报", f"{y}0331", "当年一季报"),
            "4-4": (f"{y-1}1231", "去年年报", f"{y}0331", "当年一季报"),
            "5-6": (f"{y}0331", "当年一季报", f"{y}0630", "当年中报"),
            "7-8": (f"{y}0630", "当年中报", f"{y}0930", "当年三季报"),
            "9-10": (f"{y}0930", "当年三季报", f"{y}1231", "当年年报"),
            "11-12": (f"{y}0930", "当年三季报", f"{y}1231", "当年年报"),
        }

        # 匹配当前月份对应的双轨财报
        if 1 <= m <= 3:
            main_date, main_name, forward_date, forward_name = quarter_mapping["1-3"]
        elif m == 4:
            main_date, main_name, forward_date, forward_name = quarter_mapping["4-4"]
        elif 5 <= m <= 6:
            main_date, main_name, forward_date, forward_name = quarter_mapping["5-6"]
        elif 7 <= m <= 8:
            main_date, main_name, forward_date, forward_name = quarter_mapping["7-8"]
        elif 9 <= m <= 10:
            main_date, main_name, forward_date, forward_name = quarter_mapping["9-10"]
        else:
            main_date, main_name, forward_date, forward_name = quarter_mapping["11-12"]

        return main_date,forward_date

        
    def scan_daily_earnings(self, date: str = None) -> List[Dict]:
        """扫描每日发布的财报"""
        if date is None:
            date = datetime.now()
        

        print(date)
        report_date =self.get_full_dual_track_financial_data(date)
        print(f"开始扫描{date}发布的财报...", report_date)
        
        # 获取当日发布的财报
        earnings_list = []
        earnings_list_maindate = self.data_fetcher.get_earnings_by_date(report_date[0])
        if earnings_list_maindate:  # 确保有数据才加
            earnings_list.extend(earnings_list_maindate)
            print(f"✅ 第一个日期返回：{len(earnings_list_maindate)} 条")
        earnings_list_forwarddate = self.data_fetcher.get_earnings_by_date(report_date[1])
        if earnings_list_forwarddate:  # 确保有数据才加
            earnings_list.extend(earnings_list_forwarddate)
            print(f"✅ 第二个日期返回：{len(earnings_list_forwarddate)} 条")    
            
        
        if not earnings_list:
            print(f"{date}无财报发布")
            return []
        
        print(f"找到{len(earnings_list)}份财报")
        
        results = []
        for earnings in earnings_list:
            print(earnings)
            result = self.analyze_earnings(earnings)
            if result and result['score'] >= 70:
                results.append(result)
        
        # 按得分排序
        results.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"发现{len(results)}只符合条件的股票")
        return results
    
    def scan_earnings_season(self, start_date: str, end_date: str) -> List[Dict]:
        """扫描财报季所有财报"""
        print(f"扫描财报季 {start_date} 至 {end_date}")
        
        # 获取日期范围内的所有财报
        earnings_list = self.data_fetcher.get_earnings_in_range(start_date, end_date)
        
        results = []
        for earnings in earnings_list:
            result = self.analyze_earnings(earnings)
            if result and result['score'] >= 70:
                results.append(result)
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results
    
    def analyze_earnings(self, earnings: Dict) -> Optional[Dict]:
        """分析单份财报"""
        try:
            stock_code = earnings.get('stock_code')
            stock_name = earnings.get('stock_name')
            quarter = earnings.get('quarter')
          
            # 1. 超预期幅度分析
            surprise_analysis = self.surprise_analyzer.analyze(earnings)

            print("surprise_analysis", surprise_analysis)

            if surprise_analysis['score'] < 60:
                return None  # 超预期不明显
            
            # 2. 增长质量分析
            quality_analysis = self.quality_analyzer.analyze(stock_code, earnings)
            print("quality_analysis", quality_analysis)

            # 3. 市场反应分析
            market_analysis = self.market_analyzer.analyze(stock_code, earnings)
            print("market_analysis", market_analysis)
            # 4. 机构态度分析
            institutional_analysis = self._analyze_institutional_attitude(stock_code)
            print("institutional_analysis", institutional_analysis)
            # 5. 行业景气度分析
            industry_analysis = self._analyze_industry(earnings.get('industry', ''))
            print("industry_analysis: ",industry_analysis)
            # 计算总分
            total_score = self._calculate_total_score(
                surprise_analysis,
                quality_analysis,
                market_analysis,
                institutional_analysis,
                industry_analysis
            )
            print("total_score: ", total_score)
            # 生成交易建议
            recommendation = self._generate_recommendation(
                total_score,
                surprise_analysis,
                market_analysis
            )
            
            print(  "recommendation: ", recommendation)
            # 风险评估
            # risks = self.risk_assessor.assess(
            #     stock_code,
            #     earnings,
            #     market_analysis
            # )
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'quarter': quarter,
                'announcement_date': earnings.get('announcement_date'),
                'signal': 'BUY' if total_score >= 75 else 'WATCH',
                'score': round(total_score, 2),
                'surprise_analysis': surprise_analysis,
                'quality_analysis': quality_analysis,
                'market_analysis': market_analysis,
                'institutional_analysis': institutional_analysis,
                'industry_analysis': industry_analysis,
                'recommendation': recommendation,
                #'risks': risks,
                'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            print(f"分析{earnings.get('stock_code')}失败: {e}")
            return None
    
    def _analyze_institutional_attitude(self, stock_code: str) -> Dict:
        """分析机构态度"""
        try:
            # 获取分析师评级
            ratings = self.data_fetcher.get_analyst_ratings(stock_code)
            # print(ratings)
            if not ratings:
                return {'score': 60, 'level': '数据不足'}
            
            # 评级变化
            recent_ratings = ratings[:5]
            # --------------------------
            # 新逻辑：用【评级好坏】替代（完全不影响你原有分数体系）
            # --------------------------
            high_rating = ["买入", "强烈推荐", "增持", "推荐"]
            upgrades = sum(1 for r in recent_ratings if r.get('rating') in high_rating)
            downgrades = sum(1 for r in recent_ratings if r.get('rating') not in high_rating)
            
            if upgrades > downgrades:
                score = 85
                level = "机构看好"
            elif upgrades == downgrades:
                score = 70
                level = "机构中性"
            else:
                score = 50
                level = "机构谨慎"
            
            # 目标价空间 to_do ..
            target_price = self.data_fetcher.get_target_price(stock_code)
            current_price = self.data_fetcher.get_current_price(stock_code)
            
            if target_price and current_price:
                upside = (target_price - current_price) / current_price * 100
                if upside > 20:
                    score = min(100, score + 10)
                    level += "，目标价空间大"
            
            return {
                'score': score,
                'level': level,
                'upgrades': upgrades,
                'downgrades': downgrades,
                'target_upside': upside if target_price else None
            }
            
        except Exception as e:
            return {'score': 60, 'level': '无法获取', 'error': str(e)}
    
    def _analyze_industry(self, industry: str) -> Dict:
        """分析行业景气度"""
        try:
            if not industry:
                return {'score': 70, 'level': '未知'}
            
            # 获取行业指数表现
            industry_performance = self.data_fetcher.get_industry_performance(industry)
            print("industry_performance: ", industry_performance)
            if industry_performance:
                if industry_performance > 20:
                    score = 100
                    level = "高景气"
                elif industry_performance > 10:
                    score = 85
                    level = "中高景气"
                elif industry_performance > 0:
                    score = 70
                    level = "温和增长"
                else:
                    score = 40
                    level = "景气下行"
            else:
                score = 70
                level = "行业数据不足"
            
            return {'score': score, 'level': level, 'performance': industry_performance}
            
        except Exception as e:
            return {'score': 70, 'level': '无法评估', 'error': str(e)}
    
    def _calculate_total_score(self, surprise: Dict, quality: Dict,
                               market: Dict, institutional: Dict,
                               industry: Dict) -> float:
        """计算总分"""
        total = (
            surprise['score'] * self.weights['surprise_magnitude'] +
            quality['score'] * self.weights['growth_quality'] +
            market['score'] * self.weights['market_reaction'] +
            institutional['score'] * self.weights['institutional_attitude'] +
            industry['score'] * self.weights['industry_prosperity']
        )
        return total
    
    def _generate_recommendation(self, score: float, 
                                  surprise: Dict,
                                  market: Dict) -> Dict:
        """生成交易建议"""
        if score >= 85:
            action = "强烈推荐"
            urgency = "公告后1-2日内买入"
            entry = "公告次日开盘买入"
            position = "25%"
        elif score >= 75:
            action = "推荐"
            urgency = "公告后3-5日内择机买入"
            entry = "回调至5日线买入"
            position = "15%"
        elif score >= 70:
            action = "关注"
            urgency = "等待确认信号"
            entry = "突破公告日高点买入"
            position = "10%"
        else:
            action = "暂缓"
            urgency = "条件不充分"
            entry = "继续观察"
            position = "0%"
        
        return {
            'action': action,
            'urgency': urgency,
            'entry_method': entry,
            'suggested_position': position,
            'stop_loss': '-8%或跌破公告日最低价',
            'target': '15-25%',
            'holding_period': '2-4周'
        }


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='财报超预期策略扫描')
    parser.add_argument('--scan', action='store_true', help='扫描今日财报')
    parser.add_argument('--date', type=str, help='指定日期 YYYY-MM-DD')
    parser.add_argument('--stock', type=str, help='分析指定股票')
    parser.add_argument('--name', type=str, help='股票名称')
    parser.add_argument('--quarter', type=str, help='财报季度 e.g., 2024Q1')
    parser.add_argument('--top', type=int, default=10, help='返回前N名')
    
    args = parser.parse_args()
    
    scanner = EarningsSurpriseScanner()
    
    if args.scan:
        date = args.date or datetime.now().strftime('%Y-%m-%d')
        results = scanner.scan_daily_earnings(date)
        
        report = scanner.report_generator.generate_scan_report(results, args.top)
        print(report)
        
    elif args.stock:
        # 分析指定股票
        earnings = scanner.data_fetcher.get_earnings_by_stock(
            args.stock, args.quarter
        )
        if earnings:
            result = scanner.analyze_earnings(earnings)
            report = scanner.report_generator.generate_stock_report(result)
            print(report)
        else:
            print(f"未找到{args.stock}的财报数据")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()