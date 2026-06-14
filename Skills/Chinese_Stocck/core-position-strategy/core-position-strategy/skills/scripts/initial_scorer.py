"""
核心仓交易系统 - 个股初筛评分器
严格遵循《核心仓策略 V3.0》第一阶段设计文档
"""
from typing import List, Dict, Optional
from models import StockInitialScore


class InitialScorer:
    """个股六维初筛评分器"""
    
    def __init__(self):
        pass
    
    def score(self, stock_data: Dict) -> Optional[StockInitialScore]:
        """
        初筛评分
        
        Args:
            stock_data: {
                'code': str,
                'name': str,
                'sector': str,
                # 六维数据
                'sector_heat_score': float,       # 赛道热度分(0-100)
                'chain_position_score': float,    # 产业链地位分(0-100)
                'tech_barrier_score': float,      # 技术壁垒分(0-100)
                'earnings_certainty_score': float, # 业绩确定性分(0-100)
                'management_quality_score': float, # 管理层质量分(0-100)
                'institution_consensus_score': float, # 机构共识分(0-100)
                # 一票否决数据
                'management_violation_2y': bool,  # 近2年违规记录
                'analyst_coverage_count': int,    # 券商覆盖数
                'revenue_decline_quarters': int,  # 营收连续下滑季度数
                'revenue_decline_pct': float,     # 营收下滑幅度%
                'daily_avg_volume': float,        # 日均成交额(亿)
                'goodwill_to_net_asset': float,   # 商誉/净资产
                'pledge_ratio': float,            # 质押/总股本%
                'roe_y1': float,                  # 第1年ROE
                'roe_y2': float,                  # 第2年ROE
                'audit_opinion': str,             # 审计意见
            }
            
        Returns:
            StockInitialScore or None（被否决）
        """
        code = stock_data.get('code', '')
        name = stock_data.get('name', '')
        sector = stock_data.get('sector', '')
        
        # ========== 一票否决检查 ==========
        veto_result = self._check_veto(stock_data)
        if not veto_result['passed']:
            return StockInitialScore(
                stock_code=code,
                stock_name=name,
                sector=sector,
                veto_passed=False,
                veto_reason=veto_result['reason']
            )
        
        # ========== 六维评分 ==========
        sector_heat = stock_data.get('sector_heat_score', 0)
        chain_position = stock_data.get('chain_position_score', 0)
        tech_barrier = stock_data.get('tech_barrier_score', 0)
        earnings_certainty = stock_data.get('earnings_certainty_score', 0)
        management_quality = stock_data.get('management_quality_score', 0)
        institution_consensus = stock_data.get('institution_consensus_score', 0)
        
        return StockInitialScore(
            stock_code=code,
            stock_name=name,
            sector=sector,
            sector_heat_score=sector_heat,
            chain_position_score=chain_position,
            tech_barrier_score=tech_barrier,
            earnings_certainty_score=earnings_certainty,
            management_quality_score=management_quality,
            institution_consensus_score=institution_consensus,
            veto_passed=True,
            raw_data=stock_data
        )
    
    def _check_veto(self, stock_data: Dict) -> Dict:
        """
        一票否决检查
        
        Returns:
            {'passed': bool, 'reason': str}
        """
        # 1. 管理层诚信：近2年有违规记录
        if stock_data.get('management_violation_2y', False):
            return {'passed': False, 'reason': '近2年有违规记录（减持未预披/财务造假等）'}
        
        # 2. 机构覆盖 < 2家券商
        if stock_data.get('analyst_coverage_count', 0) < 2:
            return {'passed': False, 'reason': f"机构覆盖仅{stock_data.get('analyst_coverage_count', 0)}家，<2家券商"}
        
        # 3. 营收连续2季度下滑 > 8%
        if (stock_data.get('revenue_decline_quarters', 0) >= 2 and
            stock_data.get('revenue_decline_pct', 0) > 8):
            return {'passed': False, 'reason': f"营收连续{stock_data.get('revenue_decline_quarters')}季度下滑>{stock_data.get('revenue_decline_pct')}%"}
        
        # 4. 日均成交额 < 1.5亿
        if stock_data.get('daily_avg_volume', 0) < 1.5:
            return {'passed': False, 'reason': f"日均成交额{stock_data.get('daily_avg_volume')}亿<1.5亿"}
        
        # 5. 商誉/净资产 > 20%
        if stock_data.get('goodwill_to_net_asset', 0) > 0.20:
            return {'passed': False, 'reason': f"商誉/净资产{stock_data.get('goodwill_to_net_asset'):.1%}>20%"}
        
        # 6. 质押/总股本 > 35%
        if stock_data.get('pledge_ratio', 0) > 35:
            return {'passed': False, 'reason': f"质押比例{stock_data.get('pledge_ratio')}%>35%"}
        
        # 7. ROE < 8% 连续2年
        roe_y1 = stock_data.get('roe_y1', 0)
        roe_y2 = stock_data.get('roe_y2', 0)
        if roe_y1 < 8 and roe_y2 < 8:
            return {'passed': False, 'reason': f"ROE连续2年低于8%（{roe_y2}%, {roe_y1}%）"}
        
        # 8. 审计意见为"非标"
        audit = stock_data.get('audit_opinion', '')
        if audit and '非标' in audit:
            return {'passed': False, 'reason': f"审计意见为{audit}"}
        
        return {'passed': True, 'reason': ''}
    
    def filter_and_rank(self, scores: List[StockInitialScore], 
                       target_pool_size: int = 60) -> List[StockInitialScore]:
        """
        过滤并排序，产出初筛股票池
        
        Args:
            scores: 评分列表
            target_pool_size: 目标池大小（默认60只）
            
        Returns:
            排序后的初筛股票池
        """
        # 过滤掉被否决的
        qualified = [s for s in scores if s.veto_passed]
        
        # 按总分排序
        qualified.sort(key=lambda x: x.total_score, reverse=True)
        
        return qualified[:target_pool_size]
