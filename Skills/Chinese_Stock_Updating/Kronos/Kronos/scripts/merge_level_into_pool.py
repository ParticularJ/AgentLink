# -*- coding: utf-8 -*-
"""
merge_level_into_pool.py

Enriches finetune_csv/data/pool.csv with the watchlist 'level' (S/A/B+/压舱石)
so the multi-symbol dataset can sample with level-aware weights.

Usage:
    python scripts/merge_level_into_pool.py
"""

import os
import pandas as pd
import yaml


WATCHLIST = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_stock_pool/watchlist.yaml"
POOL_CSV = "finetune_csv/data/pool.csv"
POOL_OUT = "finetune_csv/data/pool.csv"   # overwrite in place


def main() -> int:
    with open(WATCHLIST, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    code2level = {}
    for sector, info in doc["watchlist"].items():
        level = info.get("level", "")
        for role in ("core", "focus"):
            for entry in info.get(role, []) or []:
                if not isinstance(entry, list) or len(entry) != 2:
                    continue
                # Normalise to both str6 and int for robust matching.
                code_str = str(entry[1]).zfill(6)
                code_int = int(entry[1])
                rank = {"压舱石": 0, "B+": 1, "A": 2, "S": 3}.get(level, 1)
                for k in (code_str, code_int):
                    prev = code2level.get(k)
                    if prev is None or rank > prev[0]:
                        code2level[k] = (rank, level)
    print(f"[load] {len(code2level)} symbol→level mappings from watchlist")

    # Read pool.csv forcing `symbol` to string so we keep leading zeros.
    pool = pd.read_csv(POOL_CSV, dtype={"symbol": str})
    if "level" in pool.columns:
        pool = pool.drop(columns=["level"])
        print("[reset] dropping pre-existing empty 'level' column")

    pool["level"] = pool["symbol"].map(lambda c: code2level.get(c, (None, ""))[1])
    n_with = pool["level"].notna().sum()
    print(f"[merge] {n_with}/{len(pool)} rows have a level assigned")
    pool.to_csv(POOL_OUT, index=False)
    print(f"[done] {POOL_OUT} updated, distribution:")
    print(pool["level"].value_counts(dropna=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())