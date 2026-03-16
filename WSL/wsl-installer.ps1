#!/bin/bash
# OpenClaw WSL Ubuntu 管理脚本（精简版）
# 支持: 安装 | 更新 | 卸载

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

# OpenClaw 要求的最低 Node.js 版本
REQUIRED_NODE_VERSION="22.16.0"

# 打印消息
print_msg() {
    local color=$1
    local msg=$2
    printf "${color}%s${NC}\n" "$msg"
}

# 显示帮助
show_help() {
    printf "${CYAN}🦞 OpenClaw WSL Ubuntu 管理脚本（精简版）${NC}\n\n"
    printf "${GREEN}用法:${NC} %s [选项]\n\n" "$0"
    printf "${YELLOW}选项:${NC}\n"
    printf "    install, i      安装 OpenClaw（首次安装或完整重装）\n"
    printf "    update, u       更新 OpenClaw 到最新版本\n"
    printf "    uninstall, rm   完全卸载 OpenClaw\n"
    printf "    help, h         显示此帮助信息\n\n"
    printf "${YELLOW}示例:${NC}\n"
    printf "    %s install      # 首次安装\n" "$0"
    printf "    %s update       # 更新版本\n" "$0"
    printf "    %s uninstall    # 完全卸载\n\n" "$0"
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 版本比较函数：如果 $1 >= $2 返回 0，否则返回 1
version_ge() {
    local v1=$1
    local v2=$2

    local v1_major=$(echo "$v1" | cut -d'.' -f1 | sed 's/v//')
    local v1_minor=$(echo "$v1" | cut -d'.' -f2)
    local v1_patch=$(echo "$v1" | cut -d'.' -f3)

    local v2_major=$(echo "$v2" | cut -d'.' -f1 | sed 's/v//')
    local v2_minor=$(echo "$v2" | cut -d'.' -f2)
    local v2_patch=$(echo "$v2" | cut -d'.' -f3)

    if [[ "$v1_major" -gt "$v2_major" ]]; then return 0; fi
    if [[ "$v1_major" -lt "$v2_major" ]]; then return 1; fi
    if [[ "$v1_minor" -gt "$v2_minor" ]]; then return 0; fi
    if [[ "$v1_minor" -lt "$v2_minor" ]]; then return 1; fi
    if [[ "$v1_patch" -ge "$v2_patch" ]]; then return 0; fi
    return 1
}

# 修复 nvm 和 npm 的冲突
fix_nvm_npm_conflict() {
    print_msg "$BLUE" "检查 nvm 和 npm 配置冲突..."

    local npmrc_file="$HOME/.npmrc"

    if [[ -f "$npmrc_file" ]]; then
        if grep -qE "^(prefix|globalconfig)=" "$npmrc_file" 2>/dev/null; then
            print_msg "$YELLOW" "检测到 .npmrc 中的 prefix/globalconfig 设置与 nvm 冲突"
            print_msg "$BLUE" "备份并修复 .npmrc..."
            cp "$npmrc_file" "$npmrc_file.backup.$(date +%Y%m%d%H%M%S)"
            grep -vE "^(prefix|globalconfig)=" "$npmrc_file" > "$npmrc_file.tmp" || true
            mv "$npmrc_file.tmp" "$npmrc_file"
            print_msg "$GREEN" "✓ 已移除 .npmrc 中的冲突设置"
        fi
    fi

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

    if version_ge "$current_version" "$REQUIRED_NODE_VERSION"; then
        print_msg "$GREEN" "✓ Node.js 版本满足要求 (>= $REQUIRED_NODE_VERSION)"
    else
        print_msg "$YELLOW" "⚠️  Node.js 版本过低 ($current_version < $REQUIRED_NODE_VERSION)"
        print_msg "$YELLOW" "OpenClaw 2026.3.13+ 要求 Node.js >= 22.16.0"

        if [[ -n "$NVM_DIR" ]] || [[ -d "$HOME/.nvm" ]]; then
            print_msg "$BLUE" "检测到 nvm，尝试通过 nvm 升级..."
            fix_nvm_npm_conflict
            upgrade_node_with_nvm
        else
            print_msg "$BLUE" "尝试通过 NodeSource 升级..."
            install_nodejs_22_16
        fi
    fi

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

    if ! command_exists npm; then
        print_msg "$RED" "✗ npm 未安装"
        exit 1
    fi
    print_msg "$GREEN" "✓ npm 版本: $(npm --version)"
}

# 使用 nvm 升级 Node.js
upgrade_node_with_nvm() {
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"

    if [[ -s "$NVM_DIR/nvm.sh" ]]; then
        source "$NVM_DIR/nvm.sh"
    else
        print_msg "$YELLOW" "nvm 未找到，尝试安装 nvm..."
        install_nvm_and_node
        return
    fi

    print_msg "$BLUE" "安装 Node.js 22.16.0 (LTS)..."
    nvm install 22.16.0
    nvm use --delete-prefix v22.16.0 --silent
    nvm alias default 22.16.0
    print_msg "$GREEN" "✓ nvm 已安装并切换到 Node 22.16.0"
}

# 安装 nvm 和 Node.js
install_nvm_and_node() {
    print_msg "$BLUE" "安装 nvm..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash

    export NVM_DIR="$HOME/.nvm"
    source "$NVM_DIR/nvm.sh"

    print_msg "$BLUE" "通过 nvm 安装 Node.js 22.16.0..."
    nvm install 22.16.0
    nvm use --delete-prefix v22.16.0 --silent
    nvm alias default 22.16.0

    print_msg "$GREEN" "✓ nvm 和 Node.js 22.16.0 安装完成"
}

# 通过 NodeSource 安装 Node.js 22.x
install_nodejs_22_16() {
    print_msg "$BLUE" "通过 NodeSource 安装 Node.js 22.x..."

    sudo apt-get remove -y nodejs npm 2>/dev/null || true
    sudo rm -f /etc/apt/sources.list.d/nodesource.list* 2>/dev/null || true

    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs

    local installed_version=$(node --version)
    print_msg "$GREEN" "✓ Node.js 安装完成: $installed_version"

    if ! version_ge "$installed_version" "$REQUIRED_NODE_VERSION"; then
        print_msg "$YELLOW" "NodeSource 版本 ($installed_version) 仍低于 22.16.0"
        print_msg "$BLUE" "尝试通过 nvm 安装精确版本..."
        install_nvm_and_node
    fi
}

# 配置 npm 环境（兼容 nvm）
setup_npm() {
    print_msg "$BLUE" "[配置] npm 环境..."

    if [[ -n "$NVM_DIR" ]] && [[ -s "$NVM_DIR/nvm.sh" ]]; then
        print_msg "$BLUE" "检测到 nvm，使用 nvm 默认 npm 配置"
        return
    fi

    mkdir -p ~/.npm-global
    npm config set prefix '~/.npm-global'

    if ! grep -q ".npm-global/bin" ~/.bashrc 2>/dev/null; then
        echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
        print_msg "$GREEN" "✓ 已添加 npm 全局路径到 ~/.bashrc"
    fi

    export PATH=~/.npm-global/bin:$PATH

    printf "是否使用国内 npm 镜像加速下载? [y/N]: "
    read -r use_mirror
    if [[ "$use_mirror" =~ ^[Yy]$ ]]; then
        npm config set registry https://registry.npmmirror.com
        print_msg "$GREEN" "✓ 已设置 npm 国内镜像"
    fi
}

# 安装 OpenClaw
cmd_install() {
    print_msg "$CYAN" "\n🚀 开始安装 OpenClaw"
    printf "==========================================\n"

    print_msg "$BLUE" "[1/3] 环境准备..."
    sudo apt update && sudo apt install -y curl git build-essential

    check_nodejs
    setup_npm

    print_msg "$BLUE" "[3/3] 安装 OpenClaw..."

    if curl -fsSL https://openclaw.ai/install.sh | bash; then
        print_msg "$GREEN" "✓ 官方脚本安装成功"
    else
        print_msg "$YELLOW" "⚠️  脚本安装失败，尝试 npm 安装..."
        npm install -g openclaw@$OPENCLAW_VERSION
    fi

    if ! command_exists openclaw; then
        print_msg "$RED" "✗ OpenClaw 安装失败"
        exit 1
    fi

    print_msg "$GREEN" "✓ OpenClaw 安装成功: $(openclaw --version 2>/dev/null || echo 'unknown')"

    print_msg "$GREEN" "\n=========================================="
    print_msg "$GREEN" "🎉 OpenClaw 安装完成！"
    print_msg "$GREEN" "=========================================="
    printf "\n"
    print_msg "$CYAN" "🔧 常用命令:"
    printf "   openclaw --version    # 查看版本\n"
    printf "   openclaw --help       # 查看帮助\n"
    printf "   %s update             # 更新版本\n" "$0"
    printf "   %s uninstall          # 卸载\n" "$0"
}

# 更新 OpenClaw
cmd_update() {
    print_msg "$CYAN" "\n🔄 更新 OpenClaw"
    printf "==========================================\n"

    if ! command_exists openclaw; then
        print_msg "$RED" "✗ OpenClaw 未安装，请先执行安装"
        exit 1
    fi

    check_nodejs

    local old_version
    old_version=$(openclaw --version 2>/dev/null || echo "unknown")
    print_msg "$BLUE" "当前版本: $old_version"

    print_msg "$BLUE" "停止当前服务..."
    openclaw gateway stop 2>/dev/null || true

    print_msg "$BLUE" "正在更新..."
    if npm update -g openclaw 2>/dev/null || npm install -g openclaw@latest; then
        print_msg "$GREEN" "✓ 更新成功"
        print_msg "$GREEN" "新版本: $(openclaw --version 2>/dev/null || echo 'unknown')"
    else
        print_msg "$RED" "✗ 更新失败"
        exit 1
    fi

    print_msg "$BLUE" "重启服务..."
    openclaw gateway start 2>/dev/null || true

    print_msg "$GREEN" "\n✓ 更新完成"
}

# 卸载 OpenClaw
cmd_uninstall() {
    print_msg "$CYAN" "\n🗑️  卸载 OpenClaw"
    printf "==========================================\n"

    printf "确定要完全卸载 OpenClaw 吗? [y/N]: "
    read -r confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_msg "$YELLOW" "已取消卸载"
        exit 0
    fi

    print_msg "$BLUE" "停止服务..."
    openclaw gateway stop 2>/dev/null || true
    openclaw gateway uninstall 2>/dev/null || true

    print_msg "$BLUE" "卸载 OpenClaw..."
    npm uninstall -g openclaw 2>/dev/null || true

    print_msg "$BLUE" "清理残留文件..."
    rm -rf ~/.npm-global/lib/node_modules/openclaw 2>/dev/null || true
    rm -f ~/.npm-global/bin/openclaw 2>/dev/null || true

    print_msg "$GREEN" "\n✓ OpenClaw 已完全卸载"
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

main "$@"