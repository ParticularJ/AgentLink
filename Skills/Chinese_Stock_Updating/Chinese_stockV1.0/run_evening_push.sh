#!/usr/bin/env bash
# 尾盘推荐飞书推送 (14:35)
# 路径 / 解释器 / 代理清理统一由 scripts/_common.sh 处理，本脚本不含任何绝对路径。
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/_common.sh"

cd "$STOCK_ROOT"
PYTHONPATH="$FUSION_SCRIPTS" \
  "$STOCK_PYTHON" "$FUSION_SCRIPTS/send_feishu_card.py" evening 2>&1
report_exit "send_feishu_card" $?
