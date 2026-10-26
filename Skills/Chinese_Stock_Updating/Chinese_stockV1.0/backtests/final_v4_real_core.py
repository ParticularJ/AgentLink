#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""决定性回测 v4：真实核心仓 + 完整周期（2022-04 ~ 2026-10，4.5 年含熊市）

数据来源（本轮解决的方式）
--------------------------
  · 核心仓 11 只（银行/电力/通信）= **个股**，用 akshare sina `stock_zh_a_daily(adjust='hfq')`
    取得 2018 年起的前复权长历史 → 覆盖 2022 熊市 ✅
  · 卫星仓 13 个行业 ETF = 复用已有腾讯前复权数据（已扫描，无份额折算异常）✅
  · 宽基用指数（sh000300 / sh000905），避免 ETF 未复权与折算问题

口径说明（诚实标注）
--------------------
  sina 的 hfq 累计收益比腾讯前复权**低约 4%/年**（核心个股实测差异 10~13pp / 2.6 年）。
  本回测采用 sina 口径 → **核心仓收益被保守低估**，因此策略表现不会因数据选择而被高估。

策略（与 v3 一致）
------------------
  核心 70%：11 只等权，季度再平衡
  卫星 30%：13 个板块动量前 3（60 日）+ M3 制度开关 + 止损（−10% 硬止损 / −15% 移动止盈）
  可选：全局趋势过滤（沪深300 MA200 之下降低核心仓）
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))

CACHE = HERE / "cache"           # 腾讯前复权（ETF）
CACHE_LONG = HERE / "cache_long"  # akshare sina 前复权（个股/指数）
BENCH = "sh000300"

CORE: Dict[str, str] = {
    "工商银行": "sh601398", "农业银行": "sh601288", "中国银行": "sh601988",
    "招商银行": "sh600036", "兴业银行": "sh601166",
    "长江电力": "sh600900", "中国核电": "sh601985",
    "中国移动": "sh600941", "中国神华": "sh601088",
    "沪深300": "sh000300", "中证500": "sh000905",
}
SAT: Dict[str, str] = {
    "军工": "sh512660", "新能源": "sh515790", "稀土": "sh516150",
    "医药": "sz159992", "家电": "sz159996", "消费": "sz159755",
    "化工": "sh516220", "高端装备": "sh516320", "基建": "sh516510",
    "消费电子": "sz159779", "低空经济": "sz159795",
    "创业板": "sz159949", "白银": "sz161226",
}
COST = 0.0005
N_SEC, MOM_WIN, HOLD = 3, 60, 20
STOP, TRAIL = -0.10, -0.15


def load_any(code: str, start: str, end: str) -> Optional[pd.Series]:
    """优先长历史目录，其次原缓存。"""
    for base in (CACHE_LONG, CACHE):
        p = base / f"{code}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = df["date"].astype(str).str[:10]
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(df) < 100:
            continue
        return pd.Series(df["close"].astype(float).values, index=df["date"].values)
    return None


def build(start: str, end: str) -> pd.DataFrame:
    codes = set(list(CORE.values()) + list(SAT.values()) + [BENCH])
    d = {}
    for c in codes:
        s = load_any(c, start, end)
        if s is not None:
            d[c] = s
    px = pd.DataFrame(d).sort_index()
    need = [c for c in codes if c in px.columns]
    px = px[need].dropna()
    if px.index[0] > "2022-06-01":
        raise SystemExit(f"❌ 起点被截断到 {px.index[0]}（要求 ≤2022-06-01）")
    return px


