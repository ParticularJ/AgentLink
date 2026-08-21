# -*- coding: utf-8 -*-
"""
daily_advisor.py
每日顾问 — 用 Kronos 给您的推荐和持仓打分,并给出具体建议。

用法:
    python scripts/daily_advisor.py --holdings-path /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json

逻辑:
  1. 加载您当前真实持仓
  2. 加载您最近 5 个交易日的所有推荐
  3. 用本地微调 Kronos 模型对每只票打分(预测 5 日收益)
  4. 综合考虑:
     - Kronos 预测
     - 推荐系统 combined_score
     - 当前持仓盈亏
     - Kronos 是否"反复看跌"(持续信号)
  5. 输出每只票的 "买入 / 持有 / 减仓 / 卖出" 建议
"""
import argparse, json, os, sys
sys.path.insert(0, "/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos")
sys.path.insert(0, "/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/scripts")

import numpy as np
import pandas as pd
import torch
from datetime import datetime, timedelta

from model import Kronos, KronosTokenizer, KronosPredictor
from evaluate_kronos_ic import apply_price_limit, load_daily_bars_csv


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--holdings-path",
                   default="/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/"
                           "my_holdings/holdings.json")
    p.add_argument("--rec-dir",
                   default="/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/"
                           "recommendations")
    p.add_argument("--csv-dir", default="/tmp/kilo/kronos_pool_csv")
    p.add_argument("--model",
                   default="/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/"
                           "finetune_csv/finetuned/pool_300_daily_uniform_rank/basemodel/best_model")
    p.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base")
    p.add_argument("--lookback", type=int, default=200)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--sample-count", type=int, default=2)
    p.add_argument("--device", default="cuda")
    p.add_argument("--threshold-bear", type=float, default=-0.03,
                   help="Kronos 预测 < 此阈值 → 看跌")
    p.add_argument("--threshold-bull", type=float, default=0.03,
                   help="Kronos 预测 > 此阈值 → 看多")
    return p.parse_args()


def kronos_score_one(predictor, sym, csv_dir, lookback, pred_len, sample_count, device):
    """对单只票打分,返回 (pred_ret, last_close, last_date)"""
    lookback = int(lookback)
    pred_len = int(pred_len)
    fp = os.path.join(csv_dir, f"{sym}.csv")
    if not os.path.exists(fp):
        # fallback: pytdx
        try:
            from pytdx.hq import TdxHq_API
            api = TdxHq_API()
            with api.connect('218.75.126.9', 7709):
                mkt = 1 if sym.startswith(("5", "6", "9")) or sym.startswith("1") else 0
                d = api.get_security_bars(9, mkt, sym, 0, 800)
                if not d:
                    return None
                df = api.to_df(d).rename(columns={'datetime': 'date', 'vol': 'volume'})
                df['date'] = pd.to_datetime(df['date'])
                df['amount'] = df['close'] * df['volume']
                df = df[['date', 'open', 'close', 'high', 'low', 'volume', 'amount']]
        except Exception:
            return None
    else:
        df = load_daily_bars_csv(sym, csv_dir)

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


def load_recent_recs(rec_dir, days=5):
    """加载最近 N 天所有推荐"""
    import glob
    files = sorted(glob.glob(f'{rec_dir}/2026*.json'))[-days * 2:]
    recs = []
    for f in files:
        with open(f) as fp:
            d = json.load(fp)
        for r in d.get("recommendations", []):
            recs.append({
                'date': d['date'],
                'session': d['session'],
                'code': str(r['code']).zfill(6),
                'name': r['name'],
                'weight': r.get('weight', 0),
                'combined_score': r.get('combined_score', 0),
            })
    return recs


def load_holdings(path):
    with open(path) as f:
        return json.load(f)


