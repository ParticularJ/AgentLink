#!/bin/bash
# earnings-surprise-strategy/setup.sh

set -e

echo "========================================="
echo "财报超预期策略安装脚本"
echo "========================================="

# 安装依赖
pip install -r requirements.txt

# 创建配置目录
mkdir -p ~/.openclaw/config

# 复制配置文件
cp ../config/*.yaml ~/.openclaw/config/

echo "安装完成！"