"""
核心仓交易系统 - 主流程管道
整合：宏观过滤 → 赛道筛选 → 个股初筛 → 财报验证 → 买点判断 → 持仓监控
严格遵循《核心仓策略 V3.0》四份设计文档
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from models import (
    MacroLiquidity, MarketContext, SectorRating, SectorLifecycle,
    StockInitialScore, StockSecondaryScore, CorePosition,
    BuyPointSignal, MonitorSignal, SignalLevel
)
from macro_filter import MacroFilter
from sector_scorer import SectorScorer
from initial_scorer import InitialScorer
from secondary_scorer import SecondaryScorer
from buy_signal import BuySignalDetector
from position_monitor import PositionMonitor
from portfolio_manager import CorePortfolioManager


class CorePositionPipeline:
    """核心仓交易主流程管道"""

    def __init__(self, total_capital: float = 1000000.0, core_ratio: float = 0.50):
        # 各模块初始化
        self.macro_filter = MacroFilter()
        self.sector_scorer = SectorScorer()
        self.initial_scorer = InitialScorer()
        self.secondary_scorer = SecondaryScorer()
        self.buy_detector = BuySignalDetector()
        self.monitor = PositionMonitor()
        self.portfolio = CorePortfolioManager(total_capital, core_ratio)

        # 状态保存
        self.macro: Optional[MacroLiquidity] = None
        self.market: Optional[MarketContext] = None
        self.sector_pool: List[SectorRating] = []
        self.initial_pool: List[StockInitialScore] = []
        self.candidate_pool: List[StockSecondaryScore] = []

    # ========== 第一阶段：选股 ==========

    def phase1_macro_check(self, macro_data: Dict) -> Tuple[bool, str, float]:
        """
        宏观流动性检查

        Returns:
            (是否可继续, 原因, 胜率调整)
        """
        print("\n" + "=" * 60)
        print("【Phase 1】宏观流动性评估")
        print("=" * 60)

        self.macro = self.macro_filter.evaluate(macro_data)
        env = self.macro.environment

        print(f"   环境判断: {env.value}")
        print(f"   社融增速: {self.macro.social_financing_growth}%")
        print(f"   10Y国债: {self.macro.treasury_yield_10y}%")
        print(f"   风险溢价: {self.macro.risk_premium}%")

        can_proceed, reason, adjustment = self.macro_filter.can_proceed(self.macro)
        print(f"   结论: {reason}")

        return can_proceed, reason, adjustment

    def phase1_sector_screen(self, sectors_data: List[Dict]) -> List[SectorRating]:
        """
        赛道筛选

        Args:
            sectors_data: 赛道数据列表

        Returns:
            符合条件的赛道列表
        """
        print("\n【Phase 1-2】赛道筛选")

        all_sectors = []
        for sector_data in sectors_data:
            rating = self.sector_scorer.score(sector_data, self.macro)
            if rating:
                all_sectors.append(rating)
                print(f"   {rating.sector_name}: {rating.rating}级, "
                      f"生命周期{rating.lifecycle.value}, "
                      f"渗透率{rating.penetration_rate}%, "
                      f"配置上限{rating.max_allocation_pct:.0%}")

        # 筛选目标赛道（爆发初期/中期）
        target_sectors = self.sector_scorer.filter_target_sectors(all_sectors)
        self.sector_pool = target_sectors

        print(f"   目标赛道: {len(target_sectors)}/{len(all_sectors)}个")

        return target_sectors

    def phase1_initial_screen(self, stocks_data: List[Dict],
                              target_pool_size: int = 60) -> List[StockInitialScore]:
        """
        个股初筛

        Args:
            stocks_data: 股票数据列表
            target_pool_size: 目标池大小

        Returns:
            初筛股票池
        """
        print("\n【Phase 1-3】个股初筛")

        all_scores = []
        veto_count = 0

        for stock_data in stocks_data:
            score = self.initial_scorer.score(stock_data)
            if score:
                if score.veto_passed:
                    all_scores.append(score)
                else:
                    veto_count += 1

        # 过滤排序
        self.initial_pool = self.initial_scorer.filter_and_rank(all_scores, target_pool_size)

        print(f"   初筛通过: {len(self.initial_pool)}只")
        print(f"   一票否决: {veto_count}只")
        print(f"   初筛池目标: {target_pool_size}只")

        return self.initial_pool

    # ========== 第二阶段：二次筛选 ==========

    def phase2_secondary_screen(self,
                                financial_reports: Dict[str, Dict],
                                verifications: Dict[str, Dict]) -> List[StockSecondaryScore]:
        """
        财报验证与二次筛选

        Args:
            financial_reports: {stock_code: report_data}
            verifications: {stock_code: verification_data}

        Returns:
            二次筛选结果
        """
        print("\n" + "=" * 60)
        print("【Phase 2】财报验证与二次筛选")
        print("=" * 60)

        from models import FinancialReport, EarningsVerification

        # 转换数据
        reports = {}
        for code, data in financial_reports.items():
            reports[code] = FinancialReport(**data)

        verifs = {}
        for code, data in verifications.items():
            verifs[code] = EarningsVerification(**data)

        # 执行二筛
        results = self.secondary_scorer.secondary_screen(
            self.initial_pool, reports, verifs
        )

        # 过滤买入候选
        candidates = self.secondary_scorer.filter_buy_candidates(results, min_score=82)
        self.candidate_pool = candidates

        print(f"   财报验证通过: {len(results)}只")
        print(f"   买入候选池: {len(candidates)}只")

        for i, c in enumerate(candidates, 1):
            print(f"   {i}. {c.stock_name}({c.stock_code}): "
                  f"综合{c.total_score:.0f}分 [{c.signal_level.value}] "
                  f"仓位上限{c.max_position_pct:.0%}")

        return candidates

    # ========== 第三阶段：买入时机判断 ==========

    def phase3_buy_timing(self,
                          market_data: Dict,
                          tech_data_map: Dict[str, Dict],
                          stock_fundamentals: Dict[str, Dict]) -> List[Tuple[StockSecondaryScore, BuyPointSignal]]:
        """
        每日买入时机判断

        Args:
            market_data: 大盘数据
            tech_data_map: {stock_code: tech_data}
            stock_fundamentals: {stock_code: fundamental_data}

        Returns:
            [(候选股, 买点信号)] 列表
        """
        print("\n" + "=" * 60)
        print("【Phase 3】每日买入时机判断")
        print("=" * 60)

        # 大盘环境检查
        self.market = MarketContext(**market_data)
        can_trade, reason, market_coeff = self.buy_detector.check_market_environment(self.market)

        print(f"   大盘状态: {self.market.status.value}")
        print(f"   仓位系数: {market_coeff}")
        print(f"   交易许可: {'是' if can_trade else '否'} ({reason})")

        if not can_trade:
            return []

        # 识别买点
        buy_signals = []
        for candidate in self.candidate_pool:
            code = candidate.stock_code
            tech_data = tech_data_map.get(code)

            if not tech_data:
                continue

            # 检测买点
            buy_point = self.buy_detector.detect_buy_point(
                code, candidate.stock_name, tech_data
            )

            if not buy_point:
                continue

            # 计算仓位
            position_pct = self.buy_detector.calculate_position_size(
                candidate, buy_point, self.market
            )

            if position_pct <= 0:
                continue

            # 最终确认清单
            fundamentals = stock_fundamentals.get(code, {})
            checklist = self.buy_detector.final_checklist(fundamentals, buy_point)

            if not self.buy_detector.can_execute_buy(checklist):
                print(f"   ❌ {candidate.stock_name}: 六项确认未全通过")
                continue

            buy_signals.append((candidate, buy_point))
            print(f"   ✅ {candidate.stock_name}: {buy_point.quality.value} "
                  f"建议仓位{position_pct:.1%}")

        print(f"   有效买点: {len(buy_signals)}个")

        return buy_signals

    def execute_buy(self,
                   candidate: StockSecondaryScore,
                   buy_point: BuyPointSignal,
                   entry_price: float,
                   atr: float = 0) -> Optional[CorePosition]:
        """
        执行买入

        Args:
            candidate: 候选股
            buy_point: 买点信号
            entry_price: 买入价格
            atr: ATR值

        Returns:
            CorePosition or None
        """
        print(f"\n【买入执行】{candidate.stock_name}({candidate.stock_code})")

        position = self.portfolio.open_position(
            candidate, buy_point, entry_price, atr
        )

        if position:
            print(f"   ✅ 买入成功")
        else:
            print(f"   ❌ 买入失败")

        return position

    # ========== 第四阶段：持仓监控 ==========

    def phase4_monitor(self,
                      daily_tech_data: Dict[str, Dict],
                      weekly_fundamental_data: Dict[str, Dict],
                      market_data: Dict) -> List[MonitorSignal]:
        """
        持仓监控

        Args:
            daily_tech_data: {stock_code: daily_tech_data}
            weekly_fundamental_data: {stock_code: weekly_fundamental_data}
            market_data: 大盘数据

        Returns:
            所有监控信号
        """
        print("\n" + "=" * 60)
        print("【Phase 4】持仓监控")
        print("=" * 60)

        all_signals = []
        active_positions = [p for p in self.portfolio.portfolio.positions
                           if p.status.value in ["持仓中", "部分卖出"]]

        if not active_positions:
            print("   当前无持仓")
            return []

        # 每日技术监控
        print("\n   【每日技术监控】")
        for position in active_positions:
            code = position.stock_code
            data = daily_tech_data.get(code, {})

            from models import DailyTechMonitor
            monitor = DailyTechMonitor(stock_code=code, **data)

            signals = self.monitor.daily_tech_monitor(position, monitor)
            all_signals.extend(signals)

            # 止损检查
            stop_signals = self.monitor.check_stop_loss(
                position, monitor.close_price, data.get('ma60', 0)
            )
            all_signals.extend(stop_signals)

            # 止盈检查
            market = MarketContext(**market_data)
            profit_signals = self.monitor.check_take_profit(
                position, monitor.close_price, market
            )
            all_signals.extend(profit_signals)

        # 每周基本面监控
        print("\n   【每周基本面监控】")
        for position in active_positions:
            code = position.stock_code
            data = weekly_fundamental_data.get(code, {})

            from models import WeeklyFundamentalMonitor
            monitor = WeeklyFundamentalMonitor(stock_code=code, **data)

            signals = self.monitor.weekly_fundamental_monitor(position, monitor)
            all_signals.extend(signals)

        # 组合层面风控
        print("\n   【组合风控】")
        sector_positions = self.portfolio.get_sector_positions()
        vix = market_data.get('vix', 20)
        risk_signals = self.monitor.check_portfolio_risk(
            active_positions, sector_positions, vix
        )
        all_signals.extend(risk_signals)

        # 输出信号
        if all_signals:
            print(f"\n   发现 {len(all_signals)} 个信号:")
            for sig in all_signals:
                print(f"   - [{sig.signal_type}] {sig.signal_desc} "
                      f"(紧急度: {sig.urgency})")
        else:
            print("   无异常信号")

        return all_signals

    def execute_signals(self, signals: List[MonitorSignal]) -> Dict:
        """
        执行监控信号

        Returns:
            执行结果统计
        """
        results = {"executed": 0, "failed": 0, "details": []}

        for signal in signals:
            success = self.portfolio.execute_signal(signal)
            if success:
                results["executed"] += 1
                results["details"].append(f"✅ {signal.signal_type}: {signal.stock_code}")
            else:
                results["failed"] += 1
                results["details"].append(f"❌ {signal.signal_type}: {signal.stock_code}")

        return results

    # ========== 完整工作流 ==========

    def run_full_pipeline(self,
                         macro_data: Dict,
                         sectors_data: List[Dict],
                         stocks_data: List[Dict],
                         financial_reports: Dict[str, Dict],
                         verifications: Dict[str, Dict],
                         market_data: Dict,
                         tech_data_map: Dict[str, Dict],
                         stock_fundamentals: Dict[str, Dict]) -> Dict:
        """
        执行完整选股+买入流程

        Returns:
            流程结果
        """
        print("\n" + "=" * 60)
        print("核心仓策略 V3.0 - 完整工作流程")
        print("=" * 60)

        # Phase 1: 宏观+赛道+初筛
        can_proceed, reason, adjustment = self.phase1_macro_check(macro_data)
        if not can_proceed:
            return {"status": "blocked", "reason": reason, "phase": "macro"}

        self.phase1_sector_screen(sectors_data)
        self.phase1_initial_screen(stocks_data)

        # Phase 2: 财报验证
        candidates = self.phase2_secondary_screen(financial_reports, verifications)

        # Phase 3: 买入时机
        buy_signals = self.phase3_buy_timing(market_data, tech_data_map, stock_fundamentals)

        return {
            "status": "success",
            "macro_environment": self.macro.environment.value,
            "target_sectors": [s.sector_name for s in self.sector_pool],
            "initial_pool_size": len(self.initial_pool),
            "candidate_pool_size": len(candidates),
            "buy_signals": len(buy_signals),
            "buy_details": [
                {
                    "code": c.stock_code,
                    "name": c.stock_name,
                    "quality": bp.quality.value,
                    "position_pct": bp.suggested_position_pct
                }
                for c, bp in buy_signals
            ]
        }

    def run_daily_monitor(self,
                         daily_tech_data: Dict[str, Dict],
                         weekly_fundamental_data: Dict[str, Dict],
                         market_data: Dict) -> Dict:
        """
        执行每日监控流程

        Returns:
            监控结果
        """
        print("\n" + "=" * 60)
        print("核心仓策略 V3.0 - 每日监控")
        print("=" * 60)

        # 持仓监控
        signals = self.phase4_monitor(
            daily_tech_data, weekly_fundamental_data, market_data
        )

        # 执行信号
        if signals:
            results = self.execute_signals(signals)
        else:
            results = {"executed": 0, "failed": 0, "details": []}

        # 组合摘要
        summary = self.portfolio.get_portfolio_summary()

        return {
            "signals_count": len(signals),
            "executed": results["executed"],
            "failed": results["failed"],
            "portfolio_summary": summary
        }

    def get_portfolio_status(self) -> Dict:
        """获取当前组合状态"""
        return self.portfolio.get_portfolio_summary()
