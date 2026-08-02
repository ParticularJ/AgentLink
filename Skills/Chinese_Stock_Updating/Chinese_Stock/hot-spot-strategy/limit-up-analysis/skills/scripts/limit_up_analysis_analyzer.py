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
import os,yaml 

import pandas as pd
from colorama import Fore, Style, init



# 导入数据源适配器
try:
    from data_source_adapter import DataSourceAdapter
except ImportError:
    # 尝试从 ma-bullish-strategy 导入共享的数据源适配器
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../data-strategy/skills/scripts')
    print(adapter_path)
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        # 备选：从项目根目录相对导入
        sys.path.insert(0, os.path.join(os.getcwd(), 'data-strategy/skills/scripts'))
        from data_source_adapter import DataSourceAdapter

# 导入市场分析器
try:
    from position_monitor import MarketContext
except ImportError:
    # 尝试从 ma-bullish-strategy 导入共享的数据源适配器
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../Medium-termHoldingStrategy/skills/scripts')
    print(adapter_path)
    sys.path.insert(0, adapter_path)
    try:
        from position_monitor import MarketContext
    except ImportError:
        # 备选：从项目根目录相对导入
        sys.path.insert(0, os.path.join(os.getcwd(), 'Medium-termHoldingStrategy/skills/scripts'))
        from position_monitor import MarketContext


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
        today = (datetime.now() - timedelta(days=0)).strftime("%Y%m%d")
        print(today)
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

            if df.empty:
                return df

            # ========== 批量计算所有涨停股的量比 ==========
            volume_ratio_list = []
            amount_ratio_list = []  # 新增
            for _, row in df.iterrows():
                code = row['代码']
                # print('code: ', code)
                try:
                    # 取近6日数据（含当日，计算前5日均量）
                    hist = self.data_adapter.get_stock_data(code)
                    # print("hist", hist)
                    if hist is not None and len(hist) >= 5:
                        # 前5日均量
                        avg_vol = hist['volume'].iloc[-6:-1].mean()
                        today_vol = hist['volume'].iloc[-1]
                        volume_ratio = round(today_vol / avg_vol, 2) if avg_vol > 0 else 1.0

                        # 新增：成交额环比
                        today_amount = hist['amount'].iloc[-1]
                        prev_amount = hist['amount'].iloc[-2]
                        amount_ratio = round(today_amount / prev_amount, 2) if prev_amount > 0 else 1.0
                    else:
                        volume_ratio = 1.0
                        amount_ratio = 1.0
                except:
                    volume_ratio = 1.0
                    amount_ratio = 1.0
                volume_ratio_list.append(volume_ratio)
                amount_ratio_list.append(amount_ratio)
            
            df['量比'] = volume_ratio_list
            df['额比'] = amount_ratio_list
            print(df)
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
    
    def calc_scores(self, row: pd.Series, all_df: pd.DataFrame, market_score: float = None, reasons: list=[]) -> Dict:
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
        # 一字板一票否决（无法打板参与）
        turnover = self._safe_float(row.get('换手率', 0))
        zdp = self._safe_float(row.get('涨跌幅', 0))
        if turnover < 1 and zdp >= 9.8:
            scores = {k: 0 for k in scores}
            scores['total'] = 0
            return scores
        # 1. 封板强度 (30%)
        # print("row, ", row)
        scores['sealing_strength'] = self._calc_sealing_strength(row, reasons)
        print(f"  封板强度评分: {scores['sealing_strength']}分")
        # 2. 板块效应 (25%)
        scores['sector_effect'] = self._calc_sector_effect(row, all_df, reasons)
        print(f"  板块效应评分: {scores['sector_effect']}分")
        # 3. 资金流向 (20%)
        scores['capital_flow'] = self._calc_capital_flow(row, reasons)
        print(f"  资金流向评分: {scores['capital_flow']}分")
        # 4. 技术形态 (15%)
        scores['technical_pattern'] = self._calc_technical_pattern(row, reasons)
        print(f"  技术形态评分: {scores['technical_pattern']}分")
        # 5. 市场情绪 (10%)
        if market_score is not None:
            scores['market_sentiment'] = max(0, min(100, market_score))
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


    def _calc_sealing_strength(self, row: pd.Series, reason: list) -> float:
        """
        封板强度评分（0-100）
        优化点：下调基础分、细化时间梯度、柔化炸板扣分、市值分层封单、回封加分挂钩炸板次数
        """
        score = 45  # 基础分从60下调至45，拉开区分度
        limit_days = self._safe_int(row.get('连板数', 1))
        market_cap = self._safe_float(row.get('流通市值', 1))

        # 1. 封板时间评分（细化档位，区分竞价/早盘/午盘/下午/尾盘）
        first_time = self._parse_time(row.get('首次封板时间', ''))
        if first_time:
            minute_of_day = first_time[0] * 60 + first_time[1]
            if minute_of_day <= 9*60 + 25:
                score += 28
                reason.append(f"9:25集合竞价封板，极强盘口 ")
            elif minute_of_day <= 9*60 + 35:
                score += 25
                reason.append(f"9:35前早盘秒板，强势盘口 ")
            elif minute_of_day <= 10*60:
                score += 20
                reason.append(f"10:00前早盘封板，盘口尚可 ")
            elif minute_of_day <= 11*60 + 30:
                score += 12
                reason.append(f"11:30午盘前封板，中等盘口")
            elif minute_of_day <= 13*60 + 30:
                score += 7
                reason.append(f"13:30下午开盘封板，偏弱 ")
            elif minute_of_day <= 14*60:
                score += 3
                reason.append(f"14:00前下午封板，弱势小幅加分 ")
            else:
                score -= 10
                reason.append(f"14:00后尾盘封板，资金认可度弱 ")
        else:
            return 20  # 无封板时间，判定为未有效封板，低分

        # 2. 炸板次数扣分（柔化首板扣分，连板维持重扣）
        open_count = self._safe_int(row.get('炸板次数', 0))
        if open_count == 0:
            score += 10
            reason.append("全程零炸板，封板稳定性高")
        elif open_count == 1:
            # 首板1次炸板良性换手少扣，连板正常扣
            if limit_days == 1:
                score -= 3
                reason.append("首板仅炸板1次，良性换手小幅扣减 ")
            else:
                score -= 8
                reason.append("连板炸板1次，筹码松动扣减")
        elif open_count == 2:
            if limit_days == 1:
                score -= 10
                reason.append("首板炸板2次，分歧加大 ")
            else:
                score -= 18
                reason.append("连板炸板2次，抛压较重 ")
        elif open_count >= 3:
            score -= 30
            reason.append("炸板{open_count}次及以上，封板极差")
       
        # 3. 封单比评分（按市值分层，大盘股降低阈值）
        seal_amount = self._safe_float(row.get('封板资金', 0))
        if market_cap > 0:
            seal_ratio = seal_amount / market_cap
            reason.append(f"封单资金{seal_amount:.0f}，流通市值{market_cap:.0f}，封单比{round(seal_ratio, 4)}")
            # 市值分层：100亿以上大盘股、30-100亿中盘、30亿以下小盘
            if market_cap >= 100 * 1e8:
                # 大盘股：比例要求降低
                if seal_ratio >= 0.08:
                    score += 15
                    reason.append(f"大盘股封单比{seal_ratio:.4f}≥0.08，封单极充足")
                elif seal_ratio >= 0.04:
                    score += 12
                    reason.append(f"大盘股封单比0.04≤{seal_ratio:.4f}<0.08，封单充足")
                elif seal_ratio >= 0.02:
                    score += 8
                    reason.append(f"大盘股封单比0.02≤{seal_ratio:.4f}<0.04，封单尚可")
                elif seal_ratio >= 0.01:
                    score += 4
                    reason.append(f"大盘股封单比0.01≤{seal_ratio:.4f}<0.02，封单一般")
                elif seal_ratio < 0.003:
                    score -= 10
                    reason.append(f"大盘股封单比{seal_ratio:.4f}<0.003，封单薄弱抛压易炸开")
            else:
                # 中小盘股：原标准微调
                if seal_ratio >= 0.15:
                    score += 15
                    reason.append(f"中小盘个股封单比{seal_ratio:.4f}≥0.15，巨量封单资金认可度极高")
                elif seal_ratio >= 0.08:
                    score += 12
                    reason.append(f"中小盘个股封单比0.08≤{seal_ratio:.4f}<0.15，封单充足稳定性强")
                elif seal_ratio >= 0.05:
                    score += 8
                    reason.append(f"中小盘个股封单比0.05≤{seal_ratio:.4f}<0.08，封单力度尚可")
                elif seal_ratio >= 0.02:
                    score += 4
                    reason.append(f"中小盘个股封单比0.02≤{seal_ratio:.4f}<0.05，封单力度一般小幅加分")
                elif seal_ratio < 0.005:
                    score -= 10
                    reason.append(f"中小盘个股封单比{seal_ratio:.4f}<0.005，封单薄弱极易炸板")
        else:
            # 无市值数据降级用绝对金额
            if seal_amount > 200000000:
                score += 10
            elif seal_amount > 100000000:
                score += 7
            elif seal_amount > 50000000:
                score += 5
            elif seal_amount < 10000000:
                score -= 15

        # 4. 回封加分（和炸板次数挂钩，炸越少加分越多）
        last_t = self._parse_time(row.get('最后封板时间', ''))
        print('last_t: ', last_t, ', open_count: ', open_count, 'limit_days: ', limit_days, 'market_cap: ', market_cap, 'seal_amount', seal_amount)
        strTime = "最后封板时间" + str(last_t)
        reason.append( strTime) 
        if open_count > 0 and last_t:
            lh, lm, _ = last_t
            last_min = lh * 60 + lm
            # 上午回封加分多，下午回封加分少
            time_bonus = 6 if last_min <= 11*60+30 else 3
            # 炸板次数越少，回封含金量越高
            open_penalty_factor = max(0.3, 1 - (open_count - 1) * 0.3)
            score += int(time_bonus * open_penalty_factor)

        return max(0, min(100, score))
    

    def _calc_sector_effect(self, row: pd.Series, all_df: pd.DataFrame, reason: list) -> float:
        """
        板块效应评分（0-100）
        优化点：下调基础分、细分档位、控制龙头加分权重、新增涨停占比修正、放宽高度加分
        """
        sector = row.get('所属行业', '')
        if not sector or pd.isna(sector):
            return 30  # 无行业归属，板块效应直接给低分
        
        # 获取当日同行业涨停股票
        sector_stocks = all_df[all_df['所属行业'] == sector]
        sector_count = len(sector_stocks)



        # ========== 1. 合并后基础分：直接一步到位，内置主线梯度倾斜 ==========
        if sector_count >= 15:
            score = 95
        elif sector_count >= 10:
            score = 86
        elif sector_count >= 7:
            score = 77
        elif sector_count >= 5:
            score = 67
        elif sector_count >= 3:
            score = 55
        elif sector_count == 2:
            score = 39
        elif sector_count == 1:
            score = 25
        else:
            score = 20
            
        # ========== 2. 龙头加分：控制权重，同板块内排序 ==========
        if sector_count >= 2:
            sector_stocks_sorted = sector_stocks.copy()
            sector_stocks_sorted['_time_rank'] = sector_stocks_sorted['首次封板时间'].apply(
                lambda x: self._parse_time(x) if self._parse_time(x) else (999, 999)
            )
            sector_stocks_sorted = sector_stocks_sorted.sort_values('_time_rank')
            
            first_code = sector_stocks_sorted.iloc[0]['代码']
            if first_code == row['代码']:
                score += 10  # 龙头加分从18下调至10，避免主次颠倒
                reason.append(f"本股为板块第一封板龙头")
            elif len(sector_stocks_sorted) > 1 and sector_stocks_sorted.iloc[1]['代码'] == row['代码']:
                score += 4   # 龙二加分
                reason.append(f"本股为板块龙二")
        
        # ========== 3. 板块连板高度：放宽门槛，分档加分 ==========
        if '连板数' in sector_stocks.columns:
            max_continuous = sector_stocks['连板数'].max()
            if max_continuous >= 4 and sector_count >= 3:
                score += 6
                reason.append(f"板块最高连板{max_continuous}板≥4板，板块热度高")
            elif max_continuous >= 3 and sector_count >= 3:
                score += 4
                reason.append(f"板块最高连板{max_continuous}板≥3板，板块热度尚可")
            elif max_continuous >= 2 and sector_count >= 2:
                score += 2
                reason.append(f"板块最高连板{max_continuous}板≥2板，小幅加分")
            # 板块规模分类字典，按需补充即可
        SECTOR_SCALE = {
            "small": {"工程机械", "林业", "贵金属", "航运港口", "地面兵装", "煤炭开采"},  # <20只
            "medium": {"广告营销", "塑料", "纺织制造", "农化制品", "水泥", "家居用品"},      # 20-50只
            "large": {"化学制药", "汽车零部件", "电子", "通用设备", "专用设备", "电力设备"}   # >80只
        }

        # 在板块效应打分函数内追加修正逻辑
        if sector in SECTOR_SCALE["small"] and sector_count >= 2:
            score += 5  # 小板块2只涨停的资金集中度，相当于大板块5只
            reason.append(f"属于小众行业，已有{sector_count}只涨停，资金集中")
        elif sector in SECTOR_SCALE["large"] and sector_count < 5:
            score -= 3  # 大行业少于5只属于零散炒作，适度扣分
            reason.append(f"属于大盘大类行业，仅{sector_count}只涨停，炒作零散")
        
        return max(0, min(100, score))


    def _calc_capital_flow(self, row: pd.Series, reason: list) -> float:
        """
        资金流向评分（0-100）
        优化：去重封单比、替换量比、分首板/连板、市值分层、修正缩量逻辑
        核心维度：成交强度(核心)、连板持续性、换手健康度、量能相对变化
        """
        score = 40  # 基础分下调，拉开区分度
        
        seal_amount = self._safe_float(row.get('封板资金', 0))
        market_cap = self._safe_float(row.get('流通市值', 1))
        turnover = self._safe_float(row.get('换手率', 10))
        limit_days = self._safe_int(row.get('连板数', 1))
        amount = self._safe_float(row.get('成交额', 0))
        is_first_board = (limit_days == 1)
        # ========== 1. 成交强度（额比，分市值分板型修正） ==========
        amount_ratio = self._safe_float(row.get('额比', 1.0))
        is_early_board = False
        # 判断是否为10点前封板的早盘硬板
        first_time = self._parse_time(row.get('首次封板时间', ''))
        if first_time:
            minute_of_day = first_time[0] * 60 + first_time[1]
            is_early_board = (minute_of_day <= 10 * 60)

        is_large_cap = (market_cap >= 100 * 1e8)

         # 基础属性记录
        cap_text = "百亿以上大盘股" if is_large_cap else "中小盘个股"
        board_text = "首板" if is_first_board else f"{limit_days}连板"
        early_text = "10点前早盘硬板" if is_early_board else "午盘/尾盘封板"
        reason.append(f"标的属性：{cap_text}，{board_text}，{early_text}")




        print("is_large_cap", is_large_cap, is_early_board, is_first_board, amount_ratio)
        if is_first_board:
            # 首板分场景
            if is_large_cap and is_early_board:
                # 大盘股+早盘硬板：缩量=惜售强势，放量=分歧
                if amount_ratio < 0.7:
                    score += 18    # 极致缩量锁仓，极强
                    reason.append(f"额比{amount_ratio}<0.7，大盘早盘硬板极致缩量锁仓")
                elif 0.7 <= amount_ratio <= 1.2:
                    score += 12    # 平量，稳定
                    reason.append(f"额比0.7~1.2，大盘早盘硬板平量稳定")
                elif amount_ratio > 2:
                    score -= 8     # 爆量分歧
                    reason.append(f"额比{amount_ratio}>2，大盘早盘硬板爆量分歧")
            else:
                # 中小盘/晚封板首板：温和放量好，缩量承接差
                if 1.2 <= amount_ratio <= 2.5:
                    score += 20    # 健康放量突破
                    reason.append(f"额比1.2~2.5，中小盘首板健康放量突破 ")
                elif 2.5 < amount_ratio <= 4:
                    score += 10
                    reason.append(f"额比2.5~4，中小盘首板放量尚可 ")
                elif amount_ratio > 4:
                    score -= 8
                    reason.append(f"额比{amount_ratio}>4，中小盘首板严重爆量分歧")
                elif amount_ratio < 0.7:
                    score -= 6
                    reason.append(f"额比{amount_ratio}<0.7，中小盘首板缩量承接不足 -6分")
        else:
            # 连板：统一缩量加分，放量扣分
            if amount_ratio < 0.7:
                score += 20
                reason.append(f"连板额比{amount_ratio}<0.7，极致缩量锁仓 +20分")
            elif 0.7 <= amount_ratio <= 1.2:
                score += 12
                reason.append(f"连板额比0.7~1.2，平量承接稳定 +12分")
            elif amount_ratio > 2:
                score -= 8
                reason.append(f"连板额比{amount_ratio}>2，放量出货分歧 -8分")
        print("score: ", score)
        # ========== 2. 连板资金持续性（适配首板策略，首板给基础分） ==========
        if limit_days == 1:
            score += 5   # 首板基础资金分，避免首板天然劣势
        elif limit_days == 2:
            score += 10
        elif limit_days == 3:
            score += 12
        elif limit_days == 4:
            score += 9
        elif limit_days >= 5:
            score += 4   # 高位谨慎
        print("score: ", score)
        # ========== 3. 换手率健康度（分首板/连板，分市值） ==========
     
        if market_cap >= 100 * 1e8:
            # 大盘股：换手阈值整体下调
            if is_first_board:
                if 2 <= turnover <= 8:
                    score += 10
                    reason.append(f"大盘首板换手2~8%，换手健康 ")
                elif 8 < turnover <= 15:
                    score += 4
                    reason.append(f"大盘首板换手8~15%，换手尚可")
                elif turnover > 15:
                    score -= 10
                    reason.append(f"大盘首板换手>15%，换手过高分歧大")
                elif turnover < 1:
                    score -= 5
                    reason.append(f"大盘首板换手<1%，流动性不足")
            else:
                # 连板：低换手加分，高换手扣分
                if turnover <= 5:
                    score += 10  # 缩量锁仓
                    reason.append(f"大盘连板换手≤5%，缩量锁仓")
                elif 5 < turnover <= 10:
                    score += 4
                    reason.append(f"大盘连板换手5~10%，换手平稳")
                elif turnover > 15:
                    score -= 12
                    reason.append(f"大盘连板换手>15%，筹码松动 -12分")
        else:
            # 中小盘股
            if is_first_board:
                if 5 <= turnover <= 18:
                    score += 10

                    reason.append(f"中小盘首板换手5~18%，换手健康")
                elif 18 < turnover <= 25:
                    score += 4
                    reason.append(f"中小盘首板换手18~25%，换手尚可")
                elif turnover > 30:
                    score -= 10
                    reason.append(f"中小盘首板换手>30%，巨量分歧")
                elif turnover < 2:
                    score -= 5
                    reason.append(f"中小盘首板换手<2%，流动性差")
            else:
                # 连板：缩量加速加分
                if turnover <= 8:
                    score += 10
                    reason.append(f"中小盘连板换手≤8%，缩量加速")
                elif 8 < turnover <= 15:
                    score += 4
                    reason.append(f"中小盘连板换手8~15%，换手平稳")
                elif turnover > 25:
                    score -= 12
                    reason.append(f"中小盘连板换手>25%，筹码大量交换风险")
        print("score: ", score)
        # ========== 4. 量能相对变化（真实量比） ==========
        volume_ratio = self._safe_float(row.get('量比', 1.0))

        if is_first_board:
            # 首板：温和放量最优，爆量分歧扣分，极度缩量也扣分
            if 1.2 <= volume_ratio <= 2.5:
                score += 6    # 温和放量，健康突破
                reason.append(f"首板量比1.2~2.5，温和放量突破")
            elif 2.5 < volume_ratio <= 4:
                score += 2    # 偏大量，尚可接受
                reason.append(f"首板量比2.5~4，放量尚可")
            elif volume_ratio > 4:
                score -= 8    # 爆量，分歧过大
                reason.append(f"首板量比>4，短期爆量分歧大")
            elif volume_ratio < 0.7:
                score -= 4    # 缩量严重，承接不足
                reason.append(f"首板量比<0.7，短期缩量承接弱")
        else:
            # 连板：缩量加速最优，放量分歧扣分
            if volume_ratio < 0.7:
                score += 8    # 缩量锁仓，一致性极强
                reason.append(f"连板量比<0.7，持续缩量一致性强")
            elif 0.7 <= volume_ratio <= 1.2:
                score += 4    # 平量，承接稳定
                reason.append(f"连板量比0.7~1.2，量能平稳承接稳定")
            elif 1.2 < volume_ratio <= 2:
                score -= 2    # 温和放量，分歧略增
                reason.append(f"连板量比1.2~2，小幅放量分歧小幅扣减")
            elif volume_ratio > 2:
                score -= 8    # 大幅放量，出货嫌疑
                reason.append(f"连板量比>2，持续放量出货风险")
        print("score: ", score)
        return max(0, min(100, score))
    
    def _calc_technical_pattern(self, row: pd.Series, reason: list) -> float:
        """
        技术形态评分（进阶版）
        新增：相对位置、均线多头、突破新高，完整体现形态质量
        """
        limit_days = self._safe_int(row.get('连板数', 1))
        is_first = (limit_days == 1)
        code = row['代码']
        
        # 基础分
        if limit_days == 1:
            base_score = 60
        elif limit_days == 2:
            base_score = 58
        elif limit_days == 3:
            base_score = 50
        elif limit_days == 4:
            base_score = 42
        else:
            base_score = 32

        reason.append(f"连扳次数{limit_days}")
        # ========== 拉取20日日线，计算形态指标 ==========
        try:
            hist = self.fetcher.get_stock_data(code)
            if hist is not None and len(hist) >= 10:
                close_list = hist['close'].values
                current = close_list[-1]
                ma5 = close_list[-5:-1].mean()
                ma20 = close_list[-20: -1].mean() if len(close_list) >= 20 else close_list.mean()
                high_20 = close_list[-20: -1].max() if len(close_list) >= 20 else close_list.max()

                # 1. 均线结构（多头排列加分）
                if current > ma5 > ma20:
                    base_score += 10  # 完美多头趋势
                elif current > ma20:
                    base_score += 5   # 站在20日线上，趋势向上
                elif current < ma20:
                    base_score -= 8   # 跌破20日线，弱势反弹

                # 2. 突破新高加分
                if current >= high_20 * 0.99:
                    if is_first:
                        base_score += 12  # 首板突破20日新高，确定性最强
                    else:
                        base_score += 7

                # 3. 相对位置（低位加分，高位扣分）
                range_20 = high_20 - close_list[-20:-1].min() if len(close_list) >= 20 else high_20 - close_list.min()
                if range_20 > 0:
                    position = (current - close_list[-20:-1].min()) / range_20
                    if position < 0.3 and is_first:
                        base_score += 6   # 低位首板启动，性价比高
                    elif position > 0.9 and limit_days >= 3:
                        base_score -= 7  # 高位连板，风险大


                # 4. 20日累计涨幅：高位风险扣分（覆盖断板反包）
                if len(close_list) >= 20:
                    price_20 = close_list[-21]
                    if price_20 > 0:
                        gain_20 = (current - price_20) / price_20
                        if gain_20 >= 0.6:
                            base_score -= 15   # 60%+ 极高位，重扣
                            reason.append("20日涨幅超60% 极高位置")
                        elif gain_20 >= 0.4:
                            base_score -= 8    # 40%+ 高位，中度扣分
                            reason.append("20日涨幅超40% 高位风险")
                        elif gain_20 <= 0.1 and is_first:
                            base_score += 5    # 低位启动首板，性价比高，小幅加分
        except:
            pass

        # ========== 盘口形态补充 ==========
        # 跳空缺口
        open_price = self._safe_float(row.get('最新价', 0))
        prev_close = open_price / (1 + self._safe_float(row.get('涨跌幅', 10))/100)
        if prev_close > 0:
            gap_pct = (open_price - prev_close) / prev_close
            if is_first and gap_pct >= 0.04:
                base_score += 5
                reason.append("当日高开4%以上跳空首板")
            elif not is_first and limit_days >= 3 and gap_pct >= 0.07:
                base_score -= 4
                reason.append("高位连板大幅跳空 风险 ")

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
    
    
    def _calc_market_sentiment(self, all_df: pd.DataFrame) -> float:
        """
        计算全局市场情绪得分（所有股票共享）
        基于大盘指数涨跌幅、成交量、涨停数量综合判断
        """
        score = 50  # 基础分
        
        # 1. 获取大盘指数数据
        market_data_sent = MarketContext.get_market_sentiment()
        # 2. 大盘指数涨跌幅评分 (40%)
        # 计算四大指数平均涨跌幅（上证、深证、创业板、科创板）

        if market_data_sent == "极端恐慌":
            score -= 20
        elif market_data_sent == "恐慌":
            score -= 10
        elif market_data_sent == "偏弱":
            score -= 5
        elif market_data_sent == "正常震荡":
             score += 5
        elif market_data_sent == "温和强势":
             score += 10
        elif market_data_sent == "强势大涨":
             score += 15
        elif market_data_sent == "极端暴涨":
             score += 20
        
        
        #3. 涨停数量评分 (25%)
        total_zt = len(all_df)
        if total_zt >= 150:
            score += 10  # 情绪极度高涨
        elif total_zt >= 100:
            score += 8
        elif total_zt >= 70:
            score += 6 
        elif total_zt >= 50:
            score += 4
        elif total_zt >= 30:
            score += 2
        elif total_zt < 20:
            score -= 8  # 涨停太少，情绪低迷
        

        max_limit = 1
        avg_limit = 1.0
        # 4. 连板高度评分 (15%)
        if '连板数' in all_df.columns and not all_df.empty:
            # print("all_df: ", all_df)
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
        print(f"{Fore.CYAN}📊 市场情绪分析:{market_data_sent}")
        print(f"   max_limit: {max_limit}")
        print(f"   avg_limit: {avg_limit}")
        print(f"   涨停数量: {total_zt}只")
        
        return min(100, max(0, round(score, 1)))

    def get_top_sectors(self, all_df: pd.DataFrame, top_n: int = 3) -> List[Dict]:
        """
        统计当日涨停数量排名前N的行业
        返回：行业名称、涨停数、涨停占比、最高连板、强度标签
        """
        if all_df.empty:
            return []
        
        # 过滤掉空行业的异常数据
        valid_df = all_df[all_df['所属行业'].notna() & (all_df['所属行业'] != '')]
        if valid_df.empty:
            return []
        
        total_zt = len(valid_df)
        
        # 按行业分组统计：涨停数量、板块最高连板
        sector_stats = valid_df.groupby('所属行业').agg(
            涨停数=('代码', 'count'),
            最高连板=('连板数', 'max')
        ).reset_index()
        
        # 排序规则：优先按涨停数降序，涨停数相同按最高连板降序
        sector_stats = sector_stats.sort_values(['涨停数', '最高连板'], ascending=False)
        top_list = sector_stats.head(top_n).to_dict('records')
        
        # 补充涨停占全市场比例
        for item in top_list:
            item['涨停占比'] = round(item['涨停数'] / total_zt * 100, 1)
            # 附加强度标签，和你现有板块效应档位对齐
            count = item['涨停数']
            if count >= 15:
                item['强度'] = '顶级主线'
            elif count >= 7:
                item['强度'] = '强主线'
            elif count >= 5:
                item['强度'] = '普通主线'
            else:
                item['强度'] = '支线'
        
        return top_list


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

        # 放在 market_sentiment 计算之后，循环打分之前
        top_sectors = self.get_top_sectors(limit_up_df)
        print(f"{Fore.CYAN}📊 当日涨停Top{len(top_sectors)}行业:{Style.RESET_ALL}")
        for idx, sector in enumerate(top_sectors, 1):
            # 不同强度对应不同颜色
            if sector['强度'] == '顶级主线':
                color = Fore.RED
            elif sector['强度'] == '强主线':
                color = Fore.YELLOW
            elif sector['强度'] == '普通主线':
                color = Fore.GREEN
            else:
                color = Fore.WHITE
            print(f"  {idx}. {sector['所属行业']} - {sector['涨停数']}只涨停 - 占比{sector['涨停占比']}% - 最高连板{sector['最高连板']}天 - {color}{sector['强度']}{Style.RESET_ALL}")
        print()
       
        results = []
        
        for _, row in limit_up_df.iterrows():
            
            reasons = []
            scores = self.calc_scores(row, limit_up_df, market_sentiment, reasons)
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
                'TopSector': top_sectors,
                'reasons': reasons
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
        reasons =[]
        market_score = None
        scores = self.calc_scores(row, limit_up_df, market_score, reasons)

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
            'reasons': reasons
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

if __name__ == "__main__":
    limit_up_df = StockDataFetcher()
    ##result =LimitUpAnalyzer().analyze_all_limit_up()
    result =LimitUpAnalyzer().analyze_stock('300912')
    print(result)