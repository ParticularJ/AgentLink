from typing import List, Optional, Tuple
from datetime import datetime

from models import Holding, Alert, RiskLevel, StockData, TechnicalIndicators, StockScore
from config import MA_CONFIG

class RiskController:
    """风险控制器"""
    
    def __init__(self):
        self.alerts = []
        
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