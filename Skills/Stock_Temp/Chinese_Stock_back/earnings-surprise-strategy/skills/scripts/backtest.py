# earnings-surprise-strategy/skills/scripts/backtest.py

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from .data_fetcher import EarningsDataFetcher
from .surprise_analyzer import SurpriseAnalyzer

class EarningsBacktest:
    """财报超预期策略回测"""
    
    def __init__(self):
        self.data_fetcher = EarningsDataFetcher()
        self.surprise_analyzer = SurpriseAnalyzer()
        self.initial_capital = 1000000
        self.commission = 0.0003
        self.slippage = 0.0001
        
    def run_backtest(self, start_date: str, end_date: str) -> Dict:
        """运行回测"""
        print(f"开始回测 {start_date} 至 {end_date}")
        
        # 获取回测区间内的所有财报
        earnings_list = self.data_fetcher.get_earnings_in_range(start_date, end_date)
        
        if not earnings_list:
            return {'error': '无财报数据'}
        
        # 模拟交易
        trades = []
        capital = self.initial_capital
        positions = {}
        
        for earnings in earnings_list:
            # 分析是否值得买入
            result = self._should_buy(earnings)
            
            if result['should_buy']:
                # 模拟买入
                trade = self._simulate_buy(earnings, result['score'], capital)
                if trade:
                    trades.append(trade)
                    capital -= trade['cost']
                    positions[earnings['stock_code']] = trade
        
        # 计算绩效
        performance = self._calculate_performance(trades, capital)
        
        return {
            'start_date': start_date,
            'end_date': end_date,
            'total_trades': len(trades),
            'performance': performance,
            'trades': trades
        }
    
    def _should_buy(self, earnings: Dict) -> Dict:
        """判断是否应该买入"""
        surprise_analysis = self.surprise_analyzer.analyze(earnings)
        
        # 超预期且得分>=75分才买入
        if surprise_analysis['score'] >= 75:
            return {
                'should_buy': True,
                'score': surprise_analysis['score'],
                'reason': surprise_analysis['level']
            }
        
        return {'should_buy': False, 'score': 0}
    
    def _simulate_buy(self, earnings: Dict, score: float, capital: float) -> Dict:
        """模拟买入"""
        stock_code = earnings['stock_code']
        announcement_date = earnings['announcement_date']
        
        # 获取公告日收盘价
        price = self._get_price_on_date(stock_code, announcement_date)
        
        if price is None:
            return None
        
        # 根据评分决定仓位
        if score >= 85:
            position_pct = 0.25
        elif score >= 75:
            position_pct = 0.15
        else:
            position_pct = 0.10
        
        # 计算买入数量
        buy_amount = capital * position_pct
        shares = int(buy_amount / price / 100) * 100  # 按手买入
        
        if shares == 0:
            return None
        
        cost = shares * price * (1 + self.commission + self.slippage)
        
        # 模拟卖出（持有20个交易日）
        sell_date = self._get_trading_day(announcement_date, 20)
        sell_price = self._get_price_on_date(stock_code, sell_date)
        
        if sell_price is None:
            return None
        
        sell_value = shares * sell_price * (1 - self.commission - self.slippage)
        profit = sell_value - cost
        profit_pct = (profit / cost) * 100
        
        return {
            'stock_code': stock_code,
            'buy_date': announcement_date,
            'buy_price': price,
            'shares': shares,
            'cost': cost,
            'sell_date': sell_date,
            'sell_price': sell_price,
            'sell_value': sell_value,
            'profit': profit,
            'profit_pct': profit_pct,
            'score': score
        }
    
    def _get_price_on_date(self, stock_code: str, date: str) -> float:
        """获取指定日期的收盘价"""
        try:
            import akshare as ak
            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=date.replace('-', ''),
                end_date=date.replace('-', ''),
                adjust="qfq"
            )
            
            if df is not None and not df.empty:
                return float(df['收盘'].iloc[0])
        except:
            pass
        return None
    
    def _get_trading_day(self, start_date: str, days: int) -> str:
        """获取N个交易日后的日期"""
        # 简化实现
        from datetime import datetime, timedelta
        start = datetime.strptime(start_date, '%Y-%m-%d')
        
        trading_days = 0
        current = start
        
        while trading_days < days:
            current += timedelta(days=1)
            # 跳过周末（简化处理）
            if current.weekday() < 5:
                trading_days += 1
        
        return current.strftime('%Y-%m-%d')
    
    def _calculate_performance(self, trades: List[Dict], final_capital: float) -> Dict:
        """计算绩效指标"""
        if not trades:
            return {
                'total_return': 0,
                'win_rate': 0,
                'avg_profit': 0,
                'max_profit': 0,
                'max_loss': 0
            }
        
        profits = [t['profit'] for t in trades]
        profit_pcts = [t['profit_pct'] for t in trades]
        
        total_profit = sum(profits)
        total_return = (total_profit / self.initial_capital) * 100
        
        win_trades = len([p for p in profits if p > 0])
        win_rate = (win_trades / len(trades)) * 100
        
        return {
            'total_return': round(total_return, 2),
            'total_profit': round(total_profit, 2),
            'win_rate': round(win_rate, 2),
            'avg_profit_pct': round(np.mean(profit_pcts), 2),
            'max_profit_pct': round(max(profit_pcts), 2),
            'max_loss_pct': round(min(profit_pcts), 2),
            'total_trades': len(trades),
            'win_trades': win_trades,
            'loss_trades': len(trades) - win_trades
        }


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='财报超预期策略回测')
    parser.add_argument('--start', type=str, default='2024-01-01', help='开始日期')
    parser.add_argument('--end', type=str, default='2024-12-31', help='结束日期')
    
    args = parser.parse_args()
    
    backtest = EarningsBacktest()
    result = backtest.run_backtest(args.start, args.end)
    
    print("\n" + "=" * 60)
    print("财报超预期策略回测报告")
    print("=" * 60)
    print(f"回测区间: {args.start} 至 {args.end}")
    print(f"初始资金: {backtest.initial_capital:,.0f}")
    print("-" * 60)
    
    perf = result.get('performance', {})
    print(f"总收益率: {perf.get('total_return', 0)}%")
    print(f"总盈利: {perf.get('total_profit', 0):,.0f}")
    print(f"胜率: {perf.get('win_rate', 0)}%")
    print(f"平均盈利: {perf.get('avg_profit_pct', 0)}%")
    print(f"最大盈利: {perf.get('max_profit_pct', 0)}%")
    print(f"最大亏损: {perf.get('max_loss_pct', 0)}%")
    print(f"总交易次数: {perf.get('total_trades', 0)}")
    print(f"盈利次数: {perf.get('win_trades', 0)}")
    print(f"亏损次数: {perf.get('loss_trades', 0)}")
    print("=" * 60)


if __name__ == '__main__':
    main()