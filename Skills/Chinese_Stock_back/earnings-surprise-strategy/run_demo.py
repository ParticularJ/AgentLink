#!/usr/bin/env python3
"""
财报超预期策略 - 完整演示
"""

import sys
sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/earnings-surprise-strategy/skills/scripts')

from surprise_analyzer import SurpriseAnalyzer
from quality_analyzer import QualityAnalyzer
from market_analyzer import MarketReactionAnalyzer
from risk_assessor import RiskAssessor
from datetime import datetime

def analyze_stock(stock_code, stock_name, earnings_data):
    """分析单只股票"""
    # 创建分析器
    surprise = SurpriseAnalyzer()
    quality = QualityAnalyzer()
    market = MarketReactionAnalyzer()
    risk = RiskAssessor()
    
    # 1. 超预期分析
    surprise_result = surprise.analyze(earnings_data)
    
    # 2. 质量分析
    try:
        quality_result = quality.analyze(stock_code, earnings_data)
    except:
        quality_result = {'score': 70, 'level': '良好增长'}
    
    # 3. 市场反应分析
    market_result = market.analyze(stock_code, earnings_data.get('announce_date', ''))
    
    # 4. 风险评估
    stock_data = {
        'current_price': earnings_data.get('current_price', 100),
        'market_cap': earnings_data.get('market_cap', 1000),
        'avg_volume': earnings_data.get('avg_volume', 1000000),
        'volatility': 0.25
    }
    risk_result = risk.assess(stock_data)
    
    # 计算综合得分
    total_score = (
        surprise_result['surprise_score'] * 0.30 +
        quality_result['score'] * 0.25 +
        market_result['reaction_score'] * 0.20 +
        75 * 0.15 +  # 机构态度（模拟）
        80 * 0.10    # 行业景气度（模拟）
    )
    
    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'quarter': earnings_data.get('quarter', ''),
        'total_score': round(total_score, 2),
        'surprise_result': surprise_result,
        'quality_result': quality_result,
        'market_result': market_result,
        'risk_result': risk_result,
        'net_profit_yoy': earnings_data.get('net_profit_yoy', 0),
        'revenue_yoy': earnings_data.get('revenue_yoy', 0),
        'eps_surprise': earnings_data.get('eps_surprise', 0)
    }


def main():
    print('='*80)
    print('财报超预期策略 - 2026年一季度财报分析')
    print('='*80)
    print(f'分析时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()
    
    # 模拟2026年一季度财报数据
    stocks_data = [
        {
            'stock_code': '600519',
            'stock_name': '贵州茅台',
            'quarter': '2026Q1',
            'announce_date': '2026-04-25',
            'net_profit_yoy': 35.2,
            'revenue_yoy': 28.5,
            'eps_surprise': 18.5,
            'gross_margin': 92.1,
            'roe': 28.5,
            'current_price': 1700,
            'market_cap': 2100
        },
        {
            'stock_code': '002594',
            'stock_name': '比亚迪',
            'quarter': '2026Q1',
            'announce_date': '2026-04-28',
            'net_profit_yoy': 45.6,
            'revenue_yoy': 38.9,
            'eps_surprise': 25.3,
            'gross_margin': 21.8,
            'roe': 18.5,
            'current_price': 280,
            'market_cap': 800
        },
        {
            'stock_code': '300750',
            'stock_name': '宁德时代',
            'quarter': '2026Q1',
            'announce_date': '2026-04-22',
            'net_profit_yoy': 52.3,
            'revenue_yoy': 42.1,
            'eps_surprise': 32.1,
            'gross_margin': 26.5,
            'roe': 22.8,
            'current_price': 220,
            'market_cap': 950
        },
        {
            'stock_code': '000001',
            'stock_name': '平安银行',
            'quarter': '2026Q1',
            'announce_date': '2026-04-20',
            'net_profit_yoy': 22.8,
            'revenue_yoy': 15.3,
            'eps_surprise': 8.2,
            'gross_margin': 45.2,
            'roe': 12.1,
            'current_price': 12,
            'market_cap': 2300
        },
        {
            'stock_code': '000858',
            'stock_name': '五粮液',
            'quarter': '2026Q1',
            'announce_date': '2026-04-23',
            'net_profit_yoy': 28.5,
            'revenue_yoy': 22.1,
            'eps_surprise': 15.8,
            'gross_margin': 75.2,
            'roe': 24.5,
            'current_price': 165,
            'market_cap': 650
        }
    ]
    
    # 分析所有股票
    results = []
    print('正在分析...')
    print()
    
    for data in stocks_data:
        print(f'  分析 {data["stock_name"]} ({data["stock_code"]})...')
        result = analyze_stock(data['stock_code'], data['stock_name'], data)
        results.append(result)
    
    # 按得分排序
    results.sort(key=lambda x: x['total_score'], reverse=True)
    
    # 统计
    strong_buy = sum(1 for r in results if r['total_score'] >= 75)
    buy = sum(1 for r in results if 70 <= r['total_score'] < 75)
    watch = sum(1 for r in results if 60 <= r['total_score'] < 70)
    
    print()
    print('='*80)
    print('2026年一季度财报超预期分析结果')
    print('='*80)
    print()
    print(f'统计: 强烈推荐(≥75分): {strong_buy}只 | 推荐(70-74分): {buy}只 | 关注(60-69分): {watch}只')
    print()
    
    # 显示结果
    print('【分析结果】')
    print('-'*80)
    
    surprise_analyzer = SurpriseAnalyzer()
    risk_assessor = RiskAssessor()
    
    for i, r in enumerate(results, 1):
        if r['total_score'] >= 75:
            signal = '强烈推荐'
            emoji = '🔥'
        elif r['total_score'] >= 70:
            signal = '推荐'
            emoji = '✅'
        elif r['total_score'] >= 60:
            signal = '关注'
            emoji = '👀'
        else:
            signal = '观望'
            emoji = '❌'
        
        print(f'{emoji} {i}. {r["stock_name"]} ({r["stock_code"]})')
        print(f'   综合得分: {r["total_score"]}分 | 信号: {signal}')
        print(f'   业绩: 净利润+{r["net_profit_yoy"]}% | 营收+{r["revenue_yoy"]}% | EPS超预期+{r["eps_surprise"]}%')
        print(f'   超预期: {surprise_analyzer.get_surprise_level_name(r["surprise_result"]["surprise_level"])} ({r["surprise_result"]["surprise_score"]}分)')
        print(f'   质量: {r["quality_result"]["level"]} ({r["quality_result"]["score"]}分)')
        print(f'   风险: {risk_assessor.get_risk_level_name(r["risk_result"]["risk_level"])}')
        print(f'   建议仓位: {r["risk_result"]["suggested_position"]*100:.0f}%')
        print()
    
    print('='*80)
    print('分析完成')
    print('注意：以上数据为模拟数据，实际分析需要连接akshare获取真实财报数据')
    print('='*80)


if __name__ == '__main__':
    main()
