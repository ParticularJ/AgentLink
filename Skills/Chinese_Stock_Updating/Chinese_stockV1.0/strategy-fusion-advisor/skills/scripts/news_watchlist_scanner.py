#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股池新闻扫描器
- 只扫描核心股（watchlist_core.yaml）+ 自选股（holdings.json）
- 仅推送"重大利空"：penalty <= -10 且命中强利空关键词
- 利好不再推送
"""
import os, json, sys, traceback, yaml
from datetime import datetime
from pathlib import Path

# 确保父目录在 PYTHONPATH
from test_news import recommendations_penalty

# 飞书配置
FEISHU_APP_ID = "cli_a93eb458ceb81cc0"
FEISHU_APP_SECRET = "1i18JUKuFhQEejUOkNividRbMdJBMpV8"
FEISHU_GROUP_ID = "oc_0ac1e4e8d09f939d887f4992bba2886b"

WATCHLIST_PATH = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_stock_pool/watchlist_core.yaml"
HOLDINGS_PATH = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json"
LOG_DIR = Path("/home/jarvis/.openclaw/logs/stock")
LOG_FILE = LOG_DIR / "watchlist_scan.log"


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


def load_watchlist(path: Path) -> list[tuple[str, str]]:
    """返回 [(股票名, 代码), ...]"""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    stocks = []
    for category, sections in data.get("watchlist", {}).items():
        for level in ["core", "focus"]:
            if level in sections:
                for item in sections[level]:
                    if isinstance(item, list) and len(item) >= 2:
                        stocks.append((item[0], item[1]))
    return stocks


def load_holdings(path: Path) -> list[tuple[str, str]]:
    """从 holdings.json 加载自选股，返回 [(股票名, 代码), ...]"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    stocks = []
    for item in data:
        code = item.get("code", "")
        name = item.get("name", "")
        if code and name:
            stocks.append((name, code))
    return stocks


def get_tenant_token_with_retry(max_retries=3, retry_interval=5):
    import requests, time
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
            time.sleep(retry_interval)
    log_error("获取token全部重试失败，退出")
    sys.exit(1)


def send_card_with_retry(token, group_id, card, max_retries=3, retry_interval=5):
    import requests, time
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
            time.sleep(retry_interval)
    return {"code": -1, "msg": "全部重试失败"}


SEVERE_PENALTY_THRESHOLD = -10
SEVERE_KEYWORDS = [
    "退市", "ST", "*ST", "立案", "调查", "处罚", "处罚决定",
    "财务造假", "造假", "违规", "减持", "清仓减持", "大额减持",
    "诉讼", "仲裁", "冻结", "质押爆仓", "强平", "亏损", "巨亏",
    "停牌", "停牌核查", "跌停", "连续跌停", "商誉减值",
    "业绩预亏", "首亏", "退市风险", "风险警示", "重大违法",
    "问询函", "关注函", "监管函", "解聘", "辞职", "被查",
]


def is_severe_negative(penalty: int, reasons: list) -> bool:
    """判定是否重大利空：分值 <= -10 且原因命中关键词"""
    if penalty > SEVERE_PENALTY_THRESHOLD:
        return False
    if not reasons:
        return penalty <= SEVERE_PENALTY_THRESHOLD
    blob = "；".join(reasons)
    return any(kw in blob for kw in SEVERE_KEYWORDS)


def analyze_stock(name: str, code: str) -> dict:
    """分析单只股票，返回 {'name', 'code', 'penalty', 'reasons'}"""
    try:
        log(f"分析 {name}({code})...")
        penalty, reasons = recommendations_penalty(code, name)
        log(f"  → penalty={penalty}, reasons={reasons}")
        return {"name": name, "code": code, "penalty": penalty, "reasons": reasons}
    except Exception as e:
        log_error(f"分析 {name}({code}) 失败: {e}")
        return None


