# 核心仓策略

基于赛道生命周期与基本面六维评分的核心仓位管理系统，持仓周期3-6个月，资金占比50%。

## 包含策略

| 策略 | 说明 | 版本 |
|:---|:---|:---|
| **core-position-strategy** | 核心仓V3.0 - 赛道生命周期+基本面六维评分 | v3.0.0 |
| **Medium-termHoldingStrategy** | 中期持仓监控与交易执行系统 | v1.0.0 |

## 策略特点

- 🌍 **宏观流动性匹配**：扩张期/稳定期/收缩期三档环境判断
- 🎯 **赛道生命周期评估**：仅参与爆发初期（5-10%）和爆发中期（10-20%）
- 📊 **六维个股初筛**：赛道热度、产业链地位、技术壁垒、业绩确定性、管理层质量、机构共识
- 🛡️ **强化一票否决**：管理层诚信、机构覆盖、ROE、质押比例等8项红线
- 📈 **财报验证模型**：营收/利润/现金流/毛利率/前瞻指标五维评分
- 🔍 **超预期验证**：股价反应、研报反应、资金反应、北向资金四维验证
- ⏰ **每日买点判断**：上升趋势回踩20日线（首选）+ 大盘环境过滤
- 💰 **智能仓位计算**：基准仓位 × 综合评分系数 × 技术面系数 × 大盘系数
- 📉 **波动率自适应止损**：ATR动态止损替代固定百分比
- 📊 **分层止盈**：15%/25%/40%/60%四档分批止盈
- ➕ **加仓策略**：浮盈20%/40%两档加仓，逆板块不加仓铁律
- 🛡️ **三道防线风控**：个股止损→行业止损→组合止损

## 目录结构

```
核心仓策略/
├── README.md                          # 本文件
├── core-position-strategy/            # 核心仓V3.0策略引擎
│   ├── SKILL.md                       # Skill定义文档
│   └── skills/scripts/
│       ├── models.py                  # 数据模型
│       ├── macro_filter.py            # 宏观流动性过滤器
│       ├── sector_scorer.py           # 赛道评分器
│       ├── initial_scorer.py          # 个股初筛评分器
│       ├── secondary_scorer.py        # 二次筛选评分器（财报验证）
│       ├── buy_signal.py              # 每日买点判断
│       ├── position_monitor.py        # 持仓监控（止损/止盈/加仓）
│       ├── portfolio_manager.py       # 组合管理器
│       ├── core_position_pipeline.py  # 主流程管道
│       └── test_core_position.py      # 单元测试
├── Medium-termHoldingStrategy/        # 中期持仓监控执行
│   └── skills/
│       ├── SKILL.md                   # 交易执行器文档
│       ├── trade_executor.py          # 执行引擎
│       └── scripts/                   # 监控与执行脚本
│           ├── main.py
│           ├── new_holding_monitor.py
│           ├── stop_loss_engine.py
│           ├── add_position_analyzer.py
│           └── ...
├── stock-pool/                        # 股票池
│   ├── README.md
│   ├── watchlist.yaml                 # 观察列表
│   └── watchlist_copy.yaml            # 观察列表备份
├── holdings/                          # 持仓数据
│   ├── README.md
│   ├── holdings.json                  # 当前持仓
│   ├── cash_balance.json              # 现金余额
│   └── backup/                        # 历史备份
└── recommendations/                   # 推荐记录
    ├── README.md
    └── *.json                         # 每日推荐
```

## 使用流程

### 1. 季度选股（阶段1-2）
```python
from core-position-strategy.skills.scripts.core_position_pipeline import CorePositionPipeline

pipeline = CorePositionPipeline(total_capital=1000000.0, core_ratio=0.50)
result = pipeline.run_full_pipeline(
    macro_data={...},
    sectors_data=[...],
    stocks_data=[...],
    financial_reports={...},
    verifications={...},
    market_data={...},
    tech_data_map={...},
    stock_fundamentals={...}
)
```

### 2. 每日监控（阶段3-4）
```python
monitor_result = pipeline.run_daily_monitor(
    daily_tech_data={...},
    weekly_fundamental_data={...},
    market_data={...}
)
```

### 3. 交易执行
通过 Medium-termHoldingStrategy 的 trade_executor 执行实际交易。

## 资金配置

| 规则 | 数值 |
|:---|:---|
| 核心仓占总资金 | 50% |
| 单只个股最大仓位 | ≤18% |
| 最多持仓数量 | 8只 |
| 组合止损线 | -15% |

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。
