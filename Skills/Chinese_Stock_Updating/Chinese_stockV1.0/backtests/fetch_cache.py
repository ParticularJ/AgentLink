#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测数据抓取：把标的日线缓存到本地 CSV，回测时不再联网。

数据源（按优先级）：
  1. 腾讯前复权日线 web.ifzq.gtimg.cn（qfq）——**默认**，
     必须用前复权：新浪的未复权序列会把基金份额折算/大额分红记成价格暴跌，
     实测 sh515880 在 2026-02-03 出现 -65.7% 的假跌、sh588200 在 2026-07-21 出现 -61.9% 的假跌，
     直接导致年度回测结果失真；
  2. 新浪日线（未复权）——仅作腾讯失败时的兜底，命中时会打警告。
缓存目录：backtests/cache/<symbol>.csv  列：date,open,high,low,close,volume
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "common"))

for _k in list(os.environ):
    if "proxy" in _k.lower():
        del os.environ[_k]

CACHE = HERE / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
SOURCES = HERE / "cache" / "_sources.json"

SINA = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={n}")
# 腾讯前复权日线：主域名 web.ifzq.gtimg.cn 会返回 JS 挑战页（HTTP 501），
# 实测 proxy.finance.qq.com 与 ifzq.gtimg.cn 稳定可用，依次尝试。
TENCENT_HOSTS = (
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?param={sym},day,,,{n},qfq",
    "https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq",
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq",
)
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Referer": "https://gu.qq.com/",
}


def sina_symbol(code: str) -> str:
    """6 位代码 / sh600584 形式 → 新浪接口需要的 sh600584。"""
    c = code.strip()
    if c[:2].lower() in ("sh", "sz", "bj"):
        return c.lower()
    return ("sh" if c[:1] in ("6", "5", "9") else "sz") + c


