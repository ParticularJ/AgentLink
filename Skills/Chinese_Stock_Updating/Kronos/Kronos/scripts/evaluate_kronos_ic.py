# -*- coding: utf-8 -*-
"""
evaluate_kronos_ic.py

Daily cross-sectional backtest: rank-IC / IC / top-K hit-rate of Kronos-base
predictions against the user's daily stock-pick list.

Pipeline per rebalance day t:
    1. Build the daily candidate universe (your external recommendations).
    2. For each candidate, fetch the past `lookback` daily bars.
    3. Run Kronos-base autoregressive inference to get next `pred_len` bars.
    4. Compute the model's predicted forward return:
           pred_ret = (predicted_close[t+pred_len] / last_close) - 1
       (optionally clipped by the daily price-limit band).
    5. Compute the realised forward return:
           real_ret = (actual_close[t+realise_horizon] / last_close) - 1
    6. Cross-sectionally correlate pred_ret vs real_ret across candidates:
           IC    = Pearson  (pred, real)
           RankIC= Spearman (pred, real)
    7. Optionally report TopK hit-rate (fraction of realised-top-K that are
       also in predicted-top-K).

Notes
-----
- Uses the *official* `NeoQuasar/Kronos-base` + `Kronos-Tokenizer-base` weights,
  so this script evaluates whether *out-of-the-box* Kronos has any alpha for
  your daily recommendation screen. Do NOT use it as a stand-alone trading
  signal without further validation.
- Data source is pluggable: pass `--data-source qlib` (default, expects
  `~/.qlib/qlib_data/cn_data`) or `--data-source csv` (each symbol at
  `<csv_dir>/<symbol>.csv` with columns
  `date,open,high,low,close,volume,amount`).
- Output is written to `./outputs/eval/<run_tag>/`:
      ic_series.csv        IC / RankIC per day
      summary.json         mean/std/IR of IC, RankIC, hit-rate
      picks_<date>.csv     per-symbol pred vs real per day

Usage
-----
    python scripts/evaluate_kronos_ic.py \
        --start 2024-01-01 --end 2025-06-30 \
        --rebalance-freq W --pick-source qlib --universe csi300 \
        --lookback 400 --pred-len 5 --realise-horizon 5 \
        --top-k 10 --sample-count 3 \
        --run-tag kronos_csi300_w_2024_2025

    # CSV data source
    python scripts/evaluate_kronos_ic.py \
        --start 2024-01-01 --end 2025-06-30 \
        --pick-source csv --csv-pick-file my_picks.csv \
        --csv-dir data/csv --run-tag kronos_csv_demo
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

# Repo root on path so `from model import ...` works regardless of CWD.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: E402


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Kronos cross-sectional IC eval")
    p.add_argument("--start", required=True, help="Backtest start YYYY-MM-DD")
    p.add_argument("--end", required=True, help="Backtest end YYYY-MM-DD")
    p.add_argument("--rebalance-freq", default="W",
                   choices=["D", "W", "M"], help="Rebalance frequency")

    # Pick universe
    p.add_argument("--pick-source", default="qlib", choices=["qlib", "csv"])
    p.add_argument("--universe", default="csi300",
                   help="Qlib instrument, e.g. csi300 / csi800 / csi1000")
    p.add_argument("--qlib-provider", default="~/.qlib/qlib_data/cn_data")
    p.add_argument("--csv-pick-file", default=None,
                   help="CSV with columns [date, symbol, ...]; "
                        "if missing, all symbols in csv-dir are used.")
    p.add_argument("--csv-dir", default="./data/csv",
                   help="Directory of per-symbol daily CSVs (date,open,high,"
                        "low,close,volume,amount)")

    # Model settings
    p.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base")
    p.add_argument("--model", default="NeoQuasar/Kronos-base")
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    p.add_argument("--max-context", type=int, default=512)
    p.add_argument("--lookback", type=int, default=400,
                   help="Historical bars fed to Kronos")
    p.add_argument("--pred-len", type=int, default=5,
                   help="Number of forward bars Kronos predicts")
    p.add_argument("--sample-count", type=int, default=3,
                   help="Number of parallel samples averaged per stock")
    p.add_argument("--T", type=float, default=1.0)
    p.add_argument("--top-p", type=float, default=0.9)

    # Realisation
    p.add_argument("--realise-horizon", type=int, default=5,
                   help="Compare against actual return at t+realise_horizon. "
                        "Typically equals pred-len.")
    p.add_argument("--top-k", type=int, default=10,
                   help="Top-K used for hit-rate metric")
    p.add_argument("--price-limit", type=float, default=0.10,
                   help="A-share daily price-limit band (0.10 = ±10%%). "
                        "Applied to predicted closes before computing "
                        "pred_ret, to avoid unrealistic extrapolation.")
    p.add_argument("--max-symbols-per-day", type=int, default=80,
                   help="Cap to keep inference manageable")

    # Output
    p.add_argument("--out-dir", default="./outputs/eval")
    p.add_argument("--run-tag", default="kronos_ic_default")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def init_qlib(provider_uri: str):
    import qlib
    from qlib.config import REG_CN
    qlib.init(provider_uri=os.path.expanduser(provider_uri), region=REG_CN)


def load_daily_bars_qlib(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Pull daily OHLCV(+amount) for one symbol from Qlib."""
    from qlib.data import D
    fields = ["$open", "$close", "$high", "$low", "$volume", "$vwap"]
    df = D.features([symbol], fields, disk_cache=0)
    df = df.loc[symbol].reset_index()
    df = df.rename(columns={
        "datetime": "date",
        "$open": "open", "$close": "close", "$high": "high",
        "$low": "low", "$volume": "volume", "$vwap": "vwap"
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= start) & (df["date"] <= end)].sort_values("date")
    df["amount"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4 * df["volume"]
    return df[["date", "open", "high", "low", "close", "volume", "amount"]].reset_index(drop=True)


def load_daily_bars_csv(symbol: str, csv_dir: str) -> pd.DataFrame:
    fp = os.path.join(csv_dir, f"{symbol}.csv")
    df = pd.read_csv(fp)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def get_universe_symbols_qlib(instrument: str) -> List[str]:
    from qlib.data import D
    instruments = D.instruments(market=instrument, dump=True)
    return list(D.list_instruments(instruments, as_list=True))


def load_pick_schedule(args) -> pd.DataFrame:
    """
    Return a DataFrame indexed by rebalance date with column `symbol`.
    """
    if args.pick_source == "qlib":
        init_qlib(args.qlib_provider)
        symbols = get_universe_symbols_qlib(args.universe)
        trading_dates = pd.date_range(args.start, args.end, freq="B")
        if args.rebalance_freq == "W":
            dates = pd.date_range(args.start, args.end, freq="W-FRI")
        elif args.rebalance_freq == "M":
            dates = pd.date_range(args.start, args.end, freq="BM")
        else:
            dates = trading_dates
        rows = []
        for d in dates:
            for s in symbols:
                rows.append((d, s))
        sched = pd.DataFrame(rows, columns=["date", "symbol"])
    else:
        sched = pd.read_csv(args.csv_pick_file) if args.csv_pick_file else None
        if sched is None:
            # fall back to every CSV file in csv_dir
            syms = [f[:-4] for f in os.listdir(args.csv_dir) if f.endswith(".csv")]
            rows = []
            if args.rebalance_freq == "W":
                dates = pd.date_range(args.start, args.end, freq="W-FRI")
            elif args.rebalance_freq == "M":
                dates = pd.date_range(args.start, args.end, freq="BM")
            else:
                dates = pd.date_range(args.start, args.end, freq="B")
            for d in dates:
                for s in syms:
                    rows.append((d, s))
            sched = pd.DataFrame(rows, columns=["date", "symbol"])
        else:
            sched["date"] = pd.to_datetime(sched["date"])
    sched = sched.sort_values(["date", "symbol"]).reset_index(drop=True)
    if args.max_symbols_per_day > 0:
        sched = sched.groupby("date").head(args.max_symbols_per_day).reset_index(drop=True)
    return sched


# ---------------------------------------------------------------------------
# Kronos scoring
# ---------------------------------------------------------------------------

@dataclass
class ScoreResult:
    symbol: str
    date: pd.Timestamp
    last_close: float
    pred_close: float
    real_close: float
    pred_ret: float
    real_ret: float
    status: str  # "ok" / "skip_<reason>"


def apply_price_limit(pred_close_path: np.ndarray, last_close: float,
                      limit: float) -> np.ndarray:
    """Walk the predicted close path and clip each step by ±limit vs prev close."""
    if limit <= 0:
        return pred_close_path
    out = [float(last_close)]
    for x in pred_close_path:
        prev = out[-1]
        lo, hi = prev * (1 - limit), prev * (1 + limit)
        out.append(float(np.clip(x, lo, hi)))
    return np.array(out[1:])


def score_one_day(predictor: KronosPredictor,
                  df_hist: pd.DataFrame,
                  symbol: str,
                  day: pd.Timestamp,
                  lookback: int,
                  pred_len: int,
                  realise_horizon: int,
                  sample_count: int,
                  T: float,
                  top_p: float,
                  price_limit: float) -> Optional[ScoreResult]:
    """Score a single (symbol, day). Returns None if data insufficient."""
    if len(df_hist) < lookback + realise_horizon + 1:
        return None

    x_df = df_hist.iloc[-lookback:][["open", "high", "low", "close", "volume", "amount"]]
    x_ts = pd.DatetimeIndex(x_df["date"])

    # Future prediction timestamps: daily business days after the last bar.
    last_date = x_df["date"].iloc[-1]
    y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=pred_len)

    pred_df = predictor.predict(
        df=x_df[["open", "high", "low", "close", "volume", "amount"]],
        x_timestamp=x_ts,
        y_timestamp=pd.Series(y_ts),
        pred_len=pred_len,
        T=T,
        top_p=top_p,
        sample_count=sample_count,
        verbose=False,
    )

    last_close = float(x_df["close"].iloc[-1])
    pred_close_path = pred_df["close"].values.astype(float)
    pred_close_path = apply_price_limit(pred_close_path, last_close, price_limit)
    pred_close = float(pred_close_path[-1])

    # Realised close: the row at t + realise_horizon in the *same* df_hist
    real_idx = len(df_hist) - 1 + realise_horizon
    if real_idx >= len(df_hist):
        return None
    real_close = float(df_hist["close"].iloc[real_idx])

    pred_ret = pred_close / last_close - 1.0
    real_ret = real_close / last_close - 1.0

    return ScoreResult(
        symbol=symbol, date=day, last_close=last_close,
        pred_close=pred_close, real_close=real_close,
        pred_ret=pred_ret, real_ret=real_ret, status="ok",
    )


