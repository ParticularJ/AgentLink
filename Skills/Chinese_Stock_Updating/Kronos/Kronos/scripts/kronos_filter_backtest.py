# -*- coding: utf-8 -*-
"""
kronos_filter_backtest.py

历史回测:验证"Kronos 极端看跌剔除过滤器"是否真能提升胜率。

实验设计:
  - 每周随机抽 N 只做"候选池"
  - 跑 Kronos,得到每只 pred_ret
  - 比较以下策略 5 日持有期表现:
      A. no_filter      : 原 N 只等权
      B. drop_bottom_1  : 剔除 Kronos 最看跌 1 只
      C. drop_bottom_2  : 剔除 Kronos 最看跌 2 只
      D. drop_bottom_3  : 剔除 Kronos 最看跌 3 只
      E. keep_top_K     : 只保留 Kronos 最看多 K 只
  - 输出每个 N (5/8/10/15) 的对比表
  - 还跑随机剔除做对照(random_drop_2 = 随机剔除 2 只)
"""
import argparse, json, os, sys
sys.path.insert(0, '/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos')
sys.path.insert(0, '/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/scripts')

import numpy as np
import pandas as pd
import torch
from model import Kronos, KronosTokenizer, KronosPredictor
from evaluate_kronos_ic import apply_price_limit, load_daily_bars_csv


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2023-06-01")
    p.add_argument("--end", default="2026-08-07")
    p.add_argument("--rebalance-freq", default="W-FRI")
    p.add_argument("--candidate-pool-sizes", default="5,8,10,15",
                   help="逗号分隔,每个 N 做一轮实验")
    p.add_argument("--lookback", type=int, default=200)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--realise-horizon", type=int, default=5)
    p.add_argument("--sample-count", type=int, default=1)
    p.add_argument("--csv-dir", default="/tmp/kilo/kronos_pool_csv")
    p.add_argument("--model",
                   default="/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/"
                           "finetune_csv/finetuned/pool_133_daily_uniform/basemodel/best_model")
    p.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", default="./outputs/filter_backtest")
    p.add_argument("--run-tag", default="filter_v1")
    return p.parse_args()


