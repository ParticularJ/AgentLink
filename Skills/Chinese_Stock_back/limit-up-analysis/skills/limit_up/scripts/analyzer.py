#!/usr/bin/env python3
"""
A股涨停板连板分析器
基于多维度量化分析的涨停板连板可能性评估系统
支持多数据源：akshare、tushare、baostock、yfinance
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

import pandas as pd
from colorama import Fore, Style, init

# 导入数据源适配器
try:
    from skills.scripts.data_source_adapter import DataSourceAdapter
except ImportError:
    sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/limit-up-analysis')
    from skills.scripts.data_source_adapter import DataSourceAdapter

# 初始化颜色输出
init(autoreset=True)


class StockDataFetcher:
    """股票数据获取器 - 支持多数据源"""
    
    def __init__(self, data_source: str = "auto", cache_ttl: int = 5):
        self.cache_ttl = cache_ttl
        self.cache_dir = os.path.expanduser("~/.openclaw/stock/data/cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 初始化数据源适配器
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源，请安装akshare、tushare、baostock或yfinance")
    
    def get_limit_up_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """获取涨停股票列表"""
        try:
            # 涨停数据目前只有akshare支持，尝试直接使用akshare
            try:
                import akshare as ak
                print(f"{Fore.CYAN}📊 正在尝试连接akshare获取涨停数据...{Style.RESET_ALL}")
                date = date or datetime.now().strftime("%Y%m%d")
                df = ak.stock_zt_pool_em(date=date)
                print(f"{Fore.GREEN}✅ 成功获取涨停数据，共{len(df)}只股票{Style.RESET_ALL}")
                return df
            except ImportError:
                print(f"{Fore.YELLOW}⚠️ 未安装akshare，无法获取涨停数据{Style.RESET_ALL}")
                print(f"{Fore.CYAN}   请安装: pip install akshare{Style.RESET_ALL}")
                return pd.DataFrame()
            except Exception as e:
                print(f"{Fore.YELLOW}⚠️ akshare连接失败: {e}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}   当前环境可能无法连接akshare服务器{Style.RESET_ALL}")
                return pd.DataFrame()
        except Exception as e:
            print(f"{Fore.RED}❌ 获取涨停数据失败: {e}{Style.RESET_ALL}")
            return pd.DataFrame()
    
    def get_stock_data(self, stock_code: str, days: int = 30) -> Optional[pd.DataFrame]:
        """获取股票历史数据"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        return self.data_adapter.get_stock_data(
            stock_code,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d')
        )


