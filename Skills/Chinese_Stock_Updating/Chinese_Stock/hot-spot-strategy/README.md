# 热点仓策略

捕捉A股短期情绪溢价与资金惯性的短线交易策略体系，持仓周期3-8天，资金占比20-30%。

## 包含策略

| 策略 | 说明 | 版本 |
|:---|:---|:---|
| **hot-spot-strategy** | 热点仓四大策略体系（首板/回调/龙头/次新） | v1.1.0 |
| **limit-up-retrace-strategy** | 涨停板首次回调策略 | v1.0.0 |
| **limit-up-analysis** | 涨停分析工具 | v1.0.0 |

## 策略特点

- 🔥 **四大策略体系**：首次涨停板、涨停回调、热门板块龙头、次新股
- 📊 **量化评分模型**：0-100分多维评分，交叉验证加分
- 🛡️ **立体风控框架**：固定止损、ATR动态止损、移动止损、时间止损、Chandelier Exit
- 💰 **智能仓位管理**：动态仓位建议、加仓策略、熔断机制
- 📈 **实时监控**：盘中监控+收盘监控+特殊信号识别
- 📋 **每日复盘**：自动生成交易复盘报告

## 目录结构

```
热点仓策略/
├── README.md                          # 本文件
├── hot-spot-strategy/                 # 热点仓四大策略体系
│   ├── SKILL.md                       # Skill定义文档
│   ├── README.md                      # 策略说明
│   ├── requirements.txt               # Python依赖
│   ├── config/                        # 配置文件
│   │   ├── strategy_config.yaml       # 策略参数
│   │   ├── scoring_weights.yaml       # 评分权重
│   │   └── risk_rules.yaml            # 风险规则
│   ├── agents/                        # Agent配置
│   │   └── hot-spot-agent.yaml
│   ├── crons/                         # 定时任务
│   │   └── hot-spot-crons.yaml
│   └── skills/scripts/                # 策略脚本
│       ├── models.py                  # 数据模型
│       ├── strategy_scorer.py         # 四大策略评分器
│       ├── portfolio_manager.py       # 组合管理器
│       ├── risk_manager.py            # 风险管理器
│       ├── hot_spot_pipeline.py       # 主流程管道
│       └── test_hot_spot.py           # 单元测试
├── limit-up-retrace-strategy/         # 涨停回调策略
│   ├── SKILL.md                       # Skill定义文档
│   ├── README.md                      # 策略说明
│   ├── requirements.txt               # Python依赖
│   ├── config/                        # 配置文件
│   └── skills/scripts/                # 策略脚本
│       ├── limit_up_retrace_scanner.py      # 扫描器
│       └── limit_up_retrace_strategy_analyzer.py  # 分析器
├── limit-up-analysis/                 # 涨停分析工具
│   ├── SKILL.md                       # Skill定义文档
│   ├── README.md                      # 策略说明
│   ├── config/                        # 配置文件
│   └── skills/scripts/                # 分析脚本
├── stock-pool/                        # 股票池
│   └── README.md
├── holdings/                          # 持仓数据
│   └── README.md
└── recommendations/                   # 推荐记录
    └── README.md
```

## 四大策略体系

### 策略一：首次涨停板
- **目标**：捕捉个股从量变到质变的突破节点
- **评分维度**：涨停时间(30%)、封单质量(25%)、板块效应(25%)、换手率(20%)
- **入围门槛**：≥75分
- **持股周期**：3-5天

### 策略二：涨停回调
- **目标**：利用获利回吐后的技术性反弹获取收益
- **评分维度**：回调幅度(25%)、回调天数(20%)、缩量程度(25%)、企稳信号(30%)
- **入围门槛**：≥65分
- **持股周期**：5-7天，可加仓1次

### 策略三：热门板块龙头
- **目标**：捕捉板块龙头股的趋势性机会
- **评分维度**：涨幅领先度(25%)、涨停强度(15%)、板块热度(20%)、带动性(15%)、换手率(15%)、流通市值(10%)
- **入围门槛**：≥70分
- **持股周期**：5-8天，可加仓1次

### 策略四：次新股（T+0层）
- **目标**：上市当日新股的机会捕捉
- **评分维度**：行业景气度(30%)、首日换手率(25%)、尾盘企稳(25%)、发行估值(20%)
- **入围门槛**：≥80分
- **持股周期**：最长3天

## 快速开始

```python
from hot-spot-strategy.skills.scripts.hot_spot_pipeline import HotSpotPipeline
from hot-spot-strategy.skills.scripts.models import StrategyType

# 创建管道
pipeline = HotSpotPipeline(total_capital=1000000.0)

# 准备数据
stocks_data = {
    StrategyType.FIRST_LIMIT_UP: [...],
    StrategyType.LIMIT_UP_RETRACE: [...],
    StrategyType.SECTOR_LEADER: [...],
    StrategyType.NEW_STOCK: [...],
}

# 生成推荐
recommendations = pipeline.generate_recommendations(stocks_data)

# 执行买入
for rec in recommendations:
    position = pipeline.execute_buy(rec, entry_price=12.50)

# 监控持仓
signals = pipeline.monitor_positions(market_data)

# 执行卖出
for signal in signals:
    if signal.action == "SELL":
        pipeline.execute_sell(signal)

# 每日复盘
summary = pipeline.daily_review()
```

## 资金配置

| 规则 | 数值 |
|:---|:---|
| 热点仓占总资金 | 20%-30% |
| 单只股票最大仓位 | ≤热点仓资金的30% |
| 同时持有股票数量 | ≤3只 |
| 单日总亏损上限 | 热点仓资金的2% |

## 风险控制

### 止损规则
- **固定止损**：成本价-7%
- **ATR动态止损**：买入价-2×ATR(14)
- **移动止损**：从最高点回撤-5%（浮盈>5%后启用）
- **时间止损**：持有5日未盈利（次新股3天）
- **均线止损**：收盘破5日线

### 止盈规则
- **普通热点股**：5%卖1/3，10%再卖1/3，>20%剩余保本
- **龙头股**：5%/10%/20%/30%四档分批止盈
- **次新股**：5%-10%卖1/2，>10%逐步清仓

### 熔断机制
- **一级熔断**：日亏损达1.5%，禁止开新仓
- **二级熔断**：日亏损达2%，强制清仓，停止交易
- **连续熔断**：连续2日触发二级熔断，暂停交易3天

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。
