"""
波段交易系统 - 第一阶段：完整流程管道
"""
from typing import List, Tuple, Dict, Optional
import pandas as pd
from datetime import datetime

from src.common.models import (
    Stock, Track, Phase1Result, Phase1Score, Grade,
    MarketEnvironmentScore, RotationPhase
)
from src.common.constants import FIRST_GRADE_RATIO

from .market_environment import MarketEnvironmentEvaluator
from .track_discovery import TrackDiscovery, TrackSourceData
from .filters import Phase1Filter
from .scoring import Phase1Scorer


class Phase1Pipeline:
    """第一阶段完整流程管道"""

    def __init__(self):
        self.market_evaluator = MarketEnvironmentEvaluator()
        self.track_discovery = TrackDiscovery()
        self.scorer = None  # 需要market_status初始化
        self.filter = None  # 需要market_status初始化

    def run_market_environment(
        self,
        rps50: float,
        rps120: float,
        ma20: float,
        ma60: float,
        current_index: float,
        avg_daily_volume_5d: float,
        rise_fall_ratio: float,
        limit_up_count: int,
        net_inflow_20d: float,
    ) -> MarketEnvironmentScore:
        """
        执行大盘环境评估
        """
        score = self.market_evaluator.evaluate(
            rps50, rps120, ma20, ma60, current_index,
            avg_daily_volume_5d, rise_fall_ratio, limit_up_count, net_inflow_20d
        )

        if self.market_evaluator.should_suspend_screening(score):
            print(f"⚠️ 大盘环境红灯（{score.total_score:.1f}分），暂停初筛")
        else:
            print(f"✅ 大盘环境{score.environment.value}（{score.total_score:.1f}分），继续初筛")

        return score

    def run_track_discovery(
        self,
        policy_tracks: List[str],
        capital_data: List[TrackSourceData],
        industry_data: List[TrackSourceData],
        catalyst_data: Optional[Dict[str, int]] = None,
    ) -> List[Track]:
        """
        执行赛道发现
        """
        tracks = self.track_discovery.discover(
            policy_tracks, capital_data, industry_data, catalyst_data
        )
        print(f"✅ 发现 {len(tracks)} 个赛道")
        for track in tracks:
            print(f"  - {track.name}: {track.rating.value} ({track.total_score:.1f}分)")
        return tracks

    def run_filter_and_score(
        self,
        stocks: List[Stock],
        tracks: List[Track],
        track_catalysts: Optional[Dict[str, int]] = None,
        stock_catalysts: Optional[Dict[str, int]] = None,
        historical_data: Optional[Dict[str, Dict]] = None,
        earnings_data: Optional[Dict[str, bool]] = None,
        risk_data: Optional[Dict[str, Dict]] = None,
    ) -> Tuple[List[Phase1Result], List[Tuple[Stock, str]]]:
        """
        执行过滤和评分
        
        Returns:
            (通过的结果列表, 剔除的股票及原因列表)
        """
        if not self.filter or not self.scorer:
            raise ValueError("需要先初始化market_status")

        # 强制过滤
        passed_stocks, rejected = self.filter.filter_batch(stocks)
        print(f"✅ 强制过滤: {len(passed_stocks)}只通过, {len(rejected)}只剔除")

        # 评分
        results = []
        track_dict = {t.name: t for t in tracks}

        for stock in passed_stocks:
            track = track_dict.get(stock.track)
            if not track:
                rejected.append((stock, "未找到对应赛道"))
                continue

            # 获取催化事件数
            catalyst_count = 0
            if stock_catalysts and stock.code in stock_catalysts:
                catalyst_count = stock_catalysts[stock.code]
            elif track_catalysts and stock.track in track_catalysts:
                catalyst_count = track_catalysts[stock.track]

            # 获取历史数据
            hist = historical_data.get(stock.code, {}) if historical_data else {}
            earnings = earnings_data.get(stock.code, True) if earnings_data else True
            risks = risk_data.get(stock.code, {}) if risk_data else {}

            # 评分
            score = self.scorer.score_and_grade(
                stock=stock,
                track=track,
                catalyst_count=catalyst_count,
                historical_avg_rise=hist.get("avg_rise", 0.0),
                historical_win_rate=hist.get("win_rate", 0.0),
                earnings_accelerating=earnings,
                has_reduction_risk=risks.get("reduction", False),
                has_unlock_risk=risks.get("unlock", False),
            )

            # 只保留第一档和第二档（第三档不进入第二阶段）
            if score.grade in [Grade.FIRST, Grade.SECOND]:
                result = Phase1Result(
                    stock=stock,
                    track_obj=track,
                    phase1_score=score,
                    market_status=self.filter.market_status,
                    rotation_phase=track.rotation_phase,
                )
                results.append(result)
            else:
                rejected.append((stock, f"第三档剔除（总分{score.total_score:.0f}分）"))

        return results, rejected

    def adjust_grade_ratio(
        self,
        results: List[Phase1Result],
    ) -> List[Phase1Result]:
        """
        调整第一档占比到30%-40%
        """
        if not results:
            return results

        first_count = sum(1 for r in results if r.phase1_score.grade == Grade.FIRST)
        total = len(results)
        ratio = first_count / total if total > 0 else 0

        if ratio > FIRST_GRADE_RATIO["max"]:
            # 第一档过多，将部分降级
            target_count = int(total * FIRST_GRADE_RATIO["max"])
            first_results = [r for r in results if r.phase1_score.grade == Grade.FIRST]
            # 按总分排序，保留高分
            first_results.sort(key=lambda x: x.phase1_score.total_score, reverse=True)

            # 降级超出数量的第一档
            for result in first_results[target_count:]:
                result.phase1_score.grade = Grade.SECOND
                result.remark = "第一档占比调整降级"

            print(f"📊 第一档占比从{ratio:.1%}调整至{target_count/total:.1%}")

        elif ratio < FIRST_GRADE_RATIO["min"]:
            # 第一档过少，将部分升级
            target_count = int(total * FIRST_GRADE_RATIO["min"])
            second_results = [r for r in results if r.phase1_score.grade == Grade.SECOND]
            # 按总分排序，升级高分
            second_results.sort(key=lambda x: x.phase1_score.total_score, reverse=True)

            upgrade_count = target_count - first_count
            for result in second_results[:upgrade_count]:
                # 检查是否符合第一档条件
                if result.phase1_score.total_score >= 80:
                    result.phase1_score.grade = Grade.FIRST
                    result.remark = "第一档占比调整升级"

            print(f"📊 第一档占比从{ratio:.1%}调整至{target_count/total:.1%}")

        return results

    def generate_output(
        self,
        results: List[Phase1Result],
        output_dir: str = "./data/phase1_output",
    ) -> str:
        """
        生成第一阶段输出CSV
        
        Returns:
            输出文件路径
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        # 构建数据
        data = []
        for result in results:
            stock = result.stock
            score = result.phase1_score

            data.append({
                "代码": stock.code,
                "名称": stock.name,
                "赛道": stock.track,
                "产业链层级": stock.chain_level.value,
                "产业链环节": stock.chain_link,
                "卡位评级": stock.position_rating.value,
                "景气传导阶段": stock.prosperity_phase,
                "催化日历": stock.catalyst_calendar,
                "数据日期": datetime.now().strftime("%Y-%m-%d"),
                "流通市值": stock.float_market_cap,
                "近60日涨幅": stock.rise_60d,
                "近20日涨幅": stock.rise_20d,
                "Beta": stock.beta,
                "产业动量": score.industry_momentum,
                "个股弹性": score.individual_flexibility,
                "安全边际": score.safety_margin,
                "第一阶段总分": score.total_score,
                "第一阶段档位": score.grade.value,
                "业绩状态": "加速" if score.earnings_trend_score >= 10 else "改善",
                "板块轮动阶段": result.rotation_phase.value,
                "核心逻辑": result.core_logic,
                "备注": result.remark,
            })

        df = pd.DataFrame(data)

        # 保存CSV
        quarter = self._get_quarter()
        filename = f"{output_dir}/波段初筛池_{quarter}.csv"
        df.to_csv(filename, index=False, encoding="utf-8-sig")

        print(f"✅ 已保存初筛池: {filename}")
        print(f"   共 {len(df)} 只股票")
        if len(df) > 0:
            print(f"   第一档: {len(df[df['第一阶段档位']=='一档'])} 只")
            print(f"   第二档: {len(df[df['第一阶段档位']=='二档'])} 只")

        return filename

    def _get_quarter(self) -> str:
        """获取当前季度字符串"""
        now = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        return f"{now.year}Q{quarter}"

    def run(
        self,
        # 大盘环境参数
        market_params: Dict,
        # 赛道发现参数
        policy_tracks: List[str],
        capital_data: List[TrackSourceData],
        industry_data: List[TrackSourceData],
        catalyst_data: Optional[Dict[str, int]] = None,
        # 股票参数
        stocks: List[Stock] = None,
        track_catalysts: Optional[Dict[str, int]] = None,
        stock_catalysts: Optional[Dict[str, int]] = None,
        historical_data: Optional[Dict[str, Dict]] = None,
        earnings_data: Optional[Dict[str, bool]] = None,
        risk_data: Optional[Dict[str, Dict]] = None,
        # 输出参数
        output_dir: str = "./data/phase1_output",
    ) -> Tuple[MarketEnvironmentScore, List[Track], List[Phase1Result], str]:
        """
        执行第一阶段完整流程
        
        Returns:
            (大盘环境评分, 赛道列表, 初筛结果, 输出文件路径)
        """
        print("=" * 60)
        print("波段交易系统 - 第一阶段：赛道与个股初筛")
        print("=" * 60)

        # 1. 大盘环境评估
        print("\n【步骤1】大盘环境评估...")
        market_score = self.run_market_environment(**market_params)

        if self.market_evaluator.should_suspend_screening(market_score):
            return market_score, [], [], ""

        # 2. 赛道发现
        print("\n【步骤2】赛道发现...")
        tracks = self.run_track_discovery(
            policy_tracks, capital_data, industry_data, catalyst_data
        )

        # 3. 初始化过滤器和评分器
        self.filter = Phase1Filter(market_score.market_status)
        self.scorer = Phase1Scorer(market_score.market_status)

        # 4. 过滤和评分
        print("\n【步骤3】强制过滤与三因子评分...")
        results, rejected = self.run_filter_and_score(
            stocks or [], tracks,
            track_catalysts, stock_catalysts,
            historical_data, earnings_data, risk_data
        )

        # 5. 调整档位占比
        print("\n【步骤4】档位占比调整...")
        results = self.adjust_grade_ratio(results)

        # 6. 生成输出
        print("\n【步骤5】生成输出文件...")
        output_file = self.generate_output(results, output_dir)

        print("\n" + "=" * 60)
        print("第一阶段完成")
        print("=" * 60)

        return market_score, tracks, results, output_file
