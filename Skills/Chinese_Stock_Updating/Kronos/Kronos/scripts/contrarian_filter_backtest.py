# -*- coding: utf-8 -*-
"""
contrarian_filter_backtest.py

"反指过滤器" — Contrarian filter backtest using Kronos (大幅改进版).

Idea
----
经验上很多小模型 / LLM 在 A 股横截面打分时具有 **负 alpha**: 模型"最看多"
的标的未来实际表现往往偏弱,而"最看跌"的标的反而容易跑赢。本脚本以
Kronos-base 作为打分器,执行一个干净的样本外(OOS)反指回测:

    每个调仓日 t:
      1. 取当日 N 个候选(默认 5)。
      2. Kronos 对每个候选预测未来 pred_len 日的收盘价路径 → pred_ret。
      3. 计算真实 realised_ret = close[t+H] / close[t] - 1。
      4. 构造以下策略(全部 long-only,持有 H 个交易日):
           - contrarian      反指: 多头 = Kronos最看跌(rank 0)
           - bullish         正指: 多头 = Kronos最看多(rank N-1)
           - bottom_K        多头 = Kronos最看跌的 K 只(等权)
           - top_K           多头 = Kronos最看多的 K 只(等权)
           - random_top      蒙特卡洛: 随机选 K 只(等权,跑 --mc-trials 次)
           - equal_weight    多头 = 全部候选(等权)
      5. 扣除双边交易成本 + 滑点,按日 mark-to-market 累计权益曲线。

输出 (./outputs/contrarian/<run_tag>/):
    trades.csv           每个 trade-leg 一行
    equity_<strat>.csv   每个策略一条日度权益曲线
    summary.json         每个策略的完整绩效指标
    subperiods.csv       滚动窗口(默认季度)的分段绩效
    picks_<date>.csv     每个调仓日的打分明细

使用示例
--------
    python scripts/contrarian_filter_backtest.py \
        --start 2024-01-01 --end 2025-06-30 \
        --pick-source csv --csv-pick-file my_picks.csv --csv-dir data/csv \
        --lookback 400 --pred-len 5 --realise-horizon 5 \
        --max-symbols-per-day 5 --mc-trials 200 \
        --cost-bps 15 --slippage-bps 5 \
        --run-tag contrarian_oos_v1
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: E402

from evaluate_kronos_ic import (  # noqa: E402
    load_pick_schedule,
    load_daily_bars_qlib,
    load_daily_bars_csv,
    apply_price_limit,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Kronos 反指过滤器 OOS 回测 (大幅改进版)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--rebalance-freq", default="W",
                   choices=["D", "W", "M"])

    # Universe
    p.add_argument("--pick-source", default="csv", choices=["qlib", "csv"])
    p.add_argument("--universe", default="csi300")
    p.add_argument("--qlib-provider", default="~/.qlib/qlib_data/cn_data")
    p.add_argument("--csv-pick-file", default=None)
    p.add_argument("--csv-dir", default="./data/csv")
    p.add_argument("--max-symbols-per-day", type=int, default=5,
                   help="每日候选上限 (反指逻辑要求 N>=3,默认 5)")

    # Model
    p.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base",
                   help="HF model id 或本地路径")
    p.add_argument("--model", default="NeoQuasar/Kronos-base",
                   help="HF model id 或本地路径(可用 finetune_csv/finetuned/.../basemodel/best_model)")
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    p.add_argument("--max-context", type=int, default=512)
    p.add_argument("--lookback", type=int, default=400)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--sample-count", type=int, default=3)
    p.add_argument("--T", type=float, default=1.0)
    p.add_argument("--top-p", type=float, default=0.9)

    # Realisation / frictions
    p.add_argument("--realise-horizon", type=int, default=5)
    p.add_argument("--price-limit", type=float, default=0.10,
                   help="A 股日 ±10% 限制")
    p.add_argument("--cost-bps", type=float, default=15.0,
                   help="单边交易佣金+印花税 (基点),默认 15 bps")
    p.add_argument("--slippage-bps", type=float, default=5.0,
                   help="单边冲击/滑点 (基点),默认 5 bps")
    p.add_argument("--mc-trials", type=int, default=200,
                   help="random_top / random_baseline 的蒙特卡洛次数")
    p.add_argument("--seed", type=int, default=42)

    # Output
    p.add_argument("--out-dir", default="./outputs/contrarian")
    p.add_argument("--run-tag", default="contrarian_v1")
    p.add_argument("--subperiod-freq", default="Q",
                   choices=["M", "Q", "Y"],
                   help="分段绩效窗口")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Per-day scoring
# ---------------------------------------------------------------------------

@dataclass
class Score:
    date: pd.Timestamp
    symbol: str
    last_close: float
    pred_close: float
    real_close: float
    pred_ret: float
    real_ret: float
    status: str = "ok"


def score_one_symbol(predictor: KronosPredictor,
                     df_hist: pd.DataFrame,
                     symbol: str,
                     day: pd.Timestamp,
                     lookback: int,
                     pred_len: int,
                     realise_horizon: int,
                     sample_count: int,
                     T: float,
                     top_p: float,
                     price_limit: float) -> Optional[Score]:
    df_hist = df_hist.sort_values("date").reset_index(drop=True)
    ctx = df_hist[df_hist["date"] <= day]
    if len(ctx) < lookback:
        return None

    x_df = ctx.iloc[-lookback:]
    x_ts = pd.DatetimeIndex(x_df["date"])
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
    pred_close_path = apply_price_limit(
        pred_df["close"].values.astype(float), last_close, price_limit
    )
    pred_close = float(pred_close_path[-1])

    target_date = last_date + pd.tseries.offsets.BDay(realise_horizon)
    future = df_hist[df_hist["date"] >= target_date]
    if future.empty:
        return None
    real_close = float(future.iloc[0]["close"])

    pred_ret = pred_close / last_close - 1.0
    real_ret = real_close / last_close - 1.0

    return Score(
        date=pd.Timestamp(day),
        symbol=symbol,
        last_close=last_close,
        pred_close=pred_close,
        real_close=real_close,
        pred_ret=pred_ret,
        real_ret=real_ret,
    )


# ---------------------------------------------------------------------------
# Strategy construction (per rebalance day)
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    symbol: str
    weight: float             # 仓位权重,等权策略下为 1/N
    last_close: float
    real_close: float
    pred_ret: float
    real_ret: float           # 持仓净收益 (已扣成本)
    gross_ret: float          # 毛收益 (未扣成本)
    strategy: str
    rank_pred: int
    n_candidates: int


def _build_day_trades(scored: List[Score],
                      bottom_k: int,
                      top_k: int,
                      mc_trials: int,
                      rng: np.random.Generator) -> List[Trade]:
    """
    scored : 当日所有 Score (按 pred_ret 升序 = 最看跌在前)
    返回当日所有 strategy 的 Trade 列表(每个 trade 已绑定 strategy 名和权重)
    """
    if not scored:
        return []

    n = len(scored)
    order = sorted(range(n), key=lambda i: scored[i].pred_ret)
    sym_to_rank = {scored[i].symbol: r for r, i in enumerate(order)}
    sym_to_idx = {s: i for i, s in enumerate([scored[i].symbol for i in order])}

    last_close_by_sym = {s.symbol: s.last_close for s in scored}
    real_close_by_sym = {s.symbol: s.real_close for s in scored}
    pred_ret_by_sym = {s.symbol: s.pred_ret for s in scored}
    gross_ret_by_sym = {s.symbol: s.real_ret for s in scored}
    entry_date = scored[0].date
    exit_date = entry_date + pd.tseries.offsets.BDay(_HORIZON)

    out: List[Trade] = []

    def make_trade(sym: str, strategy: str, weight: float) -> Trade:
        return Trade(
            entry_date=entry_date,
            exit_date=exit_date,
            symbol=sym,
            weight=weight,
            last_close=last_close_by_sym[sym],
            real_close=real_close_by_sym[sym],
            pred_ret=pred_ret_by_sym[sym],
            real_ret=gross_ret_by_sym[sym],
            gross_ret=gross_ret_by_sym[sym],
            strategy=strategy,
            rank_pred=sym_to_rank[sym],
            n_candidates=n,
        )

    # 1) contrarian: 最看跌 (rank 0)
    sym0 = scored[order[0]].symbol
    out.append(make_trade(sym0, "contrarian", 1.0))

    # 2) bullish: 最看多 (rank N-1)
    symn = scored[order[-1]].symbol
    out.append(make_trade(symn, "bullish", 1.0))

    # 3) bottom_K basket: K 只最看跌等权
    k_bot = min(bottom_k, n)
    w = 1.0 / k_bot
    for j in range(k_bot):
        out.append(make_trade(scored[order[j]].symbol, f"bottom_{k_bot}", w))

    # 4) top_K basket: K 只最看多等权
    k_top = min(top_k, n)
    w = 1.0 / k_top
    for j in range(k_top):
        out.append(make_trade(scored[order[-(j + 1)]].symbol, f"top_{k_top}", w))

    # 5) equal_weight basket
    w = 1.0 / n
    for j in range(n):
        out.append(make_trade(scored[order[j]].symbol, "equal_weight", w))

    # 6) random_top: 蒙特卡洛,随机选 K 只等权
    if mc_trials > 0 and k_top >= 2:
        syms = [scored[i].symbol for i in range(n)]
        for t in range(mc_trials):
            pick = rng.choice(syms, size=k_top, replace=False)
            w = 1.0 / k_top
            for s in pick:
                out.append(make_trade(s, f"random_top_{k_top}_t{t}", w))

    # 7) random_single: 每次随机选一只
    if mc_trials > 0:
        syms = [scored[i].symbol for i in range(n)]
        for t in range(mc_trials):
            s = rng.choice(syms)
            out.append(make_trade(s, f"random_single_t{t}", 1.0))

    return out


# Module-level state set per-day (avoids globals in main loop).
_DAY_SCRATCH: List[Score] = []
_HORIZON: int = 5


# ---------------------------------------------------------------------------
# Equity curves & metrics
# ---------------------------------------------------------------------------

def apply_costs_to_trades(trades: pd.DataFrame,
                          cost_bps: float,
                          slippage_bps: float) -> pd.DataFrame:
    """双边扣费: 单边 cost_bps + slippage_bps."""
    trades = trades.copy()
    one_way = (cost_bps + slippage_bps) / 10000.0
    two_way = 2.0 * one_way
    trades["real_ret_net"] = trades["real_ret"] - two_way
    return trades


def build_equity_curve(trades: pd.DataFrame,
                       start: str,
                       end: str,
                       strat: str) -> pd.Series:
    """
    每个 strategy 在 entry_date 按权重开仓,持有 H 个交易日后在 exit_date 平仓。
    我们用日度 mark-to-market 累计: 在 entry_date 当日应用当日收益(若无
    当日 → entry_date 前最后一日); exit_date (含) 后仓位为空,曲线保持平。
    """
    sub = trades[trades["strategy"] == strat].copy()
    if sub.empty:
        return pd.Series(dtype=float)

    idx = pd.date_range(start, end, freq="B")
    eq = pd.Series(1.0, index=idx, dtype=float)

    for _, row in sub.iterrows():
        entry = pd.Timestamp(row["entry_date"])
        exit_ = pd.Timestamp(row["exit_date"])
        w = float(row["weight"])
        net = float(row["real_ret_net"])
        # entry 日(含)之前已有 1.0 资金;entry 日按权重承担 net 的仓位收益。
        # 我们把仓位收益一次性记到 entry 日(因为 close[t+H] 是相对 close[t] 的)。
        if entry in eq.index:
            eq.loc[entry] *= (1.0 + w * net)
        else:
            pos = eq.index.get_indexer([entry], method="bfill")[0]
            if pos >= 0:
                eq.iloc[pos] *= (1.0 + w * net)
        # exit 日及之后仓位已平,曲线保持;但等权 basket 多日叠加,需复利。
        # 为简化,每个 rebalance 独立贡献一次复利到 entry 日,即可代表整体。
    return eq.cumprod()


def metrics_from_curve(eq: pd.Series,
                       trades: pd.DataFrame,
                       strat: str,
                       cost_bps: float,
                       slippage_bps: float) -> dict:
    sub = trades[trades["strategy"] == strat]
    if sub.empty or eq.empty:
        return {"strategy": strat, "n_trades": 0}

    rets = eq.pct_change().dropna()
    total = float(eq.iloc[-1] / eq.iloc[0] - 1.0)
    n_days = max(len(eq), 1)
    cagr = (1.0 + total) ** (252.0 / n_days) - 1.0 if total > -1.0 else -1.0
    vol = float(rets.std() * np.sqrt(252)) if len(rets) > 1 else 0.0
    sharpe = cagr / vol if vol > 1e-9 else 0.0
    peak = eq.cummax()
    mdd = float((eq / peak - 1.0).min())
    calmar = cagr / abs(mdd) if abs(mdd) > 1e-9 else 0.0

    win_rate = float((sub["real_ret_net"] > 0).mean())
    avg_ret = float(sub["real_ret_net"].mean())
    avg_win = float(sub.loc[sub["real_ret_net"] > 0, "real_ret_net"].mean()) \
        if (sub["real_ret_net"] > 0).any() else 0.0
    avg_loss = float(sub.loc[sub["real_ret_net"] < 0, "real_ret_net"].mean()) \
        if (sub["real_ret_net"] < 0).any() else 0.0
    profit_factor = (
        sub.loc[sub["real_ret_net"] > 0, "real_ret_net"].sum() /
        abs(sub.loc[sub["real_ret_net"] < 0, "real_ret_net"].sum())
        if (sub["real_ret_net"] < 0).any() else float("inf")
    )

    return {
        "strategy": strat,
        "n_trades": int(len(sub)),
        "total_return": total,
        "cagr": cagr,
        "ann_vol": vol,
        "sharpe": sharpe,
        "calmar": calmar,
        "max_drawdown": mdd,
        "win_rate": win_rate,
        "avg_trade_ret": avg_ret,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": float(profit_factor) if profit_factor != float("inf") else None,
        "start_date": str(eq.index[0].date()),
        "end_date": str(eq.index[-1].date()),
        "cost_bps_round_trip": 2 * (cost_bps + slippage_bps),
    }


def random_baseline_stats(trades: pd.DataFrame,
                          start: str, end: str,
                          prefix: str,
                          cost_bps: float, slippage_bps: float) -> dict:
    """对所有 random_* 策略计算均值±std。"""
    rng_strats = [s for s in trades["strategy"].unique() if s.startswith(prefix)]
    if not rng_strats:
        return {}
    metrics_list = []
    for s in rng_strats:
        sub = trades[trades["strategy"] == s]
        if sub.empty:
            continue
        eq = build_equity_curve(trades, start, end, s)
        m = metrics_from_curve(eq, trades, s, cost_bps, slippage_bps)
        metrics_list.append(m)
    if not metrics_list:
        return {}
    df = pd.DataFrame(metrics_list)
    return {
        "strategy": prefix,
        "n_trials": int(len(df)),
        "total_return_mean": float(df["total_return"].mean()),
        "total_return_std": float(df["total_return"].std()),
        "sharpe_mean": float(df["sharpe"].mean()),
        "sharpe_std": float(df["sharpe"].std()),
        "avg_trade_ret_mean": float(df["avg_trade_ret"].mean()),
        "win_rate_mean": float(df["win_rate"].mean()),
    }


def subperiod_metrics(eq: pd.Series, freq: str) -> pd.DataFrame:
    """季度 / 月度 / 年度分段指标。"""
    if eq.empty:
        return pd.DataFrame()
    grp = eq.groupby(pd.Grouper(freq=freq))
    rows = []
    for period, sub_eq in grp:
        if len(sub_eq) < 5:
            continue
        rets = sub_eq.pct_change().dropna()
        if rets.std() < 1e-9:
            sharpe = 0.0
        else:
            sharpe = float(rets.mean() / rets.std() * np.sqrt(252))
        rows.append({
            "period": str(period),
            "start": str(sub_eq.index[0].date()),
            "end": str(sub_eq.index[-1].date()),
            "total_return": float(sub_eq.iloc[-1] / sub_eq.iloc[0] - 1.0),
            "sharpe": sharpe,
            "max_drawdown": float((sub_eq / sub_eq.cummax() - 1.0).min()),
            "n_bdays": int(len(sub_eq)),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global _DAY_SCRATCH, _HORIZON
    args = parse_args()
    _HORIZON = args.realise_horizon
    out_dir = os.path.join(args.out_dir, args.run_tag)
    os.makedirs(out_dir, exist_ok=True)

    rng = np.random.default_rng(args.seed)

    print(f"[load] model={args.model} device={args.device}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(
        model, tokenizer, device=args.device, max_context=args.max_context,
    )

    print(f"[load] pick schedule (source={args.pick_source})")
    schedule = load_pick_schedule(args)
    days = sorted(schedule["date"].unique())
    print(f"[load] {len(schedule)} (date, symbol) pairs across {len(days)} rebalance days")

    symbol_bars: Dict[str, pd.DataFrame] = {}
    if args.pick_source == "qlib":
        for s in schedule["symbol"].unique():
            symbol_bars[s] = load_daily_bars_qlib(s, args.start, args.end)
    else:
        for s in schedule["symbol"].unique():
            symbol_bars[s] = load_daily_bars_csv(s, args.csv_dir)

    all_trades: List[Trade] = []
    for i, day in enumerate(days):
        _DAY_SCRATCH = []
        day_picks = schedule[schedule["date"] == day]
        for _, row in day_picks.iterrows():
            sym = row["symbol"]
            df_hist = symbol_bars.get(sym)
            if df_hist is None or df_hist.empty:
                continue
            try:
                sc = score_one_symbol(
                    predictor, df_hist, sym, pd.Timestamp(day),
                    args.lookback, args.pred_len, args.realise_horizon,
                    args.sample_count, args.T, args.top_p, args.price_limit,
                )
            except Exception as e:
                print(f"  [warn] {sym} {pd.Timestamp(day).date()}: "
                      f"{type(e).__name__}: {e}")
                sc = None
            if sc is not None:
                _DAY_SCRATCH.append(sc)

        day_trades = _build_day_trades(
            _DAY_SCRATCH,
            bottom_k=min(3, args.max_symbols_per_day),
            top_k=min(3, args.max_symbols_per_day),
            mc_trials=args.mc_trials,
            rng=rng,
        )
        all_trades.extend(day_trades)

        # 每日 dumps: 打分明细
        if _DAY_SCRATCH:
            pd.DataFrame([asdict(s) for s in _DAY_SCRATCH]).to_csv(
                os.path.join(out_dir,
                             f"picks_{pd.Timestamp(day).strftime('%Y-%m-%d')}.csv"),
                index=False,
            )
        contr = next((t for t in day_trades if t.strategy == "contrarian"), None)
        bull = next((t for t in day_trades if t.strategy == "bullish"), None)
        if contr and bull:
            print(f"[{i+1:>4}/{len(days)}] {contr.entry_date.strftime('%Y-%m-%d')}  "
                  f"n={contr.n_candidates:>2}  "
                  f"CONTRARIAN {contr.symbol} pred={contr.pred_ret:+.3f} "
                  f"real={contr.real_ret:+.3f} | "
                  f"BULLISH {bull.symbol} pred={bull.pred_ret:+.3f} "
                  f"real={bull.real_ret:+.3f}")

    trades_df = pd.DataFrame([asdict(t) for t in all_trades])
    trades_df = apply_costs_to_trades(trades_df, args.cost_bps, args.slippage_bps)
    trades_df.to_csv(os.path.join(out_dir, "trades.csv"), index=False)
    print(f"\n[save] {len(trades_df)} trade-legs -> {out_dir}/trades.csv")

    # ---- 策略评估 ----------------------------------------------------------
    # 命名策略 vs 蒙特卡洛聚合
    named_strats = ["contrarian", "bullish",
                    f"bottom_{min(3, args.max_symbols_per_day)}",
                    f"top_{min(3, args.max_symbols_per_day)}",
                    "equal_weight"]

    summary: Dict[str, dict] = {}
    eq_curves: Dict[str, pd.Series] = {}

    for strat in named_strats:
        if strat not in trades_df["strategy"].unique():
            continue
        eq = build_equity_curve(trades_df, args.start, args.end, strat)
        eq_curves[strat] = eq
        eq.to_csv(os.path.join(out_dir, f"equity_{strat}.csv"),
                  header=["equity"])
        summary[strat] = metrics_from_curve(
            eq, trades_df, strat, args.cost_bps, args.slippage_bps)

    # 蒙特卡洛 baseline
    mc_random_top = random_baseline_stats(
        trades_df, args.start, args.end,
        f"random_top_{min(3, args.max_symbols_per_day)}_",
        args.cost_bps, args.slippage_bps,
    )
    mc_random_single = random_baseline_stats(
        trades_df, args.start, args.end, "random_single_",
        args.cost_bps, args.slippage_bps,
    )
    summary["random_top_baseline"] = mc_random_top
    summary["random_single_baseline"] = mc_random_single

    # ---- 分段绩效 ----------------------------------------------------------
    sub_rows = []
    for strat, eq in eq_curves.items():
        sp = subperiod_metrics(eq, args.subperiod_freq)
        if sp.empty:
            continue
        sp.insert(0, "strategy", strat)
        sub_rows.append(sp)
    sub_df = pd.concat(sub_rows, ignore_index=True) if sub_rows else pd.DataFrame()
    if not sub_df.empty:
        sub_df.to_csv(os.path.join(out_dir, "subperiods.csv"), index=False)

    # ---- 输出 --------------------------------------------------------------
    out_json = {
        "args": vars(args),
        "n_rebalance_days": len(days),
        "n_unique_candidates": int(
            trades_df.drop_duplicates("symbol")["symbol"].nunique()),
        "total_trade_legs": int(len(trades_df)),
        "round_trip_cost_bps": 2 * (args.cost_bps + args.slippage_bps),
        "strategies": summary,
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(out_json, f, indent=2, default=str)

    # ---- 报告 --------------------------------------------------------------
    print("\n=========== 反指过滤器 OOS 回测汇总 ===========")
    print(f"区间: {args.start} → {args.end}  "
          f"调仓频率: {args.rebalance_freq}  "
          f"调仓次数: {len(days)}  "
          f"候选池大小: ≤{args.max_symbols_per_day}  "
          f"持有期: {args.realise_horizon}B  "
          f"双边成本: {2*(args.cost_bps+args.slippage_bps):.0f} bps")
    print()
    print(f"{'strategy':<14} {'n':>5} {'total':>8} {'CAGR':>8} "
          f"{'sharpe':>7} {'maxDD':>8} {'win%':>6} {'avgTr':>8} {'PF':>6}")
    for s in ["contrarian", "bullish",
              f"bottom_{min(3, args.max_symbols_per_day)}",
              f"top_{min(3, args.max_symbols_per_day)}",
              "equal_weight"]:
        m = summary.get(s)
        if not m or m.get("n_trades", 0) == 0:
            continue
        pf = m.get("profit_factor")
        pf_s = f"{pf:>5.2f}" if pf is not None else "  inf"
        print(f"{s:<14} {m['n_trades']:>5} "
              f"{m['total_return']*100:>7.2f}% "
              f"{m['cagr']*100:>7.2f}% "
              f"{m['sharpe']:>7.2f} "
              f"{m['max_drawdown']*100:>7.2f}% "
              f"{m['win_rate']*100:>5.1f}% "
              f"{m['avg_trade_ret']*100:>7.3f}% {pf_s:>6}")

    # 蒙特卡洛对比
    for key, label in [("random_top_baseline", "random_top_K"),
                       ("random_single_baseline", "random_single")]:
        rb = summary.get(key)
        if not rb:
            continue
        print(f"\n{label} ({rb['n_trials']} 次蒙特卡洛):")
        print(f"  total_return = {rb['total_return_mean']*100:.2f}% ± "
              f"{rb['total_return_std']*100:.2f}%   "
              f"sharpe = {rb['sharpe_mean']:.2f} ± {rb['sharpe_std']:.2f}   "
              f"avg_trade_ret = {rb['avg_trade_ret_mean']*100:.3f}%")

    # 显著性检验 (contrarian vs bullish, 配对 t 检验)
    contr_rets = (trades_df[trades_df["strategy"] == "contrarian"]
                  .sort_values("entry_date")["real_ret_net"].values)
    bull_rets = (trades_df[trades_df["strategy"] == "bullish"]
                 .sort_values("entry_date")["real_ret_net"].values)
    if len(contr_rets) == len(bull_rets) and len(contr_rets) >= 5:
        from scipy.stats import ttest_rel
        diff = contr_rets - bull_rets
        t, p = ttest_rel(contr_rets, bull_rets)
        print(f"\n[paired t-test] contrarian vs bullish (n={len(contr_rets)}): "
              f"diff_mean = {diff.mean()*100:.3f}%   "
              f"t = {t:+.3f}   p = {p:.3f}   "
              f"{'SIGNIFICANT' if p < 0.05 else 'not significant'} @ 5%")

    print(f"\n所有产物已保存到: {out_dir}")


if __name__ == "__main__":
    main()