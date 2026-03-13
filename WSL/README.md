
```markdown
# WSL Manager

Windows Subsystem for Linux 管理脚本，支持一键安装、卸载和更新。

## 功能

- **install** - 安装 WSL2 + Ubuntu（自动检测最新 LTS）
- **uninstall** - 卸载指定发行版或完全移除 WSL
- **update** - 更新 WSL 内核和系统软件包

## 使用

### 安装

```powershell
# 安装最新 Ubuntu LTS（推荐）
.\wsl-manager.ps1 install

# 安装指定版本
.\wsl-manager.ps1 install -Distro Ubuntu-22.04

# 强制重新安装
.\wsl-manager.ps1 install -Force
```

### 卸载

```powershell
# 交互式选择卸载
.\wsl-manager.ps1 uninstall

# 完全移除 WSL
.\wsl-manager.ps1 uninstall -All
```

### 更新

```powershell
# 更新 WSL 内核和 Ubuntu 系统
.\wsl-manager.ps1 update
```

## 要求

- Windows 10 版本 1903+ 或 Windows 11
- 管理员权限（脚本自动申请）
- BIOS 启用虚拟化（Intel VT-x / AMD-V）

## 说明

- 首次安装后可能需要重启计算机
- 安装过程自动配置 systemd 支持和 sudo 用户
- 使用 `wsl --list --online` 查看可用发行版
```
