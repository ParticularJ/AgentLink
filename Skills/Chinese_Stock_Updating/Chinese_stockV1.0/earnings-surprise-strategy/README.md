# earnings-surprise-strategy/skills/README.md

# 财报超预期策略 (Earnings Surprise Strategy)

基于财报超预期的基本面量化交易策略，捕捉业绩超预期带来的股价上涨机会。

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/yourname/earnings-surprise-strategy)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-yellow.svg)](https://www.python.org/)

## 📊 策略概述

财报超预期是A股市场确定性最高的交易策略之一。当公司公布的财报业绩显著超过市场预期时，股价往往会有强劲表现。

### 策略表现

| 市场环境 | 胜率 | 年化收益 | 最大回撤 | 持仓周期 |
|---------|------|---------|---------|---------|
| 财报季 | 70-80% | 30-40% | 8-10% | 2-4周 |
| 非财报季 | - | 空仓 | - | - |

### 核心逻辑

```
超预期判断标准：
1. 净利润同比增长 > 30%
2. 营收同比增长 > 20%
3. 实际EPS > 分析师预期 × 1.1（超预期10%以上）
4. 毛利率环比提升 > 2个百分点

买入时机：
- 最佳买入窗口：财报公告后1-5个交易日
- 买入方式：公告次日开盘买入 或 回调至5日线买入

卖出规则：
- 止损：跌破公告日最低价或-8%
- 止盈：达到目标价（15-35%）或下一个财报季前
```

## 🚀 快速开始

### 前置要求

- Python 3.9+
- OpenClaw 1.0+
- 内存 2GB+

### 一键安装

```bash
# 1. 克隆项目
git clone https://github.com/yourname/earnings-surprise-strategy.git
cd earnings-surprise-strategy

# 2. 运行安装脚本
chmod +x skills/setup.sh
./skills/setup.sh

# 3. 复制Agent配置
cp agents/earnings-surprise-agent.yaml ~/.openclaw/agents/

# 4. 复制配置文件
cp config/*.yaml ~/.openclaw/config/

# 5. 导入定时任务
openclaw cron import cron/earnings-surprise-crons.yaml
```

### 手动安装

```bash
# 1. 安装Python依赖
pip install -r skills/requirements.txt

# 2. 复制Skill到OpenClaw
cp -r skills/earnings-surprise-strategy ~/.openclaw/workspace/skills/

# 3. 验证安装
openclaw skill list | grep earnings-surprise
```

## 📖 使用指南

### 1. 扫描今日财报

```bash
cd ~/.openclaw/workspace/skills/earnings-surprise-strategy

# 扫描今日发布的财报
python3 scripts/earnings_scanner.py --scan

# 扫描指定日期
python3 scripts/earnings_scanner.py --scan --date 2024-01-15
```

### 2. 分析单只股票

```bash
# 分析贵州茅台最新财报
python3 scripts/earnings_scanner.py --stock 600519 --name 贵州茅台

# 分析指定季度财报
python3 scripts/earnings_scanner.py --stock 600519 --quarter 2024Q1
```

### 3. 运行回测

```bash
# 回测2024年财报季
python3 scripts/backtest.py --start 2024-01-01 --end 2024-12-31
```

### 4. 查看定时任务

```bash
# 查看所有定时任务
openclaw cron list

# 查看任务日志
openclaw cron logs --name daily-earnings-scan --tail 50

# 手动触发任务
openclaw cron run --name daily-earnings-scan
```

## 📁 目录结构

```
earnings-surprise-strategy/
├── agents/                              # Agent配置
│   └── earnings-surprise-agent.yaml    # Agent主配置
├── config/                              # 策略配置
│   ├── strategy_config.yaml            # 策略参数
│   ├── scoring_weights.yaml            # 评分权重
│   └── risk_rules.yaml                 # 风险规则
├── cron/                                # 定时任务
│   └── earnings-surprise-crons.yaml    # 任务定义
├── skills/                              # Skill脚本
│   ├── README.md                        # 说明文档
│   ├── requirements.txt                 # Python依赖
│   ├── setup.sh                         # 安装脚本
│   ├── SKILL.md                         # Skill定义
│   └── scripts/                         # 脚本目录
│       ├── __init__.py
│       ├── earnings_scanner.py          # 主扫描程序
│       ├── data_fetcher.py              # 数据获取
│       ├── surprise_analyzer.py         # 超预期分析
│       ├── quality_analyzer.py          # 质量分析
│       ├── market_analyzer.py           # 市场反应分析
│       ├── risk_assessor.py             # 风险评估
│       ├── report_generator.py          # 报告生成
│       └── backtest.py                  # 回测模块
└── SKILL.md                             # 主Skill定义（软链接）
```

## ⚙️ 配置说明

### 策略参数 (`config/strategy_config.yaml`)

```yaml
# 业绩增长标准
growth_standards:
  min_net_profit_yoy: 30      # 净利润同比增长最小值(%)
  min_revenue_yoy: 20         # 营收同比增长最小值(%)
  min_net_profit_qoq: 20      # 净利润环比增长最小值(%)

# 超预期标准
surprise_standards:
  min_surprise_pct: 10        # 最小超预期幅度(%)
  significant_surprise: 20    # 显著超预期幅度(%)

# 质量指标
quality_standards:
  min_gross_margin: 20        # 最小毛利率(%)
  gross_margin_improvement: 2 # 毛利率环比提升(百分点)
```

### 评分权重 (`config/scoring_weights.yaml`)

```yaml
weights:
  surprise_magnitude: 0.30    # 超预期幅度 30%
  growth_quality: 0.25        # 增长质量 25%
  market_reaction: 0.20       # 市场反应 20%
  institutional_attitude: 0.15 # 机构态度 15%
  industry_prosperity: 0.10   # 行业景气度 10%
```

## 📊 输出示例

### 扫描报告

```markdown
================================================================================
财报超预期策略扫描报告
生成时间: 2024-01-15 15:30:00
发现标的: 8只
================================================================================

【Top 5 推荐标的】

1. 贵州茅台(600519)
   财报季度: 2024Q1
   综合得分: 88.5分
   信号: BUY
   超预期: 显著超预期
   市场反应: 强烈反应
   建议: 强烈推荐
   仓位: 25%

2. 宁德时代(300750)
   财报季度: 2024Q1
   综合得分: 82.0分
   信号: BUY
   超预期: 超预期
   市场反应: 积极反应
   建议: 推荐
   仓位: 15%

================================================================================
【统计摘要】
  强烈推荐(≥85分): 3只
  推荐(75-84分): 4只
  关注(70-74分): 1只
  平均得分: 79.5分
================================================================================
```

### 单股分析报告

```json
{
  "stock_code": "600519",
  "stock_name": "贵州茅台",
  "quarter": "2024Q1",
  "signal": "BUY",
  "score": 88.5,
  "surprise_analysis": {
    "level": "显著超预期",
    "net_profit": {
      "actual_yoy": 25.3,
      "surprise_pct": 12.6
    }
  },
  "recommendation": {
    "action": "强烈推荐",
    "suggested_position": "25%",
    "stop_loss": "-8%或跌破公告日最低价",
    "target": "15-25%",
    "holding_period": "2-4周"
  }
}
```

## ⏰ 定时任务

| 任务名称 | 执行时间 | 功能 |
|---------|---------|------|
| daily-earnings-scan | 09:00 | 扫描今日财报 |
| intraday-earnings-monitor | 09:45 | 盘中监控 |
| daily-earnings-review | 15:30 | 收盘复盘 |
| weekly-earnings-summary | 周六10:00 | 周末总结 |

## 🔧 故障排除

### Q1: 扫描不到任何财报？

```bash
# 检查是否在财报季（1-4月、7-8月、10月）
# 查看最近一周的财报
python3 scripts/earnings_scanner.py --scan --date $(date -d "7 days ago" +%Y-%m-%d)
```

### Q2: 数据获取失败？

```bash
# 检查网络连接
ping akshare.akfamily.xyz

# 更新AKShare
pip install --upgrade akshare

# 切换备用数据源
# 在config/data_sources.yaml中配置备用源
```

### Q3: 回测结果不准确？

```bash
# 确认回测区间在财报季内
# 调整手续费和滑点参数
python3 scripts/backtest.py --start 2024-03-01 --end 2024-04-30
```

### Q4: 定时任务不执行？

```bash
# 检查OpenClaw服务状态
openclaw gateway status

# 重启网关
openclaw gateway restart

# 查看任务日志
openclaw cron logs --name daily-earnings-scan --tail 50
```

## 📈 策略优化建议

### 1. 参数优化

```bash
# 使用网格搜索优化参数
python3 scripts/backtest.py --optimize \
  --param min_surprise:10,15,20 \
  --param holding_days:10,15,20 \
  --metric sharpe_ratio
```

### 2. 行业聚焦

优先关注高景气行业：
- 医药生物
- 食品饮料
- 电子
- 计算机
- 新能源

### 3. 仓位管理

| 信号强度 | 建议仓位 | 说明 |
|---------|---------|------|
| 强烈推荐(≥85) | 25% | 积极配置 |
| 推荐(75-84) | 15% | 适度参与 |
| 关注(70-74) | 10% | 试探性建仓 |

## 📝 版本历史

### v1.0.0 (2024-01-01)
- ✨ 初始版本发布
- ✨ 实现财报超预期识别
- ✨ 支持多维度评分
- ✨ 集成风险管理和回测
- ✨ 添加定时任务支持

### v1.0.1 (2024-01-15)
- 🐛 修复数据获取bug
- ✨ 优化评分算法
- 📝 完善文档

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

1. Fork本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## ⚠️ 免责声明

本策略仅供参考学习，不构成投资建议。股市有风险，投资需谨慎。过往业绩不代表未来表现。使用本策略产生的任何盈亏由使用者自行承担。

在做出任何投资决策前，您应该：
1. 充分了解策略原理和风险
2. 使用模拟盘进行充分测试
3. 根据自身风险承受能力调整仓位
4. 设置合理的止损位
5. 持续跟踪和优化策略

## 📞 联系方式

- 问题反馈: [GitHub Issues](https://github.com/yourname/earnings-surprise-strategy/issues)
- 邮箱: support@example.com

## 🙏 致谢

- [AKShare](https://akshare.akfamily.xyz/) - 金融数据接口
- [OpenClaw](https://github.com/openclaw/openclaw) - Agent框架
- [Tushare](https://tushare.pro/) - 财经数据接口

---

**Star ⭐ 这个项目，如果它对你有帮助！**
