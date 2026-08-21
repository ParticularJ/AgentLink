# -*- coding: utf-8 -*-
"""
real_rec_filter_full.py
完整版:用 7/1-8/13 的真实推荐 + yfinance 拉真实收盘价
验证 Kronos 过滤器效果。

每个交易日 d:
  - 取 d 当天的 morning+evening 推荐(去重)
  - 跑 Kronos (lookback=200 截止 d) 得每只 pred_ret
  - 假设 d+1 开盘买入,持有 5 个交易日(到 d+5 收盘)
  - 比较 5 种策略:
      A. no_filter
      B. drop_bottom_1
      C. drop_bottom_2
      D. drop_bottom_3
      E. keep_top_K (只留最看多 K=N-2 只)
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
    p.add_argument("--start", default="2026-07-01")
    p.add_argument("--end", default="2026-08-13")
    p.add_argument("--lookback", type=int, default=200)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--hold-bd", type=int, default=5,
                   help="持有天数 (BD)")
    p.add_argument("--sample-count", type=int, default=2)
    p.add_argument("--csv-dir", default="/tmp/kilo/kronos_pool_csv")
    p.add_argument("--yf-dir", default="/tmp/kilo/yf_data")
    p.add_argument("--model",
                   default="/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/"
                           "finetune_csv/finetuned/pool_133_daily_uniform/basemodel/best_model")
    p.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base")
    p.add_argument("--device", default="cuda")
    p.add_argument("--out-dir", default="./outputs/filter_real_rec_full")
    p.add_argument("--run-tag", default="full_v1")
    return p.parse_args()


def load_yf_real_prices(args, syms):
    """从 yfinance 或 yf_dir 缓存读取 7/1-8/14 真实收盘价。"""
    cache = {}
    for s in syms:
        fp = f'{args.yf_dir}/{s}.csv'
        if os.path.exists(fp):
            h = pd.read_csv(fp, parse_dates=['Date'])
            h = h.rename(columns={'Date': 'date', 'Open': 'open', 'Close': 'close'})
            h['date'] = pd.to_datetime(h['date']).dt.tz_localize(None)
            cache[s] = h[['date', 'open', 'close']]
        else:
            yt = (f'{s}.SS' if s.startswith(('600','601','603','605','688','900'))
                  else f'{s}.SZ')
            try:
                h = yf.Ticker(yt).history(start='2026-06-25', end='2026-08-16')
                if not h.empty:
                    h = h.reset_index()[['Date','Open','Close']]
                    h.columns = ['date','open','close']
                    h['date'] = pd.to_datetime(h['date']).dt.tz_localize(None)
                    cache[s] = h
            except Exception as e:
                print(f'  [warn] {s} yf fail: {e}')
    return cache


def main():
    args = parse_args()
    out_dir = os.path.join(args.out_dir, args.run_tag)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[load] tokenizer + model")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(model, tokenizer, device=args.device, max_context=512)

    # 1) 加载推荐
    files = sorted(glob.glob(f'{args.rec_dir}/20260[7-8]*.json'))
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
            })
    recs = pd.DataFrame(rows).drop_duplicates(["date", "code"])
    recs["date"] = pd.to_datetime(recs["date"])
    recs = recs[(recs["date"] >= args.start) & (recs["date"] <= args.end)]
    print(f"[load] {len(recs)} recs, days: {sorted(recs['date'].dt.date.unique())}")

    # 2) 预加载本地 bars(给 Kronos) + yfinance 真实收盘(给收益)
    syms = sorted(recs["code"].unique())
    local_bars = {}
    for s in syms:
        fp = f'{args.csv_dir}/{s}.csv'
        if os.path.exists(fp):
            local_bars[s] = load_daily_bars_csv(s, args.csv_dir)
    print(f"[load] {len(local_bars)} local bars (in 133 pool)")

    # 不在 133 池的票 → 从 yfinance 拉历史数据给 Kronos
    print(f"[load] fetching yf history for remaining {len(syms) - len(local_bars)} symbols...")
    yf_bars = {}
    for s in syms:
        if s in local_bars:
            continue
        yt = (f'{s}.SS' if s.startswith(('600','601','603','605','688','900'))
              else f'{s}.SZ')
        try:
            h = yf.Ticker(yt).history(start='2020-01-01', end='2026-08-14')
            if not h.empty:
                h = h.reset_index()
                # 适配字段
                df = pd.DataFrame({
                    'date': pd.to_datetime(h['Date']).dt.tz_localize(None),
                    'open': h['Open'], 'high': h['High'],
                    'low': h['Low'], 'close': h['Close'],
                    'volume': h['Volume'],
                })
                df['amount'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4 * df['volume']
                yf_bars[s] = df
        except Exception as e:
            print(f'  [warn] {s} yf fail: {e}')
    print(f"[load] {len(yf_bars)} additional yf bars")

    yf_prices = load_yf_real_prices(args, syms)
    print(f"[load] {len(yf_prices)} yf price series (真实)")

    # 3) 每个交易日:跑 Kronos + 计算真实 hold 期收益
    daily_results = []
    for day, grp in recs.groupby("date"):
        cands = grp["code"].tolist()
        print(f"\n>> {day.date()}  N={len(cands)}")

        scored = {}
        for sym in cands:
            df_hist = local_bars.get(sym)
            if df_hist is None:
                df_hist = yf_bars.get(sym)
            if df_hist is None or df_hist.empty:
                # print(f'    [skip] {sym}: no bars')
                continue
            ctx = df_hist[df_hist["date"] <= day].sort_values("date")
            if len(ctx) < args.lookback:
                # print(f'    [skip] {sym}: ctx rows={len(ctx)} < {args.lookback}')
                continue
            x_df = ctx.iloc[-args.lookback:]
            x_ts = pd.DatetimeIndex(x_df["date"])
            last_date = x_df["date"].iloc[-1]
            y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1),
                                  periods=args.pred_len)
            try:
                pred_df = predictor.predict(
                    df=x_df[["open","high","low","close","volume","amount"]],
                    x_timestamp=x_ts,
                    y_timestamp=pd.Series(y_ts),
                    pred_len=args.pred_len, T=1.0, top_p=0.9,
                    sample_count=args.sample_count, verbose=False,
                )
                last_close = float(x_df["close"].iloc[-1])
                path = apply_price_limit(pred_df["close"].values.astype(float),
                                          last_close, 0.10)
                pred_ret = float(path[-1] / last_close - 1)

                # 真实收益:用 d+1 开盘买入,d+hold 收盘卖出
                if sym not in yf_prices:
                    # print(f'    [skip] {sym}: no yf prices')
                    continue
                yf_df = yf_prices[sym]
                # entry: day + 1 BD 之后的第一个交易日 open
                future = yf_df[yf_df["date"] > last_date].sort_values("date")
                if future.empty:
                    # print(f'    [skip] {sym}: future empty (last_date={last_date})')
                    continue
                entry_open = float(future.iloc[0]["open"])
                # exit: entry 后第 hold BD 收盘
                if len(future) < args.hold_bd + 1:
                    # print(f'    [skip] {sym}: future rows={len(future)} < {args.hold_bd+1}')
                    continue
                exit_close = float(future.iloc[args.hold_bd]["close"])
                real_ret = exit_close / entry_open - 1

                scored[sym] = {
                    "pred_ret": pred_ret,
                    "last_close": last_close,
                    "last_date": last_date,
                    "entry_open": entry_open,
                    "exit_close": exit_close,
                    "real_ret": real_ret,
                }
            except Exception as e:
                print(f'    [err] {sym}: {type(e).__name__}: {e}')

        if len(scored) < 3:
            print(f"  only {len(scored)} scored, skip")
            continue

        # 按 Kronos 升序排
        ranked = sorted(scored.items(), key=lambda x: x[1]["pred_ret"])
        ranked_syms = [s for s, _ in ranked]
        N = len(ranked_syms)

        print(f"  ranked (most-bearish → most-bullish):")
        for sym in ranked_syms:
            print(f"    {sym}  pred={scored[sym]['pred_ret']*100:+6.2f}%  "
                  f"realH={scored[sym]['real_ret']*100:+6.2f}%")

        # 各策略
        def avg(syms):
            return np.mean([scored[s]["real_ret"] for s in syms]) if syms else np.nan

        A_ret = avg(ranked_syms)
        B_ret = avg(ranked_syms[1:]) if N >= 4 else np.nan
        C_ret = avg(ranked_syms[2:]) if N >= 5 else np.nan
        D_ret = avg(ranked_syms[3:]) if N >= 6 else np.nan
        K = max(1, N - 2)
        E_ret = avg(ranked_syms[-K:])

        def f(x):
            return f'{x*100:+6.2f}%' if not (isinstance(x, float) and np.isnan(x)) else '   N/A'
        print(f"  A(no)={f(A_ret)} B(drop1)={f(B_ret)} "
              f"C(drop2)={f(C_ret)} D(drop3)={f(D_ret)} "
              f"E(top)={f(E_ret)}")

        daily_results.append({
            "date": day.date(),
            "N": N,
            "A_no_filter": A_ret,
            "B_drop_1": B_ret,
            "C_drop_2": C_ret,
            "D_drop_3": D_ret,
            "E_keep_top": E_ret,
            "most_bearish": ranked_syms[0],
            "most_bearish_pred": scored[ranked_syms[0]]["pred_ret"],
            "most_bearish_real": scored[ranked_syms[0]]["real_ret"],
            "most_bullish": ranked_syms[-1],
            "most_bullish_pred": scored[ranked_syms[-1]]["pred_ret"],
            "most_bullish_real": scored[ranked_syms[-1]]["real_ret"],
            "ranked_detail": json.dumps([(s, scored[s]["pred_ret"],
                                          scored[s]["real_ret"])
                                         for s in ranked_syms],
                                         ensure_ascii=False),
        })

    df = pd.DataFrame(daily_results)
    df.to_csv(os.path.join(out_dir, "daily_results.csv"), index=False)
    print(f"\n[save] {len(df)} days → {out_dir}/daily_results.csv")

    # ---- 汇总 ----
    print("\n" + "="*100)
    print(f"{'策略':<35} {'n':>3} {'avg%':>8} {'累计%':>9} {'胜率':>7} {'vs A(配对)':>20}")
    print("="*100)
    from scipy.stats import ttest_rel

    summary = {}
    A = df["A_no_filter"].dropna()
    for col, label in [
        ("A_no_filter", "A 您的原推荐 (no filter)"),
        ("B_drop_1",    "B drop_bottom_1 (剔除1只)"),
        ("C_drop_2",    "C drop_bottom_2 (剔除2只)"),
        ("D_drop_3",    "D drop_bottom_3 (剔除3只)"),
        ("E_keep_top",  "E keep_top_K (N-2 只最看多)"),
    ]:
        r = df[col].dropna()
        if r.empty:
            continue
        avg = r.mean()
        total = (1 + r).prod() - 1
        win = (r > 0).mean()
        sharpe = avg / (r.std() + 1e-9) * np.sqrt(252 / 5)
        sig = ""
        if col != "A_no_filter":
            common = r.index.intersection(A.index)
            if len(common) >= 3:
                t, p = ttest_rel(r.loc[common], A.loc[common])
                diff = (r.loc[common] - A.loc[common]).mean()
                sig = f"  diff={diff*100:+.3f}% t={t:+.2f} p={p:.3f} {'✓' if p<0.05 else '✗'}"
        print(f"{label:<35} {len(r):>3} {avg*100:>+7.3f}% {total*100:>+8.2f}% "
              f"{win*100:>5.1f}% sharpe={sharpe:>5.2f}{sig}")
        summary[label] = {
            "n": int(len(r)), "avg_ret": float(avg),
            "total_return": float(total), "win_rate": float(win),
            "sharpe": float(sharpe),
        }

    # Kronos 准确率
    bear_hit = bear_tot = bull_hit = bull_tot = 0
    for _, row in df.iterrows():
        if row["most_bearish_real"] < 0: bear_hit += 1
        bear_tot += 1
        if row["most_bullish_real"] > 0: bull_hit += 1
        bull_tot += 1
    print(f"\n[Kronos 准确率]  最看跌真跌: {bear_hit}/{bear_tot} = {bear_hit/bear_tot*100:.0f}%")
    print(f"[Kronos 准确率]  最看多真涨: {bull_hit}/{bull_tot} = {bull_hit/bull_tot*100:.0f}%")
    summary["kronos_most_bearish_hit_rate"] = bear_hit / bear_tot
    summary["kronos_most_bullish_hit_rate"] = bull_hit / bull_tot

    # 配对检验细节
    print("\n[逐日明细]")
    print(f"{'date':<12}{'N':>3}{'A':>8}{'B':>8}{'C':>8}{'D':>8}{'E':>8}")
    for _, r in df.iterrows():
        def f(x):
            return f'{x*100:+6.2f}%' if not (isinstance(x, float) and np.isnan(x)) else '   N/A'
        print(f"{str(r['date']):<12}{int(r['N']):>3}{f(r['A_no_filter']):>8}{f(r['B_drop_1']):>8}"
              f"{f(r['C_drop_2']):>8}{f(r['D_drop_3']):>8}{f(r['E_keep_top']):>8}")

    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump({"args": vars(args), "summary": summary}, f, indent=2, default=str)
    print(f"\n[saved] {out_dir}/summary.json")


if __name__ == "__main__":
    main()