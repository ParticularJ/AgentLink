# OpenClaw 配置指南

本文档详细介绍了 OpenClaw 的完整配置流程，帮助你快速搭建并运行 OpenClaw 智能助手系统。

## 📋 目录

- [初始化配置](#初始化配置)
- [模型提供商配置](#模型提供商配置)
- [消息渠道配置](#消息渠道配置)
- [Web Search 服务配置](#web-search-服务配置)
- [Skills 配置](#skills-配置)
- [Hooks 配置](#hooks-配置)
- [验证与启动](#验证与启动)
- [访问控制台](#访问控制台)

---

## 初始化配置

### 1. 启动配置向导

如果安装 OpenClaw 后未自动进入配置向导，请执行以下命令：

```bash
openclaw onboard
```

### 2. 安全授权

当出现安全警示时，使用键盘**方向键**调整到 **Yes**，按 **回车键** 确认。

![1773930198309](images/how_to_configure_openclaw/1773930198309.png)

### 3. 选择快速开始

选择**快速开始**选项，继续进行配置。

![1773930216227](images/how_to_configure_openclaw/1773930216227.png)

---

## 模型提供商配置

### 选择提供商类型

向导中最重要的部分是 **Model / Provider** 配置：

![1773930239301](images/how_to_configure_openclaw/1773930239301.png)


| 类型                | 说明                                  |
| ------------------- | ------------------------------------- |
| **官方提供商**      | 如 KIMI、OpenAI、Anthropic 等官方服务 |
| **Custom Provider** | 兼容 OpenAI/Anthropic 协议的自建端点  |

### Custom Provider 配置参数

如果选择 Custom Provider，通常需要填写：

- **`baseUrl`**: API 端点地址（常见格式：`https://xxx/v1`）
- **`apiKey`**: 你的 API 密钥
- **`modelId`**: 模型标识符

### 配置示例：Kimi K2.5

以使用 **Kimi K2.5** 模型为例：

1. 访问 [Moonshot AI 开放平台](https://platform.moonshot.cn/console/api-keys) 获取 API Key

   ![1773930255502](images/how_to_configure_openclaw/1773930255502.png)
2. 在配置向导中填入获取到的 **API Key**

   ![1773930268259](images/how_to_configure_openclaw/1773930268259.png)

   ![1773930295937](images/how_to_configure_openclaw/1773930295937.png)

   ![1773930305302](images/how_to_configure_openclaw/1773930305302.png)
3. 完成模型配置

---

## 消息渠道配置

消息渠道用于与 OpenClaw 后台机器人进行对话和交互。

![1773930328559](images/how_to_configure_openclaw/1773930328559.png)

### 以飞书为例

1. **阅读文档**: 查看 [飞书应用创建说明](https://open.feishu.cn/document/develop-process/self-built-application-development-process)
2. **创建应用**: 进入 [飞书开放平台](https://open.feishu.cn/app) 创建自己的应用
3. **配置凭证**: 根据向导提示填入飞书应用的 App ID 和 App Secret

   ![1773930354425](images/how_to_configure_openclaw/1773930354425.png)

   ![1773930375136](images/how_to_configure_openclaw/1773930375136.png)

   ![1773930389368](images/how_to_configure_openclaw/1773930389368.png)

   ![1773930398360](images/how_to_configure_openclaw/1773930398360.png)

   ![1773930415514](images/how_to_configure_openclaw/1773930415514.png)

---

## Web Search 服务配置

可选择配置 Web Search 服务以增强 AI 的搜索能力：

![1773930487067](images/how_to_configure_openclaw/1773930487067.png)

- **推荐**: 选择 **Kimi** 作为搜索服务提供商
- **跳过**: 如暂时不需要，可选择跳过此步骤

---

## Skills 配置

配置想要预装的 Skills（技能插件）：

![1773930500056](images/how_to_configure_openclaw/1773930500056.png)

- **预装 Skills**: 选择需要的功能插件（如代码分析、文件处理等）

![1773930516125](images/how_to_configure_openclaw/1773930516125.png)

- **跳过**: 如暂时不确定，可跳过并在后续通过控制台添加

---

## 其他配置

根据向导提示完成其他基础配置项。

![1773930541151](images/how_to_configure_openclaw/1773930541151.png)

![1773930547320](images/how_to_configure_openclaw/1773930547320.png)

![1773930554797](images/how_to_configure_openclaw/1773930554797.png)

![1773930562062](images/how_to_configure_openclaw/1773930562062.png)

---

## Hooks 配置

### 什么是 Hooks？

Hooks 是一种**自动化机制**，允许你在执行特定命令时自动触发某些操作。就像一个"触发器"，当某个事件发生时，系统会自动执行预设的任务。

![1773930575369](images/how_to_configure_openclaw/1773930575369.png)

### 配置建议

根据你的使用场景选择合适的 Hooks 选项：

![1773930588556](images/how_to_configure_openclaw/1773930588556.png)

- **自动部署**: 代码提交时自动触发部署
- **消息通知**: 特定事件发生时发送通知
- **自定义脚本**: 执行自定义的自动化脚本

---

## 验证与启动

### 1. 配置检查

完成所有配置后，执行以下命令验证配置是否正确：

```bash
# 基础配置验证
openclaw config validate

# 深度健康检查
openclaw doctor --deep
```

### 2. 启动网关

验证通过后，启动 OpenClaw 网关服务：

```bash
openclaw gateway run
```

### 3. 启动控制台（可选）

如需启动 Web 控制台 UI：

```bash
openclaw dashboard --no-open
```

> **注意**: `--no-open` 参数防止自动打开浏览器，适用于远程服务器部署场景。

---

## 访问控制台

### 本地访问

在浏览器地址栏输入：

```
http://127.0.0.1:18789
```

复制带 token 的完整地址打开即可。

### 远程服务器访问

如果 OpenClaw 运行在远程服务器，建议通过 SSH 隧道访问：

```bash
ssh -N -L 18789:127.0.0.1:18789 <user>@<server-ip>
```

然后在本地浏览器访问 `http://127.0.0.1:18789`

---

## 🚀 快速检查清单

- [ ]  执行 `openclaw onboard` 启动配置向导
- [ ]  完成模型提供商配置（API Key 已填写）
- [ ]  配置消息渠道（如飞书应用已创建）
- [ ]  运行 `openclaw config validate` 验证配置
- [ ]  运行 `openclaw doctor --deep` 检查环境
- [ ]  启动网关 `openclaw gateway run`
- [ ]  成功访问控制台 UI

---

## ❓ 常见问题

**Q: 配置过程中断如何恢复？**
A: 重新执行 `openclaw onboard` 即可继续配置。

**Q: 如何修改已完成的配置？**
A: 使用 `openclaw config edit` 命令或访问控制台 UI 进行修改。

**Q: 远程服务器无法访问控制台？**
A: 确保使用 SSH 隧道转发端口，或检查服务器防火墙设置。

---

## 📚 相关资源

- [Moonshot AI 开放平台](https://platform.moonshot.cn/)
- [飞书开放平台文档](https://open.feishu.cn/document/)
- [OpenClaw 官方文档](https://docs.openclaw.io/)

---

*最后更新: 2026-03-19*