def fetch_tencent(symbol: str, datalen: int = 600):
    """腾讯前复权日线（多主机轮询）。返回 [date, open, close, high, low, volume]。"""
    arr, last_err = None, None
    for host in TENCENT_HOSTS:
        try:
            r = requests.get(host.format(sym=symbol, n=datalen), headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = (r.json().get("data") or {}).get(symbol) or {}
            got = data.get("qfqday") or data.get("day") or []
            if got:
                arr = got
                break
        except Exception as e:  # 换下一个主机
            last_err = e
    if not arr:
        raise RuntimeError(f"腾讯全部主机均失败: {last_err}")
    rows = []
    for x in arr:
        if len(x) < 6:
            continue
        rows.append({
            "date": str(x[0])[:10],
            "open": float(x[1]),
            "close": float(x[2]),
            "high": float(x[3]),
            "low": float(x[4]),
            "volume": float(x[5] or 0),
        })
    return rows or None


def fetch(symbol: str, datalen: int = 600, retries: int = 3, prefer: str = "tencent"):
    """优先腾讯前复权；失败再退回新浪（未复权，会打警告）。"""
    order = ("tencent", "sina") if prefer == "tencent" else ("sina", "tencent")
    for src in order:
        rows = _fetch_one(src, symbol, datalen, retries)
        if rows:
            if src == "sina":
                print(f"  [WARN] {symbol} 退回到新浪未复权数据，回测结果可能受折算影响")
            return rows, src
    return None, None


def _fetch_one(src: str, symbol: str, datalen: int, retries: int):
    if src == "tencent":
        for attempt in range(1, retries + 1):
            try:
                return fetch_tencent(symbol, datalen)
            except Exception:
                if attempt == retries:
                    return None
                time.sleep(2.0 * attempt)   # 腾讯有限速，退避要够长
        return None
    return _fetch_sina(symbol, datalen, retries)


def _fetch_sina(symbol: str, datalen: int, retries: int):
    url = SINA.format(sym=symbol, n=datalen)
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            txt = r.text.strip()
            if not txt or txt in ("null", "[]"):
                return None
            rows = json.loads(txt)
            if not rows:
                return None
            return [
                {
                    "date": row["day"][:10],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume") or 0),
                }
                for row in rows
            ]
        except Exception as e:
            if attempt == retries:
                print(f"  [FAIL] {symbol}: {type(e).__name__}: {str(e)[:80]}")
                return None
            time.sleep(1.5 * attempt)
    return None


def load_sources() -> dict:
    try:
        return json.loads(SOURCES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_sources(src: dict) -> None:
    SOURCES.write_text(json.dumps(src, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def save(symbol: str, rows, source: str = "") -> None:
    p = CACHE / f"{symbol}.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(rows)
    if source:
        src = load_sources()
        src[symbol] = source
        save_sources(src)


# A 股单日涨跌幅上限：主板 ±10%、创业板/科创板 ±20%、ETF ±10% 或 ±20%。
# 因此任何单日 |涨跌| > 21% 都只可能是数据问题（基金份额折算/分红未复权）。
ARTIFACT_LIMIT = 0.21


def scan_artifacts(limit: float = ARTIFACT_LIMIT):
    """扫描缓存中疑似「未复权折算」造成的假跳变，返回 {symbol: 最大单日涨跌幅}。"""
    bad = {}
    for f in sorted(CACHE.glob("*.csv")):
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if len(df) < 3 or "close" not in df.columns:
            continue
        chg = df["close"].pct_change().abs()
        worst = float(chg.max())
        if worst > limit:
            bad[f.stem] = worst
    return bad


def build_universe() -> list:
    """股票池 + 板块 ETF + 指数。"""
    from holdings import to_sina_code
    from paths import WATCHLIST_FILE
    from watchlist import load_watchlist_entries

    codes = []
    for e in load_watchlist_entries():
        codes.append(to_sina_code(e["code"]))

    fusion_scripts = REPO / "strategy-fusion-advisor" / "skills" / "scripts"
    sys.path.insert(0, str(fusion_scripts))
    import market_phase_detector as mpd

    for sector, etfs in mpd.SECTOR_ETFS.items():
        for c in etfs:
            codes.append(c)
    # 当前 watchlist 文件里的 etf_pool（十月池等）也要一起抓，
    # 否则「ETF 买入持有」基线没有数据。
    try:
        import yaml
        with open(os.environ.get("STOCK_WATCHLIST_FILE") or str(WATCHLIST_FILE), encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        for group, items in (raw.get("etf_pool") or {}).items():
            for item in items or []:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    codes.append(to_sina_code(str(item[1])))
    except Exception as e:
        print(f"[WARN] 读取 etf_pool 失败（忽略）: {e}")

    # 指数：上证 / 沪深300 / 深证 / 创业板，供大盘 phase 判定
    codes += ["sh000001", "sh000300", "sz399001", "sz399006"]
    # 去重且保序
    seen, out = set(), []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def main():
    import argparse

    ap = argparse.ArgumentParser(description="抓取并缓存日线")
    ap.add_argument("--datalen", type=int, default=600,
                    help="每个标的抓取的 K 线根数（600 根约 2.4 年，供长周期回测预热）")
    ap.add_argument("--force", action="store_true", help="忽略已有缓存，全部重抓")
    ap.add_argument("--fix-unadjusted", action="store_true",
                    help="只重抓上次退回新浪（未复权）的标的")
    ap.add_argument("--sleep", type=float, default=1.0, help="每个标的之间的间隔秒数")
    ap.add_argument("--symbols", default="", help="只抓这些代码（逗号分隔）")
    ap.add_argument("--scan", action="store_true", help="只扫描疑似未复权的异常跳变")
    args = ap.parse_args()

    if args.scan:
        bad = scan_artifacts()
        print(f"疑似未复权（单日涨跌 > {ARTIFACT_LIMIT:.0%}）的标的: {len(bad)} 个")
        for sym, worst in sorted(bad.items(), key=lambda kv: -kv[1]):
            print(f"  {sym}  最大单日 {worst * 100:.1f}%")
        return

    universe = build_universe()
    sources = load_sources()
    if args.symbols:
        wanted = [s.strip() for s in args.symbols.split(",") if s.strip()]
        # 以用户给的清单为准（即使不在当前 watchlist 里也照抓）
        todo = [s for s in universe if s in wanted] + [s for s in wanted if s not in set(universe)]
        print(f"定向抓取: {len(todo)} 个")
    elif args.fix_unadjusted:
        todo = [s for s in universe if sources.get(s) == "sina"]
        print(f"待修复（上次退回未复权）: {len(todo)} / {len(universe)}")
    else:
        todo = list(universe)
        print(f"待抓取标的: {len(todo)}  每标的 {args.datalen} 根")

    ok = skip = fail = 0
    for i, sym in enumerate(todo, 1):
        p = CACHE / f"{sym}.csv"
        if not args.force and not args.fix_unadjusted and p.exists() and p.stat().st_size > 200:
            skip += 1
            continue
        rows, source = fetch(sym, datalen=args.datalen)
        if rows:
            save(sym, rows, source)
            ok += 1
        else:
            fail += 1
        if i % 25 == 0:
            print(f"  进度 {i}/{len(todo)}  新抓 {ok} 跳过 {skip} 失败 {fail}")
        time.sleep(args.sleep)
    src = load_sources()
    n_tencent = sum(1 for v in src.values() if v == "tencent")
    n_sina = sum(1 for v in src.values() if v == "sina")
    print(f"完成：本次写入 {ok}，跳过 {skip}，失败 {fail}")
    print(f"数据来源统计：腾讯前复权 {n_tencent} 个，新浪未复权 {n_sina} 个")


if __name__ == "__main__":
    main()
