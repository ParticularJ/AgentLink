# -*- coding: utf-8 -*-
"""
build_pool_300.py

构建 300 只 A 股训练池:
  1. 沪深 300 成分股(~300 只)
  2. + 您最近 6 个月推荐过的所有股票(去重)
  3. + 现有 133 池里的行业龙头(去重)
  4. 自动过滤: ST、退市、停牌 > 60 天、上市 < 1 年
  5. 输出:
     - data/pool_300.csv (训练数据, 与现有 pool.csv 同格式)
     - data/pool_300_meta.json (元数据)

Usage:
    python scripts/build_pool_300.py
"""
import os
import sys
import json
import time
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

import pandas as pd

# Repo root on path so we can import existing pool utilities
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
DATA_DIR = os.path.join(_ROOT, "finetune_csv", "data")


# ---------------------------------------------------------------------------
# 1) 沪深 300 成分股 (akshare)
# ---------------------------------------------------------------------------

def fetch_hs300_symbols() -> pd.DataFrame:
    """拉沪深 300 成分股。返回 [symbol, name]"""
    import akshare as ak
    print("[fetch] akshare 沪深 300 成分股 ...")
    try:
        df = ak.index_stock_cons_weight_csindex(symbol="000300")
        # 列: 指数代码, 成分券代码, 成分券名称, 交易所
        df = df.rename(columns={"成分券代码": "symbol", "成分券名称": "name"})
        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
        df = df[["symbol", "name"]].drop_duplicates("symbol")
        print(f"  → {len(df)} 只 HS300")
        return df
    except Exception as e:
        print(f"  [warn] HS300 fetch failed: {e}")
        return pd.DataFrame(columns=["symbol", "name"])


def fetch_zz500_symbols() -> pd.DataFrame:
    """拉中证 500 成分股 (用于覆盖中小盘)"""
    import akshare as ak
    print("[fetch] akshare 中证 500 成分股 ...")
    try:
        df = ak.index_stock_cons_weight_csindex(symbol="000905")
        df = df.rename(columns={"成分券代码": "symbol", "成分券名称": "name"})
        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
        df = df[["symbol", "name"]].drop_duplicates("symbol")
        print(f"  → {len(df)} 只 ZZ500")
        return df
    except Exception as e:
        print(f"  [warn] ZZ500 fetch failed: {e}")
        return pd.DataFrame(columns=["symbol", "name"])


def _ak_symbol(code: str) -> str:
    """600/601/603/605/688/9 → sh; 其余 → sz"""
    return f"sh{code}" if code.startswith(("5","6","9","1")) else f"sz{code}"


# ---------------------------------------------------------------------------
# 2) 您最近 6 个月推荐过的所有股票 (本地 JSON)
# ---------------------------------------------------------------------------

def fetch_user_recommended_symbols(months=6) -> pd.DataFrame:
    """从 recommendations/ 目录读取最近 N 个月的推荐"""
    rec_dir = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/recommendations"
    if not os.path.exists(rec_dir):
        print(f"  [warn] rec dir not found: {rec_dir}")
        return pd.DataFrame(columns=["symbol", "name"])

    cutoff = (datetime.now() - timedelta(days=30 * months)).strftime("%Y%m%d")
    print(f"[fetch] 用户推荐 (>= {cutoff}) ...")
    rows = []
    for fn in sorted(os.listdir(rec_dir)):
        if not fn.endswith(".json"):
            continue
        date_str = fn[:8]
        if date_str < cutoff:
            continue
        try:
            with open(os.path.join(rec_dir, fn)) as f:
                d = json.load(f)
            for r in d.get("recommendations", []):
                rows.append({
                    "symbol": str(r["code"]).zfill(6),
                    "name": r["name"],
                })
        except Exception:
            continue
    df = pd.DataFrame(rows).drop_duplicates("symbol")
    print(f"  → {len(df)} 只 (用户推荐去重)")
    return df


# ---------------------------------------------------------------------------
# 3) 现有 133 池
# ---------------------------------------------------------------------------

