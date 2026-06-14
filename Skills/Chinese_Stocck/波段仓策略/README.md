# 波段仓策略

基于技术形态和事件驱动的中短线波段交易策略体系，持仓周期2-8周，资金占比20-30%。

## 包含策略

| 策略 | 说明 | 核心逻辑 |
|:---|:---|:---|
| **breakout-high-strategy** | 突破新高策略 | 股价突破历史高点后的趋势跟随 |
| **earnings-surprise-strategy** | 业绩超预期策略 | 财报超预期后的净利润断层交易 |
| **gap-fill-strategy** | 缺口回补策略 | 跳空缺口后的回补与反向交易 |
| **ma-bullish-strategy** | 均线多头策略 | 均线多头排列后的趋势跟踪 |
| **macd-divergence-strategy** | MACD背离策略 | MACD顶底背离的反转交易 |
| **morning-star-strategy** | 晨星形态策略 | K线晨星/黄昏星形态交易 |
| **rsi-oversold-strategy** | RSI超卖策略 | RSI超卖/超买的均值回归 |
| **volume-extreme-strategy** | 量能极端策略 | 成交量异常放大/萎缩的信号 |
| **volume-retrace-ma-strategy** | 量能回踩均线策略 | 放量上涨后缩量回踩均线 |

## 策略特点

- 📈 **技术驱动**：基于价格、成交量、技术指标的多维度分析
- 🎯 **形态识别**：自动识别经典技术形态和K线组合
- ⚡ **事件敏感**：对业绩、政策、市场事件快速反应
- 🛡️ **严格止损**：技术位止损，控制单笔风险
- 💰 **灵活仓位**：根据信号强度动态调整仓位
- 📊 **多周期验证**：日线+周线多周期确认

## 目录结构

```
波段仓策略/
├── breakout-high-strategy/          # 突破新高策略
│   ├── SKILL.md
│   ├── config/
│   └── skills/scripts/
├── earnings-surprise-strategy/      # 业绩超预期策略
│   ├── SKILL.md
│   ├── config/
│   └── skills/scripts/
├── gap-fill-strategy/               # 缺口回补策略
│   ├── SKILL.md
│   ├── config/
│   └── skills/scripts/
├── ma-bullish-strategy/             # 均线多头策略
│   ├── SKILL.md
│   ├── config/
│   └── skills/scripts/
├── macd-divergence-strategy/        # MACD背离策略
│   ├── SKILL.md
│   ├── config/
│   └── skills/scripts/
├── morning-star-strategy/           # 晨星形态策略
│   ├── SKILL.md
│   ├── config/
│   └── skills/scripts/
├── rsi-oversold-strategy/           # RSI超卖策略
│   ├── SKILL.md
│   ├── config/
│   └── skills/scripts/
├── volume-extreme-strategy/         # 量能极端策略
│   ├── SKILL.md
│   ├── config/
│   └── skills/scripts/
└── volume-retrace-ma-strategy/      # 量能回踩均线策略
    ├── SKILL.md
    ├── config/
    └── skills/scripts/
```

## 策略分类

### 趋势跟踪型
- **突破新高策略**：股价创历史新高，趋势确认后跟进
- **均线多头策略**：短期均线上穿长期均线，多头排列形成
- **量能回踩均线策略**：放量上涨后缩量回踩均线企稳

### 反转交易型
- **MACD背离策略**：价格与MACD指标背离，预示趋势反转
- **RSI超卖策略**：RSI进入超卖/超买区域，均值回归
- **晨星形态策略**：K线出现晨星/黄昏星反转形态

### 事件驱动型
- **业绩超预期策略**：财报超预期后的净利润断层交易
- **缺口回补策略**：跳空缺口形成后的回补交易
- **量能极端策略**：成交量异常变化预示价格变动

## 通用交易规则

### 买入条件
1. 技术信号触发（形态/指标/量能）
2. 大盘环境不处于弱势
3. 板块强度排名前50%
4. 个股流动性充足（日均成交额>1亿）

### 卖出规则
- **止损**：跌破买入技术位-5%至-8%
- **止盈**：达到目标价位或技术位阻力
- **移动止盈**：浮盈10%后，回撤5%止盈
- **时间止损**：买入后2周无表现则离场

### 仓位管理
- 单只标的仓位：5%-15%
- 同时持仓数量：5-10只
- 总仓位上限：80%

## 快速开始

各策略独立运行，详见各策略目录下的 SKILL.md 文件。

通用调用方式：
```python
# 以突破新高策略为例
from breakout-high-strategy.skills.scripts.scanner import BreakoutScanner

scanner = BreakoutScanner()
results = scanner.scan_market()
for stock in results:
    print(f"{stock.code}: 突破价格 {stock.breakout_price}")
```

## 资金配置

| 规则 | 数值 |
|:---|:---|
| 波段仓占总资金 | 20%-30% |
| 单只标的仓位 | 5%-15% |
| 同时持仓数量 | 5-10只 |
| 总仓位上限 | 80% |

## 风险控制

- 严格技术位止损，单笔亏损不超过总资金2%
- 大盘弱势时（<250日线）降低仓位至30%
- 连续3笔亏损后暂停交易，复盘策略
- 每月回顾策略表现，淘汰胜率<55%的策略

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。
