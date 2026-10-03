#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026 年 9 月回测：用真实日线数据重放生产代码的信号链路。

设计原则
--------
1. **不改生产代码**：通过给三个 analyzer 注入「按日期截断的数据源替身」实现历史重放，
   生产模块一行都不用动。
2. **真实调用链**：策略信号由各自的 analyzer 真实产生（走 scan_all_stocks），
   融合与板块门控真实调用 fusion_runner.fuse_recommendations。
3. **不可复现的部分显式关闭**：新闻情绪（依赖当日 LLM 判定）与财报黑名单
   无法从历史还原，回测中置为中性，并在报告里说明。

输出：backtests/out/<variant>.csv + 控制台摘要
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CACHE = HERE / "cache"
OUT = HERE / "out"
for p in (str(REPO), str(REPO / "common"),
          str(REPO / "strategy-fusion-advisor" / "skills" / "scripts"),
          str(REPO / "Medium-termHoldingStrategy" / "skills" / "scripts"),
          str(REPO / "ma-bullish-strategy" / "skills" / "scripts"),
          str(REPO / "gap-fill-strategy" / "skills" / "scripts"),
          str(REPO / "breakout-high-strategy" / "skills" / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from holdings import to_pure_code, to_sina_code


def _entry_quality_threshold(recs: List[dict], keep_ratio: float) -> float:
    """按当日候选的入场质量分分位取阈值（keep_ratio = 保留比例，如 0.7 保留前 70%）。"""
    vals = sorted(r["entry_quality_score"] for r in recs if r.get("entry_quality_score") is not None)
    if not vals:
        return -1e9
    idx = int(len(vals) * (1.0 - keep_ratio))
    idx = max(0, min(idx, len(vals) - 1))
    return vals[idx]


# ═══════════════════════════════════════════════════════════
# 行情缓存（离线）
# ═══════════════════════════════════════════════════════════

class QuoteCache:
    """把 backtests/cache/*.csv 读进内存，并支持「截至某日」的视图。"""

    def __init__(self, cache_dir: Path = CACHE):
        self.raw: Dict[str, pd.DataFrame] = {}
        for p in sorted(cache_dir.glob("*.csv")):
            try:
                df = pd.read_csv(p)
            except Exception:
                continue
            if df.empty or "date" not in df.columns:
                continue
            df["date"] = df["date"].astype(str).str[:10]
            df = df.sort_values("date").reset_index(drop=True)
            self.raw[p.stem] = df
        dates = set()
        for df in self.raw.values():
            dates.update(df["date"].tolist())
        self.all_dates = sorted(dates)

    def _symbol(self, code: str) -> str:
        c = code.strip()
        return c.lower() if c[:2].lower() in ("sh", "sz") else to_sina_code(c)

    def frame(self, code: str, upto: Optional[str] = None, min_rows: int = 60) -> Optional[pd.DataFrame]:
        df = self.raw.get(self._symbol(code))
        if df is None:
            return None
        if upto is not None:
            df = df[df["date"] <= upto]
        if len(df) < min_rows:
            return None
        out = df.copy()
        out["day"] = pd.to_datetime(out["date"])
        close = out["close"].astype(float)
        for n in (5, 10, 20, 60):
            out[f"ma{n}"] = close.rolling(n).mean()
        return out.reset_index(drop=True)

    def bar(self, code: str, date: str) -> Optional[dict]:
        df = self.raw.get(self._symbol(code))
        if df is None:
            return None
        hit = df[df["date"] == date]
        if hit.empty:
            return None
        return hit.iloc[0].to_dict()

    def days_between(self, start: str, end: str) -> List[str]:
        return [d for d in self.all_dates if start <= d <= end]

    def next_day(self, date: str) -> Optional[str]:
        for d in self.all_dates:
            if d > date:
                return d
        return None

    def forward(self, code: str, date: str, n: int) -> List[dict]:
        df = self.raw.get(self._symbol(code))
        if df is None:
            return []
        fwd = df[df["date"] > date]
        return fwd.head(n).to_dict("records")


# ═══════════════════════════════════════════════════════════
# 数据源替身：让 analyzer 以为自己在看「今天」
# ═══════════════════════════════════════════════════════════

class CacheAdapter:
    """替代 DataSourceAdapter：用缓存数据回答历史查询。"""

    source = "backtest-cache"
    data_source = "backtest"

    def __init__(self, cache: QuoteCache, upto: str):
        self.cache = cache
        self.upto = upto

    def get_stock_data(self, code, start_date=None, end_date=None, **kw):
        return self.cache.frame(code, self.upto)

    def get_stock_list(self):
        return None


def make_realtime_provider(cache: QuoteCache, upto: str):
    """返回一个 get_stock_realtime 替身：(df 截至 upto, 最新一根的行情 dict)。"""

    def _provider(code: str):
        df = cache.frame(code, upto)
        if df is None or df.empty:
            return None, None
        last = df.iloc[-1]
        prev_close = float(df.iloc[-2]["close"]) if len(df) > 1 else float(last["close"])
        current = {
            "code": to_pure_code(code),
            "name": to_pure_code(code),
            "price": float(last["close"]),
            "open": float(last["open"]),
            "high": float(last["high"]),
            "low": float(last["low"]),
            "volume": float(last["volume"]),
            "turnover": float(last.get("amount", 0) or 0),
            "chg_pct": (float(last["close"]) / prev_close - 1) * 100 if prev_close else 0.0,
            "volume_ratio": 1.0,
        }
        return df, current

    return _provider


@contextlib.contextmanager
def patched_analyzers(cache: QuoteCache, upto: str, modules: List):
    """把各 analyzer 模块的数据源整体换成缓存替身，退出时原样还原。"""
    provider = make_realtime_provider(cache, upto)
    saved = []
    for mod in modules:
        saved.append((mod, getattr(mod, "get_stock_realtime", None),
                      getattr(mod, "_HAS_REALTIME", None),
                      getattr(mod, "DataSourceAdapter", None)))
        mod.get_stock_realtime = provider
        mod._HAS_REALTIME = True
        mod.DataSourceAdapter = CacheAdapter
    try:
        yield provider
    finally:
        for mod, rt, has, adapter in saved:
            if rt is not None:
                mod.get_stock_realtime = rt
            if has is not None:
                mod._HAS_REALTIME = has
            if adapter is not None:
                mod.DataSourceAdapter = adapter

# ═══════════════════════════════════════════════════════════
# 板块/大盘 phase（与生产同源：market_phase_detector.judge_single）
# ═══════════════════════════════════════════════════════════

def daily_phases(cache: QuoteCache, day: str):
    """返回 (大盘 phase, {板块: phase}, sectors_detail)。

    sectors_detail 的结构与 market_phase.json 一致，可直接喂给生产的
    fusion_runner.collect_strong_up_etf_recommendations()。
    """
    import market_phase_detector as mpd

    market = "UNKNOWN"
    mdf = cache.frame("sh000300", day)
    if mdf is not None:
        try:
            market, _ = mpd.judge_single(mdf["close"].values, mdf)
        except Exception:
            market = "UNKNOWN"

    sectors: Dict[str, str] = {}
    detail = []
    for sector, etfs in mpd.SECTOR_ETFS.items():
        phase, ind = "UNKNOWN", {}
        df = None
        for code in etfs:
            df = cache.frame(code, day)
            if df is not None:
                break
        if df is not None:
            try:
                phase, ind = mpd.judge_single(df["close"].values, df)
            except Exception:
                phase = "UNKNOWN"
        sectors[sector] = phase
        detail.append({
            "sector": sector,
            "phase": phase,
            "stable_phase": phase,
            "meta": {"etf_codes": list(etfs)},
            "indicator": ind if isinstance(ind, dict) else {},
        })
    return market, sectors, detail


# ═══════════════════════════════════════════════════════════
# 交易模拟
# ═══════════════════════════════════════════════════════════

@dataclass
class Trade:
    date: str
    symbol: str
    name: str
    strategy: str
    score: float
    position_pct: float
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    exit_reason: str
    ret: float


def simulate_trade(cache: QuoteCache, symbol: str, signal_day: str,
                   hold_days: int, stop_pct: float,
                   time_stop: Optional[Tuple[int, float]] = None,
                   trail_pct: float = 0.0,
                   entry_gap_max: Optional[float] = None) -> Optional[Trade]:
    """信号日次日开盘买入，持有 hold_days 个交易日。

    退出优先级（逐日检查，与实盘 14:40 判定一致）：
      1) 盘中触及 stop_pct → 止损
      2) time_stop=(N, min_profit) 且已持有 > N 个交易日且浮盈 < min_profit → 时间止损
      3) 到期按收盘价卖出
    """
    entry_day = cache.next_day(signal_day)
    if entry_day is None:
        return None
    bar = cache.bar(symbol, entry_day)
    if bar is None:
        return None
    entry = float(bar["open"])
    if entry <= 0:
        return None
    if entry_gap_max is not None:
        ref = cache.bar(symbol, signal_day)
        if ref and entry / float(ref["close"]) - 1 > entry_gap_max:
            return None            # 次日跳空过高，放弃追高
    stop_price = entry * (1 + stop_pct)
    peak = entry

    fwd = cache.forward(symbol, entry_day, hold_days)
    if not fwd:
        return None
    for i, row in enumerate(fwd, start=1):
        if trail_pct:
            stop_price = max(stop_price, peak * (1 - trail_pct))
        if float(row["low"]) <= stop_price:
            return Trade(signal_day, symbol, "", "", 0.0, 0.0, entry_day, entry,
                         str(row["date"]), stop_price, "stop", stop_pct)
        if time_stop is not None:
            ts_days, ts_min_profit = time_stop
            close = float(row["close"])
            if i > ts_days and (close / entry - 1) < ts_min_profit:
                return Trade(signal_day, symbol, "", "", 0.0, 0.0, entry_day, entry,
                             str(row["date"]), close, "time_stop", close / entry - 1)
    last = fwd[-1]
    exit_price = float(last["close"])
    return Trade(signal_day, symbol, "", "", 0.0, 0.0, entry_day, entry,
                 str(last["date"]), exit_price, "hold",
                 exit_price / entry - 1)


# ═══════════════════════════════════════════════════════════
# 单日信号生成
# ═══════════════════════════════════════════════════════════

def collect_recommendations(analyzers, day: str, sector_phases: Dict[str, str], gate: bool = True,
                            include_reserve: bool = False, cache=None):
    """cache 不为 None 时，为每条候选附加 entry_quality_score（入场质量分）。"""
    """复用 fusion_runner.scan_strategy 的过滤口径，但由回测驱动。

    include_reserve=True 时同时保留 sector_action == "reserve" 的候选
    （WAVE_UP / RANGE 板块），用于验证"被文档承诺却从未落地的 reserve 路径"。
    """
    import fusion_config as fc
    import fusion_runner as fr
    from market_phase_detector import get_sector_by_stock

    recs = []
    for name, analyzer in analyzers:
        meta = fc.STRATEGY_META.get(name, {})
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                result = analyzer.scan_all_stocks(top_n=50)
        except Exception:
            continue
        if not result:
            continue
        for res in result:
            if res.get("score", 0) < fc.MIN_STRATEGY_SCORE:
                continue
            raw = res.get("stock_code", "")
            sector = res.get("sector", "") or get_sector_by_stock(raw)
            phase = sector_phases.get(sector, "UNKNOWN")
            is_etf = fr._is_etf_code(raw)
            if gate:
                table = fc.PHASE_SECTOR_FILTER_ETF if is_etf else fc.PHASE_SECTOR_FILTER_STOCK
                action = table.get(phase, "block")
                allowed = ("run", "run_low") + (("reserve",) if include_reserve else ())
                if action not in allowed:
                    continue
            else:
                action = "run"   # 对照组：完全不做板块门控
            _ms = None
            if cache is not None:
                try:
                    import entry_quality as _msmod
                    _bars = cache.frame(raw, day, min_rows=61)
                    if _bars is not None and len(_bars) >= 61:
                        _ms = _msmod.entry_quality_score([{
                            "open": float(x["open"]), "high": float(x["high"]),
                            "low": float(x["low"]), "close": float(x["close"]),
                            "volume": float(x["volume"]),
                            "amount": float(x["close"]) * float(x["volume"])}
                            for _, x in _bars.iterrows()])
                except Exception:
                    _ms = None

            recs.append({
                "stock_code": raw[2:] if len(raw) > 6 else raw,
                "entry_quality_score": _ms,
                "raw_code": raw,
                "stock_name": res.get("stock_name", ""),
                "strategy_name": name,
                "strategy_display": meta.get("display", name),
                "strategy_win_rate": meta.get("win_rate", 0.6),
                "strategy_weight": meta.get("weight", 1.0),
                "strategy_score": res.get("score", 70),
                "sector": sector,
                "sector_phase": phase,
                "sector_action": action,
                "sector_phase": phase,
                "reasons": res.get("reasons", ""),
            })
    return recs

# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def build_analyzers():
    """构造三个已启用策略的 analyzer（数据源已由 patched_analyzers 接管）。"""
    import breakout_high_strategy_analyzer as bh
    import gap_fill_strategy_analyzer as gf
    import ma_bullish_strategy_analyzer as mb

    mods = [mb, gf, bh]
    return mods, [("ma-bullish-strategy", mb.MABullishAnalyzer()),
                  ("gap-fill-strategy", gf.GapFillAnalyzer()),
                  ("breakout-high-strategy", bh.BreakoutHighAnalyzer())]


def run(cache: QuoteCache, days: List[str], hold_days: int, stop_pct: float,
        top_n: int, gate: bool = True, cooldown: int = 0,
        include_reserve: bool = False, market_switch: bool = False,
        entry_quality_keep: float = 0.0) -> dict:
    """逐日重放，返回 {day: {"candidates": [...], "all_recs": [...]}}。"""
    import fusion_runner as fr

    result = {}
    cooled: Dict[str, str] = {}          # code -> 上次被推荐的日期
    day_idx: Dict[str, int] = {d: i for i, d in enumerate(days)}
    for i, day in enumerate(days, 1):
        market, sectors, detail = daily_phases(cache, day)

        # 大盘趋势交易开关（生产 fusion_runner 同款规则）
        if market_switch:
            import fusion_config as _fc
            if _fc.MARKET_TRADE_SWITCH.get(market, "off") == "off":
                result[day] = {"market": market, "candidates": [], "all_recs": []}
                print(f"  [{i}/{len(days)}] {day} 大盘={market:12s} 🛑 开关关闭，不开仓")
                continue
        with patched_analyzers(cache, day, [__import__("ma_bullish_strategy_analyzer"),
                                             __import__("gap_fill_strategy_analyzer"),
                                             __import__("breakout_high_strategy_analyzer")]):
            mods, analyzers = build_analyzers()
            for name, a in analyzers:
                a.data_adapter = CacheAdapter(cache, day)
            recs = collect_recommendations(analyzers, day, sectors, gate=gate,
                                           include_reserve=include_reserve, cache=cache)
            if entry_quality_keep > 0 and recs:
                _thr = _entry_quality_threshold(recs, entry_quality_keep)
                _before = len(recs)
                recs = [r for r in recs
                        if r.get("entry_quality_score") is None or r["entry_quality_score"] >= _thr]
                if len(recs) != _before:
                    print(f"  [入场质量分] {day} {_before} → {len(recs)} 条（阈值 {_thr:.3f}）")

        with contextlib.redirect_stdout(io.StringIO()):
            with patch_fusion_neutral():
                # 显式传 0：冷却期由回测自己重放，避免读写真实推荐历史
                cands = fr.fuse_recommendations(recs, top_n=9999, session="EVENING",
                                                cooldown_days=0)
                # 与生产一致：追加 STRONG_UP 板块的 ETF 推荐
                etf_recs = (fr.collect_strong_up_etf_recommendations(
                    {"phase": market, "sectors_detail": detail}) if gate else [])
                if etf_recs:
                    cands = sorted(cands + etf_recs,
                                   key=lambda x: x.get("combined_score", 0), reverse=True)


        # ── 冷却期重放（不回填）：先取 top_n，再剔除冷却期内的标的 ──
        if cooldown > 0:
            sel, dropped = [], 0
            for c in cands[:top_n]:
                code = c.get("stock_code") or c.get("code", "")
                last = cooled.get(code)
                if last is not None and day_idx[day] - day_idx.get(last, -10 ** 6) < cooldown:
                    dropped += 1
                    continue
                sel.append(c)
            if dropped:
                print(f"  [冷却期] {day} 剔除 {dropped} 只")
            for c in sel:
                cooled[c.get("stock_code") or c.get("code", "")] = day
            cands = sel

        result[day] = {"market": market, "candidates": cands, "all_recs": recs}
        print(f"  [{i}/{len(days)}] {day} 大盘={market:12s} 原始信号={len(recs):3d} 通过门控={len(cands):3d}")
    return result


@contextlib.contextmanager
def patch_fusion_neutral():
    """回测中关闭无法历史还原的外部依赖：新闻情绪、财报黑名单、持仓加分。"""
    import fusion_runner as fr

    saved = (fr.news_penalty, fr.dangerous_stocks, fr.load_holded_sectors)
    fr.news_penalty = lambda code, name: (0, [])
    fr.dangerous_stocks = lambda: []
    fr.load_holded_sectors = lambda: set()
    try:
        yield
    finally:
        fr.news_penalty, fr.dangerous_stocks, fr.load_holded_sectors = saved


def legacy_order(cands: List[dict], all_recs: List[dict]) -> List[dict]:
    """复现修复前的排序：只看截断后的 combined_score，并列时按信号到达顺序。

    修复前 fuse_recommendations 用 `sorted(key=combined_score)`（稳定排序），
    而 scored 是按「首次出现顺序」生成的，因此并列时的次序就是该顺序。
    """
    order: Dict[str, int] = {}
    for r in all_recs:
        code = r.get("stock_code", "")
        if code and code not in order:
            order[code] = len(order)
    return sorted(cands, key=lambda x: (-x["combined_score"], order.get(x["stock_code"], 10 ** 9)))


def to_trades(cache: QuoteCache, picks: List[dict], day: str,
              hold_days: int, stop_pct: float,
              time_stop: Optional[Tuple[int, float]] = None,
              trail_pct: float = 0.0,
              entry_gap_max: Optional[float] = None) -> List[Trade]:
    trades = []
    for pick in picks:
        symbol = pick.get("raw_code") or to_sina_code(pick["stock_code"])
        t = simulate_trade(cache, symbol, day, hold_days, stop_pct, time_stop=time_stop,
                           trail_pct=trail_pct, entry_gap_max=entry_gap_max)
        if t is None:
            continue
        t.name = pick.get("stock_name", "")
        t.strategy = "/".join(pick.get("strategies", []) or [])
        t.score = pick.get("combined_score", 0.0)
        t.position_pct = pick.get("position_pct", 0.0)
        trades.append(t)
    return trades


def monthly_breakdown(trades: List[Trade]) -> List[str]:
    """按信号月份聚合，用来观察策略对不同市场环境的适应性。"""
    buckets: Dict[str, List[Trade]] = {}
    for tr in trades:
        buckets.setdefault(tr.date[:7], []).append(tr)
    lines = []
    for month in sorted(buckets):
        rows = buckets[month]
        rets = [x.ret for x in rows]
        win = sum(1 for r in rets if r > 0) / len(rets) * 100
        lines.append(f"    {month}   {len(rows):>4} 笔   {win:>5.1f}%   "
                     f"{statistics.mean(rets) * 100:>+7.2f}%   "
                     f"{statistics.median(rets) * 100:>+7.2f}%")
    return lines


def summarise(trades: List[Trade], label: str) -> dict:
    closed = [t for t in trades if t.exit_reason != "open"]
    if not closed:
        return {"variant": label, "trades": 0, "win_rate": 0.0, "avg": 0.0, "median": 0.0}
    rets = [t.ret for t in closed]
    wins = [r for r in rets if r > 0]
    return {
        "variant": label,
        "trades": len(closed),
        "win_rate": len(wins) / len(closed) * 100,
        "avg": statistics.mean(rets) * 100,
        "median": statistics.median(rets) * 100,
        "best": max(rets) * 100,
        "worst": min(rets) * 100,
        "stop_count": sum(1 for t in closed if t.exit_reason == "stop"),
        "stop_ratio": sum(1 for t in closed if t.exit_reason == "stop") / len(closed) * 100,
        "time_stop_count": sum(1 for t in closed if t.exit_reason == "time_stop"),
    }

def main():
    ap = argparse.ArgumentParser(description="2026 年 9 月回测")
    ap.add_argument("--start", default="2026-09-01")
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--hold", type=int, default=5, help="持有交易日数 T+N")
    ap.add_argument("--stop", type=float, default=-0.05, help="止损比例，如 -0.05")
    ap.add_argument("--top", type=int, default=5, help="每日取前 N 名")
    ap.add_argument("--ungated", action="store_true", help="关闭板块门控（对照组）")
    ap.add_argument("--time-stop", action="store_true",
                    help="启用优先级9 时间止损（持仓>10日且浮盈<5% 清仓）")
    ap.add_argument("--ts-days", type=int, default=10)
    ap.add_argument("--ts-profit", type=float, default=0.05)
    ap.add_argument("--report", default="", help="把摘要写入指定 UTF-8 文件")
    ap.add_argument("--dump-candidates", default="",
                    help="把每日全部候选（含分数与来源）导出为 pickle，供离线做重排序实验")
    ap.add_argument("--entry-quality", type=float, default=0.0,
                    help="入场质量分过滤：保留分位前 N（如 0.7 保留前 70%%）；0=不过滤")
    ap.add_argument("--market-switch", action="store_true",
                    help="启用大盘趋势交易开关（STRONG_DOWN/WEAK_DOWN/UNKNOWN 不开仓）")
    ap.add_argument("--include-reserve", action="store_true",
                    help="把 WAVE_UP/RANGE 板块的候选也纳入（验证 reserve 路径）")
    ap.add_argument("--cooldown", type=int, default=0,
                    help="信号冷却期：同一标的 N 个交易日内只接受首次信号")
    ap.add_argument("--prod-exit", action="store_true",
                    help="直接采用生产出场配置（fusion_config.EXIT_* 与 ENTRY_MAX_GAP_UP）")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    cache = QuoteCache()
    days = cache.days_between(args.start, args.end)
    print(f"回测区间 {args.start} → {args.end}，共 {len(days)} 个交易日；"
          f"持有 T+{args.hold}，止损 {args.stop:.0%}，每日取 {args.top} 名")
    print(f"板块门控: {'关闭（对照组）' if args.ungated else '开启'}")
    print("-" * 78)

    ts = (args.ts_days, args.ts_profit) if args.time_stop else None
    trail_pct, gap_max = 0.0, None
    if args.prod_exit:
        import fusion_config as fc
        args.hold = fc.EXIT_MAX_HOLD_DAYS
        args.stop = -fc.EXIT_STOP_PCT
        trail_pct = fc.EXIT_TRAIL_PCT
        gap_max = fc.ENTRY_MAX_GAP_UP
        print(f"生产出场配置：T+{args.hold} / {args.stop:.0%} 止损 / 移动 {trail_pct:.0%} / "
              f"跳空 >{gap_max:.0%} 放弃")
    if args.cooldown:
        print(f"信号冷却期：{args.cooldown} 个交易日内同一标的只取首次")
    _play = run(cache, days, args.hold, args.stop, args.top, gate=not args.ungated,
                cooldown=args.cooldown, include_reserve=args.include_reserve,
                market_switch=args.market_switch,
                entry_quality_keep=args.entry_quality)
    play = _play

    if args.dump_candidates:
        import pickle
        slim = {d: {"market": v["market"], "candidates": [
                    {k: c.get(k) for k in ("stock_code", "stock_name", "combined_score",
                                           "rank_score", "best_score", "strategy_count",
                                           "strategies", "sectors", "sector_action",
                                           "is_etf", "raw_code", "price")}
                    for c in v["candidates"]]}
                for d, v in _play.items()}
        with open(args.dump_candidates, "wb") as f:
            pickle.dump(slim, f)
        print(f"候选已导出: {args.dump_candidates}（{len(slim)} 个交易日，"
              f"合计 {sum(len(v['candidates']) for v in slim.values())} 条）")


    # ── 三种口径的交易 ──────────────────────────────
    fixed_all, legacy_all, etf_all = [], [], []
    for day, info in play.items():
        cands = info["candidates"]
        if not cands:
            continue
        fixed_picks = cands[: args.top]
        legacy_picks = legacy_order(cands, info["all_recs"])[: args.top]
        fixed_all += to_trades(cache, fixed_picks, day, args.hold, args.stop, time_stop=ts,
                         trail_pct=trail_pct, entry_gap_max=gap_max)
        legacy_all += to_trades(cache, legacy_picks, day, args.hold, args.stop, time_stop=ts,
                         trail_pct=trail_pct, entry_gap_max=gap_max)
        etf_picks = [c for c in cands if c.get("is_etf")]
        etf_all += to_trades(cache, etf_picks[: args.top], day, args.hold, args.stop, time_stop=ts,
                         trail_pct=trail_pct, entry_gap_max=gap_max)

    stats = [summarise(fixed_all, "修复后（rank_score 排序）"),
             summarise(legacy_all, "修复前（combined_score 排序）"),
             summarise(etf_all, "仅 ETF 口径")]

    print()
    print("=" * 78)
    print("回测结果（9 月，T+%d / %.0f%% 止损）" % (args.hold, args.stop * 100))
    print("=" * 78)
    header = f"{'口径':<28}{'笔数':>6}{'胜率':>8}{'均值':>9}{'中位':>9}{'最好':>9}{'最差':>9}{'止损占比':>10}"
    print(header)
    for s in stats:
        print(f"{s['variant']:<28}{s.get('trades',0):>6}{s.get('win_rate',0):>7.1f}%"
              f"{s.get('avg',0):>8.2f}%{s.get('median',0):>8.2f}%{s.get('best',0):>8.2f}%"
              f"{s.get('worst',0):>8.2f}%{s.get('stop_ratio',0):>9.1f}%")

    # 逐日明细
    print()
    print("逐日通过门控的候选数：")
    for day, info in play.items():
        names = ", ".join(f"{c['stock_name'] or c['stock_code']}({c['combined_score']:.1f})"
                          for c in info["candidates"][:5])
        print(f"  {day}  {info['market']:<12} {len(info['candidates']):>3}  {names}")

    # 落盘
    if args.dump_candidates:
        return

    tag = "ungated" if args.ungated else "gated"
    if args.time_stop:
        tag += "_timestop"
    if args.start[:7] != "2026-09":
        tag += f"_{args.start}_{args.end}"
    csv_path = OUT / f"trades_{tag}_T{args.hold}.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "signal_date", "symbol", "name", "strategy", "score",
                    "entry_date", "entry_price", "exit_date", "exit_price", "reason", "ret"])
        for label, trades in (("fixed", fixed_all), ("legacy", legacy_all), ("etf", etf_all)):
            for t in trades:
                w.writerow([label, t.date, t.symbol, t.name, t.strategy, round(t.score, 2),
                            t.entry_date, t.entry_price, t.exit_date, t.exit_price,
                            t.exit_reason, round(t.ret, 4)])
    print()
    print(f"明细已写入: {csv_path}")

    if args.report:
        lines = [f"回测区间 {args.start} → {args.end}  持有 T+{args.hold}  止损 {args.stop:.0%}  "
                 f"每日取 {args.top} 名  门控={'关' if args.ungated else '开'}  "
                 f"时间止损={'开' if args.time_stop else '关'}",
                 "",
                 f"{'口径':<28}{'笔数':>6}{'胜率':>8}{'均值':>9}{'中位':>9}{'最好':>9}{'最差':>9}{'止损占比':>10}{'时间止损':>10}"]
        for s in stats:
            lines.append(f"{s['variant']:<28}{s.get('trades',0):>6}{s.get('win_rate',0):>7.1f}%"
                         f"{s.get('avg',0):>8.2f}%{s.get('median',0):>8.2f}%{s.get('best',0):>8.2f}%"
                         f"{s.get('worst',0):>8.2f}%{s.get('stop_ratio',0):>9.1f}%"
                         f"{s.get('time_stop_count',0):>10}")
        fixed_closed = [x for x in fixed_all]
        lines += ["", "逐月表现（修复后口径）：",
                  f"    {'月份':<8}{'笔数':>8}{'胜率':>9}{'均值':>10}{'中位':>10}"]
        lines += monthly_breakdown(fixed_closed)
        lines += ["", "逐日通过门控的候选数："]
        for day, info in play.items():
            names = ", ".join(f"{c['stock_name'] or c['stock_code']}({c['combined_score']:.1f})"
                              for c in info["candidates"][:5])
            lines.append(f"  {day}  {info['market']:<12} {len(info['candidates']):>3}  {names}")
        Path(args.report).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
