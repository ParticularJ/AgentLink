"""
波段交易系统 - 第一阶段：赛道发现机制
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
from src.common.models import Track, TrackRating
from src.common.constants import TRACK_SCORE_THRESHOLDS, TRACK_COUNT_LIMITS


@dataclass
class TrackSourceData:
    """赛道来源数据"""
    name: str
    source_type: str  # policy/capital/industry
    rps20: Optional[float] = None
    volume_ratio: Optional[float] = None
    financing_growth: Optional[float] = None
    limit_up_count: Optional[int] = None
    northbound_inflow: Optional[float] = None
    penetration_rate: Optional[float] = None
    capex_growth: Optional[float] = None
    research_report_count: Optional[int] = None
    funding_amount: Optional[float] = None
    price_change: Optional[float] = None


class TrackDiscovery:
    """赛道发现器"""

    def __init__(self):
        self.candidate_tracks: List[Track] = []

    def discover_from_policy(
        self,
        policy_tracks: List[str],
    ) -> List[Track]:
        """
        从政策文件发现赛道
        
        Args:
            policy_tracks: 政策提及的赛道列表
            
        Returns:
            候选赛道列表
        """
        tracks = []
        for name in policy_tracks:
            track = Track(name=name)
            track.policy_score = 20.0  # 国家战略级默认20分
            track.sources.append("政策")
            tracks.append(track)
        return tracks

    def discover_from_capital(
        self,
        capital_data: List[TrackSourceData],
    ) -> List[Track]:
        """
        从市场资金发现赛道
        
        Args:
            capital_data: 资金驱动数据列表
            
        Returns:
            候选赛道列表
        """
        tracks = []
        for data in capital_data:
            score = 0.0
            met_conditions = 0

            # 检查各项指标
            if data.rps20 and data.rps20 > 85:
                score += 6.0
                met_conditions += 1
            if data.volume_ratio and data.volume_ratio > 0.04:
                score += 6.0
                met_conditions += 1
            if data.financing_growth and data.financing_growth > 0.10:
                score += 6.0
                met_conditions += 1
            if data.limit_up_count and data.limit_up_count > 3:
                score += 6.0
                met_conditions += 1
            if data.northbound_inflow and data.northbound_inflow > 30:
                score += 6.0
                met_conditions += 1

            # 满足任意2项才纳入
            if met_conditions >= 2:
                track = Track(name=data.name)
                track.capital_consensus_score = min(score, 30.0)
                track.sources.append("资金")
                tracks.append(track)

        return tracks

    def discover_from_industry(
        self,
        industry_data: List[TrackSourceData],
    ) -> List[Track]:
        """
        从产业数据发现赛道
        
        Args:
            industry_data: 产业驱动数据列表
            
        Returns:
            候选赛道列表
        """
        tracks = []
        for data in industry_data:
            score = 0.0
            met_conditions = 0

            # 检查各项指标
            if data.penetration_rate and 0.03 <= data.penetration_rate <= 0.15:
                score += 6.0
                met_conditions += 1
            if data.capex_growth and data.capex_growth > 0.30:
                score += 6.0
                met_conditions += 1
            if data.research_report_count and data.research_report_count > 3:
                score += 6.0
                met_conditions += 1
            if data.funding_amount and data.funding_amount > 50:
                score += 6.0
                met_conditions += 1
            if data.price_change and data.price_change > 0.20:
                score += 6.0
                met_conditions += 1

            # 满足任意2项才纳入
            if met_conditions >= 2:
                track = Track(name=data.name)
                track.industry_phase_score = min(score, 30.0)
                track.sources.append("产业")
                tracks.append(track)

        return tracks

    def merge_tracks(
        self,
        policy_tracks: List[Track],
        capital_tracks: List[Track],
        industry_tracks: List[Track],
    ) -> List[Track]:
        """
        合并三个来源的赛道，去重并合并分数
        
        Returns:
            合并后的候选赛道池
        """
        track_dict: Dict[str, Track] = {}

        # 合并所有赛道
        for track in policy_tracks + capital_tracks + industry_tracks:
            if track.name not in track_dict:
                track_dict[track.name] = track
            else:
                # 合并分数
                existing = track_dict[track.name]
                existing.policy_score = max(existing.policy_score, track.policy_score)
                existing.capital_consensus_score = max(
                    existing.capital_consensus_score, track.capital_consensus_score
                )
                existing.industry_phase_score = max(
                    existing.industry_phase_score, track.industry_phase_score
                )
                existing.sources = list(set(existing.sources + track.sources))

        return list(track_dict.values())

    def evaluate_tracks(
        self,
        tracks: List[Track],
        catalyst_data: Optional[Dict[str, int]] = None,
    ) -> List[Track]:
        """
        对候选赛道进行四维评估
        
        Args:
            tracks: 候选赛道列表
            catalyst_data: 赛道催化事件数量 {赛道名: 事件数}
            
        Returns:
            评分后的赛道列表
        """
        for track in tracks:
            # 计算催化密度分数
            if catalyst_data and track.name in catalyst_data:
                count = catalyst_data[track.name]
                if count >= 3:
                    track.catalyst_density_score = 15.0
                elif count >= 1:
                    track.catalyst_density_score = 8.0
                else:
                    track.catalyst_density_score = 3.0
            else:
                track.catalyst_density_score = 3.0

            # 计算总分
            track.total_score = (
                track.policy_score * 0.25
                + track.industry_phase_score * 0.30
                + track.capital_consensus_score * 0.30
                + track.catalyst_density_score * 0.15
            )

            # 判定评级
            if track.total_score >= TRACK_SCORE_THRESHOLDS["s_level"]:
                track.rating = TrackRating.S
            elif track.total_score >= TRACK_SCORE_THRESHOLDS["a_level"]:
                track.rating = TrackRating.A
            elif track.total_score >= TRACK_SCORE_THRESHOLDS["b_level"]:
                track.rating = TrackRating.B
            else:
                track.rating = TrackRating.B

        return tracks

    def filter_tracks(
        self,
        tracks: List[Track],
    ) -> List[Track]:
        """
        过滤赛道，控制数量
        
        Returns:
            过滤后的赛道列表
        """
        # 按分数排序
        tracks.sort(key=lambda x: x.total_score, reverse=True)

        # 筛选 >= 70分的赛道
        qualified = [t for t in tracks if t.total_score >= TRACK_SCORE_THRESHOLDS["pass"]]

        # 控制数量
        s_tracks = [t for t in qualified if t.rating == TrackRating.S][:TRACK_COUNT_LIMITS["s_max"]]
        a_tracks = [t for t in qualified if t.rating == TrackRating.A][:TRACK_COUNT_LIMITS["a_max"]]
        b_tracks = [t for t in qualified if t.rating == TrackRating.B][:TRACK_COUNT_LIMITS["b_max"]]

        result = s_tracks + a_tracks + b_tracks

        # 确保总数在8-12个
        if len(result) > TRACK_COUNT_LIMITS["total_max"]:
            result = result[:TRACK_COUNT_LIMITS["total_max"]]

        return result

    def discover(
        self,
        policy_tracks: List[str],
        capital_data: List[TrackSourceData],
        industry_data: List[TrackSourceData],
        catalyst_data: Optional[Dict[str, int]] = None,
    ) -> List[Track]:
        """
        完整的赛道发现流程
        
        Returns:
            最终赛道列表
        """
        # 三层漏斗
        policy_results = self.discover_from_policy(policy_tracks)
        capital_results = self.discover_from_capital(capital_data)
        industry_results = self.discover_from_industry(industry_data)

        # 合并
        merged = self.merge_tracks(policy_results, capital_results, industry_results)

        # 评估
        evaluated = self.evaluate_tracks(merged, catalyst_data)

        # 过滤
        final_tracks = self.filter_tracks(evaluated)

        return final_tracks