def main():
    args = parse_args()
    out_dir = os.path.join(args.out_dir, args.run_tag)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[load] tokenizer + model from {args.model}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(model, tokenizer, device=args.device, max_context=512)

    # 1) 加载 133 池所有可用标的的 K 线
    sym_files = sorted([f for f in os.listdir(args.csv_dir) if f.endswith('.csv')])
    print(f"[load] {len(sym_files)} symbol CSVs")

    bars = {}
    valid_syms = []
    for f in sym_files:
        sym = f[:-4]
        df = load_daily_bars_csv(sym, args.csv_dir)
        if len(df) >= args.lookback + args.realise_horizon + 30:
            bars[sym] = df
            valid_syms.append(sym)
    print(f"[load] {len(valid_syms)} symbols have enough history")

    # 2) 调仓日历
    rebal_dates = pd.date_range(args.start, args.end, freq=args.rebalance_freq)
    print(f"[plan] {len(rebal_dates)} rebalance dates")

    # 3) 候选池规模
    N_list = [int(x) for x in args.candidate_pool_sizes.split(",")]
    rng = np.random.default_rng(args.seed)

    # 4) 每个调仓日:对每个 N 抽 N 只候选,跑 Kronos,得到评分
    #    然后比较 6 种策略的 5 日真实收益
    daily_results = []

    for i, day in enumerate(rebal_dates):
        # 池中当日及之前有数据的票
        avail = [s for s in valid_syms if bars[s]["date"].max() >= day]
        if len(avail) < max(N_list) + 3:
            continue

        # 一次性抽 max(N)+5,所有 N 共享同一随机子集(更公平)
        max_n = max(N_list) + 3
        chosen = list(rng.choice(avail, size=min(max_n, len(avail)), replace=False))

        # 跑 Kronos 给每只打分
        scored = {}  # sym -> pred_ret
        last_close_map = {}
        real_close_map = {}

        for sym in chosen:
            df_hist = bars[sym]
            ctx = df_hist[df_hist["date"] <= day].sort_values("date")
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
                    pred_len=args.pred_len,
                    T=1.0, top_p=0.9,
                    sample_count=args.sample_count, verbose=False,
                )
                last_close = float(x_df["close"].iloc[-1])
                path = apply_price_limit(
                    pred_df["close"].values.astype(float), last_close, 0.10)
                pred_ret = float(path[-1] / last_close - 1)

                # 5 日真实收益
                target = last_date + pd.tseries.offsets.BDay(args.realise_horizon)
                fut = df_hist[df_hist["date"] >= target]
                if fut.empty:
                    continue
                real_close = float(fut.iloc[0]["close"])
                real_ret = real_close / last_close - 1

                scored[sym] = pred_ret
                last_close_map[sym] = last_close
                real_close_map[sym] = real_close
            except Exception:
                continue

        if len(scored) < max(N_list):
            continue

        # 实际拿 max(N_list) 只,按 Kronos 升序排
        ranked = sorted(scored.items(), key=lambda x: x[1])
        ranked_syms = [s for s, _ in ranked]

        # 对每个 N 跑各种策略
        for N in N_list:
            if N > len(ranked_syms):
                continue
            sub_syms = ranked_syms[:N]
            sub_rets = {s: real_close_map[s] / last_close_map[s] - 1 for s in sub_syms}

            # 策略 A: no_filter (全部 N 只等权)
            A_ret = np.mean([sub_rets[s] for s in sub_syms])

            # 策略 B/C/D: 剔除最看跌 1/2/3 只(如果 N > drop)
            def filter_drop(k):
                if k >= N:
                    return None, None
                keep = sub_syms[k:]
                return np.mean([sub_rets[s] for s in keep]), keep

            B_ret, _ = filter_drop(1)
            C_ret, C_keep = filter_drop(2)
            D_ret, _ = filter_drop(3)

            # 策略 E: keep_top_K 只看多 K 只
            top_k = max(1, N - 3)
            E_ret = np.mean([sub_rets[s] for s in sub_syms[-top_k:]])

            # 策略 F: 随机剔除 2 只(对照,跑 20 次取均值)
            np.random.seed(int(day.strftime("%Y%m%d")) + N)
            F_rets = []
            for _ in range(20):
                drop_idx = np.random.choice(N, size=2, replace=False)
                keep = [sub_syms[i] for i in range(N) if i not in drop_idx]
                F_rets.append(np.mean([sub_rets[s] for s in keep]))
            F_ret = np.mean(F_rets)

            daily_results.append({
                "date": day, "N": N,
                "A_no_filter": A_ret,
                "B_drop_1": B_ret if B_ret is not None else np.nan,
                "C_drop_2": C_ret if C_ret is not None else np.nan,
                "D_drop_3": D_ret if D_ret is not None else np.nan,
                "E_keep_top": E_ret,
                "F_random_drop_2": F_ret,
            })

        if (i + 1) % 20 == 0 or i == 0:
            print(f"[{i+1:>4}/{len(rebal_dates)}] {day.date()}  "
                  f"scored {len(scored)} symbols")

    df = pd.DataFrame(daily_results)
    df.to_csv(os.path.join(out_dir, "daily_results.csv"), index=False)
    print(f"\n[save] {len(df)} rebalance-days × {len(N_list)} N-sizes → "
          f"{out_dir}/daily_results.csv")

    # ---- 汇总每个 N 的策略对比 ----
    print("\n" + "=" * 90)
    print("Kronos 过滤器历史回测结果")
    print("=" * 90)
    print(f"{'N':>4} {'策略':<18} {'win%':>7} {'avgRet':>9} {'总收益':>9} "
          f"{'Sharpe':>7} {'胜vs A':>9} {'p值':>7}")
    print("-" * 90)

    summary_per_N = {}
    for N in sorted(df["N"].unique()):
        sub = df[df["N"] == N]
        A = sub["A_no_filter"].dropna()
        metrics = {}

        def stats(col, label):
            r = sub[col].dropna()
            if r.empty:
                return
            win = (r > 0).mean()
            avg = r.mean()
            total = (1 + r).prod() - 1
            sharpe = r.mean() / (r.std() + 1e-9) * np.sqrt(252 / 5)
            metrics[label] = {
                "win_rate": float(win), "avg_ret": float(avg),
                "total_return": float(total), "sharpe": float(sharpe),
                "n": int(len(r)),
            }
            return win, avg, total, sharpe

        print(f"\n--- 候选池大小 N = {N} ---")
        for col, label in [
            ("A_no_filter", "no_filter"),
            ("B_drop_1", "drop_bottom_1"),
            ("C_drop_2", "drop_bottom_2"),
            ("D_drop_3", "drop_bottom_3"),
            ("E_keep_top", "keep_top_K"),
            ("F_random_drop_2", "random_drop_2"),
        ]:
            stats(col, label)

        # 配对 t 检验 vs A
        from scipy.stats import ttest_rel
        out = {}
        for col, label in [
            ("B_drop_1", "drop_bottom_1"),
            ("C_drop_2", "drop_bottom_2"),
            ("D_drop_3", "drop_bottom_3"),
            ("E_keep_top", "keep_top_K"),
            ("F_random_drop_2", "random_drop_2"),
        ]:
            r = sub[col].dropna()
            rA = A.loc[r.index]
            if len(r) >= 10:
                t, p = ttest_rel(r, rA)
                win = (r > 0).mean()
                win_A = (rA > 0).mean()
                sig = "✓" if p < 0.05 else "✗"
                print(f"{'':>4}{label:<18}{(r>0).mean()*100:>6.1f}% "
                      f"{r.mean()*100:>+8.3f}% {(1+r).prod()-1:>+8.2f}% "
                      f"{r.mean()/(r.std()+1e-9)*np.sqrt(252/5):>7.2f} "
                      f"{(win-win_A)*100:>+8.1f}%{p:>7.3f} {sig}")
                out[label] = {
                    "win_rate": float((r > 0).mean()),
                    "avg_ret": float(r.mean()),
                    "total_return": float((1 + r).prod() - 1),
                    "sharpe": float(r.mean() / (r.std() + 1e-9) * np.sqrt(252 / 5)),
                    "n": int(len(r)),
                    "win_rate_A": float(win_A),
                    "win_rate_delta": float(win - win_A),
                    "t_stat": float(t), "p_value": float(p),
                    "significant_5pct": bool(p < 0.05),
                }
        summary_per_N[int(N)] = out

        # 单独打 no_filter 行
        print(f"{'':>4}{'no_filter (A)':<18}{(A>0).mean()*100:>6.1f}% "
              f"{A.mean()*100:>+8.3f}% {(1+A).prod()-1:>+8.2f}% "
              f"{A.mean()/(A.std()+1e-9)*np.sqrt(252/5):>7.2f}  ---     ---")

    # 保存
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump({"args": vars(args), "per_N": summary_per_N}, f,
                  indent=2, default=str)
    print(f"\n[saved] {out_dir}/summary.json")


if __name__ == "__main__":
    main()