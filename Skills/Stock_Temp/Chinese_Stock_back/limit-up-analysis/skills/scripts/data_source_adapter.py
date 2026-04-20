# A股数据源适配器
# 支持多个数据源：akshare、tushare、baostock、yfinance
# 优先级：tushare > akshare > baostock > yfinance

import pandas as pd
import numpy as np
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import os
import time

class DataSourceAdapter:
    """A股多数据源适配器 - 支持优先级自动切换"""
    
    # 数据源优先级（质量从高到低）
    PRIORITY = ["tushare", "akshare", "baostock", "yfinance"]
    
    # 数据源质量评分
    QUALITY_SCORE = {
        "tushare": 5,    # 数据最全面、稳定，但需要token
        "akshare": 4,    # 免费，数据丰富，偶尔不稳定
        "baostock": 3,   # 免费，数据稳定，但获取较慢
        "yfinance": 2    # 有限支持A股
    }
    
    def __init__(self, source: str = "auto", fallback: bool = True):
        """
        初始化数据源适配器
        
        Args:
            source: 数据源名称 ("akshare", "tushare", "baostock", "yfinance", "auto")
                   auto会按优先级自动选择最佳可用数据源
            fallback: 是否启用自动降级（主数据源失败时自动尝试其他）
        """
        self.source = source
        self.fallback = fallback
        self.data_source = None
        self.available_sources = []  # 所有可用的数据源
        self.current_source_index = 0  # 当前使用的数据源索引
        self._init_source()
    
    def _init_source(self):
        """初始化数据源"""
        if self.source == "auto":
            # 按优先级尝试所有数据源，记录所有可用的
            for src in self.PRIORITY:
                if self._try_init_source(src, silent=True):
                    self.available_sources.append(src)
            
            # 选择优先级最高的可用数据源
            if self.available_sources:
                # 按质量排序
                self.available_sources.sort(key=lambda x: self.QUALITY_SCORE.get(x, 0), reverse=True)
                best_source = self.available_sources[0]
                self._try_init_source(best_source)
                self.source = best_source
            else:
                print("❌ 没有可用的数据源")
        else:
            # 尝试指定的数据源
            if self._try_init_source(self.source):
                self.available_sources.append(self.source)
            elif self.fallback:
                # 如果指定数据源失败，尝试其他
                print(f"⚠️ 指定数据源 {self.source} 不可用，尝试其他数据源...")
                for src in self.PRIORITY:
                    if src != self.source and self._try_init_source(src, silent=True):
                        self.available_sources.append(src)
                
                if self.available_sources:
                    self.available_sources.sort(key=lambda x: self.QUALITY_SCORE.get(x, 0), reverse=True)
                    best_source = self.available_sources[0]
                    self._try_init_source(best_source)
                    self.source = best_source
    
    def _try_init_source(self, source: str, silent: bool = False) -> bool:
        """
        尝试初始化指定数据源
        
        Args:
            source: 数据源名称
            silent: 是否静默模式（不打印日志）
        """
        try:
            if source == "akshare":
                import akshare as ak
                # 测试获取数据
                test_df = ak.stock_zh_a_spot_em()
                if test_df is None or test_df.empty:
                    if not silent:
                        print(f"⚠️ akshare 测试获取数据失败")
                    return False
                self.data_source = ak
                if not silent:
                    print(f"✅ 使用数据源: akshare (质量评分: {self.QUALITY_SCORE['akshare']}/5)")
                return True
                
            elif source == "tushare":
                import tushare as ts
                token = os.getenv("TUSHARE_TOKEN")
                if not token:
                    if not silent:
                        print(f"⚠️ TUSHARE_TOKEN 环境变量未设置")
                    return False
                pro = ts.pro_api(token)
                # 测试获取数据
                test_df = pro.stock_basic(limit=1)
                if test_df is None or test_df.empty:
                    if not silent:
                        print(f"⚠️ tushare 测试获取数据失败")
                    return False
                self.data_source = pro
                if not silent:
                    print(f"✅ 使用数据源: tushare (质量评分: {self.QUALITY_SCORE['tushare']}/5)")
                return True
                
            elif source == "baostock":
                import baostock as bs
                lg = bs.login()
                if lg.error_code != '0':
                    if not silent:
                        print(f"⚠️ baostock登录失败: {lg.error_msg}")
                    return False
                # 测试获取数据
                today = datetime.now()
                if today.weekday() >= 5:
                    today = today - timedelta(days=today.weekday() - 4)
                rs = bs.query_all_stock(day=today.strftime('%Y-%m-%d'))
                if rs.error_code != '0':
                    if not silent:
                        print(f"⚠️ baostock 测试获取数据失败")
                    return False
                self.data_source = bs
                if not silent:
                    print(f"✅ 使用数据源: baostock (质量评分: {self.QUALITY_SCORE['baostock']}/5)")
                return True
                
            elif source == "yfinance":
                import yfinance as yf
                # 测试获取数据
                ticker = yf.Ticker("000001.SS")
                test_df = ticker.history(period="5d")
                if test_df is None or test_df.empty:
                    if not silent:
                        print(f"⚠️ yfinance 测试获取数据失败")
                    return False
                self.data_source = yf
                if not silent:
                    print(f"✅ 使用数据源: yfinance (质量评分: {self.QUALITY_SCORE['yfinance']}/5)")
                return True
                
        except ImportError:
            if not silent:
                print(f"⚠️ {source} 未安装")
            return False
        except Exception as e:
            if not silent:
                print(f"⚠️ {source} 初始化失败: {e}")
            return False
        
        return False
    
    def switch_to_next_source(self) -> bool:
        """
        切换到下一个可用数据源
        
        Returns:
            是否切换成功
        """
        if len(self.available_sources) <= 1:
            print("❌ 没有其他可用数据源")
            return False
        
        self.current_source_index = (self.current_source_index + 1) % len(self.available_sources)
        next_source = self.available_sources[self.current_source_index]
        
        print(f"🔄 切换到备用数据源: {next_source}")
        return self._try_init_source(next_source)
    
    def get_source_quality(self) -> int:
        """获取当前数据源质量评分"""
        return self.QUALITY_SCORE.get(self.source, 0)
    
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """获取A股列表"""
        max_retries = len(self.available_sources) if self.fallback else 1
        
        for attempt in range(max_retries):
            try:
                if self.source == "akshare":
                    return self._akshare_stock_list()
                elif self.source == "tushare":
                    return self._tushare_stock_list()
                elif self.source == "baostock":
                    return self._baostock_stock_list()
                elif self.source == "yfinance":
                    return self._yfinance_stock_list()
            except Exception as e:
                print(f"⚠️ {self.source} 获取股票列表失败: {e}")
                if self.fallback and attempt < max_retries - 1:
                    if self.switch_to_next_source():
                        continue
                return None
        
        return None
    
    def get_stock_data(self, stock_code: str, 
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None,
                       max_retries: int = 2) -> Optional[pd.DataFrame]:
        """
        获取股票历史数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            max_retries: 最大重试次数
        """
        for attempt in range(max_retries):
            try:
                if self.source == "akshare":
                    return self._akshare_stock_data(stock_code, start_date, end_date)
                elif self.source == "tushare":
                    return self._tushare_stock_data(stock_code, start_date, end_date)
                elif self.source == "baostock":
                    return self._baostock_stock_data(stock_code, start_date, end_date)
                elif self.source == "yfinance":
                    return self._yfinance_stock_data(stock_code, start_date, end_date)
            except Exception as e:
                print(f"⚠️ {self.source} 获取{stock_code}数据失败 (尝试 {attempt+1}/{max_retries}): {e}")
                if self.fallback and attempt < max_retries - 1:
                    time.sleep(1)  # 等待1秒后重试
                    continue
                return None
        
        return None
    
    # ============== akshare 实现 ==============
    
    def _akshare_stock_list(self) -> Optional[pd.DataFrame]:
        """akshare获取股票列表"""
        try:
            df = self.data_source.stock_zh_a_spot_em()
            return df[['代码', '名称']].rename(columns={'代码': 'code', '名称': 'name'})
        except Exception as e:
            print(f"akshare获取股票列表失败: {e}")
            return None
    
    def _akshare_stock_data(self, stock_code: str, 
                            start_date: Optional[str] = None,
                            end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """akshare获取股票数据"""
        try:
            if not end_date:
                end_date = datetime.now()
            else:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
            
            if not start_date:
                start_date = end_date - timedelta(days=180)
            else:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
            
            df = self.data_source.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date.strftime('%Y%m%d'),
                end_date=end_date.strftime('%Y%m%d'),
                adjust="qfq"
            )
            
            df.columns = ['date', 'open', 'close', 'high', 'low', 
                         'volume', 'amount', 'amplitude', 
                         'pct_change', 'change', 'turnover']
            # 转换日期列为datetime类型
            df['date'] = pd.to_datetime(df['date'])
            return df
        except Exception as e:
            print(f"akshare获取{stock_code}数据失败: {e}")
            return None
    
    # ============== tushare 实现 ==============
    
    def _tushare_stock_list(self) -> Optional[pd.DataFrame]:
        """tushare获取股票列表"""
        try:
            df = self.data_source.stock_basic(exchange='', list_status='L')
            return df[['ts_code', 'name', 'symbol']].rename(columns={'symbol': 'code'})
        except Exception as e:
            print(f"tushare获取股票列表失败: {e}")
            return None
    
    def _tushare_stock_data(self, stock_code: str,
                            start_date: Optional[str] = None,
                            end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """tushare获取股票数据"""
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            else:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').strftime('%Y%m%d')
            
            if not start_date:
                start_date = (datetime.now() - timedelta(days=180)).strftime('%Y%m%d')
            else:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').strftime('%Y%m%d')
            
            # 转换股票代码格式
            if len(stock_code) == 6:
                if stock_code.startswith('6'):
                    ts_code = f"{stock_code}.SH"
                else:
                    ts_code = f"{stock_code}.SZ"
            else:
                ts_code = stock_code
            
            df = self.data_source.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            
            if df is None or df.empty:
                return None
            
            df = df.sort_values('trade_date')
            df.columns = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 
                         'pre_close', 'pct_change', 'change', 'vol', 'amount']
            df['date'] = pd.to_datetime(df['trade_date'])
            df['volume'] = df['vol'] * 100  # 手转股
            
            return df[['date', 'open', 'close', 'high', 'low', 'volume', 'amount', 'pct_change']]
        except Exception as e:
            print(f"tushare获取{stock_code}数据失败: {e}")
            return None
    
    # ============== baostock 实现 ==============
    
    def _baostock_stock_list(self) -> Optional[pd.DataFrame]:
        """baostock获取股票列表"""
        try:
            # 获取当前交易日
            today = datetime.now()
            # 如果今天是周末，获取周五的数据
            if today.weekday() >= 5:
                today = today - timedelta(days=today.weekday() - 4)
            
            rs = self.data_source.query_all_stock(day=today.strftime('%Y-%m-%d'))
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                print("baostock返回空数据")
                return None
                
            df = pd.DataFrame(data_list, columns=rs.fields)
            # baostock返回的code格式为 sh.600000 或 sz.000001
            df['code'] = df['code'].str.extract(r'\.(\d{6})$')[0]
            df['name'] = df['code']  # baostock不返回名称，用代码代替
            return df[['code', 'name']].dropna()
        except Exception as e:
            print(f"baostock获取股票列表失败: {e}")
            return None
    
    def _baostock_stock_data(self, stock_code: str,
                             start_date: Optional[str] = None,
                             end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """baostock获取股票数据"""
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
            
            # 转换股票代码格式
            if len(stock_code) == 6:
                if stock_code.startswith('6'):
                    bs_code = f"sh.{stock_code}"
                else:
                    bs_code = f"sz.{stock_code}"
            else:
                bs_code = stock_code
            
            rs = self.data_source.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,preclose,volume,amount,pctChg",
                start_date=start_date, end_date=end_date,
                frequency="d", adjustflag="3"
            )
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            df = pd.DataFrame(data_list, columns=rs.fields)
            df.columns = ['date', 'code', 'open', 'high', 'low', 'close', 
                         'pre_close', 'volume', 'amount', 'pct_change']
            
            # 转换日期列为datetime类型
            df['date'] = pd.to_datetime(df['date'])
            
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_change']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
        except Exception as e:
            print(f"baostock获取{stock_code}数据失败: {e}")
            return None
    
    # ============== yfinance 实现 ==============
    
    def _yfinance_stock_list(self) -> Optional[pd.DataFrame]:
        """yfinance获取股票列表（有限支持）"""
        print("⚠️ yfinance不支持获取完整A股列表，请使用其他数据源")
        return None
    
    def _yfinance_stock_data(self, stock_code: str,
                             start_date: Optional[str] = None,
                             end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """yfinance获取股票数据"""
        try:
            # 转换股票代码格式
            if len(stock_code) == 6:
                if stock_code.startswith('6'):
                    yf_code = f"{stock_code}.SS"
                else:
                    yf_code = f"{stock_code}.SZ"
            else:
                yf_code = stock_code
            
            ticker = self.data_source.Ticker(yf_code)
            
            if not end_date:
                end_date = datetime.now()
            else:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
            
            if not start_date:
                start_date = end_date - timedelta(days=180)
            else:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
            
            df = ticker.history(start=start_date, end=end_date)
            
            if df.empty:
                return None
            
            df = df.reset_index()
            df.columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'dividends', 'stock_splits']
            df['amount'] = df['close'] * df['volume']
            df['pct_change'] = df['close'].pct_change() * 100
            
            return df[['date', 'open', 'close', 'high', 'low', 'volume', 'amount', 'pct_change']]
        except Exception as e:
            print(f"yfinance获取{stock_code}数据失败: {e}")
            return None


# ============== 便捷函数 ==============

def create_adapter(source: str = "auto", fallback: bool = True) -> DataSourceAdapter:
    """创建数据源适配器"""
    return DataSourceAdapter(source, fallback)


# ============== 测试 ==============

if __name__ == '__main__':
    print("=== 测试数据源适配器（优先级模式）===\n")
    
    # 测试自动选择（按优先级）
    adapter = create_adapter("auto")
    
    if adapter.data_source:
        print(f"\n✅ 当前数据源: {adapter.source}")
        print(f"   质量评分: {adapter.get_source_quality()}/5")
        print(f"   可用数据源: {adapter.available_sources}")
        
        # 测试获取单只股票数据
        print("\n--- 测试获取股票数据 (000001) ---")
        df = adapter.get_stock_data('000001', days=30)
        if df is not None:
            print(f"成功获取 {len(df)} 条数据")
            print(df.head())
        else:
            print("获取失败")
    else:
        print("\n❌ 没有可用的数据源")
        print("\n请安装以下数据源之一:")
        print("  pip install akshare    # 推荐，免费")
        print("  pip install tushare    # 需要token，质量最高")
        print("  pip install baostock   # 免费，稳定")
        print("  pip install yfinance   # 有限支持A股")
