#!/bin/bash
# ma-bullish-strategy/setup.sh

set -e

echo "========================================="
echo "均线多头排列策略安装脚本"
echo "========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查OpenClaw是否安装
if ! command -v openclaw &> /dev/null; then
    echo -e "${RED}错误: OpenClaw未安装${NC}"
    echo "请先安装OpenClaw: https://github.com/openclaw/openclaw"
    exit 1
fi

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_DIR="${HOME}/.openclaw"

echo -e "${GREEN}安装目录: ${SCRIPT_DIR}${NC}"

# 1. 安装Python依赖
echo -e "\n${YELLOW}[1/6] 安装Python依赖...${NC}"
pip install -r requirements.txt

# 2. 创建OpenClaw目录结构
echo -e "\n${YELLOW}[2/6] 创建目录结构...${NC}"
mkdir -p "${OPENCLAW_DIR}/agents"
mkdir -p "${OPENCLAW_DIR}/config"
mkdir -p "${OPENCLAW_DIR}/crons"
mkdir -p "${OPENCLAW_DIR}/workspace/skills"
mkdir -p "${OPENCLAW_DIR}/data/reports/ma-bullish"
mkdir -p "${OPENCLAW_DIR}/data/logs"

# 3. 复制Agent配置
echo -e "\n${YELLOW}[3/6] 复制Agent配置...${NC}"
cp "${SCRIPT_DIR}/agents/ma-bullish-agent.yaml" "${OPENCLAW_DIR}/agents/"

# 4. 复制配置文件
echo -e "\n${YELLOW}[4/6] 复制策略配置...${NC}"
cp "${SCRIPT_DIR}/config/"*.yaml "${OPENCLAW_DIR}/config/"

# 5. 复制Skill
echo -e "\n${YELLOW}[5/6] 复制Skill...${NC}"
mkdir -p "${OPENCLAW_DIR}/workspace/skills/ma-bullish-strategy"
cp -r "${SCRIPT_DIR}/skills/ma-bullish-strategy/scripts" "${OPENCLAW_DIR}/workspace/skills/ma-bullish-strategy/"
cp "${SCRIPT_DIR}/skills/ma-bullish-strategy/SKILL.md" "${OPENCLAW_DIR}/workspace/skills/ma-bullish-strategy/"

# 6. 导入定时任务
echo -e "\n${YELLOW}[6/6] 导入定时任务...${NC}"
read -p "是否导入定时任务? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    openclaw cron import "${SCRIPT_DIR}/cron/ma-bullish-crons.yaml"
    echo -e "${GREEN}定时任务已导入${NC}"
fi

# 验证安装
echo -e "\n${GREEN}========================================="
echo "安装完成！"
echo "=========================================${NC}"

echo -e "\n快速测试:"
echo "  cd ${OPENCLAW_DIR}/workspace/skills/ma-bullish-strategy"
echo "  python3 scripts/ma_analyzer.py --stock 000001 --name 平安银行"

echo -e "\n查看Agent:"
echo "  openclaw agent list"

echo -e "\n查看定时任务:"
echo "  openclaw cron list"

echo -e "\n${YELLOW}提示: 请确保已配置数据源Token${NC}"