#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股池新闻扫描器
- 核心股（watchlist_core.yaml）：利好推送（penalty > 0）
- 自选股（holdings.json）：利空推送（penalty < 0）
- 去重：同一只股不重复推送
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


def build_combined_card(date_str, positive_stocks, negative_stocks, core_total, holdings_total):
    """构建利好+利空合并推送卡片"""
    elements = []

    # 汇总区
    summary = (
        f"**📊 股池新闻扫描结果**\n\n"
        f"• 核心股扫描：{core_total} 只｜利好 {len(positive_stocks)} 只\n"
        f"• 自选股扫描：{holdings_total} 只｜利空 {len(negative_stocks)} 只\n"
        f"• 扫描时间：{date_str}"
    )
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": summary}})

    # -------- 利好专区 --------
    if positive_stocks:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "### 🏆 核心股利好（penalty > 0）"}})
        emojis_pos = ["🔥", "✅", "📌", "📌", "📌", "📌", "📌", "📌", "📌", "📌"]
        for i, stk in enumerate(positive_stocks[:10]):
            reason_text = '; '.join(stk["reasons"]) if stk["reasons"] else "新闻情绪偏正面"
        
            emoji = emojis_pos[i] if i < len(emojis_pos) else "  "
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{emoji} {i+1}. {stk['name']}({stk['code']})**\n   利好分：+{stk['penalty']}\n   利好原因：{reason_text}"
                }
            })
    else:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "### 🏆 核心股利好\n暂无利好股票，继续观察。"}})

    # -------- 利空专区 --------
    if negative_stocks:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "### ⚠️ 自选股利空（penalty < 0）"}})
        emojis_neg = ["🚨", "🔻", "📉", "📉", "📉", "📉", "📉", "📉", "📉", "📉"]
        for i, stk in enumerate(negative_stocks[:10]):
            reason_text = "；".join(stk["reasons"]) if stk["reasons"] else "新闻情绪偏负面"
            emoji = emojis_neg[i] if i < len(emojis_neg) else "  "
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{emoji} {i+1}. {stk['name']}({stk['code']})**\n   利空分：{stk['penalty']}\n   利空原因：{reason_text}"
                }
            })
    else:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "### ⚠️ 自选股利空\n暂无利空股票，继续持有。"}})

    # 免责声明
    elements.append(
        {"tag": "note", "elements": [{"tag": "plain_text", "content": "⚠️ 仅供参考，不构成投资建议。股市有风险，投资需谨慎。"}]}
    )

    card = {
        "header": {
            "title": {"tag": "plain_text", "content": f"📰 股池新闻扫描 | {date_str}"},
            "subtitle": {"tag": "plain_text", "content": "利好核心股 · 利空自选股"},
            "template": "blue"
        },
        "elements": elements
    }
    return card


if __name__ == "__main__":
    import requests

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    log("=" * 50)
    log(f"股池新闻扫描开始 | {date_str}")

    # 1. 加载核心股池（利好分析）
    core_stocks = load_watchlist(WATCHLIST_PATH)
    log(f"加载核心股池完成，共 {len(core_stocks)} 只股票")

    # 2. 加载自选股（利空分析）
    holdings_stocks = load_holdings(HOLDINGS_PATH)
    log(f"加载自选股完成，共 {len(holdings_stocks)} 只股票")

    # 3. 构建去重后的合并分析列表
    #    同一只股若同时在两个池里，只分析一次；
    #    利好/利空根据所在池分别判定
    seen_codes = set()
    core_analysis = []   # [(name, code)] 只在core中且未重复的
    holdings_only = []   # [(name, code)] 只在holdings中且未重复的
    both = []            # 同时在两个池里的

    for name, code in core_stocks:
        if code not in seen_codes:
            seen_codes.add(code)
            core_analysis.append((name, code))

    for name, code in holdings_stocks:
        if code not in seen_codes:
            seen_codes.add(code)
            holdings_only.append((name, code))
        else:
            # 已在core中出现过，去重合并到both
            both.append((name, code))

    log(f"去重后：核心股 {len(core_analysis)} | 自选股 {len(holdings_only)} | 重叠 {len(both)}")

    # 4. 遍历核心股 → 利好（penalty > 0）
    positive_stocks = []
    all_results = []

    for name, code in core_analysis:
        result = analyze_stock(name, code)
        if result:
            all_results.append(result)
            if result["penalty"] > 0:
                positive_stocks.append(result)

    # 重叠股：如果在core中penalty>0算利好，在holdings中penalty<0算利空
    # 由于重叠股只分析一次，以core分析结果为准
    # holdings_only → 利空（penalty < 0）
    negative_stocks = []
    for name, code in holdings_only:
        result = analyze_stock(name, code)
        if result:
            all_results.append(result)
            if result["penalty"] < 0:
                negative_stocks.append(result)

    log(f"扫描完成: 核心股{len(core_analysis)}只 利好{len(positive_stocks)}只 | 自选股{len(holdings_only)}只 利空{len(negative_stocks)}只")

    # 5. 推送飞书
    card = build_combined_card(
        date_str,
        positive_stocks,
        negative_stocks,
        len(core_analysis),
        len(holdings_only)
    )

    token = get_tenant_token_with_retry()
    result = send_card_with_retry(token, FEISHU_GROUP_ID, card)
    code = result.get('code')
    msg = result.get('msg', '')
    if code == 0:
        log(f"飞书推送成功: msg={msg}")
    else:
        log_error(f"飞书推送失败: code={code} msg={msg}")

    print(json.dumps({
        "positive_count": len(positive_stocks),
        "negative_count": len(negative_stocks),
        "core_total": len(core_analysis),
        "holdings_total": len(holdings_only),
        "feishu": result
    }, ensure_ascii=False, indent=2))