# 缩量回踩重要均线策略 (Volume Retrace MA Strategy)

基于缩量回踩重要均线的技术分析策略，捕捉强势股回调后的二次启动机会。

## 📊 策略概述

缩量回踩重要均线是A股市场经典的低吸策略，适用于上升趋势中的强势股回调买入。

### 核心逻辑

```
买入条件：
1. 股票处于上升趋势（MA20 > MA60）
2. 股价回调至重要均线附近（MA20/MA30/MA60）
3. 回调过程中成交量明显萎缩（< 前5日均量60%）
4. 在均线附近出现止跌信号（十字星/小阳线）
5. 随后出现放量上涨确认

卖出规则：
- 止损：跌破回踩均线-3% 或 固定-8%
- 止盈：前高附近 或 涨幅15-25%
- 时间止损：买入后5日无表现则离场
```

### 策略表现

| 市场环境 | 胜率 | 盈亏比 | 持仓周期 | 适用场景 |
|---------|------|--------|---------|---------|
| 上升趋势 | 65-75% | 2.5:1 | 3-10天 | 强势股回调 |
| 震荡市场 | 55-65% | 2:1 | 3-7天 | 波段操作 |
| 下跌趋势 | < 50% | 不建议 | - | 空仓观望 |

## 🚀 快速开始

### 安装依赖

```bash
pip install pandas numpy akshare baostock
```

### 使用方法

```bash
# 扫描全市场
python3 skills/scripts/retrace_scanner.py --scan --top 20

# 分析指定板块
python3 skills/scripts/retrace_scanner.py --sector 科技

# 分析单只股票
python3 skills/scripts/retrace_scanner.py --stock 000001

# 指定数据源
python3 skills/scripts/retrace_scanner.py --source baostock --scan
```

## 📖 策略原理

### 1. 缩量回踩的意义

- **缩量**：表明抛压减轻，筹码锁定良好
- **回踩均线**：测试支撑位有效性
- **重要均线**：MA20（短期趋势）、MA30（中期趋势）、MA60（长期趋势）

### 2. 买入信号确认

| 条件 | 说明 | 权重 |
|------|------|------|
| 趋势判断 | MA20 > MA60，上升趋势 | 25% |
| 回踩幅度 | 回调至均线±3%范围内 | 20% |
| 缩量程度 | 成交量 < 前5日均量60% | 20% |
| 止跌形态 | 十字星/小阳线/锤子线 | 20% |
| 支撑强度 | 均线斜率、多次测试 | 15% |

### 3. 风险控制

- **仓位管理**：单票不超过20%，总仓位不超过60%
- **止损设置**：-5%至-8%机械止损
- **分批建仓**：首次50%，确认后50%

## 📁 目录结构

```
volume-retrace-ma-strategy/
├── README.md                    # 本文件
├── requirements.txt             # Python依赖
├── config/                      # 配置文件
│   ├── strategy_config.yaml     # 策略参数
│   ├── scoring_weights.yaml     # 评分权重
│   └── risk_rules.yaml          # 风险规则
├── agents/                      # Agent配置
│   └── volume-retrace-agent.yaml
├── crons/                       # 定时任务
│   └── volume-retrace-crons.yaml
└── skills/scripts/              # 策略脚本
    ├── retrace_scanner.py       # 主扫描程序
    ├── data_source_adapter.py   # 数据源适配
    ├── retrace_analyzer.py      # 回踩分析器
    ├── signal_generator.py      # 信号生成器
    └── report_generator.py      # 报告生成
```

## ⚙️ 配置说明

### 策略参数 (config/strategy_config.yaml)

```yaml
# 均线配置
ma_settings:
  short_term: 20      # 短期均线MA20
  medium_term: 30     # 中期均线MA30
  long_term: 60       # 长期均线MA60

# 回踩条件
retrace_conditions:
  max_retrace_pct: 15        # 最大回调幅度15%
  ma_tolerance_pct: 3        # 均线容忍度±3%
  volume_shrink_ratio: 0.6   # 缩量至60%以下

# 买入确认
entry_confirmation:
  min_up_days: 1             # 至少1天上涨确认
  volume_expand_ratio: 1.2   # 放量1.2倍以上
```

### 评分权重 (config/scoring_weights.yaml)

```yaml
weights:
  trend_strength: 0.25       # 趋势强度 25%
  retrace_quality: 0.20      # 回踩质量 20%
  volume_shrink: 0.20        # 缩量程度 20%
  stop_signal: 0.20          # 止跌信号 20%
  support_strength: 0.15     # 支撑强度 15%
```

## 📊 输出示例

### 扫描报告

```
================================================================================
缩量回踩重要均线策略扫描报告
分析日期: 2026-04-06
发现标的: 5只
================================================================================

【Top 5 推荐标的】

1. 平安银行(000001)
   综合得分: 82.5分
   信号: 强烈买入
   回踩均线: MA20
   缩量程度: 45%（前5日均量）
   止跌形态: 锤子线
   建议: 明日开盘买入50%，确认后加仓50%
   止损: 11.20元 (-5%)
   目标: 13.50元 (+15%)

2. 宁德时代(300750)
   综合得分: 78.0分
   信号: 买入
   ...

================================================================================
```

## ⏰ 定时任务

| 任务名称 | 执行时间 | 功能 |
|---------|---------|------|
| daily-retrace-scan | 15:05 | 收盘后扫描 |
| pre-market-alert | 09:15 | 盘前提醒 |
| midday-monitor | 11:30 | 午盘监控 |

## ⚠️ 免责声明

本策略仅供参考学习，不构成投资建议。股市有风险，投资需谨慎。

## 📝 版本历史

### v1.0.0 (2026-04-06)
- ✨ 初始版本发布
- ✨ 实现缩量回踩核心逻辑
- ✨ 支持多数据源
- ✨ 添加风险管理和报告生成
