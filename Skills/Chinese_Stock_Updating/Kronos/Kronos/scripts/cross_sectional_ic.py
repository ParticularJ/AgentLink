# -*- coding: utf-8 -*-
"""
cross_sectional_ic.py  —  横截面 IC 评估(在你 145 只票池子上)

功能:
  选池子里 N 只 S 级核心票(默认 15 只),在每周调仓日对所有票打分,
  用 Kronos 预测未来 5 日收益率,然后对真实 5 日收益做截面
  Pearson IC / Spearman RankIC / DA。

数据源:
  finetune_csv/data/pool.csv (long-format multi-symbol)

使用:
  python scripts/cross_sectional_ic.py \
      --pool-csv finetune_csv/data/pool.csv \
      --tokenizer finetune_csv/finetuned/pool_133_daily/tokenizer/best_model \
      --model finetune_csv/finetuned/pool_133_daily/basemodel/best_model \
      --start 2025-06-01 --end 2026-08-07 \
      --lookback 200 --pred-len 5 \
      --anchor-freq W \
      --max-symbols 15 \
      --device cuda \
      --run-tag pool_133_cs
"""
import argparse
import json
import os
import sys
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description="Cross-sectional IC over pool symbols")
    p.add_argument("--pool-csv", required=True)
    p.add_argument("--tokenizer", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--lookback", type=int, default=200)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--anchor-freq", default="W", choices=["B", "W", "M"])
    p.add_argument("--max-symbols", type=int, default=15)
    p.add_argument("--symbol-level", default="S",
                   help="Only include symbols with this level (S/A/B+/压舱石). Empty = all")
    p.add_argument("--device", default="cuda", choices=["cpu", "cuda"])
    p.add_argument("--max-context", type=int, default=200)
    p.add_argument("--sample-count", type=int, default=2)
    p.add_argument("--T", type=float, default=1.0)
    p.add_argument("--top-p", type=float, default=0.9)
    p.add_argument("--price-limit", type=float, default=0.10)
    p.add_argument("--out-dir", default="./outputs/cs")
    p.add_argument("--run-tag", default="pool_cs")
    return p.parse_args()


