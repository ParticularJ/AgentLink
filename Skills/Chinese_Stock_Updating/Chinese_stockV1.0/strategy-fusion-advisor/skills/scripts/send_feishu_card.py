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

def build_card(date_str, session_label, recs, total_pos, success_count, no_result_count, err_count, filename,
               market_phase='UNKNOWN', phase_label='未知', position_cap=0.30,
               sector_phases=None, sector_filter=None):
    """构建飞书 interactive card"""
    template_map = {
        "早盘买（次日）": ("☀️", "orange"),
        "尾盘买": ("🌙", "blue"),
    }
    icon, color = template_map.get(session_label, ("📊", "grey"))

    sector_phases = sector_phases or {}
    sector_filter = sector_filter or {}

    # ── 板块按 phase 分组 ──
    PHASE_LABELS_CN = {
        'STRONG_UP':   '单边上行',
        'WAVE_UP':     '波段',
        'RANGE':       '震荡',
        'STRONG_DOWN': '下行',
        'UNKNOWN':     '未知',
    }
    PHASE_ICONS = {
        'STRONG_UP':   '✅',
        'WAVE_UP':     '🌊',
        'RANGE':       '↔️',
        'STRONG_DOWN': '⬇️',
        'UNKNOWN':     '❓',
    }
    sector_by_phase = {}
    for sec, phase in sector_phases.items():
        sector_by_phase.setdefault(phase, []).append(sec)
    for phase in sector_by_phase:
        sector_by_phase[phase].sort()

    reserve_n = len(sector_filter.get('reserve', []))
    block_n = len(sector_filter.get('block', []))
    unknown_n = len(sector_filter.get('unknown_sector', []))

    # ── 大盘 + 仓位 + 板块过滤 概览 ──
    pos_cap_pct = int(round(position_cap * 100))
    market_block = {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": (
                f"**📊 大盘状态**：`{phase_label}`（`{market_phase}`）\n"
                f"**💰 仓位上限**：`{pos_cap_pct}%`\n"
                f"**🚦 板块过滤**：预留 `{reserve_n}` 只 | 禁止 `{block_n}` 只 | 无板块 `{unknown_n}` 只"
            )
        }
    }

    # ── 板块状态分组展示（每组一行）──
    sector_lines = []
    # 按 STRONG_UP → WAVE_UP → RANGE → STRONG_DOWN → UNKNOWN 顺序
    phase_order = ['STRONG_UP', 'WAVE_UP', 'RANGE', 'STRONG_DOWN', 'UNKNOWN']
    for phase in phase_order:
        secs = sector_by_phase.get(phase, [])
        if not secs:
            continue
        icon_p = PHASE_ICONS[phase]
        label = PHASE_LABELS_CN[phase]
        # 板块名换行显示（每行最多 4 个，控制长度）
        sec_text = '、'.join(secs)
        sector_lines.append(f"{icon_p} **{label}（{len(secs)}）**：{sec_text}")

    sector_block = {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "**📋 板块状态**\n" + ('\n'.join(sector_lines) if sector_lines else '_无板块数据_')
        }
    }

    # ── 未推荐原因分析（板块过滤明细）──
    filter_reasons = []
    reserve_list = sector_filter.get('reserve', [])
    block_list = sector_filter.get('block', [])
    unknown_list = sector_filter.get('unknown_sector', [])

    # 按 phase 重新分组（板块 STRONG_DOWN 集中展示）
    def _group_by_phase(items):
        groups = {}
        for it in items:
            p = it.get('sector_phase', 'UNKNOWN')
            groups.setdefault(p, []).append(it)
        return groups

    order = ['STRONG_DOWN', 'UNKNOWN', 'WAVE_UP', 'RANGE', 'STRONG_UP']

    def _format_phase_items(items, verb):
        out = []
        groups = _group_by_phase(items)
        for phase in order:
            group_items = groups.get(phase, [])
            if not group_items:
                continue
            icon_p = PHASE_ICONS.get(phase, '❓')
            label = PHASE_LABELS_CN.get(phase, phase)
            shown = group_items[:5]
            line_items = [
                f"`{it.get('stock_code', '?')}` {it.get('stock_name', '?')}({it.get('sector', '?')})"
                for it in shown
            ]
            extra = len(group_items) - len(shown)
            text = '、'.join(line_items)
            if extra > 0:
                text += f" 等 {len(group_items)} 只"
            out.append(f"{icon_p} **{label}板块{verb}（{len(group_items)} 只）**：{text}")
        return out

    if block_list:
        filter_reasons.extend(_format_phase_items(block_list, '禁止买入'))

    if reserve_list:
        filter_reasons.extend(_format_phase_items(reserve_list, '预留策略'))

    # 无推荐原因汇总
    summary_lines = []
    if block_list:
        by_phase = _group_by_phase(block_list)
        n_down = len(by_phase.get('STRONG_DOWN', []))
        n_unk = len(by_phase.get('UNKNOWN', []))
        n_other = len(block_list) - n_down - n_unk
        parts = []
        if n_down:
            parts.append(f"{n_down} 只因板块**下行**禁止")
        if n_unk:
            parts.append(f"{n_unk} 只因板块**未知**禁止")
        if n_other:
            parts.append(f"{n_other} 只板块状态其他原因禁止")
        summary_lines.append('🚫 **禁止原因**：' + '，'.join(parts))
    if reserve_list:
        summary_lines.append(f"🚧 **预留原因**：{len(reserve_list)} 只因板块**波段/震荡**策略设计中暂不买入")
    if unknown_list:
        summary_lines.append(f"❓ **无板块**：{len(unknown_list)} 只股票无板块信息，保守禁止")
    if not recs and (block_list or reserve_list or unknown_list):
        summary_lines.append('\n**💡 建议**：当前可买板块较少，建议控制仓位等待')

    filter_reason_block = {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": (
                "**🚫 未推荐原因分析**\n\n" +
                ('\n'.join(summary_lines) if summary_lines else '_无过滤_') +
                ('\n\n**明细**：\n' + '\n'.join(filter_reasons) if filter_reasons else '')
            )
        }
    }

    # ── Top 5 推荐 ──
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

        # 板块 + phase（取第一个板块做展示）
        sector_text = ''
        sectors_detail = rec.get('sectors_detail') or []
        sectors = rec.get('sectors', [])
        if sectors_detail:
            parts = [f"{sd['name']}({PHASE_LABELS_CN.get(sd.get('phase','UNKNOWN'), '未知')})"
                     for sd in sectors_detail[:2]]
            sector_text = f"   板块：`{ '、'.join(parts) }`\n"
        elif sectors:
            sector_text = f"   板块：`{ '、'.join(sectors[:2]) }`\n"

        stock_blocks.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**{emoji} {i+1}. {name}({code})**\n"
                    f"{sector_text}"
                    f"   综合评分：`{score}` | 最高单策略：`{best}`\n"
                    f"   确认策略：`{strat_str}`\n"
                    f"   买入理由：{reason}\n"
                    f"   **买入仓位: {pos}%**\n"
                    f"   **新闻损失: {penalty}分**\n"
                    f"   新闻原因: {penalty_reason if penalty < 0 else '无'}"
                )
            }
        })

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**📊 策略运行概览**\n\n• 共计策略: {success_count + no_result_count + err_count}个\n• 有结果：{success_count}个 -无结果：{no_result_count}个 -运行错误：{err_count}个  \n• 融合推荐：{len(recs)} 只  \n• 总仓位建议：💰 **{total_pos}%**\n• 生成时间：{date_str}"}
        },
        market_block,
        {"tag": "hr"},
        sector_block,
        {"tag": "hr"},
        filter_reason_block,
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": "### 🏆 融合推荐 TOP 5"}},
    ]
    elements.extend(stock_blocks)
    elements.append({"tag": "hr"})
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**策略来源**：早盘融合策略组" if "早盘" in session_label else "**策略来源**：尾盘融合策略组"}})

    # 副标题里显示大盘 phase + 仓位
    subtitle = f"{phase_label} · 仓位上限 {pos_cap_pct}% · {session_label}"

    card = {
        "header": {
            "title": {"tag": "plain_text", "content": f"{icon} 融合推荐 | {date_str} {session_label}"},
            "subtitle": {"tag": "plain_text", "content": subtitle},
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

    # ── 大盘 + 板块信息（来自 fusion_runner 写入的 JSON）──
    market_phase = data.get('market_phase', 'UNKNOWN')
    phase_label = data.get('market_phase_label', '未知')
    position_cap = data.get('position_cap', 0.30)
    sector_filter = data.get('sector_filter', {}) or {}
    sector_phases = sector_filter.get('sector_phases', {}) or {}

    card = build_card(date_str, session_display, recs, total_pos,
                      success_count, no_result_count, err_count, fname,
                      market_phase=market_phase, phase_label=phase_label,
                      position_cap=position_cap,
                      sector_phases=sector_phases, sector_filter=sector_filter)
    token = get_tenant_token_with_retry()
    result = send_card_with_retry(token, FEISHU_GROUP_ID, card)
    code = result.get('code')
    msg = result.get('msg', '')
    if code == 0:
        log(f"飞书推送成功: msg={msg}")
    else:
        log_error(f"飞书推送失败: code={code} msg={msg}")
    print(json.dumps(result, ensure_ascii=False))
