# -*- coding: utf-8 -*-
"""
daily_kronos_advisor.py

早盘 / 尾盘双时点 Kronos 筛选器:
  - 09:00 早盘:从 morning 推荐 + 当前持仓 → Kronos 评分 → D 策略 → 飞书推送
  - 14:35 尾盘:从 evening 推荐 + 当前持仓 → 同上

数据源:
  - /home/jarvis/.openclaw/workspace/skills/Chinese_Stock/hot-spot-strategy/recommendations/
  - /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/recommendations/
  - /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json

飞书推送:复制 simple_feishu.py 模式(直接发卡片)
模型:您本地 v3 ranking loss 微调产物
策略:D = 剔除 Kronos 最看跌 min(3, N-2) 只 (8 月 OOS p=0.015 显著)

用法:
    python scripts/daily_kronos_advisor.py --phase morning
    python scripts/daily_kronos_advisor.py --phase evening
    # 加 --dry-run 仅打印,不发飞书
"""
import argparse
import json
import os
import sys
import glob
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos")
sys.path.insert(0, "/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/scripts")

import numpy as np
import pandas as pd
import torch
import requests

from model import Kronos, KronosTokenizer, KronosPredictor
from evaluate_kronos_ic import apply_price_limit, load_daily_bars_csv


# ---------------------------------------------------------------------------
# 飞书推送(直接内联,不依赖 simple_feishu.py 路径)
# ---------------------------------------------------------------------------
FEISHU_APP_ID = "cli_a93eb458ceb81cc0"
FEISHU_APP_SECRET = "1i18JUKuFhQEejUOkNividRbMdJBMpV8"
FEISHU_GROUP_ID = "oc_0ac1e4e8d09f939d887f4992bba2886b"
LOG_FILE = Path("/home/jarvis/.openclaw/logs/stock/kronos_advisor_feishu.log")


def feishu_log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_tenant_token():
    try:
        r = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("tenant_access_token", "")
    except Exception as e:
        feishu_log(f"get_token failed: {e}")
    return None


def send_card(card):
    token = get_tenant_token()
    if not token:
        return {"code": -1, "msg": "no token"}
    try:
        r = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": FEISHU_GROUP_ID,
                "msg_type": "interactive",
                "content": json.dumps(card),
            },
            timeout=10,
        )
        return r.json()
    except Exception as e:
        return {"code": -1, "msg": str(e)}


# ---------------------------------------------------------------------------
# 数据源
# ---------------------------------------------------------------------------
HOTSPOT_REC_DIR = Path("/home/jarvis/.openclaw/workspace/skills/Chinese_Stock/hot-spot-strategy/recommendations")
BACKEND_REC_DIR = Path("/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/recommendations")
HOLDINGS_PATH = Path("/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json")

CSV_DIR = "/tmp/kilo/kronos_pool_csv"


def latest_rec_files_for_phase(phase, max_age_days=3):
    """
    phase = 'morning' 或 'evening'
    收集最近 max_age_days 天内的推荐文件(从今天往前找)。
    如果今天/昨天没生成,自动回退到最近一个有数据的日期。
    """
    from datetime import timedelta
    session_token = "morning" if phase == "morning" else "evening"
    candidates = []
    today = datetime.now().date()
    for d in range(0, max_age_days):
        target_date = today - timedelta(days=d)
        for rec_dir in [HOTSPOT_REC_DIR, BACKEND_REC_DIR]:
            if not rec_dir.exists():
                continue
            pat = f"{target_date.strftime('%Y%m%d')}_{session_token}_buy_recommendation.json"
            fp = rec_dir / pat
            if fp.exists():
                candidates.append(fp)
    return candidates