def build_severe_negative_card(date_str, severe_stocks, scanned_total):
    """仅构建重大利空卡片（无重大利空时返回 None 跳过推送）"""
    if not severe_stocks:
        log(f"无重大利空股票（扫描 {scanned_total} 只），跳过推送")
        return None

    elements = []
    summary = (
        f"**🚨 重大利空扫描结果**\n\n"
        f"• 扫描总数：{scanned_total} 只\n"
        f"• 触发重大利空：{len(severe_stocks)} 只\n"
        f"• 阈值：penalty ≤ -10 且命中强利空关键词\n"
        f"• 扫描时间：{date_str}"
    )
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": summary}})

    elements.append({"tag": "hr"})
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "### ⚠️ 重大利空清单"}})
    emojis_neg = ["🚨", "🔻", "📉", "📉", "📉", "📉", "📉", "📉", "📉", "📉"]
    for i, stk in enumerate(severe_stocks[:10]):
        reason_text = "；".join(stk["reasons"]) if stk["reasons"] else "新闻情绪偏负面"
        emoji = emojis_neg[i] if i < len(emojis_neg) else "  "
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**{emoji} {i+1}. {stk['name']}({stk['code']})**\n   利空分：{stk['penalty']}\n   利空原因：{reason_text}"
            }
        })

    elements.append(
        {"tag": "note", "elements": [{"tag": "plain_text", "content": "⚠️ 仅供参考，不构成投资建议。重大利空请结合持仓与风险偏好决策。"}]}
    )

    return {
        "header": {
            "title": {"tag": "plain_text", "content": f"🚨 重大利空提醒 | {date_str}"},
            "subtitle": {"tag": "plain_text", "content": "仅推送重大利空 · 普通利空已过滤"},
            "template": "red"
        },
        "elements": elements
    }


if __name__ == "__main__":
    import requests

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    log("=" * 50)
    log(f"股池重大利空扫描开始 | {date_str}")

    # 1. 加载核心股池
    core_stocks = load_watchlist(WATCHLIST_PATH)
    log(f"加载核心股池完成，共 {len(core_stocks)} 只股票")

    # 2. 加载自选股
    holdings_stocks = load_holdings(HOLDINGS_PATH)
    log(f"加载自选股完成，共 {len(holdings_stocks)} 只股票")

    # 3. 去重合并
    seen_codes = set()
    scan_targets = []
    for name, code in core_stocks:
        if code not in seen_codes:
            seen_codes.add(code)
            scan_targets.append((name, code))
    for name, code in holdings_stocks:
        if code not in seen_codes:
            seen_codes.add(code)
            scan_targets.append((name, code))

    log(f"去重后总扫描数：{len(scan_targets)} 只")

    # 4. 全部扫描，仅筛选重大利空
    severe_stocks = []
    for name, code in scan_targets:
        result = analyze_stock(name, code)
        if result and is_severe_negative(result["penalty"], result["reasons"]):
            severe_stocks.append(result)
            log(f"🚨 命中重大利空: {name}({code}) penalty={result['penalty']}")

    log(f"扫描完成：共 {len(scan_targets)} 只，触发重大利空 {len(severe_stocks)} 只")

    # 5. 仅当有重大利空时推送
    card = build_severe_negative_card(date_str, severe_stocks, len(scan_targets))
    if card is None:
        log("无重大利空，不推送飞书")
        print(json.dumps({
            "severe_count": 0,
            "scanned_total": len(scan_targets),
            "feishu": "skipped"
        }, ensure_ascii=False, indent=2))
        sys.exit(0)

    token = get_tenant_token_with_retry()
    result = send_card_with_retry(token, FEISHU_GROUP_ID, card)
    code = result.get('code')
    msg = result.get('msg', '')
    if code == 0:
        log(f"飞书推送成功: msg={msg}")
    else:
        log_error(f"飞书推送失败: code={code} msg={msg}")

    print(json.dumps({
        "severe_count": len(severe_stocks),
        "scanned_total": len(scan_targets),
        "feishu": result
    }, ensure_ascii=False, indent=2))