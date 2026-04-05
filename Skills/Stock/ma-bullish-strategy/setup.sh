#!/bin/bash
# 均线多头排列策略 - 安装脚本

set -e

echo "🚀 开始安装均线多头排列策略..."

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "📌 Python 版本: $PYTHON_VERSION"

# 安装依赖
echo "📦 安装 Python 依赖..."
pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt

# 创建数据目录
echo "📁 创建数据目录..."
mkdir -p ~/.openclaw/stock/ma-bullish/data
mkdir -p ~/.openclaw/stock/ma-bullish/logs

# 设置权限
chmod +x skills/ma_bullish/scripts/*.py 2>/dev/null || true

echo "✅ 安装完成！"
echo ""
echo "使用方法:"
echo "  1. 扫描全市场:   python skills/ma_bullish/scripts/ma_analyzer.py --scan"
echo "  2. 分析单只股票: python skills/ma_bullish/scripts/ma_analyzer.py --stock 000001"
echo "  3. 显示前10名:   python skills/ma_bullish/scripts/ma_analyzer.py --scan --top 10"
