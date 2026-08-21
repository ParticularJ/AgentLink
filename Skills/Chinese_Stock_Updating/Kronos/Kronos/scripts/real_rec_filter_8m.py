# -*- coding: utf-8 -*-
"""
real_rec_filter_8m.py
2026-01 → 2026-08 真实推荐反指过滤器验证 (8 个月窗口)。

特点:
  - 区分 morning (9:30 买) vs evening (14:50 买) 的 entry 时间
  - 多数据源 fallback (本地池 > akshare 腾讯 > yfinance)
  - 加载失败的票不静默丢弃,而是打 WARNING 并保留其默认收益 0
  - 记录:每日入池→调仓→真实收益,细到 morning / evening 分开

Usage:
    python scripts/real_rec_filter_8m.py \
        --model /data/AgentLink/.../pool_300_daily_uniform/basemodel/best_model \
        --run-tag v2_8m_test
"""
import argparse, json, os, sys, warnings
import numpy as np
import pandas as pd
import torch

warnings.filterwarnings("ignore")

sys.path.insert(0, "/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos")
sys.path.insert(0, "/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/scripts")

from model import Kronos, KronosTokenizer, KronosPredictor
from evaluate_kronos_ic import apply_price_limit, load_daily_bars_csv


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--rec-dir",
                   default="/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/recommendations")
    p.add_argument("--start", default="2026-01-01")
    p.add_argument("--end", default="2026-08-14")
    p.add_argument("--lookback", type=int, default=200)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--hold-bd", type=int, default=5)
    p.add_argument("--sample-count", type=int, default=2)
    p.add_argument("--csv-dir", default="/tmp/kilo/kronos_pool_csv")
    p.add_argument("--model",
                   default="/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/"
                           "finetune_csv/finetuned/pool_300_daily_uniform/basemodel/best_model")
    p.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base")
    p.add_argument("--device", default="cuda")
    p.add_argument("--out-dir", default="./outputs/filter_real_rec_8m")
    p.add_argument("--run-tag", default="8m_v1")
    return p.parse_args()


# ---------------------------------------------------------------------------
# 多源 fallback: 本地池 > pytdx > akshare 腾讯 > yfinance
# ---------------------------------------------------------------------------
# pytdx 服务器列表 (从 ma-bullish-strategy/scripts/data_source_adapter.py 抄)
_PYTDX_SERVERS = [
    ('218.75.126.9', 7709),
    ('60.12.136.250', 7709),
    ('113.105.142.38', 7721),
    ('123.125.108.14', 7709),
    ('119.147.171.116', 7709),
]
_PYTDX_API = None
_PYTDX_API_HOST = None


def _get_pytdx_api():
    """懒加载 pytdx API,复用连接。"""
    global _PYTDX_API, _PYTDX_API_HOST
    if _PYTDX_API is None:
        from pytdx.hq import TdxHq_API
        api = TdxHq_API()
        # 尝试多个服务器,选一个能连上的
        for host, port in _PYTDX_SERVERS:
            try:
                if api.connect(host, port):
                    _PYTDX_API_HOST = host
                    _PYTDX_API = api
                    print(f"  [pytdx] 连接成功: {host}")
                    return _PYTDX_API
            except Exception:
                continue
        print("  [pytdx] 所有服务器连接失败")
        return None
    return _PYTDX_API


def _fetch_pytdx_one(api, sym, start_date="20200101", end_date="20260814"):
    """从 pytdx 拉 800 根日 K (覆盖 ~3 年)。"""
    mkt = 1 if sym.startswith(("5", "6", "9")) or sym.startswith("1") else 0
    d = api.get_security_bars(9, mkt, sym, 0, 800)
    if not d:
        return None
    df = api.to_df(d)
    df = df.rename(columns={"datetime": "date", "vol": "volume"})
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["close"] * df["volume"]
    return df[["date", "open", "close", "high", "low", "volume", "amount"]]


