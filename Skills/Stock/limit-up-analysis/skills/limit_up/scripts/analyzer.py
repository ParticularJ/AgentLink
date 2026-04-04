#!/usr/bin/env python3
"""
A股涨停板连板分析器
基于多维度量化分析的涨停板连板可能性评估系统
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# 清除代理环境变量，避免连接问题
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    if key in os.environ:
        del os.environ[key]

import akshare as ak
import pandas as pd
from colorama import Fore, Style, init

# 初始化颜色输出
init(autoreset=True)


class StockDataFetcher:
    """股票数据获取器"""
    
    def __init__(self, cache_ttl: int = 5):
        self.cache_ttl = cache_ttl
        self.cache_dir = os.path.expanduser("~/.openclaw/stock/data/cache")
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_limit_up_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """获取涨停股票列表"""
        try:
            date = date or datetime.now().strftime("%Y%m%d")
            df = ak.stock_zt_pool_em(date=date)
            return df
        except Exception as e:
            print(f"{Fore.RED}❌ 获取涨停数据失败: {e}{Style.RESET_ALL}")
            return pd.DataFrame()


class LimitUpAnalyzer:
    """涨停板连板分析器"""
    
    def __init__(self):
        self.fetcher = StockDataFetcher()
        self.data_dir = os.path.expanduser("~/.openclaw/stock/data")
        self.history_dir = os.path.join(self.data_dir, "history")
        self._ensure_dirs()
    
    def _ensure_dirs(self):
        """确保数据目录存在"""
        os.makedirs(self.history_dir, exist_ok=True)
    
    def calc_scores(self, row: pd.Series, all_df: pd.DataFrame) -> Dict:
        """基于涨停数据计算五维度评分"""
        scores = {}
        
        # 1. 封板强度 (30%)
        sealing_score = 50
        
        # 封板时间评分
        first_time = row.get('首次封板时间', '')
        if first_time and len(first_time) >= 4:
            try:
                hour = int(first_time[:2])
                minute = int(first_time[2:4])
                if hour == 9 and minute <= 35:
                    sealing_score += 25
                elif hour == 9 and minute <= 45:
                    sealing_score += 20
                elif hour == 9:
                    sealing_score += 15
                else:
                    sealing_score += 10
            except:
                pass
        
        # 炸板次数评分
        open_count = row.get('炸板次数', 0)
        if open_count == 0:
            sealing_score += 15
        elif open_count == 1:
            sealing_score += 10
        elif open_count <= 2:
            sealing_score += 5
        
        # 封板资金评分
        seal_amount = row.get('封板资金', 0)
        if seal_amount > 100000000:  # 1亿
            sealing_score += 10
        elif seal_amount > 50000000:
            sealing_score += 7
        elif seal_amount > 10000000:
            sealing_score += 5
        
        scores['sealing_strength'] = min(100, sealing_score)
        
        # 2. 板块效应 (25%)
        sector = row.get('所属行业', '')
        sector_count = len(all_df[all_df['所属行业'] == sector])
        sector_score = 40
        if sector_count >= 10:
            sector_score += 30
        elif sector_count >= 5:
            sector_score += 22
        elif sector_count >= 3:
            sector_score += 15
        elif sector_count >= 1:
            sector_score += 8
        
        # 龙头地位
        sector_df = all_df[all_df['所属行业'] == sector].sort_values('首次封板时间')
        if not sector_df.empty and sector_df.iloc[0]['代码'] == row['代码']:
            sector_score += 20
        elif len(sector_df) > 1 and sector_df.iloc[1]['代码'] == row['代码']:
            sector_score += 10
        
        scores['sector_effect'] = min(100, sector_score)
        
        # 3. 资金流向 (20%) - 涨停数据中无此信息，给基础分
        scores['capital_flow'] = 60
        
        # 4. 技术形态 (15%) - 根据连板数推断
        limit_up_days = row.get('连板数', 1)
        if limit_up_days >= 5:
            scores['technical_pattern'] = 85
        elif limit_up_days >= 3:
            scores['technical_pattern'] = 75
        elif limit_up_days >= 2:
            scores['technical_pattern'] = 65
        else:
            scores['technical_pattern'] = 55
        
        # 5. 市场情绪 (10%)
        sentiment_score = 50
        if limit_up_days >= 5:
            sentiment_score += 30
        elif limit_up_days >= 3:
            sentiment_score += 20
        elif limit_up_days >= 2:
            sentiment_score += 10
        
        # 涨停数量
        total_zt = len(all_df)
        if total_zt >= 100:
            sentiment_score += 15
        elif total_zt >= 50:
            sentiment_score += 10
        elif total_zt >= 30:
            sentiment_score += 5
        
        scores['market_sentiment'] = min(100, sentiment_score)
        
        # 总分
        total = (
            scores['sealing_strength'] * 0.30 +
            scores['sector_effect'] * 0.25 +
            scores['capital_flow'] * 0.20 +
            scores['technical_pattern'] * 0.15 +
            scores['market_sentiment'] * 0.10
        )
        scores['total'] = round(total, 1)
        
        return scores
    
    def get_rating(self, score: float) -> Dict:
        """获取评级"""
        if score >= 85:
            return {'label': '极高', 'description': '龙头气质'}
        elif score >= 75:
            return {'label': '高', 'description': '连板可能性大'}
        elif score >= 65:
            return {'label': '中等', 'description': '需结合盘面'}
        elif score >= 55:
            return {'label': '低', 'description': '谨慎参与'}
        else:
            return {'label': '极低', 'description': '建议观望'}
    
    def get_recommendation(self, score: float) -> str:
        """获取操作建议"""
        if score >= 85:
            return f"{Fore.GREEN}✅ 重点关注 - 龙头气质，明日高开概率极大{Style.RESET_ALL}"
        elif score >= 75:
            return f"{Fore.GREEN}✅ 关注 - 连板可能性大，可考虑打板{Style.RESET_ALL}"
        elif score >= 65:
            return f"{Fore.YELLOW}⚠️ 观察 - 需结合明日开盘情况判断{Style.RESET_ALL}"
        elif score >= 55:
            return f"{Fore.YELLOW}⚠️ 谨慎 - 连板概率较低，不建议追高{Style.RESET_ALL}"
        else:
            return f"{Fore.RED}❌ 观望 - 连板可能性极低{Style.RESET_ALL}"
    
    def analyze_all_limit_up(self) -> List[Dict]:
        """分析当日所有涨停股票"""
        print(f"{Fore.CYAN}📊 正在获取当日涨停股票数据...{Style.RESET_ALL}")
        
        limit_up_df = self.fetcher.get_limit_up_stocks()
        if limit_up_df.empty:
            print(f"{Fore.YELLOW}⚠️ 未获取到涨停数据{Style.RESET_ALL}")
            return []
        
        print(f"{Fore.GREEN}✅ 获取到 {len(limit_up_df)} 只涨停股票{Style.RESET_ALL}")
        
        results = []
        for _, row in limit_up_df.iterrows():
            scores = self.calc_scores(row, limit_up_df)
            
            result = {
                'code': row['代码'],
                'name': row['名称'],
                'date': datetime.now().strftime("%Y-%m-%d"),
                'limit_up_days': row['连板数'],
                'sector': row['所属行业'],
                'first_time': row['首次封板时间'],
                'open_count': row['炸板次数'],
                'seal_amount': row['封板资金'],
                'scores': scores,
                'rating': self.get_rating(scores['total']),
                'recommendation': self.get_recommendation(scores['total'])
            }
            results.append(result)
        
        # 按总分排序
        results.sort(key=lambda x: x['scores']['total'], reverse=True)
        
        return results
    
    def analyze_stock(self, code: str) -> Optional[Dict]:
        """分析单只股票"""
        limit_up_df = self.fetcher.get_limit_up_stocks()
        if limit_up_df.empty:
            return None
        
        stock_row = limit_up_df[limit_up_df['代码'] == code]
        if stock_row.empty:
            print(f"{Fore.YELLOW}⚠️ 股票 {code} 不在今日涨停列表中{Style.RESET_ALL}")
            return None
        
        row = stock_row.iloc[0]
        scores = self.calc_scores(row, limit_up_df)
        
        return {
            'code': row['代码'],
            'name': row['名称'],
            'date': datetime.now().strftime("%Y-%m-%d"),
            'limit_up_days': row['连板数'],
            'sector': row['所属行业'],
            'scores': scores,
            'rating': self.get_rating(scores['total']),
            'recommendation': self.get_recommendation(scores['total'])
        }
    
    def print_analysis(self, result: Dict):
        """打印分析结果"""
        code = result['code']
        name = result['name']
        scores = result['scores']
        total = scores['total']
        rating = result['rating']
        
        # 根据分数设置颜色
        if total >= 75:
            color = Fore.GREEN
        elif total >= 65:
            color = Fore.YELLOW
        else:
            color = Fore.WHITE
        
        print(f"\n{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}")
        print(f"{Fore.CYAN}📈 股票: {code} {name} ({result['sector']}){Style.RESET_ALL}")
        print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}\n")
        
        print(f"{Fore.WHITE}【综合评分】 {color}{total}/100 ({rating['label']}){Style.RESET_ALL}")
        print(f"{Fore.WHITE}【连板数】 {result['limit_up_days']}板{Style.RESET_ALL}\n")
        
        print(f"{Fore.WHITE}【五维分析】{Style.RESET_ALL}")
        bar_width = 30
        dimensions = [
            ('封板强度', scores['sealing_strength']),
            ('板块效应', scores['sector_effect']),
            ('资金流向', scores['capital_flow']),
            ('技术形态', scores['technical_pattern']),
            ('市场情绪', scores['market_sentiment'])
        ]
        
        for dim_name, score in dimensions:
            filled = int(score / 100 * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            score_color = Fore.GREEN if score >= 75 else (Fore.YELLOW if score >= 65 else Fore.WHITE)
            print(f"  {dim_name}: {bar} {score_color}{score:.0f}{Style.RESET_ALL}")
        
        print(f"\n{Fore.WHITE}【操作建议】{Style.RESET_ALL}")
        print(f"  {result['recommendation']}\n")
    
    def save_result(self, result: Dict):
        """保存分析结果"""
        date = result.get('date', datetime.now().strftime("%Y-%m-%d"))
        filename = os.path.join(self.history_dir, f"{date}.json")
        
        existing = []
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                pass
        
        code = result.get('code')
        existing = [r for r in existing if r.get('code') != code]
        existing.append(result)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    
    def load_history(self, date: str) -> List[Dict]:
        """加载历史分析数据"""
        filename = os.path.join(self.history_dir, f"{date}.json")
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"{Fore.RED}❌ 加载历史数据失败: {e}{Style.RESET_ALL}")
        return []


def main():
    parser = argparse.ArgumentParser(description='A股涨停板连板分析器')
    parser.add_argument('--code', type=str, help='分析单只股票，如 000001')
    parser.add_argument('--all', action='store_true', help='分析当日所有涨停股')
    parser.add_argument('--history', type=str, help='查看历史分析，格式 YYYY-MM-DD')
    parser.add_argument('--save', action='store_true', help='保存分析结果')
    parser.add_argument('--top', type=int, default=10, help='显示前N名，默认10')
    
    args = parser.parse_args()
    
    analyzer = LimitUpAnalyzer()
    
    if args.code:
        result = analyzer.analyze_stock(args.code)
        if result:
            analyzer.print_analysis(result)
            if args.save:
                analyzer.save_result(result)
                print(f"{Fore.GREEN}✅ 结果已保存{Style.RESET_ALL}")
    
    elif args.all:
        results = analyzer.analyze_all_limit_up()
        if results:
            print(f"\n{Fore.CYAN}📊 当日涨停股票连板可能性分析 (前{args.top}名){Style.RESET_ALL}\n")
            for i, result in enumerate(results[:args.top], 1):
                print(f"{Fore.YELLOW}#{i}{Style.RESET_ALL}", end=" ")
                analyzer.print_analysis(result)
                if args.save:
                    analyzer.save_result(result)
            if args.save:
                print(f"{Fore.GREEN}✅ 所有结果已保存{Style.RESET_ALL}")
    
    elif args.history:
        results = analyzer.load_history(args.history)
        if results:
            print(f"\n{Fore.CYAN}📊 {args.history} 涨停股票分析{Style.RESET_ALL}\n")
            results.sort(key=lambda x: x.get('scores', {}).get('total', 0), reverse=True)
            for i, result in enumerate(results[:args.top], 1):
                print(f"{Fore.YELLOW}#{i}{Style.RESET_ALL}", end=" ")
                analyzer.print_analysis(result)
        else:
            print(f"{Fore.YELLOW}⚠️ 未找到 {args.history} 的历史数据{Style.RESET_ALL}")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
