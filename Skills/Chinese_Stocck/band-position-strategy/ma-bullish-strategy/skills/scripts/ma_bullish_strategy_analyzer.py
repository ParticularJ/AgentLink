#!/usr/bin/env python3
"""
均线多头排列策略分析器
支持多数据源：akshare、tushare、baostock、yfinance
"""

import os
import sys
import time
# 清除代理环境变量
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    if key in os.environ:
        del os.environ[key]

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import warnings
import yaml
warnings.filterwarnings('ignore')

# 导入数据源适配器
from .data_source_adapter import DataSourceAdapter

class MarketEnvironment:
    """市场环境评估（大盘/科创板/创业板等涨跌、涨停家数、成交量）"""
    
    def __init__(self):
        self.index_data = {}
        self.zt_count = 0
        self.zt_pool_date = ''
        self._load()
    
    def _load(self):
        """加载市场环境数据"""
        try:
            import akshare as ak
            today = datetime.now().strftime('%Y%m%d')
            self.zt_pool_date = today
            
            # 获取今日涨停股数量
            try:
                zt_df = ak.stock_zt_pool_em(date=today)
                self.zt_count = len(zt_df) if zt_df is not None and not zt_df.empty else 0
            except:
                self.zt_count = 0
            
            # 获取主要指数数据
            index_codes = [
                ('sh000300', '沪深300'),   # 000300
                ('sh000001', '上证指数'),  # 000001  
                ('sh000688', '科创50'),    # 000688
                ('sz399001', '深证成指'),  # 399001
                ('sz399006', '创业板指'), # 399006
            ]
            
            end = datetime.now().strftime('%Y%m%d')
            start = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
            
            for code, name in index_codes:
                try:
                    df = ak.stock_zh_index_daily(symbol=code)
                    if df is not None and not df.empty:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df[(df['date'] >= start) & (df['date'] <= end)]
                        if not df.empty:
                            self.index_data[name] = df.tail(5)
                    time.sleep(0.1)
                except:
                    pass
                    
        except Exception as e:
            print(f"[市场环境] 加载失败: {e}")
    
    def get_market_score(self) -> float:
        """
        市场环境综合评分 (0-100)
        50分为中性，>60偏牛，<40偏弱
        维度：指数涨跌(35分) + 涨停家数(35分) + 市场广度(30分)
        """
        if not self.index_data:
            return 50
        
        best_changes = []
        for name, df in self.index_data.items():
            if len(df) < 2 or 'close' not in df.columns:
                continue
            latest_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-2]
            if prev_close > 0:
                change = (latest_close - prev_close) / prev_close * 100
                best_changes.append(change)
        
        if not best_changes:
            return 50
        
        # 1. 指数涨跌 (0-35分) — 看最强指数
        best_change = max(best_changes)
        if best_change >= 3.0:   idx = 35
        elif best_change >= 2.0: idx = 32
        elif best_change >= 1.5:  idx = 28
        elif best_change >= 1.0:  idx = 25
        elif best_change >= 0.5:  idx = 21
        elif best_change >= 0.2:  idx = 17
        elif best_change >= 0:    idx = 13
        elif best_change >= -0.5: idx = 8
        else:                     idx = 4
        
        # 2. 涨停家数 (0-35分)
        zt = self.zt_count
        print(f"涨停家数: {zt}")
        if zt >= 200:   z = 35
        elif zt >= 150: z = 32
        elif zt >= 100: z = 28
        elif zt >= 80:  z = 25
        elif zt >= 60:  z = 21
        elif zt >= 40:  z = 16
        elif zt >= 20:  z = 11
        elif zt >= 10:  z = 6
        else:           z = 2
        
        # 3. 市场广度 (0-30分) — 看上涨指数占比和均值
        avg_change = sum(best_changes) / len(best_changes)
        up_count = sum(1 for c in best_changes if c > 0)
        breadth = up_count / len(best_changes) * 100
        
        if avg_change >= 1.0 and breadth >= 80:  b = 30
        elif avg_change >= 0.6 and breadth >= 60: b = 26
        elif avg_change >= 0.3 and breadth >= 50: b = 22
        elif avg_change >= 0.1 and breadth >= 50: b = 18
        elif avg_change >= 0 and breadth >= 40:   b = 14
        elif avg_change >= -0.3:                   b = 9
        else:                                     b = 4
        
        # 三维度等权平均，映射到0-100
        raw = (idx + z + b) / 3
        # 当前数据: idx=21(创业板+1.43%), z=21(71家), b=14(60%广度+0.37%)
        # raw = (21+21+14)/3 = 18.7 → 非常弱
        
      # ✅ 改为更合理的映射
        # raw范围约2-33，映射到0-100
        score = raw * (100 / 35)  # 0-100
        score = score * 0.8 + 10  # 微调到合理区间
        return round(min(max(score, 10), 90), 1)
        
    def get_summary(self) -> Dict:
        """获取市场环境摘要"""
        summary = {'涨停家数': self.zt_count, '指数评分': 0, '总分': 50}
        
        index_gains = []
        for name, df in self.index_data.items():
            if 'close' in df.columns and len(df) >= 2:
                gain = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
                index_gains.append((name, round(gain, 2)))
        
        summary['指数涨跌'] = index_gains
        summary['总分'] = self.get_market_score()
        return summary