def fetch_existing_133() -> pd.DataFrame:
    """读取现有 133 池"""
    meta_fp = os.path.join(DATA_DIR, "pool_meta.json")
    if not os.path.exists(meta_fp):
        return pd.DataFrame(columns=["symbol", "name"])
    with open(meta_fp) as f:
        meta = json.load(f)
    rows = [{"symbol": sym, "name": info.get("name", "")}
            for sym, info in meta["symbols"].items()]
    df = pd.DataFrame(rows)
    print(f"  → {len(df)} 只 (现有 133 池)")
    return df


# ---------------------------------------------------------------------------
# 4) 过滤: ST、退市、停牌 > 60 天、上市 < 1 年
# ---------------------------------------------------------------------------

def filter_bad_symbols(df: pd.DataFrame) -> pd.DataFrame:
    """
    轻量过滤: 只校验名称(不拉数据)
      - ST / *ST / 退市 (从 name 字段判断)
    数据质量过滤在拉数据阶段做(避免重复网络请求)
    """
    print("[filter] 轻量过滤 ST / 退市 ...")

    keep_rows = []
    drop_reasons = {"ST": 0, "退市": 0}

    for _, row in df.iterrows():
        name = row["name"]
        if "退" in name:
            drop_reasons["退市"] += 1
            continue
        if any(k in name for k in ["ST", "*ST"]):
            drop_reasons["ST"] += 1
            continue
        keep_rows.append(row.to_dict())

    print(f"  drop reasons: {drop_reasons}")
    print(f"  → kept {len(keep_rows)} / {len(df)}")
    return pd.DataFrame(keep_rows)


# ---------------------------------------------------------------------------
# 5) 合并 + 写 CSV (Kronos 训练格式)
# ---------------------------------------------------------------------------

def merge_and_save(hs300, zz500, user_recs, existing133, out_csv, out_meta):
    """合并三个来源 → 训练池 → 写 CSV"""
    print("\n[merge] 合并三个来源 ...")
    # 优先级: HS300 (300) + ZZ500 (500, 去重 HS300) + 用户推荐 (去重) + 133池 (去重)
    seen = set()
    rows = []
    sources = {"HS300": [], "ZZ500_only": [], "user_recs": [], "pool133": []}

    # 1. HS300 (全部保留)
    for _, r in hs300.iterrows():
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            rows.append(r.to_dict())
            sources["HS300"].append(r["symbol"])

    # 2. ZZ500 去重 HS300
    for _, r in zz500.iterrows():
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            rows.append(r.to_dict())
            sources["ZZ500_only"].append(r["symbol"])

    # 3. 用户推荐去重
    for _, r in user_recs.iterrows():
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            rows.append(r.to_dict())
            sources["user_recs"].append(r["symbol"])

    # 4. 现有 133 池去重
    for _, r in existing133.iterrows():
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            rows.append(r.to_dict())
            sources["pool133"].append(r["symbol"])

    df = pd.DataFrame(rows)
    print(f"  合并后: {len(df)} 只")
    for k, v in sources.items():
        print(f"    {k}: {len(v)} 只")

    # 过滤
    df = filter_bad_symbols(df)

    # 截断到 500 (训练池上限)
    if len(df) > 500:
        print(f"  截断到 500 只 (原 {len(df)} 只)")
        # 优先保留 HS300, 然后 ZZ500, 然后 user_recs, 然后 133
        priority = []
        for s in sources["HS300"]:
            if s in df["symbol"].values and s not in priority:
                priority.append(s)
        for s in sources["ZZ500_only"]:
            if s in df["symbol"].values and s not in priority:
                priority.append(s)
        for s in sources["user_recs"]:
            if s in df["symbol"].values and s not in priority:
                priority.append(s)
        for s in sources["pool133"]:
            if s in df["symbol"].values and s not in priority:
                priority.append(s)
        df = df[df["symbol"].isin(priority[:500])].reset_index(drop=True)
        print(f"  最终: {len(df)} 只")

    return df, sources


