#!/bin/bash
# 中期持有策略早盘 (09:15)
unset ALL_PROXY all_proxy http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
cd /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/Medium-termHoldingStrategy/skills/scripts
PYTHONPATH=/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/Medium-termHoldingStrategy/skills/scripts \
timeout 300 /home/jarvis/miniconda3/envs/vllm/bin/python main.py 2>&1
exit_code=$?
if [ $exit_code -eq 139 ]; then
    echo "[WARN] main.py 被超时终止"
elif [ $exit_code -ne 0 ]; then
    echo "[ERROR] main.py 异常退出: $exit_code"
fi