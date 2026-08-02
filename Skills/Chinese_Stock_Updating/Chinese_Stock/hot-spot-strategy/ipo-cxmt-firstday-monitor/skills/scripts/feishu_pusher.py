#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CXMT首日作战矩阵 - 飞书推送模块
将实时监控状态/操作建议/铁律预警推送到飞书群
"""

import os
import sys
import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

import requests
from colorama import Fore, Style, init

init(autoreset=True)

# ==================== 飞书配置 ====================

FEISHU_APP_ID = "cli_a93eb458ceb81cc0"
FEISHU_APP_SECRET = "1i18JUKuFhQEejUOkNividRbMdJBMpV8"
FEISHU_GROUP_ID = "oc_0ac1e4e8d09f939d887f4992bba2886b"

# 日志
LOG_DIR = Path("/home/jarvis/.openclaw/logs/stock")
LOG_FILE = LOG_DIR / "cxmt_push.log"


def log(msg: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def log_error(msg: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [ERROR] {msg}\n{traceback.format_exc()}"
    print(line, file=sys.stderr)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ==================== 飞书认证 ====================

def get_tenant_token(max_retries: int = 3, retry_interval: int = 5) -> Optional[str]:
    """获取 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                url,
                json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
                timeout=10
            )
            resp.raise_for_status()
            result = resp.json()
            token = result.get("tenant_access_token", "")
            if token:
                if attempt > 1:
                    log(f"获取token重试第{attempt}次成功")
                return token
            log(f"获取token为空，第{attempt}次重试")
        except Exception as e:
            log(f"获取token异常 ({attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            time.sleep(retry_interval)
    log_error("获取token全部重试失败")
    return None


# ==================== 卡片构建 ====================

def _color_for_gain(gain_pct: float) -> str:
    """涨幅决定卡片颜色"""
    if gain_pct > 80:
        return "red"
    elif gain_pct > 50:
        return "orange"
    elif gain_pct > 0:
        return "green"
    elif gain_pct == 0:
        return "grey"
    else:
        return "blue"


def _phase_emoji(phase: str) -> str:
    return {
        "集合竞价": "🔔",
        "开盘连续竞价": "🚀",
        "冲高回落监控": "📉",
        "尾盘确认": "🌙",
        "收盘": "📊",
        "盘中": "⏳",
    }.get(phase, "⏳")


def _action_emoji(action: str) -> str:
    if "禁止" in action or "放弃" in action:
        return "🛑"
    elif "买入" in action or "加仓" in action:
        return "✅"
    elif "观望" in action:
        return "👀"
    elif "等" in action:
        return "⏰"
    else:
        return "📌"


def _iron_rules_md(iron: Dict, gain_pct: float, used_budget: int) -> str:
    """构建铁律检查markdown"""
    lines = []
    for r in iron.get("rules", []):
        status = r["status"]
        rule_num = r["rule"]
        desc = r["desc"]
        value = r["value"]

        if status in ["通过", "正常"]:
            icon = "✅"
        elif "⚠️" in status:
            icon = "❌"
        else:
            icon = "⚠️"

        lines.append(f"{icon} **铁律{rule_num}** {desc} → {status}({value})")
    return "\n".join(lines)


def build_realtime_status_card(
    phase: str,
    price: float,
    gain_pct: float,
    issue_price: float,
    threshold_80: float,
    action_result: Dict,
    iron: Dict,
    used_budget: int,
    remaining_budget: int,
    peak_price: float,
) -> Dict:
    """
    构建实时状态卡片
    每轮监控推送，简洁版
    """
    action = action_result.get("action", "观望")
    amount = action_result.get("amount", 0)
    reason = action_result.get("reason", "")
    rule_broken = action_result.get("rule_broken", [])
    alert_level = action_result.get("alert_level", "正常")
    phase_emoji_str = _phase_emoji(phase)
    action_emoji_str = _action_emoji(action)

    # 颜色
    color = _color_for_gain(gain_pct)
    alert_color = "red" if alert_level == "高危" else ("orange" if alert_level == "警告" else "grey")

    # 操作区块
    action_md = f"**{action_emoji_str} 本阶段操作: {action}**"
    if amount > 0:
        action_md += f"\n> 💰 买入金额: **{amount // 10000:.0f}万**"
    if reason:
        action_md += f"\n> 📝 {reason}"

    # 仓位进度条文字
    budget_bar_len = 20
    filled = int(used_budget / 200000 * budget_bar_len)
    bar = "█" * filled + "░" * (budget_bar_len - filled)
    budget_md = (
        f"**首日仓位**: {bar} `{used_budget // 10000:.0f}万` / 20万\n"
        f"**剩余预算**: {remaining_budget // 10000:.0f}万"
    )

    # 铁律
    iron_md = _iron_rules_md(iron, gain_pct, used_budget)

    # 告警信息
    alert_md = ""
    if rule_broken:
        alert_md = f"🛑 **铁律预警**: {' '.join(rule_broken)}"

    elements = [
        # 价格信息
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**📈 CXMT首日作战矩阵**\n\n"
                    f"**阶段**: {phase_emoji_str} {phase}\n"
                    f"**当前价**: `{price:.2f}元`\n"
                    f"**涨幅(vs发行价)**: `{gain_pct:+.1f}%`\n"
                    f"**200%涨幅线**: {threshold_80:.1f}元\n"
                    f"**今日最高**: {peak_price:.2f}元"
                )
            }
        },
        {"tag": "hr"},
        # 操作建议
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": action_md}
        },
        {"tag": "hr"},
        # 仓位
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": budget_md}
        },
        {"tag": "hr"},
        # 铁律检查
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": iron_md}
        },
    ]

    if alert_md:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": alert_md}})

    # 底部免责
    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": "⚠️ 仅供参考，不构成投资建议。股市有风险，投资需谨慎。"}
        ]
    })

    card = {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"📊 CXMT首日监控 | {phase}"
            },
            "subtitle": {
                "tag": "plain_text",
                "content": f"{alert_level} | {datetime.now().strftime('%H:%M:%S')}"
            },
            "template": color if alert_level == "正常" else alert_color
        },
        "elements": elements
    }
    return card


