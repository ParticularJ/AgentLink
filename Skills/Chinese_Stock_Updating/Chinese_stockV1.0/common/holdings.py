#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持仓 / 现金文件的读写、备份与原子写入。

这一层解决三处历史重复：
  - main.py / add_position_analyzer.py / send_holding_card.py 各自实现了一遍 load/save
  - add_position_analyzer.py / main.py 各自实现了一遍 backup_file
  - add_position_analyzer.py / position_monitor.py 各自实现了一遍 _to_sina_code

约定：
  - 读操作只读，不修改文件；文件缺失时返回默认值而不是抛异常（cron 场景更稳）；
  - 写操作一律「先备份 → 写临时文件 → 原子替换」，保证 holdings.json 不会写坏。
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

# 是否把 [备份]/[写入] 等过程信息打到 stdout。
# 生产环境保持 True（cron 日志里有用），单元测试置为 False 以免污染输出。
VERBOSE = True

try:  # 常规：common 目录已在 sys.path 上
    from paths import CASH_FILE, HOLDINGS_FILE
except ImportError:  # 以包形式导入（from common import holdings）
    from .paths import CASH_FILE, HOLDINGS_FILE


# ═══════════════════════════════════════════════════════════
# 代码规范化
# ═══════════════════════════════════════════════════════════

def to_pure_code(code: str) -> str:
    """去掉 sh/sz 前缀，返回 6 位纯代码。

    注意：不要用 lstrip("sh")——lstrip 按字符集剥离，
    会把 000001 之外的边界情况弄错（如 "shh600" 之类）。
    """
    c = (code or "").strip()
    if c[:2].lower() in ("sh", "sz", "bj"):
        return c[2:]
    return c


def to_sina_code(code: str) -> str:
    """6 位代码 → 新浪/腾讯行情接口需要的 sh/sz 前缀格式。

    沪市：6(主板/科创) 5(ETF/基金) 8/9(科创板/北交所沪市部分)；
    深市：0(主板) 3(创业板) 4/1(ETF/基金)。
    """
    pure = to_pure_code(code)
    if pure.startswith(("6", "5", "8", "9")):
        return "sh" + pure
    return "sz" + pure


# ═══════════════════════════════════════════════════════════
# 读
# ═══════════════════════════════════════════════════════════

def _say(msg: str) -> None:
    """统一的（可关闭的）过程输出。"""
    if VERBOSE:
        print(msg)


def load_json(path, default: Any = None) -> Any:
    """读取 JSON；文件缺失或损坏时返回 default，并打印一条警告。"""
    if default is None:
        default = {}
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        _say(f"[警告] 文件不存在: {path}")
    except json.JSONDecodeError as e:
        _say(f"[警告] JSON 解析失败: {path}: {e}")
    return default


def load_holdings(path=None) -> List[Dict[str, Any]]:
    """读取持仓列表；文件缺失或内容非列表时返回空列表。"""
    data = load_json(path or HOLDINGS_FILE, [])
    return data if isinstance(data, list) else []


def load_cash(path=None) -> Dict[str, Any]:
    """读取现金余额；文件缺失或内容非字典时返回空字典。"""
    data = load_json(path or CASH_FILE, {})
    return data if isinstance(data, dict) else {}


def holding_codes(path=None) -> Set[str]:
    """持仓代码集合（纯 6 位），用于扫描时排除已持仓标的。"""
    return {to_pure_code(h.get("code", "")) for h in load_holdings(path) if h.get("code")}


def find_holding(code: str, holdings: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """按代码查找持仓，兼容 6 位码与 sh/sz 前缀写法。"""
    target = to_pure_code(code)
    if holdings is None:
        holdings = load_holdings()
    for h in holdings:
        if to_pure_code(h.get("code", "")) == target:
            return h
    return None


# ═══════════════════════════════════════════════════════════
# 备份 / 原子写
# ═══════════════════════════════════════════════════════════

def backup_file(target_path, backup_dir=None) -> bool:
    """把 target_path 复制到同目录 backup/ 下（文件名带时间戳）。

    返回 True 表示「已备份」或「无需备份」，False 表示备份失败（调用方可继续）。
    """
    target = str(target_path)
    if not os.path.exists(target):
        _say(f"[备份跳过] 文件不存在: {target}")
        return True
    directory = str(backup_dir) if backup_dir else os.path.join(os.path.dirname(target), "backup")
    os.makedirs(directory, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(directory, f"{ts}_{os.path.basename(target)}")
    try:
        shutil.copy2(target, backup_path)
        _say(f"[备份] {target}\n     → {backup_path}")
        return True
    except OSError as e:
        _say(f"[备份警告] 备份失败: {e}（继续执行写入）")
        return False


def atomic_write_json(path, data: Any, indent: int = 2) -> None:
    """先备份 → 写临时文件 → 原子替换，避免写一半崩溃导致持仓丢失。"""
    target = str(path)
    backup_file(target)
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=directory, suffix=".json",
                                         delete=False) as tmp:
            tmp_path = tmp.name
            json.dump(data, tmp, ensure_ascii=False, indent=indent)
        os.replace(tmp_path, target)
    except BaseException:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    _say(f"[写入] {target}")


def save_holdings(holdings: List[Dict[str, Any]], path=None) -> None:
    """保存持仓（先备份 → 原子写入）。"""
    atomic_write_json(path or HOLDINGS_FILE, holdings)


def save_cash(data: Dict[str, Any], path=None) -> None:
    """保存现金余额（先备份 → 原子写入）。"""
    atomic_write_json(path or CASH_FILE, data)