def load_recommendations(phase):
    """phase: 'morning' | 'evening' | 'both'"""
    files = []
    if phase in ("morning", "both"):
        files.extend(latest_rec_files_for_phase("morning"))
    if phase in ("evening", "both"):
        files.extend(latest_rec_files_for_phase("evening"))
    recs = []
    for fp in files:
        try:
            with open(fp) as f:
                d = json.load(f)
            for r in d.get("recommendations", []):
                recs.append({
                    "date": d["date"],
                    "session": d["session"],
                    "source_dir": str(fp.parent),
                    "code": str(r["code"]).zfill(6),
                    "name": r["name"],
                    "weight": r.get("weight", 0),
                    "combined_score": r.get("combined_score", 0),
                    "position_pct": r.get("position_pct", 0),
                    "strategy_name": r.get("strategy_name", ""),
                })
        except Exception as e:
            feishu_log(f"load rec failed {fp}: {e}")

    # 去重 + 只保留今天日期的推荐
    today_str = datetime.now().strftime("%Y%m%d")
    seen = {}
    for r in recs:
        # 只保留今天日期的推荐(排除昨天)
        if r["date"] != today_str:
            continue
        key = (r["code"], r["date"], r["session"])
        if key not in seen or r["combined_score"] > seen[key]["combined_score"]:
            seen[key] = r
    return list(seen.values())


def load_holdings():
    if not HOLDINGS_PATH.exists():
        return []
    with open(HOLDINGS_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Kronos 打分
# ---------------------------------------------------------------------------
_PYTDX_SERVERS = [
    ('218.75.126.9', 7709),
    ('60.12.136.250', 7709),
]


def kronos_score_one(predictor, sym, csv_dir, lookback=200, pred_len=5, sample_count=2):
    fp = os.path.join(csv_dir, f"{sym}.csv")
    if os.path.exists(fp):
        df = load_daily_bars_csv(sym, csv_dir)
    else:
        try:
            from pytdx.hq import TdxHq_API
            api = TdxHq_API()
            df = None
            for host, port in _PYTDX_SERVERS:
                try:
                    if api.connect(host, port):
                        mkt = 1 if sym.startswith(("5", "6", "9")) or sym.startswith("1") else 0
                        d = api.get_security_bars(9, mkt, sym, 0, 800)
                        if d:
                            df = api.to_df(d).rename(columns={"datetime": "date", "vol": "volume"})
                            df["date"] = pd.to_datetime(df["date"])
                            df["amount"] = df["close"] * df["volume"]
                            df = df[["date", "open", "close", "high", "low", "volume", "amount"]]
                            break
                except Exception:
                    continue
        except Exception:
            df = None
    if df is None or len(df) < lookback:
        return None
    x_df = df.iloc[-lookback:]
    x_ts = pd.DatetimeIndex(x_df["date"])
    last_date = x_df["date"].iloc[-1]
    last_close = float(x_df["close"].iloc[-1])
    y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=pred_len)
    try:
        pred_df = predictor.predict(
            df=x_df[["open", "high", "low", "close", "volume", "amount"]],
            x_timestamp=x_ts,
            y_timestamp=pd.Series(y_ts),
            pred_len=pred_len, T=1.0, top_p=0.9,
            sample_count=sample_count, verbose=False,
        )
        path = apply_price_limit(pred_df["close"].values.astype(float), last_close, 0.10)
        pred_ret = float(path[-1] / last_close - 1)
        return pred_ret, last_close, last_date
    except Exception:
        return None


# ---------------------------------------------------------------------------
# D 策略(剔除 Kronos 最看跌 min(3, N-2) 只)
# ---------------------------------------------------------------------------
def apply_keep_top_3(candidates_with_kronos):
    """
    您指定的策略:每天只保留 Kronos 看多的前 3 只。

    逻辑:
      - 按 Kronos 预测降序(=看多在前)
      - 取前 3 只
      - 即使 N < 3,也全部保留(没法再筛)

    返回:
      keep:  保留的票列表(最多 3 只,Kronos 最看多)
      drop:  剔除的票列表(剩余全部)
    """
    if not candidates_with_kronos:
        return [], []
    # 按 Kronos 降序(看多在前)
    ordered = sorted(candidates_with_kronos, key=lambda x: x["kronos_pred"], reverse=True)
    keep = ordered[:3]
    drop = ordered[3:]
    return keep, drop


