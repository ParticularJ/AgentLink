# earnings-surprise-strategy/skills/scripts/data_fetcher.py

import akshare as ak
import pandas as pd
import requests
import os
import yaml
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import time

class EarningsDataFetcher:
    """财报数据获取器"""
    
    def __init__(self):
        self.cache = {}
        self.cache_ttl = 300  # 5分钟缓存
        self._spot_cache = None
        
    def _load_watchlist_codes(self) -> List[str]:
        """加载自选股池"""
        watchlist_path = './my_stock_pool/watchlist.yaml'
        if not os.path.exists(watchlist_path):
            
            watchlist_path = '../../../my_stock_pool/watchlist.yaml'
            if not os.path.exists(watchlist_path):
                print(f"watchlist.yaml 文件不存在: {watchlist_path}")
                return None

        try:
            with open(watchlist_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            stock_codes = []
            if isinstance(data, dict) and 'watchlist' in data:
                for sector, categories in data['watchlist'].items():
                    for category, stock_list in categories.items():
                        for stock in stock_list:
                            if isinstance(stock, (list, tuple)) and len(stock) >= 2: 
                                                           
                                stock_codes.append(stock[1])
            return sorted(set(stock_codes))
        except Exception as e:
            print(f"加载自选股池失败: {e}")
            return []

    
    def _to_full_code(self, code: str) -> str:
        """
        纯数字代码 → 加市场前缀（sz/sh）
        300058 → sz300058
        600000 → sh600000
        """
        if not code or len(code) != 6:
            return ""
        
        if code.startswith(('60', '68', '90')):
            return f"sh{code}"
        else:
            return f"sz{code}"

    def get_earnings_by_date(self, date: str) -> List[Dict]:
        """获取指定日期发布的财报"""
        earnings_list = []
        
        try:
            # 使用AKShare获取业绩预告
            try:
                yjyg_df = ak.stock_yjbb_em(date=date)
                print(yjyg_df)
            except Exception as e:
                yjyg_df = None
                print(f"获取财报数据失败: {e}")
            if yjyg_df is not None and not yjyg_df.empty:
                watchlist_codes = self._load_watchlist_codes()
                if watchlist_codes:
                    codes = yjyg_df['股票代码'].fillna('').astype(str).str.strip()
    
                    # 筛选自选股池
                    yjyg_df = yjyg_df[codes.isin(watchlist_codes)]
                    
                    print(f"仅处理自选池股票，共{len(yjyg_df)}条业绩预告记录")
                else:
                    print("未找到自选池，默认处理所有业绩预告记录")

               # target_date = pd.to_datetime(date)


               # filtered = yjyg_df[yjyg_df['最新公告日期'].dt.date != target_date.date()]
                yjyg_df['最新公告日期'] = pd.to_datetime(yjyg_df['最新公告日期'], errors='coerce')
                            
                 # 获取今天日期
                today = pd.Timestamp.now()
                
                # 往前推 5 个【交易日】（自动跳过周末、节假日）
                # 这是你最想要的功能！
                business_days = pd.bdate_range(end=today, periods=5)
                start_date = business_days[0]  # 第 1 天（最早那天）
                end_date = business_days[-1]   # 今天


                for _, row in yjyg_df.iterrows():
                     # 筛选指定日期的公告

            
                    # 筛选 近5天内发布的公告
                    ann_date = row.get('最新公告日期')
                    #跳过：空值 OR 不在最近5个交易日内
                    if ann_date >= start_date:
                        print("this is row: ", row)

                    elif pd.isna(ann_date) or not (start_date < ann_date < end_date):
                        print("ann_date is: ", ann_date, ", start_date: ", start_date, ", end_date: ", end_date)
                        continue
                        
                    




                    earnings = {
                        'stock_code': self._to_full_code(row.get('股票代码', '')),
                        'stock_name': row.get('股票简称', ''),
                        'announcement_date': row.get('最新公告日期', ''),
                        'report_date': row.get('最新公告日期', ''),
                        'quarter': self._get_quarter_from_date(row.get('最新公告日期', '')),
                        'industry': row.get('所处行业', ''),
                        'eps': row.get('每股收益', ''),
                        'revenue': row.get('营业总收入-营业总收入', ''),
                        'revenue_yoy': row.get('营业总收入-同比增长', ''),
                        'revenue_qoq': row.get('营业总收入-季度环比增长', ''),
                        'net_profit': row.get('净利润-净利润', ''),
                        'net_profit_yoy': row.get('净利润-同比增长', ''),
                        'net_profit_qoq': row.get('净利润-季度环比增长', ''),
                        'net_asset_per_share': row.get('每股净资产', ''),
                        'roe': row.get('净资产收益率', ''),
                        'operating_cashflow_per_share': row.get('每股经营现金流量', ''),
                        'gross_margin': row.get('销售毛利率', ''),
                    }
                    
                    earnings_list.append(earnings)
            
            # 获取正式财报（使用利润表数据）
            # 这里简化处理，实际需要从多个接口获取
            
        except Exception as e:
            print(f"获取财报数据失败: {e}")
        
        return earnings_list
    
    def get_earnings_in_range(self, start_date: str, end_date: str) -> List[Dict]:
        """获取日期范围内的所有财报"""
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        all_earnings = []
        current = start
        
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            earnings = self.get_earnings_by_date(date_str)
            all_earnings.extend(earnings)
            current += timedelta(days=1)
            time.sleep(0.5)  # 避免请求过快
        
        return all_earnings
    
    def get_earnings_by_stock(self, stock_code: str, quarter: str = None) -> Optional[Dict]:
        """获取指定股票的财报"""
        try:
            # 获取利润表数据
            profit_df = ak.stock_profit_sheet_by_report_em(symbol=stock_code)
            
            if profit_df is not None and not profit_df.empty:
                latest = profit_df.iloc[0]
                
                earnings = {
                    'stock_code': stock_code,
                    'stock_name': self._get_stock_name(stock_code),
                    'announcement_date': latest.get('公告日期', datetime.now().strftime('%Y-%m-%d')),
                    'quarter': quarter or latest.get('报告期', ''),
                    'net_profit': self._parse_number(latest.get('净利润', 0)),
                    'net_profit_yoy': self._calculate_yoy(profit_df, '净利润'),
                    'revenue': self._parse_number(latest.get('营业总收入', 0)),
                    'revenue_yoy': self._calculate_yoy(profit_df, '营业总收入'),
                    'gross_margin': self._parse_number(latest.get('销售毛利率', 0)),
                    'operating_cash_flow': self._parse_number(latest.get('经营活动现金流净额', 0)),
                    'source': '正式财报'
                }
                
                return earnings
            
        except Exception as e:
            print(f"获取{stock_code}财报失败: {e}")
        
        return None
    
    def get_analyst_ratings(self, stock_code: str) -> List[Dict]:
        """获取分析师评级"""
        ratings = []
        
        try:
            # 获取分析师评级数据
            if len(stock_code) > 6:
                code = stock_code[2:]
            else:
                code = stock_code

          
            rating_df = ak.stock_research_report_em(symbol=code)
           # rating_df = ak.stock_institute_recommend_detail(symbol=stock_code)

            # # 过滤当前股票
            # df = rating_df[rating_df["股票代码"] == stock_code].copy()
            # if df.empty:
            #     return None

            # # 只取有目标价的记录
            # df = df.dropna(subset=["目标价"])
            # if df.empty:
            #     return None
            
            # print("rating_df: ", df["股票代码"], df["目标价"])
            if rating_df is not None and not rating_df.empty:
                for _, row in rating_df.head(10).iterrows():
                    print(row.get('目标价_下限'), row.get("目标价_上限"))
                    target_price = row.get('目标价_下限')
                    if pd.isna(target_price) or target_price == '-':
                        target_price = row.get('目标价_上限')

                      # 如果还是没有目标价，则跳过这份研报
                    if pd.isna(target_price) or target_price == '-':
                        continue

                    rating = {
                        'date': row.get('日期', ''),
                        'institution': row.get('机构', ''),
                        'rating': row.get('东财评级', ''),
                        #'change': self._get_rating_change(row.get('评级调整', '')),
                        'target_price': self._parse_number(target_price)
                    }
                    ratings.append(rating)
                    
        except Exception as e:
            print(f"获取{stock_code}评级失败: {e}")
        
        return ratings
    
    def get_target_price(self, stock_code: str) -> Optional[float]:
        """获取目标价"""
        try:
            ratings = self.get_analyst_ratings(stock_code)
            if ratings:
                target_prices = [r['target_price'] for r in ratings if r['target_price'] > 0]
                if target_prices:
                    return sum(target_prices) / len(target_prices)
        except:
            pass
        return None

    def _get_spot_data(self) -> pd.DataFrame:
        """获取缓存的实时行情"""
        if  self._spot_cache is None:
            self._spot_cache = ak.stock_zh_a_spot_em()
            print(f"刷新缓存，共{len(self._spot_cache)}只股票")  # 调试用
        return self._spot_cache


    def get_current_price(self, stock_code: str) -> Optional[float]:
        """获取当前股价"""
        try:
            # 获取实时行情

            spot_df = self._get_spot_data()
            stock_row = spot_df[spot_df['代码'] == stock_code[2:]]
            
            if not stock_row.empty:
                return float(stock_row['最新价'].iloc[0])
        except:
            pass
        return None
    
    def get_industry_performance(self, industry: str) -> Optional[float]:
        """获取行业表现"""
        try:
            # 获取行业板块表现
            sector_df = ak.stock_board_industry_summary_ths()
            if sector_df is not None and not sector_df.empty:
                sector_row = sector_df[sector_df['板块'] == industry]
                if not sector_row.empty:
                    return float(sector_row['涨跌幅'].iloc[0])
        except:
            pass
        return None
    
    def get_analyst_forecast(self, stock_code: str, quarter: str) -> Dict:
        """获取分析师预期数据"""
        # 简化实现，实际需要从专业数据源获取
        # 这里返回模拟数据
        return {
            'eps_forecast': None,
            'revenue_forecast': None,
            'forecast_count': 0
        }
    
    def _get_quarter_from_date(self, date: str) -> str:
        """根据日期获取季度"""
        dt = pd.to_datetime(date)
        month = dt.month
        year = dt.year
        
        if month <= 3:
            return f"{year}Q1"
        elif month <= 6:
            return f"{year}Q2"
        elif month <= 9:
            return f"{year}Q3"
        else:
            return f"{year}Q4"
    
    def _get_stock_name(self, stock_code: str) -> str:
        """获取股票名称"""
        try:
            spot_df = ak.stock_zh_a_spot_em()
            stock_row = spot_df[spot_df['代码'] == stock_code]
            if not stock_row.empty:
                return stock_row['名称'].iloc[0]
        except:
            pass
        return stock_code
    
    def _calculate_yoy(self, df: pd.DataFrame, column: str) -> float:
        """计算同比增长率"""
        if len(df) >= 2:
            current = self._parse_number(df.iloc[0].get(column, 0))
            previous = self._parse_number(df.iloc[1].get(column, 0))
            
            if previous != 0:
                return (current - previous) / abs(previous) * 100
        return 0
    
    def _parse_number(self, value) -> float:
        """解析数值"""
        if value is None or value == '-':
            return 0
        try:
            if isinstance(value, str):
                # 移除单位和逗号
                value = value.replace('亿', '').replace('万', '').replace(',', '')
                # 处理百分比
                if '%' in value:
                    value = value.replace('%', '')
                return float(value)
            return float(value)
        except:
            return 0
    
    def _get_rating_change(self, change_str: str) -> str:
        """解析评级变化"""
        if not change_str:
            return '维持'
        if '上调' in change_str:
            return '上调'
        elif '下调' in change_str:
            return '下调'
        else:
            return '维持'
