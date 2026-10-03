#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# 公共运行环境：被所有 run_*.sh source
#
# 设计要点：
#   1. 所有路径从本文件位置推导，不再出现 /home/jarvis/... 硬编码；
#   2. Python 解释器可用 STOCK_PYTHON 覆盖（部署机常需要指定 conda 环境）；
#   3. 统一清代理：akshare / pytdx 在代理环境下经常连不上；
#   4. 统一退出码汇报：124 = timeout 终止，其他非 0 = 异常。
#
# 可用环境变量：
#   STOCK_PYTHON  Python 解释器（默认 python3）
#   STOCK_ROOT    仓库根目录（默认本文件的上两级）
# ─────────────────────────────────────────────────────────────

_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STOCK_ROOT="${STOCK_ROOT:-$(cd "$_COMMON_DIR/.." && pwd)}"
STOCK_PYTHON="${STOCK_PYTHON:-python3}"

FUSION_SCRIPTS="$STOCK_ROOT/strategy-fusion-advisor/skills/scripts"
HOLDING_SCRIPTS="$STOCK_ROOT/Medium-termHoldingStrategy/skills/scripts"

# 清空代理变量
unset ALL_PROXY all_proxy http_proxy https_proxy HTTP_PROXY HTTPS_PROXY \
      FTP_PROXY ftp_proxy SOCKS_PROXY socks_proxy 2>/dev/null || true

# report_exit <脚本名> <退出码>：统一的中文错误提示
report_exit() {
    local name="$1" code="$2"
    if [ "$code" -eq 124 ]; then
        echo "[WARN] $name 被 timeout 终止"
    elif [ "$code" -ne 0 ]; then
        echo "[ERROR] $name 异常退出: $code"
    fi
    return 0
}

# require_file <路径> <说明>：启动前做一次存在性校验，避免在远端才炸
require_file() {
    if [ ! -e "$1" ]; then
        echo "[ERROR] 缺少 $2: $1"
        exit 2
    fi
}
