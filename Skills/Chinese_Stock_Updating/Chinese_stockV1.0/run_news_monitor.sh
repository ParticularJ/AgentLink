#!/usr/bin/env bash
# 股池新闻利空盯盘 (08:00)
# 路径 / 解释器 / 代理清理统一由 scripts/_common.sh 处理，本脚本不含任何绝对路径。
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/_common.sh"

cd "$STOCK_ROOT"
timeout 2400 "$STOCK_PYTHON" "$FUSION_SCRIPTS/news_watchlist_scanner.py" 2>&1
report_exit "fusion_runner" $?
