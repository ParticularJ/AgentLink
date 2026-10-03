#!/usr/bin/env bash
# 盘中交易询问-尾盘 (15:00)
# 路径 / 解释器 / 代理清理统一由 scripts/_common.sh 处理，本脚本不含任何绝对路径。
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/_common.sh"

cd "$STOCK_ROOT"
"$STOCK_PYTHON" "$STOCK_ROOT/scripts/trade_query.py" evening 2>&1
report_exit "trade_query.py" $?