def main():
    args = parse_args()

    print(f"[load] Kronos from {args.model}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(model, tokenizer, device=args.device, max_context=512)

    print(f"\n[load] 最近 5 天推荐")
    recs = load_recent_recs(args.rec_dir, days=5)
    print(f"  共 {len(recs)} 条")

    print(f"[load] 当前持仓")
    holdings = load_holdings(args.holdings_path)
    print(f"  共 {len(holdings)} 只\n")

    # 收集所有需要打分的票
    rec_codes = sorted(set(r["code"] for r in recs))
    hold_codes = sorted(set(h["code"] for h in holdings))
    all_codes = sorted(set(rec_codes + hold_codes))

    # 打分
    print(f"[score] {len(all_codes)} 只票 Kronos 打分中...")
    scores = {}
    for code in all_codes:
        res = kronos_score_one(predictor, code, args.csv_dir,
                                args.lookback, args.pred_len,
                                args.sample_count, args.device)
        if res is None:
            scores[code] = {"pred_ret": None, "last_close": None}
        else:
            pred_ret, last_close, last_date = res
            scores[code] = {
                "pred_ret": pred_ret,
                "last_close": last_close,
                "last_date": last_date,
            }

    # 输出建议
    print("\n" + "=" * 100)
    print(f"📊 Kronos 每日顾问 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 100)

    print("\n## 🎯 推荐 vs Kronos 评分")
    rec_grouped = {}
    for r in recs:
        key = r["code"]
        if key not in rec_grouped:
            rec_grouped[key] = {"name": r["name"], "recs": []}
        rec_grouped[key]["recs"].append(
            f"{r['date'][-5:]}/{r['session'][:1]} ({r['combined_score']:.0f})"
        )

    print(f"{'代码':<8}{'名称':<12}{'推荐次数':<18}{'Kronos预测':<14}{'方向':<8}{'建议'}")
    print("-" * 100)
    for code in sorted(rec_grouped):
        info = rec_grouped[code]
        sc = scores.get(code, {})
        pr = sc.get("pred_ret")
        if pr is None:
            pr_s = "无数据"
            direction = "—"
            rec = "❓ 缺数据"
        elif pr < args.threshold_bear:
            pr_s = f"{pr*100:+.2f}%"
            direction = "↓ 看跌"
            rec = "⚠️ 慎重"
        elif pr > args.threshold_bull:
            pr_s = f"{pr*100:+.2f}%"
            direction = "↑ 看多"
            rec = "✅ 可买"
        else:
            pr_s = f"{pr*100:+.2f}%"
            direction = "→ 中性"
            rec = "⚪ 中性"
        print(f"{code:<8}{info['name']:<12}{len(info['recs']):<3}次         "
              f"{pr_s:<14}{direction:<8}{rec}")

    print("\n## 💼 当前持仓 vs Kronos")
    print(f"{'代码':<8}{'名称':<14}{'入场日':<10}{'成本':<9}{'现价':<9}{'浮盈%':<10}"
          f"{'Kronos':<12}{'建议'}")
    print("-" * 100)
    for h in holdings:
        code = h["code"]
        cost = h["cost"]
        cur = h["current_price"]
        pnl_pct = (cur / cost - 1) * 100
        pr = scores.get(code, {}).get("pred_ret")
        if pr is None:
            kronos_s, direction, rec = "—", "—", "❓"
        elif pr < args.threshold_bear:
            kronos_s = f"{pr*100:+.2f}%"
            direction = "↓ 看跌"
            if pnl_pct > 5:
                rec = "🟢 减仓可止盈"
            elif pnl_pct < -5:
                rec = "🔴 评估止损"
            else:
                rec = "⚠️ 考虑减仓"
        elif pr > args.threshold_bull:
            kronos_s = f"{pr*100:+.2f}%"
            direction = "↑ 看多"
            if pnl_pct < -3:
                rec = "🟢 持有等待"
            else:
                rec = "✅ 继续持有"
        else:
            kronos_s = f"{pr*100:+.2f}%"
            direction = "→ 中性"
            if pnl_pct < -5:
                rec = "⚪ 评估减仓"
            else:
                rec = "⚪ 持有观察"
        print(f"{code:<8}{h['name']:<14}{h['entry_date'][-5:]:<10}{cost:<9.3f}"
              f"{cur:<9.3f}{pnl_pct:>+8.2f}%  {kronos_s:<12}{rec}")

    print("\n" + "=" * 100)
    print("📋 综合建议(融合 Kronos + 您的推荐系统)")
    print("=" * 100)

    # 综合推荐
    buy_recs = []
    warn_recs = []
    for code, info in rec_grouped.items():
        pr = scores.get(code, {}).get("pred_ret")
        if pr is None:
            continue
        # 综合:推荐分数 + Kronos
        avg_score = np.mean([float(r.split("(")[-1].rstrip(")"))
                            for r in info["recs"]
                            if "(" in r])
        kronos_score = (1 - abs(pr)) * 100  # |pred| 越小越好
        rec_score = avg_score
        combined = (rec_score + kronos_score) / 2
        if pr < args.threshold_bear and rec_score > 70:
            warn_recs.append((code, info["name"], pr, avg_score,
                              "推分高但 Kronos 持续看跌,建议谨慎"))
        elif pr > args.threshold_bull and rec_score > 70:
            buy_recs.append((code, info["name"], pr, avg_score,
                            "推分高 + Kronos 看多,可以买"))
        elif pr > args.threshold_bull and rec_score < 70:
            warn_recs.append((code, info["name"], pr, avg_score,
                              "Kronos 看多但推分一般"))
        elif pr < args.threshold_bear and rec_score < 70:
            warn_recs.append((code, info["name"], pr, avg_score,
                              "推分低 + Kronos 看跌,避免"))

    print("\n✅ **建议买入**(推分高 + Kronos 看多):")
    if buy_recs:
        for code, name, pr, sc, reason in buy_recs:
            print(f"  {code} {name}: Kronos {pr*100:+.2f}%, 推分 {sc:.0f} → {reason}")
    else:
        print("  (无)")

    print("\n⚠️ **建议谨慎/避免**:")
    if warn_recs:
        for code, name, pr, sc, reason in warn_recs:
            print(f"  {code} {name}: Kronos {pr*100:+.2f}%, 推分 {sc:.0f} → {reason}")
    else:
        print("  (无)")


if __name__ == "__main__":
    main()