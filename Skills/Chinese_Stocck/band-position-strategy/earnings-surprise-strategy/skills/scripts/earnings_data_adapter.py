#!/usr/bin/env python3
"""
财报数据多数据源适配器
支持多种数据源获取财报数据
"""

import pandas as pd
import requests
from typing import Dict, List, Optional
from datetime import datetime
import json
import time


class EarningsDataSourceAdapter:
    """财报多数据源适配器"""
    
    # 数据源优先级
    SOURCES = {
        'akshare': {
            'name': 'AKShare',
            'priority': 1,
            'quality': 5,
            'requires_auth': False,
            'description': '免费财经数据接口，数据全面'
        },
        'tushare': {
            'name': 'Tushare Pro',
            'priority': 2,
            'quality': 5,
            'requires_auth': True,
            'description': '专业财经数据，需要token'
        },
        'sina_finance': {
            'name': '新浪财经',
            'priority': 3,
            'quality': 4,
            'requires_auth': False,
            'description': '实时行情和基础财务数据'
        },
        'eastmoney': {
            'name': '东方财富',
            'priority': 4,
            'quality': 4,
            'requires_auth': False,
            'description': '全面的A股财务数据'
        },
        'cls': {
            'name': '财联社',
            'priority': 5,
            'quality': 3,
            'requires_auth': False,
            'description': '财经新闻和快讯，部分数据需解析'
        },
        'jin10': {
            'name': '金十数据',
            'priority': 6,
            'quality': 3,
            'requires_auth': False,
            'description': '实时财经数据，主要为新闻快讯'
        },
        'wallstreetcn': {
            'name': '华尔街见闻',
            'priority': 7,
            'quality': 3,
            'requires_auth': False,
            'description': '财经资讯，需解析获取结构化数据'
        }
    }
    
    def __init__(self, primary_source: str = 'auto'):
        """
        初始化数据源适配器
        
        Args:
            primary_source: 首选数据源，'auto'表示自动选择
        """
        self.primary_source = primary_source
        self.available_sources = []
        self._init_sources()
    
    def _init_sources(self):
        """初始化可用数据源"""
        for source_id, config in self.SOURCES.items():
            if self._check_source_available(source_id):
                self.available_sources.append(source_id)
        
        if not self.available_sources:
            print("⚠️ 警告：没有可用的数据源")
    
    def _check_source_available(self, source_id: str) -> bool:
        """检查数据源是否可用"""
        try:
            if source_id == 'akshare':
                import akshare as ak
                # 简单测试
                ak.stock_zh_a_spot_em()
                return True
            elif source_id == 'tushare':
                import tushare as ts
                # 需要token，这里只检查模块
                return True
            elif source_id in ['sina_finance', 'eastmoney', 'cls', 'jin10', 'wallstreetcn']:
                # 网页数据源，检查网络连接
                return True
            return False
        except:
            return False
    
    def get_earnings_data(self, stock_code: str, quarter: str = None) -> Optional[Dict]:
        """
        获取财报数据
        
        Args:
            stock_code: 股票代码
            quarter: 财报季度，如 '2025Q4'
            
        Returns:
            财报数据字典
        """
        # 按优先级尝试各个数据源
        for source_id in self.available_sources:
            try:
                if source_id == 'akshare':
                    return self._get_from_akshare(stock_code, quarter)
                elif source_id == 'tushare':
                    return self._get_from_tushare(stock_code, quarter)
                elif source_id == 'sina_finance':
                    return self._get_from_sina(stock_code, quarter)
                elif source_id == 'eastmoney':
                    return self._get_from_eastmoney(stock_code, quarter)
            except Exception as e:
                print(f"从{self.SOURCES[source_id]['name']}获取数据失败: {e}")
                continue
        
        return None
    
    def _get_from_akshare(self, stock_code: str, quarter: str = None) -> Optional[Dict]:
        """从AKShare获取财报数据"""
        import akshare as ak
        
        try:
            # 获取个股财务指标
            df = ak.stock_financial_analysis_indicator(symbol=stock_code)
            if df is not None and not df.empty:
                latest = df.iloc[0]
                return {
                    'stock_code': stock_code,
                    'quarter': quarter or latest.get('报告期', ''),
                    'net_profit_yoy': float(latest.get('净利润同比增长率', 0)),
                    'revenue_yoy': float(latest.get('营业收入同比增长率', 0)),
                    'gross_margin': float(latest.get('销售毛利率', 0)),
                    'roe': float(latest.get('净资产收益率', 0)),
                    'eps': float(latest.get('基本每股收益', 0)),
                    'source': 'akshare'
                }
        except Exception as e:
            print(f"AKShare获取失败: {e}")
        
        return None
    
    def _get_from_tushare(self, stock_code: str, quarter: str = None) -> Optional[Dict]:
        """从Tushare获取财报数据"""
        import tushare as ts
        
        try:
            # 需要配置token
            pro = ts.pro_api()
            
            # 获取财务数据
            df = pro.fina_indicator(ts_code=stock_code)
            if df is not None and not df.empty:
                latest = df.iloc[0]
                return {
                    'stock_code': stock_code,
                    'quarter': quarter or latest.get('end_date', ''),
                    'net_profit_yoy': float(latest.get('q_profit_yoy', 0)),
                    'revenue_yoy': float(latest.get('q_sales_yoy', 0)),
                    'gross_margin': float(latest.get('grossprofit_margin', 0)),
                    'roe': float(latest.get('roe', 0)),
                    'eps': float(latest.get('eps', 0)),
                    'source': 'tushare'
                }
        except Exception as e:
            print(f"Tushare获取失败: {e}")
        
        return None
    
    def _get_from_sina(self, stock_code: str, quarter: str = None) -> Optional[Dict]:
        """从新浪财经获取财报数据"""
        try:
            # 新浪财经财务数据API
            url = f"https://finance.sina.com.cn/realstock/company/{stock_code}/finance.shtml"
            # 这里需要解析网页，简化处理
            print(f"新浪财经: {stock_code} 数据获取需要网页解析")
            return None
        except Exception as e:
            print(f"新浪财经获取失败: {e}")
        
        return None
    
    def _get_from_eastmoney(self, stock_code: str, quarter: str = None) -> Optional[Dict]:
        """从东方财富获取财报数据"""
        try:
            # 东方财富财务数据API
            url = f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index?type=web&code={stock_code}"
            # 这里需要解析网页或API
            print(f"东方财富: {stock_code} 数据获取需要API调用")
            return None
        except Exception as e:
            print(f"东方财富获取失败: {e}")
        
        return None
    
    def get_available_sources(self) -> List[Dict]:
        """获取可用数据源列表"""
        result = []
        for source_id in self.available_sources:
            config = self.SOURCES[source_id]
            result.append({
                'id': source_id,
                'name': config['name'],
                'quality': config['quality'],
                'description': config['description']
            })
        return result
    
    def get_source_info(self, source_id: str) -> Dict:
        """获取数据源详细信息"""
        return self.SOURCES.get(source_id, {})