def apply_d_filter(candidates_with_kronos):
    """
    D 策略:剔除 Kronos 最看跌 min(3, N-2) 只,保留其余。
    8 月 OOS p=0.015 显著(全部), MORNING 适用。

    返回:
      keep:  保留的票列表(按 Kronos 升序排列)
      drop:  剔除的票列表 (按 Kronos 看跌排序)
    """
    if not candidates_with_kronos:
        return [], []
    n = len(candidates_with_kronos)
    ordered = sorted(candidates_with_kronos, key=lambda x: x["kronos_pred"])
    drop_k = min(3, max(1, n - 2))
    drop = ordered[:drop_k]
    keep = ordered[drop_k:]
    return keep, drop


def filter_recommendations(phase, recs_with_score):
    """
    按阶段选择不同过滤策略(8 月 OOS 回测结果驱动):
      - MORNING 用 D策略 (剔除看跌): MORNING 胜率从 43.9% 提到 51.2%
      - EVENING 用 keep_top_3 (只留看多): EVENING 累计 +199%
    """
    if not recs_with_score:
        return [], [], ""
    if phase == "morning":
        kept, dropped = apply_d_filter(recs_with_score)
        strategy_name = "D策略(剔除Kronos看跌,保留剩余)"
    else:
        kept, dropped = apply_keep_top_3(recs_with_score)
        strategy_name = "keep_top_3(保留Kronos看多前3只)"
    return kept, dropped, strategy_name


# ---------------------------------------------------------------------------
# Kronos 数字格式化(让人一眼看出信号强度)
# ---------------------------------------------------------------------------
def _format_kronos(pred_ret: float) -> str:
    """
    把 Kronos 预测值格式化成"信号强度"标签。
    返回: '🔴🔴🔴 Kronos -18.5% (强烈看跌)'
    """
    if pred_ret is None:
        return "Kronos ?"
    pct = pred_ret * 100
    if pct <= -10:
        return f"🔴🔴🔴 Kronos {pct:+.1f}% (强烈看跌)"
    elif pct <= -5:
        return f"🔴🔴 Kronos {pct:+.1f}% (看跌)"
    elif pct <= -1:
        return f"🔴 Kronos {pct:+.1f}% (弱看跌)"
    elif pct < 1:
        return f"⚪ Kronos {pct:+.1f}% (中性)"
    elif pct < 5:
        return f"🟢 Kronos {pct:+.1f}% (弱看多)"
    elif pct < 10:
        return f"🟢🟢 Kronos {pct:+.1f}% (看多)"
    else:
        return f"🟢🟢🟢 Kronos {pct:+.1f}% (强烈看多)"


