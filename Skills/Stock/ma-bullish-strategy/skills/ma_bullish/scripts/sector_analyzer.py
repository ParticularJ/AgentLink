#!/usr/bin/env python3
"""
板块分析模块 - 支持按板块分析股票
"""

import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime


class SectorAnalyzer:
    """板块分析器"""
    
    # 预定义板块和成分股
    SECTORS = {
        '科技': ['000938', '000977', '002230', '002236', '002415', '300033', '300059', '600570', '600584', '603019'],
        '医药': ['000538', '000623', '000999', '002001', '002007', '300003', '300015', '600276', '600436', '603259'],
        '金融': ['000001', '000002', '600000', '600016', '600030', '600036', '600837', '601318', '601398', '601628'],
        '消费': ['000568', '000596', '000858', '002304', '600519', '600887', '601012', '601888', '603288', '603899'],
        '新能源': ['002074', '002129', '002202', '002594', '300014', '300124', '600438', '601012', '601727', '603806'],
        '军工': ['000768', '002013', '002179', '300034', '300114', '600038', '600150', '600372', '600893', '600967'],
    }
    
    def __init__(self, ma_analyzer):
        """
        初始化板块分析器
        
        Args:
            ma_analyzer: MABullishAnalyzer 实例
        """
        self.analyzer = ma_analyzer
    
    def get_sector_stocks(self, sector_name: str) -> List[str]:
        """
        获取板块成分股
        
        Args:
            sector_name: 板块名称
            
        Returns:
            股票代码列表
        """
        return self.SECTORS.get(sector_name, [])
    
    def list_sectors(self) -> List[str]:
        """
        列出所有支持的板块
        
        Returns:
            板块名称列表
        """
        return list(self.SECTORS.keys())
    
    def analyze_sector(self, sector_name: str, analysis_date: Optional[str] = None) -> Dict:
        """
        分析指定板块
        
        Args:
            sector_name: 板块名称
            analysis_date: 分析日期，格式 'YYYY-MM-DD'
            
        Returns:
            分析结果
        """
        stocks = self.get_sector_stocks(sector_name)
        if not stocks:
            return {
                'sector': sector_name,
                'error': f'未找到板块: {sector_name}',
                'available_sectors': self.list_sectors()
            }
        
        candidates = []
        errors = []
        
        print(f"分析 {sector_name} 板块 ({len(stocks)} 只股票)...")
        
        for i, stock_code in enumerate(stocks, 1):
            print(f"  [{i}/{len(stocks)}] {stock_code}...", end=' ', flush=True)
            try:
                result = self.analyzer.analyze_stock(stock_code, stock_code, analysis_date=analysis_date)
                if result and result['signal'] == 'BUY' and result['score'] >= 70:
                    candidates.append(result)
                    print(f"✅ 评分{result['score']}")
                else:
                    print("❌")
            except Exception as e:
                errors.append(f"{stock_code}: {str(e)}")
                print(f"⚠️ 错误")
        
        # 按得分排序
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        return {
            'sector': sector_name,
            'analysis_date': analysis_date or datetime.now().strftime('%Y-%m-%d'),
            'total_stocks': len(stocks),
            'candidates': candidates,
            'candidate_count': len(candidates),
            'errors': errors
        }
    
    def analyze_all_sectors(self, analysis_date: Optional[str] = None) -> Dict:
        """
        分析所有板块
        
        Args:
            analysis_date: 分析日期，格式 'YYYY-MM-DD'
            
        Returns:
            所有板块的分析结果
        """
        results = {}
        for sector_name in self.list_sectors():
            print(f"\n{'='*60}")
            print(f"分析板块: {sector_name}")
            print('='*60)
            results[sector_name] = self.analyze_sector(sector_name, analysis_date)
        return results
    
    def generate_sector_report(self, result: Dict) -> str:
        """
        生成板块分析报告
        
        Args:
            result: 板块分析结果
            
        Returns:
            格式化的报告
        """
        lines = []
        lines.append("="*80)
        lines.append(f"【{result['sector']}】板块分析报告")
        lines.append(f"分析日期: {result['analysis_date']}")
        lines.append("="*80)
        lines.append("")
        
        if 'error' in result:
            lines.append(f"错误: {result['error']}")
            lines.append(f"可用板块: {', '.join(result.get('available_sectors', []))}")
            return "\n".join(lines)
        
        lines.append(f"板块股票总数: {result['total_stocks']}")
        lines.append(f"符合条件股票: {result['candidate_count']}")
        lines.append("")
        
        if result['candidates']:
            lines.append("【符合条件的股票】")
            lines.append("-"*80)
            
            for i, stock in enumerate(result['candidates'], 1):
                lines.append(f"\n{i}. {stock['stock_name']}({stock['stock_code']})")
                lines.append(f"   评分: {stock['score']}")
                lines.append(f"   当前价: {stock['current_price']}元")
                lines.append(f"   入场价: {stock['entry_price']}元")
                lines.append(f"   止损价: {stock['stop_loss']}元")
                lines.append(f"   目标价: {stock['target_price']}元")
                lines.append(f"   风险收益比: 1:{stock['risk_reward_ratio']}")
                lines.append(f"   建议: {stock['suggestion']}")
                
                # 详细指标
                details = stock.get('details', {})
                ma = details.get('ma_arrangement', {})
                if ma:
                    lines.append(f"   均线排列: {ma.get('level', 'N/A')}")
                
                volume = details.get('volume_trend', {})
                if volume:
                    lines.append(f"   成交量: {volume.get('trend', 'N/A')}")
        else:
            lines.append("未发现符合条件的股票。")
            lines.append("")
            lines.append("可能原因:")
            lines.append("  - 板块整体处于调整期")
            lines.append("  - 均线多头排列的股票较少")
            lines.append("  - 成交量条件不满足")
        
        if result['errors']:
            lines.append("")
            lines.append("【错误信息】")
            for error in result['errors']:
                lines.append(f"  ⚠️ {error}")
        
        lines.append("")
        lines.append("="*80)
        
        return "\n".join(lines)


# 便捷函数
def analyze_sector(ma_analyzer, sector_name: str, analysis_date: Optional[str] = None) -> Dict:
    """分析指定板块"""
    sector_analyzer = SectorAnalyzer(ma_analyzer)
    return sector_analyzer.analyze_sector(sector_name, analysis_date)


def analyze_all_sectors(ma_analyzer, analysis_date: Optional[str] = None) -> Dict:
    """分析所有板块"""
    sector_analyzer = SectorAnalyzer(ma_analyzer)
    return sector_analyzer.analyze_all_sectors(analysis_date)


if __name__ == '__main__':
    # 测试
    import sys
    sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/ma-bullish-strategy')
    from skills.ma_bullish.scripts.ma_analyzer import MABullishAnalyzer
    
    print("=== 板块分析器测试 ===\n")
    
    analyzer = MABullishAnalyzer(data_source='baostock')
    sector_analyzer = SectorAnalyzer(analyzer)
    
    print("支持的板块:")
    for sector in sector_analyzer.list_sectors():
        print(f"  - {sector}")
    
    print("\n测试分析科技板块:")
    result = sector_analyzer.analyze_sector('科技', analysis_date='2026-04-03')
    print(sector_analyzer.generate_sector_report(result))