class LimitUpAnalyzer:
    """涨停板连板分析器"""
    
    # 评分权重配置（与scoring_weights.yaml一致）
    WEIGHTS = {
        'sealing_strength': 0.30,    # 封板强度
        'sector_effect': 0.20,       # 板块效应
        'capital_flow': 0.20,        # 资金流向
        'technical_pattern': 0.20,   # 技术形态
        'market_sentiment': 0.10     # 市场情绪
    }
    
    # 评分阈值（与scoring_weights.yaml一致）
    THRESHOLDS = {
        'strong_buy': 85,    # 极高
        'buy': 75,           # 高
        'watch': 65,         # 中等
        'exclude': 55        # 低
    }
    
    def __init__(self, data_source: str = "auto"):
        self.fetcher = StockDataFetcher(data_source)
        self.data_dir = os.path.expanduser("~/.openclaw/stock/data")
        self.history_dir = os.path.join(self.data_dir, "history")
        self._ensure_dirs()
    
    def _ensure_dirs(self):
        """确保数据目录存在"""
        os.makedirs(self.history_dir, exist_ok=True)
    
    def calc_scores(self, row: pd.Series, all_df: pd.DataFrame) -> Dict:
        """基于涨停数据计算五维度评分
                WEIGHTS = {
            'sealing_strength': 0.30,   # 封板强度 → 最重要
            'sector_effect': 0.20,      # 板块效应 → 中等
            'capital_flow': 0.20,       # 资金流向 → 非常重要
            'technical_pattern': 0.20,  # 技术形态 → 重要
            'market_sentiment': 0.10    # 市场情绪 → 次要
        }
        
        
        """
             
        scores = {}
        
        # 1. 封板强度 (30%) —— 实战优化版
        sealing_score = 30  # 基础分降低

        # 封板时间（核心：越早越强）
        first_time = row.get('首次封板时间', '')
        if first_time and len(first_time) >= 4:
            try:
                hour = int(first_time[:2])
                minute = int(first_time[2:4])
                if hour == 9 and minute <= 32:   # 9:32前 最强
                    sealing_score += 40
                elif hour == 9 and minute <= 40:
                    sealing_score += 30
                elif hour == 9 and minute <= 50:
                    sealing_score += 20
                elif hour == 9:
                    sealing_score += 10
                elif hour == 10:
                    sealing_score += 5
                # 10点后不加分
            except:
                pass

        # 炸板次数（炸板必须扣分！）
        open_count = row.get('炸板次数', 0)
        if open_count == 0:
            sealing_score += 20  # 完美封板
        elif open_count == 1:
            sealing_score += 10
        elif open_count == 2:
            sealing_score += 0
        else:
            sealing_score -= 15  # 多次炸板直接扣分

        # 封板资金
        seal_amount = row.get('封板资金', 0)
        if seal_amount >= 150000000:
            sealing_score += 15
        elif seal_amount >= 80000000:
            sealing_score += 10
        elif seal_amount >= 30000000:
            sealing_score += 5

        scores['sealing_strength'] = max(0, min(100, sealing_score))
        
        # 2. 板块效应 (20%) —— 更真实
        sector = row.get('所属行业', '')
        sector_count = len(all_df[all_df['所属行业'] == sector])
        sector_score = 20  # 基础分降低

        if sector_count >= 8:
            sector_score += 30
        elif sector_count >= 5:
            sector_score += 20
        elif sector_count >= 3:
            sector_score += 10
        elif sector_count >= 1:
            sector_score += 5

        # 龙头地位（只有龙1加分，龙2不加分，更真实）
        sector_df = all_df[all_df['所属行业'] == sector].sort_values('首次封板时间')
        if not sector_df.empty and sector_df.iloc[0]['代码'] == row['代码']:
            sector_score += 30  # 真龙头大幅加分

        scores['sector_effect'] = max(0, min(100, sector_score))
        



        # 3. 资金流向 (20%) —— 不再瞎给分
        capital_score = 40

        # 换手率（健康区间加分）
        turnover = row.get('换手率', 0)
        if 3 <= turnover <= 15:
            capital_score += 25
        elif 15 < turnover <= 25:
            capital_score += 10
        elif turnover > 30:
            capital_score -= 20  # 高换手危险

        # 封单/流通市值（越强越安全）
        lt = row.get('流通市值', 1)
        seal_amount = row.get('封板资金', 0)
        if lt > 0 and seal_amount / lt > 0.08:
            capital_score += 25
        elif seal_amount / lt > 0.04:
            capital_score += 15
        elif seal_amount / lt > 0.02:
            capital_score += 5

        scores['capital_flow'] = max(0, min(100, capital_score))
        # 4. 技术形态 (20%)
        limit_up_days = row.get('连板数', 1)
        lt = row.get('流通市值', 99999999999)

        tech_score = 40

        # 连板
        if limit_up_days >= 5:
            tech_score += 30
        elif limit_up_days >= 3:
            tech_score += 20
        elif limit_up_days >= 2:
            tech_score += 10

        # 流通盘（小票更容易连板，加分）
        if lt < 5000000000:   # 50亿
            tech_score += 15
        elif lt < 10000000000: # 100亿
            tech_score += 8

        # 股价（低价更容易涨）
        price = row.get('最新价', 999)
        if 5 <= price <= 20:
            tech_score += 10

        scores['technical_pattern'] = max(0, min(100, tech_score))

        # 5. 市场情绪 (10%)
        sentiment_score = 40

        # 连板高度
        if limit_up_days >= 5:
            sentiment_score += 30
        elif limit_up_days >= 3:
            sentiment_score += 15
        elif limit_up_days >= 2:
            sentiment_score += 8

        # 市场涨停家数
        total_zt = len(all_df)
        if total_zt >= 80:
            sentiment_score += 15
        elif total_zt >= 40:
            sentiment_score += 8
        elif total_zt >= 20:
            sentiment_score += 3

        scores['market_sentiment'] = max(0, min(100, sentiment_score))


        # 总分（使用配置的权重）
        total = (
            scores['sealing_strength'] * self.WEIGHTS['sealing_strength'] +
            scores['sector_effect'] * self.WEIGHTS['sector_effect'] +
            scores['capital_flow'] * self.WEIGHTS['capital_flow'] +
            scores['technical_pattern'] * self.WEIGHTS['technical_pattern'] +
            scores['market_sentiment'] * self.WEIGHTS['market_sentiment']
        )
        scores['total'] = round(total, 1)
        
        return scores
    
    def get_rating(self, score: float) -> Dict:
        """获取评级"""
        if score >= self.THRESHOLDS['strong_buy']:
            return {'label': '极高', 'description': '龙头气质'}
        elif score >= self.THRESHOLDS['buy']:
            return {'label': '高', 'description': '连板可能性大'}
        elif score >= self.THRESHOLDS['watch']:
            return {'label': '中等', 'description': '需结合盘面'}
        elif score >= self.THRESHOLDS['exclude']:
            return {'label': '低', 'description': '谨慎参与'}
        else:
            return {'label': '极低', 'description': '建议观望'}
    
    def get_recommendation(self, score: float) -> str:
        """获取操作建议"""
        if score >= self.THRESHOLDS['strong_buy']:
            return f"{Fore.GREEN}✅ 重点关注 - 龙头气质，明日高开概率极大{Style.RESET_ALL}"
        elif score >= self.THRESHOLDS['buy']:
            return f"{Fore.GREEN}✅ 关注 - 连板可能性大，可考虑打板{Style.RESET_ALL}"
        elif score >= self.THRESHOLDS['watch']:
            return f"{Fore.YELLOW}⚠️ 观察 - 需结合明日开盘情况判断{Style.RESET_ALL}"
        elif score >= self.THRESHOLDS['exclude']:
            return f"{Fore.YELLOW}⚠️ 谨慎 - 连板概率较低，不建议追高{Style.RESET_ALL}"
        else:
            return f"{Fore.RED}❌ 观望 - 连板可能性极低{Style.RESET_ALL}"
    
    def analyze_all_limit_up(self) -> List[Dict]:
        """分析当日所有涨停股票"""
        print(f"{Fore.CYAN}📊 正在获取当日涨停股票数据...{Style.RESET_ALL}")
        print(f"{Fore.CYAN}   使用数据源: {self.fetcher.data_adapter.source}{Style.RESET_ALL}")
        
        limit_up_df = self.fetcher.get_limit_up_stocks()
        if limit_up_df.empty:
            print(f"{Fore.YELLOW}⚠️ 未获取到涨停数据{Style.RESET_ALL}")
            return []
        
        print(f"{Fore.GREEN}✅ 获取到 {len(limit_up_df)} 只涨停股票{Style.RESET_ALL}")
        
        results = []
        for _, row in limit_up_df.iterrows():
            # print("row: ", row)
            scores = self.calc_scores(row, limit_up_df)
            
            result = {
                'stock_code': row['代码'],
                'stock_name': row['名称'],
                'date': datetime.now().strftime("%Y-%m-%d"),
                'limit_up_days': row['连板数'],
                'sector': row['所属行业'],
                'first_time': row['首次封板时间'],
                'open_count': row['炸板次数'],
                'seal_amount': row['封板资金'],
                'all_scores': scores,
                'score': scores['total'],
                'rating': self.get_rating(scores['total']),
                'recommendation': self.get_recommendation(scores['total'])
            }
            results.append(result)
        
        # 按总分排序
        results.sort(key=lambda x: x['all_scores']['total'], reverse=True)
        
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
        if total >= self.THRESHOLDS['buy']:
            color = Fore.GREEN
        elif total >= self.THRESHOLDS['watch']:
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
            score_color = Fore.GREEN if score >= self.THRESHOLDS['buy'] else (Fore.YELLOW if score >= self.THRESHOLDS['watch'] else Fore.WHITE)
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
    parser = argparse.ArgumentParser(description='A股涨停板连板分析器 - 支持多数据源')
    parser.add_argument('--code', type=str, help='分析单只股票，如 000001')
    parser.add_argument('--all', action='store_true', help='分析当日所有涨停股')
    parser.add_argument('--history', type=str, help='查看历史分析，格式 YYYY-MM-DD')
    parser.add_argument('--save', action='store_true', help='保存分析结果')
    parser.add_argument('--top', type=int, default=10, help='显示前N名，默认10')
    parser.add_argument('--source', type=str, default='auto', 
                       choices=['auto', 'akshare', 'tushare', 'baostock', 'yfinance'],
                       help='数据源选择 (默认auto自动选择)')
    
    args = parser.parse_args()
    
    try:
        analyzer = LimitUpAnalyzer(data_source=args.source)
    except RuntimeError as e:
        print(f"{Fore.RED}错误: {e}{Style.RESET_ALL}")
        print("\n请安装以下数据源之一:")
        print("  pip install akshare    # 推荐，免费")
        print("  pip install tushare    # 需要token")
        print("  pip install baostock   # 免费")
        print("  pip install yfinance   # 有限支持A股")
        return
    
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
