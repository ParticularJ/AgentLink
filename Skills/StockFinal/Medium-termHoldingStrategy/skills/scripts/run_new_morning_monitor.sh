#!/bin/bash
# 早盘持仓监控（09:20）- 新止损策略
cd /home/qinliming/.openclaw/plugin-skills/AgentLink/Skills/StockFinal/Medium-termHoldingStrategy/skills/scripts
PYTHONPATH=/home/qinliming/.openclaw/plugin-skills/AgentLink/Skills/StockFinal/Medium-termHoldingStrategy/skills/scripts \
timeout 180 /usr/bin/python3 new_holding_monitor.py MORNING 2>&1
exit_code=$?
if [ $exit_code -ne 0 ]; then
    echo "[ERROR] new_holding_monitor.py 异常退出: $exit_code"
fi