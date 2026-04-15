# skills/ma_bullish/scripts/backtest.py

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

class StrategyBacktest:
    """策略回测引擎"""
    
    def __init__(self, analyzer):
        self.analyzer = analyzer
        self.results = {}
        
    def run_backtest(self, stock_code: str, start_date: str, end_date: str) -> Dict:
        """运行回测"""
        print(f"开始回测{stock_code}...")
        
        # 获取历史数据
        df = self.analyzer._get_stock_data(stock_code)
        if df is None:
            return {'error': '无法获取数据'}
        
        # 过滤回测区间
        df['date'] = pd.to_datetime(df['date'])
        mask = (df['date'] >= start_date) & (df['date'] <= end_date)
        df = df[mask].reset_index(drop=True)
        
        # 计算指标
        df = self.analyzer._calculate_indicators(df)
        
        # 生成交易信号
        signals = self._generate_signals(df)
        
        # 模拟交易
        trades = self._simulate_trades(df, signals)
        
        # 计算绩效指标
        performance = self._calculate_performance(trades, df)
        
        # 生成报告
        report = self._generate_report(performance, trades)
        
        return report
    
    def _generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """生成买卖信号"""
        signals = pd.DataFrame(index=df.index)
        signals['signal'] = 0
        
        for i in range(self.analyzer.ma_long, len(df)):
            latest = df.iloc[i]
            prev = df.iloc[i-1]
            
            # 买入信号
            ma_bullish = (latest[f'ma{self.analyzer.ma_short}'] > 
                         latest[f'ma{self.analyzer.ma_mid}'] > 
                         latest[f'ma{self.analyzer.ma_long}'])
            price_above_ma = latest['close'] > latest[f'ma{self.analyzer.ma_long}']
            volume_surge = latest['volume'] > latest[f'volume_ma{self.analyzer.volume_ma}'] * 1.2
            
            if ma_bullish and price_above_ma and volume_surge and latest['close'] > prev['close']:
                signals.loc[i, 'signal'] = 1  # 买入信号
            
            # 卖出信号
            if i > 0 and signals.loc[i-1, 'signal'] == 1:
                # 止损：跌破20日线
                if latest['close'] < latest[f'ma{self.analyzer.ma_long}']:
                    signals.loc[i, 'signal'] = -1  # 卖出信号
                # 止盈：5日线死叉10日线
                elif (latest[f'ma{self.analyzer.ma_short}'] < latest[f'ma{self.analyzer.ma_mid}']):
                    signals.loc[i, 'signal'] = -1  # 卖出信号
        
        return signals
    
    def _simulate_trades(self, df: pd.DataFrame, signals: pd.DataFrame) -> List[Dict]:
        """模拟交易"""
        trades = []
        position = None
        
        for i, row in signals.iterrows():
            if row['signal'] == 1 and position is None:
                # 买入
                position = {
                    'entry_date': df.loc[i, 'date'],
                    'entry_price': df.loc[i, 'close'],
                    'shares': 1000  # 假设买入1000股
                }
            elif row['signal'] == -1 and position is not None:
                # 卖出
                exit_price = df.loc[i, 'close']
                profit = (exit_price - position['entry_price']) * position['shares']
                profit_pct = (exit_price - position['entry_price']) / position['entry_price'] * 100
                
                trades.append({
                    'entry_date': position['entry_date'],
                    'exit_date': df.loc[i, 'date'],
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'shares': position['shares'],
                    'profit': profit,
                    'profit_pct': profit_pct
                })
                position = None
        
        return trades
    
    def _calculate_performance(self, trades: List[Dict], df: pd.DataFrame) -> Dict:
        """计算绩效指标"""
        if not trades:
            return {
                'total_return': 0,
                'annual_return': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'win_rate': 0,
                'profit_loss_ratio': 0
            }
        
        # 总收益
        total_profit = sum(t['profit'] for t in trades)
        initial_capital = 100000  # 假设初始资金10万
        total_return = total_profit / initial_capital * 100
        
        # 年化收益
        days = (df['date'].iloc[-1] - df['date'].iloc[0]).days
        annual_return = total_return * 365 / days if days > 0 else 0
        
        # 胜率
        win_trades = [t for t in trades if t['profit'] > 0]
        win_rate = len(win_trades) / len(trades) * 100
        
        # 盈亏比
        avg_win = np.mean([t['profit_pct'] for t in win_trades]) if win_trades else 0
        lose_trades = [t for t in trades if t['profit'] <= 0]
        avg_loss = abs(np.mean([t['profit_pct'] for t in lose_trades])) if lose_trades else 1
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        # 最大回撤（简化计算）
        max_drawdown = 0
        peak = 0
        cumulative = 0
        for trade in trades:
            cumulative += trade['profit']
            if cumulative > peak:
                peak = cumulative
            drawdown = (peak - cumulative) / initial_capital * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # 夏普比率（简化）
        returns = [t['profit_pct'] for t in trades]
        sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if len(returns) > 1 and np.std(returns) > 0 else 0
        
        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'win_rate': win_rate,
            'profit_loss_ratio': profit_loss_ratio
        }
    
    def _generate_report(self, performance: Dict, trades: List[Dict]) -> Dict:
        """生成回测报告"""
        return {
            'performance': performance,
            'trades': trades,
            'trade_count': len(trades),
            'win_count': len([t for t in trades if t['profit'] > 0]),
            'loss_count': len([t for t in trades if t['profit'] <= 0])
        }


def main():
    """测试回测功能"""
    import sys
    sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/ma-bullish-strategy')
    from skills.ma_bullish.scripts.ma_analyzer import MABullishAnalyzer
    
    analyzer = MABullishAnalyzer()
    backtest = StrategyBacktest(analyzer)
    
    # 回测示例
    result = backtest.run_backtest('000001', '2023-01-01', '2023-12-31')
    print(f"回测结果: {result}")


if __name__ == '__main__':
    main()