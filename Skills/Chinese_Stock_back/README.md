# Stock - 股票交易策略 Skills

本目录包含11个股票交易策略的 OpenClaw Skills，涵盖趋势跟踪、反转、突破、基本面等多种策略类型。

---

## 📊 策略列表

### 1. 均线多头排列策略 (ma-bullish-strategy) ⭐
**版本：** v1.2.0 | **胜率：** 65% | **持仓周期：** 5-15天

基于均线多头排列的技术分析策略，识别上升趋势中的买入机会。

**核心逻辑：**
- 5日 > 10日 > 20日均线多头排列
- 价格位于5日均线上方
- 成交量温和放大

**使用方法：**
```bash
cd ma-bullish-strategy
python3 skills/scripts/ma_bullish_scanner.py --scan --top 20
python3 skills/scripts/ma_bullish_scanner.py --sector 科技
```

---

### 2. 涨停板连板分析 (limit-up-analysis)
**版本：** v1.1.0 | **胜率：** 65% | **持仓周期：** 1-3天

基于多维度量化分析的涨停板连板可能性评估系统。

**核心逻辑：**
- 封板强度分析（封单比、封板时间）
- 板块效应分析
- 资金流向分析
- 技术形态分析

**使用方法：**
```bash
cd limit-up-analysis
python3 skills/scripts/limit_up_scanner.py --scan
```

---

### 3. 财报超预期策略 (earnings-surprise-strategy) 📈
**版本：** v1.0.0 | **胜率：** 70% | **持仓周期：** 2-4周

基于财报超预期的基本面量化交易策略，捕捉业绩超预期带来的股价上涨机会。

**核心逻辑：**
- 净利润同比增长 > 30%
- 营收同比增长 > 20%
- 实际EPS > 预期EPS × 1.1
- 毛利率环比提升

**使用方法：**
```bash
cd earnings-surprise-strategy
python3 skills/scripts/earnings_scanner.py --scan
```

---

### 4. 缩量回踩重要均线策略 (volume-retrace-ma-strategy)
**版本：** v1.0.0 | **胜率：** 62% | **持仓周期：** 3-7天

识别强势股缩量回踩重要均线（20日/60日）后的反弹机会。

**核心逻辑：**
- 股价回踩20日或60日均线
- 成交量萎缩至20日均量的60%以下
- 均线仍保持多头排列
- 出现止跌K线形态

**使用方法：**
```bash
cd volume-retrace-ma-strategy
python3 skills/scripts/volume_retrace_scanner.py --scan
```

---

### 5. 涨停板首次回调策略 (limit-up-retrace-strategy)
**版本：** v1.0.0 | **胜率：** 60% | **持仓周期：** 2-5天

捕捉涨停板后首次回调的买入机会，属于强势股回调策略。

**核心逻辑：**
- 近期出现过涨停板
- 回调幅度在5%-15%之间
- 成交量萎缩
- 重要均线支撑有效

**使用方法：**
```bash
cd limit-up-retrace-strategy
python3 skills/scripts/limit_up_retrace_scanner.py --scan
```

---

### 6. MACD底背离策略 (macd-divergence-strategy)
**版本：** v1.0.0 | **胜率：** 58% | **持仓周期：** 5-10天

基于MACD指标底背离形态的反转交易策略。

**核心逻辑：**
- 股价创新低但MACD未创新低（底背离）
- MACD在零轴下方金叉
- 成交量温和放大
- 出现止跌K线形态

**使用方法：**
```bash
cd macd-divergence-strategy
python3 skills/scripts/macd_divergence_scanner.py --scan
```

---

### 7. 早晨之星形态策略 (morning-star-strategy) 🌅
**版本：** v1.0.0 | **胜率：** 58% | **持仓周期：** 3-7天

基于K线早晨之星（Morning Star）形态的反转交易策略。

**核心逻辑：**
- 下跌趋势中出现早晨之星形态
- 第三根阳线实体吞没第一根阴线实体
- 伴随成交量放大
- 位于重要支撑位

**使用方法：**
```bash
cd morning-star-strategy
python3 skills/scripts/morning_star_scanner.py --scan
```

---

### 8. 突破前期高点策略 (breakout-high-strategy)
**版本：** v1.0.0 | **胜率：** 60% | **持仓周期：** 5-15天

识别股价突破前期高点的趋势延续交易机会。

**核心逻辑：**
- 股价突破60日或120日高点
- 突破时成交量放大（≥1.5倍均量）
- 均线多头排列
- 突破幅度适中（3%-10%）

**使用方法：**
```bash
cd breakout-high-strategy
python3 skills/scripts/breakout_scanner.py --scan
```

---

### 9. RSI超卖反弹策略 (rsi-oversold-strategy)
**版本：** v1.0.0 | **胜率：** 58% | **持仓周期：** 3-7天

基于RSI指标超卖后的技术性反弹交易策略。

**核心逻辑：**
- RSI值 ≤ 30（超卖）
- 价格偏离20日均线 ≥ 8%
- 成交量明显萎缩
- 出现止跌信号

**使用方法：**
```bash
cd rsi-oversold-strategy
python3 skills/scripts/rsi_oversold_scanner.py --scan
```

---

### 10. 成交量地量见底策略 (volume-extreme-strategy)
**版本：** v1.0.0 | **胜率：** 62% | **持仓周期：** 5-10天

识别成交量极度萎缩后的底部反弹机会。

**核心逻辑：**
- 成交量 ≤ 20日均量的40%（极度地量）
- 价格低于20日均线 ≥ 5%
- 出现企稳信号
- 有反弹迹象