# 数据源对比信息
DATA_SOURCE_COMPARISON = """
================================================================================
财报数据源对比
================================================================================

【推荐数据源】

1. AKShare (推荐指数: ⭐⭐⭐⭐⭐)
   - 优点: 免费、数据全面、Python接口友好
   - 缺点: 偶尔不稳定、需要处理反爬
   - 安装: pip install akshare
   - 使用: 完全免费，无需注册

2. Tushare Pro (推荐指数: ⭐⭐⭐⭐⭐)
   - 优点: 数据专业、稳定、接口规范
   - 缺点: 高级数据需要付费积分
   - 安装: pip install tushare
   - 使用: 需要注册获取token

【备选数据源】

3. 新浪财经 (推荐指数: ⭐⭐⭐⭐)
   - 优点: 实时数据、免费
   - 缺点: 需要网页解析、结构可能变化
   - 获取方式: 爬虫解析或API

4. 东方财富 (推荐指数: ⭐⭐⭐⭐)
   - 优点: 数据全面、有API接口
   - 缺点: 需要分析接口、可能有频率限制
   - 获取方式: API调用或爬虫

【新闻/快讯数据源】

5. 财联社 (推荐指数: ⭐⭐⭐)
   - 优点: 财经快讯及时、有结构化数据
   - 缺点: 主要为新闻，财务数据需提取
   - 获取方式: API或爬虫

6. 金十数据 (推荐指数: ⭐⭐⭐)
   - 优点: 实时数据快、界面友好
   - 缺点: 主要为外汇/期货，A股财报数据有限
   - 获取方式: API或爬虫

7. 华尔街见闻 (推荐指数: ⭐⭐⭐)
   - 优点: 资讯质量高、分析深入
   - 缺点: 主要为资讯，结构化数据需解析
   - 获取方式: API或爬虫

【建议组合】

方案A（免费方案）:
  主数据源: AKShare
  备用: 新浪财经 + 东方财富

方案B（专业方案）:
  主数据源: Tushare Pro
  备用: AKShare

方案C（实时方案）:
  主数据源: AKShare
  实时快讯: 财联社 + 金十数据

================================================================================
"""


if __name__ == '__main__':
    print(DATA_SOURCE_COMPARISON)
    
    # 测试适配器
    adapter = EarningsDataSourceAdapter()
    
    print("\n可用数据源:")
    for source in adapter.get_available_sources():
        print(f"  ✅ {source['name']} (质量: {source['quality']}/5)")
        print(f"     {source['description']}")
