# 股票交易策略系统

基于三大仓位策略的完整A股交易系统，涵盖核心仓、热点仓、波段仓的全流程管理。

## 系统架构

```
Chinese_Stocck/
├── 核心仓策略/          # 中长线持仓（季度级）
│   ├── core-position-strategy/     # 核心仓V3.0（赛道生命周期+基本面）
│   └── Medium-termHoldingStrategy/ # 中期持仓监控与交易执行
├── 热点仓策略/          # 短线交易（日/周级）
│   ├── hot-spot-strategy/          # 热点仓四大策略体系
│   ├── limit-up-retrace-strategy/  # 涨停回调策略
│   └── limit-up-analysis/          # 涨停分析工具
├── 波段仓策略/          # 中短线波段（周/月级）
│   ├── breakout-high-strategy/     # 突破新高策略
│   ├── earnings-surprise-strategy/ # 业绩超预期策略
│   ├── gap-fill-strategy/          # 缺口回补策略
│   ├── ma-bullish-strategy/        # 均线多头策略
│   ├── macd-divergence-strategy/   # MACD背离策略
│   ├── morning-star-strategy/      # 晨星形态策略
│   ├── rsi-oversold-strategy/      # RSI超卖策略
│   ├── volume-extreme-strategy/    # 量能极端策略
│   └── volume-retrace-ma-strategy/ # 量能回踩均线策略
├── 策略工具/            # 跨策略通用工具
│   ├── strategy-fusion-advisor/    # 策略融合顾问
│   ├── strategy-optimizer/         # 策略优化器
│   ├── stock_earnings_analysis/    # 财报分析工具
│   └── stock_event/                # 股票事件监控
└── 共享组件/            # 公共数据与配置
    ├── _shared/                      # 共享脚本与配置
    ├── my_holdings/                  # 持仓数据
    ├── my_stock_pool/                # 股票池数据
    └── recommendations/              # 交易推荐记录
```

## 三大策略对比

| 维度 | 核心仓策略 | 热点仓策略 | 波段仓策略 |
|:---|:---|:---|:---|
| **投资周期** | 季度级（3-6月） | 日/周级（3-8天） | 周/月级（2-8周） |
| **选股逻辑** | 赛道生命周期+基本面 | 涨停板+情绪+资金 | 技术形态+事件驱动 |
| **持仓数量** | 5-8只 | ≤3只 | 5-10只 |
| **资金占比** | 50% | 20-30% | 20-30% |
| **止损策略** | ATR自适应/固定-10% | 固定-7%/移动-5% | 技术位止损-5~-8% |
| **止盈策略** | 四档分层（15/25/40/60%） | 三档分批（5/10/20%） | 目标位/移动止盈 |
| **核心能力** | 赛道判断+财报验证 | 情绪感知+资金追踪 | 技术识别+事件捕捉 |

## 快速开始

### 核心仓策略
```python
from 核心仓策略.core-position-strategy.skills.scripts.core_position_pipeline import CorePositionPipeline

pipeline = CorePositionPipeline(total_capital=1000000.0, core_ratio=0.50)
result = pipeline.run_full_pipeline(...)
```

### 热点仓策略
```python
from 热点仓策略.hot-spot-strategy.skills.scripts.hot_spot_pipeline import HotSpotPipeline

pipeline = HotSpotPipeline(total_capital=1000000.0)
recommendations = pipeline.generate_recommendations(stocks_data)
```

### 波段仓策略
各波段策略独立运行，详见各策略目录下的 SKILL.md

## 数据流

```
市场数据 → 共享组件/_shared/ → 各策略模块
                                    ↓
                           交易信号 → 共享组件/my_holdings/
                                    ↓
                           推荐记录 → 共享组件/recommendations/
```

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。

## 更新日志

### v2.0.0 (2025-06-14)
- ✅ 重构目录结构，按三大策略分类组织
- ✅ 新增核心仓策略 V3.0 完整实现
- ✅ 统一共享组件管理
- ✅ 更新所有策略文档

### v1.0.0
- ✅ 热点仓策略四大体系
- ✅ 波段仓多策略实现
- ✅ 基础持仓与推荐系统
