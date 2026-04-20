#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推送最新推荐至飞书群（interactive card格式）"""
import os, json, glob, sys, requests
from datetime import datetime

RECO_DIR = '/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/recommendations'
FEISHU_APP_ID = "cli_a93eb458ceb81cc0"
FEISHU_APP_SECRET = "1i18JUKuFhQEejUOkNividRbMdJBMpV8"
FEISHU_GROUP_ID = "oc_01eafbec4f9b3fb54ff669d792e3fb72"

def get_tenant_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10)
    resp.raise_for_status()
    return resp.json()["tenant_access_token"]

def build_card(date_str, session_label, recs, total_pos, filename):
    """构建飞书 interactive card"""
    template_map = {
        "早盘买（次日）": ("☀️", "orange"),
        "尾盘买": ("🌙", "blue"),
    }
    icon, color = template_map.get(session_label, ("📊", "grey"))

    # Top stocks
    stock_blocks = []
    emojis = ["🔥", "✅", "📌", "📌", "📌"]
    for i, rec in enumerate(recs[:5]):
        code = rec.get('code', rec.get('stock_code', 'N/A'))
        name = rec.get('name', rec.get('stock_name', ''))
        score = rec.get('combined_score', rec.get('best_score', 0))
        best = rec.get('best_score', 0)
        strategies = rec.get('strategies', [])
        strat_str = ', '.join(strategies) if isinstance(strategies, list) else str(strategies)
        reason = rec.get('target_reason', rec.get('reason', ''))
        pos = rec.get('position_pct', 0)
        emoji = emojis[i] if i < len(emojis) else "  "
        stock_blocks.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**{emoji} {i+1}. {name}({code})**\n   综合评分：`{score}` | 最高单策略：`{best}`\n   确认策略：`{strat_str}`\n   买入理由：{reason}\n   **买入仓位: {pos}%**"
            }
        })

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**📊 策略运行概览**\n\n• 运行策略：`{len(recs)}` 个  • 融合推荐：`{len(recs)}` 只  • 总仓位建议：💰 **{total_pos}%**\n• 生成时间：{date_str}"}
        },
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": "### 🏆 融合推荐 TOP 5"}},
    ]
    elements.extend(stock_blocks)
    elements.append({"tag": "hr"})
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**策略来源**：早盘融合策略组" if "早盘" in session_label else "**策略来源**：尾盘融合策略组"}})

    card = {
        "header": {
            "title": {"tag": "plain_text", "content": f"{icon} 融合推荐 | {date_str} {session_label}"},
            "subtitle": {"tag": "plain_text", "content": f"融合多策略 · {session_label}"},
            "template": color
        },
        "elements": elements + [
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "⚠️ 仅供参考，不构成投资建议。股市有风险，投资需谨慎。"}]}
        ]
    }
    return card

def send_card(token, group_id, card):
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "receive_id": group_id,
        "msg_type": "interactive",
        "content": json.dumps(card)
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_latest_reco(session_filter="morning"):
    pattern = f"*_{session_filter}_*recommendation.json"
    files = glob.glob(os.path.join(RECO_DIR, pattern))
    if not files:
        print(f"未找到 {session_filter} 推荐文件")
        sys.exit(0)
    latest = max(files, key=os.path.getmtime)
    with open(latest, encoding='utf-8') as f:
        data = json.load(f)
    return data, os.path.basename(latest)

if __name__ == "__main__":
    session = sys.argv[1] if len(sys.argv) > 1 else "morning"
    data, fname = get_latest_reco(session)

    date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    recs = data.get('recommendations', [])
    total_pos = data.get('total_position', 0)
    session_label = data.get('session', 'MORNING_BUY')
    session_display = "早盘买（次日）" if "MORNING" in session_label else "尾盘买"

    card = build_card(date_str, session_display, recs, total_pos, fname)

    token = get_tenant_token()
    result = send_card(token, FEISHU_GROUP_ID, card)
    print(json.dumps(result, ensure_ascii=False))
