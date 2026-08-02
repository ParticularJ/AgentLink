# 统一数据采集层

## 概述

为 Chinese_Stock 下的 10 个策略（除 limit-up-analysis 已有保存机制）提供统一的结果持久化功能。

## 文件说明

| 文件 | 说明 |
|------|------|
| `data_collector.py` | 核心采集器，负责结果的标准化保存和加载 |
| `run_and_save.py` | 通用执行器，通过命令行运行指定策略并保存结果 |
| `batch_collector.py` | 批量执行器，一次运行所有策略（耗时长，适合 cron） |

## 数据存储位置

```
~/.openclaw/stock/data/
├── ma-bullish-strategy/
│   └── 2026-04-11.json
├── earnings-surprise-strategy/
│   └── 2026-04-11.json
├── limit-up-retrace-strategy/
│   └── 2026-04-11.json
├── macd-divergence-strategy/
│   └── 2026-04-11.json
├── morning-star-strategy/
│   └── 2026-04-11.json
├── breakout-high-strategy/
│   └── 2026-04-11.json
├── rsi-oversold-strategy/
│   └── 2026-04-11.json
├── volume-extreme-strategy/
│   └── 2026-04-11.json
├── gap-fill-strategy/
│   └── 2026-04-11.json
└── volume-retrace-ma-strategy/
    └── 2026-04-11.json
```

## 使用方法

### 方法1：单策略执行（推荐日常使用）

```bash
# 运行单个策略并保存结果
python3 _shared/run_and_save.py ma-bullish-strategy 2026-04-11

# 不保存，仅查看结果
python3 _shared/run_and_save.py ma-bullish-strategy 2026-04-11 --no-save

# 不指定日期，默认今天
python3 _shared/run_and_save.py limit-up-retrace-strategy
```

### 方法2：批量执行（适合 cron 收盘后运行）

```bash
# 一次运行所有策略（耗时约 10-30 分钟）
python3 _shared/batch_collector.py --date 2026-04-11

# 仅扫描不保存
python3 _shared/batch_collector.py --dry-run
```

### 方法3：在 Python 代码中调用

```python
from _shared.data_collector import DataCollector, collect

# 方式1：直接使用
collector = DataCollector()
filepath = collector.save('ma-bullish-strategy', results_list, '2026-04-11')

# 方式2：使用便捷函数
filepath = collect('ma-bullish-strategy', results_list, '2026-04-11')

# 读取历史数据
results = collector.load('ma-bullish-strategy', '2026-04-11')
```

## JSON 数据格式

每个策略的输出被标准化为统一格式：

```json
{
  "date": "2026-04-11",
  "strategy": "ma-bullish-strategy",
  "stock_code": "000001",
  "stock_name": "平安银行",
  "signal": "BUY",
  "score": 82.5,
  "current_price": 12.50,
  "entry_price": 12.55,
  "stop_loss": 11.88,
  "target_price": 13.75,
  "risk_reward_ratio": 2.5,
  "details": {...},
  "suggestion": "建议开盘买入50%...",
  "analysis_time": "2026-04-11 22:30:00"
}
```

## 每日推荐数量

| 策略 | 每日约推荐数 | 最低评分门槛 |
|------|------------|------------|
| ma-bullish-strategy | 5~20 | score≥70 + signal=BUY |
| earnings-surprise-strategy | 3~15 | score≥70 |
| limit-up-retrace-strategy | 2~10 | score≥75 |
| macd-divergence-strategy | 3~15 | score≥75 |
| morning-star-strategy | 3~15 | score≥70 |
| breakout-high-strategy | 3~15 | score≥70 |
| rsi-oversold-strategy | 5~20 | score≥70 |
| volume-extreme-strategy | 5~20 | score≥70 |
| gap-fill-strategy | 3~15 | score≥70 |
| volume-retrace-ma-strategy | 3~15 | score≥70 |

**每日合计约 40~160 只候选**（视市场情况）

## 定时任务建议

```bash
# 交易日收盘后自动运行（周一~周五 16:30）
openclaw cron add \
  --name "daily-strategy-collect" \
  --schedule "cron:30 16 * * 1-5" \
  --sessionTarget isolated \
  --payload.kind agentTurn \
  --payload.message "运行批量采集: cd /home/jarvis/.openclaw/workspace/skills/Chinese_Stock/_shared && python3 batch_collector.py"
```

## 下一步

数据采集后的应用场景：
1. **策略优化** - 将历史 JSON 数据转换为 optimizer 所需的 CSV 回测格式
2. **策略融合** - 将各策略输出汇聚给 `strategy-fusion-advisor` 生成综合推荐
3. **结果展示** - 每日生成汇总报告推送
