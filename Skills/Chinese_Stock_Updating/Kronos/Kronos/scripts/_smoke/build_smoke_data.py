# -*- coding: utf-8 -*-
"""
Smoke test data builder.

Fetches daily K-line for a handful of A-share symbols via akshare and writes
one CSV per symbol with the exact columns expected by
`evaluate_kronos_ic.py` (csv source):

    date,open,high,low,close,volume,amount

Also writes a small `picks.csv` with columns: date,symbol
covering the most recent N weekly rebalance dates.
"""

import os
import time
import pandas as pd
import akshare as ak

SYMBOLS = ["000001", "600519", "000858", "002594", "600036"]
END_DATE = "20250101"
START_DATE = "20220101"
OUT_DIR = os.path.join(os.path.dirname(__file__))
N_WEEKS = 10  # 10 recent weekly rebalance dates


def fetch_one(symbol: str) -> pd.DataFrame:
    last_err = None
    for attempt in range(1, 4):
        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=START_DATE,
                end_date=END_DATE,
                adjust="qfq",  # forward-adjusted; remove if you want raw
            )
            if df is not None and not df.empty:
                break
        except Exception as e:
            last_err = e
            time.sleep(1.5)
    if df is None or df.empty:
        raise RuntimeError(f"fetch failed for {symbol}: {last_err}")

    df = df.rename(columns={
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
        "成交额": "amount",
    })
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        df[c] = (
            df[c].astype(str).str.replace(",", "", regex=False)
            .replace({"--": None, "": None})
        )
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[["date", "open", "high", "low", "close", "volume", "amount"]] \
        .sort_values("date").reset_index(drop=True)
    # Fix bad opens
    bad = (df["open"] == 0) | df["open"].isna()
    if bad.any():
        df.loc[bad, "open"] = df["close"].shift(1)
        df["open"] = df["open"].fillna(df["close"])
    # Fix missing amount
    if df["amount"].isna().all() or (df["amount"] == 0).all():
        df["amount"] = df["close"] * df["volume"]
    df = df.dropna().reset_index(drop=True)
    return df


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for sym in SYMBOLS:
        fp = os.path.join(OUT_DIR, f"{sym}.csv")
        if os.path.exists(fp) and os.path.getsize(fp) > 1000:
            print(f"[skip] {sym} exists -> {fp}")
            continue
        print(f"[fetch] {sym} ...")
        df = fetch_one(sym)
        df.to_csv(fp, index=False)
        print(f"  -> {fp}  rows={len(df)}  "
              f"range={df['date'].min().date()} ~ {df['date'].max().date()}")

    # Pick schedule: every Friday in the most recent N weeks
    end = pd.Timestamp.today().normalize()
    weekly = pd.date_range(end=end, periods=N_WEEKS, freq="W-FRI")
    picks = pd.DataFrame(
        [(d.date().isoformat(), s) for d in weekly for s in SYMBOLS],
        columns=["date", "symbol"],
    )
    picks_fp = os.path.join(OUT_DIR, "picks.csv")
    picks.to_csv(picks_fp, index=False)
    print(f"[picks] {picks_fp}  rows={len(picks)}  weeks={N_WEEKS}")


if __name__ == "__main__":
    main()