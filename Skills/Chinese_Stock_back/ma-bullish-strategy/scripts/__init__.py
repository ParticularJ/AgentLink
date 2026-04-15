# ~/.openclaw/workspace/skills/ma-bullish-strategy/scripts/__init__.py

"""
均线多头排列策略模块
提供趋势跟踪交易信号分析
"""

from .ma_analyzer import MABullishAnalyzer
from .signal_generator import SignalGenerator
from .risk_manager import RiskManager
from .backtest import StrategyBacktest
from .report_generator import ReportGenerator

__all__ = [
    'MABullishAnalyzer',
    'SignalGenerator', 
    'RiskManager',
    'StrategyBacktest',
    'ReportGenerator'
]

__version__ = '1.0.0'
__author__ = 'QuantTeam'
__description__ = '基于均线多头排列的趋势跟踪策略'