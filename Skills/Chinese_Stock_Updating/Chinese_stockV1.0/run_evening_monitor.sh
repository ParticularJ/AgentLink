#!/usr/bin/env bash
# 持仓监控尾盘 (14:50)
# 路径 / 解释器 / 代理清理统一由 scripts/_common.sh 处理，本脚本不含任何绝对路径。
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/_common.sh"

cd "$HOLDING_SCRIPTS"
PYTHONPATH="$HOLDING_SCRIPTS" \
  timeout 120 "$STOCK_PYTHON" send_holding_card.py evening 2>&1
report_exit "Medium-termHoldingStrategy" $?
