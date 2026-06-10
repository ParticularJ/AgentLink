#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持仓监控 - 飞书推送脚本（供 cron 调用）
09:15 早盘分析推送 / 14:50 尾盘分析推送
"""
import os,glob
import sys
import json
from tracemalloc import start
import requests
import traceback
from datetime import datetime
from pathlib import Path
import akshare as ak
import pandas as pd

# 清除代理
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try: del os.environ[k]
        except: pass

# 全局缓存交易日历，避免重复请求
_TRADE_CALENDAR = None


# ====================== 【止盈策略核心：静态龙头定级】======================
STOCK_GRADE = {
    # L1 行业绝对龙头
    "600584": "L1_行业龙头",  # 长电科技(封测全行业龙头)
    "600183": "L1_行业龙头",  # 生益科技(覆铜板全行业龙头)
    "600276": "L1_行业龙头",  # 恒瑞医药(创新药全行业龙头)
    "601975": "L1_行业龙头",  # 招商南油(油运央企龙头)
    "300831": "L1_行业龙头",  # 派瑞股份(功率器件细分龙头)
    "300408": "L1_行业龙头",  # 三环集团(MLCC瓷件+通用陶瓷全产业链龙头)
    "002859": "L1_行业龙头",  # 洁美科技【新增】纸质载带全球龙头、MLCC耗材全球隐形冠军
    # L2 细分龙头/强二线
    "603267": "L2_细分龙头",  # 鸿远电子【新增】军工航天高可靠MLCC细分龙头
    "002179": "L2_细分龙头",  # 中航光电(连接器细分龙头)
    "000021": "L2_细分龙头",  # 深科技(存储封测细分龙头)
    "603893": "L2_细分龙头",  # 瑞芯微(消费IC细分龙头)
    # L3 题材跟风/普通标的
    "603728": "L3_题材跟风",  # 鸣志电器
}
GRADE_CONFIG = {
    "L1_行业龙头": {
        "profit_targets": [0.18, 0.40, 0.50],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.08,      # 8%止损（中档）
        "trailing_stop": 0.06,   # 6%回撤止盈
        "position_pct": 0.20,    # 单票上限20%
        "time_stop": {
            (10, 15): 0.03,
            (15, 20): 0.07,
            (20, 25): 0.12,
            (25, 999): 0.15,
        }
    },
    "L2_细分龙头": {
        "profit_targets": [0.12, 0.22, 0.38],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.07,      # 7%止损（中档）
        "trailing_stop": 0.05,   # 5%回撤止盈
        "position_pct": 0.15,    # 单票上限15%
         "time_stop": {
            (8, 12): 0.02,
            (12, 16): 0.05,
            (16, 20): 0.08,
            (20, 999): 0.10,
        }
    },
    "L3_题材跟风": {
        "profit_targets": [0.10, 0.18, 0.30],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.06,      # 6%止损（中档）
        "trailing_stop": 0.04,   # 4%回撤止盈
        "position_pct": 0.10,    # 单票上限10%
        "time_stop": {
            (5, 8): 0.01,
            (8, 12): 0.03,
            (12, 15): 0.05,
            (15, 999): 0.07,
        }
    },
}

# 保留旧格式兼容（calc_profit_target 会用到）
GRADE_RULE = GRADE_CONFIG  # 兼容别名
# ====================== 止盈策略结束 ======================


# 持仓文件
HOLDINGS_FILE = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json"

# 资金文件
CASH_FILE = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/cash_balance.json"

# 飞书配置
FEISHU_APP_ID = "cli_a93eb458ceb81cc0"
FEISHU_APP_SECRET = "1i18JUKuFhQEejUOkNividRbMdJBMpV8"
FEISHU_GROUP_ID = "oc_0ac1e4e8d09f939d887f4992bba2886b"
RECO_DIR = '/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/recommendations'

# 日志文件
LOG_DIR = Path("/home/jarvis/.openclaw/logs/stock")
LOG_FILE = LOG_DIR / "holding_push.log"


def log(msg):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def log_error(msg):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [ERROR] {msg}\n{traceback.format_exc()}"
    print(line, file=sys.stderr)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def get_tenant_token():
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


def load_holdings():
    with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_cash_balance():
    with open(CASH_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# ====================== 【止盈计算函数】 ======================


def get_profit_coef(trend_coef):
    if trend_coef >= 0.99:
        return 1.2
    elif trend_coef >= 0.75:
        return 1.0
    else:
        return 0.7
    
def calc_profit_target(code, cost, shares, trend_coef):
    profit_coef = get_profit_coef(trend_coef)  # 自动转换
    grade = STOCK_GRADE.get(code, "L3_题材跟风")
    cfg = GRADE_CONFIG[grade]
    
    

      # 动态止盈目标
    p1 = round(cost * (1 + cfg["profit_targets"][0] ), 2)
    p2 = round(cost * (1 + cfg["profit_targets"][1] ), 2)
    p3 = round(cost * (1 + cfg["profit_targets"][2] ), 2)

     # 卖出股数
    s1 = int(shares * cfg["sell_ratio"][0])
    s2 = int(shares * cfg["sell_ratio"][1])
    s3 = int(shares * cfg["sell_ratio"][2])

    # 分级止损（使用新配置）
    stop = round(cost * (1 + cfg["stop_loss"]), 2)

    return {
        "grade": grade,
        "p1": p1, "s1": s1,
        "p2": p2, "s2": s2,
        "p3": p3, "s3": s3,
        "stop": stop,
        "trailing_stop": cfg["trailing_stop"],      # 新增：回撤阈值
        "time_stop": cfg.get("time_stop", {}),
        "retreat": f"{cfg['trailing_stop']*100:.0f}%",
        "coef": profit_coef,
        "trend_coef": trend_coef,
        "position_pct": cfg["position_pct"],        # 新增：仓位上限
        "first_target": cfg["profit_targets"][0],  # ✅ 添加这一行
    }
# ====================== 止盈计算结束 ======================

def get_trade_calendar():
    """获取A股交易日历（带缓存）"""
    global _TRADE_CALENDAR
    if _TRADE_CALENDAR is None:
        # 获取历史至今的交易日数据
        trade_calendar = ak.tool_trade_date_hist_sina()
        # 转换为日期列表
        _TRADE_CALENDAR = set(pd.to_datetime(trade_calendar['trade_date']).dt.date)
    return _TRADE_CALENDAR

def count_trading_days(start_date, end_date):
    """精确计算两个日期之间的A股交易日数量"""
    if not start_date:
        return 0
    
    trade_days = get_trade_calendar()
    # 确保日期是date类型
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    
    # 统计区间内的交易日
    trading_days = [d for d in trade_days if start_date <= d <= end_date]
    
    return len(trading_days)

def run_analysis(session: str):
    """运行持仓分析（复用 main.py 的分析逻辑）"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from models import Holding, PositionAdvice, MarketState
    from market_analyzer import MarketAnalyzer
    from stock_analyzer import StockAnalyzer
    from risk_controller import RiskController

    # 加载持仓
    raw = load_holdings()
    cash_info = load_cash_balance()

    holdings = []
    for item in raw:
        h = Holding(
            code=item['code'], name=item['name'], cost=item['cost'],
            shares=item['shares'],
            init_shares=item['init_shares'],
            current_price=item.get('current_price', item['cost']),
            highest_price=item.get('highest_price', item['cost']),
            entry_date=datetime.strptime(item['entry_date'], "%Y-%m-%d"),
            last_add_date=datetime.strptime(item['last_add_date'], "%Y-%m-%d") if item.get('last_add_date') else datetime.now(),
            strategy_name=item.get('strategy_name', 'unknown'),
            score=item.get('score', 0),
            stop_level_hit=item.get('stop_level_hit'),
            stop_lose_hit=item.get('stop_lose_hit')
        )
        holdings.append(h)
    # print("加载持仓数据: ", holdings)
    # 初始化分析器
    market_analyzer = MarketAnalyzer()
    stock_analyzer = StockAnalyzer()
    #stock_analyzer.refresh_sector_strength()
    risk_controller = RiskController()
     # 大盘仓位建议
    position_advice = market_analyzer.calculate_position_limit()
    print("pos: ",position_advice)


  
    # 更新价格并分析
    results = []
    for h in holdings:
        r = stock_analyzer.fetch_stock_data(h.code)
        if not r or r[1] is None or r[0] is None:  # 防止 df_history 或 current_data 为 None
            print(f"[警告] 股票 {h.code} 获取数据不完整(df_history={r[0] is not None if r else False}, current={r[1] is not None if r else False})，跳过")
            continue
        df_history, current_data = r
        tech = stock_analyzer.calculate_technical_indicators(df_history)
        #print("技术指标: ", tech)
        score = stock_analyzer.calculate_comprehensive_score(h.code, current_data, tech)
        #print("综合评分: ", score)

        alert = risk_controller.check_ma_breakdown(
                    h, current_data.price, tech, current_data.volume_ratio
                )


        h.current_price = current_data.price
        h.score = score.total_score
        h.tech_indicators = tech
         # 计算盈亏
        profit_pct = (current_data.price - h.cost) / h.cost * 100
        profit_val = (current_data.price - h.cost) * h.shares

        stop_level_hit = h.stop_level_hit
        stop_lose_hit = h.stop_lose_hit
        # ========== 新增：计算回撤 ==========
        drawdown_pct = 0
        if h.highest_price > h.cost:
            drawdown_pct = (h.highest_price - current_data.price) / h.highest_price * 100
        
        # ========== 新增：计算持仓天数 ==========
        holding_days = 0
        if h.entry_date:
            start = h.entry_date    # 结束
            end = datetime.now()   # 开始
           
            #print("开始日期: ", start, "结束日期: ", end)
            holding_days = count_trading_days(start, end)
            #print("持仓天数（交易日）: ", holding_days)
            #holding_days = (datetime.now() - h.entry_date).days + 1


        
        # ========== 计算止盈信息 ==========
        profit_info = calc_profit_target(h.code, h.cost, h.init_shares, position_advice.trend_coef)
        
        # ========== 新增：收集预警消息 ==========
        alert_messages = []
        
        # ========== 时间止损检查 ==========
        time_stop_config = profit_info.get("time_stop", {})


        for (min_days, max_days), min_profit in time_stop_config.items():
            if min_days <= holding_days <= max_days:
                if profit_pct < min_profit * 100:
                    if min_profit <= 0.02:
                        action = "减仓30%"
                    elif min_profit <= 0.05:
                        action = "减仓50%"
                    elif min_profit <= 0.08:
                        action = "减仓70%"
                    else:
                        action = "清仓"
                    alert_messages.append(
                        f"⏰ 持仓{holding_days}天，利润{profit_pct:.1f}% < {min_profit*100:.0f}%，{action}"
                    )
                break

          # ========== 评分过低检查 ==========
        if score.total_score < 65:
            alert_messages.append(f"❌ 评分{score.total_score:.1f}<65，减仓50%")
           # ========== 合并原有 alert ==========
        if alert:
            alert_messages.append(f"⚠️ {alert.message} | {alert.action}")     

        results.append({
            'name': h.name,
            'code': h.code,
            'sector': score.sector_name,
            'current_price': current_data.price,
            'cost': h.cost,
            'alert': alert_messages,
            'shares': h.shares,
            'profit_pct': profit_pct,
            'profit_val': profit_val,
            'profit': profit_info,
            'stop_level_hit': stop_level_hit,
            'stop_lose_hit': stop_lose_hit,
            'score': score.total_score,
            'tech': tech,
            'strategy_name': h.strategy_name,
            'highest_price': h.highest_price,
            'drawdown_pct': drawdown_pct,
            'holding_days': holding_days,
        })

       # 计算持仓总市值
    position_value = sum(h.shares * h.current_price for h in holdings)
    #print(f"持仓市值: {position_value:,.2f}元")
       


    cash = cash_info.get('available_cash', 0)
    # 总资产 = 持仓市值 + 可用现金
    total_asset = position_value + cash

    current_position = position_value / (total_asset) if position_value > 0 else 0
    position_advice.current_position = current_position
    position_advice.available_position = max(0, position_advice.suggested_position - current_position)

    return results, position_advice, total_asset, cash_info



