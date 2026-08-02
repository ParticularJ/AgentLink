"""
核心仓交易系统 - 二次筛选评分器（财报验证）
严格遵循《核心仓策略 V3.0》第二阶段设计文档
"""
from typing import List, Dict, Optional
from models import (
    StockInitialScore, StockSecondaryScore, 
    FinancialReport, EarningsVerification, SignalLevel
)


class SecondaryScorer:
    """财报验证与二次筛选评分器"""
    
    def __init__(self):
        pass
    
    def score_financial(self, report: FinancialReport) -> float:
        """
        财报打分模型
        
        权重：
        - 营收增速：25%
        - 利润增速：25%
        - 现金流质量：20%
        - 毛利率趋势：15%
        - 前瞻指标：15%
        
        Returns:
            业绩得分 (0-100)
        """
        # 1. 营收增速评分 (25分)
        revenue_score = self._score_revenue_growth(report.revenue_growth)
        
        # 2. 利润增速评分 (25分)
        profit_score = self._score_profit_growth(report.profit_growth)
        
        # 3. 现金流质量评分 (20分)
        cashflow_score = self._score_cashflow_quality(report.cash_flow_to_profit)
        
        # 4. 毛利率趋势评分 (15分)
        margin_score = self._score_margin_trend(report.gross_margin_trend)
        
        # 5. 前瞻指标评分 (15分)
        forward_score = self._score_forward_indicators(
            report.guidance_adjustment, report.order_visibility
        )
        
        return (revenue_score * 0.25 + profit_score * 0.25 +
                cashflow_score * 0.20 + margin_score * 0.15 +
                forward_score * 0.15)
    
    def _score_revenue_growth(self, growth: float) -> float:
        """营收增速评分"""
        if growth > 50:
            return 100.0
        elif growth >= 30:
            return 80.0
        elif growth >= 15:
            return 60.0
        else:
            return max(0, growth / 15 * 60)
    
    def _score_profit_growth(self, growth: float) -> float:
        """利润增速评分"""
        if growth > 80:
            return 100.0
        elif growth >= 50:
            return 80.0
        elif growth >= 30:
            return 60.0
        else:
            return max(0, growth / 30 * 60)
    
    def _score_cashflow_quality(self, ratio: float) -> float:
        """现金流质量评分"""
        if ratio > 1.0:
            return 100.0
        elif ratio >= 0.8:
            return 80.0
        elif ratio >= 0.6:
            return 60.0
        else:
            return max(0, ratio / 0.6 * 60)
    
    def _score_margin_trend(self, trend: float) -> float:
        """毛利率趋势评分"""
        if trend >= 3:
            return 100.0
        elif trend >= 1:
            return 80.0
        elif trend >= -1:
            return 60.0
        elif trend > -3:
            return 30.0
        else:
            return 0.0
    
    def _score_forward_indicators(self, guidance: str, orders: str) -> float:
        """前瞻指标评分"""
        score = 0.0
        
        # 业绩指引
        if guidance == "上调":
            score += 60.0
        elif guidance == "持平":
            score += 40.0
        else:  # 下调
            score += 10.0
        
        # 订单能见度
        if orders == "饱满":
            score += 40.0
        elif orders == "一般":
            score += 20.0
        else:
            score += 5.0
        
        return min(score, 100.0)
    
    def check_risk(self, report: FinancialReport) -> Dict:
        """
        财报风险排查
        
        Returns:
            {'should_veto': bool, 'deduction': float, 'reasons': List[str]}
        """
        should_veto = False
        deduction = 0.0
        reasons = []
        
        # 1. 连续2季度现金流为负 -> 直接剔除
        if report.cash_flow_negative_quarters >= 2:
            should_veto = True
            reasons.append(f"连续{report.cash_flow_negative_quarters}季度现金流为负")
        
        # 2. 应收账款增速 > 营收增速×1.5 -> -10分
        if report.receivable_growth_vs_revenue > 1.5:
            deduction += 10.0
            reasons.append(f"应收账款增速/营收增速={report.receivable_growth_vs_revenue:.2f}>1.5")
        
        # 3. 存货增速 > 营收增速×1.3 -> -8分
        if report.inventory_growth_vs_revenue > 1.3:
            deduction += 8.0
            reasons.append(f"存货增速/营收增速={report.inventory_growth_vs_revenue:.2f}>1.3")
        
        # 4. 大股东公告减持 > 1% -> -5分
        if report.major_holder_reduction_pct > 1.0:
            deduction += 5.0
            reasons.append(f"大股东减持{report.major_holder_reduction_pct}%")
        
        return {
            'should_veto': should_veto,
            'deduction': deduction,
            'reasons': reasons
        }
    
    def evaluate_expectation(self, verification_data: Dict) -> EarningsVerification:
        """
        超预期验证
        
        Args:
            verification_data: {
                'price_reaction': bool,          # 财报后1-3日股价上涨
                'analyst_reaction': bool,        # ≥3家券商上调评级/目标价
                'volume_reaction': bool,         # 后续3日成交量放大
                'northbound_inflow': bool,       # 财报后5日净流入>5000万
            }
            
        Returns:
            EarningsVerification对象
        """
        return EarningsVerification(
            price_reaction=verification_data.get('price_reaction', False),
            analyst_reaction=verification_data.get('analyst_reaction', False),
            volume_reaction=verification_data.get('volume_reaction', False),
            northbound_inflow=verification_data.get('northbound_inflow', False)
        )
    
    def calculate_expectation_score(self, verification: EarningsVerification) -> float:
        """
        计算预期差分
        
        基于4项验证的满足数量：
        - 4项全满足（胜率88%）：100分
        - 3项满足（胜率78%）：85分
        - 2项满足（胜率68%）：70分
        - 1项满足（胜率55%）：50分
        - 0项满足（胜率35%）：30分
        """
        match_count = verification.match_count
        scores = {4: 100.0, 3: 85.0, 2: 70.0, 1: 50.0, 0: 30.0}
        return scores.get(match_count, 30.0)
    
    def secondary_screen(self, 
                        initial_scores: List[StockInitialScore],
                        financial_reports: Dict[str, FinancialReport],
                        verifications: Dict[str, EarningsVerification]) -> List[StockSecondaryScore]:
        """
        执行二次筛选
        
        Args:
            initial_scores: 初筛评分列表
            financial_reports: {stock_code: FinancialReport}
            verifications: {stock_code: EarningsVerification}
            
        Returns:
            二次筛选结果列表
        """
        results = []
        
        for initial in initial_scores:
            code = initial.stock_code
            
            # 获取财报数据
            report = financial_reports.get(code)
            if not report:
                continue
            
            # 风险排查
            risk_check = self.check_risk(report)
            if risk_check['should_veto']:
                continue
            
            # 财报打分
            financial_score = self.score_financial(report)
            
            # 预期差分
            verification = verifications.get(code, EarningsVerification())
            expectation_score = self.calculate_expectation_score(verification)
            
            # 综合评分
            secondary = StockSecondaryScore(
                stock_code=code,
                stock_name=initial.stock_name,
                sector=initial.sector,
                initial_score=initial.total_score,
                financial_score=financial_score,
                expectation_score=expectation_score,
                risk_deduction=risk_check['deduction'],
                verification=verification
            )
            
            results.append(secondary)
        
        return results
    
    def filter_buy_candidates(self, scores: List[StockSecondaryScore],
                              min_score: float = 82) -> List[StockSecondaryScore]:
        """
        过滤出买入候选池
        
        Args:
            scores: 二次筛选评分列表
            min_score: 最低买入分数线（默认82分）
            
        Returns:
            买入候选池（5-8只）
        """
        # 只保留推荐及以上
        candidates = [s for s in scores if s.total_score >= min_score]
        
        # 按综合评分排序
        candidates.sort(key=lambda x: x.total_score, reverse=True)
        
        # 限制8只
        return candidates[:8]
