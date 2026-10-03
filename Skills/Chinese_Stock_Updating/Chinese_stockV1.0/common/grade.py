#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个股分级（L1 行业龙头 / L2 细分龙头 / L3 题材跟风）相关的纯函数。

分级表本身属于策略参数，保留在 Medium-termHoldingStrategy/skills/scripts/config.py，
这里通过参数注入，好处是：
  - common 层不反向依赖某个策略目录（分层清晰）
  - 测试时可以直接传入构造好的表，无需 import 整个策略配置

历史问题：add_position_analyzer 与 position_monitor 各写了一份 _get_stock_grade
和 _get_first_profit_target，且后者语义还不一致（一个返回百分比数字，
一个返回整张 profit_targets 列表），调用时极易搞错。这里用明确的函数名区分开。
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping

DEFAULT_GRADE = "L3_题材跟风"


def stock_grade(code6: str, stock_grade_table: Mapping[str, str]) -> str:
    """返回个股等级，未登记时按最低等级处理。"""
    return stock_grade_table.get(code6, DEFAULT_GRADE)


def grade_config(code6: str,
                 stock_grade_table: Mapping[str, str],
                 grade_config_table: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    """返回个股等级对应的配置块。"""
    grade = stock_grade(code6, stock_grade_table)
    config = grade_config_table.get(grade) or grade_config_table[DEFAULT_GRADE]
    # 必须深拷贝：内部含 profit_targets / sell_ratio 这类列表，
    # 浅拷贝会让调用方无意中改到全局配置表。
    return copy.deepcopy(config)


def profit_targets(code6: str,
                   stock_grade_table: Mapping[str, str],
                   grade_config_table: Mapping[str, Dict[str, Any]]) -> List[float]:
    """该股的分档止盈目标（比例，如 [0.10, 0.19, 0.30]）。"""
    return list(grade_config(code6, stock_grade_table, grade_config_table)["profit_targets"])


def first_profit_target_pct(code6: str,
                            stock_grade_table: Mapping[str, str],
                            grade_config_table: Mapping[str, Dict[str, Any]]) -> float:
    """第 1 档止盈目标，换算成百分数（如 10.0 表示 +10%）。"""
    return profit_targets(code6, stock_grade_table, grade_config_table)[0] * 100
