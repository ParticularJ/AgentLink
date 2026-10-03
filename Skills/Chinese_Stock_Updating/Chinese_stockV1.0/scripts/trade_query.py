#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘中交易询问卡片（早盘 10:00 / 尾盘 15:00）。

原来这段逻辑以 python -c 内联脚本的形式塞在两个 .sh 里，
凭据与绝对路径都写死在 shell 中；现在收敛成一个可测试的 Python 脚本。

用法：
    python scripts/trade_query.py morning
    python scripts/trade_query.py evening
"""

import json
import os
import sys
from datetime import datetime


# ── 统一路径与凭据 ──────────────────────────────────────────
_root = os.path.abspath(os.path.dirname(__file__))
while not os.path.exists(os.path.join(_root, "common", "paths.py")) and _root != os.path.dirname(_root):
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "common"))
import feishu
from paths import HOLDINGS_FILE, CASH_FILE  # noqa: E402

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
MSG_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"

# 时段 → 卡片外观
SESSIONS = {
    "morning": {"title": "📊 盘中交易询问 | 10:00", "subtitle": "开盘时段", "template": "orange",
                "prompt": "**盘中交易询问**\n\n当前是否有交易需求？",
                "note": "⚠️ 交易时段，请谨慎操作"},
    "evening": {"title": "📊 盘中交易询问 | 15:00", "subtitle": "尾盘时段", "template": "purple",
                "prompt": "**盘中交易询问**\n\n临近收盘，当前是否有交易需求？",
                "note": "⚠️ 尾盘时段，请注意交易时间"},
}


def _load_json(path, default):
    """读 JSON；文件不存在或损坏时返回默认值，不中断推送。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[WARN] 文件不存在: {path}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"[WARN] JSON 解析失败: {path}: {e}", file=sys.stderr)
    return default


def build_card(session: str) -> dict:
    cfg = SESSIONS[session]
    holdings = _load_json(str(HOLDINGS_FILE), [])
    cash_info = _load_json(str(CASH_FILE), {})
    available_cash = cash_info.get("available_cash", 0) or 0

    if holdings:
        holdings_text = "\n".join(
            f"- {h.get('name', '')}({h.get('code', '')}): "
            f"持仓{h.get('shares', 0)}股，成本{h.get('cost', 0):.2f}"
            for h in holdings
        )
    else:
        holdings_text = "（暂无持仓）"

    return {
        "header": {
            "title": {"tag": "plain_text", "content": cfg["title"]},
            "subtitle": {"tag": "plain_text",
                         "content": f'{datetime.now().strftime("%Y-%m-%d %H:%M")} {cfg["subtitle"]}'},
            "template": cfg["template"],
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": cfg["prompt"]}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md",
                                    "content": f"**💰 可用资金：{available_cash:,.2f} 元**"}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md",
                                    "content": "**📋 当前持仓参考**\n" + holdings_text}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md",
                                    "content": "**💬 操作方式**\n如需买入/卖出，请直接回复指令，例如：\n"
                                               "- 买入 600105 100股 # 50.0\n"
                                               "- 卖出 600105 50股 # 55.0"}},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": cfg["note"]}]},
        ],
    }


def main(argv) -> int:
    session = (argv[1] if len(argv) > 1 else "morning").lower()
    if session not in SESSIONS:
        print(f"用法: {argv[0]} [morning|evening]", file=sys.stderr)
        return 2
    try:
        feishu.send_card(build_card(session))
        print(f"✅ 已发送盘中交易询问（{session}）")
        return 0
    except Exception as e:
        print(f"❌ 发送失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
