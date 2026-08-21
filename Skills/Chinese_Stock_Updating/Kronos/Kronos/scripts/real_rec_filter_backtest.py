# -*- coding: utf-8 -*-
"""
real_rec_filter_backtest.py

用您最近 2 周 (2026-08-03 → 2026-08-14) 的真实推荐做 Kronos 过滤器验证。

每天:
  - 取 evening + morning 推荐(去重) = N 只候选
  - 用 8/7 或更早的本地数据跑 Kronos 评分(每只)
  - 假设次日开盘(T+1)按推荐买入,持有 5 个交易日到 T+5 收盘卖出
  - 比较:
      A. no_filter (原 N 只等权)
      B. drop_bottom_1 (剔除 Kronos 最看跌 1 只)
      C. drop_bottom_2 (剔除 2 只,N>=3 时)
      D. drop_bottom_3 (剔除 3 只,N>=4 时)
      E. keep_top_K (只留 Kronos 最看多 K=N-2 只)

由于 8/14 是周五,8/15 之后的数据无法获取(预测当日),所以 hold=5d 后
8/14 入场无法验证。这里限定:8/3-8/7 入场,8/8-8/14 完整验证。
"""
import argparse, json, os, sys, glob
sys.path.insert(0, '/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos')
sys.path.insert(0, '/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/scripts')

import numpy as np
import pandas as pd
import torch
import yfinance as yf
from model import Kronos, KronosTokenizer, KronosPredictor
from evaluate_kronos_ic import apply_price_limit, load_daily_bars_csv


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--rec-dir",
                   default="/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/recommendations")
    p.add_argument("--start", default="2026-08-03")
    p.add_argument("--end", default="2026-08-07",
                   help="入场日范围(必须在 lookback + 5d 窗口内)")
    p.add_argument("--lookback", type=int, default=200)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--realise-horizon", type=int, default=5)
    p.add_argument("--sample-count", type=int, default=2)
    p.add_argument("--csv-dir", default="/tmp/kilo/kronos_pool_csv")
    p.add_argument("--model",
                   default="/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/"
                           "finetune_csv/finetuned/pool_133_daily_uniform/basemodel/best_model")
    p.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base")
    p.add_argument("--device", default="cuda")
    p.add_argument("--out-dir", default="./outputs/filter_real_rec")
    p.add_argument("--run-tag", default="real_rec_v1")
    return p.parse_args()


def load_real_recs(args):
    files = sorted(glob.glob(f'{args.rec_dir}/*.json'))
    rows = []
    for fp in files:
        with open(fp) as f:
            d = json.load(f)
        for r in d["recommendations"]:
            rows.append({
                "date": d["date"],
                "session": d["session"],
                "code": str(r["code"]).zfill(6),
                "name": r["name"],
                "weight": r.get("weight", 0),
                "combined_score": r.get("combined_score", 0),
            })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= args.start) & (df["date"] <= args.end)]
    # 每天 morning+evening 合并去重
    df = df.drop_duplicates(subset=["date", "code"]).sort_values(["date", "code"])
    return df


