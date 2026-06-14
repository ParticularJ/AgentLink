#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新持仓监控脚本 - 基于波动率的动态止损 + 原有止盈策略
整合方案：
  - 止损：使用新的 stop_loss_engine.py（9级优先级）
  - 止盈：保留原有三档止盈（L1/L2/L3分级）+ 回撤止盈

触发方式：
  python new_holding_monitor.py MORNING   # 早盘 09:20
  python new_holding_monitor.py EVENING   # 尾盘 14:50
"""
import os
import sys
import json
import traceback
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

# 清除代理
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try:
            del os.environ[k]
        except:
            pass

# ── 路径配置 ────────────────────────────────────────────
AGENT_LINK_BASE = "/home/qinliming/.openclaw/plugin-skills/AgentLink/Skills/StockFinal"
SCRIPTS_DIR = f"{AGENT_LINK_BASE}/Medium-termHoldingStrategy/skills/scripts"
HOLDINGS_FILE = f"{AGENT_LINK_BASE}/my_holdings/holdings.json"
CASH_FILE = f"{AGENT_LINK_BASE}/my_holdings/cash_balance.json"
LOG_DIR = Path("/home/qinliming/.openclaw/logs/stock")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "new_holding_push.log"

sys.path.insert(0, SCRIPTS_DIR)

from models import StockData, TechnicalIndicators
from market_sentiment import MarketSentiment, MarketState
from atr_calculator import auto_calc_stop_levels, get_lot_size
from stop_loss_engine import StopLossEngine, HoldingState, Action
from data_source import get_stock_realtime


# ══ 原有止盈配置（从 send_holding_card.py 保留）═════════════
STOCK_GRADE = {
    "600584": "L1_行业龙头", "600183": "L1_行业龙头",
    "600276": "L1_行业龙头", "601975": "L1_行业龙头",
    "300831": "L1_行业龙头", "300408": "L1_行业龙头",
    "002859": "L1_行业龙头",
    "603267": "L2_细分龙头", "002179": "L2_细分龙头",
    "000021": "L2_细分龙头", "603893": "L2_细分龙头",
    "603728": "L3_题材跟风",
}

GRADE_CONFIG = {
    "L1_行业龙头": {
        "profit_targets": [0.18, 0.40, 0.50],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.08,
        "trailing_stop": 0.06,
    },
    "L2_细分龙头": {
        "profit_targets": [0.12, 0.22, 0.38],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.07,
        "trailing_stop": 0.05,
    },
    "L3_题材跟风": {
        "profit_targets": [0.10, 0.18, 0.30],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.06,
        "trailing_stop": 0.04,
    },
}

# ── 飞书配置 ────────────────────────────────────────────
FEISHU_APP_ID = "cli_a93eb458ceb81cc0"
FEISHU_APP_SECRET = "cli_a93eb458ceb81cc0"
FEISHU_GROUP_ID = "oc_0ac1e4e8d09f939d887f4992bba2886b"


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def log_error(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [ERROR] {msg}\n{traceback.format_exc()}"
    print(line, file=sys.stderr)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_tenant_token() -> str:
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10)
    resp.raise_for_status()
    return resp.json()["tenant_access_token"]


def send_feishu_card(token: str, card: dict, receive_id: str):
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": json.dumps(card)
    }
    resp = requests.post(url, params={"receive_id_type": "chat_id"}, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── 止盈计算（原保留逻辑）──────────────────────────────
def calc_profit_targets(code: str, cost: float, init_shares: int, trend_coef: float = 1.0) -> dict:
    """计算三档止盈目标（原有逻辑，完整保留）"""
    grade = STOCK_GRADE.get(code, "L3_题材跟风")
    cfg = GRADE_CONFIG[grade]

    # 动态系数（趋势强时上调止盈目标）
    if trend_coef >= 0.99:
        coef = 1.2
    elif trend_coef >= 0.75:
        coef = 1.0
    else:
        coef = 0.7

    p1 = round(cost * (1 + cfg["profit_targets"][0] * coef), 2)
    p2 = round(cost * (1 + cfg["profit_targets"][1] * coef), 2)
    p3 = round(cost * (1 + cfg["profit_targets"][2] * coef), 2)
    # 止盈股数：向下取整到交易单位整数倍（科创板200，其余100）
    # 不足1手保留原值；超过1手但非整手数时，向下取整到整手
    lot = get_lot_size(code)
    s1_raw = int(init_shares * cfg["sell_ratio"][0])
    s2_raw = int(init_shares * cfg["sell_ratio"][1])
    s3_raw = int(init_shares * cfg["sell_ratio"][2])
    s1 = int(s1_raw / lot) * lot if s1_raw >= lot and s1_raw % lot != 0 else s1_raw
    s2 = int(s2_raw / lot) * lot if s2_raw >= lot and s2_raw % lot != 0 else s2_raw
    s3 = int(s3_raw / lot) * lot if s3_raw >= lot and s3_raw % lot != 0 else s3_raw
    trailing = cfg["trailing_stop"]

    return {
        "grade": grade,
        "p1": p1, "s1": s1,
        "p2": p2, "s2": s2,
        "p3": p3, "s3": s3,
        "trailing_pct": trailing,
        "trailing_label": f"{trailing * 100:.0f}%",
    }


def check_profit_signals(code: str, current_price: float, cost: float,
                        init_shares: int, stop_level_hit: List[bool],
                        trend_coef: float = 1.0) -> List[str]:
    """
    检查止盈信号（原保留逻辑）
    返回需要执行的止盈操作列表
    """
    signals = []
    targets = calc_profit_targets(code, cost, init_shares, trend_coef)

    # 第一档止盈
    if current_price >= targets["p1"] and not stop_level_hit[0]:
        signals.append(f"🎯 达到第一止盈 {targets['p1']}元 → 建议卖出{int(targets['s1'])}股")
    # 第二档止盈
    if current_price >= targets["p2"] and not stop_level_hit[1]:
        signals.append(f"🎯 达到第二止盈 {targets['p2']}元 → 建议卖出{int(targets['s2'])}股")
    # 第三档止盈
    if current_price >= targets["p3"] and not stop_level_hit[2]:
        signals.append(f"🎯 达到第三止盈 {targets['p3']}元 → 建议卖出{int(targets['s3'])}股")

    return signals


# ── 持仓加载 ────────────────────────────────────────────
def load_holdings() -> list:
    with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_cash_balance() -> dict:
    with open(CASH_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── 主分析逻辑 ──────────────────────────────────────────
def run_analysis(session: str, n_multiplier: float = 2.0):
    """
    运行持仓分析，返回分析结果列表
    """
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 初始化大盘情绪
    market = MarketSentiment()
    market_state, market_df = market.get_market_state(today_str)
    trend_coef = getattr(market_state, 'value', 1.0)  # 简化
    log(f"[持仓分析] 大盘状态: {market.get_state_description()}")

    # 初始化止损引擎
    engine = StopLossEngine(market, n_multiplier)

    raw_holdings = load_holdings()
    cash_info = load_cash_balance()

    results = []
    for item in raw_holdings:
        code = item['code']
        name = item['name']
        cost = item['cost']
        shares = item['shares']
        init_shares = item.get('init_shares', shares)
        entry_date = item.get('entry_date', today_str)
        strategy_name = item.get('strategy_name', 'unknown')
        sector = item.get('sector', 'default')
        stop_level_hit = item.get('stop_level_hit', [False, False, False])
        highest_profit_pct = item.get('highest_profit_pct', 0.0)
        profit_mode = item.get('profit_mode', False)

        if shares <= 0:
            continue

        # 获取实时数据
        df_history, current_data = get_stock_realtime(code)
        if current_data is None or current_data.get('price', 0) == 0:
            log(f"[警告] 股票 {code}({name}) 获取数据失败，跳过")
            continue

        current_price = current_data['price']

        # ── 止损参数（ATR计算）──────────────────────
        stop_info = auto_calc_stop_levels(df_history, code, cost, sector, n_multiplier)

        # ── 构建HoldingState ─────────────────────
        hs = HoldingState(
            code=code, name=name, cost=cost, shares=shares,
            init_shares=init_shares, entry_date=entry_date,
        )
        hs.atr_pct = stop_info.get("atr_pct", 0.0)
        hs.clear_stop_pct = stop_info.get("clear_stop_pct", 0.0)
        hs.clear_stop_price = stop_info.get("clear_stop_price", 0.0)
        hs.half_stop_pct = stop_info.get("half_stop_pct", 0.0)
        hs.half_stop_price = stop_info.get("half_stop_price", 0.0)
        hs.stop_method = stop_info.get("method", "")
        hs.highest_profit_pct = highest_profit_pct
        hs.profit_mode = profit_mode
        # 从持仓恢复触发状态
        if item.get('stop_lose_hit'):
            hs.half_hit = item['stop_lose_hit'][2] if len(item['stop_lose_hit']) > 2 else False
            hs.ma5_hit = item['stop_lose_hit'][0] if len(item['stop_lose_hit']) > 0 else False
            hs.ma10_hit = item['stop_lose_hit'][1] if len(item['stop_lose_hit']) > 1 else False

        # ── 计算当前浮盈 ──────────────────────────
        profit_pct = (current_price - cost) / cost
        profit_val = (current_price - cost) * shares
        hs.current_profit_pct = profit_pct
        if profit_pct > hs.highest_profit_pct:
            hs.highest_profit_pct = profit_pct
        hs.profit_mode = profit_pct >= 0.10

        # ── 计算技术指标 ─────────────────────────
        tech = None
        if df_history is not None and len(df_history) >= 5:
            import pandas as pd
            close = df_history['close'].values
            tech = TechnicalIndicators(
                ma5=float(pd.Series(close).rolling(5).mean().iloc[-1]),
                ma10=float(pd.Series(close).rolling(10).mean().iloc[-1]),
                ma20=float(pd.Series(close).rolling(20).mean().iloc[-1]) if len(close) >= 20 else close[-1],
                ma60=float(pd.Series(close).rolling(60).mean().iloc[-1]) if len(close) >= 60 else close[-1],
                macd=0, macd_signal=0, macd_hist=0,
                kdj_k=0, kdj_d=0, kdj_j=0
            )

        # ── 转换为StockData ─────────────────────
        stock_data = StockData(
            code=code, name=name, price=current_price,
            open=current_data.get('open', current_price),
            high=current_data.get('high', current_price),
            low=current_data.get('low', current_price),
            volume=current_data.get('volume', 0),
            turnover=current_data.get('turnover', 0),
            change_pct=current_data.get('chg_pct', 0),
            volume_ratio=current_data.get('volume_ratio', 1.0),
        )

        # ── 执行止损检查 ──────────────────────────
        action = engine.check(hs, current_price, stock_data, tech, df_history, today_str)

        # ── 检查止盈信号（原保留逻辑）────────────────
        profit_signals = check_profit_signals(
            code, current_price, cost, init_shares, stop_level_hit
        )

        # ── 合并所有信号 ──────────────────────────
        all_signals = []
        if action.action in ("清仓", "减半", "减至3成"):
            all_signals.append(f"【止损】{action.reason}")
        if profit_signals:
            for sig in profit_signals:
                all_signals.append(f"【止盈】{sig}")

        # ── 回撤止盈检查 ──────────────────────────
        hp = hs.highest_profit_pct
        cp = profit_pct
        if hp > 0:
            drawdown = (hp - cp) / hp
        else:
            drawdown = 0.0
        grade = STOCK_GRADE.get(code, "L3_题材跟风")
        trailing_pct = GRADE_CONFIG[grade]["trailing_stop"]
        if hp > 0 and cp > 0:
            # 从最高浮盈回撤超过回撤阈值 → 警告
            if drawdown >= trailing_pct:
                all_signals.append(
                    f"【回撤止盈】最高浮盈{hp:.1%}，当前回撤{drawdown:.1%}≥阈值{trailing_pct:.1%}，考虑减半"
                )

        results.append({
            'name': name,
            'code': code,
            'sector': sector,
            'current_price': current_price,
            'cost': cost,
            'shares': shares,
            'profit_pct': profit_pct * 100,
            'profit_val': profit_val,
            'strategy_name': strategy_name,
            'stop_info': stop_info,
            'action': action,
            'profit_targets': calc_profit_targets(code, cost, init_shares),
            'all_signals': all_signals,
            'market_state': market.get_state_description(),
            'highest_profit_pct': hs.highest_profit_pct,
            'profit_mode': hs.profit_mode,
            'trailing_pct': trailing_pct,
            'df_history': df_history,
        })

    return results, market, cash_info


# ── 飞书卡片构建 ─────────────────────────────────────────
def build_feishu_card(session: str, results: list, market: MarketSentiment,
                      cash_info: dict, date_str: str):
    """构建飞书交互卡片，同时展示止损信号和止盈信号"""
    is_morning = session == "MORNING"
    icon = "☀️" if is_morning else "🌙"
    label = "早盘持仓分析" if is_morning else "尾盘持仓分析"
    time_hint = "09:20" if is_morning else "14:50"

    market_state, _ = market.get_market_state(date_str)
    market_icon = {
        MarketState.NORMAL: "✅",
        MarketState.WEAK: "⚠️",
        MarketState.PANIC: "🚨",
        MarketState.EXTREME_PANIC: "🔴",
    }.get(market_state, "📊")

    # 分类
    need_action = []
    normal_holdings = []

    for r in results:
        action: Action = r['action']
        if action.action in ("清仓", "减半", "减至3成") or r['all_signals']:
            need_action.append(r)
        else:
            normal_holdings.append(r)

    # 资产计算
    position_value = sum(r['current_price'] * r['shares'] for r in results)
    cash = cash_info.get('available_cash', 0)
    total_asset = position_value + cash
    total_profit = total_asset - cash_info.get('initial_capital', total_asset)

    lines = []
    lines.append(f"**{icon} {label}** | {date_str} {time_hint}")
    lines.append(f"**大盘: {market_icon} {market.get_state_description()}**")
    lines.append("")

    # ── 需要操作 ──────────────────────────────────────
    if need_action:
        lines.append(f"⚠️ **需要操作 ({len(need_action)}只)**")
        lines.append("")
        for r in need_action:
            action: Action = r['action']
            stop_info = r['stop_info']
            pt = r['profit_targets']
            profit_pct = r['profit_pct']

            lines.append(f"**{action.alert_level} {r['name']}({r['code']})**  {r['sector']}")
            lines.append(
                f"  现价: {r['current_price']:.2f} | 成本: {r['cost']:.2f} | "
                f"{profit_pct:+.1f}% 盈亏{r['profit_val']:+,.0f} | {r['shares']}股"
            )
            lines.append(
                f"  策略: {r['strategy_name']} | 级别: {pt['grade']}"
            )

            # 信号列表
            for sig in r['all_signals']:
                lines.append(f"  {sig}")

            # 止损参数
            lines.append(
                f"  止损: 减半线={stop_info['half_stop_price']:.2f} "
                f"清仓线={stop_info['clear_stop_price']:.2f} "
                f"(ATR{stop_info['method']})"
            )
            # 止盈目标
            lines.append(
                f"  止盈: {pt['p1']}/{pt['p2']}/{pt['p3']} | "
                f"回撤阈值:{r['trailing_pct']*100:.0f}% | "
                f"最高浮盈:{r['highest_profit_pct']*100:+.1f}%"
            )
            lines.append("")
    else:
        lines.append("✅ **暂无触发信号，正常持仓**")
        lines.append("")

    # ── 正常持仓 ───────────────────────────────────────
    if normal_holdings:
        lines.append(f"📋 **正常持仓 ({len(normal_holdings)}只)**")
        lines.append("")
        for r in normal_holdings:
            pp = r['profit_pct']
            emoji = "🟢" if pp >= 0 else "🔴"
            pt = r['profit_targets']
            lines.append(
                f"{emoji} **{r['name']}** {pp:+.1f}% "
                f"盈亏{r['profit_val']:+,.0f} | {r['shares']}股 "
                f"| 止盈:{pt['p1']}/{pt['p2']}/{pt['p3']}"
            )
        lines.append("")

    # ── 资产总览 ──────────────────────────────────────
    lines.append("---")
    lines.append(f"📊 **资产总览**")
    lines.append(f"总资产: **{total_asset:+,.0f}元**")
    lines.append(f"总盈亏: **{total_profit:+,.0f}元**")
    lines.append(f"可用现金: **{cash:+,.0f}元**")
    lines.append("")
    lines.append("⚠️ 止损策略仅供参考，不构成投资建议")

    # ── 卡片 ──────────────────────────────────────────
    elements = [{
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "\n".join(lines)
        }
    }]

    has_action = any(a.action in ("清仓", "减半", "减至3成") for a in [r['action'] for r in results])
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{icon} 动态止损止盈监控 | {label}"},
            "subtitle": {"tag": "plain_text",
                         "content": f"{date_str} {time_hint} | {market.get_state_description()}"},
            "template": "red" if has_action else "blue" if is_morning else "purple"
        },
        "elements": elements
    }
    return card


# ── 主函数 ──────────────────────────────────────────────
def main():
    session = sys.argv[1] if len(sys.argv) > 1 else "MORNING"
    n_multiplier = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    date_str = datetime.now().strftime("%Y-%m-%d")

    log(f"[新止损监控] 开始 {session}，N={n_multiplier}...")

    try:
        results, market, cash_info = run_analysis(session, n_multiplier)
        log(f"[新止损监控] 分析完成，共{len(results)}只持仓")
    except Exception as e:
        log_error(f"[新止损监控] 分析失败: {e}")
        return

    if results:
        card = build_feishu_card(session, results, market, cash_info, date_str)
        try:
            token = get_tenant_token()
            resp = send_feishu_card(token, card, FEISHU_GROUP_ID)
            code = resp.get('code')
            msg = resp.get('msg') or resp.get('message', '')
            if code == 0:
                log(f"[新止损监控] 飞书推送成功")
            else:
                log_error(f"[新止损监控] 飞书推送失败: code={code} msg={msg}")
        except Exception as e:
            log_error(f"[新止损监控] 飞书推送异常")
    else:
        log("[新止损监控] 无数据，跳过推送")


if __name__ == "__main__":
    main()