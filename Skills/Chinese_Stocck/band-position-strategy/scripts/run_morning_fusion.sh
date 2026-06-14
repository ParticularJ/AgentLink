#!/bin/bash
# 早盘融合策略 (08:00)
unset ALL_PROXY all_proxy http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
cd /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back
timeout 2400 /home/jarvis/miniconda3/envs/vllm/bin/python /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/strategy-fusion-advisor/skills/scripts/fusion_runner.py --session MORNING 2>&1
exit_code=$?
if [ $exit_code -eq 139 ]; then
    echo "[WARN] fusion_runner 被超时终止 (SIGKILL)"
elif [ $exit_code -ne 0 ]; then
    echo "[ERROR] fusion_runner 异常退出: $exit_code"
fi