def build_action_alert_card(
    phase: str,
    price: float,
    gain_pct: float,
    action: str,
    amount: int,
    reason: str,
    iron: Dict,
    threshold_80: float,
) -> Dict:
    """
    构建操作触发告警卡片（当阶段操作变化时推送）
    """
    color = _color_for_gain(gain_pct)
    phase_emoji_str = _phase_emoji(phase)

    iron_md = _iron_rules_md(iron, gain_pct, 0)

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**🚨 CXMT操作信号**\n\n"
                    f"**阶段**: {phase_emoji_str} {phase}\n"
                    f"**当前价**: `{price:.2f}元`\n"
                    f"**涨幅**: `{gain_pct:+.1f}%` (200%线: {threshold_80:.1f}元)"
                )
            }
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**✅ 操作建议: {action}**\n"
                    f"**买入金额: {amount // 10000:.0f}万**\n"
                    f"**原因: {reason}**"
                )
            }
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": iron_md}
        },
        {
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": "⚠️ 仅供参考，不构成投资建议。股市有风险，投资需谨慎。"}
            ]
        },
    ]

    card = {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"🚨 CXMT操作信号 | {phase}"
            },
            "subtitle": {
                "tag": "plain_text",
                "content": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "template": color
        },
        "elements": elements
    }
    return card


