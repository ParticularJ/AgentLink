#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推送最新推荐至飞书群（interactive card格式）"""
import os, json, glob, sys, requests, traceback
from datetime import datetime
from pathlib import Path

RECO_DIR = '/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/recommendations'
FEISHU_APP_ID = "cli_a93eb458ceb81cc0"
FEISHU_APP_SECRET = "1i18JUKuFhQEejUOkNividRbMdJBMpV8"
FEISHU_GROUP_ID = "oc_0ac1e4e8d09f939d887f4992bba2886b"

LOG_DIR = Path("/home/jarvis/.openclaw/logs/stock")
LOG_FILE = LOG_DIR / "fusion_push.log"

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

def get_tenant_token_with_retry(max_retries=3, retry_interval=5):
    """获取tenant_access_token，带试错重试机制"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10)
            resp.raise_for_status()
            token = resp.json().get("tenant_access_token", "")
            if token:
                if attempt > 1:
                    log(f"获取token重试第{attempt}次成功")
                return token
            log(f"获取token为空, 第{attempt}次重试")
        except Exception as e:
            log(f"获取token异常 (第{attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            import time
            time.sleep(retry_interval)
    log_error("获取token全部重试失败，退出")
    sys.exit(1)

def build_card(date_str, session_label, recs, total_pos, success_count, no_result_count, err_count, filename):
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
        penalty = rec.get('penalty', rec.get('penalty', 0))
        if penalty < 0:
            penalty_reason = rec.get('penalty_reason', [])
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
                "content": f"**{emoji} {i+1}. {name}({code})**\n   综合评分：`{score}` | 最高单策略：`{best}`\n   确认策略：`{strat_str}`\n   买入理由：{reason}\n   **买入仓位: {pos}%**\n   **新闻损失: {penalty}分** \n  新闻原因: {penalty_reason if penalty < 0 else '无'}"
            }
        })

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**📊 策略运行概览**\n\n• 共计策略: {success_count + no_result_count + err_count}个\n• 有结果：{success_count}个 -无结果：{no_result_count}个 -运行错误：{err_count}个  \n• 融合推荐：{len(recs)} 只  \n• 总仓位建议：💰 **{total_pos}%**\n• 生成时间：{date_str}"}
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

def send_card_with_retry(token, group_id, card, max_retries=3, retry_interval=5):
    """发送飞书卡片，带试错重试机制"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "receive_id": group_id,
        "msg_type": "interactive",
        "content": json.dumps(card)
    }
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            code = result.get('code')
            if code == 0:
                if attempt > 1:
                    log(f"重试第{attempt}次成功")
                return result
            else:
                log(f"飞书返回错误: code={code} msg={result.get('msg','')}, 第{attempt}次重试")
        except Exception as e:
            log(f"推送异常 (第{attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            log(f"{retry_interval}秒后重试...")
            import time
            time.sleep(retry_interval)
    return {"code": -1, "msg": "全部重试失败"}

def get_latest_reco(session_filter="morning"):
    pattern = f"*_{session_filter}_*recommendation.json"
    files = glob.glob(os.path.join(RECO_DIR, pattern))
    if not files:
        log(f"未找到 {session_filter} 推荐文件")
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
    success_count = data.get('strategy_count',  0)
    no_result_count = data.get('no_result_count', 0)
    err_count = data.get('error_count',  0)
    session_label = data.get('session', 'MORNING_BUY')
    session_display = "早盘买（次日）" if "MORNING" in session_label else "尾盘买"

    card = build_card(date_str, session_display, recs, total_pos, success_count, no_result_count, err_count, fname)

    token = get_tenant_token_with_retry()
    result = send_card_with_retry(token, FEISHU_GROUP_ID, card)
    code = result.get('code')
    msg = result.get('msg', '')
    if code == 0:
        log(f"飞书推送成功: msg={msg}")
    else:
        log_error(f"飞书推送失败: code={code} msg={msg}")
    print(json.dumps(result, ensure_ascii=False))