def fetch_history_and_save_csv(df: pd.DataFrame, out_csv: str):
    """拉每只票的日 K (腾讯数据源) + 数据质量过滤"""
    import akshare as ak
    print(f"\n[fetch+save] 拉 {len(df)} 只票的日 K (腾讯数据源) → {out_csv}")
    all_data = []
    fail = []
    skip_reasons = {"短": 0, "停牌": 0, "僵尸": 0}

    for i, row in df.iterrows():
        sym = row["symbol"]
        try:
            end = datetime.now().strftime("%Y%m%d")
            hist = ak.stock_zh_a_hist_tx(symbol=_ak_symbol(sym),
                                          start_date="20200101",
                                          end_date=end,
                                          adjust="qfq")
            if hist is None or hist.empty:
                fail.append(sym)
                continue

            # 上市 < 1 年
            first_date = pd.to_datetime(hist["date"]).min()
            if (datetime.now() - first_date).days < 365:
                skip_reasons["短"] += 1
                fail.append(sym)
                continue

            # 近 60 天交易日数 < 40
            recent = hist.tail(60)
            if len(recent) < 40:
                skip_reasons["停牌"] += 1
                fail.append(sym)
                continue

            # 2025 年日均成交额 < 1000 万
            hist_2025 = hist[pd.to_datetime(hist["date"]) >= "2025-01-01"]
            if len(hist_2025) > 0:
                avg_amount = hist_2025["amount"].astype(float).mean()
                if avg_amount < 10_000_000:
                    skip_reasons["僵尸"] += 1
                    fail.append(sym)
                    continue

            # 列名适配
            hist = hist.rename(columns={
                "date": "timestamps",
                "open": "open", "high": "high",
                "low": "low", "close": "close",
                "volume": "volume", "amount": "amount",
            })
            hist["timestamps"] = pd.to_datetime(hist["timestamps"]).dt.strftime(
                "%Y-%m-%d 15:00")
            hist["symbol"] = sym
            hist["level"] = ""
            all_data.append(hist[["symbol","timestamps","open","high","low",
                                   "close","volume","amount","level"]])
            if (i + 1) % 30 == 0:
                print(f"  [{i+1}/{len(df)}] kept={len(all_data)} skip={sum(skip_reasons.values())} fail={len(fail)-sum(skip_reasons.values())}")
        except Exception as e:
            fail.append(sym)
        time.sleep(0.2)  # 限流

    print(f"\n  skip reasons: {skip_reasons}")
    if fail:
        print(f"  ⚠️ 失败/跳过 {len(fail)} 只")

    out = pd.concat(all_data, ignore_index=True)
    out.to_csv(out_csv, index=False)
    print(f"\n[save] {out_csv}  ({len(out)} 行, {out['symbol'].nunique()} 只)")
    return out, fail


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    out_csv = os.path.join(DATA_DIR, "pool_300.csv")
    out_meta = os.path.join(DATA_DIR, "pool_300_meta.json")

    # 1. 拉成分股
    hs300 = fetch_hs300_symbols()
    zz500 = fetch_zz500_symbols()

    # 2. 用户最近 6 个月推荐
    user_recs = fetch_user_recommended_symbols(months=6)

    # 3. 现有 133 池
    existing133 = fetch_existing_133()

    # 4. 合并 + 过滤
    df, sources = merge_and_save(hs300, zz500, user_recs, existing133, out_csv, out_meta)

    # 5. 拉日 K + 保存 CSV
    out, fail = fetch_history_and_save_csv(df, out_csv)

    # 6. 写元数据
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sources": {k: len(v) for k, v in sources.items()},
        "total_symbols": int(out["symbol"].nunique()),
        "failed_symbols": fail,
        "date_range": {
            "start": str(pd.to_datetime(out["timestamps"].str[:10]).min().date()),
            "end": str(pd.to_datetime(out["timestamps"].str[:10]).max().date()),
        },
        "symbols": {},
    }
    # 每只票的统计
    for sym, grp in out.groupby("symbol"):
        grp = grp.copy()
        grp["date"] = pd.to_datetime(grp["timestamps"].str[:10])
        meta["symbols"][sym] = {
            "n_rows": int(len(grp)),
            "first_date": str(grp["date"].min().date()),
            "last_date": str(grp["date"].max().date()),
        }

    with open(out_meta, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"\n[save] {out_meta}")

    print(f"\n✅ 完成: {len(out)} 行 / {out['symbol'].nunique()} 只票")
    print(f"\n下一步:")
    print(f"  1. 复制并修改 configs/config_pool_v1.yaml → config_pool_v2.yaml")
    print(f"     - data_path 改为 pool_300.csv")
    print(f"  2. python finetune_csv/train.py --config configs/config_pool_v2.yaml")


if __name__ == "__main__":
    main()