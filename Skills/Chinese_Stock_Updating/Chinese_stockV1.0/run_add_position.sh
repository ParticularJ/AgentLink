#!/usr/bin/env bash
# 加仓策略执行 (14:40)
# 路径 / 解释器 / 代理清理统一由 scripts/_common.sh 处理，本脚本不含任何绝对路径。
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/_common.sh"

cd "$HOLDING_SCRIPTS"
PYTHONPATH="$HOLDING_SCRIPTS" \
  timeout 300 "$STOCK_PYTHON" add_position_analyzer.py --feishu 2>&1
report_exit "Medium-termHoldingStrategy" $?
