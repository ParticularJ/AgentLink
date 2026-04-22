#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持仓编辑器 - 交互式录入持仓信息
生成 YYYYMMDD_holdings.json 文件
"""

import os
import sys
import json
from datetime import datetime

# ── 路径设置（相对路径）────────────────────────────────
__file__ = os.path.abspath(__file__)
SCRIPT_DIR = os.path.dirname(__file__)                          # my_holdings/scripts/
_HOLDINGS_DIR = os.path.dirname(SCRIPT_DIR)                    # my_holdings/


BUY_REASONS = [
    ('limit_up',           '涨停连板（激进）'),
    ('breakout_high',      '突破新高（激进）'),
    ('gap_fill',           '缺口填充（稳健）'),
    ('ma_bullish',         '均线多头（稳健）'),
    ('macd_divergence',    'MACD底背离（保守）'),
    ('rsi_oversold',       'RSI超卖（保守）'),
    ('morning_star',        '早晨之星（保守）'),
    ('volume_extreme',     '地量见底（保守）'),
    ('a_stock_1430',       '尾盘超短（超短）'),
]


def print_header():
    print()
    print("=" * 50)
    print("  持仓编辑器")
    print("=" * 50)
    print()


def ask_yes_no(prompt: str) -> bool:
    while True:
        ans = input(f"  {prompt} (y/n): ").strip().lower()
        if ans in ('y', 'yes'):
            return True
        elif ans in ('n', 'no'):
            return False


def ask_stock():
    """录入单只股票"""
    print()
    print("-" * 40)

    # 股票代码
    code = input("  股票代码 (6位，如 600105): ").strip()
    if len(code) != 6 or not code.isdigit():
        print("  ⚠️  股票代码应为6位数字")
        return None

    # 股票名称
    name = input("  股票名称 (如 永鼎股份): ").strip()
    if not name:
        print("  ⚠️  股票名称不能为空")
        return None

    # 买入价格
    try:
        buy_price = float(input("  买入价格 (元): ").strip())
    except ValueError:
        print("  ⚠️  请输入有效数字")
        return None

    # 持股数量
    try:
        shares = int(input("  持股数量 (股): ").strip())
    except ValueError:
        print("  ⚠️  请输入整数")
        return None

    # 持仓占比
    try:
        ratio = float(input("  持仓占比 (0.0~1.0，如 0.20): ").strip())
        if ratio <= 0 or ratio > 1:
            print("  ⚠️  占比应在 0~1 之间")
            return None
    except ValueError:
        print("  ⚠️  请输入有效数字")
        return None

    # 持仓市值
    try:
        position_value = float(input("  持仓市值 (元): ").strip())
    except ValueError:
        position_value = round(buy_price * shares, 2)

    # 买入日期
    buy_date = input("  买入日期 (YYYY-MM-DD，留空则今天): ").strip()
    if not buy_date:
        buy_date = datetime.now().strftime('%Y-%m-%d')

    # 买入原因
    print("  买入原因 (buy_reason):")
    for i, (key, desc) in enumerate(BUY_REASONS, 1):
        print(f"    {i}. {desc}")
    try:
        idx = int(input("  选择 (数字): ").strip()) - 1
        buy_reason = BUY_REASONS[idx][0]
    except (ValueError, IndexError):
        print("  ⚠️  无效选择，默认使用 breakout_high")
        buy_reason = 'breakout_high'

    return {
        'code': code,
        'name': name,
        'buy_price': round(buy_price, 2),
        'shares': shares,
        'position_ratio': round(ratio, 4),
        'position_value': round(position_value, 2),
        'buy_reason': buy_reason,
        'buy_date': buy_date,
    }


def edit_holdings():
    """交互式编辑持仓"""
    holdings = []

    print_header()
    print(f"  当前输出目录: {_HOLDINGS_DIR}")
    print()

    # 是否追加现有持仓
    existing_file = os.path.join(_HOLDINGS_DIR, 'holdings.json')
    if os.path.exists(existing_file):
        print(f"  📋 检测到现有持仓文件: holdings.json")
        if ask_yes_no("是否追加现有持仓"):
            try:
                with open(existing_file, 'r', encoding='utf-8') as f:
                    holdings = json.load(f)
                print(f"  ✅ 已加载 {len(holdings)} 条持仓")
            except Exception:
                print("  ⚠️  加载失败，将从头开始")

    print()
    print("  请输入持仓信息（输入 done 结束）：")
    print()

    while True:
        cmd = input("  > ").strip()
        if cmd.lower() in ('done', 'q', 'quit', 'exit'):
            break

        stock = ask_stock()
        if stock:
            holdings.append(stock)
            print(f"  ✅ 已添加: {stock['name']}({stock['code']})")
        else:
            print("  ⚠️  添加失败，请重试")

    if not holdings:
        print("\n  ⚠️  未录入任何持仓，退出。")
        return

    # 计算总市值和占比
    total_value = sum(h.get('position_value', 0) for h in holdings)

    # 归一化占比
    if total_value > 0:
        for h in holdings:
            h['position_ratio'] = round(h['position_value'] / total_value, 4)

    # 保存
    date_str = datetime.now().strftime('%Y%m%d')
    output_file = os.path.join(_HOLDINGS_DIR, f'{date_str}_holdings.json')

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)

    # 同时覆盖 holdings.json（最新持仓）
    latest_file = os.path.join(_HOLDINGS_DIR, 'holdings.json')
    with open(latest_file, 'w', encoding='utf-8') as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 50)
    print(f"  ✅ 已保存到: {output_file}")
    print(f"  ✅ 同时更新: holdings.json")
    print(f"  📊 共录入 {len(holdings)} 只股票，总市值 {total_value:.2f} 元")
    print("=" * 50)

    # 预览
    print()
    print("  预览：")
    print(f"  {'代码':<8} {'名称':<10} {'买入价':>8} {'数量':>8} {'市值':>10} {'占比':>6} {'买入原因'}")
    print("  " + "-" * 70)
    for h in holdings:
        print(f"  {h['code']:<8} {h['name']:<10} {h['buy_price']:>8.2f} {h['shares']:>8} "
              f"{h['position_value']:>10.2f} {h['position_ratio']:>6.0%}  {h['buy_reason']}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='持仓编辑器')
    parser.add_argument('--list', action='store_true', help='查看现有持仓')
    args = parser.parse_args()

    if args.list:
        existing_file = os.path.join(_HOLDINGS_DIR, 'holdings.json')
        if os.path.exists(existing_file):
            with open(existing_file, 'r', encoding='utf-8') as f:
                holdings = json.load(f)
            print(f"\n📋 当前持仓 (共 {len(holdings)} 只)：\n")
            print(f"  {'代码':<8} {'名称':<10} {'买入价':>8} {'数量':>8} {'市值':>10} {'占比':>6} {'买入原因'}")
            print("  " + "-" * 70)
            for h in holdings:
                print(f"  {h['code']:<8} {h['name']:<10} {h['buy_price']:>8.2f} {h['shares']:>8} "
                      f"{h['position_value']:>10.2f} {h['position_ratio']:>6.0%}  {h['buy_reason']}")
            print()
        else:
            print("⚠️  暂无持仓文件")
        return

    edit_holdings()


if __name__ == '__main__':
    main()
