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

# 导入新闻情绪模块
try:
    from skills.scripts.news_sentiment import search_stock_news, calc_news_penalty
except ImportError:
    # sys.path dynamically set below
    try:
        from skills.scripts.news_sentiment import search_stock_news, calc_news_penalty
    except ImportError:
        search_stock_news = None
        calc_news_penalty = None

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
    
    # 评分权重配置（五维评分，新闻情绪作为加减分项）
    WEIGHTS = {
        'sealing_strength': 0.30,    # 封板强度 (30%)
        'sector_effect': 0.25,       # 板块效应 (25%)
        'capital_flow': 0.20,        # 资金流向 (20%)
        'technical_pattern': 0.15,   # 技术形态 (15%)
        'market_sentiment': 0.10,    # 市场情绪 (10%)
        # 新闻情绪不作为维度，而是作为加减分项 (-10 ~ +5分)
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
    
    def calc_scores(self, row: pd.Series, all_df: pd.DataFrame, market_sentiment: float = None) -> Dict:
        """基于涨停数据计算六维度评分（新增新闻情绪）"""
        scores = {}
        
        # 1. 封板强度 (28%)
        sealing_score = 50
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
        
        open_count = row.get('炸板次数', 0)
        if open_count == 0:
            sealing_score += 15
        elif open_count == 1:
            sealing_score += 10
        elif open_count <= 2:
            sealing_score += 5
        
        seal_amount = row.get('封板资金', 0)
        if seal_amount > 100000000:
            sealing_score += 10
        elif seal_amount > 50000000:
            sealing_score += 7
        elif seal_amount > 10000000:
            sealing_score += 5
        
        scores['sealing_strength'] = min(100, sealing_score)
        
        # 2. 板块效应 (22%) - 基础分50，更合理
        sector = row.get('所属行业', '')
        sector_count = len(all_df[all_df['所属行业'] == sector])
        sector_score = 50  # 提高基础分
        if sector_count >= 10:
            sector_score += 25  # 热点板块
        elif sector_count >= 5:
            sector_score += 18
        elif sector_count >= 3:
            sector_score += 10
        elif sector_count >= 1:
            sector_score += 5
        
        sector_df = all_df[all_df['所属行业'] == sector].sort_values('首次封板时间')
        if not sector_df.empty and sector_df.iloc[0]['代码'] == row['代码']:
            sector_score += 15  # 板块龙头加分
        elif len(sector_df) > 1 and sector_df.iloc[1]['代码'] == row['代码']:
            sector_score += 8   # 板块龙二加分
        
        scores['sector_effect'] = min(100, sector_score)
        
        # 3. 资金流向 (18%) - 根据封板资金和连板数估算
        capital_score = 50  # 提高基础分
        seal_amount = row.get('封板资金', 0)
        if seal_amount > 500000000:  # 5亿
            capital_score += 30
        elif seal_amount > 100000000:  # 1亿
            capital_score += 20
        elif seal_amount > 50000000:  # 5000万
            capital_score += 12
        elif seal_amount > 10000000:  # 1000万
            capital_score += 6
        
        # 连板数反映资金认可度
        limit_up_days = row.get('连板数', 1)
        if limit_up_days >= 3:
            capital_score += 15  # 3板以上说明资金持续流入
        elif limit_up_days >= 2:
            capital_score += 8
        
        scores['capital_flow'] = min(100, capital_score)
        
        # 4. 技术形态 (14%) - 改为风险折扣模式
        limit_up_days = row.get('连板数', 1)
        if limit_up_days >= 6:
            scores['technical_pattern'] = 35  # ⚠️ 极高风险折扣
        elif limit_up_days >= 5:
            scores['technical_pattern'] = 45  # 高风险折扣
        elif limit_up_days >= 4:
            scores['technical_pattern'] = 55  # 中等风险
        elif limit_up_days >= 3:
            scores['technical_pattern'] = 65
        elif limit_up_days >= 2:
            scores['technical_pattern'] = 75
        else:
            scores['technical_pattern'] = 80  # 首板最强
        
        # 5. 市场情绪 (10%) - 使用传入的全局市场情绪
        if market_sentiment is not None:
            scores['market_sentiment'] = market_sentiment
        else:
            # 兼容单股分析模式
            scores['market_sentiment'] = self._calc_market_sentiment(all_df)
        
        # 新闻情绪不作为维度，而是作为加减分项
        # 默认0分（无影响），有负面新闻时扣分，有正面新闻时加分
        scores['news_adjustment'] = 0.0
        
        # 总分（五维加权）
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
        
        try:
            # 尝试获取上证指数数据
            df_sh = self.fetcher.data_adapter.get_stock_data('000001')
            if df_sh is not None and len(df_sh) >= 2:
                latest = df_sh.iloc[-1]
                prev = df_sh.iloc[-2]
                market_data['sh_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
                
                # 计算量比（今日成交量/昨日成交量）
                if 'volume' in latest and 'volume' in prev and prev['volume'] > 0:
                    market_data['sh_volume_ratio'] = latest['volume'] / prev['volume']
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 获取上证指数数据失败: {e}{Style.RESET_ALL}")
        
        try:
            # 尝试获取深证成指数据
            df_sz = self.fetcher.data_adapter.get_stock_data('399001')
            if df_sz is not None and len(df_sz) >= 2:
                latest = df_sz.iloc[-1]
                prev = df_sz.iloc[-2]
                market_data['sz_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 获取深证成指数据失败: {e}{Style.RESET_ALL}")
        
        try:
            # 尝试获取创业板指数据
            df_cy = self.fetcher.data_adapter.get_stock_data('399006')
            if df_cy is not None and len(df_cy) >= 2:
                latest = df_cy.iloc[-1]
                prev = df_cy.iloc[-2]
                market_data['cy_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 获取创业板指数据失败: {e}{Style.RESET_ALL}")
        
        try:
            # 尝试获取科创板指数据（科创50）
            df_kc = self.fetcher.data_adapter.get_stock_data('000688')
            if df_kc is not None and len(df_kc) >= 2:
                latest = df_kc.iloc[-1]
                prev = df_kc.iloc[-2]
                market_data['kc_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 获取科创板指数据失败: {e}{Style.RESET_ALL}")
        
        return market_data
    
    def _calc_market_sentiment(self, all_df: pd.DataFrame) -> float:
        """
        计算全局市场情绪得分（所有股票共享）
        基于大盘指数涨跌幅、成交量、涨停数量综合判断
        """
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
        
        # 3. 成交量评分 (20%) - 量比
        volume_ratio = market_data['sh_volume_ratio']
        if volume_ratio >= 1.5:
            score += 10  # 明显放量，情绪活跃
        elif volume_ratio >= 1.2:
            score += 7
        elif volume_ratio >= 1.0:
            score += 5
        elif volume_ratio >= 0.8:
            score += 2
        else:
            score -= 3  # 缩量，情绪低迷
        
        # 4. 涨停数量评分 (25%)
        total_zt = len(all_df)
        if total_zt >= 150:
            score += 15  # 情绪极度高涨
        elif total_zt >= 100:
            score += 12
        elif total_zt >= 70:
            score += 9
        elif total_zt >= 50:
            score += 6
        elif total_zt >= 30:
            score += 3
        elif total_zt < 20:
            score -= 8  # 涨停太少，情绪低迷
        
        # 5. 连板高度评分 (15%)
        if '连板数' in all_df.columns:
            max_limit = all_df['连板数'].max()
            avg_limit = all_df['连板数'].mean()
            
            # 最高连板数反映情绪热度
            if max_limit >= 7:
                score += 8  # 有7板股，情绪火热
            elif max_limit >= 5:
                score += 6
            elif max_limit >= 3:
                score += 3
            
            # 平均连板数
            if avg_limit >= 2:
                score += 4
            elif avg_limit >= 1.5:
                score += 2
        
        # 打印市场情绪详情
        print(f"{Fore.CYAN}📊 市场情绪分析:{Style.RESET_ALL}")
        print(f"   上证涨跌: {market_data['sh_change']:+.2f}%")
        print(f"   深证涨跌: {market_data['sz_change']:+.2f}%")
        print(f"   创业板涨跌: {market_data['cy_change']:+.2f}%")
        print(f"   科创板涨跌: {market_data['kc_change']:+.2f}%")
        print(f"   平均涨跌: {avg_index_change:+.2f}%")
        print(f"   上证量比: {market_data['sh_volume_ratio']:.2f}")
        print(f"   涨停数量: {total_zt}只")
        
        return min(100, max(0, round(score, 1)))
    
    def analyze_all_limit_up(self) -> List[Dict]:
        """分析当日所有涨停股票（含新闻情绪检测）"""
        print(f"{Fore.CYAN}📊 正在获取当日涨停股票数据...{Style.RESET_ALL}")
        print(f"{Fore.CYAN}   使用数据源: {self.fetcher.data_adapter.source}{Style.RESET_ALL}")

        limit_up_df = self.fetcher.get_limit_up_stocks()
        if limit_up_df.empty:
            print(f"{Fore.YELLOW}⚠️ 未获取到涨停数据{Style.RESET_ALL}")
            return []

        print(f"{Fore.GREEN}✅ 获取到 {len(limit_up_df)} 只涨停股票{Style.RESET_ALL}")
        
        # 计算全局市场情绪（所有股票共享）
        market_sentiment = self._calc_market_sentiment(limit_up_df)
        print(f"{Fore.CYAN}📊 当日市场情绪得分: {market_sentiment:.0f}{Style.RESET_ALL}")

        results = []
        for _, row in limit_up_df.iterrows():
            scores = self.calc_scores(row, limit_up_df, market_sentiment)
            result = {
                'stock_code': row['代码'],
                'stock_name': row['名称'],
                'date': datetime.now().strftime("%Y-%m-%d"),
                'limit_up_days': row['连板数'],
                'sector': row['所属行业'],
                'first_time': row['首次封板时间'],
                'open_count': row['炸板次数'],
                'seal_amount': row['封板资金'],
                'scores': scores,
                'score': scores['total'],
                'rating': self.get_rating(scores['total']),
                'recommendation': self.get_recommendation(scores['total']),
                'news': None,
            }
            results.append(result)

        # 按总分排序
        results.sort(key=lambda x: x['scores']['total'], reverse=True)
        # print(results[:5])  # 打印前5条结果预览
        # # ——— 新闻情绪检测（仅对前10名候选股）——

        # if search_stock_news and calc_news_penalty:
        #     print(f"\n{Fore.CYAN}📰 正在检测新闻情绪（前10名候选股）...{Style.RESET_ALL}")
        #     for r in results[:1]:
        #         try:
        #             print("The r is: ", r)
        #             news = search_stock_news(r['stock_code'], r['stock_name'], days=7)
        #             penalty = calc_news_penalty(
        #                 news['sentiment'],
        #                 news['sentiment_score'],
        #                 r['limit_up_days']
        #             )
        #             r['news'] = news
        #             # 新闻情绪作为加减分项，而不是维度
        #             # penalty 范围: -20 ~ +5
        #             r['scores']['news_adjustment'] = penalty
        #             print("Penalty is: ", penalty)
        #             # 修正总分：直接加减
        #             r['scores']['total'] = round(r['scores']['total'] + penalty, 1)
        #             r['score']= r['scores']['total']
        #             # 重新评级
        #             r['rating'] = self.get_rating(r['scores']['total'])
        #             r['recommendation'] = self.get_recommendation(r['scores']['total'])

        #             if news['sentiment'] == 'negative':
        #                 print(f"  {Fore.RED}⚠️ {r['stock_name']}({r['stock_code']}) 利空: {news['risk_warnings'][0][:50] if news['risk_warnings'] else news['news_summary']}{Style.RESET_ALL}")
        #             elif news['sentiment'] == 'positive':
        #                 print(f"  {Fore.GREEN}✅ {r['stock_name']}({r['stock_code']}) 利好: {news['highlights'][0][:50] if news['highlights'] else ''}{Style.RESET_ALL}")
        #         except Exception as e:
        #             print("Error: ", e)
        #             print(f"  {Fore.YELLOW}⚠️ {r['stock_name']} 新闻检测失败: {e}{Style.RESET_ALL}")

        #     # 重新排序
        #     results.sort(key=lambda x: x['scores']['total'], reverse=True)
        # else:
        #     print(f"\n{Fore.YELLOW}⚠️ 新闻情绪模块不可用，跳过新闻检测（ Tavily API 或 news_sentiment 模块未安装）{Style.RESET_ALL}")

        print("The final is: ", results[:5])  # 打印前5条结果预览
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
            'recommendation': self.get_recommendation(scores['total']),
            'news': None,
        }

        # ——— 新闻情绪检测 ——
        if search_stock_news and calc_news_penalty:
            try:
                news = search_stock_news(result['code'], result['name'], days=7)
                penalty = calc_news_penalty(
                    news['sentiment'],
                    news['sentiment_score'],
                    result['limit_up_days']
                )
                result['news'] = news
                # 新闻情绪作为加减分项
                result['scores']['news_adjustment'] = penalty
                result['scores']['total'] = round(result['scores']['total'] + penalty, 1)
                result['rating'] = self.get_rating(result['scores']['total'])
                result['recommendation'] = self.get_recommendation(result['scores']['total'])
            except Exception as e:
                print(f"{Fore.YELLOW}⚠️ 新闻检测失败: {e}{Style.RESET_ALL}")

        return result
    
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
            ('市场情绪', scores['market_sentiment']),
        ]

        for dim_name, score in dimensions:
            filled = int(score / 100 * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            score_color = Fore.GREEN if score >= self.THRESHOLDS['buy'] else (Fore.YELLOW if score >= self.THRESHOLDS['watch'] else Fore.WHITE)
            print(f"  {dim_name}: {bar} {score_color}{score:.0f}{Style.RESET_ALL}")
        
        # 新闻调整
        news_adjustment = result['scores'].get('news_adjustment', 0)
        if news_adjustment != 0:
            adj_color = Fore.GREEN if news_adjustment > 0 else Fore.RED
            print(f"  {Fore.WHITE}新闻调整: {adj_color}{news_adjustment:+.1f}分{Style.RESET_ALL}")
        
        # 新闻详情
        news = result.get('news')
        if news:
            print(f"\n{Fore.WHITE}【新闻情绪】{Style.RESET_ALL}")
            if news.get('sentiment') == 'negative':
                color_n = Fore.RED
                warnings = news.get('risk_warnings', [])
                for w in warnings[:3]:
                    print(f"  {color_n}⚠️ {w}{Style.RESET_ALL}")
            elif news.get('sentiment') == 'positive':
                color_n = Fore.GREEN
                highlights = news.get('highlights', [])
                for h in highlights[:3]:
                    print(f"  {color_n}✅ {h}{Style.RESET_ALL}")
            else:
                print(f"  {Fore.WHITE}  {news.get('news_summary', '')}{Style.RESET_ALL}")

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
