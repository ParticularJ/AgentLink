"""
热点仓交易系统 - 主流程管道
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from models import StrategyType, StockScore, Position, MonitorSignal
from strategy_scorer import (
    FirstLimitUpScorer, LimitUpRetraceScorer, 
    SectorLeaderScorer, NewStockScorer
)
from portfolio_manager import PortfolioManager
from risk_manager import RiskManager


class HotSpotPipeline:
    """热点仓交易主流程管道"""
    
    def __init__(self, total_capital: float = 1000000.0):
        self.scorers = {
            StrategyType.FIRST_LIMIT_UP: FirstLimitUpScorer(),
            StrategyType.LIMIT_UP_RETRACE: LimitUpRetraceScorer(),
            StrategyType.SECTOR_LEADER: SectorLeaderScorer(),
            StrategyType.NEW_STOCK: NewStockScorer(),
        }
        self.portfolio = PortfolioManager(total_capital)
        self.risk = RiskManager()
    
    def scan_strategies(self, stocks_data: Dict[StrategyType, List[Dict]]) -> List[StockScore]:
        """
        扫描四大策略
        
        Args:
            stocks_data: {
                StrategyType.FIRST_LIMIT_UP: [stock_data1, stock_data2, ...],
                StrategyType.LIMIT_UP_RETRACE: [...],
                ...
            }
            
        Returns:
            所有评分结果列表
        """
        all_scores = []
        
        for strategy_type, stocks in stocks_data.items():
            scorer = self.scorers.get(strategy_type)
            if not scorer:
                continue
            
            for stock_data in stocks:
                score = scorer.score(stock_data)
                if score and score.veto_passed and score.total_score > 0:
                    all_scores.append(score)
        
        return all_scores
    
    def apply_multi_strategy_bonus(self, scores: List[StockScore]) -> List[StockScore]:
        """
        应用多策略加分
        
        同一股票命中多个策略时：
        - 2个策略：+3分
        - 3个策略：+5分
        - 4个策略：+6分
        """
        # 按股票代码分组
        code_groups: Dict[str, List[StockScore]] = {}
        for score in scores:
            if score.stock_code not in code_groups:
                code_groups[score.stock_code] = []
            code_groups[score.stock_code].append(score)
        
        # 处理多策略
        final_scores = []
        for code, group in code_groups.items():
            if len(group) == 1:
                final_scores.append(group[0])
            else:
                # 取最高分为基础
                best = max(group, key=lambda x: x.total_score)
                
                # 计算加分
                hit_count = len(group)
                if hit_count >= 4:
                    bonus = 6.0
                elif hit_count >= 3:
                    bonus = 5.0
                elif hit_count >= 2:
                    bonus = 3.0
                else:
                    bonus = 0.0
                
                # 更新分数
                best.multi_strategy_bonus = bonus
                best.total_score = min(best.total_score + bonus, 100.0)
                best.hit_strategies = [s.strategy_type for s in group]
                
                # 重新评估信号等级
                if best.total_score >= 90:
                    from models import SignalLevel
                    best.signal_level = SignalLevel.STRONG_BUY
                
                # 更新仓位建议
                best.suggested_position_pct = self.scorers[best.strategy_type]._get_position_pct(
                    best.total_score, best.strategy_type
                )
                
                final_scores.append(best)
        
        return final_scores
    
    def filter_and_rank(self, scores: List[StockScore], 
                       max_results: int = 3) -> List[StockScore]:
        """
        过滤并排序候选股票
        
        Args:
            scores: 评分列表
            max_results: 最大推荐数量
            
        Returns:
            排序后的候选列表
        """
        # 过滤掉不及格的
        qualified = [s for s in scores if s.signal_level.value in ["强烈买入", "买入"]]
        
        # 按总分排序
        qualified.sort(key=lambda x: x.total_score, reverse=True)
        
        # 限制次新股数量
        new_stock_count = sum(1 for s in qualified[:max_results] 
                             if s.strategy_type == StrategyType.NEW_STOCK)
        
        if new_stock_count > 1:
            # 只保留评分最高的1只次新股
            new_stocks = [s for s in qualified if s.strategy_type == StrategyType.NEW_STOCK]
            other_stocks = [s for s in qualified if s.strategy_type != StrategyType.NEW_STOCK]
            
            new_stocks.sort(key=lambda x: x.total_score, reverse=True)
            qualified = [new_stocks[0]] + other_stocks
            qualified.sort(key=lambda x: x.total_score, reverse=True)
        
        return qualified[:max_results]
    
    def generate_recommendations(self, stocks_data: Dict[StrategyType, List[Dict]],
                                max_results: int = 3) -> List[StockScore]:
        """
        生成每日推荐
        
        Returns:
            推荐列表（最多3只）
        """
        print("=" * 60)
        print("热点仓策略扫描")
        print("=" * 60)
        
        # 1. 扫描所有策略
        print("\n【步骤1】扫描四大策略...")
        all_scores = self.scan_strategies(stocks_data)
        print(f"   扫描到 {len(all_scores)} 只候选股")
        
        # 2. 多策略加分
        print("\n【步骤2】应用多策略加分...")
        scores = self.apply_multi_strategy_bonus(all_scores)
        
        # 统计多策略命中
        multi_strategy_count = sum(1 for s in scores if len(s.hit_strategies) > 1)
        print(f"   {multi_strategy_count} 只股票命中多个策略")
        
        # 3. 过滤排序
        print("\n【步骤3】过滤排序...")
        recommendations = self.filter_and_rank(scores, max_results)
        
        print(f"\n✅ 最终推荐 {len(recommendations)} 只股票:")
        for i, rec in enumerate(recommendations, 1):
            strategies = ", ".join([s.value for s in rec.hit_strategies]) if rec.hit_strategies else rec.strategy_type.value
            print(f"   {i}. {rec.stock_name}({rec.stock_code}) - {rec.total_score:.0f}分")
            print(f"      策略: {strategies}")
            print(f"      建议仓位: {rec.suggested_position_pct:.1%}")
            print(f"      买入时机: {rec.buy_timing}")
        
        return recommendations
    
    def execute_buy(self, stock_score: StockScore, entry_price: float) -> Optional[Position]:
        """
        执行买入
        
        Args:
            stock_score: 股票评分
            entry_price: 买入价格
            
        Returns:
            Position or None
        """
        print(f"\n【买入执行】{stock_score.stock_name}({stock_score.stock_code})")
        
        position = self.portfolio.open_position(stock_score, entry_price)
        
        if position:
            print(f"   ✅ 买入成功")
        else:
            print(f"   ❌ 买入失败")
        
        return position
    
    def monitor_positions(self, market_data: Dict[str, Dict]) -> List[MonitorSignal]:
        """
        监控所有持仓
        
        Args:
            market_data: {
                'stock_code': {
                    'current_price': float,
                    'intraday_data': {...},
                    'daily_data': {...},
                    'special_data': {...},
                }
            }
            
        Returns:
            所有监控信号
        """
        all_signals = []
        
        for position in self.portfolio.portfolio.positions:
            if position.status.value not in ["持仓中", "部分卖出"]:
                continue
            
            code = position.stock_code
            data = market_data.get(code, {})
            
            # 盘中监控
            if 'intraday_data' in data:
                signals = self.risk.intraday_monitor(position, data['intraday_data'])
                all_signals.extend(signals)
            
            # 收盘监控
            if 'daily_data' in data:
                signals = self.risk.daily_monitor(position, data['daily_data'])
                all_signals.extend(signals)
            
            # 特殊信号
            if 'special_data' in data:
                signals = self.risk.check_special_signals(position, data['special_data'])
                all_signals.extend(signals)
        
        return all_signals
    
    def execute_sell(self, signal: MonitorSignal) -> bool:
        """
        执行卖出信号
        
        Args:
            signal: 监控信号
            
        Returns:
            是否成功
        """
        if signal.action != "SELL":
            return False
        
        print(f"\n【卖出执行】{signal.stock_code}")
        print(f"   信号: {signal.signal_desc}")
        print(f"   建议卖出比例: {signal.suggested_ratio:.1%}")
        
        result = self.portfolio.sell_position(
            stock_code=signal.stock_code,
            sell_price=signal.price,
            sell_ratio=signal.suggested_ratio,
            reason=signal.signal_desc
        )
        
        return result is not None
    
    def daily_review(self):
        """每日复盘"""
        print("\n" + "=" * 60)
        print("每日复盘")
        print("=" * 60)
        
        # 更新当日盈亏
        self.portfolio.update_daily_pnl()
        
        # 获取组合摘要
        summary = self.portfolio.get_portfolio_summary()
        
        print(f"\n【组合状态】")
        print(f"   热点仓资金: {summary['热点仓资金']:,.0f}")
        print(f"   可用现金: {summary['可用现金']:,.0f}")
        print(f"   当前持仓: {summary['当前持仓数']}/{summary['最大持仓数']}")
        print(f"   当日盈亏: {summary['当日盈亏']:,.0f} ({summary['当日盈亏%']:+.2f}%)")
        print(f"   熔断状态: {summary['熔断状态']}")
        
        if summary['持仓列表']:
            print(f"\n【持仓明细】")
            for pos in summary['持仓列表']:
                print(f"   {pos['名称']}({pos['代码']})")
                print(f"      成本: {pos['成本']:.2f}, 现价: {pos['现价']:.2f}")
                print(f"      盈亏: {pos['盈亏%']:+.1f}%, 仓位: {pos['仓位']:.1%}")
        
        # 检查熔断
        if summary['当日盈亏%'] <= -self.portfolio.portfolio.daily_loss_limit_pct:
            print(f"\n🚨 触发二级熔断！强制清仓！")
            # 这里可以添加强制清仓逻辑
        
        return summary
    
    def run_daily_workflow(self, stocks_data: Dict[StrategyType, List[Dict]],
                          market_data: Dict[str, Dict] = None) -> Dict:
        """
        执行每日完整流程
        
        Returns:
            流程结果
        """
        print("\n" + "=" * 60)
        print("热点仓每日工作流程")
        print("=" * 60)
        
        # 1. 生成推荐
        recommendations = self.generate_recommendations(stocks_data)
        
        # 2. 监控持仓
        signals = []
        if market_data:
            print("\n【持仓监控】")
            signals = self.monitor_positions(market_data)
            
            if signals:
                print(f"   发现 {len(signals)} 个信号")
                for sig in signals:
                    print(f"   - {sig.signal_type}: {sig.signal_desc}")
                    
                    # 执行卖出
                    if sig.action == "SELL" and sig.urgency == "urgent":
                        self.execute_sell(sig)
            else:
                print("   无异常信号")
        
        # 3. 每日复盘
        summary = self.daily_review()
        
        return {
            "recommendations": recommendations,
            "signals": signals,
            "summary": summary
        }
