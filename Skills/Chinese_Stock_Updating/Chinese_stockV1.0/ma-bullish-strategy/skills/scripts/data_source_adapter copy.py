# A股数据源适配器
# 支持多个数据源：tushare > pytdx > akshare > baostock > yfinance
# 新增：pytdx 通达信数据源（无风控、无报错、极速稳定）

import pandas as pd
import numpy as np
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import os
import time

class DataSourceAdapter:
    """A股多数据源适配器 - 支持优先级自动切换 + 新增 pytdx"""
    
    # 数据源优先级（质量从高到低）
    PRIORITY = ["tushare", "pytdx", "akshare", "baostock", "yfinance"]
    
    # 数据源质量评分
    QUALITY_SCORE = {
        "tushare": 5,      # 数据最全面、稳定，但需要token
        "pytdx": 4.8,      # 【新增】通达信数据源，极速、无风控、免费、稳定
        "akshare": 4,      # 免费，数据丰富，偶尔不稳定
        "baostock": 3,     # 免费，数据稳定，但获取较慢
        "yfinance": 2      # 有限支持A股
    }
    
    def __init__(self, source: str = "pytdx", fallback: bool = True):
        self.source = source
        self.fallback = fallback
        self.data_source = None
        self.available_sources = []
        self.current_source_index = 0
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
        try:
            if source == "akshare":
                import akshare as ak
                self.data_source = ak
                if not silent:
                    print(f"✅ 使用数据源: akshare (质量评分: {self.QUALITY_SCORE['akshare']}/5)")
                return True

            elif source == "tushare":
                import tushare as ts
                token = ""  # 在这里填入你的 token
                if not token:
                    return False
                pro = ts.pro_api(token)
                self.data_source = pro
                if not silent:
                    print(f"✅ 使用数据源: tushare (质量评分: {self.QUALITY_SCORE['tushare']}/5)")
                return True

            elif source == "baostock":
                import baostock as bs
                bs.login()
                self.data_source = bs
                if not silent:
                    print(f"✅ 使用数据源: baostock (质量评分: {self.QUALITY_SCORE['baostock']}/5)")
                return True

            elif source == "yfinance":
                import yfinance as yf
                self.data_source = yf
                if not silent:
                    print(f"✅ 使用数据源: yfinance (质量评分: {self.QUALITY_SCORE['yfinance']}/5)")
                return True

            # ===================== 【新增】pytdx 通达信数据源 =====================
            elif source == "pytdx":
                from pytdx.hq import TdxHq_API
                self.data_source = TdxHq_API()
                if not silent:
                    print(f"✅ 使用数据源: pytdx (质量评分: {self.QUALITY_SCORE['pytdx']}/5)")
                return True

        except Exception:
            return False
        return False
    
    def switch_to_next_source(self) -> bool:
        if len(self.available_sources) <= 1:
            print("❌ 没有其他可用数据源")
            return False
        
        self.current_source_index = (self.current_source_index + 1) % len(self.available_sources)
        next_source = self.available_sources[self.current_source_index]
        print(f"🔄 切换到备用数据源: {next_source}")
        return self._try_init_source(next_source)
    
    def get_source_quality(self) -> int:
        return self.QUALITY_SCORE.get(self.source, 0)
    
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        max_retries = len(self.available_sources) if self.fallback else 1
        for attempt in range(max_retries):
            try:
                if self.source == "akshare":
                    return self._akshare_stock_list()
                elif self.source == "tushare":
                    return self._tushare_stock_list()
                elif self.source == "baostock":
                    return self._baostock_stock_list()
                elif self.source == "pytdx":
                    return self._pytdx_stock_list()
            except Exception as e:
                if self.fallback:
                    self.switch_to_next_source()
                continue
        return None
    
    def get_stock_data(self, stock_code: str, 
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None,
                       max_retries: int = 3) -> Optional[pd.DataFrame]:
        for attempt in range(max_retries):
            try:
                if self.source == "akshare":
                    return self._akshare_stock_data(stock_code, start_date, end_date)
                elif self.source == "tushare":
                    return self._tushare_stock_data(stock_code, start_date, end_date)
                elif self.source == "baostock":
                    return self._baostock_stock_data(stock_code, start_date, end_date)
                elif self.source == "pytdx":
                    return self._pytdx_stock_data(stock_code)
                elif self.source == "yfinance":
                    return self._yfinance_stock_data(stock_code, start_date, end_date)
            except Exception as e:
                print(f"⚠️ {self.source} 获取{stock_code} 失败，重试 {attempt+1}/{max_retries}")
                time.sleep(1)
                continue
        return None
    
    # ============== akshare ==============
    def _akshare_stock_list(self):
        df = self.data_source.stock_zh_a_spot_em()
        return df[['代码', '名称']].rename(columns={'代码': 'code', '名称': 'name'})

    def _akshare_stock_data(self, stock_code, start_date, end_date):
        if not end_date: end_date = datetime.now()
        else: end_date = datetime.strptime(end_date, '%Y-%m-%d')
        if not start_date: start_date = end_date - timedelta(days=180)
        else: start_date = datetime.strptime(start_date, '%Y-%m-%d')
        
        df = self.data_source.stock_zh_a_hist(symbol=stock_code, period="daily",
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'), adjust="qfq")
        df.columns = ['date','open','close','high','low','volume','amount','amplitude','pct_change','change','turnover']
        df['date'] = pd.to_datetime(df['date'])
        return df

    # ============== tushare ==============
    def _tushare_stock_list(self):
        df = self.data_source.stock_basic(exchange='', list_status='L')
        return df[['ts_code','name','symbol']].rename(columns={'symbol':'code'})

    def _tushare_stock_data(self, stock_code, start_date, end_date):
        if not end_date: end_date = datetime.now().strftime('%Y%m%d')
        else: end_date = datetime.strptime(end_date, '%Y-%m-%d').strftime('%Y%m%d')
        if not start_date: start_date = (datetime.now()-timedelta(days=180)).strftime('%Y%m%d')
        else: start_date = datetime.strptime(start_date, '%Y-%m-%d').strftime('%Y%m%d')
        
        ts_code = f"{stock_code}.SH" if stock_code.startswith('6') else f"{stock_code}.SZ"
        df = self.data_source.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        df = df.sort_values('trade_date')
        df['date'] = pd.to_datetime(df['trade_date'])
        df['volume'] = df['vol']*100
        return df[['date','open','close','high','low','volume','amount','pct_change']]

    # ============== baostock ==============
    def _baostock_stock_list(self):
        today = datetime.now()
        if today.weekday()>=5: today=today-timedelta(days=today.weekday()-4)
        rs = self.data_source.query_all_stock(day=today.strftime('%Y-%m-%d'))
        data=[]
        while rs.next(): data.append(rs.get_row_data())
        df=pd.DataFrame(data,columns=rs.fields)
        df['code']=df['code'].str.extract(r'\.(\d{6})$')[0]
        df['name']=df['code']
        return df[['code','name']].dropna()

    def _baostock_stock_data(self,stock_code,start_date,end_date):
        if not end_date: end_date=datetime.now().strftime('%Y-%m-%d')
        if not start_date: start_date=(datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d')
        bs_code=f"sh.{stock_code}" if stock_code.startswith('6') else f"sz.{stock_code}"
        rs=self.data_source.query_history_k_data_plus(bs_code,
            "date,open,high,low,close,volume,amount,pctChg",
            start_date=start_date,end_date=end_date,frequency="d",adjustflag="3")
        data=[]
        while rs.next(): data.append(rs.get_row_data())
        df=pd.DataFrame(data,columns=['date','open','high','low','close','volume','amount','pct_change'])
        df['date']=pd.to_datetime(df['date'])
        for c in ['open','high','low','close','volume','amount','pct_change']:
            df[c]=pd.to_numeric(df[c],errors='coerce')
        return df

    # ============== 【新增】pytdx 通达信实现 ==============
    def _pytdx_stock_list(self):
        api = self.data_source
        if api.connect('113.105.167.39', 7709):
            stocks = api.get_stock_list()
            api.disconnect()
            df = api.to_df(stocks)
            df = df[['code', 'name']]
            return df
        return None

    def _pytdx_stock_data(self, stock_code):
        api = self.data_source
        market = 1 if stock_code.startswith('6') else 0
        
        servers = [
           # ('113.105.167.39', 7709),
           # ('119.147.171.116', 7709),
           ('218.75.126.9', 7709)
        ]
        
        for host, port in servers:
            if api.connect(host, port):
                data = api.get_security_bars(9, market, stock_code, 0, 35)
                api.disconnect()
                df = api.to_df(data)
                df = df.rename(columns={'datetime':'date','vol':'volume'})
                df['date'] = pd.to_datetime(df['date'])
                df['amount'] = df['close'] * df['volume']
                df['pct_change'] = df['close'].pct_change() * 100
                return df[['date','open','close','high','low','volume','amount','pct_change']]
        return None

    # ============== yfinance ==============
    def _yfinance_stock_list(self):
        print("⚠️ yfinance 不支持股票列表")
        return None

    def _yfinance_stock_data(self, stock_code, start_date, end_date):
        yf_code = f"{stock_code}.SS" if stock_code.startswith('6') else f"{stock_code}.SZ"
        ticker = self.data_source.Ticker(yf_code)
        df = ticker.history(start=start_date, end=end_date)
        df = df.reset_index()
        df['amount'] = df['close'] * df['volume']
        df['pct_change'] = df['close'].pct_change() * 100
        return df[['date','open','close','high','low','volume','amount','pct_change']]


def create_adapter(source="auto", fallback=True):
    return DataSourceAdapter(source, fallback)


if __name__ == '__main__':
    print("=== 测试数据源适配器（已添加 pytdx）===\n")
    
    # 自动选择最优数据源
    adapter = create_adapter("pytdx")
    
    if adapter.data_source:
        print(f"✅ 当前数据源: {adapter.source}")
        print(f"✅ 质量评分: {adapter.get_source_quality()}/5")
        
        print("\n--- 测试获取股票 000001 ---")
        df = adapter.get_stock_data("000001")
        if df is not None:
            print(f"成功获取 {len(df)} 条数据")
            print(df.head())
        else:
            print("获取失败")
    else:
        print("❌ 无可用数据源")
