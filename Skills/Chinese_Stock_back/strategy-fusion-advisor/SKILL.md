# SKILL.md

---
name: strategy-fusion-advisor
description: 策略融合投资顾问 - 融合11个交易策略的推荐结果，输出最优投资组合
version: 1.0.0
author: QuantTeam
tags: [投资组合, 策略融合, 仓位管理, 智能投顾]
dependencies:
  - pandas>=1.5.0
  - numpy>=1.23.0
  - pyyaml>=6.0
---

# 策略融合投资顾问

## 概述

策略融合投资顾问收集自选股池中各策略的推荐信号，按时间段（尾盘/早盘）分组融合，输出 top5 推荐股票及仓位建议。

## 运行逻辑

### 14:30 尾盘买策略（EVENING）
- 缺口填充、涨停回踩、MACD底背离、RSI超卖、地量见底、缩量回踩均线、均线多头

### 16:00 早盘买策略（MORNING，次日）
- 突破新高、涨停分析/打板、业绩超预期、早晨之星

## 推荐输出

写入 `recommendations/YYYYMMDD_EVENING_BUY_recommendation.json` 或 `recommendations/YYYYMMDD_MORNING_BUY_recommendation.json`

## 定时任务

```bash
# 每天 14:30 尾盘买
python3 skills/scripts/fusion_runner.py --session EVENING --top 5

# 每天 16:00 早盘买
python3 skills/scripts/fusion_runner.py --session MORNING --top 5
```

融合后每个推荐包含：股票代码、名称、综合得分、确认策略、买入理由、建议仓位

## 目录结构

```
strategy-fusion-advisor/
├── SKILL.md
├── README.md
├── requirements.txt
├── crons/
│   └── strategy-fusion-crons.yaml   # 定时任务配置
└── skills/scripts/
    └── fusion_runner.py             # 融合运行器（主入口）
```

## 免责声明

本工具仅供参考学习，不构成投资建议。股市有风险，投资需谨慎。
