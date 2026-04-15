#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持仓监控 - 简化版 v4
运行时间：09:20 和 14:30
逻辑：
  1. 建仓：在推荐列表中，但不在持仓中
  2. 减仓：在持仓中，触发止盈或止损条件
  3. 加仓：同时在持仓和推荐列表中（且未触发止盈）
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Set

# ── 代理清除 ───────────────────────────────────────────
for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    os.environ.pop(k, None)

import akshare as ak

# ── 路径设置 ───────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))  # Chinese_Stock/

HOLDINGS_DIR = os.path.join(_BASE_DIR, 'my_holdings')
RECOMMENDATIONS_DIR = os.path.join(_BASE_DIR, 'recommendations')

# ── 止盈止损配置 ───────────────────────────────────────
# 基于 buy_reason 的止盈止损参数
# 包含：固定比例止盈 + 动态回撤止盈
STOP_LOSS_CONFIG = {
    'limit_up': {
        'stop_loss': -7,
        'profit_levels': [(15, 20), (30, 30), (40, 50), (50, 70), (80, 100)],  # 增加15%第一道防线
        'max_drawdown': 0.10,  # 从高点回撤10%触发动态止盈
    },
    'breakout_high': {
        'stop_loss': -7,
        'profit_levels': [(15, 20), (30, 30), (40, 50), (50, 70), (80, 100)],
        'max_drawdown': 0.10,
    },
    'gap_fill': {
        'stop_loss': -5,
        'profit_levels': [(10, 30), (15, 50), (20, 50), (30, 70), (40, 100)],
        'max_drawdown': 0.08,  # 稳健策略回撤8%
    },
    'ma_bullish': {
        'stop_loss': -5,
        'profit_levels': [(10, 30), (15, 50), (20, 50), (30, 70), (40, 100)],
        'max_drawdown': 0.08,
    },
    'macd_divergence': {
        'stop_loss': -3,
        'profit_levels': [(5, 20), (8, 30), (10, 50), (15, 70), (20, 100)],
        'max_drawdown': 0.05,  # 保守策略回撤5%
    },
    'rsi_oversold': {
        'stop_loss': -3,
        'profit_levels': [(5, 20), (8, 30), (10, 50), (15, 70), (20, 100)],
        'max_drawdown': 0.05,
    },
    'morning_star': {
        'stop_loss': -3,
        'profit_levels': [(5, 20), (8, 30), (10, 50), (15, 70), (20, 100)],
        'max_drawdown': 0.05,
    },
    'volume_extreme': {
        'stop_loss': -3,
        'profit_levels': [(5, 20), (8, 30), (10, 50), (15, 70), (20, 100)],
        'max_drawdown': 0.05,
    },
    'a_stock_1430': {
        'stop_loss': -2,
        'profit_levels': [(2, 50), (5, 100)],
        'max_drawdown': 0.03,  # 超短策略回撤3%
    },
    'default': {
        'stop_loss': -5,
        'profit_levels': [(10, 30), (20, 50), (30, 100)],
        'max_drawdown': 0.08,
    },
}


def get_latest_holdings_file() -> str:
    """获取最新的持仓文件"""
    import glob
    pattern = os.path.join(HOLDINGS_DIR, '*_holdings.json')
    files = glob.glob(pattern)
    if files:
        return max(files, key=os.path.getmtime)
    return os.path.join(HOLDINGS_DIR, 'holdings.json')


def get_latest_recommendation_file() -> Optional[str]:
    """获取最新的推荐文件"""
    import glob
    pattern = os.path.join(RECOMMENDATIONS_DIR, '*_recommendation.json')
    files = glob.glob(pattern)
    if files:
        return max(files, key=os.path.getmtime)
    return None


def load_holdings() -> List[Dict]:
    """加载持仓数据"""
    holdings_file = get_latest_holdings_file()
    if not os.path.exists(holdings_file):
        return []
    try:
        with open(holdings_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] 加载持仓文件失败: {e}")
        return []