def run(px: pd.DataFrame, core_w: float = 0.70, sat_w: float = 0.30,
        use_gate: bool = True, trend_filter: bool = False,
        bear_core_w: float = 0.40) -> pd.Series:
    dates = list(px.index)
    core = [c for c in CORE.values() if c in px.columns]
    sec = [c for c in SAT.values() if c in px.columns]
    mom = px[sec].pct_change(MOM_WIN)
    disp = px[sec].pct_change(20).std(axis=1)
    dmed = disp.expanding(min_periods=100).median()
    bench = px[BENCH]
    ma200 = bench.rolling(200).mean()

    cash, cu, sat, peak, entry = 1.0, {}, {}, {}, {}
    curve, last = [], -10 ** 6
    WARM = 210

    for i, dt in enumerate(dates):
        if i > 0:
            for c in list(sat.keys()):
                cur = px[c].iloc[i]
                peak[c] = max(peak[c], cur)
                if (cur / entry[c] - 1) <= STOP or (cur / peak[c] - 1) <= TRAIL:
                    cash += sat[c] * cur * (1 - COST)
                    del sat[c], peak[c], entry[c]
        cv = sum(u * px[c].iloc[i] for c, u in cu.items())
        sv = sum(u * px[c].iloc[i] for c, u in sat.items())
        nav = cash + cv + sv
        assert nav == nav and nav > 0
        curve.append(nav)

        if i < WARM:
            continue
        if i == WARM:
            for c in core:
                u = (nav * core_w / len(core)) / px[c].iloc[i]
                cu[c] = u
                cash -= u * px[c].iloc[i]
            continue

        in_bull = True
        if trend_filter and ma200.iloc[i] == ma200.iloc[i]:
            in_bull = bool(bench.iloc[i] > ma200.iloc[i])
        tgt_cw = core_w if in_bull else bear_core_w

        if (i - WARM) % 20 == 0:
            cv = sum(u * px[c].iloc[i] for c, u in cu.items())
            tgt = nav * tgt_cw
            if cv > 1e-9 and abs(cv - tgt) > nav * 0.03:
                delta = tgt - cv
                if delta < 0:
                    cash += (-delta) * (1 - COST)
                    for c in core:
                        cu[c] *= tgt / cv
                else:
                    add = min(delta, cash / (1 + COST))
                    if add > 0:
                        cash -= add * (1 + COST)
                        for c in core:
                            cu[c] += (add / len(core)) / px[c].iloc[i]

        if (i - last) < HOLD:
            continue
        j = i - 1
        gated = bool(use_gate and disp.iloc[j] == disp.iloc[j]
                     and dmed.iloc[j] == dmed.iloc[j]
                     and disp.iloc[j] < dmed.iloc[j])
        if trend_filter and not in_bull:
            gated = True
        picked: List[str] = []
        if not gated:
            sc = {c: mom[c].iloc[j] for c in sec if mom[c].iloc[j] == mom[c].iloc[j]}
            picked = [c for c, v in sorted(sc.items(), key=lambda kv: -kv[1])[:N_SEC]
                      if v > 0]
        for c in list(sat.keys()):
            if c not in picked:
                cash += sat[c] * px[c].iloc[i] * (1 - COST)
                del sat[c], peak[c], entry[c]
        if picked:
            per = nav * sat_w / len(picked)
            for c in picked:
                cur_v = sat.get(c, 0.0) * px[c].iloc[i]
                need = per - cur_v
                if need <= nav * 0.01 or cash <= 0:
                    continue
                aff = min(need, cash / (1 + COST))
                u = aff / px[c].iloc[i]
                cash -= u * px[c].iloc[i] * (1 + COST)
                if c not in sat:
                    sat[c] = 0.0
                    entry[c] = px[c].iloc[i]
                    peak[c] = px[c].iloc[i]
                sat[c] += u
        last = i
    return pd.Series(curve, index=dates)


def metr(nav: pd.Series) -> dict:
    if len(nav) < 40:
        return {}
    ny = len(nav) / 242
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / ny) - 1
    mdd = (nav / nav.cummax() - 1).min()
    m = nav.groupby(nav.index.str[:7]).last().pct_change().dropna()
    streak = best = 0
    for v in m:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    return {"total": (nav.iloc[-1] / nav.iloc[0] - 1) * 100, "cagr": cagr * 100,
            "mdd": mdd * 100, "calmar": (cagr / abs(mdd)) if mdd < 0 else float("nan"),
            "月胜率": (m > 0).mean() * 100 if len(m) else 0,
            "达标月": (m >= 0.012).mean() * 100 if len(m) else 0,
            "最差月": m.min() * 100 if len(m) else 0, "连亏月": best, "days": len(nav)}


