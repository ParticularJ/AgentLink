#!/bin/bash
# 加仓策略执行 (14:40)
unset ALL_PROXY all_proxy http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
cd /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/Medium-termHoldingStrategy/skills/scripts
PYTHONPATH=/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/Medium-termHoldingStrategy/skills/scripts \
timeout 300 /home/jarvis/miniconda3/envs/vllm/bin/python add_position_analyzer.py --feishu 2>&1
exit_code=$?
if [ $exit_code -eq 139 ]; then
    echo "[WARN] add_position_analyzer.py 被超时终止"
elif [ $exit_code -ne 0 ]; then
    echo "[ERROR] add_position_analyzer.py 异常退出: $exit_code"
fi