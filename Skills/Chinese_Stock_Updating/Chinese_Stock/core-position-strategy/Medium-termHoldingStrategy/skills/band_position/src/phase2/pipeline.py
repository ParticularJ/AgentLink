"""
波段交易系统 - 第二阶段：完整流程管道
"""
from typing import List, Tuple, Dict, Optional
import pandas as pd
from datetime import datetime

from src.common.models import (
    Stock, Phase1Result, Phase2Result, Grade, IndustryType,
    MoatScore, VetoResult, FinancialReportScore, ValuationResult
)
from src.common.constants import PHASE2_PASS_SCORES

from .moat import MoatEvaluator
from .veto import VetoChecker
from .financial import FinancialScorer
from .valuation import ValuationEvaluator
from .position import PositionCalculator


class Phase2Pipeline:
    """第二阶段完整流程管道"""

    def __init__(self):
        self.position_calculator = PositionCalculator()
        self.industry_positions: Dict[str, float] = {}  # 行业仓位跟踪

    def _get_industry_type(self, track_name: str) -> IndustryType:
        """根据赛道确定行业类型"""
        tech_keywords = ["AI", "芯片", "半导体", "软件", "通信", "新能源", "创新药", "算力", "光通信"]
        consumer_keywords = ["白酒", "家电", "食品", "饮料", "医药"]
        cyclical_keywords = ["有色", "化工", "煤炭", "钢铁", "航运"]
        manufacturing_keywords = ["机械", "汽车", "电力", "电子制造"]

        for keyword in tech_keywords:
            if keyword in track_name:
                return IndustryType.TECH_GROWTH
        for keyword in consumer_keywords:
            if keyword in track_name:
                return IndustryType.CONSUMER_VALUE
        for keyword in cyclical_keywords:
            if keyword in track_name:
                return IndustryType.CYCLICAL_RESOURCE
        for keyword in manufacturing_keywords:
            if keyword in track_name:
                return IndustryType.MANUFACTURING

        return IndustryType.TECH_GROWTH  # 默认科技成长型

    def run_moat_evaluation(
        self,
        stock: Stock,
        moat_data: dict,
    ) -> MoatScore:
        """执行护城河评估"""
        industry_type = self._get_industry_type(stock.track)
        evaluator = MoatEvaluator(industry_type)

        score = evaluator.evaluate(
            gross_margin=moat_data.get("gross_margin", 0.0),
            industry_avg_margin=moat_data.get("industry_avg_margin", 0.0),
            rd_ratio=moat_data.get("rd_ratio", 0.0),
            top5_customer_ratio=moat_data.get("top5_customer_ratio", 0.0),
            net_profit_cash_ratio=moat_data.get("net_profit_cash_ratio", 0.0),
            renewal_rate=moat_data.get("renewal_rate", 0.0),
            avg_cooperation_years=moat_data.get("avg_cooperation_years", 0.0),
        )

        return score

    def run_veto_check(
        self,
        stock: Stock,
        veto_data: dict,
        market_status,
    ) -> VetoResult:
        """执行一票否决检查"""
        checker = VetoChecker(market_status)
        return checker.check_stock(stock, veto_data)

    def run_financial_scoring(
        self,
        stock: Stock,
        financial_data: dict,
    ) -> FinancialReportScore:
        """执行财报评分"""
        industry_type = self._get_industry_type(stock.track)
        scorer = FinancialScorer(industry_type)
        return scorer.evaluate_stock(stock, financial_data)

    def run_valuation(
        self,
        stock: Stock,
        valuation_data: dict,
    ) -> ValuationResult:
        """执行估值判断"""
        industry_type = self._get_industry_type(stock.track)
        evaluator = ValuationEvaluator(industry_type)
        return evaluator.evaluate_stock(stock, valuation_data)

    def run_position_calculation(
        self,
        financial_score: FinancialReportScore,
        valuation: ValuationResult,
        moat_score: MoatScore,
        grade: Grade,
        beta: float,
        veto_passed: bool,
        track_name: str,
    ) -> Tuple[float, float, str, float, int]:
        """执行仓位计算"""
        # 获取差异化及格线
        pass_score = PHASE2_PASS_SCORES[grade.value]

        # 获取护城河调整系数
        if moat_score.level.value == "强":
            moat_coefficient = 1.0
        elif moat_score.level.value == "中":
            moat_coefficient = 0.6
        else:
            moat_coefficient = 0.4

        # 获取行业已配置仓位
        industry_position = self.industry_positions.get(track_name, 0.0)

        # 计算
        base_pos, final_pos, decision, stop_loss, time_stop = self.position_calculator.calculate(
            financial_score=financial_score.total_score,
            pass_score=pass_score,
            valuation_conclusion=valuation.conclusion,
            valuation_coefficient=valuation.position_coefficient,
            moat_level=moat_score.level,
            moat_coefficient=moat_coefficient,
            grade=grade,
            beta=beta,
            veto_passed=veto_passed,
            industry_position=industry_position,
            surprise_score=financial_score.surprise_score,
        )

        # 更新行业仓位
        if final_pos > 0:
            self.industry_positions[track_name] = industry_position + final_pos

        return base_pos, final_pos, decision.value, stop_loss, time_stop

    def process_stock(
        self,
        phase1_result: Phase1Result,
        moat_data: dict,
        veto_data: dict,
        financial_data: dict,
        valuation_data: dict,
    ) -> Optional[Phase2Result]:
        """
        处理单只股票
        
        Returns:
            Phase2Result or None
        """
        stock = phase1_result.stock

        # 1. 护城河评估
        moat_score = self.run_moat_evaluation(stock, moat_data)

        # 2. 一票否决
        veto_result = self.run_veto_check(stock, veto_data, phase1_result.market_status)

        # 3. 财报评分
        financial_score = self.run_financial_scoring(stock, financial_data)

        # 4. 估值判断
        valuation = self.run_valuation(stock, valuation_data)

        # 5. 仓位计算
        base_pos, final_pos, decision, stop_loss, time_stop = self.run_position_calculation(
            financial_score, valuation, moat_score,
            phase1_result.phase1_score.grade, stock.beta,
            veto_result.passed, stock.track
        )

        # 构建结果
        result = Phase2Result(
            stock=stock,
            phase1_result=phase1_result,
            moat_score=moat_score,
            veto_result=veto_result,
            financial_score=financial_score,
            valuation=valuation,
            base_position=base_pos,
            final_position=final_pos,
            stop_loss=stop_loss,
            time_stop=time_stop,
            trigger_condition="突破5日均线+放量",  # 默认触发条件
            final_decision=decision,
        )

        return result

    def generate_output(
        self,
        results: List[Phase2Result],
        output_dir: str = "./data/phase2_output",
    ) -> str:
        """
        生成第二阶段输出CSV
        
        Returns:
            输出文件路径
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        # 构建数据
        data = []
        for result in results:
            stock = result.stock
            phase1 = result.phase1_result

            data.append({
                "代码": stock.code,
                "名称": stock.name,
                "第一阶段档位": phase1.phase1_score.grade.value,
                "第一阶段总分": phase1.phase1_score.total_score,
                "行业类型": self._get_industry_type(stock.track).value,
                "护城河得分": result.moat_score.total_score,
                "护城河结论": result.moat_score.level.value,
                "一票否决结果": "通过" if result.veto_result.passed else result.veto_result.triggered_item,
                "财报评分": result.financial_score.total_score,
                "超预期幅度": f"{result.financial_score.surprise_score/10*20:.1f}%",  # 简化显示
                "机构态度": "上调" if result.financial_score.institution_attitude_score == 10 else "维持" if result.financial_score.institution_attitude_score == 5 else "下调",
                "估值方法": result.valuation.method.value,
                "估值结论": result.valuation.conclusion.value,
                "历史分位点": f"{result.valuation.historical_percentile:.0f}%" if result.valuation.historical_percentile else "N/A",
                "估值仓位系数": f"{result.valuation.position_coefficient:.0%}",
                "建议基准仓位": f"{result.base_position:.0f}%",
                "最终仓位": f"{result.final_position:.0f}%",
                "止损位": f"{result.stop_loss:.0f}%",
                "时间止损": f"{result.time_stop}周",
                "触发条件": result.trigger_condition,
                "最终决策": result.final_decision.value,
                "备注": result.remark,
            })

        df = pd.DataFrame(data)

        # 保存CSV
        quarter = self._get_quarter()
        filename = f"{output_dir}/待购候选池_{quarter}.csv"
        df.to_csv(filename, index=False, encoding="utf-8-sig")

        print(f"✅ 已保存候选池: {filename}")
        print(f"   共 {len(df)} 只股票")
        if len(df) > 0:
            print(f"   买入候选: {len(df[df['最终决策']=='买入候选'])} 只")
            print(f"   观察: {len(df[df['最终决策']=='观察'])} 只")
            print(f"   剔除: {len(df[df['最终决策']=='剔除'])} 只")

        return filename

    def _get_quarter(self) -> str:
        """获取当前季度字符串"""
        now = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        return f"{now.year}Q{quarter}"

    def run(
        self,
        phase1_results: List[Phase1Result],
        stock_data: Dict[str, Dict],
        output_dir: str = "./data/phase2_output",
    ) -> Tuple[List[Phase2Result], str]:
        """
        执行第二阶段完整流程
        
        Args:
            phase1_results: 第一阶段结果列表
            stock_data: 股票详细数据 {code: {moat_data, veto_data, financial_data, valuation_data}}
            
        Returns:
            (第二阶段结果列表, 输出文件路径)
        """
        print("=" * 60)
        print("波段交易系统 - 第二阶段：基本面二次筛选")
        print("=" * 60)

        results = []

        # 按档位排序（第一档优先）
        sorted_results = sorted(
            phase1_results,
            key=lambda x: 0 if x.phase1_score.grade == Grade.FIRST else 1
        )

        for i, phase1_result in enumerate(sorted_results):
            stock = phase1_result.stock
            print(f"\n【{i+1}/{len(sorted_results)}】{stock.name}({stock.code})")

            # 获取股票数据
            data = stock_data.get(stock.code, {})

            # 处理
            result = self.process_stock(
                phase1_result,
                data.get("moat", {}),
                data.get("veto", {}),
                data.get("financial", {}),
                data.get("valuation", {}),
            )

            if result:
                results.append(result)
                print(f"   财报评分: {result.financial_score.total_score:.0f}分")
                print(f"   护城河: {result.moat_score.level.value}({result.moat_score.total_score:.0f}分)")
                print(f"   估值: {result.valuation.conclusion.value}")
                print(f"   最终仓位: {result.final_position:.0f}%")
                print(f"   决策: {result.final_decision.value}")

        # 生成输出
        print("\n【生成输出文件】")
        output_file = self.generate_output(results, output_dir)

        print("\n" + "=" * 60)
        print("第二阶段完成")
        print("=" * 60)

        return results, output_file
