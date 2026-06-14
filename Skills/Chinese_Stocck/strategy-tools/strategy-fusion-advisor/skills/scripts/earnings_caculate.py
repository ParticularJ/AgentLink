#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业绩推荐数据读取和处理模块
用于解析、验证和处理JSON格式的股票业绩推荐数据
"""

import json
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
import os


class EarningsDataProcessor:
    """业绩推荐数据处理器"""
    
    def __init__(self, base_dir: str = None):
        self.data = None
        self.stocks = []
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.earnings_analysis_dir = os.path.join(self.base_dir, 'stock_earnings_analysis')
        
    def load_from_json(self, json_data: Dict[str, Any]) -> bool:
        """
        从JSON数据加载推荐信息
        
        Args:
            json_data: 包含推荐数据的字典
            
        Returns:
            bool: 加载是否成功
        """
        try:
            self.data = json_data
            self.stocks = json_data.get('stocks', [])
            print(f"✓ 成功加载 {len(self.stocks)} 只股票推荐数据")
            return True
        except Exception as e:
            print(f"✗ 加载JSON数据失败: {e}")
            return False
    
    def load_from_json_string(self, json_string: str) -> bool:
        """
        从JSON字符串加载推荐信息
        
        Args:
            json_string: JSON格式的字符串
            
        Returns:
            bool: 加载是否成功
        """
        try:
            json_data = json.loads(json_string)
            return self.load_from_json(json_data)
        except json.JSONDecodeError as e:
            print(f"✗ JSON解析失败: {e}")
            return False
    
    def load_from_file(self, file_path: str) -> bool:
        """
        从JSON文件加载推荐信息
        
        Args:
            file_path: JSON文件路径
            
        Returns:
            bool: 加载是否成功
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            return self.load_from_json(json_data)
        except FileNotFoundError:
            print(f"✗ 文件未找到: {file_path}")
            return False
        except json.JSONDecodeError as e:
            print(f"✗ JSON解析失败: {e}")
            return False
    
    def validate_stock_data(self, stock: Dict) -> bool:
        """
        验证单只股票的推荐数据完整性
        
        Args:
            stock: 股票推荐数据字典
            
        Returns:
            bool: 数据是否有效
        """
        required_fields = ['stock_code', 'stock_name', 'signal', 'score']
        for field in required_fields:
            if field not in stock:
                print(f"  ⚠ 缺少必要字段: {field}")
                return False
        return True
    
    def validate_all(self) -> bool:
        """验证所有股票数据的完整性"""
        if not self.stocks:
            print("✗ 没有股票数据可验证")
            return False
        
        print(f"\n📊 验证 {len(self.stocks)} 只股票数据:")
        valid_count = 0
        for i, stock in enumerate(self.stocks, 1):
            code = stock.get('stock_code', f'Unknown-{i}')
            name = stock.get('stock_name', '')
            if self.validate_stock_data(stock):
                valid_count += 1
               # print(f"  ✓ [{code}] {name}")
            else:
                print(f"  ✗ [{code}] {name} - 数据不完整")
        
        print(f"\n✓ 数据验证完成: {valid_count}/{len(self.stocks)} 有效")
        return valid_count == len(self.stocks)
    
    def get_stock_by_code(self, stock_code: str) -> Optional[Dict]:
        """根据股票代码获取推荐数据"""
        for stock in self.stocks:
            if stock.get('stock_code') == stock_code:
                return stock
        return None
    
    def get_buy_signals(self) -> List[Dict]:
        """获取所有BUY信号的股票"""
        return [s for s in self.stocks if s.get('signal') == 'BUY']
    
    def get_top_stocks(self, top_n: int = 5, sort_by: str = 'score') -> List[Dict]:
        """
        获取Top N的股票推荐
        
        Args:
            top_n: 返回数量
            sort_by: 排序字段 ('score', 'surprise_pct' 等)
            
        Returns:
            List[Dict]: 排序后的股票列表
        """
        sorted_stocks = sorted(
            self.stocks,
            key=lambda x: x.get(sort_by, 0),
            reverse=True
        )
        return sorted_stocks[:top_n]
    
    def load_from_latest_earnings_analysis(self) -> bool:
        """
        从stock_earnings_analysis目录加载最新的业绩分析文件
        
        Returns:
            bool: 加载是否成功
        """
        try:
            if not os.path.exists(self.earnings_analysis_dir):
                print(f"✗ 目录不存在: {self.earnings_analysis_dir}")
                return False
            
            # 获取所有JSON文件
            files = [f for f in os.listdir(self.earnings_analysis_dir) 
                     if f.startswith('stock_earnings_analysis_') and f.endswith('.json')]
            
            if not files:
                print(f"✗ {self.earnings_analysis_dir} 目录中找不到业绩分析文件")
                return False
            
            # 按文件名排序，获取最新的文件
            latest_file = sorted(files)[-1]
            latest_path = os.path.join(self.earnings_analysis_dir, latest_file)
            
            print(f"📂 从最新文件加载数据: {latest_file}")
            return self.load_from_file(latest_path)
        except Exception as e:
            print(f"✗ 加载最新业绩分析文件失败: {e}")
            return False
    
    def get_underperforming_stocks(self) -> List[Dict]:
        """
        获取财报不及预期的股票
        
        Returns:
            List[Dict]: 不及预期的股票列表
        """
        underperforming = []
        for stock in self.stocks:
            surprise = stock.get('surprise_analysis', {})
            level = surprise.get('level', '')
            # 不及预期的分类
            if level == '不及预期':
                underperforming.append(stock)
        return underperforming
    
    def get_stocks_by_surprise_level(self, level: str) -> List[Dict]:
        """
        按超预期等级获取股票
        
        Args:
            level: 超预期等级 ('显著超预期', '超预期', '小幅超预期', '符合预期', '不及预期')
            
        Returns:
            List[Dict]: 匹配的股票列表
        """
        result = []
        for stock in self.stocks:
            surprise = stock.get('surprise_analysis', {})
            surprise_level = surprise.get('level', '')
            if surprise_level == level:
                result.append(stock)
        return result
    
    def print_surprise_statistics(self):
        """打印业绩预期分类统计"""
        surprise_levels = {}
        
        for stock in self.stocks:
            surprise = stock.get('surprise_analysis', {})
            level = surprise.get('level', 'Unknown')
            if level not in surprise_levels:
                surprise_levels[level] = []
            surprise_levels[level].append(stock)
        
        print("\n" + "="*60)
        print("📊 业绩预期分类统计")
        print("="*60)
        
        for level in sorted(surprise_levels.keys()):
            count = len(surprise_levels[level])
            percentage = (count / len(self.stocks)) * 100 if self.stocks else 0
            print(f"\n{level}: {count}只 ({percentage:.1f}%)")
    
    def print_summary(self):
        """打印推荐数据摘要"""
        if not self.data:
            print("✗ 没有加载任何数据")
            return
        
        print("\n" + "="*60)
        print("📈 业绩推荐数据摘要")
        print("="*60)
        
        # 基础信息
        save_time = self.data.get('save_time', 'N/A')
        count = self.data.get('count', 0)
        print(f"\n⏰ 保存时间: {save_time}")
        print(f"📊 推荐总数: {count}")
        
        # 信号分布
        buy_signals = self.get_buy_signals()
        print(f"🟢 BUY信号: {len(buy_signals)}")
        
        # Top 5
        print(f"\n🏆 Top 5 推荐股票 (按分数排序):")
        top_stocks = self.get_top_stocks(5)
        for i, stock in enumerate(top_stocks, 1):
            code = stock.get('stock_code', 'N/A')
            name = stock.get('stock_name', 'N/A')
            score = stock.get('score', 0)
            signal = stock.get('signal', 'N/A')
            print(f"  {i}. [{code}] {name}")
            print(f"     信号: {signal} | 分数: {score:.2f}")
            
            # 推荐信息
            rec = stock.get('recommendation', {})
            if rec:
                action = rec.get('action', '')
                target = rec.get('target', '')
                print(f"     推荐: {action} | 目标: {target}")
            print()
    
    def print_detail(self, stock_code: str):
        """打印单只股票的详细信息"""
        stock = self.get_stock_by_code(stock_code)
        if not stock:
            print(f"✗ 未找到股票: {stock_code}")
            return
        
        print("\n" + "="*60)
        print(f"📊 {stock.get('stock_name')} ({stock_code}) 详细信息")
        print("="*60)
        
        # 基础信息
        print(f"\n基础信息:")
        print(f"  股票代码: {stock.get('stock_code')}")
        print(f"  股票名称: {stock.get('stock_name')}")
        print(f"  季度: {stock.get('quarter', 'N/A')}")
        print(f"  信号: {stock.get('signal')}")
        print(f"  评分: {stock.get('score')}")
        
        # 业绩超预期分析
        print(f"\n业绩超预期分析:")
        surprise = stock.get('surprise_analysis', {})
        if surprise:
            print(f"  等级: {surprise.get('level', 'N/A')}")
            print(f"  分数: {surprise.get('score', 0)}")
            
            # 净利润
            np_data = surprise.get('net_profit', {})
            if np_data:
                print(f"  净利润增速: {np_data.get('actual_yoy', 0):.2f}% (预期: {np_data.get('expected_yoy', 0):.2f}%)")
                print(f"  超预期幅度: {np_data.get('surprise_pct', 0):.2f}%")
            
            # 营收
            rev_data = surprise.get('revenue', {})
            if rev_data:
                print(f"  营收增速: {rev_data.get('actual_yoy', 0):.2f}% (预期: {rev_data.get('expected_yoy', 0):.2f}%)")
                print(f"  超预期幅度: {rev_data.get('surprise_pct', 0):.2f}%")
        
        # 增长质量分析
        print(f"\n增长质量分析:")
        quality = stock.get('quality_analysis', {})
        if quality:
            print(f"  等级: {quality.get('level', 'N/A')}")
            print(f"  分数: {quality.get('score', 0)}")
            
            margin = quality.get('margin_trend', {})
            if margin:
                print(f"  毛利率: {margin.get('current_margin', 0):.2f}%")
                print(f"  毛利率变化: {margin.get('margin_change', 0):.2f}%")
        
        # 市场反应分析
        print(f"\n市场反应分析:")
        market = stock.get('market_analysis', {})
        if market:
            print(f"  等级: {market.get('level', 'N/A')}")
            details = market.get('details', {})
            if details:
                print(f"  公告日涨幅: {details.get('announcement_return', 0):.2f}%")
                print(f"  3日涨幅: {details.get('three_day_return', 0):.2f}%")
                print(f"  成交量变化: {details.get('volume_change', 0):.2f}%")
        
        # 机构态度分析
        print(f"\n机构态度分析:")
        inst = stock.get('institutional_analysis', {})
        if inst:
            print(f"  等级: {inst.get('level', 'N/A')}")
            print(f"  升级评级: {inst.get('upgrades', 0)}")
            print(f"  降级评级: {inst.get('downgrades', 0)}")
            print(f"  目标上升空间: {inst.get('target_upside', 0):.2f}%")
        
        # 行业分析
        print(f"\n行业分析:")
        industry = stock.get('industry_analysis', {})
        if industry:
            print(f"  等级: {industry.get('level', 'N/A')}")
            print(f"  表现: {industry.get('performance', 0):.2f}%")
        
        # 推荐信息
        print(f"\n推荐信息:")
        rec = stock.get('recommendation', {})
        if rec:
            print(f"  推荐: {rec.get('action', 'N/A')}")
            print(f"  紧急程度: {rec.get('urgency', 'N/A')}")
            print(f"  入场方式: {rec.get('entry_method', 'N/A')}")
            print(f"  建议仓位: {rec.get('suggested_position', 'N/A')}")
            print(f"  止损: {rec.get('stop_loss', 'N/A')}")
            print(f"  目标: {rec.get('target', 'N/A')}")
            print(f"  持仓周期: {rec.get('holding_period', 'N/A')}")
        
        print(f"\n分析时间: {stock.get('analysis_time', 'N/A')}")
        print("="*60 + "\n")
    
    def export_to_file(self, output_path: str) -> bool:
        """
        导出推荐数据到JSON文件
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            bool: 导出是否成功
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            print(f"✓ 数据已导出到: {output_path}")
            return True
        except Exception as e:
            print(f"✗ 导出失败: {e}")
            return False


def get_dangerous_stocks() -> List[Dict]:
    """主函数 - 演示如何使用EarningsDataProcessor"""
    
    # 创建处理器实例
    processor = EarningsDataProcessor()
    
    # 加载最新的业绩分析数据
    print("📥 从stock_earnings_analysis加载最新数据...\n")
    if processor.load_from_latest_earnings_analysis():
        # 验证数据
        processor.validate_all()
        
        # 打印摘要
        #processor.print_summary()
        
        # 打印超预期分类统计
        #processor.print_surprise_statistics()
        
        # 获取不及预期的股票
        print("\n" + "="*60)
        print("📉 财报不及预期的股票详情")
        print("="*60)
        underperforming = processor.get_underperforming_stocks()
        print(f"\n总数: {len(underperforming)} 只\n")
        stock_codes = []
        stock_names = []
        if underperforming:
            for i, stock in enumerate(underperforming, 1):
                code = stock.get('stock_code', 'N/A')
                name = stock.get('stock_name', 'N/A')
                stock_codes.append(code)
                stock_names.append(name)
                score = stock.get('score', 0)
                signal = stock.get('signal', 'N/A')
                surprise = stock.get('surprise_analysis', {})
                
                #print(f"{i}. [{code}] {name}")
                #print(f"   信号: {signal} | 分数: {score:.2f}")
                
                # 不及预期的具体数据
                np_data = surprise.get('net_profit', {})
                if np_data:
                    actual = np_data.get('actual_yoy', 0)
                    expected = np_data.get('expected_yoy', 0)
                    #print(f"   净利润: {actual:.2f}% (预期: {expected:.2f}%)")
                
                rev_data = surprise.get('revenue', {})
                if rev_data:
                    actual = rev_data.get('actual_yoy', 0)
                    expected = rev_data.get('expected_yoy', 0)
                    #print(f"   营收: {actual:.2f}% (预期: {expected:.2f}%)")
                print()
    return [
        {
            'stock_code': code,
            'stock_name': name
        }
        for code, name in zip(stock_codes, stock_names)
    ]

if __name__ == '__main__':
    stockinfo = get_dangerous_stocks()
    print("财报不及预期的股票列表: ", stockinfo)
