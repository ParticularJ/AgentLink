# -*- coding: utf-8 -*-
"""
build_pool_csv.py

Reads the trader watchlist YAML and pulls daily OHLCV(+amount) for every
symbol via baostock, producing:

  finetune_csv/data/pool.csv         — long-format CSV with columns
                                       [symbol, timestamps, open, high,
                                        low, close, volume, amount]
  finetune_csv/data/pool_meta.json   — per-symbol metadata:
                                       name, sector, level, n_rows,
                                       first_date, last_date, status

Filtering rules
---------------
* Skip symbols with < MIN_ROWS daily bars (default 800 ≈ 3 years).
* Skip symbols where baostock returns no data.
* Adjustflag='2' → 前复权 (qfq), matching scripts/_smoke build convention.

Concurrency
-----------
baostock is network-bound; we fan out with a ThreadPoolExecutor and write
each successful frame to disk incrementally so a Ctrl-C mid-run doesn't
lose progress. Re-running the script skips already-fetched symbols.

Usage
-----
    python scripts/build_pool_csv.py \
        --watchlist /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_stock_pool/watchlist.yaml \
        --out-dir finetune_csv/data \
        --start 2020-01-01 --end 2026-08-09 \
        --min-rows 800 --workers 16
"""

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import pandas as pd
import yaml


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build pooled daily-bar CSV from a watchlist YAML.")
    p.add_argument("--watchlist", required=True)
    p.add_argument("--out-dir", default="finetune_csv/data")
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default="2026-08-09")
    p.add_argument("--min-rows", type=int, default=800)
    p.add_argument("--workers", type=int, default=4,
                   help="Concurrent baostock workers (one bs.login per worker)")
    p.add_argument("--resume", action="store_true", default=True,
                   help="Skip symbols already present in pool.csv (default on)")
    p.add_argument("--no-resume", dest="resume", action="store_false")
    return p.parse_args()


