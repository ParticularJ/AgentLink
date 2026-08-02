# earnings-surprise-strategy/skills/scripts/report_generator.py

from datetime import datetime
from typing import Dict, List
import json

class EarningsReportGenerator:
    """财报超预期报告生成器"""
    
    def generate_scan_report(self, results: List[Dict], top_n: int = 10) -> str:
        """生成扫描报告"""
        if not results:
            return self._generate_empty_report()
        
        report = []
        report.append("=" * 80)
        report.append(f"财报超预期策略扫描报告")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"发现标的: {len(results)}只")
        report.append("=" * 80)
        
        # Top N 详情
        report.append(f"\n【Top {min(top_n, len(results))} 推荐标的】")
        report.append("-" * 80)
        
        for i, stock in enumerate(results[:top_n], 1):
            report.append(f"\n{i}. {stock['stock_name']}({stock['stock_code']})")
            report.append(f"   财报季度: {stock.get('quarter', 'N/A')}")
            report.append(f"   综合得分: {stock['score']}分")
            report.append(f"   信号: {stock['signal']}")
            
            surprise = stock.get('surprise_analysis', {})
            report.append(f"   超预期: {surprise.get('level', 'N/A')}")
            
            market = stock.get('market_analysis', {})
            report.append(f"   市场反应: {market.get('level', 'N/A')}")
            
            rec = stock.get('recommendation', {})
            report.append(f"   建议: {rec.get('action', 'N/A')}")
            report.append(f"   仓位: {rec.get('suggested_position', 'N/A')}")
        
        # 统计摘要
        report.append("\n" + "=" * 80)
        report.append("【统计摘要】")
        
        strong = len([s for s in results if s['score'] >= 85])
        recommend = len([s for s in results if 75 <= s['score'] < 85])
        watch = len([s for s in results if 70 <= s['score'] < 75])
        
        report.append(f"  强烈推荐(≥85分): {strong}只")
        report.append(f"  推荐(75-84分): {recommend}只")
        report.append(f"  关注(70-74分): {watch}只")
        report.append(f"  平均得分: {sum(s['score'] for s in results)/len(results):.1f}分")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def generate_stock_report(self, analysis: Dict) -> str:
        """生成单只股票分析报告"""
        if not analysis or 'error' in analysis:
            return f"分析失败: {analysis.get('error', '未知错误')}"
        
        report = []
        report.append("=" * 80)
        report.append(f"【{analysis['stock_name']}】({analysis['stock_code']}) 财报超预期分析报告")
        report.append("=" * 80)
        
        # 核心结论
        report.append(f"\n【核心结论】")
        report.append(f"  财报季度: {analysis.get('quarter', 'N/A')}")
        report.append(f"  综合评分: {analysis.get('score', 0)}/100分")
        report.append(f"  信号类型: {analysis.get('signal', 'N/A')}")
        
        rec = analysis.get('recommendation', {})
        report.append(f"  操作建议: {rec.get('action', 'N/A')}")
        report.append(f"  建议仓位: {rec.get('suggested_position', 'N/A')}")
        
        # 超预期分析
        surprise = analysis.get('surprise_analysis', {})
        report.append(f"\n【超预期分析】")
        report.append(f"  评级: {surprise.get('level', 'N/A')}")
        
        net_profit = surprise.get('net_profit', {})
        report.append(f"  净利润: 同比增长{net_profit.get('actual_yoy', 0):.1f}%")
        if net_profit.get('is_surprise'):
            report.append(f"    超预期{net_profit.get('surprise_pct', 0):.1f}%")
        
        revenue = surprise.get('revenue', {})
        report.append(f"  营业收入: 同比增长{revenue.get('actual_yoy', 0):.1f}%")
        if revenue.get('is_surprise'):
            report.append(f"    超预期{revenue.get('surprise_pct', 0):.1f}%")
        
        # 增长质量
        quality = analysis.get('quality_analysis', {})
        report.append(f"\n【增长质量】")
        report.append(f"  评级: {quality.get('level', 'N/A')}")
        
        sustainability = quality.get('sustainability', {})
        report.append(f"  可持续性: {sustainability.get('level', 'N/A')}")
        
        cash_flow = quality.get('cash_flow_quality', {})
        report.append(f"  现金流: {cash_flow.get('level', 'N/A')}")
        
        # 市场反应
        market = analysis.get('market_analysis', {})
        report.append(f"\n【市场反应】")
        report.append(f"  评级: {market.get('level', 'N/A')}")
        
        price = market.get('price_performance', {})
        report.append(f"  股价表现: {price.get('level', 'N/A')} ({price.get('performance', 0):.1f}%)")
        
        volume = market.get('volume_reaction', {})
        report.append(f"  成交量: {volume.get('level', 'N/A')} (放量{volume.get('volume_ratio', 1):.1f}倍)")
        
        # 风险评估
        risks = analysis.get('risks', [])
        if risks:
            report.append(f"\n【风险评估】")
            for risk in risks:
                report.append(f"  ⚠ {risk['type']}: {risk['description']}")
        else:
            report.append(f"\n【风险评估】")
            report.append(f"  无明显风险")
        
        # 操作建议
        report.append(f"\n【操作建议】")
        report.append(f"  买入时机: {rec.get('urgency', 'N/A')}")
        report.append(f"  买入方式: {rec.get('entry_method', 'N/A')}")
        report.append(f"  止损设置: {rec.get('stop_loss', 'N/A')}")
        report.append(f"  目标收益: {rec.get('target', 'N/A')}")
        report.append(f"  持仓周期: {rec.get('holding_period', 'N/A')}")
        
        report.append("\n" + "=" * 80)
        report.append(f"报告生成时间: {analysis.get('analysis_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}")
        report.append("免责声明: 本报告仅供参考，不构成投资建议。")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def generate_json_report(self, data: Dict) -> str:
        """生成JSON格式报告"""
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _generate_empty_report(self) -> str:
        """生成空报告"""
        return f"""
{'='*80}
财报超预期策略扫描报告
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*80}

【结果】
今日未发现符合条件的财报超预期股票。

【可能原因】
1. 非财报披露高峰期
2. 今日发布的财报超预期不明显
3. 筛选条件较严格

【建议】
1. 查看最近一周的财报数据
2. 适当放宽超预期标准
3. 关注业绩预告

{'='*80}
"""