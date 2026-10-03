#!/usr/bin/env bash
# 收盘后融合策略（15:05）
#
# 用户需求 3：所有策略都在当天市场结束后统一运行，数据完整（当日 K 线已定型），
# 一次跑完全部已启用策略（缺口填充 / 均线多头 / 突破新高）再融合推荐。
# 推荐 JSON 中每条都带 conditional_orders（可直接填入券商 APP 的智能条件单参数）。
# 路径 / 解释器 / 代理清理统一由 scripts/_common.sh 处理，本脚本不含任何绝对路径。
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/_common.sh"

cd "$STOCK_ROOT"
timeout 2400 "$STOCK_PYTHON" "$FUSION_SCRIPTS/fusion_runner.py" --session CLOSE 2>&1
report_exit "fusion_runner(CLOSE)" $?