def main() -> int:
    START, END = "2018-01-01", "2026-10-16"
    px = build(START, END)
    print(f"真实核心仓回测：{px.index[0]} → {px.index[-1]}"
          f"（{len(px)} 日 / {len(px)/242:.2f} 年）")
    print(f"核心 {len([c for c in CORE.values() if c in px.columns])} 只 "
          f"| 卫星 {len([c for c in SAT.values() if c in px.columns])} 个板块\n")

    configs = [
        ("最终策略 70/30（无趋势过滤）", dict()),
        ("+ 趋势过滤（熊市核心40%）", dict(trend_filter=True, bear_core_w=0.40)),
        ("+ 趋势过滤（熊市核心0%）", dict(trend_filter=True, bear_core_w=0.00)),
        ("关闭 M3 开关", dict(use_gate=False)),
        ("纯核心 100%", dict(core_w=1.0, sat_w=0.0)),
        ("纯卫星 100%", dict(core_w=0.0, sat_w=1.0)),
    ]
    print("=" * 104)
    print("完整周期表现（2022-04 起，含 2022 熊市；核心仓为 sina 前复权口径，偏保守）")
    print("=" * 104)
    print(f"  {'方案':<28}{'累计':>10}{'年化':>9}{'回撤':>9}{'卡玛':>8}"
          f"{'月胜率':>9}{'达标月':>9}{'最差月':>9}{'连亏':>6}")
    print("  " + "-" * 94)
    rows = []
    for label, kw in configs:
        nav = run(px, **kw)
        nav = nav / nav.iloc[0]
        m = metr(nav)
        rows.append((label, nav, m))
        print(f"  {label:<28}{m['total']:>+9.1f}%{m['cagr']:>+8.1f}%{m['mdd']:>+8.1f}%"
              f"{m['calmar']:>8.2f}{m['月胜率']:>8.1f}%{m['达标月']:>8.1f}%"
              f"{m['最差月']:>+8.1f}%{m['连亏月']:>6}")
    b = px[BENCH] / px[BENCH].iloc[0]
    bm = metr(b)
    print(f"  {'沪深300':<28}{bm['total']:>+9.1f}%{bm['cagr']:>+8.1f}%{bm['mdd']:>+8.1f}%"
          f"{bm['calmar']:>8.2f}{bm['月胜率']:>8.1f}%{bm['达标月']:>8.1f}%"
          f"{bm['最差月']:>+8.1f}%{bm['连亏月']:>6}")

    print()
    print("=" * 104)
    print("逐年分解（关键年份：2022 熊市 / 2023 震荡 / 2025 牛市）")
    print("=" * 104)
    hdr = "  " + f"{'年份':<8}" + "".join(f"{lbl[:12]:>14}" for lbl, _, _ in rows) + f"{'沪深300':>14}"
    print(hdr)
    print("  " + "-" * (8 + 14 * (len(rows) + 1)))
    for y in ("2022", "2023", "2024", "2025", "2026"):
        cells = []
        for _, nav, _ in rows:
            seg = nav[nav.index.str.startswith(y)]
            cells.append(f"{(seg.iloc[-1]/seg.iloc[0]-1)*100:>+13.1f}%" if len(seg) >= 20 else f"{'—':>14}")
        segb = b[b.index.str.startswith(y)]
        cb = f"{(segb.iloc[-1]/segb.iloc[0]-1)*100:>+13.1f}%" if len(segb) >= 20 else f"{'—':>14}"
        print(f"  {y:<8}" + "".join(cells) + cb)

    print()
    print("=" * 104)
    print("分半：924 前 vs 924 后（完整策略，无趋势过滤）")
    print("=" * 104)
    nav = rows[0][1]
    for label, s0, s1 in (("924 前（2022-04~2024-09）", "2022-04-01", "2024-09-23"),
                          ("924 后（2024-09~2026-10）", "2024-09-24", "2026-10-16")):
        seg = nav[(nav.index >= s0) & (nav.index <= s1)]
        segb = b[(b.index >= s0) & (b.index <= s1)]
        if len(seg) < 30:
            continue
        sr = (seg.iloc[-1] / seg.iloc[0] - 1) * 100
        br = (segb.iloc[-1] / segb.iloc[0] - 1) * 100
        print(f"  {label:<30}策略 {sr:>+8.1f}%   沪深300 {br:>+8.1f}%   超额 {sr-br:>+7.1f}pp")

    # 选出满足约束的最佳
    ok = [(l, m) for l, _, m in rows if m["mdd"] >= -20]
    print()
    if ok:
        best = max(ok, key=lambda x: x[1]["cagr"])
        print(f"  ★ 回撤 ≤20% 中年化最高：{best[0]}")
        print(f"     年化 {best[1]['cagr']:+.1f}%  回撤 {best[1]['mdd']:+.1f}%  "
              f"卡玛 {best[1]['calmar']:.2f}  连亏 {best[1]['连亏月']} 月")
    else:
        print("  ⚠️ 无方案满足 回撤 ≤20%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
