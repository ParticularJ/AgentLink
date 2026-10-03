#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票池 (my_stock_pool/watchlist.yaml) 的统一读取。

原来 9 个扫描器各自实现了内容完全相同的 _load_watchlist()，且都依赖
相对当前工作目录的路径（./my_stock_pool/... 或 ../../../my_stock_pool/...），
换个目录运行就静默返回 None。这里改为由 common/paths.py 提供绝对路径。

支持两种 sector 写法（历史文件两种都出现过）：

    sector:            # 标准写法
      core:  [[名称, 代码], ...]
      focus: [[名称, 代码], ...]

    sector:            # 旧写法 / ETF 段
      level: B         # 非列表字段会被安全跳过
      core:  [...]
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

try:
    from paths import WATCHLIST_CORE_FILE, WATCHLIST_FILE
except ImportError:
    from .paths import WATCHLIST_CORE_FILE, WATCHLIST_FILE

CATEGORIES = ("core", "focus")


def _load_yaml(path) -> Dict[str, Any]:
    """延迟导入 yaml：没有 pyyaml 时给出可读的错误而不是 ImportError 堆栈。"""
    try:
        import yaml
    except ImportError as e:  # pragma: no cover - 取决于运行环境
        raise RuntimeError("读取股票池需要 pyyaml，请先 pip install pyyaml") from e
    with open(str(path), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_watchlist_entries(path=None) -> List[Dict[str, str]]:
    """读取股票池，返回 [{name, code, sector, category}, ...]。

    容错点（历史数据里真实出现过）：
      - sector 下可能有 level: B 这类非列表字段 -> 跳过，不当成股票
      - category 可能是空列表 -> 跳过
      - 条目必须是 [名称, 代码] 形式的长度 >= 2 的列表
    """
    target = str(path or WATCHLIST_FILE)
    data = _load_yaml(target)
    entries: List[Dict[str, str]] = []
    for sector, value in (data.get("watchlist") or {}).items():
        if isinstance(value, dict):
            groups = [(c, value.get(c)) for c in CATEGORIES]
        elif isinstance(value, list):
            groups = [("core", value)]
        else:
            continue  # level: B 之类的标量字段
        for category, items in groups:
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    entries.append({
                        "name": str(item[0]),
                        "code": str(item[1]),
                        "sector": str(sector),
                        "category": category,
                    })
    return entries


def load_watchlist_codes(path=None) -> Set[str]:
    """股票池代码集合（保留原始前缀，调用方按需用 holdings.to_pure_code 规范化）。"""
    return {e["code"] for e in load_watchlist_entries(path)}


def load_watchlist_df(path=None):
    """兼容旧接口：返回含 code/name 两列的 DataFrame（需要 pandas）。"""
    import pandas as pd  # 延迟导入，便于无 pandas 环境做纯逻辑测试

    entries = load_watchlist_entries(path)
    if not entries:
        return None
    return pd.DataFrame([{"code": e["code"], "name": e["name"]} for e in entries])


def load_core_watchlist(path=None) -> List[Dict[str, str]]:
    """核心股池（watchlist_core.yaml），供新闻盯盘使用。"""
    return load_watchlist_entries(path or WATCHLIST_CORE_FILE)
