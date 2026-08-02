# SKILL.md

---
name: strategy-optimizer
description: 策略优化器 - 基于回测数据和预测结果自动优化交易策略参数
version: 1.0.0
author: QuantTeam
tags: [优化, 参数调优, 机器学习, 回测分析]
dependencies:
  - pandas>=1.5.0
  - numpy>=1.23.0
  - pyyaml>=6.0
  - scikit-learn>=1.2.0
---

# 策略优化器

## 概述

策略优化器是一个自动化工具，用于分析现有策略的回测数据，通过网格搜索和参数调优，自动优化策略参数，提高策略表现。

## 核心功能

### 1. 参数优化
- 网格搜索最优参数组合
- 支持整数、浮点数参数
- 自定义参数范围

### 2. 权重优化
- 优化评分维度权重
- 自动归一化处理
- 交叉验证验证

### 3. 阈值优化
- 优化买入/卖出阈值
- 调整评分标准
- 改善信号质量

### 4. 性能分析
- 计算胜率、夏普比率
- 分析最大回撤
- 生成综合评分

## 使用方法

### 1. 优化单个策略

```bash
cd ~/.openclaw/workspace/skills/strategy-optimizer
python3 skills/scripts/strategy_optimizer.py --strategy pullback-to-ma-strategy
2. 优化所有策略
bash
python3 skills/scripts/strategy_optimizer.py --all
3. 优化评分权重
bash
python3 skills/scripts/strategy_optimizer.py --weights pullback-to-ma-strategy
4. 启动定时任务
bash
openclaw cron import crons/strategy-optimizer-crons.yaml
优化流程
text
1. 收集回测数据
       ↓
2. 分析当前表现
       ↓
3. 生成参数组合
       ↓
4. 网格搜索优化
       ↓
5. 验证优化效果
       ↓
6. 输出优化报告
优化参数示例
yaml
pullback-to-ma-strategy:
  parameters:
    ma_short: [3, 5, 7, 10]      # 短期均线
    ma_mid: [8, 10, 12, 15]      # 中期均线
    ma_long: [15, 20, 25, 30]    # 长期均线
    volume_ratio_min: [0.4, 0.5, 0.6, 0.7]  # 缩量比例
输出示例
json
{
  "strategy": "pullback-to-ma-strategy",
  "current_performance": {
    "win_rate": 65.5,
    "sharpe_ratio": 1.35,
    "max_drawdown": 8.2
  },
  "optimized_params": {
    "ma_short": 5,
    "ma_mid": 10,
    "ma_long": 20,
    "volume_ratio_min": 0.55
  },
  "validation": {
    "win_rate_improvement": 3.2,
    "sharpe_improvement": 0.15,
    "drawdown_reduction": 1.5
  }
}
定时任务
任务名称	执行时间	功能
weekly-strategy-optimization	周日22:00	每周策略优化
monthly-comprehensive-optimization	每月1日23:00	月度综合优化
daily-strategy-health-check	每日20:00	策略健康检查
版本历史
v1.0.0 (2024-01-01)
初始版本发布

实现参数网格搜索

支持权重优化

集成性能分析

免责声明
优化结果基于历史数据，不保证未来表现。建议在模拟盘验证后应用优化参数。

text

## 13. README.md

```markdown
# README.md

# 策略优化器

基于OpenClaw开发的自动化策略优化工具，用于分析回测数据并优化交易策略参数。

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
优化单个策略
bash
python skills/scripts/strategy_optimizer.py --strategy pullback-to-ma-strategy
优化所有策略
bash
python skills/scripts/strategy_optimizer.py --all
目录结构
text
strategy-optimizer/
├── agents/
│   └── strategy-optimizer-agent.yaml
├── config/
│   ├── optimizer_config.yaml
│   ├── optimization_params.yaml
│   └── evaluation_config.yaml
├── crons/
│   └── strategy-optimizer-crons.yaml
├── skills/scripts/
│   ├── strategy_optimizer.py
│   ├── param_optimizer.py
│   ├── performance_analyzer.py
│   ├── model_updater.py
│   └── demo.py
├── data/
│   ├── backtest_results/
│   ├── predictions/
│   └── optimized_params/
├── README.md
├── requirements.txt
└── SKILL.md
支持的策略
pullback-to-ma-strategy（缩量回踩均线）

earnings-surprise-strategy（财报超预期）

ma-bullish-strategy（均线多头排列）

limit-up-pullback-strategy（涨停回调）

macd-divergence-strategy（MACD底背离）

morning-star-strategy（早晨之星）

breakout-high-strategy（突破高点）

rsi-oversold-strategy（RSI超卖）

volume-extreme-strategy（地量见底）

gap-fill-strategy（缺口回补）

版本历史
v1.0.0 (2024-01-01)
初始版本发布

许可证
MIT License

text

## 14. requirements.txt

```txt
# requirements.txt

pandas>=1.5.0
numpy>=1.23.0
pyyaml>=6.0
scikit-learn>=1.2.0