def main():
    args = parse_args()
    out_dir = os.path.join(args.out_dir, args.run_tag)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[load] model from {args.model}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(model, tokenizer, device=args.device, max_context=512)

    print(f"[load] real recs from {args.rec_dir}")
    recs = load_real_recs(args)
    print(f"  total recs in window: {len(recs)}  unique (date,symbol): "
          f"{recs.drop_duplicates(['date','code']).shape[0]}")
    print(f"  days: {sorted(recs['date'].dt.date.unique())}")

    # 预加载所有出现过的票的 K 线
    syms = sorted(recs["code"].unique())
    bars = {}
    for s in syms:
        fp = os.path.join(args.csv_dir, f"{s}.csv")
        if os.path.exists(fp):
            bars[s] = load_daily_bars_csv(s, args.csv_dir)
    print(f"  loaded bars for {len(bars)} symbols (out of {len(syms)})")

    # 每天: 跑 Kronos 评分,取 5 日真实收益,对比策略
    daily_results = []

    for day, grp in recs.groupby("date"):
        candidates = grp["code"].tolist()
        print(f"\n>> {day.date()}  N={len(candidates)} candidates: {candidates}")

        scored = {}  # sym -> pred_ret
        real_rets = {}  # sym -> 5 日真实收益
        last_close_map = {}

        for sym in candidates:
            if sym not in bars:
                continue
            df = bars[sym]
            ctx = df[df["date"] <= day].sort_values("date")
            if len(ctx) < args.lookback:
                continue
            x_df = ctx.iloc[-args.lookback:]
            x_ts = pd.DatetimeIndex(x_df["date"])
            last_date = x_df["date"].iloc[-1]
            y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1),
                                  periods=args.pred_len)
            try:
                pred_df = predictor.predict(
                    df=x_df[["open", "high", "low", "close", "volume", "amount"]],
                    x_timestamp=x_ts,
                    y_timestamp=pd.Series(y_ts),
                    pred_len=args.pred_len, T=1.0, top_p=0.9,
                    sample_count=args.sample_count, verbose=False,
                )
                last_close = float(x_df["close"].iloc[-1])
                path = apply_price_limit(pred_df["close"].values.astype(float),
                                          last_close, 0.10)
                pred_ret = float(path[-1] / last_close - 1)
                target = last_date + pd.tseries.offsets.BDay(args.realise_horizon)
                fut = df[df["date"] >= target]
                if fut.empty:
                    continue
                real_close = float(fut.iloc[0]["close"])
                real_ret = real_close / last_close - 1
                scored[sym] = pred_ret
                last_close_map[sym] = last_close
                real_rets[sym] = real_ret
            except Exception as e:
                print(f"    {sym}: {type(e).__name__}: {e}")

        if len(scored) < 3:
            print(f"  skip, only {len(scored)} scored")
            continue

        # 按 Kronos 升序 = 最看跌在前
        ranked = sorted(scored.items(), key=lambda x: x[1])
        ranked_syms = [s for s, _ in ranked]
        N = len(ranked_syms)

        # A: no_filter
        A_ret = np.mean([real_rets[s] for s in ranked_syms])

        # B: drop_bottom_1
        B_syms = ranked_syms[1:]
        B_ret = np.mean([real_rets[s] for s in B_syms])

        # C: drop_bottom_2
        if N >= 4:
            C_syms = ranked_syms[2:]
            C_ret = np.mean([real_rets[s] for s in C_syms])
        else:
            C_ret = np.nan
            C_syms = []

        # D: drop_bottom_3
        if N >= 5:
            D_syms = ranked_syms[3:]
            D_ret = np.mean([real_rets[s] for s in D_syms])
        else:
            D_ret = np.nan
            D_syms = []

        # E: keep_top_K=N-2
        if N >= 3:
            K = max(1, N - 2)
            E_syms = ranked_syms[-K:]
            E_ret = np.mean([real_rets[s] for s in E_syms])
        else:
            E_ret = np.nan
            E_syms = []

        # 每只票的明细
        per_stock = []
        for sym in ranked_syms:
            per_stock.append({
                "sym": sym,
                "kronos_pred_ret": scored[sym],
                "real_5d_ret": real_rets[sym],
                "last_close": last_close_map[sym],
            })

        print(f"  ranked (most-bearish first):")
        for ps in per_stock:
            print(f"    {ps['sym']}  pred={ps['kronos_pred_ret']:+.3f}  "
                  f"real5d={ps['real_5d_ret']:+.3f}")
        print(f"  A(no_filter={A_ret*100:+.2f}%)  B(drop1={B_ret*100:+.2f}%)  "
              f"C(drop2={C_ret*100 if not np.isnan(C_ret) else 'NA':>+.2f}%)  "
              f"D(drop3={D_ret*100 if not np.isnan(D_ret) else 'NA':>+.2f}%)  "
              f"E(keep_top={E_ret*100 if not np.isnan(E_ret) else 'NA':>+.2f}%)")

        daily_results.append({
            "date": day.date(),
            "N": N,
            "candidates": ",".join(ranked_syms),
            "kronos_most_bearish": ranked_syms[0],
            "kronos_most_bullish": ranked_syms[-1],
            "A_no_filter_ret": A_ret,
            "A_syms": ",".join(ranked_syms),
            "B_drop1_ret": B_ret,
            "B_syms": ",".join(B_syms),
            "C_drop2_ret": C_ret,
            "C_syms": ",".join(C_syms) if C_syms else "",
            "D_drop3_ret": D_ret,
            "D_syms": ",".join(D_syms) if D_syms else "",
            "E_keep_top_ret": E_ret,
            "E_syms": ",".join(E_syms) if E_syms else "",
            "per_stock_detail": json.dumps(per_stock, ensure_ascii=False),
        })

    df = pd.DataFrame(daily_results)
    df.to_csv(os.path.join(out_dir, "daily_results.csv"), index=False)

    # ---- 汇总 ----
    print("\n" + "=" * 90)
    print("真实推荐 × Kronos 过滤器 验证结果")
    print("=" * 90)

    summary = {}
    for col, label in [
        ("A_no_filter_ret", "no_filter (您的原始推荐)"),
        ("B_drop1_ret", "drop_bottom_1 (剔除 1 只)"),
        ("C_drop2_ret", "drop_bottom_2 (剔除 2 只)"),
        ("D_drop3_ret", "drop_bottom_3 (剔除 3 只)"),
        ("E_keep_top_ret", "keep_top_K (只留 Kronos 最看多)"),
    ]:
        r = df[col].dropna()
        if r.empty:
            continue
        win = (r > 0).mean()
        avg = r.mean()
        total = (1 + r).prod() - 1
        sharpe = avg / (r.std() + 1e-9) * np.sqrt(252 / 5)
        # vs no_filter 配对 t
        A = df["A_no_filter_ret"].dropna()
        r2 = df[col].dropna()
        common = r2.index.intersection(A.index)
        sig = ""
        if len(common) >= 5:
            from scipy.stats import ttest_rel
            t, p = ttest_rel(r2.loc[common], A.loc[common])
            sig = f"  vs A: t={t:+.2f} p={p:.3f} {'✓sig' if p<0.05 else '✗'}"
        print(f"{label:<35} n={len(r):>2}  win={win*100:>5.1f}%  "
              f"avg={avg*100:>+6.2f}%  total={total*100:>+7.2f}%  "
              f"sharpe={sharpe:>5.2f}{sig}")
        summary[label] = {
            "n": int(len(r)), "win_rate": float(win),
            "avg_ret": float(avg), "total_return": float(total),
            "sharpe": float(sharpe),
        }

    # 每只票的 Kronos 准确率(Kronos 看跌的票是否真的跌了?)
    correct_bear = 0
    total_bear = 0
    correct_bull = 0
    total_bull = 0
    for _, row in df.iterrows():
        dets = json.loads(row["per_stock_detail"])
        # 最看跌 = pred 最小
        worst = min(dets, key=lambda x: x["kronos_pred_ret"])
        best = max(dets, key=lambda x: x["kronos_pred_ret"])
        if worst["real_5d_ret"] < 0:
            correct_bear += 1
        total_bear += 1
        if best["real_5d_ret"] > 0:
            correct_bull += 1
        total_bull += 1
    print(f"\nKronos '最看跌' 是否真跌: {correct_bear}/{total_bear} = "
          f"{correct_bear/total_bear*100:.0f}%")
    print(f"Kronos '最看多' 是否真涨: {correct_bull}/{total_bull} = "
          f"{correct_bull/total_bull*100:.0f}%")

    summary["kronos_most_bearish_hit_rate"] = correct_bear / total_bear
    summary["kronos_most_bullish_hit_rate"] = correct_bull / total_bull

    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump({"args": vars(args), "summary": summary,
                   "per_day": df.to_dict(orient="records")},
                  f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[saved] {out_dir}/daily_results.csv + summary.json")


if __name__ == "__main__":
    main()