# skills/ma_bullish/scripts/report_generator.py

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
import json

class ReportGenerator:
    """报告生成器 - 生成格式化的分析报告"""
    
    def __init__(self):
        self.report_types = ['simple', 'detailed', 'json']
    
    def generate_scan_report(self, candidates: List[Dict], top_n: int = 20) -> str:
        """生成全市场扫描报告"""
        if not candidates:
            return self._generate_empty_report()
        
        report = []
        report.append("=" * 80)
        report.append(f"均线多头排列策略扫描报告")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"发现标的: {len(candidates)}只")
        report.append("=" * 80)
        
        # Top N 详情
        report.append(f"\n【Top {min(top_n, len(candidates))} 推荐标的】")
        report.append("-" * 80)
        
        for i, stock in enumerate(candidates[:top_n], 1):
            report.append(f"\n{i}. {stock['stock_name']}({stock['stock_code']})")
            report.append(f"   综合得分: {stock['score']}分")
            report.append(f"   当前价格: {stock['current_price']}元")
            report.append(f"   入场价格: {stock['entry_price']}元")
            report.append(f"   止损价格: {stock['stop_loss']}元 ({self._calc_pct(stock['entry_price'], stock['stop_loss'])}%)")
            report.append(f"   目标价格: {stock['target_price']}元 (+{self._calc_pct(stock['entry_price'], stock['target_price'])}%)")
            report.append(f"   风险收益比: 1:{stock['risk_reward_ratio']}")
            report.append(f"   操作建议: {stock['suggestion']}")
            
            # 详细指标
            if 'details' in stock:
                report.append(f"   【技术指标】")
                ma = stock['details'].get('ma_arrangement', {})
                if ma:
                    report.append(f"     - 均线排列: {ma.get('level', 'N/A')}")
                    report.append(f"     - MA5/MA10/MA20: {ma.get('values', {}).get('ma5', 'N/A')}/{ma.get('values', {}).get('ma10', 'N/A')}/{ma.get('values', {}).get('ma20', 'N/A')}")
                
                volume = stock['details'].get('volume_trend', {})
                if volume:
                    report.append(f"     - 成交量: {volume.get('trend', 'N/A')} (放量{volume.get('volume_ratio', 1)}倍)")
                
                trend = stock['details'].get('trend_strength', {})
                if trend:
                    report.append(f"     - 趋势强度: {trend.get('strength', 'N/A')}")
        
        # 统计摘要
        report.append("\n" + "=" * 80)
        report.append("【统计摘要】")
        report.append(f"  高分标的(≥85分): {len([s for s in candidates if s['score'] >= 85])}只")
        report.append(f"  中分标的(75-84分): {len([s for s in candidates if 75 <= s['score'] < 85])}只")
        report.append(f"  低分标的(70-74分): {len([s for s in candidates if 70 <= s['score'] < 75])}只")
        report.append(f"  平均得分: {sum(s['score'] for s in candidates)/len(candidates):.1f}分")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def generate_stock_report(self, stock_analysis: Dict) -> str:
        """生成单只股票分析报告"""
        if not stock_analysis or 'error' in stock_analysis:
            return f"分析失败: {stock_analysis.get('error', '未知错误')}"
        
        report = []
        report.append("=" * 80)
        report.append(f"【{stock_analysis['stock_name']}】({stock_analysis['stock_code']}) 均线多头排列分析报告")
        report.append("=" * 80)
        
        # 核心结论
        report.append(f"\n【核心结论】")
        report.append(f"  信号类型: {stock_analysis.get('signal', 'N/A')}")
        report.append(f"  综合评分: {stock_analysis.get('score', 0)}/100分")
        report.append(f"  操作建议: {stock_analysis.get('suggestion', 'N/A')}")
        
        # 交易计划
        report.append(f"\n【交易计划】")
        report.append(f"  当前价格: {stock_analysis.get('current_price', 'N/A')}元")
        report.append(f"  建议入场: {stock_analysis.get('entry_price', 'N/A')}元")
        report.append(f"  止损价位: {stock_analysis.get('stop_loss', 'N/A')}元")
        report.append(f"  目标价位: {stock_analysis.get('target_price', 'N/A')}元")
        report.append(f"  风险收益比: 1:{stock_analysis.get('risk_reward_ratio', 'N/A')}")
        
        # 详细分析
        details = stock_analysis.get('details', {})
        
        report.append(f"\n【技术分析详情】")
        
        ma = details.get('ma_arrangement', {})
        if ma:
            report.append(f"  ✓ 均线排列: {ma.get('level', 'N/A')}")
            values = ma.get('values', {})
            if values:
                report.append(f"    - MA5: {values.get('ma5', 'N/A')}")
                report.append(f"    - MA10: {values.get('ma10', 'N/A')}")
                report.append(f"    - MA20: {values.get('ma20', 'N/A')}")
        
        price = details.get('price_position', {})
        if price:
            report.append(f"  ✓ 价格位置: {price.get('position', 'N/A')}")
            report.append(f"    - 偏离20日线: {price.get('price_to_ma20', 'N/A')}%")
        
        volume = details.get('volume_trend', {})
        if volume:
            report.append(f"  ✓ 成交量: {volume.get('trend', 'N/A')}")
            report.append(f"    - 放量倍数: {volume.get('volume_ratio', 'N/A')}倍")
            report.append(f"    - 趋势: {'递增' if volume.get('volume_increasing') else '平稳'}")
        
        trend = details.get('trend_strength', {})
        if trend:
            report.append(f"  ✓ 趋势强度: {trend.get('strength', 'N/A')}")
        
        market = details.get('market_environment', {})
        if market:
            report.append(f"  ✓ 市场环境: {market.get('environment', 'N/A')}")
        
        # 风险评估
        report.append(f"\n【风险评估】")
        risks = self._assess_risks(stock_analysis)
        for risk in risks:
            report.append(f"  ⚠ {risk}")
        
        # 操作建议
        report.append(f"\n【操作建议】")
        report.append(f"  {self._generate_action_plan(stock_analysis)}")
        
        report.append("\n" + "=" * 80)
        report.append(f"报告生成时间: {stock_analysis.get('analysis_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}")
        report.append("免责声明: 本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def generate_backtest_report(self, backtest_results: Dict) -> str:
        """生成回测报告"""
        if not backtest_results or 'error' in backtest_results:
            return f"回测失败: {backtest_results.get('error', '未知错误')}"
        
        report = []
        report.append("=" * 80)
        report.append(f"均线多头排列策略回测报告")
        report.append(f"回测区间: {backtest_results.get('start_date', 'N/A')} 至 {backtest_results.get('end_date', 'N/A')}")
        report.append("=" * 80)
        
        # 收益指标
        perf = backtest_results.get('performance', {})
        report.append(f"\n【收益指标】")
        report.append(f"  总收益率: {perf.get('total_return', 0):.2f}%")
        report.append(f"  年化收益率: {perf.get('annual_return', 0):.2f}%")
        report.append(f"  超额收益: {perf.get('excess_return', 0):.2f}%")
        
        # 风险指标
        report.append(f"\n【风险指标】")
        report.append(f"  最大回撤: {perf.get('max_drawdown', 0):.2f}%")
        report.append(f"  夏普比率: {perf.get('sharpe_ratio', 0):.2f}")
        report.append(f"  胜率: {perf.get('win_rate', 0):.2f}%")
        report.append(f"  盈亏比: {perf.get('profit_loss_ratio', 0):.2f}")
        
        # 交易统计
        trades = backtest_results.get('trades', [])
        report.append(f"\n【交易统计】")
        report.append(f"  总交易次数: {len(trades)}")
        report.append(f"  盈利次数: {len([t for t in trades if t.get('profit', 0) > 0])}")
        report.append(f"  亏损次数: {len([t for t in trades if t.get('profit', 0) < 0])}")
        
        if trades:
            profits = [t.get('profit_pct', 0) for t in trades]
            report.append(f"  平均盈利: {max(profits):.2f}%")
            report.append(f"  平均亏损: {min(profits):.2f}%")
            report.append(f"  最大单笔盈利: {max(profits):.2f}%")
            report.append(f"  最大单笔亏损: {min(profits):.2f}%")
        
        # 月度收益
        monthly = perf.get('monthly_returns', {})
        if monthly:
            report.append(f"\n【月度收益分布】")
            for month, ret in sorted(monthly.items())[-6:]:
                report.append(f"  {month}: {ret:+.2f}%")
        
        report.append("\n" + "=" * 80)
        
        return "\n".join(report)
    
    def generate_json_report(self, data: Dict) -> str:
        """生成JSON格式报告"""
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def generate_alert_message(self, stock_analysis: Dict) -> str:
        """生成简洁的告警消息（用于微信/钉钉推送）"""
        if not stock_analysis or stock_analysis.get('score', 0) < 75:
            return None
        
        emoji = "🔴" if stock_analysis['score'] >= 85 else "🟡" if stock_analysis['score'] >= 75 else "🟢"
        
        message = f"""
{emoji} 【均线多头排列预警】
股票: {stock_analysis['stock_name']}({stock_analysis['stock_code']})
价格: {stock_analysis['current_price']}元
评分: {stock_analysis['score']}分
入场: {stock_analysis['entry_price']}元
止损: {stock_analysis['stop_loss']}元 (-{self._calc_pct(stock_analysis['entry_price'], stock_analysis['stop_loss'])}%)
目标: {stock_analysis['target_price']}元 (+{self._calc_pct(stock_analysis['entry_price'], stock_analysis['target_price'])}%)
建议: {stock_analysis['suggestion'][:50]}
"""
        return message.strip()
    
    def generate_daily_summary(self, all_signals: List[Dict]) -> str:
        """生成每日总结报告"""
        if not all_signals:
            return "今日无符合条件的股票信号"
        
        report = []
        report.append(f"📊 均线多头排列策略每日总结 - {datetime.now().strftime('%Y-%m-%d')}")
        report.append("=" * 50)
        
        # 按评分分组
        strong_signals = [s for s in all_signals if s.get('score', 0) >= 85]
        normal_signals = [s for s in all_signals if 75 <= s.get('score', 0) < 85]
        weak_signals = [s for s in all_signals if 70 <= s.get('score', 0) < 75]
        
        report.append(f"\n🔥 强烈推荐 ({len(strong_signals)}只):")
        for s in strong_signals[:5]:
            report.append(f"  • {s['stock_name']}({s['stock_code']}) 评分:{s['score']}")
        
        report.append(f"\n👍 重点关注 ({len(normal_signals)}只):")
        for s in normal_signals[:5]:
            report.append(f"  • {s['stock_name']}({s['stock_code']}) 评分:{s['score']}")
        
        if weak_signals:
            report.append(f"\n👀 观察名单 ({len(weak_signals)}只):")
            for s in weak_signals[:3]:
                report.append(f"  • {s['stock_name']}({s['stock_code']}) 评分:{s['score']}")
        
        # 行业分布
        industries = {}
        for s in all_signals:
            ind = s.get('industry', '其他')
            industries[ind] = industries.get(ind, 0) + 1
        
        report.append(f"\n📈 热点行业:")
        for ind, count in sorted(industries.items(), key=lambda x: x[1], reverse=True)[:5]:
            report.append(f"  • {ind}: {count}只")
        
        report.append("\n" + "=" * 50)
        report.append("⚠️ 温馨提示: 以上仅供参考，请结合市场环境谨慎决策")
        
        return "\n".join(report)
    
    def _calc_pct(self, price1: float, price2: float) -> str:
        """计算涨跌幅百分比"""
        if not price1 or not price2:
            return "N/A"
        pct = (price2 - price1) / price1 * 100
        return f"{pct:+.1f}"
    
    def _assess_risks(self, analysis: Dict) -> List[str]:
        """评估风险因素"""
        risks = []
        
        # 大盘风险
        details = analysis.get('details', {})
        market = details.get('market_environment', {})
        if market.get('environment') == '熊市氛围':
            risks.append("市场处于熊市氛围，策略胜率可能下降")
        
        # 追高风险
        price_pos = details.get('price_position', {})
        if price_pos.get('price_to_ma20', 0) > 10:
            risks.append("股价偏离20日线超过10%，短期追高风险较大")
        
        # 成交量风险
        volume = details.get('volume_trend', {})
        if volume.get('volume_ratio', 0) > 2:
            risks.append("成交量异常放大，警惕主力出货")
        
        # 趋势强度风险
        trend = details.get('trend_strength', {})
        if trend.get('strength') == '强势上涨':
            risks.append("短期涨幅过大，注意回调风险")
        
        if not risks:
            risks.append("无明显风险，但仍需设置止损")
        
        return risks
    
    def _generate_action_plan(self, analysis: Dict) -> str:
        """生成操作计划"""
        score = analysis.get('score', 0)
        
        if score >= 85:
            return """1. 明日开盘即可建仓30%
2. 若低开超过2%，等待企稳后买入
3. 严格设置止损位
4. 第一目标位止盈50%，剩余仓位移动止盈"""
        elif score >= 75:
            return """1. 分批建仓，首次建仓20%
2. 若回调至10日线可加仓10%
3. 严格设置止损
4. 达到第一目标位可减仓"""
        else:
            return """1. 暂时观察，等待更好的买点
2. 若放量突破今日高点可轻仓试探
3. 建议等待回调至均线附近"""
    
    def _generate_empty_report(self) -> str:
        """生成空报告"""
        return f"""
{'='*80}
均线多头排列策略扫描报告
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*80}

【结果】
今日未发现符合条件的股票标的。

【可能原因】
1. 市场处于震荡或下跌趋势
2. 均线多头排列的股票较少
3. 成交量条件过于严格

【建议】
1. 适当放宽条件重新扫描
2. 关注其他交易策略
3. 等待市场转暖

{'='*80}
"""


# 便捷函数
def quick_report(analysis_result: Dict, format_type: str = 'detailed') -> str:
    """快速生成报告"""
    generator = ReportGenerator()
    
    if format_type == 'simple':
        return generator.generate_stock_report(analysis_result)
    elif format_type == 'json':
        return generator.generate_json_report(analysis_result)
    elif format_type == 'alert':
        return generator.generate_alert_message(analysis_result)
    else:
        return generator.generate_stock_report(analysis_result)


if __name__ == '__main__':
    # 测试报告生成器
    generator = ReportGenerator()
    
    # 测试数据
    test_analysis = {
        'stock_code': '000001',
        'stock_name': '平安银行',
        'signal': 'BUY',
        'score': 85.5,
        'current_price': 12.50,
        'entry_price': 12.50,
        'stop_loss': 11.50,
        'target_price': 14.50,
        'risk_reward_ratio': 2.5,
        'suggestion': '强烈推荐买入',
        'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'details': {
            'ma_arrangement': {
                'level': '强势多头排列',
                'values': {'ma5': 12.30, 'ma10': 12.00, 'ma20': 11.80}
            },
            'price_position': {
                'position': '理想位置',
                'price_to_ma20': 5.93
            },
            'volume_trend': {
                'trend': '温和放量',
                'volume_ratio': 1.35
            },
            'trend_strength': {
                'strength': '稳定上涨'
            },
            'market_environment': {
                'environment': '震荡偏多'
            }
        }
    }
    
    print(generator.generate_stock_report(test_analysis))