# ---------------------------------------------------------------------------
# Cross-sectional metrics
# ---------------------------------------------------------------------------

def daily_metrics(rows: List[ScoreResult], top_k: int) -> dict:
    if len(rows) < 3:
        return {"n": len(rows), "ic": np.nan, "rank_ic": np.nan, f"top{top_k}_hit": np.nan}
    pred = np.array([r.pred_ret for r in rows])
    real = np.array([r.real_ret for r in rows])
    if np.std(pred) < 1e-9 or np.std(real) < 1e-9:
        return {"n": len(rows), "ic": np.nan, "rank_ic": np.nan, f"top{top_k}_hit": np.nan}
    ic, _ = pearsonr(pred, real)
    ric, _ = spearmanr(pred, real)
    k = min(top_k, len(rows))
    pred_top = set(np.array([r.symbol for r in rows])[np.argsort(-pred)[:k]])
    real_top = set(np.array([r.symbol for r in rows])[np.argsort(-real)[:k]])
    hit = len(pred_top & real_top) / k
    return {"n": len(rows), "ic": ic, "rank_ic": ric, f"top{k}_hit": hit}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    out_dir = os.path.join(args.out_dir, args.run_tag)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[load] model={args.model} device={args.device}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(
        model, tokenizer,
        device=args.device,
        max_context=args.max_context,
    )

    print(f"[load] pick schedule (source={args.pick_source})")
    schedule = load_pick_schedule(args)
    days = sorted(schedule["date"].unique())
    print(f"[load] {len(schedule)} (date, symbol) pairs across {len(days)} rebalance days")

    # Pre-load all bars (one fetch per symbol keeps the hot loop tight).
    symbol_bars: dict[str, pd.DataFrame] = {}
    if args.pick_source == "qlib":
        for s in schedule["symbol"].unique():
            symbol_bars[s] = load_daily_bars_qlib(s, args.start, args.end)
    else:
        for s in schedule["symbol"].unique():
            symbol_bars[s] = load_daily_bars_csv(s, args.csv_dir)

    ic_records: List[dict] = []
    all_rows: List[ScoreResult] = []

    for i, day in enumerate(days):
        day_rows: List[ScoreResult] = []
        day_picks = schedule[schedule["date"] == day]
        for _, row in day_picks.iterrows():
            sym = row["symbol"]
            df_hist = symbol_bars.get(sym)
            if df_hist is None or df_hist.empty:
                continue
            # Use bars up to `day` as the lookback context.
            df_ctx = df_hist[df_hist["date"] <= day].copy()
            try:
                sr = score_one_day(
                    predictor, df_ctx, sym, pd.Timestamp(day),
                    args.lookback, args.pred_len, args.realise_horizon,
                    args.sample_count, args.T, args.top_p, args.price_limit,
                )
            except Exception as e:
                sr = None
            if sr is not None:
                day_rows.append(sr)
                all_rows.append(sr)

        m = daily_metrics(day_rows, args.top_k)
        m["date"] = pd.Timestamp(day).strftime("%Y-%m-%d")
        ic_records.append(m)
        print(f"[{i+1:>4}/{len(days)}] {m['date']}  n={m['n']:>3}  "
              f"IC={m['ic']:+.3f}  RankIC={m['rank_ic']:+.3f}  "
              f"Top{args.top_k}Hit={m[f'top{args.top_k}_hit']:.2f}")

        # Per-day dump
        if day_rows:
            pd.DataFrame([r.__dict__ for r in day_rows]).to_csv(
                os.path.join(out_dir, f"picks_{m['date']}.csv"), index=False)

    ic_df = pd.DataFrame(ic_records)
    ic_df.to_csv(os.path.join(out_dir, "ic_series.csv"), index=False)

    summary = {
        "args": vars(args),
        "n_days": len(ic_records),
        "ic_mean": float(ic_df["ic"].mean()),
        "ic_std": float(ic_df["ic"].std()),
        "ic_ir": float(ic_df["ic"].mean() / (ic_df["ic"].std() + 1e-9)),
        "rank_ic_mean": float(ic_df["rank_ic"].mean()),
        "rank_ic_std": float(ic_df["rank_ic"].std()),
        "rank_ic_ir": float(ic_df["rank_ic"].mean() / (ic_df["rank_ic"].std() + 1e-9)),
        f"top{args.top_k}_hit_mean": float(ic_df[f"top{args.top_k}_hit"].mean()),
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print("\n=========== SUMMARY ===========")
    print(json.dumps(summary, indent=2, default=str))
    print(f"Artefacts saved under: {out_dir}")


if __name__ == "__main__":
    main()