def get_bars(sym, csv_dir):
    """获取历史 K 线。多源 fallback,失败返回 None 不静默。

    优先级:
      1. 本地 CSV(快)
      2. pytdx(推荐:无风控、极速)
      3. akshare 腾讯
      4. yfinance
    """
    # 1. 本地池
    fp = os.path.join(csv_dir, f"{sym}.csv")
    if os.path.exists(fp):
        df = load_daily_bars_csv(sym, csv_dir)
        if df is not None and not df.empty:
            return df, "local"

    # 2. pytdx
    try:
        api = _get_pytdx_api()
        if api is not None:
            df = _fetch_pytdx_one(api, sym)
            if df is not None and not df.empty:
                # 缓存到本地避免下次重拉
                fp_local = f"{csv_dir}/{sym}.csv"
                try:
                    df.to_csv(fp_local, index=False)
                except Exception:
                    pass
                return df, "pytdx"
    except Exception:
        pass

    # 3. akshare 腾讯
    try:
        import akshare as ak
        yt = f"sh{sym}" if sym.startswith(("5", "6", "9")) or sym.startswith("1") else f"sz{sym}"
        h = ak.stock_zh_a_hist_tx(symbol=yt, start_date="20200101", end_date="20260814", adjust="qfq")
        if h is not None and not h.empty:
            df = pd.DataFrame({
                "date": pd.to_datetime(h["date"]).dt.tz_localize(None),
                "open": h["open"].astype(float),
                "high": h["high"].astype(float),
                "low": h["low"].astype(float),
                "close": h["close"].astype(float),
                "volume": h["volume"].astype(float),
                "amount": h["amount"].astype(float) if "amount" in h.columns else h["open"]*h["volume"],
            })
            return df, "ak_tx"
    except Exception:
        pass

    # 4. yfinance
    try:
        import yfinance as yf
        yt = f"{sym}.SS" if sym.startswith(("5", "6", "9")) or sym.startswith("1") else f"{sym}.SZ"
        h = yf.Ticker(yt).history(start="2020-01-01")
        if not h.empty:
            h = h.reset_index()
            df = pd.DataFrame({
                "date": pd.to_datetime(h["Date"]).dt.tz_localize(None),
                "open": h["Open"].astype(float),
                "high": h["High"].astype(float),
                "low": h["Low"].astype(float),
                "close": h["Close"].astype(float),
                "volume": h["Volume"].astype(float),
                "amount": h["Open"] * h["Volume"],
            })
            return df, "yfinance"
    except Exception:
        pass

    return None, "missing"


def get_session_entry_exit(last_date, session, hold_bd):
    """根据 session 类型返回 (entry_date, exit_date)。
    morning: 开盘买入 = last_date 次日开盘 (= last_date+1BD 开盘价)
    evening: 尾盘买入 = last_date 当日尾盘 (≈ last_date 收盘价,近收盘价)
    """
    last = pd.Timestamp(last_date)
    if session == "EVENING_BUY":
        # 尾盘买入:用 last_date 当天的 close
        entry_date = last
        exit_date = last + pd.tseries.offsets.BDay(hold_bd)
    else:  # MORNING_BUY 或未知
        # 早盘买入:用 last_date+1BD 开盘
        entry_date = last + pd.tseries.offsets.BDay(1)
        exit_date = entry_date + pd.tseries.offsets.BDay(hold_bd - 1)
    return entry_date, exit_date


