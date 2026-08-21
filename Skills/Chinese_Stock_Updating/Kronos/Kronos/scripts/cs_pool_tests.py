# -*- coding: utf-8 -*-
"""
cs_pool_tests.py  —  池子模型的实战测试套件

三个测试:
  1) cross_sectional_ic  — 截面 IC / RankIC / DA(沿用 cross_sectional_ic.py 同样的输出)
  2) top_k_selection     — Top-K 选股:Kronos 预测 Top-K vs 真实收益 Top-K 的命中率
  3) quintile_backtest   — Q1-Q5 分层:Kronos 排序后分 5 等分,看 Q1 vs Q5 的真实收益差

数据: finetune_csv/data/pool.csv (long-format multi-symbol)

使用:
  python scripts/cs_pool_tests.py \
      --pool-csv finetune_csv/data/pool.csv \
      --tokenizer finetune_csv/finetuned/pool_133_daily/tokenizer/best_model \
      --model finetune_csv/finetuned/pool_133_daily/basemodel/best_model \
      --start 2025-06-01 --end 2026-08-07 \
      --lookback 200 --pred-len 5 \
      --anchor-freq W --max-symbols 60 \
      --device cuda --run-tag pool_133_cs_v1
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
    p = argparse.ArgumentParser(description="Pool CS tests (IC + Top-K + Q1-Q5)")
    p.add_argument("--pool-csv", required=True)
    p.add_argument("--tokenizer", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--lookback", type=int, default=200)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--anchor-freq", default="W", choices=["B", "W", "M"])
    p.add_argument("--max-symbols", type=int, default=60)
    p.add_argument("--symbol-level", default="",
                   help="Filter by level (S/A/B+/压舱石); empty = all")
    p.add_argument("--device", default="cuda", choices=["cpu", "cuda"])
    p.add_argument("--max-context", type=int, default=200)
    p.add_argument("--sample-count", type=int, default=2)
    p.add_argument("--T", type=float, default=1.0)
    p.add_argument("--top-p", type=float, default=0.9)
    p.add_argument("--price-limit", type=float, default=0.10)
    p.add_argument("--top-k", type=int, default=10,
                   help="K for Top-K selection test")
    p.add_argument("--n-quintiles", type=int, default=5)
    p.add_argument("--out-dir", default="./outputs/cs")
    p.add_argument("--run-tag", default="pool_cs_v1")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------
def select_symbols(pool: pd.DataFrame, level: str, max_n: int) -> List[str]:
    cand = pool if not level else pool[pool.level == level]
    sym_counts = cand.groupby("symbol").size().sort_values(ascending=False)
    selected = sym_counts.head(max_n).index.tolist()
    return selected


def build_anchors(start: pd.Timestamp, end: pd.Timestamp, freq: str) -> List[pd.Timestamp]:
    if freq == "B":
        return list(pd.date_range(start=start, end=end, freq="B"))
    if freq == "W":
        return list(pd.date_range(start=start, end=end, freq="W-FRI"))
    return list(pd.date_range(start=start, end=end, freq="BM"))


# ---------------------------------------------------------------------------
# Scoring pass — emit long-format rows (date, symbol, pred_ret, real_ret, ...)
# ---------------------------------------------------------------------------
def score_pool(predictor: KronosPredictor,
               by_sym: Dict[str, pd.DataFrame],
               anchors: List[pd.Timestamp],
               lookback: int,
               pred_len: int,
               sample_count: int,
               T: float,
               top_p: float) -> pd.DataFrame:
    rows = []
    for ai, anchor in enumerate(anchors, 1):
        day_records = []
        for sym, df in by_sym.items():
            ctx = df[df.timestamps <= anchor]
            if len(ctx) < lookback:
                continue
            last_close = float(ctx["close"].iloc[-1])
            future = df[(df.timestamps > anchor)].head(pred_len)
            if len(future) < pred_len:
                continue
            real_close = float(future["close"].iloc[-1])
            x = ctx.iloc[-lookback:]
            try:
                x_ts = pd.Series(pd.DatetimeIndex(x["timestamps"]))
                y_ts = pd.Series(pd.bdate_range(
                    start=x["timestamps"].iloc[-1] + pd.Timedelta(days=1),
                    periods=pred_len))
                pred = predictor.predict(
                    df=x[["open", "high", "low", "close", "volume", "amount"]],
                    x_timestamp=x_ts, y_timestamp=y_ts,
                    pred_len=pred_len, T=T, top_p=top_p,
                    sample_count=sample_count, verbose=False,
                )
                pred_close = float(pred["close"].iloc[-1])
            except Exception as e:
                continue
            day_records.append({
                "date": anchor,
                "symbol": sym,
                "last_close": last_close,
                "pred_close": pred_close,
                "real_close": real_close,
                "pred_ret": pred_close / last_close - 1.0,
                "real_ret": real_close / last_close - 1.0,
            })
        if day_records:
            rows.extend(day_records)
        if ai % 10 == 0 or ai == len(anchors):
            n_today = len(day_records)
            n_total = len(rows)
            print(f"  [anchor {ai:3d}/{len(anchors)}] {anchor.date()}  "
                  f"n_today={n_today}  cum_rows={n_total}")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 1: cross-sectional IC
# ---------------------------------------------------------------------------
def test_cs_ic(df: pd.DataFrame, n_min: int = 5) -> pd.DataFrame:
    rows = []
    for date, sub in df.groupby("date"):
        if len(sub) < n_min:
            continue
        try:
            ic, _ = pearsonr(sub.pred_ret, sub.real_ret)
            ric, _ = spearmanr(sub.pred_ret, sub.real_ret)
        except Exception:
            ic, ric = np.nan, np.nan
        sign_pred = np.sign(sub.pred_ret.values)
        sign_real = np.sign(sub.real_ret.values)
        mask = np.abs(sub.real_ret.values) >= 0.01
        da = float(np.mean(sign_pred[mask] == sign_real[mask])) if mask.sum() else np.nan
        up = sub[sub.pred_ret > 0]
        dn = sub[sub.pred_ret < 0]
        up_cap = float((up.real_ret > 0).mean()) if len(up) else np.nan
        dn_cap = float((dn.real_ret < 0).mean()) if len(dn) else np.nan
        rows.append({
            "date": date, "n": len(sub),
            "ic": ic, "rank_ic": ric, "da": da,
            "up_cap": up_cap, "dn_cap": dn_cap,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 2: Top-K selection — hit rate between pred Top-K and real Top-K
# ---------------------------------------------------------------------------
def test_top_k(df: pd.DataFrame, K_list: List[int]) -> pd.DataFrame:
    """For each anchor date and each K, compute the overlap between the
    pred-top-K and real-top-K subsets (Jaccard / hit / DA / mean real ret)."""
    rows = []
    for date, sub in df.groupby("date"):
        if len(sub) < max(K_list) + 1:
            continue
        for K in K_list:
            if K > len(sub):
                continue
            pred_top = set(sub.nlargest(K, "pred_ret").symbol)
            real_top = set(sub.nlargest(K, "real_ret").symbol)
            pred_bot = set(sub.nsmallest(K, "pred_ret").symbol)
            real_bot = set(sub.nsmallest(K, "real_ret").symbol)
            hit_long = len(pred_top & real_top) / K
            hit_short = len(pred_bot & real_bot) / K
            hit_ls = ((pred_top & real_top) | (pred_bot & real_bot))
            ls_total = 2 * K
            hit_ls_rate = len(hit_ls) / ls_total if ls_total else 0
            rows.append({
                "date": date, "K": K, "n_pool": len(sub),
                "hit_long": hit_long,
                "hit_short": hit_short,
                "hit_ls": hit_ls_rate,
                "pred_top_mean_real_ret": float(sub[sub.symbol.isin(pred_top)].real_ret.mean()),
                "real_top_mean_real_ret": float(sub.nlargest(K, "real_ret").real_ret.mean()),
                "pool_mean_real_ret": float(sub.real_ret.mean()),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 3: Q1-Q5 quintile backtest — long-only top vs bottom quintile spread
# ---------------------------------------------------------------------------
def test_quintiles(df: pd.DataFrame, n_q: int = 5) -> pd.DataFrame:
    """Per anchor: rank by pred_ret, split into n_q equal buckets, compute
    mean real_ret per bucket. The Q1-vs-Q5 spread is the model's alpha."""
    rows = []
    for date, sub in df.groupby("date"):
        if len(sub) < n_q * 3:   # need enough for quintile split
            continue
        sub = sub.copy()
        sub["quintile"] = pd.qcut(sub.pred_ret.rank(method="first"),
                                  q=n_q, labels=False) + 1   # 1 = lowest pred
        for q, g in sub.groupby("quintile"):
            rows.append({
                "date": date, "quintile": int(q),
                "n": len(g),
                "mean_pred_ret": float(g.pred_ret.mean()),
                "mean_real_ret": float(g.real_ret.mean()),
                "median_real_ret": float(g.real_ret.median()),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------
def plot_ic(dm: pd.DataFrame, out: str):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(dm.date, dm.ic, "o-", color="tab:blue",
            label=f"IC  (mean={dm.ic.mean():+.3f})", lw=1.2, ms=4)
    ax.plot(dm.date, dm.rank_ic, "s-", color="tab:orange",
            label=f"RankIC  (mean={dm.rank_ic.mean():+.3f})", lw=1.2, ms=4)
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_title(f"Cross-sectional IC over time  —  {dm.da.notna().sum()} valid days")
    ax.set_xlabel("anchor date")
    ax.set_ylabel("IC / RankIC")
    ax.legend(loc="best")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_cum_ic(dm: pd.DataFrame, out: str):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(dm.date, dm.ic.cumsum(), "-", color="tab:blue", label="cum IC")
    ax.plot(dm.date, dm.rank_ic.cumsum(), "-", color="tab:orange", label="cum RankIC")
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_title(f"Cumulative IC  —  cum IC={dm.ic.cumsum().iloc[-1]:+.2f}, "
                 f"cum RankIC={dm.rank_ic.cumsum().iloc[-1]:+.2f}")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_da_hist(dm: pd.DataFrame, out: str):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(dm.da.dropna(), bins=15, color="tab:green", edgecolor="black", alpha=0.8)
    ax.axvline(0.5, color="red", linestyle="--", label="coin-flip = 50%")
    ax.axvline(dm.da.mean(), color="black", lw=1.5,
               label=f"mean = {dm.da.mean():.1%}")
    ax.set_xlabel("directional accuracy")
    ax.set_ylabel("count (days)")
    ax.set_title(f"DA distribution  —  {dm.da.notna().sum()} days, "
                 f"mean={dm.da.mean():.1%}")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_topk(topk: pd.DataFrame, K_list: List[int], out: str):
    """Bar chart: per-K mean hit_long / hit_short / hit_ls vs random baseline."""
    agg = topk.groupby("K").agg(
        hit_long=("hit_long", "mean"),
        hit_short=("hit_short", "mean"),
        hit_ls=("hit_ls", "mean"),
        n_days=("date", "count"),
    )
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(K_list))
    w = 0.25
    ax.bar(x - w, [agg.loc[k, "hit_long"] for k in K_list], w,
           label="hit long (top-K)", color="tab:green")
    ax.bar(x,     [agg.loc[k, "hit_short"] for k in K_list], w,
           label="hit short (bottom-K)", color="tab:red")
    ax.bar(x + w, [agg.loc[k, "hit_ls"] for k in K_list], w,
           label="hit L/S (top + bot)", color="tab:purple")
    # Random baselines: long = K/N, short = K/N, L/S = 2K/N
    ax.axhline(0.5, color="grey", lw=0.5, linestyle=":")
    ax.set_xticks(x)
    ax.set_xticklabels([f"K={k}" for k in K_list])
    ax.set_ylabel("mean hit rate")
    ax.set_title(f"Top-K selection hit rate  —  {agg['n_days'].iloc[0]} days "
                 f"(random baseline scales with K/N)")
    ax.legend(loc="best")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_quintiles(qd: pd.DataFrame, out: str):
    """Per quintile: mean real_ret with std band over time."""
    summary = qd.groupby("quintile")["mean_real_ret"].agg(["mean", "std", "count"])
    fig, ax = plt.subplots(figsize=(8, 4.5))
    qs = sorted(summary.index.tolist())
    means = [summary.loc[q, "mean"] * 100 for q in qs]
    stds  = [summary.loc[q, "std"] * 100 / np.sqrt(summary.loc[q, "count"]) for q in qs]
    ax.bar(qs, means, yerr=stds, capsize=4,
           color=["tab:red" if q == 1 else ("tab:green" if q == max(qs) else "tab:grey")
                  for q in qs])
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_xlabel("quintile (1 = lowest pred, 5 = highest pred)")
    ax.set_ylabel("mean realised 5d return (%)")
    ax.set_title("Q1-Q5 quintile: pred rank vs realised return")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_quintile_timeseries(qd: pd.DataFrame, out: str):
    """Per-quintile mean real_ret over time (cumulative)."""
    pivot = qd.pivot_table(index="date", columns="quintile", values="mean_real_ret")
    pivot = pivot.sort_index()
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for q in sorted(pivot.columns):
        cum = pivot[q].fillna(0).cumsum() * 100
        ax.plot(pivot.index, cum, label=f"Q{int(q)}", lw=1.2)
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_title("Quintile cumulative realised return  —  Q1 (lowest pred) → Q5 (highest pred)")
    ax.set_xlabel("anchor date")
    ax.set_ylabel("cumulative return (%)")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    out_dir = os.path.join(args.out_dir, args.run_tag)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[load] pool: {args.pool_csv}")
    pool = pd.read_csv(args.pool_csv, dtype={"symbol": str})
    pool["timestamps"] = pd.to_datetime(pool["timestamps"])
    print(f"[load] {len(pool)} rows, {pool.symbol.nunique()} symbols")

    selected = select_symbols(pool, args.symbol_level, args.max_symbols)
    print(f"[plan] selected {len(selected)} symbols (level={args.symbol_level or 'all'}):")
    for s in selected:
        n = int((pool.symbol == s).sum())
        print(f"   {s}  rows={n}")

    by_sym = {
        s: pool[pool.symbol == s].sort_values("timestamps").reset_index(drop=True)
        for s in selected
    }

    anchors = build_anchors(pd.Timestamp(args.start), pd.Timestamp(args.end), args.anchor_freq)
    print(f"[plan] {len(anchors)} anchor dates from {args.start} to {args.end}")

    print(f"[load] tokenizer: {args.tokenizer}")
    print(f"[load] model:     {args.model}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(
        model, tokenizer, device=args.device, max_context=args.max_context,
    )

    # ---- Single scoring pass, reused across all three tests ----
    print("\n[score] running inference pass over pool...")
    df = score_pool(
        predictor, by_sym, anchors,
        args.lookback, args.pred_len,
        args.sample_count, args.T, args.top_p,
    )
    df.to_csv(os.path.join(out_dir, "scored.csv"), index=False)
    print(f"[score] {len(df)} (date, symbol) pairs")

    # ---- Test 1: IC ----
    print("\n[test 1] cross-sectional IC...")
    dm = test_cs_ic(df)
    dm.to_csv(os.path.join(out_dir, "01_ic_daily.csv"), index=False)
    plot_ic(dm, os.path.join(out_dir, "01_ic_timeseries.png"))
    plot_cum_ic(dm, os.path.join(out_dir, "02_cum_ic.png"))
    plot_da_hist(dm, os.path.join(out_dir, "03_da_hist.png"))

    # ---- Test 2: Top-K ----
    print("\n[test 2] Top-K selection...")
    K_list = sorted({3, 5, 10, args.top_k, max(3, len(selected) // 3)})
    K_list = [k for k in K_list if 2 <= k <= len(selected) - 2]
    topk = test_top_k(df, K_list)
    topk.to_csv(os.path.join(out_dir, "04_topk_daily.csv"), index=False)
    plot_topk(topk, K_list, os.path.join(out_dir, "05_topk_bars.png"))

    # ---- Test 3: Q1-Q5 ----
    print("\n[test 3] quintile backtest...")
    qd = test_quintiles(df, args.n_quintiles)
    qd.to_csv(os.path.join(out_dir, "06_quintile_daily.csv"), index=False)
    plot_quintiles(qd, os.path.join(out_dir, "07_quintile_bars.png"))
    plot_quintile_timeseries(qd, os.path.join(out_dir, "08_quintile_cum.png"))

    # ---- Summary ----
    summary = {
        "args": vars(args),
        "selected_symbols": selected,
        "n_anchors_total": len(anchors),
        "n_anchors_with_data": int(dm.da.notna().sum()),
        "n_rows_total": int(len(df)),
        # IC
        "ic_mean": float(dm.ic.mean()),
        "ic_std": float(dm.ic.std()),
        "ic_ir": float(dm.ic.mean() / dm.ic.std()) if dm.ic.std() > 0 else np.nan,
        "rank_ic_mean": float(dm.rank_ic.mean()),
        "rank_ic_ir": float(dm.rank_ic.mean() / dm.rank_ic.std()) if dm.rank_ic.std() > 0 else np.nan,
        "da_mean": float(dm.da.mean()),
        # Top-K (per-K)
        "topk_by_K": {
            int(k): {
                "hit_long_mean": float(topk[topk.K == k].hit_long.mean()),
                "hit_short_mean": float(topk[topk.K == k].hit_short.mean()),
                "hit_ls_mean": float(topk[topk.K == k].hit_ls.mean()),
                "n_days": int((topk.K == k).sum()),
            }
            for k in K_list
        },
        # Q1-Q5
        "quintile_means_real_ret": {
            int(q): float(qd[qd.quintile == q].mean_real_ret.mean()) * 100
            for q in sorted(qd.quintile.unique())
        },
        "quintile_top_minus_bottom_pct": float(
            qd[qd.quintile == args.n_quintiles].mean_real_ret.mean() -
            qd[qd.quintile == 1].mean_real_ret.mean()
        ) * 100,
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Console output
    print("\n" + "=" * 60)
    print("=== HEADLINE ===")
    print(f"  selected: {len(selected)} symbols, "
          f"{len(anchors)} anchors, {len(df)} (date,symbol) pairs")
    print()
    print(f"[1] Cross-sectional IC")
    print(f"   IC:        mean={summary['ic_mean']:+.4f}  std={summary['ic_std']:.4f}  "
          f"IR={summary['ic_ir']:+.3f}")
    print(f"   RankIC:    mean={summary['rank_ic_mean']:+.4f}  IR={summary['rank_ic_ir']:+.3f}")
    print(f"   DA(mean):  {summary['da_mean']:.1%}")
    print()
    print(f"[2] Top-K selection  (random baseline = K/N)")
    for k, v in summary["topk_by_K"].items():
        rand_long = k / len(selected)
        rand_ls = 2 * k / len(selected)
        print(f"   K={k:2d}  hit_long={v['hit_long_mean']:.1%} (rand={rand_long:.1%})  "
              f"hit_short={v['hit_short_mean']:.1%} (rand={rand_long:.1%})  "
              f"L/S={v['hit_ls_mean']:.1%} (rand={rand_ls:.1%})  "
              f"days={v['n_days']}")
    print()
    print(f"[3] Q1-Q5 quintile  (mean realised 5d return, %)")
    for q, v in summary["quintile_means_real_ret"].items():
        bar = "#" * max(0, int(v * 4))
        print(f"   Q{q}  {v:+5.2f}%  {bar}")
    print(f"   Q{args.n_quintiles} - Q1 spread: {summary['quintile_top_minus_bottom_pct']:+.2f}%")
    print()
    print(f"[done] artefacts under: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())