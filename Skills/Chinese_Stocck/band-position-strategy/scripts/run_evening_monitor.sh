#!/bin/bash
# 持仓监控尾盘 (14:50)
unset ALL_PROXY all_proxy http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
cd /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/Medium-termHoldingStrategy/skills/scripts
PYTHONPATH=/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/Medium-termHoldingStrategy/skills/scripts \
timeout 120 /home/jarvis/miniconda3/envs/vllm/bin/python send_holding_card.py evening 2>&1
exit_code=$?
if [ $exit_code -ne 0 ]; then
    echo "[ERROR] send_holding_card.py 异常退出: $exit_code"
fi