class MABullishAnalyzer:
    """均线多头排列分析器"""

    def __init__(self, data_source: str = "auto", analysis_date: Optional[str] = None):
        self.name = "均线多头排列策略"
        self.ma_short = 5
        self.ma_mid = 10
        self.ma_long = 20
        self.volume_ma = 20

      # ✅ 改为新的权重
        self.weights = {
            'bullish_quality': 0.35,      # 多头质量（新）
            'price_position': 0.15,       # 价格位置
            'volume_trend': 0.15,         # 量能趋势
            'trend_strength': 0.20,       # 趋势强度（提高）
            'market_environment': 0.15    # 市场环境（降低）
        }

        if analysis_date:
            self.analysis_date = datetime.strptime(analysis_date, '%Y-%m-%d')
        else:
            self.analysis_date = None

        self.data_adapter = DataSourceAdapter()
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源，请安装akshare、tushare、baostock或yfinance")
        
        # 全局市场环境（只加载一次）
        self.market_env = MarketEnvironment()

    def _load_watchlist(self) -> Optional[pd.DataFrame]:
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
            
            stocks = []
            if 'watchlist' in data:
                for sector, categories in data['watchlist'].items():
                    for category, stock_list in categories.items():
                        for stock in stock_list:
                            if len(stock) >= 2:
                                stocks.append({
                                    'code': stock[1],
                                    'name': stock[0]
                                })
            
            if stocks:
                return pd.DataFrame(stocks)
            return None
            
        except Exception as e:
            print(f"加载自选股池失败: {e}")
            return None

    def analyze_stock(self, stock_code: str, stock_name: str = "") -> Dict:
        """分析单只股票"""
        result = {
            'stock_code': stock_code,
            'stock_name': stock_name or stock_code,
            'score': 0,
            'reasons':'',
            'is_bullish': False,
            'signals': {},
            'data': None,
            'error': None
        }

        try:
            end_date = self.analysis_date.strftime('%Y-%m-%d') if self.analysis_date else None
            start_date = (self.analysis_date - timedelta(days=60)).strftime('%Y-%m-%d') if self.analysis_date else None

            df = self.data_adapter.get_stock_data(stock_code, start_date, end_date)
           
            if df is None or df.empty:
                result['error'] = '获取数据失败'
                return result

            df = self.calculate_ma(df)
            result['data'] = df

            is_bullish = self.is_ma_bullish(df)
            result['is_bullish'] = is_bullish
            #print("result['is_bullish']: ", result['is_bullish'])
            if is_bullish:
                quality_grade, quality_score = self.get_bullish_quality(df)
                result['bullish_quality'] = quality_grade  # 新增
                result['reasons'] = quality_grade
                result['score'] = round(self.calculate_total_score(df), 2)
                  # ✅ 在这里添加技术确认
                tech_confirm = self.get_technical_confirmation(df)
                result['tech_confirm'] = tech_confirm


                # 补充详细信息
                latest = df.iloc[-1]
                result['current_price'] = round(float(latest['close']), 2)
                result['ma_status'] = f"MA{self.ma_short}/{self.ma_mid}/{self.ma_long}多头排列"
                result['trend_strength'] = f"{self.score_trend_strength(df):.0f}分"
                
                # 市场环境摘要
                market = self.market_env.get_summary()
                result['market_info'] = market
                
                result['signals'] = {
                    #'ma_arrangement': round(self.score_ma_arrangement(df), 1),
                    'bullish_quality': round(quality_score, 1),  # 替换 ma_arrangement
                    'price_position': round(self.score_price_position(df), 1),
                    'volume_trend': round(self.score_volume_trend(df), 1),
                    'trend_strength': round(self.score_trend_strength(df), 1),
                    'market_environment': round(self.score_market_environment(df), 1),
                }

            return result

        except Exception as e:
            result['error'] = str(e)
            print(f"分析股票 {stock_code} 失败: {e}")
            return result
    
    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，找出符合均线多头排列的股票"""
        print(f"开始扫描全市场股票... {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"使用数据源: {self.data_adapter.source}")
        
        # 优先使用自选股池
        stock_list = self._load_watchlist()
        if stock_list is not None and not stock_list.empty:
            print(f"使用自选股池，共{len(stock_list)}只股票")
        else:
            # 获取A股列表
            try:
                stock_list = self.data_adapter.get_stock_list()
                if stock_list is None or stock_list.empty:
                    print("获取股票列表失败")
                    return []
                print(f"获取到{len(stock_list)}只股票")
            except Exception as e:
                print(f"获取股票列表失败: {e}")
                return []
        
        candidates = []
        total = len(stock_list)
        
        for idx, (_, row) in enumerate(stock_list.iterrows(), 1):
            stock_code = row['code']
            stock_name = row.get('name', stock_code)
            
            # 进度显示
            if idx % 20 == 0:
                print(f"进度: {idx}/{total} ({idx/total*100:.1f}%)")
            
         
            
            # 分析个股
            result = self.analyze_stock(stock_code, stock_name)
            #print(result['signals'], result['score'])
              # ✅ 修改过滤条件，加入技术确认
            if result and result['is_bullish']:
                quality = result.get('bullish_quality', '')
                tech = result.get('tech_confirm', {})
                
                # 质量过滤
                quality_ok = quality in ['强势多头', '健康多头', '温和多头']
               # 技术确认 - MACD权重加倍
                tech_score = (
                    (1 if tech.get('macd_bullish', False) else 0) * 2 +
                    (1 if tech.get('rsi_healthy', False) else 0) * 1 +
                    (1 if tech.get('volume_healthy', False) else 0) * 1
                )
                tech_ok = tech_score >= 3  # 总分4分中至少3分
                
                if quality_ok and tech_ok and result['score'] >= 75:
                    candidates.append(result)
        # 按得分排序
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"扫描完成，发现{len(candidates)}只符合条件的股票")
        return candidates[:3]
    
    def calculate_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算均线"""
        df = df.copy()
        df[f'ma{self.ma_short}'] = df['close'].rolling(window=self.ma_short).mean()
        df[f'ma{self.ma_mid}'] = df['close'].rolling(window=self.ma_mid).mean()
        df[f'ma{self.ma_long}'] = df['close'].rolling(window=self.ma_long).mean()
        df[f'volume_ma'] = df['volume'].rolling(window=self.volume_ma).mean()
        return df

    def is_ma_bullish(self, df: pd.DataFrame) -> bool:
        """真正稳健的多头判断：连续3天多头 + 均线向上"""
        if len(df) < self.ma_long + 10:
            return False
        
        # 取最近3天
        recent = df.tail(3)
        
        # 连续3天 MA5 > MA10 > MA20
        for _, row in recent.iterrows():
            ma5 = row[f'ma{self.ma_short}']
            ma10 = row[f'ma{self.ma_mid}']
            ma20 = row[f'ma{self.ma_long}']
            if pd.isna(ma5) or pd.isna(ma10) or pd.isna(ma20):
                return False
            if not (ma5 > ma10 > ma20):
                return False
        
        # 2. 价格必须站上MA5（防止均线多头但价格破位）
        if df['close'].iloc[-1] < df[f'ma{self.ma_short}'].iloc[-1]:
            return False

        # 长期均线必须向上
        ma20_series = df[f'ma{self.ma_long}'].tail(5)
        if len(ma20_series) < 5:
            return False
        if ma20_series.iloc[-1] <= ma20_series.iloc[-4]:
            return False

        # 4. 均线发散度检查（至少2%差距）
        spread = (recent[f'ma{self.ma_short}'].iloc[-1] - recent[f'ma{self.ma_long}'].iloc[-1]) / recent[f'ma{self.ma_long}'].iloc[-1]
        if spread < 0.02:
            return False
        
        # 5. 确认前5天没有均线缠绕（排除假突破）
        prev_5 = df.iloc[-8:-3]
        if len(prev_5) > 0:
            for _, row in prev_5.iterrows():
                if row[f'ma{self.ma_short}'] < row[f'ma{self.ma_mid}']:
                    return False
        return True

    def get_bullish_quality(self, df: pd.DataFrame) -> Tuple[str, float]:
        """多头排列质量评级"""
        if not self.is_ma_bullish(df):
            return '非多头', 0
        
        latest = df.iloc[-1]
        ma5, ma10, ma20 = latest['ma5'], latest['ma10'], latest['ma20']
        
        # 发散度
        spread_5_20 = (ma5 - ma20) / ma20 * 100
        
        # 均线斜率
        ma20_series = df['ma20'].dropna().tail(5)
        if len(ma20_series) < 2:
            return '数据不足', 40
        slope_20 = (ma20_series.iloc[-1] - ma20_series.iloc[0]) / ma20_series.iloc[0] * 100
        
        # 连续多头天数
        bullish_days = 0
        for i in range(len(df)-1, -1, -1):
            row = df.iloc[i]
            if pd.notna(row['ma5']) and pd.notna(row['ma10']) and pd.notna(row['ma20']):
                if row['ma5'] > row['ma10'] > row['ma20']:
                    bullish_days += 1
                else:
                    break
            else:
                break
        
        # 评级
        if spread_5_20 > 8 and slope_20 > 2 and bullish_days >= 5:
            return '强势多头', 90
        elif spread_5_20 > 5 and slope_20 > 1 and bullish_days >= 3:
            return '健康多头', 75
        elif spread_5_20 > 3 and slope_20 > 0.5:
            return '温和多头', 60
        elif spread_5_20 > 1 and slope_20 > 0:
            return '弱势多头', 45
        else:
            return '粘合多头', 30


    def check_price_above_ma_long(self, df: pd.DataFrame) -> bool:
        """检查价格是否在长期均线上方"""
        if len(df) < 1:
            return False
        latest = df.iloc[-1]
        return latest['close'] > latest[f'ma{self.ma_long}']

    def check_volume_surge(self, df: pd.DataFrame, ratio: float = 1.2) -> bool:
        """检查成交量是否放大"""
        if len(df) < self.volume_ma:
            return False
        latest = df.iloc[-1]
        vol_ma = latest['volume_ma']
        if pd.isna(vol_ma) or vol_ma == 0:
            return False
        return latest['volume'] >= vol_ma * ratio

    def score_ma_arrangement(self, df: pd.DataFrame) -> float:
        """均线排列评分 0-100 — 更严格的评判标准"""
        if not self.is_ma_bullish(df):
            return 0
        
        latest = df.iloc[-1]
        ma_s = latest[f'ma{self.ma_short}']
        ma_m = latest[f'ma{self.ma_mid}']
        ma_l = latest[f'ma{self.ma_long}']
        
        # 发散程度（很重要）
        spread = (ma_s - ma_l) / ma_l * 100
        
        # 均线角度（稳定性）
        if len(df) < 20:
            return 0
        ma20_series = df[f'ma{self.ma_long}'].tail(10)
        ma20_slope = (ma20_series.iloc[-1] - ma20_series.iloc[0]) / ma20_series.iloc[0] * 100 if ma20_series.iloc[0] > 0 else 0
        
        # 综合评分
        score = 0
        # spread 评分 (0-60)
        if spread >= 20:
            score += 60
        elif spread >= 15:
            score += 52
        elif spread >= 10:
            score += 44
        elif spread >= 7:
            score += 36
        elif spread >= 5:
            score += 28
        elif spread >= 3:
            score += 20
        else:
            score += 12  # spread太小，不够强劲
        
        # MA20角度评分 (0-40)
        if ma20_slope >= 5:
            score += 40
        elif ma20_slope >= 3:
            score += 34
        elif ma20_slope >= 1:
            score += 28
        elif ma20_slope >= 0:
            score += 20
        else:
            score += 8  # 均线向下，不强
        
        return min(score, 100)

    def score_price_position(self, df: pd.DataFrame) -> float:
        """价格位置评分 0-100 — 加入远离均线的风险评估"""
        if len(df) < self.ma_long:
            return 0
        
        latest = df.iloc[-1]
        ma_l = latest[f'ma{self.ma_long}']
        if pd.isna(ma_l) or ma_l == 0:
            return 0
        
        position = (latest['close'] - ma_l) / ma_l * 100
        
        # 价格在MA20上方太远=追高风险，太近=支撑弱
        if position >= 25:
            return 60  # 追高风险大
        elif position >= 20:
            return 70
        elif position >= 15:
            return 80  # 适中
        elif position >= 10:
            return 75
        elif position >= 5:
            return 70
        elif position >= 3:
            return 55  # 离MA20太近，支撑弱
        elif position >= 0:
            return 40
        else:
            return 20  # 在MA20下方

    def score_volume_trend(self, df: pd.DataFrame) -> float:
        """成交量趋势评分 0-100"""
        if len(df) < 10:
            return 0
        
        recent_vol = df['volume'].tail(5).mean()
        older_vol = df['volume'].iloc[-10:-5].mean() if len(df) >= 10 else recent_vol
        vol_ma20 = df['volume'].rolling(window=20).mean().iloc[-1]
        
        if older_vol == 0 or pd.isna(vol_ma20):
            return 30
        
        ratio_recent = recent_vol / older_vol
        ratio_ma = recent_vol / vol_ma20 if vol_ma20 > 0 else 1
        
        # 综合评分：既要看量能是否放大，也要看是否在均量附近健康放量
        if ratio_recent >= 1.8 and ratio_ma >= 1.3:
            return 90  # 放量健康
        elif ratio_recent >= 1.5 and ratio_ma >= 1.1:
            return 78
        elif ratio_recent >= 1.2 and ratio_ma >= 0.9:
            return 65  # 量能温和
        elif ratio_recent >= 1.0 and ratio_ma >= 0.7:
            return 50  # 量能偏低
        elif ratio_recent < 0.8:
            return 35  # 缩量
        else:
            return 55

    def score_trend_strength(self, df: pd.DataFrame) -> float:
        """趋势强度评分 0-100（基于20日斜率）"""
        if len(df) < 20:
            return 0
        
        prices = df['close'].tail(20).values
        x = np.arange(len(prices))
        slope = np.polyfit(x, prices, 1)[0]
        avg_price = np.mean(prices)
        
        if avg_price == 0:
            return 0
        
        slope_pct = slope / avg_price * 100 * 20  # 换算为20日斜率
        
        if slope_pct >= 15:
            return 95
        elif slope_pct >= 10:
            return 82
        elif slope_pct >= 6:
            return 70
        elif slope_pct >= 3:
            return 58
        elif slope_pct >= 1:
            return 45
        elif slope_pct >= 0:
            return 30
        else:
            return 15

    def score_market_environment(self, df: pd.DataFrame) -> float:
        """市场环境评分 0-100（基于真实大盘数据）"""
        base_score = self.market_env.get_market_score()
        print(f"市场环境评分: {base_score}")
        # 结合自身与大盘的关系调整
        if len(df) < self.ma_long:
            return base_score
        
        # 个股是否跑赢大盘
        latest = df.iloc[-1]
        ma_l = latest[f'ma{self.ma_long}']
        if pd.isna(ma_l) or ma_l == 0:
            return base_score
        
        stock_strength = (latest['close'] - latest[f'ma{self.ma_long}']) / latest[f'ma{self.ma_long}'] * 100
        
       # 简化调整：个股强势时加分，弱势时减分
        if stock_strength > 15 and base_score < 50:
            return min(base_score + 15, 85)  # 独立走强
        elif stock_strength > 8:
            return min(base_score + 8, 90)
        elif stock_strength < 0 and base_score > 55:
            return max(base_score - 10, 30)  # 跑输大盘
        elif stock_strength < -5:
            return max(base_score - 15, 20)  # 严重跑输
        
        return base_score

    def calculate_total_score(self, df: pd.DataFrame) -> float:
        # """计算总分"""
        # return (
        #     self.score_ma_arrangement(df) * self.weights['ma_arrangement'] +
        #     self.score_price_position(df) * self.weights['price_position'] +
        #     self.score_volume_trend(df) * self.weights['volume_trend'] +
        #     self.score_trend_strength(df) * self.weights['trend_strength'] +
        #     self.score_market_environment(df) * self.weights['market_environment']
        # )
        """计算总分"""
        quality_grade, quality_score = self.get_bullish_quality(df)
        
        return (
            quality_score * self.weights['bullish_quality'] +           # 新
            self.score_price_position(df) * self.weights['price_position'] +
            self.score_volume_trend(df) * self.weights['volume_trend'] +
            self.score_trend_strength(df) * self.weights['trend_strength'] +
            self.score_market_environment(df) * self.weights['market_environment']
        )

    def get_technical_confirmation(self, df: pd.DataFrame) -> Dict:
        """技术指标确认"""
        if len(df) < 26:
            return {'macd_bullish': False, 'rsi_healthy': False, 'volume_healthy': False}
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9).mean()
        macd_bullish = dif.iloc[-1] > dea.iloc[-1] and dif.iloc[-1] > 0
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_healthy = 50 < rsi.iloc[-1] < 75  # 不超买
        
        # 量能健康
        vol_ma20 = df['volume'].rolling(20).mean()
        volume_healthy = df['volume'].iloc[-1] > vol_ma20.iloc[-1] * 0.8
        
        return {
            'macd_bullish': macd_bullish,
            'rsi_healthy': rsi_healthy,
            'volume_healthy': volume_healthy
        }



