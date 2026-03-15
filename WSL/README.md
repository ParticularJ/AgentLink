# WSL Manager

[![PowerShell](https://img.shields.io/badge/PowerShell-5.1+-blue.svg)](https://github.com/PowerShell/PowerShell)
[![Windows](https://img.shields.io/badge/Windows-10%201903%2B%20%7C%2011-green.svg)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

## 📋 简介

这是一个用于 Windows Subsystem for Linux (WSL) 的管理脚本，提供了一键安装、卸载和更新 WSL2 + Ubuntu 的功能。脚本会自动检测最新 LTS 版本、配置 systemd 支持和 sudo 用户权限，让您能够快速部署和管理 WSL 环境。

## ✨ 功能特性

- 🚀 **一键安装** - 自动检测并安装最新 Ubuntu LTS 版本，配置 systemd 支持
- 🔄 **智能更新** - 更新 WSL 内核和 Ubuntu 系统软件包
- 🗑️ **灵活卸载** - 支持交互式选择卸载指定发行版或完全移除 WSL
- 🛠️ **环境检测** - 自动检查虚拟化支持和系统版本要求
- 📦 **版本管理** - 支持指定 Ubuntu 版本安装
- 🎨 **交互界面** - 清晰的命令行交互，便于选择操作

## 📋 系统要求

- Windows 10 版本 1903+ 或 Windows 11
- PowerShell 5.1 或更高版本
- 管理员权限（脚本自动申请）
- BIOS 启用虚拟化（Intel VT-x / AMD-V）

## 🚀 快速开始

### 安装 WSL2 + Ubuntu

```powershell
# 以管理员身份运行 PowerShell，执行：
.\wsl-manager.ps1 install

# 或安装指定版本
.\wsl-manager.ps1 install -Distro Ubuntu-22.04

# 强制重新安装
.\wsl-manager.ps1 install -Force
```

### 卸载 WSL

```powershell
# 交互式选择卸载
.\wsl-manager.ps1 uninstall

# 完全移除 WSL
.\wsl-manager.ps1 uninstall -All
```

### 更新 WSL

```powershell
# 更新 WSL 内核和 Ubuntu 系统
.\wsl-manager.ps1 update
```

## 📖 详细使用说明

### 安装模式 (install)

脚本会执行以下步骤：

- ✅ 检查 Windows 版本兼容性
- ✅ 验证 BIOS 虚拟化支持
- ✅ 自动申请管理员权限
- ✅ 启用必要的 Windows 功能
- ✅ 安装 WSL2 内核更新
- ✅ 设置 WSL2 为默认版本
- ✅ 安装指定或最新 Ubuntu LTS 版本
- ✅ 配置 systemd 支持
- ✅ 创建默认 sudo 用户

### 卸载模式 (uninstall)

- ✅ 交互式选择要卸载的发行版
- ✅ 确认卸载操作
- ✅ 注销指定 WSL 发行版
- ✅ 完全移除模式可删除所有 WSL 组件
- ✅ 清理相关配置和缓存

### 更新模式 (update)

- ✅ 更新 WSL2 内核到最新版本
- ✅ 更新 Ubuntu 系统软件包
- ✅ 更新 systemd 配置
- ✅ 显示版本变更信息

## ⚙️ 配置说明

脚本中包含以下可配置参数：

```powershell
# 默认发行版设置
$DefaultDistro = "Ubuntu"  # 默认安装 Ubuntu

# WSL 配置
$WslVersion = 2  # 默认使用 WSL2
$EnableSystemd = $true  # 启用 systemd 支持
```

## 🔧 常见问题

### 1. 虚拟化未启用

**解决方案**：

- 重启电脑进入 BIOS/UEFI 设置
- 找到虚拟化技术选项（Intel VT-x / AMD-V）
- 启用虚拟化支持
- 保存并退出 BIOS

### 2. 安装过程卡住

**解决方案**：

- 确保网络连接稳定
- 检查 Windows 更新是否完整
- 尝试以管理员身份重新运行
- 查看 Windows 功能是否正常启用

### 3. systemd 不工作

**解决方案**：

- 确认 WSL 版本为 2：`wsl --set-version <distro> 2`
- 检查 `/etc/wsl.conf` 配置是否正确
- 重启 WSL：`wsl --shutdown`

### 4. 无法访问发行版列表

**解决方案**：

- 运行 `wsl --update` 更新 WSL
- 检查网络连接
- 使用代理或更换网络环境重试

## 🔒 安全说明

- 脚本需要管理员权限以启用 Windows 功能和安装 WSL
- 所有下载均使用官方 Microsoft 源
- 不收集任何用户数据
- 不修改系统关键配置

## 📚 相关资源

- [WSL 官方文档](https://docs.microsoft.com/windows/wsl/)
- [Ubuntu on WSL](https://ubuntu.com/wsl)
- [WSL 内核更新](https://aka.ms/wsl2kernel)

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

**温馨提示**：首次安装后可能需要重启计算机以确保所有功能正常工作。建议定期运行更新命令，获取最新功能和安全性改进：

```powershell
.\wsl-manager.ps1 update
```
