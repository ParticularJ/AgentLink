"""
核心仓交易系统 - 每日买入时机判断
严格遵循《核心仓策略 V3.0》第三份设计文档
"""
from typing import List, Dict, Optional, Tuple
from models import (
    MarketContext, MarketStatus, StockSecondaryScore,
    BuyPointSignal, BuyPointType, BuyPointQuality
)


class BuySignalDetector:
    """买点识别器"""
    
    def __init__(self):
        self.buy_point_types = [
            BuyPointType.PULLBACK_MA20,      # 首选
            BuyPointType.EARNINGS_GAP_PULLBACK,  # 次选
            BuyPointType.PULLBACK_MA60,      # 次级
            BuyPointType.BREAKOUT_CONSOLIDATION  # 谨慎
        ]
    
    def check_market_environment(self, market: MarketContext) -> Tuple[bool, str, float]:
        """
        检查大盘环境
        
        Returns:
            (是否可建仓, 说明, 仓位系数)
        """
        status = market.status
        coeff = market.position_coefficient
        
        if status == MarketStatus.STRONG:
            return True, "强势市场：正常建仓", coeff
        elif status == MarketStatus.OSCILLATING:
            return True, "震荡市场：半仓试探", coeff
        else:
            return False, "弱势市场：暂停建仓", coeff
    
    def detect_buy_point(self, 
                        stock_code: str,
                        stock_name: str,
                        tech_data: Dict) -> Optional[BuyPointSignal]:
        """
        识别买点信号
        
        Args:
            tech_data: {
                'ma20': float, 'ma60': float, 'ma120': float,
                'ma20_trend': str, 'ma60_trend': str, 'ma120_trend': str,  # 'up'/'down'
                'recent_high': float, 'current_price': float,
                'volume': float, 'volume_ma20': float,
                'days_not_new_low': int,  # 连续不创新低天数
                'rsi': float,
                'atr_14_pct': float,  # 14日ATR百分比
                'is_pullback_ma20': bool,  # 是否回踩20日线
                'is_pullback_ma60': bool,
                'is_earnings_gap': bool,   # 是否净利润断层
                'is_breakout': bool,       # 是否盘整突破
            }
            
        Returns:
            BuyPointSignal or None
        """
        current_price = tech_data.get('current_price', 0)
        recent_high = tech_data.get('recent_high', current_price)
        
        # 计算回调幅度
        pullback_pct = (recent_high - current_price) / recent_high * 100 if recent_high > 0 else 0
        
        # 判断买点类型
        buy_point_type = self._classify_buy_point_type(tech_data)
        if not buy_point_type:
            return None
        
        # 检查必要条件
        ma_alignment = self._check_ma_alignment(tech_data)
        volume_shrink = self._check_volume_shrink(tech_data)
        stabilize = tech_data.get('days_not_new_low', 0) >= 2
        
        # 检查加分项
        rsi = tech_data.get('rsi', 50)
        rsi_pass = 35 <= rsi <= 50
        atr_pass = tech_data.get('atr_14_pct', 100) < 5
        
        # 判断买点质量
        bonus_count = sum([rsi_pass, atr_pass])
        if ma_alignment and 5 <= pullback_pct <= 12 and volume_shrink and stabilize:
            if bonus_count >= 2:
                quality = BuyPointQuality.IDEAL
            elif bonus_count >= 1:
                quality = BuyPointQuality.NORMAL
            else:
                quality = BuyPointQuality.MARGINAL
        else:
            return None  # 不满足必要条件
        
        return BuyPointSignal(
            stock_code=stock_code,
            stock_name=stock_name,
            buy_point_type=buy_point_type,
            quality=quality,
            ma_alignment_pass=ma_alignment,
            pullback_pct=pullback_pct,
            volume_shrink_pass=volume_shrink,
            price_stabilize_pass=stabilize,
            rsi_score=rsi if rsi_pass else 0,
            atr_volatility_pass=atr_pass
        )
    
    def _classify_buy_point_type(self, tech_data: Dict) -> Optional[BuyPointType]:
        """分类买点类型"""
        if tech_data.get('is_pullback_ma20', False):
            return BuyPointType.PULLBACK_MA20
        elif tech_data.get('is_earnings_gap', False):
            return BuyPointType.EARNINGS_GAP_PULLBACK
        elif tech_data.get('is_pullback_ma60', False):
            return BuyPointType.PULLBACK_MA60
        elif tech_data.get('is_breakout', False):
            return BuyPointType.BREAKOUT_CONSOLIDATION
        return None
    
    def _check_ma_alignment(self, tech_data: Dict) -> bool:
        """检查均线排列：20日>60日>120日，且全部向上"""
        ma20 = tech_data.get('ma20', 0)
        ma60 = tech_data.get('ma60', 0)
        ma120 = tech_data.get('ma120', 0)
        
        alignment = ma20 > ma60 > ma120
        
        trends = [
            tech_data.get('ma20_trend', 'down') == 'up',
            tech_data.get('ma60_trend', 'down') == 'up',
            tech_data.get('ma120_trend', 'down') == 'up'
        ]
        
        return alignment and all(trends)
    
    def _check_volume_shrink(self, tech_data: Dict) -> bool:
        """检查缩量：成交量 < 20日均量 × 0.6"""
        volume = tech_data.get('volume', 0)
        volume_ma20 = tech_data.get('volume_ma20', 1)
        
        if volume_ma20 <= 0:
            return False
        
        return volume < volume_ma20 * 0.6
    
    def calculate_position_size(self,
                               candidate: StockSecondaryScore,
                               buy_point: BuyPointSignal,
                               market: MarketContext) -> float:
        """
        计算建议仓位
        
        公式：建议仓位 = 基准仓位 × 综合评分系数 × 技术面系数 × 大盘系数
        
        Args:
            candidate: 二次筛选评分
            buy_point: 买点信号
            market: 大盘环境
            
        Returns:
            建议仓位比例（相对核心仓资金）
        """
        # 基准仓位
        base_position = candidate.max_position_pct
        
        # 综合评分系数
        score = candidate.total_score
        if score >= 90:
            score_coeff = 1.0
        elif score >= 82:
            score_coeff = 0.7
        else:
            score_coeff = 0.0
        
        # 技术面系数
        quality_map = {
            BuyPointQuality.IDEAL: 1.0,
            BuyPointQuality.NORMAL: 0.6,
            BuyPointQuality.MARGINAL: 0.3
        }
        tech_coeff = quality_map.get(buy_point.quality, 0.3)
        
        # 大盘系数
        market_coeff = market.position_coefficient
        
        # 计算
        suggested = base_position * score_coeff * tech_coeff * market_coeff
        
        # 更新到买点信号
        buy_point.suggested_position_pct = suggested
        
        return suggested
    
    def final_checklist(self, 
                       stock_data: Dict,
                       buy_point: BuyPointSignal) -> Dict[str, bool]:
        """
        最终确认清单（六项全通过）
        
        Args:
            stock_data: {
                'penetration_rate': float,      # 渗透率%
                'revenue_growth': float,        # 上季营收增速%
                'profit_growth': float,         # 上季利润增速%
                'analyst_coverage': int,        # 卖方覆盖数
                'expectation_conservative': bool, # 预期是否保守
                'peg_ratio': float,             # PEG
                'is_credit_contraction': bool,  # 是否信用收缩期
            }
            
        Returns:
            {检查项: 是否通过}
        """
        checklist = {}
        
        # 1. 产业生命周期：渗透率5%-20%
        penetration = stock_data.get('penetration_rate', 0)
        checklist['产业生命周期'] = 5 <= penetration <= 20
        
        # 2. 业绩验证：上季营收>25%，利润>40%
        revenue = stock_data.get('revenue_growth', 0)
        profit = stock_data.get('profit_growth', 0)
        checklist['业绩验证'] = revenue > 25 and profit > 40
        
        # 3. 预期差：卖方覆盖<12家或预期保守
        coverage = stock_data.get('analyst_coverage', 999)
        conservative = stock_data.get('expectation_conservative', False)
        checklist['预期差'] = coverage < 12 or conservative
        
        # 4. 技术面：多头趋势+买点信号（已验证）
        checklist['技术面'] = buy_point.all_necessary_passed
        
        # 5. 估值安全垫：PEG<1.5
        peg = stock_data.get('peg_ratio', 999)
        checklist['估值安全垫'] = peg < 1.5
        
        # 6. 宏观环境：非信用收缩期
        checklist['宏观环境'] = not stock_data.get('is_credit_contraction', False)
        
        buy_point.checklist = checklist
        
        return checklist
    
    def can_execute_buy(self, checklist: Dict[str, bool]) -> bool:
        """检查是否可以执行买入（六项全通过）"""
        return all(checklist.values())
    
    def get_batch_strategy(self, buy_point: BuyPointSignal) -> List[Dict]:
        """
        获取分批买入策略
        
        Returns:
            [{'batch': int, 'ratio': float, 'condition': str, 'fail_action': str}]
        """
        quality = buy_point.quality
        
        if quality == BuyPointQuality.IDEAL:
            # 理想买点：直接建仓50%
            return [
                {'batch': 1, 'ratio': 0.50, 'condition': '买点信号当日', 'fail_action': '5日跌幅>5%则暂停'},
                {'batch': 2, 'ratio': 0.30, 'condition': '站稳5日线+缩量调整3-5日', 'fail_action': '跌破首笔成本×0.95则止损'},
                {'batch': 3, 'ratio': 0.20, 'condition': '突破近期高点+放量', 'fail_action': '3日跌回平台则取消'}
            ]
        elif quality == BuyPointQuality.NORMAL:
            # 一般买点：建仓30%
            return [
                {'batch': 1, 'ratio': 0.30, 'condition': '买点信号当日', 'fail_action': '5日跌幅>5%则暂停'},
                {'batch': 2, 'ratio': 0.30, 'condition': '确认后加仓', 'fail_action': '跌破首笔成本×0.95则止损'},
                {'batch': 3, 'ratio': 0.20, 'condition': '突破近期高点+放量', 'fail_action': '3日跌回平台则取消'}
            ]
        else:
            # 勉强买点：建仓20%
            return [
                {'batch': 1, 'ratio': 0.20, 'condition': '买点信号当日', 'fail_action': '严格止损'},
                {'batch': 2, 'ratio': 0.20, 'condition': '确认后加仓', 'fail_action': '跌破首笔成本×0.95则止损'}
            ]
