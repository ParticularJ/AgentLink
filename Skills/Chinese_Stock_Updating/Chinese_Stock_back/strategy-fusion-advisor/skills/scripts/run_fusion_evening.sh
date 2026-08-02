unset ALL_PROXY all_proxy http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
#!/bin/bash
# 13:50 执行尾盘融合策略（带超时保护）
cd /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back
# 超时40分钟强制终止，防止网络卡死
timeout 2400  /home/jarvis/miniconda3/envs/vllm/bin/python /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/strategy-fusion-advisor/skills/scripts/fusion_runner.py --session EVENING 2>&1

exit_code=$?
if [ $exit_code -eq 139 ]; then
    echo "[WARN] fusion_runner 被超时终止 (SIGKILL)"
elif [ $exit_code -ne 0 ]; then
    echo "[ERROR] fusion_runner 异常退出: $exit_code"
fi
