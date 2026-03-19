# OpenClaw Windows 安装指南

本文档详细介绍在 Windows 系统上从零开始安装和配置 OpenClaw 的完整流程。

## 📋 目录

- [环境准备](#环境准备)
- [安装 Git](#安装-git)
- [拉取项目代码](#拉取项目代码)
- [安装 WSL](#安装-wsl)
- [安装 OpenClaw](#安装-openclaw)
- [配置 OpenClaw](#配置-openclaw)
- [目录结构说明](#目录结构说明)
- [常见问题](#常见问题)

---

## 环境准备

### 系统要求

- **操作系统**: Windows 10 版本 2004 及更高版本（内部版本 19041 及更高版本）或 Windows 11
- **权限**: 管理员权限（用于安装 WSL）
- **网络**: 可访问 GitHub 和外部网络

### 所需工具


| 工具       | 用途                     | 安装步骤            |
| ---------- | ------------------------ | ------------------- |
| Git        | 代码版本管理             | [见下文](#安装-git) |
| PowerShell | 执行安装脚本             | Windows 自带        |
| WSL        | Windows 子系统 for Linux | [见下文](#安装-wsl) |

---

## 安装 Git

### 方式一：官方安装包（推荐）

1. 访问 [Git 官方下载页面](https://git-scm.com/download/win)
2. 下载适用于 Windows 的安装程序（64-bit Git for Windows Setup）
3. 运行安装程序，按向导提示完成安装
4. **重要**: 安装过程中确保勾选 **"Git Bash Here"** 和 **"Git from the command line and also from 3rd-party software"**

### 方式二：Winget 安装（Windows 10/11）

```powershell
winget install --id Git.Git -e --source winget
```

### 验证安装

```powershell
git --version
```

---

## 拉取项目代码

### 1. 创建本地工作目录

打开 PowerShell，进入你的工作目录：

```powershell
cd C:\work\Agent\openclaw
```

> **提示**: 如果目录不存在，先创建：`mkdir C:\work\Agent\openclaw`

### 2. 克隆代码仓库

执行以下命令拉取 AgentLink 项目：

```powershell
git clone git@github.com:ParticularJ/AgentLink.git
```

**注意**:

- 如果使用 SSH 方式克隆失败，请改用 HTTPS：`git clone https://github.com/ParticularJ/AgentLink.git`
- 首次使用 SSH 需配置 [GitHub SSH 密钥](https://docs.github.com/zh/authentication/connecting-to-github-with-ssh)

---

## 安装 WSL

WSL（Windows Subsystem for Linux）是运行 OpenClaw 的必要环境。

### 1. 阅读安装说明

进入 WSL 安装目录查看详细文档：

```powershell
cd AgentLink\WSL
cat README.md
```

### 2. 执行安装脚本

运行 PowerShell 安装脚本：

```powershell
.\wsl-installer.ps1 install
```

**安装过程说明**:

- 脚本会自动启用 WSL 功能
- 下载并安装默认的 Linux 发行版（通常为 Ubuntu）
- 可能需要重启电脑完成安装

### 3. 验证 WSL 安装

```powershell
wsl --version
wsl --list --verbose
```

---

## 安装 OpenClaw

### 1. 阅读安装说明

进入 OpenClaw 安装目录：

```powershell
cd ..\OpenClaw	ools\WSL_and_Linux
cat README.md
```

### 2. 执行安装脚本

运行安装脚本（将在 WSL 环境中执行）：

```powershell
wsl ./openclaw-installer.sh
```

或直接执行（脚本内部会调用 WSL）：

```powershell
.\openclaw-installer.sh
```

**安装内容**:

- 在 WSL 中安装 OpenClaw 依赖
- 配置 OpenClaw 运行环境
- 安装必要的 Linux 工具链

---

## 配置 OpenClaw

安装完成后，需要进行详细配置才能正常使用。

### 配置文件位置

```
AgentLink\OpenClaw\docs\how_to_configure_openclaw.md
```

## 目录结构说明

完成安装后，目录结构如下：

```
C:\work\Agent\openclaw├── AgentLink\                    # 项目主目录
│   ├── WSL\                       # WSL 安装脚本和文档
│   │   ├── wsl-installer.ps1     # WSL 安装脚本
│   │   └── README.md              # WSL 安装说明
│   │
│   └── OpenClaw\                  # OpenClaw 主程序
│       ├── tools\                 # 工具脚本
│       │   └── WSL_and_Linux\     # WSL/Linux 安装工具
│       │       ├── openclaw-setup.sh
│       │       └── README.md
│       │
│       └── docs\                  # 文档目录
│           └── how_to_configure_openclaw.md    # 配置指南
│
└── [WSL 虚拟磁盘文件]              # WSL 系统文件（自动创建）
```

---

## 常见问题

### Q1: Git 克隆失败，提示 "Permission denied (publickey)"

**解决方案**:

1. 生成 SSH 密钥：`ssh-keygen -t ed25519 -C "your_email@example.com"`
2. 添加公钥到 GitHub：[SSH 设置指南](https://docs.github.com/zh/authentication/connecting-to-github-with-ssh)
3. 或使用 HTTPS 克隆：`git clone https://github.com/ParticularJ/AgentLink.git`

### Q2: WSL 安装脚本执行失败

**检查项**:

- 确保 PowerShell 以**管理员身份**运行
- 检查 Windows 版本是否支持 WSL2：`winver` 查看版本号（需 19041+）
- 手动启用 WSL：
  ```powershell
  dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
  dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
  ```

### Q3: openclaw-installer.sh 无法执行

**解决方案**:

1. 确保已进入正确目录：`cd AgentLink\OpenClaw\tools\WSL_and_Linux`
2. 检查脚本权限：
   ```powershell
   wsl chmod +x openclaw-installer.sh
   ```
3. 在 WSL 中直接执行：
   ```powershell
   wsl
   cd /mnt/c/work/Agent/openclaw/AgentLink/OpenClaw/tools/WSL_and_Linux
   ./openclaw-installer.sh
   ```

### Q4: 如何重新运行配置向导？

```bash
openclaw onboard
```

### Q5: 如何检查 OpenClaw 运行状态？

```bash
openclaw doctor
openclaw status
```

---

## 🚀 快速检查清单

安装完成后，请确认以下事项：

- [ ]  Git 已安装并可运行 (`git --version`)
- [ ]  代码仓库已克隆到本地 (`C:\work\Agent\openclaw\AgentLink`)
- [ ]  WSL 已启用并正常运行 (`wsl --version`)
- [ ]  OpenClaw 安装脚本执行完毕无报错
- [ ]  已阅读 `how_to_configure_openclaw.md` 配置文档
- [ ]  OpenClaw 配置验证通过 (`openclaw config validate`)
- [ ]  OpenClaw 网关成功启动 (`openclaw gateway run`)

---

## 📚 相关资源

- [Git for Windows 文档](https://git-scm.com/doc)
- [WSL 官方文档](https://docs.microsoft.com/zh-cn/windows/wsl/)
- [OpenClaw 官方文档](https://docs.openclaw.io/)
- [GitHub SSH 配置指南](https://docs.github.com/zh/authentication/connecting-to-github-with-ssh)

---

## 🆘 获取帮助

如遇到无法解决的问题：

1. 查看各目录下的 `README.md` 文档
2. 运行诊断命令：`openclaw doctor --deep`
3. 提交 Issue 到 [AgentLink 仓库](https://github.com/ParticularJ/AgentLink/issues)

---

*最后更新: 2026-03-19*
