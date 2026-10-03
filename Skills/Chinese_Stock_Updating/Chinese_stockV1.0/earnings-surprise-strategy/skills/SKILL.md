# earnings-surprise-strategy/skills/SKILL.md

---
name: earnings-surprise-strategy
description: 财报超预期交易策略 - 基于业绩超预期的基本面驱动交易
version: 1.0.0
author: QuantTeam
tags: [基本面, 财报分析, 业绩超预期, 价值投资]
dependencies:
  - akshare>=1.12.0
  - pandas>=1.5.0
  - numpy>=1.23.0
  - requests>=2.28.0
---

# 财报超预期策略

## 策略概述

财报超预期是A股市场确定性最高的交易策略之一。当公司公布的财报业绩显著超过市场预期时，股价往往会有强劲表现。

### 核心逻辑
超预期判断标准：

净利润同比增长 > 30%

营收同比增长 > 20%

实际EPS > 分析师预期 × 1.1（超预期10%以上）

毛利率环比提升 > 2个百分点

买入时机：

最佳买入窗口：财报公告后1-5个交易日

买入方式：公告次日开盘买入 或 回调至5日线买入

卖出规则：

止损：跌破公告日最低价或-8%

止盈：达到目标价（15-35%）或下一个财报季前

text

### 策略优势

- ✅ 确定性极高，历史胜率70-80%
- ✅ 逻辑清晰，基于基本面分析
- ✅ 机构共识强，资金推动明显
- ✅ 适合中线持仓，波动相对可控

### 策略劣势

- ❌ 财报季才有机会，非全年适用
- ❌ 需要专业财报数据接口
- ❌ 可能存在利好出尽风险

## 分析维度

| 维度 | 权重 | 评分标准 |
|------|------|---------|
| 超预期幅度 | 30% | 净利润/营收超预期百分比 |
| 增长质量 | 25% | 可持续性、现金流、毛利率 |
| 市场反应 | 20% | 公告后股价和成交量表现 |
| 机构态度 | 15% | 研报评级、目标价调整 |
| 行业景气度 | 10% | 行业增速、竞争格局 |

## 评分标准

| 总分 | 评级 | 操作建议 | 建议仓位 |
|------|------|---------|---------|
| ≥85分 | 强烈推荐 | 公告后积极买入 | 25% |
| 75-84分 | 推荐 | 择机买入 | 15% |
| 70-74分 | 关注 | 观察等待确认 | 10% |
| <70分 | 暂缓 | 不参与 | 0% |

## 使用方法

### 1. 扫描最新财报

```bash
# 扫描今日发布的财报
python3 scripts/earnings_scanner.py --scan --date today

# 扫描指定日期
python3 scripts/earnings_scanner.py --scan --date 2024-01-15
2. 分析单只股票
bash
# 分析特定股票的财报
python3 scripts/earnings_scanner.py --stock 600519 --name 贵州茅台 --quarter 2024Q1
3. 查看历史表现
bash
# 查看历史超预期股票表现
python3 scripts/earnings_scanner.py --backtest --start 2023-01-01 --end 2024-12-31
4. 启动定时任务
bash
# 导入定时任务
openclaw cron import cron/earnings-surprise-crons.yaml

# 查看任务
openclaw cron list
输出示例
财报分析报告
json
{
  "stock_code": "600519",
  "stock_name": "贵州茅台",
  "quarter": "2024Q1",
  "signal": "BUY",
  "score": 88.5,
  "surprise_details": {
    "net_profit": {
      "actual": 208.5,
      "expected": 185.2,
      "surprise_pct": 12.6,
      "yoy_growth": 25.3
    },
    "revenue": {
      "actual": 464.8,
      "expected": 450.5,
      "surprise_pct": 3.2,
      "yoy_growth": 18.5
    }
  },
  "recommendation": {
    "action": "积极买入",
    "entry_price": 1680.00,
    "stop_loss": 1545.60,
    "target_price": 1932.00,
    "holding_period": "2-4周"
  }
}