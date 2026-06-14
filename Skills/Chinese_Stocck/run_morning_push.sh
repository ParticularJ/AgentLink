#!/bin/bash
# 早盘推荐飞书推送 (08:30)
unset ALL_PROXY all_proxy http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
cd /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back
PYTHONPATH=/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/strategy-fusion-advisor/skills/scripts \
/home/jarvis/miniconda3/envs/vllm/bin/python /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/strategy-fusion-advisor/skills/scripts/send_feishu_card.py morning 2>&1
exit_code=$?
if [ $exit_code -ne 0 ]; then
    echo "[ERROR] send_feishu_card MORNING 失败: $exit_code"
fi