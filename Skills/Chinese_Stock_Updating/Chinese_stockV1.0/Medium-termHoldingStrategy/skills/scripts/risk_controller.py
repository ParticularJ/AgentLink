from typing import List, Optional, Tuple

from models import Holding, Alert, RiskLevel, TechnicalIndicators, StockScore
from config import MA_CONFIG

class RiskController:
    """风险控制器"""
    
    def __init__(self):
        self.alerts = []
        
    # ── 统一止损入口（2026-10 合并）────────────────────────────
    # 背景：多级止损逻辑原先在 stop_loss_engine.py 里，但**从未被生产入口调用**
    # （main.py 只用 check_ma_breakdown），是死代码。现合并进 RiskController，
    # 使优先级 1~9 的止损规则真正生效，同时保留原有均线跌破预警不变。
    def check_stop_loss(self, holding_state, current_price, current_data, tech,
                        df_history, today_str, n_multiplier: float = 2.0):
        """按优先级 1→9 检查单只持仓，返回 StopLossEngine 的 Action。

        这是**权威的止损判定**（含分级减仓、时间止损、移动止盈等）；
        check_ma_breakdown 仅作为均线跌破的辅助预警保留。
        """
        engine = self._stop_engine(n_multiplier)
        return engine.check(holding_state, current_price, current_data, tech,
                            df_history, today_str)

    def _stop_engine(self, n_multiplier: float = 2.0):
        """懒构造 StopLossEngine（需要 MarketSentiment，失败时不阻断主流程）。"""
        try:
            from stop_loss_engine import StopLossEngine
            from market_sentiment import MarketSentiment
            sentiment = getattr(self, "_sentiment", None)
            if sentiment is None:
                sentiment = MarketSentiment()
                self._sentiment = sentiment
            return StopLossEngine(sentiment, n_multiplier)
        except Exception as e:
            raise RuntimeError(f"止损引擎不可用：{e}") from e

    def check_ma_breakdown(self, holding: Holding, current_price: float,
                           tech: TechnicalIndicators, volume_ratio: float = 1.0) -> Optional[Alert]:
        """检查均线跌破预警"""
        alerts = []
       

        # 检查5日线
        if current_price < tech.ma5 :  # 评分过低的直接走评分预警，不再叠加均线预警
            # 过滤假突破: 检查是否连续3日
            ma5_config = MA_CONFIG["ma5"]
            alert = Alert(
                code=holding.code,
                name=holding.name,
                risk_level=RiskLevel.MEDIUM,
                message=ma5_config["message"],
                action=ma5_config["action"],
                current_price=current_price,
                ma_value=tech.ma5
            )
            alerts.append(alert)
        
        # 检查10日线
        if current_price < tech.ma10 :  # 评分过低的直接走评分预警，不再叠加均线预警
            ma10_config = MA_CONFIG["ma10"]
            # 缩量下跌可能是洗盘
            if volume_ratio < 0.8:
                action = "观察,可能是洗盘" + ma10_config["action"]
            else:
                action = ma10_config["action"]
            alert = Alert(
                code=holding.code,
                name=holding.name,
                risk_level=RiskLevel.HIGH,
                message=ma10_config["message"] ,
                action=action,
                current_price=current_price,
                ma_value=tech.ma10
            )
            alerts.append(alert)
        
        # 返回最严重的预警
        if alerts:
            return max(alerts, key=lambda x: x.risk_level.value)
        return None
    
    def check_rebalance_signal(self, holdings: List[Holding], 
                               recommend_stocks: List[Tuple[str, StockScore]]) -> Optional[dict]:
        """检查调仓信号"""
        if not holdings or not recommend_stocks:
            return None
        
        # 找出持仓中评分最低的
        min_holding = min(holdings, key=lambda x: x.score)
        
        # 找出荐股中评分最高的
        best_recommend = max(recommend_stocks, key=lambda x: x[1].total_score)
        best_score = best_recommend[1].total_score
        
        # 计算差距
        score_gap = best_score - min_holding.score
        
        from config import REBALANCE_THRESHOLD, BUY_THRESHOLD
        
        # 判断是否需要调仓
        if best_score >= BUY_THRESHOLD and score_gap >= REBALANCE_THRESHOLD:
            return {
                "need_rebalance": True,
                "sell_holding": min_holding,
                "buy_code": best_recommend[0],
                "buy_score": best_score,
                "sell_score": min_holding.score,
                "score_gap": score_gap,
                "action": "调仓换股"
            }
        elif best_score >= BUY_THRESHOLD:
            return {
                "need_rebalance": False,
                "action": "建仓"
            }
        
        return {"need_rebalance": False, "action": "持有"}