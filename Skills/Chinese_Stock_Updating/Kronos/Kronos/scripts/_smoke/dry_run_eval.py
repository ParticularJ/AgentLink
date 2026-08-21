# -*- coding: utf-8 -*-
"""
Offline dry-run for evaluate_kronos_ic.py
Stub KronosPredictor.predict() with a noisy linear extrapolation so we can
verify the data flow / metrics / IO without downloading the model.
Run:
    /home/jarvis/miniconda3/envs/kronos/bin/python \
        scripts/_smoke/dry_run_eval.py
"""

import json
import os
import sys
from typing import List

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# Re-import the metric / scoring functions from the real eval module.
from evaluate_kronos_ic import (
    apply_price_limit, daily_metrics, ScoreResult, load_pick_schedule,
    load_daily_bars_csv,
)
from dataclasses import dataclass

SMOKE = os.path.join(ROOT, "scripts", "_smoke")
OUT_DIR = os.path.join(SMOKE, "outputs", "_smoke_dryrun")
os.makedirs(OUT_DIR, exist_ok=True)


# ---- Stub predictor (does NOT need torch) ---------------------------------

class StubPredictor:
    """Predict by noisy linear extrapolation of last 60 closes."""
    def __init__(self, seed=0, noise_std=0.01):
        self.rng = np.random.default_rng(seed)
        self.noise_std = noise_std

    def predict(self, df, x_timestamp, y_timestamp, pred_len, **kw):
        last = df["close"].values[-60:]
        slope = (last[-1] - last[0]) / max(len(last) - 1, 1)
        path = []
        cur = float(last[-1])
        for _ in range(pred_len):
            cur = cur * (1 + slope / max(cur, 1e-9) + self.rng.normal(0, self.noise_std))
            path.append(cur)
        # Synth full OHLCV+amount
        out = pd.DataFrame({
            "open": path,
            "high": [p * 1.005 for p in path],
            "low":  [p * 0.995 for p in path],
            "close": path,
            "volume": np.zeros(pred_len),
            "amount": np.zeros(pred_len),
        }, index=y_timestamp)
        return out


def score_one_day(df_hist, day, predictor, lookback, pred_len, realise_horizon, price_limit):
    if len(df_hist) < lookback + realise_horizon + 1:
        return None
    x_df = df_hist.iloc[-lookback:][["open", "high", "low", "close", "volume", "amount"]]
    x_ts = pd.DatetimeIndex(x_df["date"])
    last_date = x_df["date"].iloc[-1]
    y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=pred_len)
    pred_df = predictor.predict(
        df=x_df[["open", "high", "low", "close", "volume", "amount"]],
        x_timestamp=x_ts,
        y_timestamp=pd.Series(y_ts),
        pred_len=pred_len,
    )
    last_close = float(x_df["close"].iloc[-1])
    pred_close_path = apply_price_limit(pred_df["close"].values.astype(float), last_close, price_limit)
    pred_close = float(pred_close_path[-1])
    real_idx = len(df_hist) - 1 + realise_horizon
    if real_idx >= len(df_hist):
        return None
    real_close = float(df_hist["close"].iloc[real_idx])
    return ScoreResult(
        symbol="?", date=day, last_close=last_close,
        pred_close=pred_close, real_close=real_close,
        pred_ret=pred_close / last_close - 1.0,
        real_ret=real_close / last_close - 1.0,
        status="ok",
    )


def main():
    # Inline arg parsing (no torch needed)
    lookback, pred_len, realise_horizon, top_k, price_limit = 256, 5, 5, 3, 0.10
    schedule = load_pick_schedule.__wrapped__ if hasattr(load_pick_schedule, "__wrapped__") else None
    # Build a simple arg object
    @dataclass
    class A:
        pick_source: str = "csv"
        csv_pick_file: str = os.path.join(SMOKE, "picks.csv")
        csv_dir: str = SMOKE
        max_symbols_per_day: int = 80
        start: str = "2024-09-01"
        end: str = "2024-12-31"
        rebalance_freq: str = "W"
        universe: str = "csi300"
        qlib_provider: str = ""
    args = A()

    sched = load_pick_schedule(args)
    syms = sched["symbol"].unique().tolist()
    bars = {s: load_daily_bars_csv(s, args.csv_dir) for s in syms}

    pred = StubPredictor(seed=0, noise_std=0.005)
    ic_records: List[dict] = []
    days = sorted(sched["date"].unique())

    for day in days:
        day_rows = []
        for _, row in sched[sched["date"] == pd.Timestamp(day)].iterrows():
            sym = row["symbol"]
            ctx = bars[sym][bars[sym]["date"] <= pd.Timestamp(day)].copy()
            # set symbol on ScoreResult
            sr = score_one_day(ctx, pd.Timestamp(day), pred, lookback, pred_len, realise_horizon, price_limit)
            if sr is not None:
                sr.symbol = sym
                day_rows.append(sr)
        m = daily_metrics(day_rows, top_k)
        m["date"] = pd.Timestamp(day).strftime("%Y-%m-%d")
        ic_records.append(m)
        print(f"{m['date']}  n={m['n']:>3}  IC={m['ic']:+.3f}  "
              f"RankIC={m['rank_ic']:+.3f}  Top{top_k}Hit={m[f'top{top_k}_hit']:.2f}")

    ic_df = pd.DataFrame(ic_records)
    ic_df.to_csv(os.path.join(OUT_DIR, "ic_series.csv"), index=False)
    summary = {
        "n_days": len(ic_records),
        "ic_mean": float(ic_df["ic"].mean()),
        "ic_std": float(ic_df["ic"].std()),
        "rank_ic_mean": float(ic_df["rank_ic"].mean()),
        "rank_ic_std": float(ic_df["rank_ic"].std()),
        f"top{top_k}_hit_mean": float(ic_df[f"top{top_k}_hit"].mean()),
        "note": "DRY RUN - stub predictor",
    }
    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("\n=== DRY-RUN SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"artefacts: {OUT_DIR}")


if __name__ == "__main__":
    main()