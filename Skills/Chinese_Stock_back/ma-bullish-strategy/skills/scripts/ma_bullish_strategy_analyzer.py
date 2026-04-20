#!/usr/bin/env python3
"""
均线多头排列策略分析器
支持多数据源：akshare、tushare、baostock、yfinance
"""

import os
import sys

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


class MABullishAnalyzer:
    """均线多头排列分析器"""
    
    def __init__(self, data_source: str = "auto", analysis_date: Optional[str] = None):
        self.name = "均线多头排列策略"
        self.ma_short = 5      # 短期均线
        self.ma_mid = 10       # 中期均线
        self.ma_long = 20      # 长期均线
        self.volume_ma = 20    # 成交量均线周期
        
        # 评分权重
        self.weights = {
            'ma_arrangement': 0.35,    # 均线排列
            'price_position': 0.20,    # 价格位置
            'volume_trend': 0.20,      # 成交量趋势
            'trend_strength': 0.15,    # 趋势强度
            'market_environment': 0.10  # 市场环境
        }
        
        # 分析日期（用于历史回测）
        if analysis_date:
            self.analysis_date = datetime.strptime(analysis_date, '%Y-%m-%d')
        else:
            self.analysis_date = None
        
        # 初始化数据源适配器
        self.data_adapter = DataSourceAdapter(data_source)
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源，请安装akshare、tushare、baostock或yfinance")
        
    def _load_watchlist(self) -> Optional[pd.DataFrame]:
        """加载自选股池"""
        # 使用当前工作目录（项目根目录）查找 watchlist.yaml
        watchlist_path = '/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/watchlist.yaml'
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
            if idx % 100 == 0:
                print(f"进度: {idx}/{total} ({idx/total*100:.1f}%)")
            
            # 过滤不符合条件的股票
            if self._should_filter(stock_code, stock_name):
                continue
            
            # 分析个股
            result = self.analyze_stock(stock_code, stock_name)
            if result and result['signal'] == 'BUY' and result['score'] >= 70:
                candidates.append(result)
        
        # 按得分排序
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"扫描完成，发现{len(candidates)}只符合条件的股票")
        return candidates[:top_n]
    
    def analyze_stock(self, stock_code: str, stock_name: str, analysis_date: Optional[str] = None) -> Optional[Dict]:
        """分析单只股票是否出现买入信号
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            analysis_date: 分析日期，格式 'YYYY-MM-DD'，默认为最新数据
        """
        try:
            # 获取历史数据
            df = self._get_stock_data(stock_code)
            if df is None or len(df) < 60:
                return None
            
            # 计算技术指标
            df = self._calculate_indicators(df)
            
            # 确保日期列是datetime类型
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            elif 'trade_date' in df.columns:
                df['date'] = pd.to_datetime(df['trade_date'])
            
            # 重置索引以确保可以用位置索引
            df = df.reset_index(drop=True)
            
            # 如果指定了分析日期，找到对应的数据
            if analysis_date:
                target_date = pd.to_datetime(analysis_date)
                # 找到小于等于目标日期的最新数据
                mask = df['date'] <= target_date
                if not mask.any():
                    print(f"{stock_code} 在 {analysis_date} 之前没有数据")
                    return None
                df_filtered = df[mask]
                if len(df_filtered) < 2:
                    print(f"{stock_code} 在 {analysis_date} 之前数据不足")
                    return None
                # 使用位置索引
                latest_idx = df_filtered.index[-1]
                prev_idx = df_filtered.index[-2]
                latest = df_filtered.loc[latest_idx]
                prev = df_filtered.loc[prev_idx]
            else:
                # 获取最新数据
                latest = df.iloc[-1]
                prev = df.iloc[-2]
            
            # 1. 均线排列分析
            ma_arrangement = self._analyze_ma_arrangement(latest)
            if not ma_arrangement['is_bullish']:
                return None
            
            # 2. 价格位置分析
            price_position = self._analyze_price_position(latest)
            
            # 3. 成交量分析
            volume_trend = self._analyze_volume_trend(latest, df)
            
            # 4. 趋势强度分析
            trend_strength = self._analyze_trend_strength(df)
            
            # 5. 市场环境分析
            market_env = self._analyze_market_environment()
            
            # 计算总分
            total_score = self._calculate_total_score(
                ma_arrangement, price_position, 
                volume_trend, trend_strength, market_env
            )
            
            # 判断是否出现买入信号
            is_buy_signal = self._check_buy_signal(
                latest, prev, ma_arrangement, volume_trend
            )
            
            if not is_buy_signal:
                return None
            
            # 计算入场价格和止损位
            entry_price = self._calculate_entry_price(latest)
            stop_loss = self._calculate_stop_loss(latest, df)
            target_price = self._calculate_target_price(latest, df)
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'signal': 'BUY',
                'score': round(total_score, 2),
                'current_price': round(entry_price, 2),
                'entry_price': round(entry_price, 2),
                'stop_loss': round(stop_loss, 2),
                'target_price': round(target_price, 2),
                'risk_reward_ratio': round((target_price - entry_price) / (entry_price - stop_loss), 2) if entry_price != stop_loss else 0,
                'details': {
                    'ma_arrangement': ma_arrangement,
                    'price_position': price_position,
                    'volume_trend': volume_trend,
                    'trend_strength': trend_strength,
                    'market_environment': market_env
                },
                'suggestion': self._generate_suggestion(total_score, stock_name),
                'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            print(f"分析{stock_code}失败: {e}")
            return None
    
    def _get_stock_data(self, stock_code: str) -> Optional[pd.DataFrame]:
        """获取股票历史数据"""
        try:
            # 获取最近120个交易日的数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=180)
            
            df = self.data_adapter.get_stock_data(
                stock_code,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )
            
            if df is None or len(df) < 60:
                return None
            
            # 标准化列名（如果适配器没有统一处理）
            column_mapping = {
                'trade_date': 'date',
                'vol': 'volume',
                'pctChg': 'pct_change',
                'preclose': 'pre_close'
            }
            df = df.rename(columns=column_mapping)
            
            # 确保必要的列存在
            required_cols = ['date', 'open', 'close', 'high', 'low', 'volume']
            for col in required_cols:
                if col not in df.columns:
                    print(f"警告: {stock_code} 缺少列 {col}")
                    return None
            
            return df
            
        except Exception as e:
            return None
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        # 移动平均线
        df[f'ma{self.ma_short}'] = df['close'].rolling(self.ma_short).mean()
        df[f'ma{self.ma_mid}'] = df['close'].rolling(self.ma_mid).mean()
        df[f'ma{self.ma_long}'] = df['close'].rolling(self.ma_long).mean()
        
        # 成交量均线
        df[f'volume_ma{self.volume_ma}'] = df['volume'].rolling(self.volume_ma).mean()
        
        # 价格相对于均线的位置
        df['price_to_ma20'] = (df['close'] - df[f'ma{self.ma_long}']) / df[f'ma{self.ma_long}'] * 100
        
        # 趋势强度（ADX简化版）
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = abs(df['high'] - df['close'].shift(1))
        df['low_close'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['atr'] = df['tr'].rolling(14).mean()
        
        return df
    
    def _analyze_ma_arrangement(self, latest: pd.Series) -> Dict:
        """分析均线排列"""
        ma5 = latest[f'ma{self.ma_short}']
        ma10 = latest[f'ma{self.ma_mid}']
        ma20 = latest[f'ma{self.ma_long}']
        
        # 判断多头排列
        is_bullish = ma5 > ma10 > ma20
        
        # 计算排列强度
        if is_bullish:
            spread_5_10 = (ma5 - ma10) / ma10 * 100
            spread_10_20 = (ma10 - ma20) / ma20 * 100
            
            if spread_5_10 > 2 and spread_10_20 > 2:
                score = 100
                level = "强势多头排列"
            elif spread_5_10 > 1 and spread_10_20 > 1:
                score = 85
                level = "标准多头排列"
            else:
                score = 70
                level = "弱多头排列"
        else:
            score = 0
            level = "非多头排列"
        
        return {
            'score': score,
            'is_bullish': is_bullish,
            'level': level,
            'values': {
                'ma5': round(ma5, 2),
                'ma10': round(ma10, 2),
                'ma20': round(ma20, 2)
            }
        }
    
    def _analyze_price_position(self, latest: pd.Series) -> Dict:
        """分析价格位置"""
        close = latest['close']
        ma20 = latest[f'ma{self.ma_long}']
        price_to_ma20 = latest['price_to_ma20']
        
        # 判断价格位置
        if close > ma20:
            if price_to_ma20 < 5:
                score = 100
                position = "理想位置（刚站上均线）"
            elif price_to_ma20 < 10:
                score = 85
                position = "良好位置（均线上方）"
            else:
                score = 70
                position = "偏高位置（注意回调）"
        else:
            score = 0
            position = "均线下方"
        
        return {
            'score': score,
            'position': position,
            'price_to_ma20': round(price_to_ma20, 2)
        }
    
    def _analyze_volume_trend(self, latest: pd.Series, df: pd.DataFrame) -> Dict:
        """分析成交量趋势"""
        current_volume = latest['volume']
        avg_volume = latest[f'volume_ma{self.volume_ma}']
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        # 判断成交量是否放大
        if volume_ratio >= 1.5:
            score = 100
            trend = "明显放量（>1.5倍）"
        elif volume_ratio >= 1.2:
            score = 85
            trend = "温和放量（1.2-1.5倍）"
        elif volume_ratio >= 1.0:
            score = 70
            trend = "正常放量（1-1.2倍）"
        else:
            score = 50
            trend = "缩量"
        
        # 检查成交量趋势（最近5日）
        recent_volumes = df['volume'].tail(5)
        volume_trend = recent_volumes.is_monotonic_increasing
        
        return {
            'score': score,
            'trend': trend,
            'volume_ratio': round(volume_ratio, 2),
            'volume_increasing': volume_trend
        }
    
    def _analyze_trend_strength(self, df: pd.DataFrame) -> Dict:
        """分析趋势强度"""
        # 使用价格斜率作为趋势强度指标
        closes = df['close'].tail(20)
        x = np.arange(len(closes))
        z = np.polyfit(x, closes, 1)
        slope = z[0]
        
        # 计算趋势强度
        price_range = closes.max() - closes.min()
        if price_range > 0:
            strength_pct = slope / price_range * 100
        else:
            strength_pct = 0
        
        if strength_pct > 30:
            score = 100
            strength = "强势上涨"
        elif strength_pct > 15:
            score = 85
            strength = "稳定上涨"
        elif strength_pct > 0:
            score = 70
            strength = "温和上涨"
        else:
            score = 40
            strength = "下跌趋势"
        
        return {
            'score': score,
            'strength': strength,
            'slope': round(slope, 2)
        }
    
    def _analyze_market_environment(self) -> Dict:
        """分析市场环境"""
        try:
            # 使用数据源适配器获取大盘指数
            sh_index = self.data_adapter.get_stock_data('000001', 
                (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                datetime.now().strftime('%Y-%m-%d'))
            
            if sh_index is not None and len(sh_index) >= 5:
                # 计算近期涨跌幅
                sh_recent = sh_index['close'].pct_change().tail(5).mean() * 100
                
                if sh_recent > 1:
                    score = 100
                    env = "牛市氛围"
                elif sh_recent > 0:
                    score = 85
                    env = "震荡偏多"
                elif sh_recent > -1:
                    score = 60
                    env = "震荡偏空"
                else:
                    score = 40
                    env = "熊市氛围"
                
                return {
                    'score': score,
                    'environment': env,
                    'sh_index_change': round(sh_recent, 2)
                }
            else:
                return {
                    'score': 70,
                    'environment': "未知",
                    'note': "无法获取市场数据"
                }
            
        except:
            return {
                'score': 70,
                'environment': "未知",
                'note': "无法获取市场数据"
            }
    
    def _check_buy_signal(self, latest: pd.Series, prev: pd.Series,
                         ma_arrangement: Dict, volume_trend: Dict) -> bool:
        """检查是否出现买入信号"""
        # 核心条件
        core_conditions = (
            ma_arrangement['is_bullish'] and  # 均线多头排列
            latest['close'] > latest[f'ma{self.ma_long}'] and  # 价格站上20日线
            volume_trend['volume_ratio'] >= 1.2  # 成交量放大20%以上
        )
        
        # 额外确认：今日收盘价高于昨日
        price_up = latest['close'] > prev['close']
        
        return core_conditions and price_up
    
    def _calculate_entry_price(self, latest: pd.Series) -> float:
        """计算入场价格"""
        # 使用当前收盘价作为入场价
        return latest['close']
    
    def _calculate_stop_loss(self, latest: pd.Series, df: pd.DataFrame) -> float:
        """计算止损位"""
        ma20 = latest[f'ma{self.ma_long}']
        # 止损设置为MA20下方2%
        return ma20 * 0.98
    
    def _calculate_target_price(self, latest: pd.Series, df: pd.DataFrame) -> float:
        """计算目标价"""
        # 使用ATR或前期高点作为目标
        atr = latest['atr'] if 'atr' in latest and not pd.isna(latest['atr']) else latest['close'] * 0.05
        # 目标价为入场价 + 3倍ATR
        return latest['close'] + atr * 3
    
    def _calculate_total_score(self, ma_arr: Dict, price_pos: Dict,
                               volume: Dict, trend: Dict, market: Dict) -> float:
        """计算总分"""
        total = (
            ma_arr['score'] * self.weights['ma_arrangement'] +
            price_pos['score'] * self.weights['price_position'] +
            volume['score'] * self.weights['volume_trend'] +
            trend['score'] * self.weights['trend_strength'] +
            market['score'] * self.weights['market_environment']
        )
        return total
    
    def _generate_suggestion(self, score: float, stock_name: str) -> str:
        """生成操作建议"""
        if score >= 85:
            return f"【强烈推荐】{stock_name}均线多头排列良好，成交量配合，建议积极买入"
        elif score >= 75:
            return f"【推荐】{stock_name}符合买入条件，建议分批建仓"
        elif score >= 70:
            return f"【关注】{stock_name}基本符合条件，建议等待更好的入场点"
        else:
            return f"【暂缓】{stock_name}条件不充分，建议继续观察"
    
    def _should_filter(self, stock_code: str, stock_name: str) -> bool:
        """过滤不符合条件的股票"""
        # 过滤ST股票
        if 'ST' in stock_name or '*ST' in stock_name:
            return True
        
        # 过滤北交所
        if stock_code.startswith('8'):
            return True
        
        # 过滤停牌股票（简化判断）
        if '退' in stock_name:
            return True
        
        return False


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='均线多头排列策略分析')
    parser.add_argument('--scan', action='store_true', help='扫描全市场（分析所有股票，较慢）')
    parser.add_argument('--stock', type=str, help='股票代码')
    parser.add_argument('--name', type=str, help='股票名称')
    parser.add_argument('--top', type=int, default=20, help='返回前N名')
    parser.add_argument('--source', type=str, default='auto', 
                       choices=['auto', 'akshare', 'tushare', 'baostock', 'yfinance'],
                       help='数据源选择')
    parser.add_argument('--date', type=str, help='分析日期 (格式: YYYY-MM-DD)，默认为最新数据')
    parser.add_argument('--sector', type=str, help='分析指定板块 (科技/医药/金融/消费/新能源/军工)')
    parser.add_argument('--all-sectors', action='store_true', help='分析所有板块')
    parser.add_argument('--stocks', type=str, help='分析指定股票列表，逗号分隔，如: 000001,000002,600000')
    
    args = parser.parse_args()
    
    try:
        analyzer = MABullishAnalyzer(data_source=args.source)
    except RuntimeError as e:
        print(f"错误: {e}")
        print("\n请安装以下数据源之一:")
        print("  pip install akshare    # 推荐，免费")
        print("  pip install tushare    # 需要token")
        print("  pip install baostock   # 免费")
        print("  pip install yfinance   # 有限支持A股")
        return
    
    # 显示分析日期
    if args.date:
        print(f"分析日期: {args.date}")
    
    if args.scan:
        # 扫描功能暂不支持指定日期（需要遍历所有股票，较慢）
        print("注意: 扫描模式使用最新数据，单只股票分析支持指定日期")
        results = analyzer.scan_all_stocks(top_n=args.top)
        
        print("\n" + "="*80)
        print(f"均线多头排列策略扫描结果 - {datetime.now().strftime('%Y-%m-%d')}")
        print("="*80)
        
        for i, stock in enumerate(results, 1):
            print(f"\n{i}. {stock['stock_name']}({stock['stock_code']})")
            print(f"   得分: {stock['score']} | 信号: {stock['signal']}")
            print(f"   当前价: {stock['current_price']} | 入场: {stock['entry_price']}")
            print(f"   止损: {stock['stop_loss']} | 目标: {stock['target_price']}")
            print(f"   建议: {stock['suggestion']}")
            print(f"   {'-'*60}")
        
        print(f"\n共发现{len(results)}只符合条件的股票")
    
    elif args.sector:
        # 板块分析
        try:
            from skills.ma_bullish.scripts.sector_analyzer import SectorAnalyzer
        except ImportError:
            #sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/ma-bullish-strategy')
            from skills.ma_bullish.scripts.sector_analyzer import SectorAnalyzer
        
        sector_analyzer = SectorAnalyzer(analyzer)
        result = sector_analyzer.analyze_sector(args.sector, analysis_date=args.date)
        print(sector_analyzer.generate_sector_report(result))
    
    elif args.all_sectors:
        # 分析所有板块
        try:
            from skills.ma_bullish.scripts.sector_analyzer import SectorAnalyzer
        except ImportError:
           # sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/ma-bullish-strategy')
            from skills.ma_bullish.scripts.sector_analyzer import SectorAnalyzer
        
        sector_analyzer = SectorAnalyzer(analyzer)
        results = sector_analyzer.analyze_all_sectors(analysis_date=args.date)
        
        for sector_name, result in results.items():
            print(sector_analyzer.generate_sector_report(result))
            print("\n")
    
    elif args.stocks:
        # 分析指定股票列表
        try:
            from skills.ma_bullish.scripts.sector_analyzer import SectorAnalyzer
        except ImportError:
           # sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/ma-bullish-strategy')
            from skills.ma_bullish.scripts.sector_analyzer import SectorAnalyzer
        
        stock_list = [s.strip() for s in args.stocks.split(',')]
        print(f"分析指定股票列表: {stock_list}")
        
        sector_analyzer = SectorAnalyzer(analyzer)
        result = sector_analyzer.analyze_stocks(stock_list, name="指定股票", analysis_date=args.date)
        print(sector_analyzer.generate_sector_report(result))
    
    elif args.stock:
        result = analyzer.analyze_stock(args.stock, args.name or args.stock, analysis_date=args.date)
        if result:
            import json
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            date_str = f"在 {args.date} " if args.date else ""
            print(f"{args.stock} {date_str}不符合均线多头排列条件")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
