#!/bin/bash
# A股涨停板连板分析系统 - 安装脚本

set -e

echo "🚀 开始安装 A股涨停板连板分析系统..."

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "📌 Python 版本: $PYTHON_VERSION"

# 安装依赖
echo "📦 安装 Python 依赖..."
pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt

# 创建数据目录
echo "📁 创建数据目录..."
mkdir -p ~/.openclaw/stock/data/history
mkdir -p ~/.openclaw/stock/data/cache
mkdir -p ~/.openclaw/stock/logs
mkdir -p ~/.openclaw/stock/config

# 复制配置文件
echo "⚙️  配置系统..."
if [ -f "config/scoring_weights.yaml" ]; then
    cp config/scoring_weights.yaml ~/.openclaw/stock/config/scoring_weights.yaml
fi

# 设置权限
chmod +x skills/limit_up/scripts/*.py 2>/dev/null || true

echo "✅ 安装完成！"
echo ""
echo "使用方法:"
echo "  1. 分析单只股票: python skills/limit_up/scripts/analyzer.py --code 000001"
echo "  2. 分析当日涨停: python skills/limit_up/scripts/analyzer.py --all"
echo "  3. 分析并保存:   python skills/limit_up/scripts/analyzer.py --all --save"
echo "  4. 显示前20名:   python skills/limit_up/scripts/analyzer.py --all --top 20"
echo "  5. 查看历史分析: python skills/limit_up/scripts/analyzer.py --history 2024-01-15"