def load_recommendations() -> List[Dict]:
    """加载推荐列表"""
    rec_file = get_latest_recommendation_file()
    if not rec_file or not os.path.exists(rec_file):
        return []
    try:
        with open(rec_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 处理嵌套格式：{ "recommendations": [...] }
        if isinstance(data, dict) and 'recommendations' in data:
            return data['recommendations']
        # 处理直接数组格式
        elif isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"[WARN] 加载推荐文件失败: {e}")
        return []


def get_realtime_quote(stock_code: str) -> Optional[Dict]:
    """获取个股实时行情"""
    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df['代码'] == stock_code]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            'code': stock_code,
            'name': r['名称'],
            'price': float(r['最新价']),
            'change_pct': float(r['涨跌幅']),
            'high': float(r['最高']),
            'low': float(r['最低']),
            'open': float(r['今开']),
            'pre_close': float(r['昨收']),
        }
    except Exception as e:
        print(f"[WARN] 获取 {stock_code} 实时行情失败: {e}")
        return None


def calculate_profit_take_action(profit_pct: float, buy_reason: str) -> tuple:
    """
    计算止盈动作
    返回: (是否触发止盈, 减仓比例, 描述)
    """
    config = STOP_LOSS_CONFIG.get(buy_reason, STOP_LOSS_CONFIG['default'])
    profit_levels = config['profit_levels']
    
    # 按盈利幅度从高到低检查
    for level_profit, reduce_pct in reversed(profit_levels):
        if profit_pct >= level_profit:
            return True, reduce_pct, f"盈利 {profit_pct:.1f}% ≥ {level_profit}%，建议减仓 {reduce_pct}%"
    
    return False, 0, ""


def calculate_stop_loss_action(profit_pct: float, buy_reason: str) -> tuple:
    """
    计算止损动作
    返回: (是否触发止损, 描述)
    """
    config = STOP_LOSS_CONFIG.get(buy_reason, STOP_LOSS_CONFIG['default'])
    stop_loss = config['stop_loss']
    
    if profit_pct <= stop_loss:
        return True, f"亏损 {abs(profit_pct):.1f}% 触及止损线 {stop_loss}%，建议清仓"
    
    return False, ""


def calculate_drawdown_action(current_price: float, high_price: float, buy_price: float, buy_reason: str) -> tuple:
    """
    计算动态回撤止盈动作
    从高点回撤一定比例时触发
    返回: (是否触发, 描述)
    """
    config = STOP_LOSS_CONFIG.get(buy_reason, STOP_LOSS_CONFIG['default'])
    max_drawdown = config.get('max_drawdown', 0.10)  # 默认10%
    
    # 只有盈利状态才检查回撤止盈
    if current_price <= buy_price:
        return False, ""
    
    # 计算从高点回撤比例
    if high_price <= buy_price:
        return False, ""
    
    drawdown_pct = (high_price - current_price) / high_price
    profit_pct = (current_price - buy_price) / buy_price * 100
    max_profit_pct = (high_price - buy_price) / buy_price * 100
    
    # 回撤超过阈值，且曾经有一定盈利（至少5%）
    if drawdown_pct >= max_drawdown and max_profit_pct >= 5:
        return True, f"从高点 {max_profit_pct:.1f}% 回撤 {drawdown_pct*100:.1f}%（阈值 {max_drawdown*100:.0f}%），建议减仓保护利润"
    
    return False, ""


