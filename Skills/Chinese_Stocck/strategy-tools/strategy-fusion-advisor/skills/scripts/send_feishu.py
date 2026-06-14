#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推送最新早盘推荐至飞书群"""
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

def send_feishu_msg(token, group_id, content):
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "receive_id": group_id,
        "msg_type": "text",
        "content": json.dumps({"text": content})
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_latest_reco():
    files = glob.glob(os.path.join(RECO_DIR, "*_morning*recommendation.json"))
    if not files:
        print("未找到早盘推荐文件")
        sys.exit(0)
    latest = max(files, key=os.path.getmtime)
    with open(latest, encoding='utf-8') as f:
        return json.load(f), os.path.basename(latest)

def format_message(data, filename):
    date_str = data.get('date', datetime.now().strftime('%Y%m%d'))
    recs = data.get('recommendations', [])
    lines = [f"📊 **{date_str} 早盘精选推荐**", ""]
    if not recs:
        lines.append("今日无符合条件的推荐股票")
    else:
        for i, rec in enumerate(recs, 1):
            code = rec.get('code', rec.get('stock_code', 'N/A'))
            name = rec.get('name', rec.get('stock_name', ''))
            combined_score = rec.get('combined_score', rec.get('best_score', 0))
            best_score = rec.get('best_score', 0)
            strategies = rec.get('strategies', [])
            strategies_str = ', '.join(strategies) if isinstance(strategies, list) else str(strategies)
            entry_reason = rec.get('target_reason', rec.get('reason', ''))
            position = rec.get('position_pct', 0)
            lines.append(f"**{i}. {code} {name}**")
            lines.append(f"   综合评分：{combined_score}（最高单策略：{best_score}）| 命中策略：{strategies_str}")
            if entry_reason:
                lines.append(f"   买入理由：{entry_reason}")
            if position:
                lines.append(f"   建议仓位：{position}%")
    lines.append("")
    lines.append(f"_📁 文件：{filename}_")
    return '\n'.join(lines)

if __name__ == "__main__":
    data, fname = get_latest_reco()
    msg = format_message(data, fname)
    print(msg)

    try:
        token = get_tenant_token()
        result = send_feishu_msg(token, FEISHU_GROUP_ID, msg)
        print(f"[OK] 已推送至飞书群: {result}")
    except Exception as e:
        print(f"[ERROR] 推送失败: {e}")
        sys.exit(1)
