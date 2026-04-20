# 持仓实时监控 (sell-monitor)

A 股持仓股票的差异化止盈/止损监控策略，根据买入原因（`buy_reason`）自动匹配不同的风险参数。

## 功能特性

- **差异化止盈/止损**：激进（涨停/突破）/稳健（均线/缺口）/保守（超跌反弹）/超短（尾盘）
- **三层过滤**：技术面 + 消息面 + 宏观确认
- **大盘仓位自适应**：根据上证/深证/创业板自动调整总仓位上限
- **调仓分析**：持仓股 vs 推荐股四维度打分对比

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置持仓

创建持仓文件 `Chinese_Stock/my_holdings/holdings.json`（脚本自动读取）：

```json
[
  {
    "code": "600105",
    "name": "永鼎股份",
    "buy_price": 38.10,
    "shares": 1000,
    "position_ratio": 0.20,
    "position_value": 38100,
    "buy_reason": "breakout_high",
    "buy_date": "2026-04-11"
  }
]
```

**buy_reason 可选值：**

| buy_reason | 含义 | 策略类型 | 止损 |
|-----------|------|---------|-----|
| `limit_up` | 涨停连板 | 激进 | -7% |
| `breakout_high` | 突破新高 | 激进 | -7% |
| `gap_fill` | 缺口填充 | 稳健 | -5% |
| `ma_bullish` | 均线多头 | 稳健 | -5% |
| `macd_divergence` | MACD底背离 | 保守 | -3% |
| `rsi_oversold` | RSI超卖 | 保守 | -3% |
| `morning_star` | 早晨之星 | 保守 | -3% |
| `volume_extreme` | 地量见底 | 保守 | -3% |
| `a_stock_1430` | 尾盘超短 | 超短 | -2% |

### 3. 运行监控

```bash
# 基本运行
python3 scripts/monitor.py

# 指定持仓文件
python3 scripts/monitor.py

# 指定大盘状态（覆盖自动判断）
python3 scripts/monitor.py --market-status bullish

# 传入持仓JSON
python3 scripts/monitor.py --holdings '[{"code":"600105","name":"永鼎股份","buy_price":38.10,"shares":1000,"buy_reason":"breakout_high"}]'
```

### 4. 运行调仓分析

```bash
# 自动读取 Chinese_Stock/recommendations/ 最新推荐文件
python3 scripts/rebalance.py
```

## 止盈速查表

| 策略 | 止损 | 盈利≥10% | 盈利≥20% | 盈利≥30% |
|------|------|---------|---------|---------|
| 激进（涨停/突破）| -7% | 不止盈 | 不止盈 | 减30% |
| 稳健（均线/缺口）| -5% | 减30% | 减50% | 减70% |
| 保守（超跌反弹）| -3% | 减50% | 清仓 | - |
| 超短（尾盘） | -2% | 清仓 | - | - |

## 文件结构

```
sell-monitor/
├── SKILL.md                      # 详细策略文档
├── README.md                     # 本文件
├── requirements.txt              # Python依赖
├── scripts/
│   ├── monitor.py               # 核心监控脚本
│   ├── indicators.py            # 技术指标（RSI/MACD/成交量）
│   ├── news_sentiment.py        # 新闻情绪分析
│   ├── market_env.py            # 大盘环境判断
│   ├── strategy_config.py       # 策略参数配置
│   └── rebalance.py             # 调仓分析脚本
└── crons/
    └── sell-monitor-crons.yaml  # 定时任务配置
```

## 大盘状态与仓位

大盘状态由系统根据三大指数自动判断：

| 大盘状态 | 条件 | 总仓位上限 |
|---------|------|-----------|
| 强势 | 三指数平均涨幅 >1.5% | 80% |
| 偏多 | 三指数平均涨幅 >0.5% | 60% |
| 中性 | 三指数平均涨跌幅 -1%~1% | 50% |
| 偏空 | 三指数平均跌幅 >1% | 30% |
| 弱势 | 三指数平均跌幅 >2% | 10% |

## 与 OpenClaw Cron 集成

使用 OpenClaw 的 cron 功能实现自动监控：

```bash
# 添加定时任务（每5分钟监控一次）
openclaw cron add \
  --name "持仓监控" \
  --cron "*/5 9,10,13,14 * * 1-5" \
  --tz "Asia/Shanghai" \
  --session isolated \
  --message "python3 ~/.npm-global/lib/node_modules/openclaw/skills/Stock/Chinese_Stock/sell-monitor/scripts/monitor.py" \
  --announce \
  --channel feishu \
  --to "chat:你的飞书群ID"
```

## 信号类型

| 信号 | 含义 |
|------|------|
| 💰 止盈建议 | 盈利达标，触发止盈 |
| 🚨 止损 | 触及硬性止损线，强制清仓 |
| 🔴 减仓警告 | RSI/MACD 偏空，建议减仓 |
| 🟢 加仓 | 超跌/趋势确认，可加仓摊薄 |
| 🟡 轻度注意 | 需密切关注，暂无操作 |
| 🟢 继续持有 | 安心持有 |

## 数据来源

- 实时行情：akshare（东方财富/新浪）
- 新闻舆情：Tavily API（需配置 `TAVILY_API_KEY`）
- 主力资金：akshare（东方财富）

## 免责声明

本工具仅供参考，不构成投资建议。股市有风险，投资需谨慎。