def main():
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser(description='均线多头排列策略分析器')
    parser.add_argument('--scan', action='store_true', help='扫描全市场（分析所有股票，较慢）')
    parser.add_argument('--stock', type=str, help='股票代码')
    parser.add_argument('--name', type=str, help='股票名称')
    parser.add_argument('--top', type=int, default=20, help='返回前N名')
    parser.add_argument('--source', type=str, default='auto',
                        help='数据源 (akshare/tushare/baostock/yfinance/auto)')
    parser.add_argument('--date', type=str, help='分析日期 (格式: YYYY-MM-DD)')
    parser.add_argument('--sector', type=str, help='分析指定板块 (科技/医药/金融/消费/新能源/军工)')
    parser.add_argument('--all-sectors', action='store_true', help='分析所有板块')
    parser.add_argument('--stocks', type=str, help='分析指定股票列表，逗号分隔，如: 000001,000002,600000')
    
    args = parser.parse_args()

    try:
        analyzer = MABullishAnalyzer(data_source=args.source, analysis_date=args.date)
    except RuntimeError as e:
        print(f"❌ {e}")
        return

    if args.scan:
        # 扫描功能暂不支持指定日期（需要遍历所有股票，较慢）
        print("注意: 扫描模式使用最新数据，单只股票分析支持指定日期")
        results = analyzer.scan_all_stocks(top_n=args.top)
        for r in results:
            analyzer.print_analysis(r)
        print(f"\n共找到 {len(results)} 只符合条件的股票")

    elif args.stocks:
        stocks = [s.strip() for s in args.stocks.split(',')]
        for code in stocks:
            result = analyzer.analyze_stock(code, code)
            analyzer.print_analysis(result)

    elif args.stock:
        result = analyzer.analyze_stock(args.stock, args.name or args.stock)
        analyzer.print_analysis(result)

    elif args.all_sectors:
        from skills.scripts.sector_analyzer import SectorAnalyzer
        sector_analyzer = SectorAnalyzer(analyzer)
        results = sector_analyzer.analyze_all_sectors(analysis_date=args.date)
        for sector, result in results.items():
            print(f"\n{'='*60}")
            print(f"板块: {sector}")
            print(f"{'='*60}")
            for r in result:
                analyzer.print_analysis(r)

    elif args.sector:
        from skills.scripts.sector_analyzer import SectorAnalyzer
        sector_analyzer = SectorAnalyzer(analyzer)
        result = sector_analyzer.analyze_sector(args.sector, analysis_date=args.date)
        print(f"\n{'='*60}")
        print(f"板块: {args.sector}")
        print(f"{'='*60}")
        for r in result:
            analyzer.print_analysis(r)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
