import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
sys.path.insert(0, os.path.dirname(__file__))
import requests
import pandas as pd
import time
import os

import pandas as pd
from colorama import Fore, Style, init

# 导入数据源适配器
try:
    from data_source_adapter import DataSourceAdapter
except ImportError:
    # 尝试从 ma-bullish-strategy 导入共享的数据源适配器
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../ma-bullish-strategy/skills/scripts')
    print(adapter_path)
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        # 备选：从项目根目录相对导入
        sys.path.insert(0, os.path.join(os.getcwd(), 'ma-bullish-strategy/skills/scripts'))
        from data_source_adapter import DataSourceAdapter


# 初始化颜色输出
init(autoreset=True)


class StockDataFetcher:
    """股票数据获取器 - 支持多数据源"""
    
    def __init__(self, data_source: str = "auto", cache_ttl: int = 5):


     
        self.cache_ttl = cache_ttl
        self.cache_dir = os.path.expanduser("~/.openclaw/stock/data/cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 初始化数据源适配器
        self.data_adapter = DataSourceAdapter()
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源，请安装akshare、tushare、baostock或yfinance")



    def get_zt_pool_full(self) -> pd.DataFrame:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
            "Referer": "https://quote.eastmoney.com/ztb/",
            "Origin": "https://quote.eastmoney.com",
            "Host": "push2ex.eastmoney.com"
        }
        url = "https://push2ex.eastmoney.com/getTopicZTPool"
        today = time.strftime("%Y%m%d")
        timestamp = int(time.time() * 1000)

        all_pool = []

        # 🔥 关键升级：自动获取第 1 页 + 第 2 页，拿全所有涨停
        for page_index in [0, 1]:  
            params = {
                "ut": "7eea3edcaed734bea9cbfc24409ed989",
                "dpt": "wz.ztzt",
                "Pageindex": page_index,  # 分页核心
                "pagesize": 100,  # 东财限制最大100
                "sort": "fbt:asc",
                "date": today,
                "_": timestamp + page_index
            }

            try:
                resp = requests.get(url, params=params, headers=headers, timeout=3)
                resp.raise_for_status()
                result = resp.json()
                pool = result.get("data", {}).get("pool", [])
                all_pool.extend(pool)
                time.sleep(0.1)

            except Exception as e:
                print(f"⚠️ 第{page_index+1}页获取失败: {e}")

        if not all_pool:
            print("⚠️ pool 为空，接口无数据")
            return pd.DataFrame()

        df = pd.DataFrame(all_pool)

        # 字段映射（你现在的真实字段）
        map_dict = {
            "c": "代码",
            "n": "名称",
            "zdp": "涨跌幅",
            "p": "最新价",
            "amount": "成交额",
            "ltsz": "流通市值",
            "tshare": "总市值",
            "hs": "换手率",
            "fund": "封板资金",
            "fbt": "首次封板时间",
            "lbt": "最后封板时间",
            "zbc": "炸板次数",
            "zttj": "涨停统计",
            "lbc": "连板数",
            "hybk": "所属行业"
        }

        df = df.rename(columns=map_dict)
        
        # 🔥 去重（分页必加）
        df = df.drop_duplicates(subset=["代码"], keep="first")
        
        df["序号"] = range(1, len(df) + 1)

        cols = [
            "序号", "代码", "名称", "涨跌幅", "最新价", "成交额",
            "流通市值", "总市值", "换手率", "封板资金",
            "首次封板时间", "最后封板时间", "炸板次数",
            "涨停统计", "连板数", "所属行业"
        ]
        
        df = df[cols]
        return df




    def get_limit_up_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """获取涨停股票列表"""
        try:
            # 涨停数据目前只有akshare支持，尝试直接使用akshare
            print(f"{Fore.CYAN}📊 正在尝试连接获取涨停数据...{Style.RESET_ALL}")
            df = self.get_zt_pool_full()
            print(f"{Fore.GREEN}✅ 成功获取涨停数据，共{len(df)}只股票{Style.RESET_ALL}")
            return df
    
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
    
    # 评分权重配置（五维评分）
    WEIGHTS = {
        'sealing_strength': 0.30,    # 封板强度 (30%)
        'sector_effect': 0.25,       # 板块效应 (25%)
        'capital_flow': 0.20,        # 资金流向 (20%)
        'technical_pattern': 0.15,   # 技术形态 (15%)
        'market_sentiment': 0.10,    # 市场情绪 (10%)
    }
    
    # 评分阈值
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
        """
        基于涨停数据计算五维评分
        
        Args:
            row: 当前股票数据
            all_df: 当日所有涨停股票数据
            market_sentiment: 市场情绪值(0-100)，不传则自动计算
        
        Returns:
            包含各维度评分和总分的字典
        """
        scores = {}
        
        # 1. 封板强度 (30%)
        print("row, ", row)
        scores['sealing_strength'] = self._calc_sealing_strength(row)
        print(f"  封板强度评分: {scores['sealing_strength']}分")
        # 2. 板块效应 (25%)
        scores['sector_effect'] = self._calc_sector_effect(row, all_df)
        print(f"  板块效应评分: {scores['sector_effect']}分")
        # 3. 资金流向 (20%)
        scores['capital_flow'] = self._calc_capital_flow(row)
        print(f"  资金流向评分: {scores['capital_flow']}分")
        # 4. 技术形态 (15%)
        scores['technical_pattern'] = self._calc_technical_pattern(row)
        print(f"  技术形态评分: {scores['technical_pattern']}分")
        # 5. 市场情绪 (10%)
        if market_sentiment is not None:
            scores['market_sentiment'] = max(0, min(100, market_sentiment))
        else:
            scores['market_sentiment'] = self._calc_market_sentiment(all_df)
        print(f"  市场情绪评分: {scores['market_sentiment']}分")
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
    
    def _calc_sealing_strength(self, row: pd.Series) -> float:
        """
        封板强度评分（0-100）
        考虑因素：封板时间、炸板次数、封单比
        """
        score = 60  # 基础分
        
        # 1. 封板时间评分
        first_time = self._parse_time(row.get('首次封板时间', ''))
        print(f"首次封板时间: {first_time}")
        if first_time:
            minute_of_day = first_time[0] * 60 + first_time[1]
            if minute_of_day <= 9*60 + 35:      # 9:35前
                score += 25
            elif minute_of_day <= 9*60 + 45:    # 9:45前
                score += 20
            elif minute_of_day <= 10*60:        # 10:00前
                score += 15
            elif minute_of_day <= 11*60:        # 11:00前
                score += 10
            elif minute_of_day <= 13*60 + 30:   # 13:30前
                score += 5
            elif minute_of_day > 14*60:         # 14:00后封板
                score -= 10
        else:
            # 没有封板时间 = 未封板或尾盘烂板
            return 25
        print(f"封板强度评分: {score}")
        # 2. 炸板次数扣分
        open_count = self._safe_int(row.get('炸板次数', 0))
        print(f"炸板次数: {open_count}")
        if open_count == 0:
            score += 10
        elif open_count == 1:
            score -= 5
        elif open_count == 2:
            score -= 15
        elif open_count >= 3:
            score -= 30
        print(f"炸板次数扣分: {score}")
        # 3. 封单比评分（核心指标）
        seal_amount = self._safe_float(row.get('封板资金', 0))
        market_cap = self._safe_float(row.get('流通市值', 1))
        print(f"封板资金: {seal_amount}, 流通市值: {market_cap}")
        if market_cap > 0:
            seal_ratio = seal_amount / market_cap
            if seal_ratio >= 0.15:      # 封单比15%以上
                score += 15
            elif seal_ratio >= 0.08:    # 8%-15%
                score += 12
            elif seal_ratio >= 0.05:    # 5%-8%
                score += 8
            elif seal_ratio >= 0.03:    # 3%-5%
                score += 5
            elif seal_ratio >= 0.01:    # 1%-3%
                score += 2
            elif seal_ratio < 0.005:    # 低于0.5%，封单不足
                score -= 10
        else:
            # 无市值数据时降级使用绝对金额
            if seal_amount > 200000000:   # >2亿
                score += 10
            elif seal_amount > 100000000: # >1亿
                score += 7
            elif seal_amount > 50000000:  # >5000万
                score += 5
            elif seal_amount < 10000000:  # <1000万
                score -= 15
        print(f"封板强度评分: {score}")
        # 4. 回封加分（烂板回封说明承接强）
        if open_count > 0 and self._parse_time(row.get('最后封板时间', '')):
            score += 5
        
        return max(0, min(100, score))
    
    def _calc_sector_effect(self, row: pd.Series, all_df: pd.DataFrame) -> float:
        """
        板块效应评分（0-100）
        考虑：板块涨停数量、龙头地位
        """
        sector = row.get('所属行业', '')
        if not sector or pd.isna(sector):
            return 40  # 无行业归属
        
        # 获取当日同行业涨停股票
        sector_stocks = all_df[all_df['所属行业'] == sector]
        sector_count = len(sector_stocks)
        
        # 基础分（板块涨停数量）
        if sector_count >= 10:
            score = 85
        elif sector_count >= 5:
            score = 75
        elif sector_count >= 3:
            score = 65
        elif sector_count >= 2:
            score = 55
        elif sector_count == 1:
            score = 50
        else:
            score = 45
        
        # 龙头加分（最早封板）
        if sector_count > 0:
            # 安全排序，处理可能的无效时间
            sector_stocks_sorted = sector_stocks.copy()
            sector_stocks_sorted['_time_rank'] = sector_stocks_sorted['首次封板时间'].apply(
                lambda x: self._parse_time(x) if self._parse_time(x) else (999, 999)
            )
            sector_stocks_sorted = sector_stocks_sorted.sort_values('_time_rank')
            
            if len(sector_stocks_sorted) > 0:
                first_code = sector_stocks_sorted.iloc[0]['代码']
                if first_code == row['代码']:
                    score += 18  # 龙头加分
                elif len(sector_stocks_sorted) > 1 and sector_stocks_sorted.iloc[1]['代码'] == row['代码']:
                    score += 8   # 龙二加分
        
        # 连板高度加成（板块内最高连板）
        if '连板数' in sector_stocks.columns:
            max_continuous = sector_stocks['连板数'].max()
            if max_continuous >= 5 and sector_count >= 3:
                score += 5  # 板块有高度龙头
        
        return max(0, min(100, score))
    
    def _calc_capital_flow(self, row: pd.Series) -> float:
        """
        资金流向评分（0-100）
        考虑：封单比、连板数、换手率、量比
        """
        score = 50  # 基础分
        
        # 1. 封单比（核心指标）
        seal_amount = self._safe_float(row.get('封板资金', 0))
        market_cap = self._safe_float(row.get('流通市值', 1))
        
        if market_cap > 0:
            seal_ratio = seal_amount / market_cap
            if seal_ratio >= 0.15:
                score += 25
            elif seal_ratio >= 0.08:
                score += 18
            elif seal_ratio >= 0.05:
                score += 12
            elif seal_ratio >= 0.03:
                score += 8
            elif seal_ratio >= 0.01:
                score += 4
        else:
            # 无市值数据降级
            if seal_amount > 200000000:
                score += 15
            elif seal_amount > 100000000:
                score += 10
            elif seal_amount > 50000000:
                score += 6
        
        # 2. 连板数（资金持续认可度）
        limit_days = self._safe_int(row.get('连板数', 1))
        if limit_days == 2:
            score += 10
        elif limit_days == 3:
            score += 12
        elif limit_days == 4:
            score += 8
        elif limit_days >= 5:
            score += 3  # 高位追涨谨慎加分
        
        # 3. 换手率（适中最好）
        turnover = self._safe_float(row.get('换手率', 10))
        if 3 <= turnover <= 10:
            score += 10   # 理想换手
        elif 10 < turnover <= 18:
            score += 5    # 偏高但可接受
        elif 18 < turnover <= 25:
            score -= 5    # 换手过大
        elif turnover > 25:
            score -= 12   # 超高换手，出货嫌疑
        elif turnover < 2:
            score -= 3    # 换手不足
        
        # 4. 量比（成交量相对变化）
        volume_ratio = self._safe_float(row.get('量比', 1))
        if 1.2 <= volume_ratio <= 2.5:
            score += 5    # 温和放量
        elif volume_ratio > 3:
            score -= 8    # 爆量
        elif volume_ratio < 0.7:
            score -= 3    # 缩量
        
        return max(0, min(100, score))
    
    def _calc_technical_pattern(self, row: pd.Series) -> float:
        """
        技术形态评分（0-100）
        考虑：连板数、涨停形态、位置、量价关系
        """
        limit_days = self._safe_int(row.get('连板数', 1))
        
        # 基础分按连板数（连板越高风险越大）
        if limit_days == 1:
            base_score = 80
        elif limit_days == 2:
            base_score = 75
        elif limit_days == 3:
            base_score = 65
        elif limit_days == 4:
            base_score = 55
        elif limit_days == 5:
            base_score = 45
        else:
            base_score = 35  # 6板以上极高风险
        
        # 1. 涨停封板强度
        open_count = self._safe_int(row.get('炸板次数', 0))
        if open_count == 0:
            base_score += 5   # 未炸板加分
        elif open_count >= 2:
            base_score -= 10  # 多次炸板扣分
        
        # 2. 是否有缺口（一字板或跳空）
        open_price = self._safe_float(row.get('开盘价', 0))
        prev_close = self._safe_float(row.get('昨日收盘价', open_price))
        if prev_close > 0 and open_price > prev_close * 1.05:
            base_score += 8   # 跳空高开5%以上，强势
        
        # 3. 量价配合（缩量板加分，放量板扣分）
        amount = self._safe_float(row.get('成交额', 0))
        prev_amount = self._safe_float(row.get('昨日成交额', amount))
        if prev_amount > 0:
            amount_ratio = amount / prev_amount
            if amount_ratio < 0.7:
                base_score += 10   # 缩量板，惜售
            elif amount_ratio > 2:
                base_score -= 8    # 爆量板，分歧大
        
        return max(0, min(100, base_score))
    
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
    
    def _get_index_code(self, index_name: str) -> str:
        """
        获取指数代码（根据数据源自动调整格式）
        """
        codes = {
            'sh': '000001', 'sz': '399001', 'cy': '399006', 'kc': '000688'
        }
        if self.fetcher.data_adapter.source == 'baostock':
            codes = {
                'sh': 'sh.000001', 'sz': 'sz.399001', 'cy': 'sz.399006', 'kc': 'sh.000688'
            }
        return codes.get(index_name, '000001')
    
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
            df_sh = self.fetcher.data_adapter.get_stock_data(self._get_index_code('sh'))
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
            df_sz = self.fetcher.data_adapter.get_stock_data(self._get_index_code('sz'))
            if df_sz is not None and len(df_sz) >= 2:
                latest = df_sz.iloc[-1]
                prev = df_sz.iloc[-2]
                market_data['sz_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 获取深证成指数据失败: {e}{Style.RESET_ALL}")
        
        try:
            # 尝试获取创业板指数据
            df_cy = self.fetcher.data_adapter.get_stock_data(self._get_index_code('cy'))
            if df_cy is not None and len(df_cy) >= 2:
                latest = df_cy.iloc[-1]
                prev = df_cy.iloc[-2]
                market_data['cy_change'] = (latest['close'] - prev['close']) / prev['close'] * 100
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 获取创业板指数据失败: {e}{Style.RESET_ALL}")
        
        try:
            # 尝试获取科创板指数据（科创50）
            df_kc = self.fetcher.data_adapter.get_stock_data(self._get_index_code('kc'))
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
        """分析当日所有涨停股票"""
        print(f"{Fore.CYAN}📊 正在获取当日涨停股票数据...{Style.RESET_ALL}")
       # print(f"{Fore.CYAN}   使用数据源: {self.fetcher.data_adapter.source}{Style.RESET_ALL}")

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
            }
            results.append(result)

        # 按总分排序
        results.sort(key=lambda x: x['scores']['total'], reverse=True)
        
        return results[:5]
    
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
        }

        return result
    
    def print_analysis(self, result: Dict):
        """打印分析结果"""
        code = result.get('code') or result.get('stock_code', '')
        name = result.get('name') or result.get('stock_name', '')
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
        print(f"{Fore.CYAN}📈 股票: {code} {name} ({result.get('sector', 'N/A')}){Style.RESET_ALL}")
        print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}\n")
        
        print(f"{Fore.WHITE}【综合评分】 {color}{total}/100 ({rating['label']}){Style.RESET_ALL}")
        print(f"{Fore.WHITE}【连板数】 {result.get('limit_up_days', 1)}板{Style.RESET_ALL}\n")
        
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
        
        code = result.get('code') or result.get('stock_code', '')
        existing = [r for r in existing if r.get('code') != code and r.get('stock_code') != code]
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
    
    # ==================== 工具函数 ====================
    
    def _parse_time(self, time_str):
        """
        解析东财格式的时间：92500 → (9, 25)
        """
        try:
            time_str = str(time_str).zfill(6)  # 补齐6位
            hh = int(time_str[0:2])
            mm = int(time_str[2:4])
            ss = int(time_str[4:6])
            return (hh, mm, ss)
        except:
            return None
    
    def _safe_int(self, value, default=0) -> int:
        """安全转换为整数"""
        try:
            if pd.isna(value):
                return default
            if isinstance(value, str):
                value = re.sub(r'[^-\d.]', '', value)
            return int(float(value))
        except (ValueError, TypeError, AttributeError):
            return default
    
    def _safe_float(self, value, default=0.0) -> float:
        """安全转换为浮点数（修复完整版）"""
        try:
            if pd.isna(value) or value is None or value == "":
                return default
            return float(value)
        except (ValueError, TypeError, AttributeError):
            return default
