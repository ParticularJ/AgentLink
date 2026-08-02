"""
轻量级飞书推送模块
直接调用飞书开放API，发送富文本卡片消息到群
"""

import json, time, requests
from datetime import datetime
from pathlib import Path

# 飞书应用凭证（从CXMT监控脚本同款配置）
FEISHU_APP_ID     = "cli_a93eb458ceb81cc0"
FEISHU_APP_SECRET = "1i18JUKuFhQEejUOkNividRbMdJBMpV8"
FEISHU_GROUP_ID   = "oc_0ac1e4e8d09f939d887f4992bba2886b"

LOG_DIR = Path("/home/jarvis/.openclaw/logs/stock")
LOG_FILE = LOG_DIR / "emotion_feishu_push.log"

def _log(msg):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def _get_token():
    """获取 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        r = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10)
        r.raise_for_status()
        token = r.json().get("tenant_access_token", "")
        if token:
            return token
    except Exception as e:
        _log(f"获取token失败: {e}")
    return None

def _send_card(card: dict) -> dict:
    """发送卡片消息到飞书群"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }
    payload = {
        "receive_id": FEISHU_GROUP_ID,
        "msg_type": "interactive",
        "content": json.dumps(card),
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        _log(f"发送失败: {e}")
        return {"code": -1, "msg": str(e)}

def _build_signal_card(signals: dict, phase: str) -> dict:
    """构建信号卡片"""
    buy_signals  = signals.get("buy", [])
    sell_signals = signals.get("sell", [])

    # 标题
    total = len(buy_signals) + len(sell_signals)
    if total == 0:
        return None

    title_emoji = "📥" if buy_signals else "📤"
    title_color = "#1F7A1F" if buy_signals else "#D43030"

    # 构造元素
    elements = []

    # 头部
    elements.append({
        "tag": "markdown",
        "content": f"**{title_emoji} 早盘信号 [{phase}]**"
    })

    # 买入信号
    if buy_signals:
        for s in buy_signals:
            confidence = s.get("confidence", 0)
            conf_bar = "▓" * int(confidence * 10) + "░" * (10 - int(confidence * 10))
            urgency = "🔴" if s.get("urgency") == "HIGH" else "🟡"
            elements.append({
                "tag": "markdown",
                "content": (
                    f"**{urgency} 买入 {s.get('name','')}({s.get('code','')})**\n"
                    f"> 操作: **{s.get('action','')}** @ {s.get('price', 0):.2f}\n"
                    f"> 股数: {s.get('shares',0)}股 / {s.get('amount',0):.0f}元\n"
                    f"> 置信度: {conf_bar} {confidence*100:.0f}%\n"
                    f"> 原因: {s.get('reason','')}\n"
                    f"> 标签: {' '.join(s.get('tags',[]))}"
                )
            })

    # 卖出信号
    if sell_signals:
        for s in sell_signals:
            urgency = "🔴" if s.get("urgency") == "HIGH" else "🟡"
            elements.append({
                "tag": "markdown",
                "content": (
                    f"**{urgency} 卖出 {s.get('name','')}({s.get('code','')})**\n"
                    f"> 操作: **{s.get('action','')}** @ {s.get('price', 0):.2f}\n"
                    f"> 股数: {s.get('shares',0)}股\n"
                    f"> 成本对比: {s.get('gain_vs_cost',0):+.1f}%\n"
                    f"> 原因: {s.get('reason','')}"
                )
            })

    # 底部时间戳
    elements.append({
        "tag": "markdown",
        "content": f"---\n*生成时间: {datetime.now().strftime('%H:%M:%S')}*"
    })

    return {
        "config": {"wide_screen_mode": True},
        "elements": elements
    }

def push_signals(signals: dict, phase: str = "早盘") -> bool:
    """推送信号到飞书群"""
    if not signals.get("buy") and not signals.get("sell"):
        return False

    card = _build_signal_card(signals, phase)
    if not card:
        return False

    result = _send_card(card)
    ok = result.get("code") == 0
    if ok:
        _log(f"✅ 推送成功: 买入{len(signals.get('buy',[]))}个 卖出{len(signals.get('sell',[]))}个")
    else:
        _log(f"❌ 推送失败: {result.get('msg', result)}")
    return ok

def push_status(phase: str, quotes_count: int, signal_count: int) -> bool:
    """推送状态心跳"""
    card = {
        "config": {"wide_screen_mode": True},
        "elements": [{
            "tag": "markdown",
            "content": f"**⏰ 早盘监控心跳**\n> 阶段: {phase}\n> 监控标的: {quotes_count}支\n> 当前信号: {signal_count}个\n> 时间: {datetime.now().strftime('%H:%M:%S')}"
        }]
    }
    result = _send_card(card)
    return result.get("code") == 0