def parse_watchlist(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    items: List[Dict] = []
    for sector, info in doc["watchlist"].items():
        level = info.get("level", "")
        for role in ("core", "focus"):
            for entry in info.get(role, []) or []:
                if not isinstance(entry, list) or len(entry) != 2:
                    continue
                name, code = entry[0], str(entry[1]).zfill(6)
                items.append({
                    "sector": sector, "level": level,
                    "name": name, "code": code, "role": role,
                })
    seen, deduped = set(), []
    for it in items:
        key = (it["sector"], it["code"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped


def to_baostock_code(code: str) -> str:
    """6-digit A-share code → baostock 'sh.600000' / 'sz.000001' / 'bj.83xxxx'."""
    if code.startswith(("60", "68", "90", "11", "13")):
        return f"sh.{code}"
    if code.startswith(("00", "30", "20")):
        return f"sz.{code}"
    if code.startswith(("8", "4", "92")):
        return f"bj.{code}"
    return f"sh.{code}"  # fallback


def fetch_one(bs, code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch daily bars for one symbol. Each thread holds its own bs session."""
    bs_code = to_baostock_code(code)
    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,open,high,low,close,volume,amount",
        start_date=start,
        end_date=end,
        adjustflag="2",
        frequency="d",
    )
    if rs.error_code != "0":
        return None
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=rs.fields)
    df = df.rename(columns={"date": "timestamps"})
    for c in ("open", "high", "low", "close", "volume", "amount"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna()
    if df.empty:
        return None
    df["timestamps"] = pd.to_datetime(df["timestamps"]).dt.strftime("%Y-%m-%d 15:00")
    return df[["timestamps", "open", "high", "low", "close", "volume", "amount"]]


def fetch_with_session(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Thread entry point: each worker creates its own baostock session."""
    import baostock as bs
    lg = bs.login()
    if lg.error_code != "0":
        return None
    try:
        return fetch_one(bs, code, start, end)
    finally:
        bs.logout()


def main() -> int:
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    pool_csv = os.path.join(args.out_dir, "pool.csv")
    meta_json = os.path.join(args.out_dir, "pool_meta.json")

    items = parse_watchlist(args.watchlist)
    print(f"[load] watchlist: {len(items)} unique (sector, code) entries")

    # ---- resume support: load existing meta + seen symbols ----
    meta: Dict[str, Dict] = {}
    seen_codes: set = set()
    if args.resume and os.path.exists(meta_json):
        try:
            with open(meta_json, "r", encoding="utf-8") as f:
                existing = json.load(f)
            meta = existing.get("symbols", {})
            seen_codes = {c for c, m in meta.items() if m.get("status") == "ok"}
            print(f"[resume] {len(seen_codes)} ok symbols already in pool_meta.json")
        except Exception as e:
            print(f"[resume] failed to read {meta_json}: {e}")

    pending = [it for it in items if it["code"] not in seen_codes]
    print(f"[plan] {len(pending)} symbols to fetch ({args.workers} workers)")

    if not pending:
        print("[done] nothing to fetch")
        return 0

    # ---- concurrent fetch ----
    lock = threading.Lock()
    completed = 0
    n_ok = n_skip_short = n_fail = 0

    def worker(it: Dict) -> tuple:
        code = it["code"]
        df = fetch_with_session(code, args.start, args.end)
        if df is not None:
            per_fp = os.path.join(args.out_dir, f"_per_symbol_{code}.csv")
            try:
                df.to_csv(per_fp, index=False)
            except Exception:
                pass
        return it, df

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(worker, it) for it in pending]
        for fut in as_completed(futures):
            it, df = fut.result()
            code = it["code"]
            if df is None:
                status = "fail"
                nrows = 0
                first = last = None
                n_fail += 1
            elif len(df) < args.min_rows:
                status = "too_short"
                nrows = int(len(df))
                first = str(df["timestamps"].iloc[0])
                last = str(df["timestamps"].iloc[-1])
                n_skip_short += 1
            else:
                status = "ok"
                nrows = int(len(df))
                first = str(df["timestamps"].iloc[0])
                last = str(df["timestamps"].iloc[-1])
                n_ok += 1

            with lock:
                meta[code] = {
                    "name": it["name"], "sector": it["sector"], "level": it["level"],
                    "role": it["role"], "n_rows": nrows,
                    "first_date": first, "last_date": last, "status": status,
                }
                completed += 1
                # Periodically flush
                if completed % 10 == 0 or completed == len(pending):
                    _flush(args.out_dir, meta, items)
                print(f"  [{completed:3d}/{len(pending)}] {code} {it['name']:8s} "
                      f"({it['sector']}) → {status:9s} ({nrows} rows)")

    # ---- final flush ----
    _flush(args.out_dir, meta, items)
    print(f"\n[done] ok={n_ok}  too_short={n_skip_short}  fail={n_fail}")
    print(f"[done] pool.csv → {pool_csv}")
    print(f"[done] pool_meta.json → {meta_json}")
    return 0


def _flush(out_dir: str, meta: Dict, items: List[Dict]) -> None:
    """Write meta + rebuild pool.csv from on-disk per-symbol files."""
    pool_csv = os.path.join(out_dir, "pool.csv")
    meta_json = os.path.join(out_dir, "pool_meta.json")

    # Build the long-format CSV from the successfully fetched frames cached on disk
    # (we keep individual files alongside pool.csv for resilience)
    frames = []
    for code, m in meta.items():
        if m.get("status") != "ok":
            continue
        per_fp = os.path.join(out_dir, f"_per_symbol_{code}.csv")
        if not os.path.exists(per_fp):
            continue
        try:
            df = pd.read_csv(per_fp)
            df["symbol"] = code
            frames.append(df)
        except Exception:
            pass
    if frames:
        pool = pd.concat(frames, ignore_index=True)
        pool = pool[["symbol", "timestamps", "open", "high", "low", "close",
                     "volume", "amount"]]
        pool = pool.sort_values(["symbol", "timestamps"]).reset_index(drop=True)
        pool.to_csv(pool_csv, index=False)

    sector_counts = {}
    for code, m in meta.items():
        if m.get("status") == "ok":
            sector_counts.setdefault(m["sector"], 0)
            sector_counts[m["sector"]] += 1

    with open(meta_json, "w", encoding="utf-8") as f:
        json.dump({
            "totals": {
                "requested": len(items),
                "ok": sum(1 for m in meta.values() if m.get("status") == "ok"),
                "too_short": sum(1 for m in meta.values() if m.get("status") == "too_short"),
                "fail": sum(1 for m in meta.values() if m.get("status") == "fail"),
            },
            "sector_counts_ok": sector_counts,
            "symbols": meta,
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())