# ---------------------------------------------------------------------------
# 飞书卡片构建
# ---------------------------------------------------------------------------
def build_card(phase, recommendations, holdings, advice_meta):
    """
    advice_meta: {
        "kept": [...],
        "dropped": [...],
        "holdings": {code: {kronos, action}},
        "strategy_name": str,
    }
    """
    title_emoji = "🌅" if phase == "morning" else "🌆"
    title = f"{title_emoji} {phase} Kronos 报告"

    kept = advice_meta.get("kept", [])
    dropped = advice_meta.get("dropped", [])
    h_meta = advice_meta.get("holdings", {})
    strategy_name = advice_meta.get("strategy_name", "")

    lines = []
    lines.append(f"**{title}** · {datetime.now().strftime('%m-%d %H:%M')}")
    lines.append("")
    lines.append(f"📌 策略: **{strategy_name}**")
    lines.append("📌 **怎么看这些数字?**")
    lines.append("• `推分` = 您推荐系统给的综合分(0-100),越高越看好")
    lines.append("• `Kronos %` = Kronos 模型给的**相对排序**(不是涨跌幅!)")
    lines.append("   负数 = 看跌,正数 = 看多;绝对值越大信号越强")
    lines.append("• 💡 Kronos 看跌越深,越应避开(8月OOS p=0.015)")
    lines.append("")

    # 推荐 - 标注 ⭐ 持仓重叠
    if kept:
        lines.append(f"**📥 推荐保留 {len(kept)} 只**")
        for r in kept[:10]:
            marker = " ⭐持仓" if r.get("in_holdings") else ""
            k_str = _format_kronos(r["kronos_pred"])
            lines.append(f"`{r['code']}` {r['name']} · {k_str} · 推分{r['combined_score']:.0f}{marker}")
        if len(kept) > 10:
            lines.append(f"...还有 {len(kept)-10} 只")

    if dropped:
        lines.append("")
        lines.append(f"**🚫 推荐剔除 {len(dropped)} 只**")
        for r in dropped[:10]:
            marker = " ⭐持仓" if r.get("in_holdings") else ""
            k_str = _format_kronos(r["kronos_pred"])
            lines.append(f"`{r['code']}` ~~{r['name']}~~ · {k_str}{marker}")

    if not kept and not dropped:
        lines.append("")
        lines.append("_今日无推荐数据_")

    # 持仓 - 标注 ⭐ 今日推荐
    if h_meta:
        lines.append("")
        lines.append("**💼 持仓 Kronos 建议**")
        sorted_h = sorted(h_meta.items(), key=lambda x: x[1]["kronos_pred"])
        for code, info in sorted_h:
            icon = info["action"].split()[0]
            short_action = info["action"].replace(icon, "").strip()
            marker = " ⭐今日推荐" if info.get("in_today_rec") else ""
            k_str = _format_kronos(info["kronos_pred"])
            lines.append(f"`{code}` {info['name']} · 浮盈{info['pnl_pct']:+.1f}% · {k_str} · {icon} {short_action}{marker}")

    # 底部
    lines.append("")
    if phase == "morning":
        lines.append("_💡 MORNING 用 D 策略剔除看跌;8月OOS MORNING 胜率 43%→51%_")
    else:
        lines.append("_💡 EVENING 用 keep_top_3;8月OOS EVENING 累计 +199%_")

    elements = [{"tag": "markdown", "content": "\n".join(lines)}]

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue",
        },
        "elements": elements,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["morning", "evening", "both"], default="both")
    p.add_argument("--model",
                   default="/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/"
                           "finetune_csv/finetuned/pool_300_daily_uniform_rank/basemodel/best_model")
    p.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base")
    p.add_argument("--device", default="cuda")
    p.add_argument("--lookback", type=int, default=200)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--sample-count", type=int, default=2)
    p.add_argument("--threshold-bear", type=float, default=-0.03)
    p.add_argument("--threshold-bull", type=float, default=0.03)
    p.add_argument("--dry-run", action="store_true", help="仅打印不发飞书")
    return p.parse_args()