def analyze_position(holding: Dict, current_price: float) -> Dict:
    """分析单个持仓的交易建议"""
    code = holding['code']
    name = holding['name']
    buy_price = holding.get('buy_price', 0)
    buy_reason = holding.get('buy_reason', 'default')
    high_price = holding.get('high_price', current_price)  # 买入后最高价
    
    if buy_price <= 0:
        return {'code': code, 'signal': '❌ 数据错误', 'reason': '买入价无效'}
    
    profit_pct = (current_price - buy_price) / buy_price * 100
    
    # 更新最高价（用于动态回撤止盈）
    if current_price > high_price:
        high_price = current_price
    
    # 1. 先检查止损（优先级最高）
    is_stop_loss, stop_desc = calculate_stop_loss_action(profit_pct, buy_reason)
    if is_stop_loss:
        return {
            'code': code,
            'name': name,
            'signal': '🚨 减仓（止损）',
            'action': '清仓',
            'reduce_pct': 100,
            'current_price': current_price,
            'profit_pct': round(profit_pct, 2),
            'reason': stop_desc,
            'buy_reason': buy_reason,
        }
    
    # 2. 检查固定比例止盈
    is_profit_take, reduce_pct, profit_desc = calculate_profit_take_action(profit_pct, buy_reason)
    if is_profit_take:
        return {
            'code': code,
            'name': name,
            'signal': '💰 减仓（止盈）',
            'action': f'减仓 {reduce_pct}%',
            'reduce_pct': reduce_pct,
            'current_price': current_price,
            'profit_pct': round(profit_pct, 2),
            'reason': profit_desc,
            'buy_reason': buy_reason,
        }
    
    # 3. 检查动态回撤止盈（从高点回撤）
    drawdown_action, drawdown_desc = calculate_drawdown_action(current_price, high_price, buy_price, buy_reason)
    if drawdown_action:
        return {
            'code': code,
            'name': name,
            'signal': '💰 减仓（回撤止盈）',
            'action': '减仓 50%',
            'reduce_pct': 50,
            'current_price': current_price,
            'profit_pct': round(profit_pct, 2),
            'reason': drawdown_desc,
            'buy_reason': buy_reason,
        }
    
    # 4. 未触发任何信号，返回持有状态
    return {
        'code': code,
        'name': name,
        'signal': '🟢 持有',
        'action': '继续持有',
        'reduce_pct': 0,
        'current_price': current_price,
        'profit_pct': round(profit_pct, 2),
        'reason': f'浮盈 {profit_pct:.1f}%，未达到止盈/止损条件',
        'buy_reason': buy_reason,
    }


