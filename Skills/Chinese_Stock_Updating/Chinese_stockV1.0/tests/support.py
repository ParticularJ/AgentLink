#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试支撑：路径引导、可选依赖打桩、合成数据工厂。

原则：
  1. 测试必须能在离线环境跑通（不联网、不依赖 akshare/pytdx 等重型数据源）；
  2. 缺失的第三方库用最小可用替身（test double）补齐，而不是跳过整组用例；
  3. 测试用 unittest 编写（pytest 也能直接收集），保证任何环境都有 runner。
"""
from __future__ import annotations

import sys
import types
from pathlib import Path


# ═══════════════════════════════════════════════════════════
# 路径引导（与生产代码同一套规则）
# ═══════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMON_DIR = REPO_ROOT / "common"

for _p in (str(REPO_ROOT), str(COMMON_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

for _mod_dir in (
    REPO_ROOT / "strategy-fusion-advisor" / "skills" / "scripts",
    REPO_ROOT / "Medium-termHoldingStrategy" / "skills" / "scripts",
    REPO_ROOT / "ma-bullish-strategy" / "skills" / "scripts",
    REPO_ROOT / "gap-fill-strategy" / "skills" / "scripts",
    REPO_ROOT / "breakout-high-strategy" / "skills" / "scripts",
):
    if str(_mod_dir) not in sys.path:
        sys.path.append(str(_mod_dir))


def install_optional_stubs() -> None:
    """为缺失的重型依赖注册最小替身，让被测模块能被 import。

    只补齐「import 期就需要存在」的名字；真正需要联网的调用在测试里不会被触发。
    """
    stubs = {
        "akshare": lambda: _make_module("akshare", tool_trade_date_hist_sina=_ak_trade_calendar),
        "pytdx": lambda: _make_package("pytdx", {"hq": _make_module("pytdx.hq")}),
        "baostock": lambda: _make_module("baostock"),
        "tushare": lambda: _make_module("tushare"),
        "yfinance": lambda: _make_module("yfinance"),
        "colorama": lambda: _make_module("colorama", Fore=_Fore(), Style=_Style(), init=lambda **_: None),
        "bs4": lambda: _make_package("bs4", {"BeautifulSoup": _BeautifulSoup}),
    }
    for name, factory in stubs.items():
        try:
            __import__(name)
        except ImportError:
            sys.modules[name] = factory()


def silence_library_output() -> None:
    """测试期间关掉共享库的过程输出（[备份]/[写入] 等）。"""
    try:
        import holdings
        holdings.VERBOSE = False
    except Exception:  # pragma: no cover
        pass


def _make_module(name: str, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def _make_package(name: str, children: dict):
    pkg = types.ModuleType(name)
    pkg.__path__ = []  # 标记为包
    for child_name, child in children.items():
        setattr(pkg, child_name, child)
        sys.modules[f"{name}.{child_name}"] = child
    return pkg


def _ak_trade_calendar(*_a, **_k):
    import pandas as pd

    return pd.DataFrame({"trade_date": pd.date_range("2024-01-01", periods=400, freq="B")})


class _Fore:
    RED = GREEN = YELLOW = CYAN = RESET_ALL = ""


class _Style:
    BRIGHT = RESET_ALL = ""


class _BeautifulSoup:  # noqa: N801 - 模拟 bs4 API
    def __init__(self, html: str = "", parser: str = "html.parser"):
        self.html = html

    def get_text(self, *_a, **_k) -> str:
        return self.html


# ═══════════════════════════════════════════════════════════
# 合成数据工厂
# ═══════════════════════════════════════════════════════════

def make_kline(closes, volumes=None, start: str = "2024-01-01"):
    """由收盘价序列生成标准 K 线 DataFrame（day/open/high/low/close/volume）。"""
    import pandas as pd

    closes = [float(c) for c in closes]
    if volumes is None:
        volumes = [1_000_000] * len(closes)
    rows = []
    for i, close in enumerate(closes):
        prev = closes[i - 1] if i else close
        rows.append({
            "open": prev,
            "high": max(prev, close) * 1.01,
            "low": min(prev, close) * 0.99,
            "close": close,
            "volume": float(volumes[i]),
        })
    df = pd.DataFrame(rows)
    df.insert(0, "day", pd.date_range(start, periods=len(closes), freq="B"))
    return df


def linear_closes(n: int, start: float = 10.0, step: float = 0.2):
    """单调上涨序列。"""
    return [start + step * i for i in range(n)]


def wave_closes(n: int, base: float = 10.0, amplitude: float = 0.5, period: int = 20):
    """正弦震荡序列（用于 RANGE 判定）。"""
    import math

    return [base + amplitude * math.sin(2 * math.pi * i / period) for i in range(n)]


# ═══════════════════════════════════════════════════════════
# 临时文件工厂
# ═══════════════════════════════════════════════════════════

def write_holdings(dir_path, holdings, filename: str = "holdings.json") -> str:
    """把持仓写进临时目录，返回文件路径。"""
    import json

    path = Path(dir_path) / filename
    path.write_text(json.dumps(holdings, ensure_ascii=False), encoding="utf-8")
    return str(path)


def sample_holdings():
    """一条结构完整的持仓样本（字段与生产 holdings.json 一致）。"""
    return [{
        "code": "600584",
        "name": "长电科技",
        "cost": 30.0,
        "real_cost": 30.0,
        "shares": 1000,
        "init_shares": 1000,
        "current_price": 33.0,
        "highest_price": 34.0,
        "entry_date": "2026-01-05",
        "strategy_name": "均线多头排列",
        "score": 72.0,
        "stop_level_hit": [False, False, False],
        "stop_lose_hit": [False, False, False, False],
        "add_count": 0,
        "last_add_date": "2026-01-05",
    }]


install_optional_stubs()
silence_library_output()
