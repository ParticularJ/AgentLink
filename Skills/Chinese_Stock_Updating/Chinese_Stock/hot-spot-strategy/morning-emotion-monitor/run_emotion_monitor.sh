#!/bin/bash
# 早盘情绪交易监控启动脚本
# 用法:
#   bash run_emotion_monitor.sh               # 实时循环监控（早盘）
#   bash run_emotion_monitor.sh --once        # 单次查询
#   bash run_emotion_monitor.sh --feishu     # 实时监控+飞书推送
#   BUY_WATCH_PATH=/path/to.yaml bash run_emotion_monitor.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills/scripts"

# 默认值
BUY_WATCH_PATH="${BUY_WATCH_PATH:-}"
HOLDINGS_PATH="${HOLDINGS_PATH:-/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json}"

# Python路径
PYTHON_CMD="${PYTHON_CMD:-python3}"

# 默认值
DURATION="${DURATION:-300}"

# 构建命令
CMD=(
    "$PYTHON_CMD"
    "$SKILLS_DIR/emotion_monitor.py"
    --holdings "$HOLDINGS_PATH"
    --interval 15
    --duration "$DURATION"
)

if [[ -n "$BUY_WATCH_PATH" ]]; then
    CMD+=(--buy-watch "$BUY_WATCH_PATH")
fi

# 追加可选参数
if [[ "$*" == *"--once"* ]]; then
    CMD+=(--once)
fi

if [[ "$*" == *"--feishu"* ]]; then
    CMD+=(--feishu)
fi

echo "🚀 早盘情绪监控启动"
echo "📁 持仓文件: $HOLDINGS_PATH"
echo "📁 买入观察: $BUY_WATCH_PATH"
echo "⏱️  运行时长: ${DURATION}分钟"
echo "▶️  命令: ${CMD[*]}"
echo ""

# 进入脚本目录再执行（确保相对路径正确）
cd "$SCRIPT_DIR"

# 激活 conda 环境（优先使用 vllm）
if command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
    conda activate vllm || echo "⚠️  未找到 conda 环境 vllm，继续使用当前 Python"
fi

eval "${CMD[@]}"
