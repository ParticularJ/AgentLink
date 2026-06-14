# 核心仓交易策略 Skill

基于赛道生命周期与基本面六维评分的核心仓位管理系统，包含宏观过滤、赛道筛选、个股初筛、财报验证、买点判断、持仓监控完整流程。

## 功能特性

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

## 策略流程

### Phase 1: 选股（季度）
1. **宏观流动性评估** → 判断是否可建仓
2. **赛道筛选** → 五维评估，仅保留爆发期赛道
3. **个股初筛** → 六维评分 + 一票否决，产出50-60只

### Phase 2: 二次筛选（财报季）
1. **财报打分** → 营收/利润/现金流/毛利率/前瞻指标
2. **风险排查** → 现金流/应收/存货/减持量化红线
3. **超预期验证** → 4项验证决定胜率
4. **综合评分** → 初筛35% + 业绩40% + 预期差25%

### Phase 3: 每日买入时机判断
1. **大盘环境过滤** → 强势/震荡/弱势三档
2. **买点识别** → 上升趋势回踩20日线（首选）
3. **买点质量评分** → 理想/一般/勉强三档
4. **仓位计算** → 多系数乘积
5. **六项确认清单** → 全通过才执行

### Phase 4: 持仓监控
1. **止损**：ATR自适应/固定-10%/移动-6%/均线/时间
2. **止盈**：四档分层，市场环境自适应调整
3. **加仓**：两档门槛，板块强度必要条件
4. **日常监控**：每日技术+每周基本面+组合风控

## 安装依赖

```bash
pip install pandas numpy
```

## 使用方法

### Python API

```python
from core_position_pipeline import CorePositionPipeline

# 创建管道
pipeline = CorePositionPipeline(total_capital=1000000.0, core_ratio=0.50)

# 执行完整选股流程
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

# 每日监控
monitor_result = pipeline.run_daily_monitor(
    daily_tech_data={...},
    weekly_fundamental_data={...},
    market_data={...}
)
```

### OpenClaw Agent

```
@core-position-agent 评估宏观环境
@core-position-agent 筛选赛道和个股
@core-position-agent 财报验证
@core-position-agent 检查买点信号
@core-position-agent 监控持仓
```

## 目录结构

```
core-position-strategy/
├── SKILL.md                           # 本文件
├── skills/scripts/
│   ├── models.py                      # 数据模型
│   ├── macro_filter.py                # 宏观流动性过滤器
│   ├── sector_scorer.py               # 赛道评分器
│   ├── initial_scorer.py              # 个股初筛评分器
│   ├── secondary_scorer.py            # 二次筛选评分器（财报验证）
│   ├── buy_signal.py                  # 每日买点判断
│   ├── position_monitor.py            # 持仓监控（止损/止盈/加仓）
│   ├── portfolio_manager.py           # 组合管理器
│   ├── core_position_pipeline.py      # 主流程管道
│   └── test_core_position.py          # 单元测试
└── config/                            # 配置文件（可选）
```

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。

## 更新日志

### v3.0.0
- ✅ 初始版本发布
- ✅ 实现宏观流动性三档环境判断
- ✅ 实现赛道五维评估与生命周期筛选
- ✅ 实现个股六维初筛+8项一票否决
- ✅ 实现财报五维评分+风险排查
- ✅ 实现超预期四维验证
- ✅ 实现每日买点识别与质量评分
- ✅ 实现多系数仓位计算
- ✅ 实现ATR自适应止损
- ✅ 实现四档分层止盈
- ✅ 实现两档加仓策略
- ✅ 实现三道防线组合风控
