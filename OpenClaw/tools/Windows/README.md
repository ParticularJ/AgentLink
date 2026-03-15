# OpenClaw Windows 管理脚本

[![PowerShell](https://img.shields.io/badge/PowerShell-5.1+-blue.svg)](https://github.com/PowerShell/PowerShell)
[![Node.js](https://img.shields.io/badge/Node.js-v22.14.0-green.svg)](https://nodejs.org/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

## 📋 简介

这是一个用于 Windows 系统的 OpenClaw 管理脚本，提供了一键安装、更新和卸载 OpenClaw 的功能。脚本会自动处理 Node.js 环境配置、npm 镜像源设置等依赖项，让您能够快速部署和管理 OpenClaw。

## ✨ 功能特性

- 🚀 **一键安装** - 自动检测并安装 Node.js，配置 npm 国内镜像源，安装 OpenClaw
- 🔄 **智能更新** - 检查并更新到最新版本，自动处理依赖关系
- 🗑️ **彻底卸载** - 完整卸载 OpenClaw 并清理相关配置文件和缓存
- 🛠️ **环境检测** - 自动检查并修复 Node.js 和 npm 环境变量
- 📦 **国内加速** - 默认使用阿里云 npm 镜像源，提升下载速度
- 🎨 **彩色输出** - 清晰的命令行界面，便于识别操作状态

## 📋 系统要求

- Windows 8/10/11
- PowerShell 5.1 或更高版本
- 管理员权限（仅安装 Node.js 时需要）

## 🚀 快速开始

### 安装 OpenClaw

```powershell
# 以管理员身份运行 PowerShell，执行：
.\openclaw-installer.ps1 install
# 或直接运行（默认执行安装）
.\openclaw-installer.ps1
```

### 更新 OpenClaw

```powershell
.\openclaw-installer.ps1 update
```

### 卸载 OpenClaw

```powershell
.\openclaw-installer.ps1 uninstall
```

### 查看帮助

```powershell
.\openclaw-installer.ps1 -Help
```

## 📖 详细使用说明

### 安装模式 (install)

脚本会执行以下步骤：
- ✅ 检查管理员权限（安装 Node.js 时需要）
- ✅ 检测 Node.js 安装状态，自动安装 v22.14.0
- ✅ 配置 Node.js 和 npm 环境变量
- ✅ 设置 npm 国内镜像源加速
- ✅ 尝试官方安装脚本安装 OpenClaw
- ✅ 失败后自动切换 npm 全局安装
- ✅ 显示安装后信息和常用命令

### 更新模式 (update)

- ✅ 检查当前 OpenClaw 版本
- ✅ 更新 npm 包管理器到最新版
- ✅ 更新 OpenClaw 到最新版本
- ✅ 清理 npm 缓存
- ✅ 显示版本变更信息

### 卸载模式 (uninstall)

- ✅ 检查 OpenClaw 安装状态
- ✅ 确认卸载操作
- ✅ 通过 npm 卸载全局包
- ✅ 清理配置文件目录
- ✅ 清理 npm 缓存

## ⚙️ 配置说明

脚本中包含以下可配置参数：

```powershell
# Node.js 版本和下载地址
$NodeVersion = "v22.14.0"
$NodeUrl = "https://nodejs.org/dist/v22.14.0/node-v22.14.0-x64.msi"

# npm 镜像源（默认使用阿里云镜像加速）
$NpmRegistry = "https://registry.npmmirror.com"

# 包名称
$PackageName = "openclaw"
```

## 🔧 常见问题

### 1. 安装 Node.js 失败

**解决方案**：
- 确保以管理员身份运行 PowerShell
- 手动下载安装 [Node.js v22.14.0](https://nodejs.org/dist/v22.14.0/node-v22.14.0-x64.msi)
- 重启 PowerShell 后重新运行脚本

### 2. npm 命令找不到

**解决方案**：
- 脚本会自动修复 PATH 环境变量
- 如未生效，请重启 PowerShell
- 或手动将 `C:\Program Files\nodejs` 添加到系统 PATH

### 3. OpenClaw 安装后无法识别

**解决方案**：
- 运行 `Refresh-Environment` 刷新环境变量
- 或重启 PowerShell 终端
- 检查 npm 全局包安装路径是否在 PATH 中

### 4. 下载速度慢

**解决方案**：
- 脚本已默认使用阿里云 npm 镜像源
- 如需修改，可编辑脚本中的 `$NpmRegistry` 变量

## 🔒 安全说明

- 脚本需要管理员权限仅用于安装 Node.js
- 所有下载均使用 HTTPS 安全连接
- 不收集任何用户数据
- 不修改系统关键配置

## 📚 相关资源

- [OpenClaw 官方文档](https://docs.openclaw.ai)
- [Node.js 官网](https://nodejs.org/)
- [npm 阿里云镜像](https://npmmirror.com/)

## 📄 许可证

MIT License

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request 改进脚本功能：

1. Fork 本仓库
2. 创建您的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交您的修改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开一个 Pull Request

## 📧 联系方式

如有问题或建议，请通过以下方式联系：

- 提交 GitHub Issue
- 查阅官方文档
- 参与社区讨论

---

**温馨提示**：建议定期运行更新命令，获取最新功能和安全性改进：

```powershell
.\openclaw-installer.ps1 update
```