#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一路径配置 —— 全工程唯一的路径来源（Single Source of Truth）。

为什么需要它
------------
旧代码把 /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/... 这样的绝对路径
硬编码在十几个脚本里，换机器 / 换目录 / 换仓库名就整体失效。
本模块把所有路径从「本文件位置」向上推导，并允许用环境变量覆盖。

用法
----
任何需要路径的脚本，加 4 行引导代码即可：

    import os, sys
    _root = os.path.abspath(os.path.dirname(__file__))
    while not os.path.exists(os.path.join(_root, "common", "paths.py")) and _root != os.path.dirname(_root):
        _root = os.path.dirname(_root)
    sys.path.insert(0, os.path.join(_root, "common"))
    from paths import HOLDINGS_FILE, CASH_FILE, LOG_DIR   # noqa: E402

可用环境变量覆盖
----------------
STOCK_ROOT              仓库根目录（默认自动推导）
STOCK_LOG_DIR           日志目录（默认 <root>/logs）
STOCK_HOLDINGS_FILE     持仓文件
STOCK_CASH_FILE         现金文件
STOCK_ANALYSIS_LOG_DIR  加仓分析日志目录
STOCK_RECO_DIR          推荐输出目录
STOCK_WATCHLIST_FILE    股票池文件
"""

from __future__ import annotations

import os
from pathlib import Path


def _detect_root() -> Path:
    """从本文件位置向上找仓库根目录（同时含 my_holdings/ 与 strategy-fusion-advisor/ 的那一层）。"""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "my_holdings").is_dir() and (candidate / "strategy-fusion-advisor").is_dir():
            return candidate
    # 兜底：common/ 的上一级
    return here.parent.parent


def _env_path(name: str, default: Path) -> Path:
    """环境变量优先，其次用默认值。"""
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else Path(default)


ROOT: Path = _env_path("STOCK_ROOT", _detect_root())

# ── 持仓 / 资金 ──────────────────────────────────────────
HOLDINGS_DIR: Path = _env_path("STOCK_HOLDINGS_DIR", ROOT / "my_holdings")
HOLDINGS_FILE: Path = _env_path("STOCK_HOLDINGS_FILE", HOLDINGS_DIR / "holdings.json")
CASH_FILE: Path = _env_path("STOCK_CASH_FILE", HOLDINGS_DIR / "cash_balance.json")
BACKUP_DIR: Path = HOLDINGS_DIR / "backup"
ANALYSIS_LOG_DIR: Path = _env_path("STOCK_ANALYSIS_LOG_DIR", HOLDINGS_DIR / "analysis_logs")

# ── 股票池 ──────────────────────────────────────────────
POOL_DIR: Path = ROOT / "my_stock_pool"
WATCHLIST_FILE: Path = _env_path("STOCK_WATCHLIST_FILE", POOL_DIR / "watchlist.yaml")
WATCHLIST_CORE_FILE: Path = POOL_DIR / "watchlist_core.yaml"

# ── 推荐 / 行情状态 ─────────────────────────────────────
RECO_DIR: Path = _env_path("STOCK_RECO_DIR", ROOT / "recommendations")
FUSION_DIR: Path = ROOT / "strategy-fusion-advisor"
FUSION_SCRIPTS_DIR: Path = FUSION_DIR / "skills" / "scripts"
MARKET_PHASE_FILE: Path = FUSION_DIR / "recommendations" / "market_phase.json"
MARKET_PHASE_CACHE_DIR: Path = FUSION_DIR / "recommendations" / "cache"
STABLE_PHASE_FILE: Path = MARKET_PHASE_CACHE_DIR / "stable_phase.json"

# ── 日志 ────────────────────────────────────────────────
LOG_DIR: Path = _env_path("STOCK_LOG_DIR", ROOT / "logs")

# ── 持仓监控脚本目录 ────────────────────────────────────
HOLDING_SCRIPTS_DIR: Path = ROOT / "Medium-termHoldingStrategy" / "skills" / "scripts"

# 需要预建的运行期目录
_RUNTIME_DIRS = (
    HOLDINGS_DIR,
    BACKUP_DIR,
    ANALYSIS_LOG_DIR,
    RECO_DIR,
    LOG_DIR,
    MARKET_PHASE_CACHE_DIR,
)


def strategy_dir(name: str) -> Path:
    """返回某个策略的根目录（含 skills/ 的那一层）。"""
    return ROOT / name


def ensure_dirs() -> None:
    """创建运行期需要的目录（幂等，可重复调用）。"""
    for d in _RUNTIME_DIRS:
        d.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":  # 自检：python common/paths.py
    print(f"ROOT = {ROOT}")
    for key in sorted(k for k in globals() if k.isupper() and isinstance(globals()[k], Path)):
        print(f"  {key:24s} {globals()[key]}")
