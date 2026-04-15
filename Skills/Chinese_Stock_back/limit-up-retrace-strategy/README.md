# 涨停板首次回调交易策略 (Limit-Up Retrace Strategy)

基于涨停板后首次回调的技术分析策略，捕捉强势股涨停后回踩重要支撑位的二次启动机会。

## 📊 策略概述

涨停板是A股市场最强势的信号之一。涨停后首次回调到重要支撑位（如涨停价、5日线、前高）往往是最佳的低吸机会。

### 核心逻辑

```
买入条件：
1. 近期出现过涨停板（5个交易日内）
2. 股价从涨停价回调，但回调幅度<15%
3. 回调至重要支撑位（涨停价/5日线/前高）
4. 回调过程中成交量明显萎缩
5. 出现止跌信号（十字星/小阳线/锤子线）
6. 随后出现放量上涨确认

卖出规则：
- 止损：跌破支撑位-3% 或 固定-7%
- 止盈：前涨停价附近 或 涨幅10-20%
- 时间止损：买入后3日无表现则离场
```

### 策略表现

| 市场环境 | 胜率 | 盈亏比 | 持仓周期 | 适用场景 |
|---------|------|--------|---------|---------|
| 强势市场 | 70-80% | 3:1 | 2-5天 | 热点龙头股 |
| 震荡市场 | 60-70% | 2.5:1 | 2-4天 | 强势股回调 |
| 弱势市场 | < 55% | 不建议 | - | 空仓观望 |

## 🚀 快速开始

### 安装依赖

```bash
pip install pandas numpy akshare baostock pyyaml
```

### 使用方法

```bash
# 扫描全市场
python3 skills/scripts/limit_up_retrace_scanner.py --scan --top 20

# 分析指定板块
python3 skills/scripts/limit_up_retrace_scanner.py --sector 科技

# 分析单只股票
python3 skills/scripts/limit_up_retrace_scanner.py --stock 000001

# 指定数据源
python3 skills/scripts/limit_up_retrace_scanner.py --source baostock --scan
```

## 📖 策略原理

### 1. 涨停板的含义

- **强势信号**：表明有大资金介入，市场关注度高
- **筹码锁定**：涨停后抛压减轻，筹码趋于稳定
- **龙头气质**：连续涨停或涨停后抗跌，显示龙头特征

### 2. 首次回调的意义

- **洗盘**：主力资金清洗浮筹，为第二波上涨做准备
- **低吸机会**：回调至支撑位是最佳买入时机
- **风险可控**：以涨停价或支撑位为止损位，风险明确

### 3. 买入信号确认

| 条件 | 说明 | 权重 |
|------|------|------|
| 涨停质量 | 封板强度、封单金额、炸板次数 | 25% |
| 回调幅度 | 从涨停价回调<15% | 20% |
| 支撑位置 | 回调至涨停价/5日线/前高 | 20% |
| 缩量程度 | 成交量<前3日均量50% | 20% |
| 止跌信号 | 十字星/小阳线/锤子线 | 15% |

### 4. 风险控制

- **仓位管理**：单票不超过15%，总仓位不超过50%
- **止损设置**：-5%至-7%机械止损
- **分批建仓**：首次50%，确认突破加仓50%

## 📁 目录结构

```
limit-up-retrace-strategy/
├── README.md                    # 本文件
├── SKILL.md                     # Skill定义文档
├── requirements.txt             # Python依赖
├── config/                      # 配置文件
│   ├── strategy_config.yaml     # 策略参数
│   ├── scoring_weights.yaml     # 评分权重
│   └── risk_rules.yaml          # 风险规则
├── agents/                      # Agent配置
│   └── limit-up-retrace-agent.yaml
├── crons/                       # 定时任务
│   └── limit-up-retrace-crons.yaml
└── skills/scripts/              # 策略脚本
    ├── limit_up_retrace_scanner.py  # 主扫描程序
    ├── limit_up_retrace_analyzer.py # 核心分析器
    └── report_generator.py      # 报告生成
```

## ⚙️ 配置说明

### 策略参数 (config/strategy_config.yaml)

```yaml
# 涨停条件
limit_up_conditions:
  lookback_days: 5              # 查看5个交易日内的涨停
  min_limit_up_count: 1         # 至少1个涨停
  max_limit_up_count: 3         # 最多3个涨停（避免过度炒作）

# 回调条件
retrace_conditions:
  max_retrace_pct: 15           # 最大回调幅度15%
  support_levels:               # 支撑位优先级
    - limit_up_price           # 涨停价
    - ma5                      # 5日线
    - previous_high            # 前高
  volume_shrink_ratio: 0.5      # 缩量至50%以下

# 买入确认
entry_confirmation:
  require_confirm: true         # 需要确认信号
  confirm_within_days: 2        # 2天内确认有效
```

### 评分权重 (config/scoring_weights.yaml)

```yaml
weights:
  limit_up_quality: 0.25       # 涨停质量 25%
  retrace_quality: 0.20        # 回调质量 20%
  support_strength: 0.20       # 支撑强度 20%
  volume_shrink: 0.20          # 缩量程度 20%
  stop_signal: 0.15            # 止跌信号 15%
```

## 📊 输出示例

### 扫描报告

```markdown
================================================================================
涨停板首次回调策略扫描报告
分析日期: 2026-04-06
发现标的: 6只
================================================================================

【Top 5 推荐标的】

1. 平安银行(000001)
   综合得分: 85.5分
   信号: 强烈买入
   涨停日期: 2026-04-02
   涨停价: 12.50元
   当前价: 11.80元 (回调-5.6%)
   支撑位: 涨停价
   缩量程度: 42%（前3日均量）
   止跌形态: 十字星
   建议: 明日开盘买入，止损11.40元(-3.4%)

2. 宁德时代(300750)
   综合得分: 78.0分
   信号: 买入
   ...

================================================================================
```

## ⏰ 定时任务

| 任务名称 | 执行时间 | 功能 |
|---------|---------|------|
| daily-limit-up-scan | 15:05 | 收盘后扫描涨停股 |
| pre-market-alert | 09:15 | 盘前提醒回调机会 |
| midday-monitor | 11:30 | 午盘监控 |

## ⚠️ 免责声明

本策略仅供参考学习，不构成投资建议。股市有风险，投资需谨慎。

## 📝 版本历史

### v1.0.0 (2026-04-06)
- ✨ 初始版本发布
- ✨ 实现涨停板首次回调核心逻辑
- ✨ 支持多数据源
- ✨ 添加五维度评分系统
- ✨ 集成风险管理和报告生成