def main():
    args = parse_args()

    print(f"[load] Kronos model: {args.model}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(model, tokenizer, device=args.device, max_context=512)

    # 决定 phases
    phases = ["morning", "evening"] if args.phase == "both" else [args.phase]

    for phase in phases:
        run_phase(phase, predictor, args)


def run_phase(phase, predictor, args):
    print(f"\n========== {phase.upper()} PHASE ==========")

    recs = load_recommendations(phase)
    holdings = load_holdings()
    print(f"  recs: {len(recs)}, holdings: {len(holdings)}")

    # 合并打分
    all_codes = sorted(set([r["code"] for r in recs] + [h["code"] for h in holdings]))
    print(f"  unique codes to score: {len(all_codes)}")

    scores = {}
    for code in all_codes:
        res = kronos_score_one(predictor, code, CSV_DIR,
                                args.lookback, args.pred_len,
                                args.sample_count)
        scores[code] = {"pred_ret": res[0] if res else None,
                          "last_close": res[1] if res else None}

    # 标记哪些是"持仓 + 今日推荐重叠"
    holding_codes = {h["code"] for h in holdings}
    rec_codes_set = {r["code"] for r in recs}

    # 推荐过滤
    recs_with_score = []
    for r in recs:
        if scores[r["code"]]["pred_ret"] is not None:
            r["kronos_pred"] = scores[r["code"]]["pred_ret"]
            r["in_holdings"] = r["code"] in holding_codes  # 标记
            recs_with_score.append(r)

    kept, dropped, strategy_name = filter_recommendations(phase, recs_with_score)
    print(f"\n  === {strategy_name} ===")
    print(f"  保留: {[r['name'] for r in kept]}")
    print(f"  剔除: {[r['name'] for r in dropped]}")

    # 持仓 Kronos 评分 (基于 D 策略的同类逻辑)
    holdings_meta = {}
    for h in holdings:
        code = h["code"]
        if scores.get(code, {}).get("pred_ret") is None:
            continue
        kronos = scores[code]["pred_ret"]
        pnl_pct = (h["current_price"] / h["cost"] - 1) * 100
        in_today_rec = code in rec_codes_set

        # 持仓建议核心逻辑:
        # 1. Kronos 看跌 (< -3%) → 优先减仓/换股
        #    - 浮盈 > 5%: 止盈机会 → 立即减仓
        #    - 浮亏 > 5%: 止损机会 → 评估止损
        #    - 否则: 考虑减仓
        # 2. Kronos 看多 (> +3%) → 继续持有
        # 3. 中性 → 观察
        # 4. 同时,该票若在今日推荐中,加标记
        if kronos < args.threshold_bear:
            if pnl_pct > 5:
                action = "🟢 减仓止盈"
                reason = "Kronos看跌+浮盈>5%"
            elif pnl_pct < -5:
                action = "🔴 评估止损"
                reason = "Kronos看跌+浮亏>5%"
            else:
                action = "⚠️ 考虑减仓"
                reason = "Kronos看跌"
        elif kronos > args.threshold_bull:
            if pnl_pct < -3:
                action = "🟢 持有待反弹"
                reason = "Kronos看多+浮亏<3%"
            else:
                action = "✅ 继续持有"
                reason = "Kronos看多"
        else:
            if pnl_pct < -5:
                action = "⚪ 评估减仓"
                reason = "Kronos中性+浮亏>5%"
            else:
                action = "⚪ 持有观察"
                reason = "Kronos中性"

        holdings_meta[code] = {
            "name": h["name"],
            "pnl_pct": pnl_pct,
            "kronos_pred": kronos,
            "action": action,
            "reason": reason,
            "in_today_rec": in_today_rec,  # NEW: 标记是否今日推荐
        }

    advice_meta = {
        "kept": kept,
        "dropped": dropped,
        "holdings": holdings_meta,
        "strategy_name": strategy_name,
    }

    # 控制台报告
    print(f"\n  === 推荐过滤结果 ===")
    for r in kept:
        marker = " ⭐持仓" if r.get("in_holdings") else ""
        print(f"  ↑ 保留 {r['name']:10}({r['code']}) Kronos={r['kronos_pred']*100:+.2f}% 推分={r['combined_score']:.0f}{marker}")
    for r in dropped:
        marker = " ⭐持仓" if r.get("in_holdings") else ""
        print(f"  ↓ 剔除 {r['name']:10}({r['code']}) Kronos={r['kronos_pred']*100:+.2f}% 推分={r['combined_score']:.0f}{marker}")

    print(f"\n  === 持仓 Kronos 评分 ===")
    for code, info in holdings_meta.items():
        marker = " ⭐今日推荐" if info["in_today_rec"] else ""
        print(f"  {info['name']:10}({code}) 浮盈={info['pnl_pct']:+.2f}% Kronos={info['kronos_pred']*100:+.2f}% → {info['action']} ({info['reason']}){marker}")

    # 推送飞书
    card = build_card(phase, recs, holdings, advice_meta)
    if args.dry_run:
        print("\n[DRY-RUN] 不推送飞书")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    result = send_card(card)
    ok = result.get("code") == 0
    if ok:
        feishu_log(f"✅ [{phase}] 推送成功: 保留{len(kept)} 剔除{len(dropped)} 持仓{len(holdings_meta)}")
        print(f"\n✅ 飞书推送成功")
    else:
        feishu_log(f"❌ [{phase}] 推送失败: {result}")
        print(f"\n❌ 飞书推送失败: {result}")


if __name__ == "__main__":
    main()