def get_realized_return(df, last_date, session, hold_bd):
    """根据 session 计算真实 5 日收益。"""
    df = df.sort_values("date").reset_index(drop=True)
    last = pd.Timestamp(last_date)
    entry_d, exit_d = get_session_entry_exit(last_date, session, hold_bd)

    # 找 entry 日的开盘(如果 evening)或次日开盘(如果 morning)
    # evening: entry_date = last_date,价格用当日 close(尾盘近似)
    # morning: entry_date = last_date+1BD,价格用次日 open
    if session == "EVENING_BUY":
        # entry 用 last_date 当天 close
        row_e = df[df["date"] == last]
        if row_e.empty:
            return None
        entry_price = float(row_e.iloc[0]["close"])
    else:
        # entry 用 last_date+1BD 当天 open
        fut = df[df["date"] > last].sort_values("date")
        if fut.empty:
            return None
        entry_price = float(fut.iloc[0]["open"])

    # exit: entry 后第 hold_bd 日(BD)的 close
    if session == "EVENING_BUY":
        # entry 是 last, exit 是 last+hold_bd 的 close
        fut = df[df["date"] >= exit_d].sort_values("date")
    else:
        # entry 是 last+1BD, exit 是 entry+(hold_bd-1)BD ≈ last+hold_bd
        fut = df[df["date"] >= exit_d].sort_values("date")
    if fut.empty:
        return None
    exit_price = float(fut.iloc[0]["close"])

    return exit_price / entry_price - 1


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    out_dir = os.path.join(args.out_dir, args.run_tag)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[load] model: {args.model}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(model, tokenizer, device=args.device, max_context=512)

    print(f"[load] recs from {args.rec_dir}")
    files = [f for f in os.listdir(args.rec_dir)
             if f.startswith("2026") and f.endswith(".json")]
    rows = []
    for fn in sorted(files):
        with open(os.path.join(args.rec_dir, fn)) as f:
            d = json.load(f)
        for r in d.get("recommendations", []):
            rows.append({
                "date": d["date"],
                "session": d["session"],
                "code": str(r["code"]).zfill(6),
                "name": r["name"],
            })
    recs = pd.DataFrame(rows).drop_duplicates(["date", "code"])
    recs["date"] = pd.to_datetime(recs["date"])
    recs = recs[(recs["date"] >= args.start) & (recs["date"] <= args.end)].reset_index(drop=True)
    print(f"  total recs in window: {len(recs)}")
    print(f"  unique days: {recs['date'].nunique()}")

    # 分离 morning 和 evening
    morning = recs[recs["session"] == "MORNING_BUY"]
    evening = recs[recs["session"] == "EVENING_BUY"]
    print(f"  morning recs: {len(morning)}  evening recs: {len(evening)}")

    # 按 (date, session) 分组
    daily_groups = recs.groupby(["date", "session"])
    print(f"  total (date, session) groups: {len(daily_groups)}")

    all_results = []
    cache = {}

    for (day, sess), grp in daily_groups:
        cands = sorted(grp["code"].tolist())
        scored = {}

        for sym in cands:
            key = (sym, day.date().isoformat(), sess)
            if key in cache:
                scored.update(cache[key])
                continue

            df_hist, source = get_bars(sym, args.csv_dir)
            if df_hist is None:
                print(f"    [WARN] {day.date()} {sess} {sym}: NO DATA, treat as 0 ret")
                # 不静默丢弃,而是给一个 0 收益标记
                # 这样它的真实表现会"中性地"进入统计,不会拉高反指效果
                scored[sym] = {"pred_ret": 0.0, "real_ret": 0.0, "source": "missing",
                                 "last_close": None}
                cache[key] = scored.copy()
                continue

            ctx = df_hist[df_hist["date"] <= day].sort_values("date")
            if len(ctx) < args.lookback:
                print(f"    [WARN] {day.date()} {sess} {sym}: ctx={len(ctx)}<{args.lookback}")
                continue

            x_df = ctx.iloc[-args.lookback:]
            x_ts = pd.DatetimeIndex(x_df["date"])
            last_date = x_df["date"].iloc[-1]
            y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=args.pred_len)

            try:
                pred_df = predictor.predict(
                    df=x_df[["open", "high", "low", "close", "volume", "amount"]],
                    x_timestamp=x_ts,
                    y_timestamp=pd.Series(y_ts),
                    pred_len=args.pred_len, T=1.0, top_p=0.9,
                    sample_count=args.sample_count, verbose=False,
                )
                last_close = float(x_df["close"].iloc[-1])
                path = apply_price_limit(pred_df["close"].values.astype(float), last_close, 0.10)
                pred_ret = float(path[-1] / last_close - 1)

                real_ret = get_realized_return(df_hist, last_date, sess, args.hold_bd)
                if real_ret is None:
                    print(f"    [WARN] {day.date()} {sess} {sym}: no realized price")
                    continue

                scored[sym] = {
                    "pred_ret": pred_ret,
                    "real_ret": real_ret,
                    "source": source,
                    "last_close": last_close,
                    "last_date": last_date,
                }
            except Exception as e:
                print(f"    [ERR] {sym}: {type(e).__name__}: {e}")
                continue
            cache[key] = scored.copy()

        if len(scored) < 3:
            continue

        # 按 Kronos 升序排(最看跌在前)
        ranked = sorted(scored.items(), key=lambda x: x[1]["pred_ret"])
        ranked_syms = [s for s, _ in ranked]
        N = len(ranked_syms)

        # 各策略(只对有真实收益的票算 mean)
        def avg(syms):
            rets = [scored[s]["real_ret"] for s in syms
                    if scored[s]["real_ret"] is not None]
            return np.mean(rets) if rets else np.nan

        A_ret = avg(ranked_syms)
        B_ret = avg(ranked_syms[1:]) if N >= 4 else np.nan
        C_ret = avg(ranked_syms[2:]) if N >= 5 else np.nan
        # D 策略:剔除 Kronos 最看跌的 3 只
        # 当 N<6 时,改为剔除 min(3, N-2) 只(至少保留 2 只)
        # 这样即使只有 3-5 只候选,D 策略也能工作
        d_drop = min(3, max(1, N - 2))
        D_ret = avg(ranked_syms[d_drop:])
        K = max(1, N - 2)
        E_ret = avg(ranked_syms[-K:])

        all_results.append({
            "date": day.date(),
            "session": sess,
            "N": N,
            "A_no_filter": A_ret,
            "B_drop_1": B_ret,
            "C_drop_2": C_ret,
            "D_drop_3": D_ret,
            "E_keep_top": E_ret,
            "most_bearish": ranked_syms[0],
            "most_bearish_pred": scored[ranked_syms[0]]["pred_ret"],
            "most_bearish_real": scored[ranked_syms[0]]["real_ret"],
            "most_bullish": ranked_syms[-1],
            "most_bullish_pred": scored[ranked_syms[-1]]["pred_ret"],
            "most_bullish_real": scored[ranked_syms[-1]]["real_ret"],
        })

    df = pd.DataFrame(all_results)
    df.to_csv(os.path.join(out_dir, "daily_results.csv"), index=False)
    print(f"\n[save] {len(df)} (date,session) groups → {out_dir}/daily_results.csv")

    # ---- 汇总 ----
    print("\n" + "=" * 100)
    print("2026-01 → 2026-08 反指过滤器验证")
    print("=" * 100)
    from scipy.stats import ttest_rel

    summary = {}

    # 按 session 分别汇总
    for sess_filter in [None, "MORNING_BUY", "EVENING_BUY"]:
        sub = df if sess_filter is None else df[df["session"] == sess_filter]
        label_prefix = "全部" if sess_filter is None else sess_filter.replace("_BUY", "")
        print(f"\n--- {label_prefix} (n={len(sub)}) ---")
        A = sub["A_no_filter"].dropna()
        for col, label in [
            ("A_no_filter", "A 不剔除"),
            ("B_drop_1", "B drop_bottom_1"),
            ("C_drop_2", "C drop_bottom_2"),
            ("D_drop_3", "D drop_bottom_3"),
            ("E_keep_top", "E keep_top_K"),
        ]:
            r = sub[col].dropna()
            if r.empty:
                continue
            win = (r > 0).mean()
            avg = r.mean()
            total = (1 + r).prod() - 1
            sharpe = avg / (r.std() + 1e-9) * np.sqrt(252 / 5)
            sig = ""
            if col != "A_no_filter":
                common = r.index.intersection(A.index)
                if len(common) >= 5:
                    t, p = ttest_rel(r.loc[common], A.loc[common])
                    diff = (r.loc[common] - A.loc[common]).mean()
                    sig = f"  vs A: diff={diff * 100:+.3f}% t={t:+.2f} p={p:.3f} {'✓sig' if p < 0.05 else '✗'}"
            print(f"  {label:<18} n={len(r):>3} win={win * 100:>5.1f}% "
                  f"avg={avg * 100:>+6.3f}% total={total * 100:>+7.2f}% "
                  f"sharpe={sharpe:>5.2f}{sig}")
            summary[f"{label_prefix}_{col}"] = {
                "n": int(len(r)), "win_rate": float(win), "avg_ret": float(avg),
                "total_return": float(total), "sharpe": float(sharpe),
            }

    # Kronos 准确率
    bear_hit = (df["most_bearish_real"] < 0).sum()
    bull_hit = (df["most_bullish_real"] > 0).sum()
    n = len(df)
    print(f"\n[Kronos 准确率]  最看跌真跌: {bear_hit}/{n} = {bear_hit / n * 100:.0f}%")
    print(f"[Kronos 准确率]  最看多真涨: {bull_hit}/{n} = {bull_hit / n * 100:.0f}%")
    summary["kronos_bearish_hit_rate"] = bear_hit / n
    summary["kronos_bull_hit_rate"] = bull_hit / n

    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump({"args": vars(args), "summary": summary,
                   "per_day_session": df.to_dict(orient="records")},
                  f, indent=2, default=str)
    print(f"\n[saved] {out_dir}/summary.json")


if __name__ == "__main__":
    main()