def generate_report(
    holdings: List[Dict],
    recommendations: List[Dict],
    position_signals: Dict[str, Dict],
    current_time: str
) -> str:
    """生成交易建议报告"""
    lines = []
    lines.append(f"🕐 {current_time} 交易建议报告")
    lines.append("=" * 60)
    
    # 构建集合
    holding_codes = {h['code'] for h in holdings}
    rec_codes = {r['code'] for r in recommendations}
    
    # 分类
    build_positions = []  # 建仓：在推荐中，不在持仓中
    add_positions = []    # 加仓：同时在持仓和推荐中
    reduce_positions = [] # 减仓：在持仓中，触发止盈/止损
    hold_positions = []   # 持有：在持仓中，未触发交易信号
    
    for rec in recommendations:
        code = rec['code']
        if code not in holding_codes:
            build_positions.append(rec)
        elif code in position_signals:
            signal = position_signals[code]
            if '减仓' in signal['signal']:
                # 触发减仓，不加入加仓列表
                reduce_positions.append(signal)
            else:
                add_positions.append({**rec, **signal})
    
    for code, signal in position_signals.items():
        if '减仓' in signal['signal'] and code not in [r['code'] for r in reduce_positions]:
            reduce_positions.append(signal)
        elif code not in rec_codes and signal['signal'] == '🟢 持有':
            hold_positions.append(signal)
    
    # 输出汇总
    lines.append(f"\n📊 汇总")
    lines.append(f"  建仓机会：{len(build_positions)} 只")
    lines.append(f"  加仓机会：{len(add_positions)} 只")
    lines.append(f"  减仓信号：{len(reduce_positions)} 只")
    lines.append(f"  继续持有：{len(hold_positions)} 只")
    lines.append("")
    
    # 建仓建议
    if build_positions:
        lines.append("━" * 60)
        lines.append("📈 【建仓建议】在推荐列表中，尚未持仓")
        lines.append("")
        for rec in build_positions:
            lines.append(f"  ▶ {rec.get('name', rec['code'])} ({rec['code']})")
            lines.append(f"    推荐理由: {rec.get('reason', rec.get('source', 'N/A'))}")
            if 'entry_price' in rec:
                lines.append(f"    建议买入价: ¥{rec['entry_price']}")
            lines.append("")
    
    # 加仓建议
    if add_positions:
        lines.append("━" * 60)
        lines.append("📈 【加仓建议】同时在持仓和推荐列表中")
        lines.append("")
        for pos in add_positions:
            lines.append(f"  ▶ {pos.get('name', pos['code'])} ({pos['code']})")
            lines.append(f"    当前价: ¥{pos['current_price']} | 浮盈: {pos['profit_pct']:+.1f}%")
            lines.append(f"    推荐理由: {pos.get('recommend_reason', pos.get('source', 'N/A'))}")
            lines.append("")
    
    # 减仓建议
    if reduce_positions:
        lines.append("━" * 60)
        lines.append("📉 【减仓建议】触发止盈或止损条件")
        lines.append("")
        for pos in reduce_positions:
            emoji = '🚨' if '止损' in pos['signal'] else '💰'
            lines.append(f"  {emoji} {pos.get('name', pos['code'])} ({pos['code']})")
            lines.append(f"    当前价: ¥{pos['current_price']} | 浮盈: {pos['profit_pct']:+.1f}%")
            lines.append(f"    操作: {pos['action']}")
            lines.append(f"    理由: {pos['reason']}")
            lines.append("")
    
    # 持有建议
    if hold_positions:
        lines.append("━" * 60)
        lines.append("🟢 【继续持有】未达到交易条件")
        lines.append("")
        for pos in hold_positions:
            lines.append(f"  • {pos.get('name', pos['code'])} ({pos['code']})")
            lines.append(f"    当前价: ¥{pos['current_price']} | 浮盈: {pos['profit_pct']:+.1f}%")
            lines.append(f"    理由: {pos['reason']}")
            lines.append("")
    
    lines.append("=" * 60)
    lines.append("⚠️ 仅供参考，不构成投资建议")
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='持仓监控 - 简化版 v4')
    parser.add_argument('--holdings-file', type=str, help='持仓文件路径')
    parser.add_argument('--rec-file', type=str, help='推荐文件路径')
    args = parser.parse_args()
    
    print(f"🔍 开始分析持仓与推荐...")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 加载数据
    holdings = load_holdings()
    recommendations = load_recommendations()
    
    print(f"   持仓数量: {len(holdings)} 只")
    print(f"   推荐数量: {len(recommendations)} 只")
    
    if not holdings and not recommendations:
        print("\n🟢 持仓和推荐均为空，无需分析")
        return
    
    # 分析持仓
    position_signals = {}
    for holding in holdings:
        code = holding['code']
        quote = get_realtime_quote(code)
        if quote:
            signal = analyze_position(holding, quote['price'])
            position_signals[code] = signal
        else:
            position_signals[code] = {
                'code': code,
                'name': holding.get('name', code),
                'signal': '❌ 数据错误',
                'reason': '获取行情失败'
            }
    
    # 生成报告
    current_time = datetime.now().strftime('%H:%M')
    report = generate_report(holdings, recommendations, position_signals, current_time)
    print("\n" + report)
    
    # 保存结果
    output = {
        'time': datetime.now().isoformat(),
        'holdings_count': len(holdings),
        'recommendations_count': len(recommendations),
        'signals': position_signals,
    }
    output_path = '/tmp/sell_monitor_last_run.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n📄 结果已保存至 {output_path}")


if __name__ == '__main__':
    main()
