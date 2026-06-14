# 共享组件

三大策略共享的数据存储、配置管理和公共脚本。

## 目录结构

```
共享组件/
├── _shared/                         # 共享脚本与配置
│   └── ...                          # 公共工具函数、数据库连接等
├── my_holdings/                     # 持仓数据
│   ├── holdings.json                # 当前持仓
│   ├── cash_balance.json            # 现金余额
│   └── backup/                      # 历史备份
├── my_stock_pool/                   # 股票池数据
│   └── ...                          # 各策略股票池
└── recommendations/                 # 交易推荐记录
    └── YYYYMMDD_session_buy_recommendation.json
```

## 数据文件说明

### my_holdings/
- **holdings.json**: 当前所有持仓记录
- **cash_balance.json**: 当前现金余额
- **backup/**: 每日收盘后的持仓备份

### my_stock_pool/
- 核心仓初筛池（50-60只）
- 核心仓候选池（5-8只）
- 热点仓候选池（≤3只）
- 波段仓候选池（5-10只）

### recommendations/
- 早盘推荐（morning_buy_recommendation）
- 尾盘推荐（evening_buy_recommendation）
- 格式：`YYYYMMDD_session_buy_recommendation.json`

## 使用规范

1. **所有策略读写共享数据必须通过统一接口**
2. **持仓修改必须通过 trade_executor**
3. **每日收盘自动备份持仓数据**
4. **推荐记录保留至少90天**

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。
