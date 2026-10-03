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

# ── 统一路径与凭据：不再硬编码绝对路径 / 明文 Secret ──────────
_root = os.path.abspath(os.path.dirname(__file__))
while not os.path.exists(os.path.join(_root, "common", "paths.py")) and _root != os.path.dirname(_root):
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "common"))
import feishu
from paths import (  # noqa: E402
    WATCHLIST_CORE_FILE,
    HOLDINGS_FILE,
    LOG_DIR,
)

WATCHLIST_PATH = str(WATCHLIST_CORE_FILE)
HOLDINGS_PATH = str(HOLDINGS_FILE)
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


# ── 重大利空判定参数 ────────────────────────────────────────
# 阈值 -10 来自模块文档：「仅推送重大利空：penalty <= -10 且命中强利空关键词」。
# 关键词取自 test_news.py 系统提示词中「实质性利空 / 极端重大利空」列举的情形
#（大额减持、高折价大宗、业绩预亏或下修、监管立案/谴责/处罚）。
SEVERE_PENALTY_THRESHOLD = -10
SEVERE_KEYWORDS = (
    "大额减持", "减持", "折价", "大宗交易",
    "业绩预亏", "预亏", "业绩下修", "下修", "业绩暴雷", "暴雷",
    "立案", "调查", "公开谴责", "谴责", "行政处罚", "处罚", "监管函", "问询函",
    "退市风险", "退市", "商誉减值", "资产减值", "股份冻结", "资金占用",
)


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

    token = feishu.get_tenant_token_with_retry(logger=log)
    result = feishu.send_card_with_retry(token, card, logger=log)
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