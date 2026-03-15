#!/bin/bash
# OpenClaw WSL Ubuntu 管理脚本
# 支持: 安装 | 更新 | 卸载 | 配置 | 状态检查 | 重启服务

set -e

# 颜色定义
RED='\e[0;31m'
GREEN='\e[0;32m'
YELLOW='\e[1;33m'
BLUE='\e[0;34m'
CYAN='\e[0;36m'
NC='\e[0m'

# 配置变量
OPENCLAW_VERSION="latest"
GATEWAY_PORT=18789
CONFIG_DIR="$HOME/.openclaw"
CONFIG_FILE="$CONFIG_DIR/openclaw.json"

# OpenClaw 要求的最低 Node.js 版本
REQUIRED_NODE_VERSION="22.16.0"
REQUIRED_NODE_MAJOR=22
REQUIRED_NODE_MINOR=16
REQUIRED_NODE_PATCH=0

# 打印消息
print_msg() {
    local color=$1
    local msg=$2
    printf "${color}%s${NC}\n" "$msg"
}

# 显示帮助
show_help() {
    printf "${CYAN}🦞 OpenClaw WSL Ubuntu 管理脚本${NC}\n\n"
    printf "${GREEN}用法:${NC} %s [选项]\n\n" "$0"
    printf "${YELLOW}选项:${NC}\n"
    printf "    install, i      安装 OpenClaw（首次安装或完整重装）\n"
    printf "    update, u       更新 OpenClaw 到最新版本\n"
    printf "    uninstall, rm   完全卸载 OpenClaw 并清理配置\n"
    printf "    configure, c    重新配置 OpenClaw（修改 API Key/端口等）\n"
    printf "    status, s       检查 OpenClaw 运行状态\n"
    printf "    restart, r      重启 OpenClaw 网关服务\n"
    printf "    logs, l         查看实时日志\n"
    printf "    doctor, d       运行诊断检查\n"
    printf "    node-fix, n     修复 Node.js 版本（升级到 22.16.0+）\n"
    printf "    help, h         显示此帮助信息\n\n"
    printf "${YELLOW}示例:${NC}\n"
    printf "    %s install      # 首次安装\n" "$0"
    printf "    %s node-fix     # 修复 Node 版本问题\n" "$0"
    printf "    %s configure    # 修改配置\n\n" "$0"
    printf "${GREEN}配置文件:${NC} %s\n" "$CONFIG_FILE"
    printf "${GREEN}网关地址:${NC} http://127.0.0.1:%s\n" "$GATEWAY_PORT"
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 版本比较函数：如果 $1 >= $2 返回 0，否则返回 1
version_ge() {
    local v1=$1
    local v2=$2

    # 提取版本号数字
    local v1_major=$(echo "$v1" | cut -d'.' -f1 | sed 's/v//')
    local v1_minor=$(echo "$v1" | cut -d'.' -f2)
    local v1_patch=$(echo "$v1" | cut -d'.' -f3)

    local v2_major=$(echo "$v2" | cut -d'.' -f1 | sed 's/v//')
    local v2_minor=$(echo "$v2" | cut -d'.' -f2)
    local v2_patch=$(echo "$v2" | cut -d'.' -f3)

    # 比较主版本
    if [[ "$v1_major" -gt "$v2_major" ]]; then return 0; fi
    if [[ "$v1_major" -lt "$v2_major" ]]; then return 1; fi

    # 主版本相同，比较次版本
    if [[ "$v1_minor" -gt "$v2_minor" ]]; then return 0; fi
    if [[ "$v1_minor" -lt "$v2_minor" ]]; then return 1; fi

    # 次版本相同，比较修订版本
    if [[ "$v1_patch" -ge "$v2_patch" ]]; then return 0; fi
    return 1
}

# 修复 nvm 和 npm 的冲突
fix_nvm_npm_conflict() {
    print_msg "$BLUE" "检查 nvm 和 npm 配置冲突..."

    local npmrc_file="$HOME/.npmrc"

    if [[ -f "$npmrc_file" ]]; then
        # 检查是否存在 prefix 或 globalconfig 设置
        if grep -qE "^(prefix|globalconfig)=" "$npmrc_file" 2>/dev/null; then
            print_msg "$YELLOW" "检测到 .npmrc 中的 prefix/globalconfig 设置与 nvm 冲突"
            print_msg "$BLUE" "备份并修复 .npmrc..."

            # 备份原文件
            cp "$npmrc_file" "$npmrc_file.backup.$(date +%Y%m%d%H%M%S)"

            # 删除 prefix 和 globalconfig 行
            grep -vE "^(prefix|globalconfig)=" "$npmrc_file" > "$npmrc_file.tmp" || true
            mv "$npmrc_file.tmp" "$npmrc_file"

            print_msg "$GREEN" "✓ 已移除 .npmrc 中的冲突设置"
        fi
    fi

    # 清理 npm 环境变量
    unset NPM_CONFIG_PREFIX 2>/dev/null || true
    unset npm_config_prefix 2>/dev/null || true
}

# 检查 Node.js 版本（要求 >= 22.16.0）
check_nodejs() {
    print_msg "$BLUE" "[检查] Node.js 环境..."

    if ! command_exists node; then
        print_msg "$YELLOW" "⚠️  Node.js 未安装，正在安装 Node.js 22.16.0+..."
        install_nodejs_22_16
        return
    fi

    local current_version=$(node --version)
    print_msg "$BLUE" "检测到 Node.js: $current_version"

    # 检查是否满足 22.16.0+
    if version_ge "$current_version" "$REQUIRED_NODE_VERSION"; then
        print_msg "$GREEN" "✓ Node.js 版本满足要求 (>= $REQUIRED_NODE_VERSION)"
    else
        print_msg "$YELLOW" "⚠️  Node.js 版本过低 ($current_version < $REQUIRED_NODE_VERSION)"
        print_msg "$YELLOW" "OpenClaw 2026.3.13+ 要求 Node.js >= 22.16.0"

        # 检查是否是 nvm 管理的 Node
        if [[ -n "$NVM_DIR" ]] || [[ -d "$HOME/.nvm" ]]; then
            print_msg "$BLUE" "检测到 nvm，尝试通过 nvm 升级..."
            fix_nvm_npm_conflict  # 先修复冲突
            upgrade_node_with_nvm
        else
            print_msg "$BLUE" "尝试通过 NodeSource 升级..."
            install_nodejs_22_16
        fi
    fi

    # 再次验证
    local new_version=$(node --version)
    if version_ge "$new_version" "$REQUIRED_NODE_VERSION"; then
        print_msg "$GREEN" "✓ Node.js 版本已更新: $new_version"
    else
        print_msg "$RED" "✗ Node.js 版本仍不满足要求: $new_version"
        print_msg "$YELLOW" "请手动升级 Node.js 到 22.16.0 或更高版本"
        print_msg "$NC" "升级方法:"
        print_msg "$NC" "  1. 使用 nvm: nvm install 22 && nvm use 22"
        print_msg "$NC" "  2. 或访问: https://nodejs.org/en/download"
        exit 1
    fi

    # 检查 npm
    if ! command_exists npm; then
        print_msg "$RED" "✗ npm 未安装"
        exit 1
    fi
    print_msg "$GREEN" "✓ npm 版本: $(npm --version)"
}

# 使用 nvm 升级 Node.js
upgrade_node_with_nvm() {
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"

    # 加载 nvm
    if [[ -s "$NVM_DIR/nvm.sh" ]]; then
        # shellcheck source=/dev/null
        source "$NVM_DIR/nvm.sh"
    else
        print_msg "$YELLOW" "nvm 未找到，尝试安装 nvm..."
        install_nvm_and_node
        return
    fi

    print_msg "$BLUE" "安装 Node.js 22.16.0 (LTS)..."

    # 使用 --delete-prefix 选项避免冲突
    nvm install 22.16.0
    nvm use --delete-prefix v22.16.0 --silent
    nvm alias default 22.16.0

    # 确保 npm 全局路径正确（使用 nvm 的默认路径）
    # 不再设置自定义 prefix，避免与 nvm 冲突

    print_msg "$GREEN" "✓ nvm 已安装并切换到 Node 22.16.0"

    # 验证
    print_msg "$BLUE" "验证 Node.js 版本..."
    node --version
    npm --version
}

# 安装 nvm 和 Node.js
install_nvm_and_node() {
    print_msg "$BLUE" "安装 nvm..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash

    export NVM_DIR="$HOME/.nvm"
    # shellcheck source=/dev/null
    source "$NVM_DIR/nvm.sh"

    print_msg "$BLUE" "通过 nvm 安装 Node.js 22.16.0..."
    nvm install 22.16.0
    nvm use --delete-prefix v22.16.0 --silent
    nvm alias default 22.16.0

    print_msg "$GREEN" "✓ nvm 和 Node.js 22.16.0 安装完成"
}

# 通过 NodeSource 安装 Node.js 22.x（最新版）
install_nodejs_22_16() {
    print_msg "$BLUE" "通过 NodeSource 安装 Node.js 22.x..."

    # 清理旧版本
    sudo apt-get remove -y nodejs npm 2>/dev/null || true
    sudo rm -f /etc/apt/sources.list.d/nodesource.list* 2>/dev/null || true

    # 安装 NodeSource 22.x 源
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs

    # 验证版本
    local installed_version=$(node --version)
    print_msg "$GREEN" "✓ Node.js 安装完成: $installed_version"

    # 如果版本仍低于 22.16.0，尝试安装 nvm 版本
    if ! version_ge "$installed_version" "$REQUIRED_NODE_VERSION"; then
        print_msg "$YELLOW" "NodeSource 版本 ($installed_version) 仍低于 22.16.0"
        print_msg "$BLUE" "尝试通过 nvm 安装精确版本..."
        install_nvm_and_node
    fi
}

# 修复 Node.js 版本（独立命令）
cmd_node_fix() {
    print_msg "$CYAN" "\n🔧 修复 Node.js 版本"
    printf "==========================================\n"

    print_msg "$BLUE" "OpenClaw 2026.3.13+ 要求 Node.js >= 22.16.0"
    print_msg "$BLUE" "当前版本: $(node --version 2>/dev/null || echo '未安装')"
    printf "\n"

    # 先修复冲突
    fix_nvm_npm_conflict

    check_nodejs

    print_msg "$GREEN" "\n✓ Node.js 版本修复完成"
    print_msg "$BLUE" "请重新运行安装或配置命令"
    printf "  %s install\n" "$0"
    printf "  %s configure\n" "$0"
}

# 配置 npm 环境（兼容 nvm）
setup_npm() {
    print_msg "$BLUE" "[配置] npm 环境..."

    # 如果使用 nvm，不需要自定义 prefix
    if [[ -n "$NVM_DIR" ]] && [[ -s "$NVM_DIR/nvm.sh" ]]; then
        print_msg "$BLUE" "检测到 nvm，使用 nvm 默认 npm 配置"
        # nvm 已经配置好 npm 全局路径
        return
    fi

    # 非 nvm 环境，使用自定义 prefix
    mkdir -p ~/.npm-global
    npm config set prefix '~/.npm-global'

    if ! grep -q ".npm-global/bin" ~/.bashrc 2>/dev/null; then
        echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
        print_msg "$GREEN" "✓ 已添加 npm 全局路径到 ~/.bashrc"
    fi

    export PATH=~/.npm-global/bin:$PATH

    # 询问是否使用国内镜像
    printf "是否使用国内 npm 镜像加速下载? [y/N]: "
    read -r use_mirror
    if [[ "$use_mirror" =~ ^[Yy]$ ]]; then
        npm config set registry https://registry.npmmirror.com
        print_msg "$GREEN" "✓ 已设置 npm 国内镜像"
    fi
}

# 获取 Moonshot API Key
get_api_key() {
    print_msg "$CYAN" "\n📝 配置 Moonshot API Key"
    printf "获取地址: https://platform.moonshot.cn/console/api-keys\n"

    local api_key=""
    while [[ -z "$api_key" ]]; do
        printf "请输入 Moonshot API Key: "
        read -s -r api_key
        printf "\n"
        if [[ -z "$api_key" ]]; then
            print_msg "$RED" "API Key 不能为空，请重新输入"
        fi
    done

    printf "%s" "$api_key"
}

# 执行非交互式配置
run_onboarding() {
    local api_key=$1

    print_msg "$BLUE" "执行 OpenClaw 非交互式配置..."

    # 先运行 doctor 确保环境正常
    print_msg "$BLUE" "运行环境检查..."
    if ! openclaw doctor 2>/dev/null; then
        print_msg "$YELLOW" "⚠️  环境检查未通过，但继续尝试配置..."
    fi

    # 尝试标准参数
    if openclaw onboard --non-interactive \
        --mode local \
        --auth-choice moonshot-api-key \
        --moonshot-api-key "$api_key" \
        --gateway-port $GATEWAY_PORT \
        --gateway-bind loopback \
        --install-daemon \
        --daemon-runtime node \
        --skip-skills 2>/dev/null; then

        print_msg "$GREEN" "✓ OpenClaw 配置成功"
        return 0
    fi

    # 备用方案：手动创建配置
    print_msg "$YELLOW" "⚠️  标准配置失败，使用备用方案..."

    mkdir -p "$CONFIG_DIR"

    cat > "$CONFIG_FILE" << EOF
{
  "models": {
    "providers": {
      "moonshot": {
        "auth": "moonshot-api-key",
        "apiKey": "$api_key",
        "baseUrl": "https://api.moonshot.cn/v1",
        "models": [
          { "id": "moonshot-v1-8k", "name": "Moonshot v1 8k" },
          { "id": "moonshot-v1-32k", "name": "Moonshot v1 32k" },
          { "id": "moonshot-v1-128k", "name": "Moonshot v1 128k" }
        ]
      }
    }
  },
  "gateway": {
    "port": $GATEWAY_PORT,
    "bind": "127.0.0.1"
  }
}
EOF

    # 尝试安装 daemon
    openclaw gateway install 2>/dev/null || true

    print_msg "$GREEN" "✓ 配置文件已创建: $CONFIG_FILE"
}

# 安装 OpenClaw
cmd_install() {
    print_msg "$CYAN" "\n🚀 开始安装 OpenClaw"
    printf "==========================================\n"

    # 1. 环境准备
    print_msg "$BLUE" "[1/5] 环境准备..."
    sudo apt update && sudo apt install -y curl git build-essential

    # 2. 检查 Node.js（关键步骤）
    check_nodejs

    # 3. 配置 npm
    setup_npm

    # 4. 安装 OpenClaw
    print_msg "$BLUE" "[4/5] 安装 OpenClaw..."

    # 方式一：官方脚本
    if curl -fsSL https://openclaw.ai/install.sh | bash; then
        print_msg "$GREEN" "✓ 官方脚本安装成功"
    else
        print_msg "$YELLOW" "⚠️  脚本安装失败，尝试 npm 安装..."
        npm install -g openclaw@$OPENCLAW_VERSION
    fi

    # 验证安装
    if ! command_exists openclaw; then
        print_msg "$RED" "✗ OpenClaw 安装失败"
        exit 1
    fi

    print_msg "$GREEN" "✓ OpenClaw 安装成功: $(openclaw --version 2>/dev/null || echo 'unknown')"

    # 5. 配置
    print_msg "$BLUE" "[5/5] 配置 OpenClaw..."
    local api_key
    api_key=$(get_api_key)
    run_onboarding "$api_key"

    # 启动服务
    print_msg "$BLUE" "启动网关服务..."
    openclaw gateway start 2>/dev/null || openclaw gateway restart 2>/dev/null || true

    # 启用用户 lingering（保持后台运行）
    loginctl enable-linger "$(whoami)" 2>/dev/null || true

    # 显示完成信息
    show_completion_info
}

# 更新 OpenClaw
cmd_update() {
    print_msg "$CYAN" "\n🔄 更新 OpenClaw"
    printf "==========================================\n"

    if ! command_exists openclaw; then
        print_msg "$RED" "✗ OpenClaw 未安装，请先执行安装"
        exit 1
    fi

    # 先检查 Node.js 版本
    check_nodejs

    local old_version
    old_version=$(openclaw --version 2>/dev/null || echo "unknown")
    print_msg "$BLUE" "当前版本: $old_version"

    # 备份配置
    if [[ -f "$CONFIG_FILE" ]]; then
        cp "$CONFIG_FILE" "$CONFIG_FILE.backup.$(date +%Y%m%d%H%M%S)"
        print_msg "$GREEN" "✓ 已备份配置文件"
    fi

    # 停止服务
    print_msg "$BLUE" "停止当前服务..."
    openclaw gateway stop 2>/dev/null || true

    # 更新
    print_msg "$BLUE" "正在更新..."
    if npm update -g openclaw 2>/dev/null || npm install -g openclaw@latest; then
        print_msg "$GREEN" "✓ 更新成功"
        print_msg "$GREEN" "新版本: $(openclaw --version 2>/dev/null || echo 'unknown')"
    else
        print_msg "$RED" "✗ 更新失败"
        exit 1
    fi

    # 重启服务
    print_msg "$BLUE" "重启服务..."
    openclaw gateway start 2>/dev/null || true

    print_msg "$GREEN" "\n✓ 更新完成"
    openclaw status 2>/dev/null || true
}

# 卸载 OpenClaw
cmd_uninstall() {
    print_msg "$CYAN" "\n🗑️  卸载 OpenClaw"
    printf "==========================================\n"

    printf "确定要完全卸载 OpenClaw 吗? 这将删除所有配置和数据 [y/N]: "
    read -r confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_msg "$YELLOW" "已取消卸载"
        exit 0
    fi

    # 停止服务
    print_msg "$BLUE" "停止服务..."
    openclaw gateway stop 2>/dev/null || true

    # 卸载 daemon
    openclaw gateway uninstall 2>/dev/null || true

    # 卸载包
    print_msg "$BLUE" "卸载 OpenClaw..."
    npm uninstall -g openclaw 2>/dev/null || true

    # 清理配置
    print_msg "$BLUE" "清理配置文件..."
    if [[ -d "$CONFIG_DIR" ]]; then
        rm -rf "$CONFIG_DIR"
        print_msg "$GREEN" "✓ 已删除配置目录: $CONFIG_DIR"
    fi

    # 清理 npm 全局目录中的残留
    rm -rf ~/.npm-global/lib/node_modules/openclaw 2>/dev/null || true
    rm -f ~/.npm-global/bin/openclaw 2>/dev/null || true

    print_msg "$GREEN" "\n✓ OpenClaw 已完全卸载"
}

# 重新配置
cmd_configure() {
    print_msg "$CYAN" "\n⚙️  重新配置 OpenClaw"
    printf "==========================================\n"

    if ! command_exists openclaw; then
        print_msg "$RED" "✗ OpenClaw 未安装"
        exit 1
    fi

    # 检查 Node.js 版本
    check_nodejs

    # 停止服务
    openclaw gateway stop 2>/dev/null || true

    # 备份原配置
    if [[ -f "$CONFIG_FILE" ]]; then
        cp "$CONFIG_FILE" "$CONFIG_FILE.backup.$(date +%Y%m%d%H%M%S)"
        print_msg "$GREEN" "✓ 已备份原配置"
    fi

    # 获取新配置
    local api_key
    api_key=$(get_api_key)

    # 询问端口
    printf "请输入网关端口 [默认 %s]: " "$GATEWAY_PORT"
    read -r input_port
    GATEWAY_PORT=${input_port:-$GATEWAY_PORT}

    # 执行配置
    run_onboarding "$api_key"

    # 重启服务
    print_msg "$BLUE" "重启服务..."
    openclaw gateway start 2>/dev/null || openclaw gateway restart 2>/dev/null || true

    print_msg "$GREEN" "\n✓ 配置完成"
    printf "新配置:\n"
    printf "  - API Key: %s...\n" "${api_key:0:10}"
    printf "  - 端口: %s\n" "$GATEWAY_PORT"
}

# 检查状态
cmd_status() {
    print_msg "$CYAN" "\n📊 OpenClaw 状态检查"
    printf "==========================================\n"

    if ! command_exists openclaw; then
        print_msg "$RED" "✗ OpenClaw 未安装"
        exit 1
    fi

    print_msg "$BLUE" "版本信息:"
    openclaw --version 2>/dev/null || print_msg "$RED" "无法获取版本"

    print_msg "$BLUE" "\n运行状态:"
    openclaw status 2>/dev/null || print_msg "$YELLOW" "无法获取状态"

    print_msg "$BLUE" "\n健康检查:"
    openclaw health 2>/dev/null || print_msg "$YELLOW" "健康检查失败"

    print_msg "$BLUE" "\n配置信息:"
    if [[ -f "$CONFIG_FILE" ]]; then
        printf "配置文件: %s\n" "$CONFIG_FILE"
        head -20 "$CONFIG_FILE" 2>/dev/null || true
    else
        print_msg "$YELLOW" "配置文件不存在"
    fi

    print_msg "$BLUE" "\n网关访问:"
    if curl -s "http://127.0.0.1:$GATEWAY_PORT" >/dev/null 2>&1; then
        print_msg "$GREEN" "✓ 网关可访问: http://127.0.0.1:$GATEWAY_PORT"
    else
        print_msg "$YELLOW" "⚠️  网关未响应 (端口: $GATEWAY_PORT)"
    fi
}

# 重启服务
cmd_restart() {
    print_msg "$CYAN" "\n🔄 重启 OpenClaw 服务"
    printf "==========================================\n"

    if ! command_exists openclaw; then
        print_msg "$RED" "✗ OpenClaw 未安装"
        exit 1
    fi

    print_msg "$BLUE" "停止服务..."
    openclaw gateway stop 2>/dev/null || true
    sleep 1

    print_msg "$BLUE" "启动服务..."
    if openclaw gateway start; then
        print_msg "$GREEN" "✓ 服务重启成功"
        sleep 1
        openclaw status 2>/dev/null || true
    else
        print_msg "$RED" "✗ 服务重启失败"
        print_msg "$YELLOW" "尝试查看日志: $0 logs"
        exit 1
    fi
}

# 查看日志
cmd_logs() {
    print_msg "$CYAN" "\n📜 OpenClaw 日志"
    printf "==========================================\n"

    if command_exists openclaw; then
        openclaw logs 2>/dev/null || journalctl --user -u openclaw-gateway -f 2>/dev/null || \
            print_msg "$YELLOW" "无法获取日志，请手动检查 ~/.openclaw/logs/"
    else
        print_msg "$RED" "OpenClaw 未安装"
    fi
}

# 运行诊断
cmd_doctor() {
    print_msg "$CYAN" "\n🔍 OpenClaw 诊断"
    printf "==========================================\n"

    # 检查 Node.js 版本
    print_msg "$BLUE" "Node.js 版本检查:"
    local current_version=$(node --version 2>/dev/null || echo "未安装")
    printf "当前版本: %s\n" "$current_version"
    printf "要求版本: >= %s\n" "$REQUIRED_NODE_VERSION"

    if version_ge "$current_version" "$REQUIRED_NODE_VERSION"; then
        print_msg "$GREEN" "✓ Node.js 版本满足要求"
    else
        print_msg "$RED" "✗ Node.js 版本过低"
        print_msg "$YELLOW" "请运行: $0 node-fix"
    fi

    if command_exists openclaw; then
        print_msg "$BLUE" "\nOpenClaw Doctor 输出:"
        openclaw doctor 2>/dev/null || true
    fi

    print_msg "$BLUE" "\n系统环境检查:"
    printf "Node.js: %s\n" "$(node --version 2>/dev/null || echo '未安装')"
    printf "npm: %s\n" "$(npm --version 2>/dev/null || echo '未安装')"
    printf "OpenClaw: %s\n" "$(openclaw --version 2>/dev/null || echo '未安装')"

    print_msg "$BLUE" "\n端口检查 ($GATEWAY_PORT):"
    if lsof -i :$GATEWAY_PORT 2>/dev/null | grep -q LISTEN; then
        printf "端口 %s: 已被占用\n" "$GATEWAY_PORT"
        lsof -i :$GATEWAY_PORT 2>/dev/null || true
    else
        print_msg "$GREEN" "端口 $GATEWAY_PORT: 可用"
    fi

    print_msg "$BLUE" "\n配置文件检查:"
    if [[ -f "$CONFIG_FILE" ]]; then
        print_msg "$GREEN" "✓ 配置文件存在"
        ls -la "$CONFIG_FILE"
    else
        print_msg "$YELLOW" "✗ 配置文件不存在: $CONFIG_FILE"
    fi
}

# 显示完成信息
show_completion_info() {
    print_msg "$GREEN" "\n=========================================="
    print_msg "$GREEN" "🎉 OpenClaw 安装配置完成！"
    print_msg "$GREEN" "=========================================="

    printf "\n"
    print_msg "$CYAN" "📊 状态信息:"
    openclaw status 2>/dev/null || true

    printf "\n"
    print_msg "$CYAN" "🌐 访问地址:"
    printf "   - Web UI: http://127.0.0.1:%s\n" "$GATEWAY_PORT"
    printf "   - 本地网关: http://localhost:%s\n" "$GATEWAY_PORT"

    printf "\n"
    print_msg "$CYAN" "🔧 常用命令:"
    printf "   %s status       # 查看状态\n" "$0"
    printf "   %s restart      # 重启服务\n" "$0"
    printf "   %s logs         # 查看日志\n" "$0"
    printf "   %s configure    # 修改配置\n" "$0"
    printf "   openclaw dashboard    # 打开 Web 控制台\n"

    printf "\n"
    print_msg "$CYAN" "⚙️  配置文件:"
    printf "   %s\n" "$CONFIG_FILE"

    printf "\n"
    print_msg "$YELLOW" "💡 提示: 如果无法访问 Web UI，请尝试重启 WSL:"
    printf "   wsl --shutdown\n"
    printf "   wsl\n"
}

# 主函数
main() {
    local cmd="${1:-help}"

    case "$cmd" in
        install|i)
            cmd_install
            ;;
        update|u)
            cmd_update
            ;;
        uninstall|remove|rm)
            cmd_uninstall
            ;;
        configure|config|c)
            cmd_configure
            ;;
        status|s)
            cmd_status
            ;;
        restart|r)
            cmd_restart
            ;;
        logs|log|l)
            cmd_logs
            ;;
        doctor|d)
            cmd_doctor
            ;;
        node-fix|n)
            cmd_node_fix
            ;;
        help|h|--help|-h)
            show_help
            ;;
        *)
            print_msg "$RED" "未知命令: $cmd"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"