def build_iron_rule_alert_card(
    rule_num: int,
    rule_desc: str,
    current_value: str,
    threshold: str,
    phase: str,
    price: float,
    gain_pct: float,
) -> Dict:
    """构建铁律触发告警卡片"""
    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**🛑 CXMT铁律触发告警**\n\n"
                    f"**触发铁律**: 铁律{rule_num} - {rule_desc}\n"
                    f"**当前值**: {current_value} (阈值: {threshold})\n"
                    f"**阶段**: {phase}\n"
                    f"**价格**: {price:.2f}元 | 涨幅: {gain_pct:+.1f}%"
                )
            }
        },
        {
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": "⚠️ 铁律触发，强烈建议遵守交易纪律！"}
            ]
        },
    ]

    return {
        "header": {
            "title": {"tag": "plain_text", "content": f"🛑 CXMT铁律告警 | 铁律{rule_num}"},
            "subtitle": {"tag": "plain_text", "content": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
            "template": "red"
        },
        "elements": elements
    }


def build_market_context_card(
    issue_price: float,
    threshold_80: float,
    phase: str,
    dram_alert: str,
    market_indices: List[Dict],
) -> Dict:
    """构建市场背景卡片（开盘前/盘前推送）"""
    indices_md = "\n".join([
        f"- **{idx['name']}**: {idx['price']} ({idx['pct']:+.2f}%)"
        for idx in market_indices
    ]) if market_indices else "_暂无指数数据_"

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**📋 CXMT首日开盘前参考**\n\n"
                    f"**发行价**: {issue_price:.1f}元\n"
                    f"**200%涨幅线**: {threshold_80:.1f}元\n"
                    f"**50%涨幅线**: {issue_price * 1.5:.1f}元\n\n"
                    f"**大盘参考**:\n{indices_md}\n\n"
                    f"**DRAM景气**: {dram_alert}"
                )
            }
        },
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "**📌 操作参考**:\n"
                    "- 涨幅≤50%: 限额买入15万\n"
                    "- 涨幅50-200%: 谨慎买入5万\n"
                    "- 涨幅>200%: **一股不买**"
                )
            }
        },
        {
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": "⚠️ 仅供参考，不构成投资建议。股市有风险，投资需谨慎。"}
            ]
        },
    ]

    return {
        "header": {
            "title": {"tag": "plain_text", "content": "📋 CXMT首日开盘参考"},
            "subtitle": {"tag": "plain_text", "content": f"{dram_alert}"},
            "template": "grey"
        },
        "elements": elements
    }


def build_daily_summary_card(
    close_price: float,
    gain_pct: float,
    peak_price: float,
    used_budget: int,
    final_positions: Dict,
    iron_summary: List[Dict],
) -> Dict:
    """构建收盘总结卡片"""
    used_pct = used_budget / 400000 * 100

    iron_lines = []
    for r in iron_summary:
        icon = "✅" if r["status"] in ["通过", "正常"] else "❌"
        iron_lines.append(f"{icon} 铁律{r['rule']}: {r['desc']} → {r['value']}")

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**📊 CXMT首日收盘报告**\n\n"
                    f"**收盘价**: `{close_price:.2f}元`\n"
                    f"**全天涨幅**: `{gain_pct:+.1f}%`\n"
                    f"**今日最高**: {peak_price:.2f}元\n"
                    f"**首日仓位**: {used_budget // 10000:.0f}万 / 40万 ({used_pct:.0f}%)"
                )
            }
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**持仓情况**:\n"
                    f"- 持仓股数: {final_positions.get('shares', 0)}股\n"
                    f"- 持仓均价: {final_positions.get('avg_cost', 0):.2f}元\n"
                    f"- 总投入: {final_positions.get('total_cost', 0) // 10000:.0f}万"
                )
            }
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**铁律检查**:\n" + "\n".join(iron_lines)
            }
        },
        {
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": "⚠️ 仅供参考，不构成投资建议。股市有风险，投资需谨慎。"}
            ]
        },
    ]

    color = _color_for_gain(gain_pct)
    return {
        "header": {
            "title": {"tag": "plain_text", "content": "📊 CXMT首日收盘报告"},
            "subtitle": {"tag": "plain_text", "content": f"涨幅{gain_pct:+.1f}% | 仓位{used_pct:.0f}%"},
            "template": color
        },
        "elements": elements
    }