def build_card(session: str, results: list, position_advice, total_asset, cash_info, date_str: str):
    """构建飞书卡片"""
    is_morning = session == "MORNING"
    icon = "☀️" if is_morning else "🌙"
    label = "早盘持仓分析" if is_morning else "尾盘持仓分析"
    time_hint = "09:15" if is_morning else "14:50"

    state_emoji = {
        "强势主升": "🚀",
        "震荡偏多": "📈",
        "弱势震荡": "📊",
        "下跌趋势": "📉",
        "系统性风险": "🚨"
    }
    state_icon = state_emoji.get(position_advice.market_state.value, "📊")

    total_profit = total_asset - cash_info.get('initial_capital', 0)
    
    # 分类：需要操作 vs 正常持仓
    need_action = []
    normal_holdings = []
    
    for r in results:
        # 判断是否需要操作
        action_reasons = []
        
        # 阶段1：跌破5日线或10日线
        #if r['profit_pct'] < r['profit']['first_target'] * 100:
        if r['tech']:
            p = r['current_price']
            # 当前股票的盈亏金额
            cur_profit_val = r['profit_val']

            # 1. 达到止盈目标（分批卖出提醒）
            pf = r['profit']
            current_price = r['current_price']
            stop_profit_hit = r['stop_level_hit']
            #print("stop_profit_hit: ", stop_profit_hit[0], stop_profit_hit[1], stop_profit_hit[2])
            if current_price >= pf['p1'] and not stop_profit_hit[0]:
                action_reasons.append(f"🎯 达到第一止盈{pf['p1']} → 卖出{pf['s1']}股")
            if current_price >= pf['p2'] and not stop_profit_hit[1]:
                action_reasons.append(f"🎯 达到第二止盈{pf['p2']} → 卖出{pf['s2']}股")
            if current_price >= pf['p3'] and not stop_profit_hit[2]:
                action_reasons.append(f"🎯 达到第三止盈{pf['p3']} → 卖出{pf['s3']}股")



            # 止损策略
            stop_loss_hit = r['stop_lose_hit']
            print("stop_loss_hit: ", stop_loss_hit[0], stop_loss_hit[1], stop_loss_hit[2], stop_loss_hit[3])

            # 当前股票的总金额
            cur_total_val = r['current_price'] * r['shares']
            # 盈亏比例 = 盈亏金额 / 总金额
            cur_profit_pct = cur_profit_val / cur_total_val if cur_total_val > 0 else 0
            # print('当前盈亏金额：', cur_profit_val, '当前总金额：', cur_total_val, '盈亏比例：', cur_profit_pct)
           
            # 盈亏金额达到总金额的10%才触发更强烈的卖出建议
            # if 'RSI超卖' in r['strategy_name']:
            #     print("触发策略： ", r['strategy_name'])
            if cur_profit_pct <= -0.06 and cur_profit_pct > -0.08 and not stop_loss_hit[2]:
                action_reasons.append(f"**买入价/现价: {r['cost']:.2f}/{r['current_price']:.2f}** 🟡 亏损: {cur_profit_val:.2f} 亏损比例: {cur_profit_pct:.2%}) → 建议减仓: {r['shares'] * 0.5}\n")
            elif cur_profit_pct <= -0.08 and not stop_loss_hit[3]:
                action_reasons.append(f"**买入价/现价: {r['cost']:.2f}/{r['current_price']:.2f}** 🔴 亏损: {cur_profit_val:.2f}  亏损比例: {cur_profit_pct:.2%}) → 强烈建议离场: {r['shares']}\n")
            elif 'RSI超卖' not in r['strategy_name']:
                if hasattr(r['tech'], 'ma10') and r['tech'].ma10 and p < r['tech'].ma10 and not stop_loss_hit[1]:
                    action_reasons.append(f"**买入价/现价: {r['cost']:.2f}/{r['current_price']:.2f}** 🟡 跌破10日线({r['tech'].ma10:.2f} ) → 强烈建议离场: {r['shares']}")
                elif hasattr(r['tech'], 'ma5') and r['tech'].ma5 and p < r['tech'].ma5 and not stop_loss_hit[0]:
                    action_reasons.append(f"**买入价/现价: {r['cost']:.2f}/{r['current_price']:.2f}** 🔴 跌破5日线({r['tech'].ma5:.2f} ) → 建议减仓: {r['shares'] * 0.5}")

        # 时间止损
        if r['alert'] and isinstance(r['alert'], list):
            for msg in r['alert']:
                if '⏰' in msg:
                    action_reasons.append(f"**买入价/现价: {r['cost']:.2f}/{r['current_price']:.2f}** | {msg}")
                    break
        
        # # 评分过低（<60）
        # if r['score'] < 60:
        #     action_reasons.append(f"❌ 评分{r['score']:.0f}<60 → 减仓50%")
        
        # 分类
        stock_info = {
            'name': r['name'],
            'code': r['code'],
            'sector': r['sector'].split('/')[-1] if r['sector'] else '未知',
            'holding_days': r.get('holding_days', 0),
            'profit_pct': r['profit_pct'],
            'profit_val': r['profit_val'],
            'current_price': r['current_price'],
            'cost': r['cost'],
            'shares': r['shares'],
            'profit': r['profit'],
            'strategy_name': r.get('strategy_name', ''),
            'reasons': action_reasons
        }
        
        if action_reasons:
            need_action.append(stock_info)
        else:
            normal_holdings.append(stock_info)
    
    # 构建卡片内容
    card_content_lines = []
    
    # 头部
    card_content_lines.append(f"**{icon} {label}** | {date_str} {time_hint}")
    card_content_lines.append("")
    
    # 需要操作区块
    if need_action:
        card_content_lines.append(f"⚠️ 需要操作 ({len(need_action)}只)")
        card_content_lines.append("")
        for s in need_action:
            card_content_lines.append(f"**{s['name']} 持有: 📅{s['holding_days']}天** {s['sector']} 持股数:{s['shares']}")
            # 操作原因（第一条最重要）
            card_content_lines.append(f"{s['reasons'][0]}")
            # 止盈止损
            pf = s['profit']
            card_content_lines.append(f"🎯 {pf['p1']}/{pf['p2']}/{pf['p3']}")
            card_content_lines.append("")
    
    # 正常持仓区块
    if normal_holdings:
        card_content_lines.append(f"✅ 正常持仓 ({len(normal_holdings)}只)")
        card_content_lines.append("")
        for s in normal_holdings:
            profit_emoji = "🟢" if s['profit_pct'] >= 0 else "🔴"
            card_content_lines.append(
                f"**{s['name']}** {profit_emoji} {s['profit_pct']:+.1f}% , 盈亏: {s['profit_val']:+,.0f} | 持股数: {s['shares']} | 持有: 📅{s['holding_days']}天"
            )
        card_content_lines.append("")
    
    # 仓位与资产
    card_content_lines.append("---")
    card_content_lines.append(f"📊 **仓位与资产**")
    #card_content_lines.append(f"大盘: {state_icon} {position_advice.market_state.value}")
    #card_content_lines.append(f"仓位: 🎯建议{position_advice.suggested_position*100:.0f}% | 💵当前{position_advice.current_position*100:.1f}% | ➕可用{position_advice.available_position*100:.0f}%")
    card_content_lines.append(f"**总资产: {total_asset:+,.0f}元 ** \n**总盈亏: {total_profit:+,.0f}元**\n**可用现金: {cash_info.get('available_cash', 0):+,.0f}元**")
    card_content_lines.append("")
    card_content_lines.append("⚠️ 仅供参考")
    
    # 构建飞书卡片
    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(card_content_lines)
            }
        }
    ]
    
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{icon} 持仓监控 | {label}"},
            "subtitle": {"tag": "plain_text", "content": f"{date_str} {time_hint}"},
            "template": "blue" if is_morning else "purple"
        },
        "elements": elements
    }
    return card


def main():
    session = sys.argv[1] if len(sys.argv) > 1 else "MORNING"
    date_str = datetime.now().strftime('%Y-%m-%d')

    print(f"[持仓监控] 开始{session}分析...")

    try:
        results, position_advice, total_asset, cash_info = run_analysis(session)
        print(f"[持仓监控] 分析完成，获取到 {len(results)} 只持仓数据")
    except Exception as e:
        print(f"[持仓监控] 分析失败: {e}")
        results, position_advice = [], None

    if results and position_advice:
        card = build_card(session, results, position_advice,total_asset,cash_info,date_str)
        log(f"卡片构建完成，共{len(results)}只持仓，准备推送...")
        #print("card:", card)
        #return
        try:
            token = get_tenant_token()
            resp = send_feishu_card(token, card, FEISHU_GROUP_ID)
            code = resp.get('code')
            msg = resp.get('msg') or resp.get('message', '')
            if code == 0:
                log(f"飞书推送成功: code={code} msg={msg}")
            else:
                log_error(f"飞书推送失败: code={code} msg={msg} resp={resp}")
        except Exception as e:
            log_error(f"飞书推送异常")
    else:
        log("无数据，跳过推送")


if __name__ == "__main__":
    main()
