#!/bin/bash
# CXMT首日作战矩阵监控运行脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 默认参数
STOCK_CODE="${CXMT_CODE:-688825}"
ISSUE_PRICE="${CXMT_PRICE:-8.66}"
THRESHOLD="${CXMT_THRESHOLD:-29.4}"
TOTAL_FUND="${CXMT_FUND:-200000}"
INTERVAL="${CXMT_INTERVAL:-10}"
FEISHU_ENABLED="${CXMT_FEISHU:-true}"
PUSH_INTERVAL="${CXMT_PUSH_INTERVAL:-10}"

echo "=========================================="
echo "CXMT首日作战矩阵监控"
echo "股票代码: $STOCK_CODE"
echo "发行价: ${ISSUE_PRICE}元"
echo "240%线: ${THRESHOLD}元"
echo "总资金: $((TOTAL_FUND/10000))万"
echo "刷新间隔: ${INTERVAL}秒"
echo "飞书推送: $FEISHU_ENABLED (间隔${PUSH_INTERVAL}秒)"
echo "=========================================="

if command -v conda >/dev/null 2>&1; then
    CONDA_BASE="$(conda info --base 2>/dev/null || true)"
    if [ -n "$CONDA_BASE" ] && [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
        . "$CONDA_BASE/etc/profile.d/conda.sh"
        conda activate vllm >/dev/null 2>&1 || echo "Warning: 无法激活 conda 环境 vllm，使用当前 Python 环境继续"
    fi
fi

PYCMD="python3 skills/scripts/cxmt_firstday_monitor.py \
    --code $STOCK_CODE \
    --price $ISSUE_PRICE \
    --threshold $THRESHOLD \
    --fund $TOTAL_FUND \
    --interval $INTERVAL \
    --push-interval $PUSH_INTERVAL"

if [ "$FEISHU_ENABLED" = "true" ]; then
    PYCMD="$PYCMD --feishu"
fi

eval $PYCMD