**使用方法：**
```bash
cd volume-extreme-strategy
python3 skills/scripts/volume_extreme_scanner.py --scan
```

---

### 11. 缺口回补策略 (gap-fill-strategy)
**版本：** v1.0.0 | **胜率：** 62% | **持仓周期：** 3-7天

识别突破性缺口后的回踩买入机会。

**核心逻辑：**
- 出现向上跳空缺口（≥3%）
- 缺口伴随放量（≥1.5倍均量）
- 价格回踩到缺口区域
- 趋势向好

**使用方法：**
```bash
cd gap-fill-strategy
python3 skills/scripts/gap_fill_scanner.py --scan
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 安装所有策略的依赖
pip install pandas numpy pyyaml
pip install akshare baostock yfinance
```

### 2. 运行策略

```bash
# 进入策略目录
cd ma-bullish-strategy

# 扫描全市场
python3 skills/scripts/ma_bullish_scanner.py --scan --top 20

# 分析指定板块
python3 skills/scripts/ma_bullish_scanner.py --sector 科技

# 分析单只股票
python3 skills/scripts/ma_bullish_scanner.py --stock 000001 --name 平安银行
```

### 3. 数据源选择

所有策略支持多数据源自动切换：
- **akshare** (推荐) - 数据质量4/5
- **baostock** - 数据质量3/5
- **tushare** - 数据质量5/5（需API Key）
- **yfinance** - 数据质量2/5

```bash
# 指定数据源
python3 skills/scripts/ma_bullish_scanner.py --source baostock --scan
```

---

## 📁 目录结构

```
Stock/
├── README.md                           # 本文件
├── check_all_consistency.py            # 一致性检查脚本
├── ma-bullish-strategy/               # 均线多头排列策略
│   ├── README.md
│   ├── SKILL.md
│   ├── requirements.txt
│   ├── config/
│   │   ├── scoring_weights.yaml       # 评分权重配置
│   │   ├── strategy_config.yaml       # 策略参数配置
│   │   └── risk_rules.yaml            # 风险规则配置
│   ├── agents/
│   │   └── ma-bullish-agent.yaml      # Agent配置
│   ├── crons/
│   │   └── ma-bullish-crons.yaml      # 定时任务配置
│   └── skills/scripts/
│       ├── ma_bullish_analyzer.py     # 核心分析器
│       └── ma_bullish_scanner.py      # 扫描程序
├── limit-up-analysis/                 # 涨停板连板分析
├── earnings-surprise-strategy/        # 财报超预期策略
├── volume-retrace-ma-strategy/        # 缩量回踩均线策略
├── limit-up-retrace-strategy/         # 涨停首次回调策略
├── macd-divergence-strategy/          # MACD底背离策略
├── morning-star-strategy/             # 早晨之星形态策略
├── breakout-high-strategy/            # 突破前期高点策略
├── rsi-oversold-strategy/             # RSI超卖反弹策略
├── volume-extreme-strategy/           # 成交量地量见底策略
└── gap-fill-strategy/                 # 缺口回补策略
```

---

## 📊 策略对比

| 策略 | 类型 | 胜率 | 持仓周期 | 适用市场 |
|------|------|------|----------|----------|
| 均线多头排列 | 趋势跟踪 | 65% | 5-15天 | 牛市/震荡 |
| 涨停板连板 | 动量 | 65% | 1-3天 | 强势市场 |
| 财报超预期 | 基本面 | 70% | 2-4周 | 财报季 |
| 缩量回踩均线 | 趋势回调 | 62% | 3-7天 | 牛市 |
| 涨停首次回调 | 动量回调 | 60% | 2-5天 | 强势市场 |
| MACD底背离 | 反转 | 58% | 5-10天 | 熊市/底部 |
| 早晨之星 | 反转 | 58% | 3-7天 | 熊市/底部 |
| 突破前期高点 | 趋势突破 | 60% | 5-15天 | 牛市 |
| RSI超卖反弹 | 反转 | 58% | 3-7天 | 超卖市场 |
| 成交量地量见底 | 反转 | 62% | 5-10天 | 底部区域 |
| 缺口回补 | 趋势延续 | 62% | 3-7天 | 强势市场 |

---

## 🔧 添加新策略

要添加新的交易策略 skill，请参考现有策略结构：

```
your-strategy/
├── README.md                    # 策略说明文档
├── SKILL.md                     # Skill定义文档
├── requirements.txt             # Python依赖
├── check_consistency.py         # 一致性检查脚本
├── demo.py                      # 演示脚本
├── config/
│   ├── scoring_weights.yaml     # 评分权重配置（权重和=100%）
│   ├── strategy_config.yaml     # 策略参数配置
│   └── risk_rules.yaml          # 风险规则配置
├── agents/
│   └── your-agent.yaml          # Agent配置
├── crons/
│   └── your-crons.yaml          # 定时任务配置
└── skills/scripts/
    ├── your_analyzer.py         # 核心分析器
    └── your_scanner.py          # 扫描程序
```

**核心分析器要求：**
1. 使用 `DataSourceAdapter` 支持多数据源
2. 实现 `analyze_stock(stock_code, stock_name)` 方法
3. 返回包含 `score`、`signal`、`current_price` 的字典
4. 评分范围 0-100，≥70分为有效信号

---

## ⚠️ 免责声明

所有策略仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。

**风险提示：**
- 历史表现不代表未来收益
- 策略存在失效风险
- 请根据自身风险承受能力谨慎投资
- 建议结合多种策略和风控措施使用

---

## 📞 支持与反馈

如有问题或建议，请通过以下方式联系：
- 提交 Issue
- 发送邮件
- 加入讨论群组

---

*最后更新：2026-04-06*
