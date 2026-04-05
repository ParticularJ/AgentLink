# skills/ma_bullish/scripts/signal_generator.py

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime

class SignalGenerator:
    """买卖信号生成器"""
    
    def __init__(self, analyzer):
        self.analyzer = analyzer
        
    def generate_buy_signal(self, stock_data: pd.DataFrame) -> Dict:
        """生成买入信号详情"""
        latest = stock_data.iloc[-1]
        
        signal = {
            'signal_type': 'BUY',
            'signal_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'entry_price': latest['close'],
            'position_size': self._calculate_position_size(stock_data),
            'stop_loss': self._calculate_dynamic_stop(stock_data),
            'take_profit': self._calculate_take_profit(stock_data),
            'confidence': self._calculate_confidence(stock_data)
        }
        
        return signal
    
    def _calculate_position_size(self, df: pd.DataFrame) -> float:
        """计算建议仓位比例"""
        # 基于信号强度计算仓位
        volatility = df['pct_change'].std() * np.sqrt(252)
        
        if volatility < 0.3:
            position = 0.3  # 低波动，30%仓位
        elif volatility < 0.5:
            position = 0.2  # 中波动，20%仓位
        else:
            position = 0.1  # 高波动，10%仓位
        
        return position
    
    def _calculate_dynamic_stop(self, df: pd.DataFrame) -> float:
        """计算动态止损价"""
        latest = df.iloc[-1]
        # 使用ATR动态止损
        atr = latest['atr'] if 'atr' in latest else latest['close'] * 0.05
        return latest['close'] - atr * 2
    
    def _calculate_take_profit(self, df: pd.DataFrame) -> Dict:
        """计算止盈目标"""
        latest = df.iloc[-1]
        atr = latest['atr'] if 'atr' in latest else latest['close'] * 0.05
        
        return {
            'target1': latest['close'] + atr * 2,  # 第一目标：2倍ATR
            'target2': latest['close'] + atr * 3,  # 第二目标：3倍ATR
            'target3': latest['close'] + atr * 4   # 第三目标：4倍ATR
        }
    
    def _calculate_confidence(self, df: pd.DataFrame) -> float:
        """计算信号置信度"""
        # 基于多个技术指标计算置信度
        latest = df.iloc[-1]
        
        confidence = 0.5  # 基础置信度
        
        # RSI判断
        if 'rsi' in latest:
            if 40 < latest['rsi'] < 70:
                confidence += 0.1
        
        # MACD判断
        if 'macd' in latest and 'macd_signal' in latest:
            if latest['macd'] > latest['macd_signal']:
                confidence += 0.1
        
        # 成交量确认
        if latest['volume'] > latest[f'volume_ma{self.analyzer.volume_ma}'] * 1.2:
            confidence += 0.1
        
        return min(confidence, 0.95)
    
    def generate_sell_signal(self, position: Dict, current_price: float) -> Dict:
        """生成卖出信号"""
        signal = {
            'signal_type': 'SELL',
            'signal_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'current_price': current_price,
            'reason': ''
        }
        
        # 检查止损
        if current_price <= position['stop_loss']:
            signal['reason'] = '止损触发'
            signal['signal_type'] = 'STOP_LOSS'
        
        # 检查止盈
        elif current_price >= position['take_profit']['target1']:
            signal['reason'] = '止盈目标达成'
            # 可以分批止盈
        
        # 检查趋势反转
        elif self._check_trend_reversal(position, current_price):
            signal['reason'] = '趋势反转信号'
        
        return signal
    
    def _check_trend_reversal(self, position: Dict, current_price: float) -> bool:
        """检查趋势反转"""
        # 检查是否跌破关键均线
        if 'ma20' in position:
            if current_price < position['ma20']:
                return True
        
        return False