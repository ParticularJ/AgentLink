#!/usr/bin/env bash
# 每日持仓条件单（收盘后 15:10）
#
# 用户需求 5：记录已买入的持仓，每天按大盘/板块行情动态给出
# 可直接填入券商 APP 的条件单形式止盈止损。
# 路径 / 解释器 / 代理清理统一由 scripts/_common.sh 处理，本脚本不含任何绝对路径。
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/_common.sh"

cd "$STOCK_ROOT"
timeout 900 "$STOCK_PYTHON" "$STOCK_ROOT/Medium-termHoldingStrategy/skills/scripts/daily_stop_plan.py" 2>&1
report_exit "daily_stop_plan" $?