# ==================== 发送接口 ====================

def send_card(
    card: Dict,
    group_id: str = FEISHU_GROUP_ID,
    max_retries: int = 3,
    retry_interval: int = 5,
) -> Dict:
    """发送飞书卡片到群组"""
    token = get_tenant_token()
    if not token:
        return {"code": -1, "msg": "获取token失败"}

    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "receive_id": group_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False)
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            code = result.get("code")
            if code == 0:
                if attempt > 1:
                    log(f"飞书推送重试第{attempt}次成功")
                return result
            else:
                log(f"飞书返回错误: code={code} msg={result.get('msg','')}, 第{attempt}次重试")
        except Exception as e:
            log(f"推送异常 ({attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            time.sleep(retry_interval)

    return {"code": -1, "msg": "全部重试失败"}


# ==================== 便捷封装 ====================

def push_realtime_status(
    phase: str,
    price: float,
    gain_pct: float,
    issue_price: float,
    threshold_80: float,
    action_result: Dict,
    iron: Dict,
    used_budget: int,
    remaining_budget: int,
    peak_price: float,
) -> bool:
    """推送实时状态（每轮监控调用）"""
    card = build_realtime_status_card(
        phase, price, gain_pct, issue_price, threshold_80,
        action_result, iron, used_budget, remaining_budget, peak_price
    )
    result = send_card(card)
    ok = result.get("code") == 0
    if ok:
        log(f"实时状态推送成功: 阶段={phase} 价={price} 涨幅={gain_pct:+.1f}%")
    else:
        log_error(f"实时状态推送失败: {result.get('msg')}")
    return ok


def push_action_alert(
    phase: str,
    price: float,
    gain_pct: float,
    action: str,
    amount: int,
    reason: str,
    iron: Dict,
    threshold_80: float,
) -> bool:
    """推送操作信号（当操作变化时调用）"""
    card = build_action_alert_card(
        phase, price, gain_pct, action, amount, reason, iron, threshold_80
    )
    result = send_card(card)
    ok = result.get("code") == 0
    if ok:
        log(f"操作信号推送成功: {action} {amount // 10000:.0f}万")
    else:
        log_error(f"操作信号推送失败: {result.get('msg')}")
    return ok


def push_iron_rule_alert(
    rule_num: int,
    rule_desc: str,
    current_value: str,
    threshold: str,
    phase: str,
    price: float,
    gain_pct: float,
) -> bool:
    """推送铁律触发告警"""
    card = build_iron_rule_alert_card(
        rule_num, rule_desc, current_value, threshold,
        phase, price, gain_pct
    )
    result = send_card(card)
    ok = result.get("code") == 0
    if ok:
        log(f"铁律告警推送成功: 铁律{rule_num}")
    else:
        log_error(f"铁律告警推送失败: {result.get('msg')}")
    return ok


def push_market_context(
    issue_price: float,
    threshold_80: float,
    phase: str,
    dram_alert: str,
    market_indices: List[Dict],
) -> bool:
    """推送市场背景（开盘前调用）"""
    card = build_market_context_card(
        issue_price, threshold_80, phase, dram_alert, market_indices
    )
    result = send_card(card)
    ok = result.get("code") == 0
    if ok:
        log("市场背景推送成功")
    else:
        log_error(f"市场背景推送失败: {result.get('msg')}")
    return ok


def push_daily_summary(
    close_price: float,
    gain_pct: float,
    peak_price: float,
    used_budget: int,
    final_positions: Dict,
    iron_summary: List[Dict],
) -> bool:
    """推送收盘总结"""
    card = build_daily_summary_card(
        close_price, gain_pct, peak_price,
        used_budget, final_positions, iron_summary
    )
    result = send_card(card)
    ok = result.get("code") == 0
    if ok:
        log("收盘总结推送成功")
    else:
        log_error(f"收盘总结推送失败: {result.get('msg')}")
    return ok


# ==================== CLI入口 ====================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CXMT飞书推送测试")
    parser.add_argument("--type", default="context", choices=["context", "status", "action", "iron", "summary"],
                        help="卡片类型")
    args = parser.parse_args()

    if args.type == "context":
        card = build_market_context_card(
            issue_price=10.0,
            threshold_80=12.6,
            phase="集合竞价",
            dram_alert="⚠️ Q3涨幅13-18%，趋势放缓",
            market_indices=[
                {"name": "上证指数", "price": 3996.16, "pct": -1.00},
                {"name": "深证成指", "price": 15046.67, "pct": -2.29},
                {"name": "创业板指", "price": 3842.73, "pct": -4.33},
            ]
        )
    elif args.type == "status":
        action_result = {
            "action": "买入(限价)",
            "amount": 150000,
            "reason": "竞价涨幅35%≤50%，在可接受范围",
            "alert_level": "正常",
            "rule_broken": [],
        }
        iron = {
            "rules": [
                {"rule": 1, "desc": "涨幅>80%不买", "status": "通过", "value": "35.0%"},
                {"rule": 2, "desc": "首日仓位≤40万", "status": "通过", "value": "0万"},
                {"rule": 3, "desc": "DRAM涨幅监控", "status": "正常", "value": "正常"},
                {"rule": 4, "desc": "账户-8%止损", "status": "通过", "value": "0.0%"},
            ],
            "all_pass": True,
        }
        card = build_realtime_status_card(
            phase="集合竞价",
            price=13.5,
            gain_pct=35.0,
            issue_price=10.0,
            threshold_80=12.6,
            action_result=action_result,
            iron=iron,
            used_budget=0,
            remaining_budget=400000,
            peak_price=13.5,
        )
    elif args.type == "action":
        iron = {
            "rules": [
                {"rule": 1, "desc": "涨幅>80%不买", "status": "通过", "value": "65.0%"},
                {"rule": 2, "desc": "首日仓位≤40万", "status": "通过", "value": "15万"},
                {"rule": 3, "desc": "DRAM涨幅监控", "status": "正常", "value": "正常"},
                {"rule": 4, "desc": "账户-8%止损", "status": "通过", "value": "0.0%"},
            ],
            "all_pass": True,
        }
        card = build_action_alert_card(
            phase="集合竞价",
            price=16.5,
            gain_pct=65.0,
            action="买入(谨慎)",
            amount=50000,
            reason="竞价涨幅65%处于50%-80%区间，谨慎参与",
            iron=iron,
            threshold_80=12.6,
        )
    elif args.type == "iron":
        card = build_iron_rule_alert_card(
            rule_num=1,
            rule_desc="涨幅>80%不买",
            current_value="92.5%",
            threshold=">80%",
            phase="集合竞价",
            price=19.25,
            gain_pct=92.5,
        )
    elif args.type == "summary":
        card = build_daily_summary_card(
            close_price=14.20,
            gain_pct=42.0,
            peak_price=18.50,
            used_budget=250000,
            final_positions={"shares": 17857, "avg_cost": 14.00, "total_cost": 250000},
            iron_summary=[
                {"rule": 1, "desc": "涨幅>80%不买", "status": "通过", "value": "42.0%"},
                {"rule": 2, "desc": "首日仓位≤40万", "status": "通过", "value": "25万"},
                {"rule": 3, "desc": "DRAM涨幅监控", "status": "正常", "value": "正常"},
                {"rule": 4, "desc": "账户-8%止损", "status": "通过", "value": "0.0%"},
            ],
        )

    result = send_card(card)
    print(f"发送结果: code={result.get('code')} msg={result.get('msg')}")
