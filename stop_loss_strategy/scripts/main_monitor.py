#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主监控入口
每日14:40执行持仓止损监控
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import List, Dict

# 添加项目路径
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_DIR)

import pandas as pd
import akshare as ak

from scripts.decision_engine import StopLossDecisionEngine
from scripts.market_status import MarketStatusChecker, MarketStatus


def get_hs300_data(days: int = 20) -> pd.DataFrame:
    """获取沪深300指数数据"""
    try:
        df = ak.index_zh_a_hist(symbol="000300", period="daily")
        df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
        })
        df = df.sort_values('date')
        return df.tail(days)
    except Exception as e:
        print(f"[ERROR] 获取沪深300数据失败: {e}")
        return pd.DataFrame()


def get_stock_data(stock_code: str, days: int = 60) -> pd.DataFrame:
    """获取个股数据"""
    try:
        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily")
        df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
        })
        df = df.sort_values('date')
        return df.tail(days)
    except Exception as e:
        print(f"[ERROR] 获取{stock_code}数据失败: {e}")
        return pd.DataFrame()


def get_realtime_price(stock_code: str) -> float:
    """获取实时价格"""
    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df['代码'] == stock_code]
        if not row.empty:
            return float(row.iloc[0]['最新价'])
    except Exception as e:
        print(f"[ERROR] 获取{stock_code}实时价格失败: {e}")
    return 0.0


def load_holdings(file_path: str) -> List[Dict]:
    """加载持仓数据"""
    if not os.path.exists(file_path):
        print(f"[ERROR] 持仓文件不存在: {file_path}")
        return []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] 加载持仓文件失败: {e}")
        return []


def save_report(report: str, output_dir: str = None):
    """保存报告"""
    if output_dir is None:
        output_dir = os.path.join(_PROJECT_DIR, 'data', 'reports')
    
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = os.path.join(output_dir, f"stop_loss_report_{timestamp}.txt")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n📄 报告已保存: {file_path}")


def run_monitor(holdings_file: str, check_time: str = "14:40"):
    """
    运行止损监控
    
    Args:
        holdings_file: 持仓文件路径
        check_time: 检查时间（用于报告）
    """
    print("=" * 70)
    print(f"🕐 {check_time} 止损监控系统启动")
    print("=" * 70)
    
    # 1. 获取大盘状态
    print("\n[1/4] 获取大盘状态...")
    hs300_df = get_hs300_data(days=20)
    
    if hs300_df.empty:
        print("[ERROR] 无法获取大盘数据，退出")
        return
    
    market_checker = MarketStatusChecker()
    market_status, market_reason = market_checker.determine_status(hs300_df)
    
    print(market_checker.format_status_report(market_status, market_reason))
    
    # 2. 加载持仓
    print("\n[2/4] 加载持仓数据...")
    holdings = load_holdings(holdings_file)
    
    if not holdings:
        print("[WARN] 持仓为空，无需监控")
        return
    
    print(f"持仓数量: {len(holdings)} 只")
    
    # 3. 逐只分析
    print("\n[3/4] 逐只分析持仓...")
    
    engine = StopLossDecisionEngine()
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    all_reports = []
    actions_needed = []
    
    for holding in holdings:
        code = holding['code']
        name = holding['name']
        buy_price = holding.get('buy_price', 0)
        buy_date = holding.get('buy_date', current_date)
        
        print(f"\n  分析: {name}({code})...")
        
        # 获取数据
        df = get_stock_data(code, days=60)
        current_price = get_realtime_price(code)
        
        if df.empty or current_price <= 0:
            print(f"    [WARN] 数据获取失败，跳过")
            continue
        
        # 执行决策
        result = engine.make_decision(
            stock_code=code,
            stock_name=name,
            buy_price=buy_price,
            current_price=current_price,
            buy_date=buy_date,
            current_date=current_date,
            df=df,
            market_status=market_status,
            current_position=holding.get('position_ratio', 1.0),
            clear_history=holding.get('clear_history', []),
            historical_max_profit=holding.get('historical_max_profit')
        )
        
        # 生成报告
        report = engine.format_full_report(result, code, name)
        all_reports.append(report)
        
        # 记录需要操作的
        final = result['final_decision']
        if final.reduce_ratio > 0:
            actions_needed.append({
                'code': code,
                'name': name,
                'action': final.action,
                'reduce_ratio': final.reduce_ratio,
                'reason': final.reason,
            })
        
        print(f"    结果: {final.action}")
    
    # 4. 汇总报告
    print("\n[4/4] 生成汇总报告...")
    
    summary_lines = []
    summary_lines.append("=" * 70)
    summary_lines.append(f"📊 {check_time} 止损监控汇总报告")
    summary_lines.append("=" * 70)
    summary_lines.append(f"\n大盘状态: {market_checker.get_status_name(market_status)}")
    summary_lines.append(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    summary_lines.append(f"持仓数量: {len(holdings)} 只")
    summary_lines.append(f"需操作: {len(actions_needed)} 只")
    
    if actions_needed:
        summary_lines.append("\n" + "-" * 70)
        summary_lines.append("⚠️ 需要执行的操作:")
        summary_lines.append("-" * 70)
        for action in actions_needed:
            summary_lines.append(f"\n  {action['name']}({action['code']}):")
            summary_lines.append(f"    操作: {action['action']}")
            summary_lines.append(f"    减仓: {action['reduce_ratio']*100:.0f}%")
            summary_lines.append(f"    原因: {action['reason']}")
    else:
        summary_lines.append("\n✅ 无需要执行的操作，继续持有")
    
    summary_lines.append("\n" + "=" * 70)
    summary_lines.append("⚠️ 免责声明：本报告仅供参考，不构成投资建议")
    summary_lines.append("=" * 70)
    
    summary_report = "\n".join(summary_lines)
    
    # 完整报告
    full_report = "\n\n".join([summary_report] + all_reports)
    
    # 输出并保存
    print("\n" + summary_report)
    save_report(full_report)


def main():
    parser = argparse.ArgumentParser(description='止损监控系统')
    parser.add_argument('--holdings', type=str, 
                        default=os.path.join(_PROJECT_DIR, 'data', 'holdings.json'),
                        help='持仓文件路径')
    parser.add_argument('--time', type=str, default='14:40',
                        help='检查时间（用于报告）')
    
    args = parser.parse_args()
    
    run_monitor(args.holdings, args.time)


if __name__ == '__main__':
    main()
