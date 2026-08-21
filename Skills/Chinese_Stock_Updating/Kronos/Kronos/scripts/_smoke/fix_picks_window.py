# -*- coding: utf-8 -*-
"""Re-align smoke picks to the available data window (ends 2024-12-31)."""

import pandas as pd
from pathlib import Path

HERE = Path(__file__).parent
fp = HERE / "picks.csv"
df = pd.read_csv(fp, parse_dates=["date"])

# Last 10 weekly Fridays on or before 2024-12-31
end = pd.Timestamp("2024-12-31")
dates = pd.date_range(end=end, periods=10, freq="W-FRI")
symbols = sorted(df["symbol"].unique())
out = pd.DataFrame(
    [(d.date().isoformat(), s) for d in dates for s in symbols],
    columns=["date", "symbol"],
)
out.to_csv(fp, index=False)
print(f"[rewrite] {fp}  rows={len(out)}  weeks={len(dates)}")
print(out.head(10))