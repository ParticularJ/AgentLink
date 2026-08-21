# -*- coding: utf-8 -*-
"""
visualise_single_symbol.py  —  A-share-trader-grade single-symbol evaluation.

Evaluates Kronos-base predictions for one A-share as if you were sitting in
front of a trading desk: every plot answers one trading decision question.

Pipeline
--------
For a chosen (symbol, start, end):
  * Load the daily bars (前复权 qfq, from scripts/_smoke).
  * Pick N "anchor" dates evenly across the window, respecting a 5-day
    realisation gap (T+1 settlement).
  * At each anchor:
        - feed past `lookback` bars to Kronos
        - get next `pred_len` close predictions
        - clip by ±price_limit (A-share daily limit)
        - compute realised close at anchor + pred_len B-days
        - compute pred_ret / real_ret in percent
  * Run THREE baseline forecasters on the same anchors for comparison:
        - naive_last     : pred[t+h] = last_close            (random walk)
        - mean_revert    : pred[t+h] = 256-day moving avg
        - momentum_20    : pred[t+h] = last_close * (1 + ret_past_20)
  * Compute trader-grade metrics:
        - Directional Accuracy (DA):  sign(pred_ret) == sign(real_ret)
        - DA_excl_flat:               same, excluding |real_ret| < 1%
        - MAE_pct:                    mean |pred_ret - real_ret|
        - RMSE_pct:                   root mean squared error in pct pts
        - Hit@1pct:                   |pred_ret - real_ret| < 1%
        - upside_capture:             when pred_ret > 0, fraction real_ret > 0
        - downside_capture:           when pred_ret < 0, fraction real_ret < 0
        - residual skewness:          skew(real_ret - pred_ret)  (>=0 means
                                     model under-predicts upside, bullish skew)
  * Plot 7 figures and dump a JSON summary + per-anchor CSV.

Outputs (under outputs/vis/<run_tag>/)
  - 01_directional_accuracy.png    bar: Kronos vs 3 baselines on DA / DA_excl_flat
  - 02_pred_vs_real_scatter.png    scatter with quadrant counts + y=x; color by year
  - 03_path_overlay_last_anchor.png  Kronos pred path vs realised, last anchor,
                                   with ±limit bands
  - 04_path_overlay_grid.png       small-multiples of pred vs realised for first
                                   6 anchors; visually scan "model trend quality"
  - 05_error_distribution.png      residual histogram + KDE, Kronos vs baselines;
                                   prints skewness & tail mass in the title
  - 06_regime_summary.png          regime-tagged timeline: bull / bear / range
                                   markers + Kronos DA per regime
  - 07_cumulative_pnl_sim.png      toy "follow-the-prediction" cumulative log-returns
                                   for Kronos vs the 3 baselines
  - summary.json                   all numeric metrics
  - per_anchor.csv                 every anchor's pred/real returns + errors
  - report.html                    single-file index page linking all artefacts

Usage
-----
    python scripts/visualise_single_symbol.py \
        --symbol 600519 \
        --start 2023-06-01 --end 2024-12-31 \
        --lookback 256 --pred-len 5 \
        --anchor-freq W --max-anchors 30 \
        --device cuda --run-tag 600519_pro

Notes
-----
* `picks.csv` / qlib universe are NOT used here — single-symbol evaluation
  doesn't need a candidate pool.
* Bars are assumed 前复权 (qfq) by convention from build_smoke_data.py.
* A-share trading rules reflected:
      - daily ±price_limit (default ±10%; STAR/ChiNext ±20% — set via CLI)
      - T+1 settlement (we only look at close[t+pred_len])
      - no look-ahead: predicted bars are strictly after the anchor
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")  # headless

import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd

# Pick a CJK-capable font if available, fall back to default
_cjk_candidates = ["Noto Sans CJK SC", "Noto Sans CJK JP", "WenQuanYi Zen Hei",
                   "AR PL UMing CN", "SimHei", "Microsoft YaHei"]
_available = {f.name for f in fm.fontManager.ttflist}
for _name in _cjk_candidates:
    if _name in _available:
        plt.rcParams["font.sans-serif"] = [_name] + plt.rcParams["font.sans-serif"]
        plt.rcParams["axes.unicode_minus"] = False
        break

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: E402


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="A-share trader-grade single-symbol eval")
    p.add_argument("--symbol", required=True)
    p.add_argument("--csv-dir", default="./scripts/_smoke")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--lookback", type=int, default=256)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--anchor-freq", default="W", choices=["B", "W", "M"])
    p.add_argument("--max-anchors", type=int, default=30)
    p.add_argument("--sample-count", type=int, default=3)
    p.add_argument("--T", type=float, default=1.0)
    p.add_argument("--top-p", type=float, default=0.9)
    p.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base")
    p.add_argument("--model", default="NeoQuasar/Kronos-base")
    p.add_argument("--device", default="cuda", choices=["cpu", "cuda", "mps"])
    p.add_argument("--max-context", type=int, default=512)
    p.add_argument("--price-limit", type=float, default=0.10,
                   help="Daily price limit (0.10 main-board, 0.20 STAR/ChiNext)")
    p.add_argument("--flat-threshold", type=float, default=0.01,
                   help="|real_ret| below this is treated as flat / noise")
    p.add_argument("--out-dir", default="./outputs/vis")
    p.add_argument("--run-tag", default="single_symbol_pro")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_bars(symbol: str, csv_dir: str) -> pd.DataFrame:
    fp = os.path.join(csv_dir, f"{symbol}.csv")
    df = pd.read_csv(fp)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------
def apply_price_limit(path: np.ndarray, last_close: float, limit: float) -> np.ndarray:
    if limit <= 0:
        return path
    out = [float(last_close)]
    for x in path:
        prev = out[-1]
        lo, hi = prev * (1 - limit), prev * (1 + limit)
        out.append(float(np.clip(x, lo, hi)))
    return np.array(out[1:])


def kronos_predict_close(predictor: KronosPredictor,
                         ctx: pd.DataFrame,
                         pred_len: int,
                         sample_count: int,
                         T: float,
                         top_p: float) -> np.ndarray:
    x_ts = pd.Series(pd.DatetimeIndex(ctx["date"]))
    last_date = ctx["date"].iloc[-1]
    y_ts = pd.Series(pd.bdate_range(start=last_date + pd.Timedelta(days=1),
                                    periods=pred_len))
    out = predictor.predict(
        df=ctx[["open", "high", "low", "close", "volume", "amount"]],
        x_timestamp=x_ts,
        y_timestamp=y_ts,
        pred_len=pred_len,
        T=T,
        top_p=top_p,
        sample_count=sample_count,
        verbose=False,
    )
    return out["close"].values.astype(float)


def baseline_naive_last(ctx: pd.DataFrame) -> np.ndarray:
    """Random walk: pred[t+h] = last_close for every h."""
    last = float(ctx["close"].iloc[-1])
    return np.full(1, last)  # caller broadcasts


def baseline_mean_revert(ctx: pd.DataFrame, lookback: int = 60) -> np.ndarray:
    """Mean-revert: pred[t+h] = mean of last `lookback` closes."""
    return np.array([float(ctx["close"].iloc[-lookback:].mean())])


def baseline_momentum(ctx: pd.DataFrame, lookback: int = 20) -> np.ndarray:
    """20-day momentum: pred[t+h] = last * (1 + past-ret)."""
    last = float(ctx["close"].iloc[-1])
    past = float(ctx["close"].iloc[-1] / ctx["close"].iloc[-1 - lookback] - 1.0)
    return np.array([last * (1.0 + past)])


# ---------------------------------------------------------------------------
# Per-anchor evaluation record
# ---------------------------------------------------------------------------
@dataclass
class AnchorRecord:
    anchor: pd.Timestamp
    last_close: float
    real_close: float
    kronos_pred_close: float
    naive_pred_close: float
    mr_pred_close: float
    mom_pred_close: float
    kronos_path: np.ndarray
    real_path: np.ndarray
    kronos_ret: float
    real_ret: float
    naive_ret: float
    mr_ret: float
    mom_ret: float
    kronos_resid: float       # real_ret - kronos_ret   (positive = upside surprise)
    regime: str               # "bull" / "bear" / "range"

    def to_row(self) -> dict:
        d = asdict(self)
        d["anchor"] = self.anchor.strftime("%Y-%m-%d")
        # drop the heavy path columns from CSV
        d.pop("kronos_path")
        d.pop("real_path")
        return d


def classify_regime(ctx: pd.DataFrame, lookback: int = 60) -> str:
    """Classify the local trend using 60-day return + 20-day vol."""
    if len(ctx) < lookback + 1:
        return "range"
    past_ret = ctx["close"].iloc[-1] / ctx["close"].iloc[-lookback] - 1.0
    vol20 = ctx["close"].pct_change().iloc[-20:].std()
    if past_ret > 0.05 and vol20 < 0.025:
        return "bull"
    if past_ret < -0.05 and vol20 < 0.025:
        return "bear"
    return "range"


def build_anchor_records(bars: pd.DataFrame,
                         predictor: KronosPredictor,
                         anchor_dates: List[pd.Timestamp],
                         args) -> List[AnchorRecord]:
    out: List[AnchorRecord] = []
    for i, anchor_date in enumerate(anchor_dates, 1):
        ctx = bars[bars["date"] <= anchor_date].iloc[-args.lookback:]
        if len(ctx) < args.lookback:
            print(f"  [skip] {anchor_date.date()} ctx too short ({len(ctx)})")
            continue
        last_close = float(ctx["close"].iloc[-1])

        future = bars[(bars["date"] > anchor_date)].iloc[: args.pred_len]
        if len(future) < args.pred_len:
            print(f"  [skip] {anchor_date.date()} not enough future bars")
            continue
        real_path = future["close"].values.astype(float)
        real_close = float(real_path[-1])

        # ---- Kronos ----
        try:
            kpath = kronos_predict_close(
                predictor, ctx, args.pred_len,
                args.sample_count, args.T, args.top_p,
            )
            kpath = apply_price_limit(kpath, last_close, args.price_limit)
        except Exception as e:
            print(f"  [warn] {anchor_date.date()} Kronos failed: {e}")
            continue

        kronos_close = float(kpath[-1])

        # ---- baselines ----
        naive_close = float(baseline_naive_last(ctx)[0])
        mr_close = float(baseline_mean_revert(ctx, lookback=60)[0])
        mom_close = float(baseline_momentum(ctx, lookback=20)[0])

        rec = AnchorRecord(
            anchor=anchor_date,
            last_close=last_close,
            real_close=real_close,
            kronos_pred_close=kronos_close,
            naive_pred_close=naive_close,
            mr_pred_close=mr_close,
            mom_pred_close=mom_close,
            kronos_path=kpath,
            real_path=real_path,
            kronos_ret=kronos_close / last_close - 1.0,
            real_ret=real_close / last_close - 1.0,
            naive_ret=naive_close / last_close - 1.0,
            mr_ret=mr_close / last_close - 1.0,
            mom_ret=mom_close / last_close - 1.0,
            kronos_resid=real_close / last_close - 1.0 - (kronos_close / last_close - 1.0),
            regime=classify_regime(ctx),
        )
        out.append(rec)
        print(f"  [{i:3d}/{len(anchor_dates)}] {anchor_date.date()} "
              f"({rec.regime:5s})  real={real_close:8.2f}  "
              f"kronos={kronos_close:8.2f}  naive={naive_close:8.2f}  "
              f"real_ret={rec.real_ret:+.2%}  kronos_ret={rec.kronos_ret:+.2%}  "
              f"resid={rec.kronos_resid:+.2%}")
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def directional_accuracy(pred: np.ndarray, real: np.ndarray,
                         flat_thr: float) -> Dict[str, float]:
    """pred/real in raw units (e.g. returns), not percent."""
    mask = np.abs(real) >= flat_thr
    if mask.sum() == 0:
        return {"n_used": 0, "da": np.nan, "da_excl_flat": np.nan}
    sign_pred = np.sign(pred[mask])
    sign_real = np.sign(real[mask])
    da = float(np.mean(sign_pred == sign_real))
    return {"n_used": int(mask.sum()), "da": da, "da_excl_flat": da}


def metrics_block(records: List[AnchorRecord], pred_attr: str, real_attr: str,
                  flat_thr: float) -> Dict[str, float]:
    pred = np.array([getattr(r, pred_attr) for r in records])
    real = np.array([getattr(r, real_attr) for r in records])
    err = real - pred
    da = directional_accuracy(pred, real, flat_thr)
    # Hit@1pct: |err| < 1 percentage point
    hit_1pct = float(np.mean(np.abs(err) < flat_thr))
    # upside / downside capture
    up_mask = pred > 0
    dn_mask = pred < 0
    up_cap = float(np.mean(real[up_mask] > 0)) if up_mask.sum() else np.nan
    dn_cap = float(np.mean(real[dn_mask] < 0)) if dn_mask.sum() else np.nan
    # simple linear IC
    if len(records) >= 3 and np.std(pred) > 1e-9 and np.std(real) > 1e-9:
        from scipy.stats import pearsonr, spearmanr
        ic, _ = pearsonr(pred, real)
        ric, _ = spearmanr(pred, real)
    else:
        ic, ric = np.nan, np.nan
    return {
        "n": len(records),
        "MAE_pct": float(np.mean(np.abs(err)) * 100),
        "RMSE_pct": float(np.sqrt(np.mean(err ** 2)) * 100),
        "DA_excl_flat": da["da_excl_flat"],
        "Hit@1pct": hit_1pct,
        "IC": float(ic) if ic == ic else None,
        "RankIC": float(ric) if ric == ric else None,
        "upside_capture": up_cap,
        "downside_capture": dn_cap,
        "residual_skew": float(pd.Series(err).skew()),
        "pred_mean_pct": float(np.mean(pred) * 100),
        "real_mean_pct": float(np.mean(real) * 100),
        "pred_std_pct": float(np.std(pred) * 100),
        "real_std_pct": float(np.std(real) * 100),
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  [plot] {path}")


def plot_directional_accuracy(records: List[AnchorRecord], flat_thr: float, path: str):
    methods = [
        ("Kronos",      "kronos_ret", "real_ret"),
        ("NaiveLast",   "naive_ret",  "real_ret"),
        ("MeanRevert",  "mr_ret",     "real_ret"),
        ("Momentum20",  "mom_ret",    "real_ret"),
    ]
    names, da_all, da_filt = [], [], []
    for name, p, r in methods:
        m = metrics_block(records, p, r, flat_thr)
        names.append(name)
        da_all.append(np.nan)
        da_filt.append(m["DA_excl_flat"])
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(names))
    bars = ax.bar(x, [v if v == v else 0 for v in da_filt],
                  color=["tab:orange", "tab:grey", "tab:cyan", "tab:olive"])
    ax.axhline(0.5, color="red", linestyle="--", lw=1, label="coin-flip = 50%")
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylim(0, 1)
    ax.set_ylabel("directional accuracy (excl. flat)")
    ax.set_title(f"Directional accuracy vs baselines  "
                 f"(flat = |real_ret| < {flat_thr:.1%})")
    for b, v in zip(bars, da_filt):
        if v == v:
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.1%}",
                    ha="center", va="bottom", fontsize=10)
    ax.legend(loc="lower right")
    ax.grid(axis="y", alpha=0.3)
    _save(fig, path)


def plot_pred_vs_real_scatter(records: List[AnchorRecord], flat_thr: float, path: str):
    pred = np.array([r.kronos_ret for r in records]) * 100
    real = np.array([r.real_ret for r in records]) * 100
    years = pd.Series([r.anchor.year for r in records])
    fig, ax = plt.subplots(figsize=(7, 7))
    for yr, sub in pd.DataFrame({"x": pred, "y": real, "yr": years}).groupby("yr"):
        ax.scatter(sub["x"], sub["y"], s=42, alpha=0.75,
                   edgecolor="black", linewidth=0.4, label=str(yr))
    lo = float(min(pred.min(), real.min()))
    hi = float(max(pred.max(), real.max()))
    pad = (hi - lo) * 0.08
    ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad],
            color="grey", lw=0.8, linestyle="--", label="y = x")
    ax.axhline(0, color="grey", lw=0.5)
    ax.axvline(0, color="grey", lw=0.5)

    # quadrant counts (with |x|>flat to avoid flat-noise)
    mask = (np.abs(pred) > flat_thr * 100) & (np.abs(real) > flat_thr * 100)
    tp = int(((pred > 0) & (real > 0) & mask).sum())
    tn = int(((pred < 0) & (real < 0) & mask).sum())
    fp = int(((pred > 0) & (real < 0) & mask).sum())
    fn = int(((pred < 0) & (real > 0) & mask).sum())
    txt = (f"Q1 (TP,涨/涨)={tp}\nQ3 (TN,跌/跌)={tn}\n"
           f"Q2 (FP,假多)={fp}\nQ4 (FN,假空)={fn}")
    ax.text(0.02, 0.98, txt, transform=ax.transAxes,
            fontsize=9, va="top", ha="left",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.85))
    if len(records) >= 3:
        m = metrics_block(records, "kronos_ret", "real_ret", flat_thr)
        ax.set_title(f"Pred vs real 5-day return  |  "
                     f"IC={m['IC']:+.2f}  RankIC={m['RankIC']:+.2f}  "
                     f"DA={m['DA_excl_flat']:.1%}  n={m['n']}")
    ax.set_xlabel("predicted return (%)")
    ax.set_ylabel("realised return (%)")
    ax.legend(loc="lower right", title="anchor year")
    ax.grid(alpha=0.3)
    _save(fig, path)


def plot_path_overlay_last(records: List[AnchorRecord], symbol: str, args, path: str):
    if not records:
        return
    last = records[-1]
    fut_dates = pd.bdate_range(start=last.anchor + pd.Timedelta(days=1),
                               periods=args.pred_len)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    # realised
    ax.plot(fut_dates, last.real_path, marker="o", color="tab:blue",
            lw=2, label="realised close")
    # Kronos
    ax.plot(fut_dates, last.kronos_path, marker="x", color="tab:orange",
            lw=1.5, linestyle="--", label="Kronos prediction")
    # ±limit bands
    lc = last.last_close
    hi_band = [lc * (1 + args.price_limit) ** (i + 1) for i in range(args.pred_len)]
    lo_band = [lc * (1 - args.price_limit) ** (i + 1) for i in range(args.pred_len)]
    ax.fill_between(fut_dates, lo_band, hi_band,
                    color="grey", alpha=0.15, label=f"±{args.price_limit:.0%} daily band")
    ax.axhline(lc, color="grey", lw=0.8, linestyle=":",
               label=f"anchor close {lc:.2f}")
    ax.set_title(f"{symbol}  anchor={last.anchor.date()} ({last.regime})  "
                 f"real_ret={last.real_ret:+.2%}  kronos_ret={last.kronos_ret:+.2%}  "
                 f"residual={last.kronos_resid:+.2%}")
    ax.set_ylabel("close (前复权 qfq)")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    _save(fig, path)


def plot_path_overlay_grid(records: List[AnchorRecord], symbol: str, path: str,
                           n_show: int = 6):
    if not records:
        return
    sub = records[:n_show]
    n = len(sub)
    cols = 2
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(11, 3.0 * rows), sharex=False)
    axes = np.atleast_1d(axes).flatten()
    for ax, rec in zip(axes, sub):
        fut_dates = pd.bdate_range(start=rec.anchor + pd.Timedelta(days=1),
                                   periods=len(rec.real_path))
        ax.plot(fut_dates, rec.real_path, marker="o", color="tab:blue",
                lw=1.8, label="realised")
        ax.plot(fut_dates, rec.kronos_path, marker="x", color="tab:orange",
                lw=1.3, linestyle="--", label="Kronos")
        ax.axhline(rec.last_close, color="grey", lw=0.5, linestyle=":")
        ax.set_title(f"{rec.anchor.date()} ({rec.regime})  "
                     f"R={rec.real_ret:+.2%}  K={rec.kronos_ret:+.2%}",
                     fontsize=10)
        ax.grid(alpha=0.3)
        ax.tick_params(axis="x", rotation=30, labelsize=8)
    for ax in axes[len(sub):]:
        ax.set_visible(False)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, fontsize=9,
               bbox_to_anchor=(0.5, 1.02))
    fig.suptitle(f"{symbol}  —  {n} earliest anchors (pred vs realised 5-day path)",
                 y=1.06, fontsize=12)
    _save(fig, path)


def plot_error_distribution(records: List[AnchorRecord], flat_thr: float, path: str):
    methods = [
        ("Kronos",      "kronos_ret"),
        ("NaiveLast",   "naive_ret"),
        ("MeanRevert",  "mr_ret"),
        ("Momentum20",  "mom_ret"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    palette = {"Kronos": "tab:orange", "NaiveLast": "tab:grey",
               "MeanRevert": "tab:cyan", "Momentum20": "tab:olive"}
    summary_rows = []
    for name, attr in methods:
        pred = np.array([getattr(r, attr) for r in records])
        real = np.array([r.real_ret for r in records])
        err = (real - pred) * 100
        axes[0].hist(err, bins=15, alpha=0.45, label=f"{name} (skew={pd.Series(err).skew():+.2f})",
                     color=palette[name])
        # KDE via gaussian
        try:
            from scipy.stats import gaussian_kde
            xs = np.linspace(err.min() - 1, err.max() + 1, 200)
            axes[1].plot(xs, gaussian_kde(err)(xs), lw=1.8, label=name,
                         color=palette[name])
        except Exception:
            pass
        summary_rows.append((name, float(np.mean(err)), float(np.std(err)),
                             float(pd.Series(err).skew())))
    axes[0].axvline(0, color="red", lw=0.8, linestyle="--")
    axes[0].set_title("Residual histogram  (real - pred), pct pts")
    axes[0].set_xlabel("residual (pct pts)"); axes[0].set_ylabel("count")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)
    axes[1].axvline(0, color="red", lw=0.8, linestyle="--")
    axes[1].set_title("Residual KDE")
    axes[1].set_xlabel("residual (pct pts)"); axes[1].set_ylabel("density")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)
    # print a tiny inset table with mean/std/skew
    txt = "\n".join(
        f"{n}: μ={m:+.2f}  σ={s:.2f}  skew={k:+.2f}"
        for (n, m, s, k) in summary_rows
    )
    axes[1].text(0.98, 0.98, txt, transform=axes[1].transAxes,
                 fontsize=8, va="top", ha="right",
                 bbox=dict(boxstyle="round", facecolor="white", alpha=0.85))
    _save(fig, path)


def plot_regime_summary(records: List[AnchorRecord], symbol: str, path: str):
    if not records:
        return
    df = pd.DataFrame([{
        "anchor": r.anchor,
        "real_ret": r.real_ret,
        "kronos_ret": r.kronos_ret,
        "regime": r.regime,
        "correct": int(np.sign(r.kronos_ret) == np.sign(r.real_ret)
                       and abs(r.real_ret) >= 0.005),
    } for r in records])

    regimes = ["bull", "bear", "range"]
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=False,
                             gridspec_kw={"height_ratios": [2, 1]})
    ax_top, ax_bot = axes
    palette = {"bull": "tab:green", "bear": "tab:red", "range": "tab:grey"}
    for rg in regimes:
        sub = df[df.regime == rg]
        if sub.empty:
            continue
        ax_top.scatter(sub.anchor, sub.real_ret * 100, s=42,
                       color=palette[rg], edgecolor="black", linewidth=0.4,
                       label=f"real  ({rg}, n={len(sub)})")
        ax_top.scatter(sub.anchor, sub.kronos_ret * 100, s=42,
                       color=palette[rg], marker="x",
                       label=f"kronos ({rg})")

    ax_top.axhline(0, color="grey", lw=0.5)
    ax_top.set_ylabel("return (%)")
    ax_top.set_xlabel("anchor date")
    ax_top.set_title(f"{symbol}  —  regime-tagged predictions vs realisations")
    ax_top.legend(loc="upper left", fontsize=8, ncol=2)
    ax_top.grid(alpha=0.3)

    # DA per regime (bar)
    da_per_regime = df.groupby("regime")["correct"].mean().reindex(regimes)
    bars = ax_bot.bar(da_per_regime.index,
                      [0.0 if (v != v) else v for v in da_per_regime.values],
                      color=[palette[r] for r in da_per_regime.index],
                      edgecolor="black", linewidth=0.4)
    ax_bot.axhline(0.5, color="red", lw=1, linestyle="--", label="coin-flip")
    ax_bot.set_ylim(0, 1)
    ax_bot.set_ylabel("directional accuracy")
    ax_bot.set_xlabel("regime")
    ax_bot.legend(loc="upper right", fontsize=8)
    ax_bot.grid(axis="y", alpha=0.3)
    for b, v in zip(bars, da_per_regime.values):
        if v == v:
            ax_bot.text(b.get_x() + b.get_width() / 2, v + 0.01,
                        f"{v:.0%}", ha="center", va="bottom", fontsize=9)

    fig.autofmt_xdate()
    _save(fig, path)


def plot_cumulative_pnl(records: List[AnchorRecord], flat_thr: float, path: str):
    """Toy PnL: at each anchor, if predicted sign != 0 (above flat threshold)
    go long (sign(pred) units of the realised return over pred_len B-days).
    No transaction costs, no borrowing — just a signal-quality sketch."""
    methods = [
        ("Kronos",      "kronos_ret"),
        ("NaiveLast",   "naive_ret"),
        ("MeanRevert",  "mr_ret"),
        ("Momentum20",  "mom_ret"),
    ]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    palette = {"Kronos": "tab:orange", "NaiveLast": "tab:grey",
               "MeanRevert": "tab:cyan", "Momentum20": "tab:olive"}
    summary = []
    for name, attr in methods:
        ret_list, date_list = [], []
        cum = 1.0
        for r in records:
            p = getattr(r, attr)
            real = r.real_ret
            if abs(p) < flat_thr:
                position = 0.0
            else:
                position = float(np.sign(p))
            pnl = position * real
            cum *= (1.0 + pnl)
            ret_list.append(cum - 1.0)
            date_list.append(r.anchor)
        ax.plot(date_list, np.array(ret_list) * 100, lw=1.6,
                color=palette[name], label=f"{name}  cum={ret_list[-1]*100:+.1f}%")
        summary.append((name, ret_list[-1]))
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_title(f"Toy signal PnL  —  position = sign(pred) × realised "
                 f"(no costs, no leverage)\nflat threshold = |pred| < {flat_thr:.1%} → flat")
    ax.set_ylabel("cumulative return (%)")
    ax.set_xlabel("anchor date")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    _save(fig, path)


def write_report_html(out_dir: str, run_tag: str, summary: dict, symbol: str):
    rel = lambda fn: f"{fn}"  # files in same dir
    figs = [
        ("01_directional_accuracy.png", "Directional accuracy vs baselines"),
        ("02_pred_vs_real_scatter.png", "Pred vs real return scatter (quadrant counts)"),
        ("03_path_overlay_last_anchor.png", "Last anchor: predicted vs realised 5-day path"),
        ("04_path_overlay_grid.png", "Earliest 6 anchors — path-level inspection"),
        ("05_error_distribution.png", "Residual distribution: skew, tail mass"),
        ("06_regime_summary.png", "Regime-tagged predictions & per-regime accuracy"),
        ("07_cumulative_pnl_sim.png", "Toy cumulative PnL — Kronos vs baselines"),
    ]
    rows = []
    for fn, title in figs:
        rows.append(
            f'<figure><img src="{rel(fn)}" alt="{title}"><figcaption>{title}</figcaption></figure>'
        )
    metrics_table = "<table border=1 cellpadding=4 cellspacing=0>"
    metrics_table += "<tr><th>method</th><th>n</th><th>MAE%</th><th>RMSE%</th>"
    metrics_table += "<th>DA(excl flat)</th><th>Hit@1%</th><th>IC</th><th>RankIC</th>"
    metrics_table += "<th>up_cap</th><th>dn_cap</th><th>skew</th>"
    metrics_table += "<th>pred_mean%</th><th>real_mean%</th><th>pred_std%</th>"
    metrics_table += "<th>real_std%</th></tr>"
    for name, m in summary["metrics_by_method"].items():
        def f(k):
            v = m.get(k)
            return "—" if v is None or (isinstance(v, float) and v != v) else f"{v:.3f}"
        metrics_table += (
            f"<tr><td><b>{name}</b></td><td>{f('n')}</td><td>{f('MAE_pct')}</td>"
            f"<td>{f('RMSE_pct')}</td><td>{f('DA_excl_flat')}</td>"
            f"<td>{f('Hit@1pct')}</td><td>{f('IC')}</td><td>{f('RankIC')}</td>"
            f"<td>{f('upside_capture')}</td><td>{f('downside_capture')}</td>"
            f"<td>{f('residual_skew')}</td><td>{f('pred_mean_pct')}</td>"
            f"<td>{f('real_mean_pct')}</td><td>{f('pred_std_pct')}</td>"
            f"<td>{f('real_std_pct')}</td></tr>"
        )
    metrics_table += "</table>"
    args_disp = "<br>".join(f"<b>{k}</b>: {v}" for k, v in summary["args"].items())
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{symbol} — {run_tag}</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 1100px; margin: 24px auto; padding: 0 16px; }}
figure {{ margin: 24px 0; }}
img {{ max-width: 100%; border: 1px solid #ddd; }}
figcaption {{ font-weight: 600; margin-top: 6px; }}
table {{ border-collapse: collapse; margin: 16px 0; }}
th, td {{ padding: 4px 10px; font-size: 14px; }}
th {{ background: #f4f4f4; }}
h1 {{ margin-bottom: 4px; }}
small {{ color: #666; }}
</style></head><body>
<h1>{symbol} — single-symbol Kronos evaluation</h1>
<small>run-tag: {run_tag}  ·  bars: 前复权 qfq  ·  T+1 settlement</small>
<h2>Configuration</h2>
<p>{args_disp}</p>
<h2>Headline metrics</h2>
{metrics_table}
<h2>Plots</h2>
{''.join(rows)}
</body></html>"""
    fp = os.path.join(out_dir, run_tag, "report.html")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [html] {fp}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    out_root = os.path.join(args.out_dir, args.run_tag)
    os.makedirs(out_root, exist_ok=True)

    print(f"[load] symbol={args.symbol} bars={args.csv_dir}/{args.symbol}.csv")
    bars = load_bars(args.symbol, args.csv_dir)
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    bars = bars[(bars["date"] >= start) & (bars["date"] <= end)].reset_index(drop=True)
    if len(bars) < args.lookback + args.pred_len + 1:
        raise RuntimeError(
            f"not enough bars: have {len(bars)}, need "
            f">= {args.lookback + args.pred_len + 1}"
        )
    print(f"[load] {len(bars)} bars in [{start.date()}, {end.date()}]")

    print(f"[load] model={args.model} device={args.device}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(
        model, tokenizer, device=args.device, max_context=args.max_context,
    )

    # anchors must leave pred_len B-days in the future
    usable = bars.iloc[: len(bars) - args.pred_len]
    if args.anchor_freq == "B":
        step = max(1, len(usable) // args.max_anchors)
        anchors = usable["date"].iloc[args.lookback::step].tolist()
    elif args.anchor_freq == "W":
        anchors = usable.set_index("date").resample("W-FRI").first().dropna() \
            .index.tolist()
    else:
        anchors = usable.set_index("date").resample("BM").first().dropna() \
            .index.tolist()
    anchors = [a for a in anchors if a >= usable["date"].iloc[args.lookback]]
    if len(anchors) > args.max_anchors:
        idx = np.linspace(0, len(anchors) - 1, args.max_anchors).round().astype(int)
        anchors = [anchors[i] for i in idx]
    print(f"[run] {len(anchors)} anchors  (freq={args.anchor_freq})")

    records = build_anchor_records(bars, predictor, anchors, args)
    if not records:
        raise RuntimeError("no successful anchors — nothing to plot")

    # ---- metrics per method ----
    methods = [
        ("Kronos",      "kronos_ret"),
        ("NaiveLast",   "naive_ret"),
        ("MeanRevert",  "mr_ret"),
        ("Momentum20",  "mom_ret"),
    ]
    summary_metrics = {
        name: metrics_block(records, attr, "real_ret", args.flat_threshold)
        for name, attr in methods
    }
    # regime breakdown for Kronos
    regime_rows = {}
    for rg in ("bull", "bear", "range"):
        sub = [r for r in records if r.regime == rg]
        if sub:
            regime_rows[rg] = metrics_block(sub, "kronos_ret", "real_ret",
                                            args.flat_threshold)
    summary_metrics["Kronos_by_regime"] = regime_rows

    # ---- save CSV / JSON ----
    df = pd.DataFrame([r.to_row() for r in records])
    df.to_csv(os.path.join(out_root, "per_anchor.csv"), index=False)
    print(f"  [csv ] {os.path.join(out_root, 'per_anchor.csv')}")

    summary = {
        "args": vars(args),
        "symbol": args.symbol,
        "n_anchors_requested": len(anchors),
        "n_anchors_succeeded": len(records),
        "metrics_by_method": summary_metrics,
    }
    with open(os.path.join(out_root, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  [json] {os.path.join(out_root, 'summary.json')}")

    # ---- plots ----
    plot_directional_accuracy(records, args.flat_threshold,
                              os.path.join(out_root, "01_directional_accuracy.png"))
    plot_pred_vs_real_scatter(records, args.flat_threshold,
                              os.path.join(out_root, "02_pred_vs_real_scatter.png"))
    plot_path_overlay_last(records, args.symbol, args,
                           os.path.join(out_root, "03_path_overlay_last_anchor.png"))
    plot_path_overlay_grid(records, args.symbol,
                           os.path.join(out_root, "04_path_overlay_grid.png"))
    plot_error_distribution(records, args.flat_threshold,
                            os.path.join(out_root, "05_error_distribution.png"))
    plot_regime_summary(records, args.symbol,
                        os.path.join(out_root, "06_regime_summary.png"))
    plot_cumulative_pnl(records, args.flat_threshold,
                        os.path.join(out_root, "07_cumulative_pnl_sim.png"))

    write_report_html(args.out_dir, args.run_tag, summary, args.symbol)

    # ---- console summary ----
    def _sf(v, spec=".2f"):
        if v is None or (isinstance(v, float) and v != v):
            return "  nan"
        return format(v, spec)

    print("\n=== Headline ===")
    for name, m in summary_metrics.items():
        if name == "Kronos_by_regime":
            print(f"\n[{name}]")
            for rg, rm in m.items():
                print(f"  {rg:5s}: n={rm['n']:2d}  "
                      f"DA={_sf(rm['DA_excl_flat'], '.1%')}  "
                      f"MAE={_sf(rm['MAE_pct'])}  "
                      f"IC={_sf(rm['IC'], '+.2f')}")
            continue
        print(f"  {name:11s} n={m['n']:2d}  "
              f"DA={_sf(m['DA_excl_flat'], '.1%')}  "
              f"MAE={_sf(m['MAE_pct'])}%  "
              f"RMSE={_sf(m['RMSE_pct'])}%  "
              f"IC={_sf(m['IC'], '+.2f')}  RankIC={_sf(m['RankIC'], '+.2f')}  "
              f"up_cap={_sf(m['upside_capture'], '.1%')}  "
              f"dn_cap={_sf(m['downside_capture'], '.1%')}  "
              f"skew={_sf(m['residual_skew'], '+.2f')}")
    print(f"\n[done] artefacts under: {out_root}")


if __name__ == "__main__":
    main()