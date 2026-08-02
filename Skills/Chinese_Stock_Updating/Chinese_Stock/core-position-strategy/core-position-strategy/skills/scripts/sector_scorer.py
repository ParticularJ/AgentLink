"""
核心仓交易系统 - 赛道评分器
严格遵循《核心仓策略 V3.0》第一阶段设计文档
"""
from typing import List, Dict, Optional
from models import SectorRating, SectorLifecycle, MacroLiquidity, MacroEnvironment


class SectorScorer:
    """赛道五维评估评分器"""
    
    def __init__(self):
        self.lifecycle_penetration_map = {
            SectorLifecycle.INTRODUCTION: (0, 5),
            SectorLifecycle.EARLY_EXPLOSION: (5, 10),
            SectorLifecycle.MID_EXPLOSION: (10, 20),
            SectorLifecycle.MATURE: (20, 100),
        }
    
    def score(self, sector_data: Dict, macro: MacroLiquidity) -> Optional[SectorRating]:
        """
        评分赛道
        
        Args:
            sector_data: {
                'sector_name': str,
                'penetration_rate': float,        # 渗透率%
                'policy_strength_score': float,   # 政策强度分(0-100)
                'foreign_consensus_score': float, # 外资共识度(0-100)
                'capex_score': float,             # 资本开支分(0-100)
            }
            macro: MacroLiquidity对象
            
        Returns:
            SectorRating or None
        """
        sector_name = sector_data.get('sector_name', '')
        penetration = sector_data.get('penetration_rate', 0)
        
        # 1. 产业阶段评分 (40%) - 基于渗透率
        lifecycle, stage_score = self._score_industry_stage(penetration)
        
        # 2. 宏观匹配度评分 (15%)
        macro_score = self._score_macro_match(macro)
        
        # 3. 政策强度评分 (20%)
        policy_score = sector_data.get('policy_strength_score', 0)
        
        # 4. 外资共识度评分 (15%)
        foreign_score = sector_data.get('foreign_consensus_score', 0)
        
        # 5. 资本开支评分 (10%)
        capex_score = sector_data.get('capex_score', 0)
        
        # 确定评级和配置上限
        rating, max_alloc = self._get_rating_and_allocation(
            stage_score, macro_score, policy_score, foreign_score, capex_score
        )
        
        return SectorRating(
            sector_name=sector_name,
            rating=rating,
            lifecycle=lifecycle,
            penetration_rate=penetration,
            max_allocation_pct=max_alloc,
            industry_stage_score=stage_score,
            macro_match_score=macro_score,
            policy_strength_score=policy_score,
            foreign_consensus_score=foreign_score,
            capex_score=capex_score
        )
    
    def _score_industry_stage(self, penetration: float) -> tuple:
        """
        产业阶段评分 - 基于渗透率
        爆发初期(5-10%)和爆发中期(10-20%)得高分
        """
        if 5 <= penetration <= 10:
            return SectorLifecycle.EARLY_EXPLOSION, 95.0
        elif 10 < penetration <= 20:
            return SectorLifecycle.MID_EXPLOSION, 90.0
        elif 2 <= penetration < 5:
            return SectorLifecycle.INTRODUCTION, 60.0
        else:
            return SectorLifecycle.MATURE, 30.0
    
    def _score_macro_match(self, macro: MacroLiquidity) -> float:
        """宏观匹配度评分"""
        env = macro.environment
        if env == MacroEnvironment.EXPANSION:
            return 95.0
        elif env == MacroEnvironment.STABLE:
            return 75.0
        else:
            return 40.0
    
    def _get_rating_and_allocation(self, stage: float, macro: float, 
                                    policy: float, foreign: float, 
                                    capex: float) -> tuple:
        """
        根据五维评分确定评级和配置上限
        """
        total = (stage * 0.40 + macro * 0.15 + policy * 0.20 + 
                 foreign * 0.15 + capex * 0.10)
        
        if total >= 85:
            return "S", 0.25  # ≤25%
        elif total >= 75:
            return "A", 0.20  # ≤20%
        elif total >= 65:
            return "B", 0.15  # ≤15%
        else:
            return "C", 0.05  # ≤5%（观察）
    
    def filter_target_sectors(self, sectors: List[SectorRating], 
                              target_lifecycles: List[SectorLifecycle] = None) -> List[SectorRating]:
        """
        筛选目标赛道
        
        Args:
            sectors: 所有赛道评分列表
            target_lifecycles: 目标生命周期列表，默认[爆发初期, 爆发中期]
            
        Returns:
            符合条件的赛道列表
        """
        if target_lifecycles is None:
            target_lifecycles = [SectorLifecycle.EARLY_EXPLOSION, SectorLifecycle.MID_EXPLOSION]
        
        return [s for s in sectors if s.lifecycle in target_lifecycles]