def main():
    args = parse_args()
    out_dir = os.path.join(args.out_dir, args.run_tag)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[load] pool: {args.pool_csv}")
    pool = pd.read_csv(args.pool_csv, dtype={"symbol": str})
    pool["timestamps"] = pd.to_datetime(pool["timestamps"])
    print(f"[load] {len(pool)} rows, {pool.symbol.nunique()} symbols")

    # Symbol selection: top by level (S preferred), then by row count.
    if args.symbol_level:
        cand = pool[pool["level"] == args.symbol_level]
    else:
        cand = pool
    sym_counts = cand.groupby("symbol").size().sort_values(ascending=False)
    selected = sym_counts.head(args.max_symbols).index.tolist()
    print(f"[plan] selected {len(selected)} symbols (level={args.symbol_level or 'all'}):")
    for s in selected:
        n = int((pool.symbol == s).sum())
        print(f"   {s}  rows={n}")

    # Per-symbol long-format data, sorted by timestamp.
    by_sym: Dict[str, pd.DataFrame] = {
        s: pool[pool.symbol == s].sort_values("timestamps").reset_index(drop=True)
        for s in selected
    }

    # Build weekly anchor dates within [start, end].
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    if args.anchor_freq == "B":
        anchors = pd.date_range(start=start, end=end, freq="B")
    elif args.anchor_freq == "W":
        anchors = pd.date_range(start=start, end=end, freq="W-FRI")
    else:
        anchors = pd.date_range(start=start, end=end, freq="BM")
    anchors = [a for a in anchors if a >= start]
    # Filter anchors: must leave pred_len B-days for realisation.
    print(f"[plan] {len(anchors)} anchor dates from {start.date()} to {end.date()}")

    print(f"[load] tokenizer: {args.tokenizer}")
    print(f"[load] model:     {args.model}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(
        model, tokenizer, device=args.device, max_context=args.max_context,
    )

    rows = []
    skipped_anchor_no_data = 0
    skipped_anchor_future = 0
    n_pred_calls = 0
    for ai, anchor in enumerate(anchors, 1):
        day_records = []
        for sym in selected:
            df = by_sym[sym]
            ctx = df[df.timestamps <= anchor]
            if len(ctx) < args.lookback:
                continue
            last_close = float(ctx["close"].iloc[-1])
            # Realised close at anchor + pred_len B-days
            future = df[(df.timestamps > anchor)].head(args.pred_len)
            if len(future) < args.pred_len:
                skipped_anchor_future += 1
                continue
            real_close = float(future["close"].iloc[-1])
            # Predict
            x = ctx.iloc[-args.lookback:]
            try:
                x_ts = pd.Series(pd.DatetimeIndex(x["timestamps"]))
                y_ts = pd.Series(pd.bdate_range(
                    start=x["timestamps"].iloc[-1] + pd.Timedelta(days=1),
                    periods=args.pred_len))
                pred = predictor.predict(
                    df=x[["open", "high", "low", "close", "volume", "amount"]],
                    x_timestamp=x_ts, y_timestamp=y_ts,
                    pred_len=args.pred_len, T=args.T, top_p=args.top_p,
                    sample_count=args.sample_count, verbose=False,
                )
                pred_close = float(pred["close"].iloc[-1])
            except Exception as e:
                print(f"  [warn] {sym} {anchor.date()}: {e}")
                continue
            n_pred_calls += 1

            day_records.append({
                "date": anchor,
                "symbol": sym,
                "last_close": last_close,
                "pred_close": pred_close,
                "real_close": real_close,
                "pred_ret": pred_close / last_close - 1.0,
                "real_ret": real_close / last_close - 1.0,
            })
        if len(day_records) >= 5:
            rows.extend(day_records)
        else:
            skipped_anchor_no_data += 1
        if ai % 5 == 0 or ai == len(anchors):
            print(f"  [anchor {ai:3d}/{len(anchors)}] {anchor.date()} "
                  f"n={len(day_records)} cum_pred={n_pred_calls}")

    if not rows:
        print("[err] no rows; abort")
        return 1

    df = pd.DataFrame(rows)

    # Cross-sectional metrics per day
    daily_metrics = []
    for date, sub in df.groupby("date"):
        if len(sub) < 5:
            continue
        try:
            ic, _ = pearsonr(sub.pred_ret, sub.real_ret)
            ric, _ = spearmanr(sub.pred_ret, sub.real_ret)
        except Exception:
            ic, ric = np.nan, np.nan
        sign_pred = np.sign(sub.pred_ret.values)
        sign_real = np.sign(sub.real_ret.values)
        mask = np.abs(sub.real_ret.values) >= 0.01  # 1% flat threshold
        if mask.sum() > 0:
            da = float(np.mean(sign_pred[mask] == sign_real[mask]))
        else:
            da = np.nan
        # Up/down capture
        up = sub[sub.pred_ret > 0]
        dn = sub[sub.pred_ret < 0]
        up_cap = float((up.real_ret > 0).mean()) if len(up) else np.nan
        dn_cap = float((dn.real_ret < 0).mean()) if len(dn) else np.nan
        daily_metrics.append({
            "date": date, "n": len(sub),
            "ic": ic, "rank_ic": ric, "da": da,
            "up_cap": up_cap, "dn_cap": dn_cap,
        })

    dm = pd.DataFrame(daily_metrics)
    dm.to_csv(os.path.join(out_dir, "daily_metrics.csv"), index=False)
    df.to_csv(os.path.join(out_dir, "per_row.csv"), index=False)

    # Headline summary
    summary = {
        "args": vars(args),
        "n_anchors_total": len(anchors),
        "n_anchors_with_data": len(dm),
        "n_rows_total": int(len(df)),
        "ic_mean": float(dm.ic.mean()),
        "ic_std": float(dm.ic.std()),
        "ic_ir": float(dm.ic.mean() / dm.ic.std()) if dm.ic.std() > 0 else np.nan,
        "rank_ic_mean": float(dm.rank_ic.mean()),
        "rank_ic_std": float(dm.rank_ic.std()),
        "rank_ic_ir": float(dm.rank_ic.mean() / dm.rank_ic.std()) if dm.rank_ic.std() > 0 else np.nan,
        "da_mean": float(dm.da.mean()),
        "da_n_days_used": int(dm.da.notna().sum()),
        "up_cap_mean": float(dm.up_cap.mean()),
        "dn_cap_mean": float(dm.dn_cap.mean()),
        "selected_symbols": selected,
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # ---- Plots ----
    # 1. IC / RankIC time series
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(dm.date, dm.ic, "o-", color="tab:blue", label=f"IC  (mean={dm.ic.mean():+.3f})", lw=1.2, ms=4)
    ax.plot(dm.date, dm.rank_ic, "s-", color="tab:orange",
            label=f"RankIC  (mean={dm.rank_ic.mean():+.3f})", lw=1.2, ms=4)
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_title(f"Cross-sectional IC  —  {len(selected)} symbols (level={args.symbol_level}) "
                 f"|  {dm.da.notna().sum()} valid days")
    ax.set_xlabel("anchor date")
    ax.set_ylabel("IC / RankIC")
    ax.legend(loc="best")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "01_ic_timeseries.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)

    # 2. Cumulative IC (a sanity check)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(dm.date, dm.ic.cumsum(), "-", color="tab:blue", label="cum IC")
    ax.plot(dm.date, dm.rank_ic.cumsum(), "-", color="tab:orange", label="cum RankIC")
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_title(f"Cumulative IC / RankIC  —  total cum IC={dm.ic.cumsum().iloc[-1]:+.2f}, "
                 f"cum RankIC={dm.rank_ic.cumsum().iloc[-1]:+.2f}")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "02_cumulative_ic.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)

    # 3. DA distribution
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(dm.da.dropna(), bins=15, color="tab:green", edgecolor="black", alpha=0.8)
    ax.axvline(0.5, color="red", linestyle="--", label="coin-flip = 50%")
    ax.axvline(dm.da.mean(), color="black", lw=1.5,
               label=f"mean = {dm.da.mean():.1%}")
    ax.set_xlabel("directional accuracy")
    ax.set_ylabel("count (days)")
    ax.set_title(f"DA distribution  —  {dm.da.notna().sum()} days, mean={dm.da.mean():.1%}")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "03_da_hist.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)

    print(f"\n=== Headline (cross-sectional, {len(dm)} days, {len(selected)} symbols) ===")
    print(f"  IC:        mean={summary['ic_mean']:+.4f}  std={summary['ic_std']:.4f}  "
          f"IR={summary['ic_ir']:+.3f}")
    print(f"  RankIC:    mean={summary['rank_ic_mean']:+.4f}  std={summary['rank_ic_std']:.4f}  "
          f"IR={summary['rank_ic_ir']:+.3f}")
    print(f"  DA(excl flat): mean={summary['da_mean']:.1%}  ({summary['da_n_days_used']} days)")
    print(f"  up_cap: {summary['up_cap_mean']:.1%}    dn_cap: {summary['dn_cap_mean']:.1%}")
    print(f"\n[done] artefacts under: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())