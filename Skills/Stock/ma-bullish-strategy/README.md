# 均线多头排列策略 (MA Bullish Strategy)

基于均线多头排列的技术分析策略，识别上升趋势中的买入机会。

## 功能特性

- 🔍 **扫描全市场** - 自动寻找均线多头排列的股票
- 📅 **指定日期分析** - 支持历史回测和指定日期分析
- 🏭 **板块分析** - 支持按板块（科技、医药、金融等）分析
- 📊 **五维度评分** - 均线排列、价格位置、成交量趋势、趋势强度、市场环境
- 🎯 **自动计算** - 入场价、止损位、目标价、风险收益比
- 📈 **多数据源** - 支持 akshare、baostock、tushare、yfinance
- 🛡️ **风险管理** - 动态仓位计算、止损止盈、移动止损
- 📋 **报告生成** - 详细分析报告、告警消息、每日总结

## 安装依赖

```bash
# 安装核心依赖
pip install pandas numpy

# 安装数据源（至少安装一个）
pip install akshare      # 推荐，免费，数据丰富
pip install baostock     # 免费，数据稳定
pip install tushare      # 需要token（pro版付费）
pip install yfinance     # 有限支持A股

# 可选依赖
pip install matplotlib   # 用于回测图表
```

## 使用方法

### 命令行

```bash
# 扫描全市场（自动选择数据源）
python skills/ma_bullish/scripts/ma_analyzer.py --scan --top 20

# 指定数据源扫描
python skills/ma_bullish/scripts/ma_analyzer.py --source baostock --scan --top 10

# 分析单只股票
python skills/ma_bullish/scripts/ma_analyzer.py --stock 000001 --name 平安银行

# 指定数据源分析
python skills/ma_bullish/scripts/ma_analyzer.py --source baostock --stock 000001

# 分析指定日期
python skills/ma_bullish/scripts/ma_analyzer.py --stock 000001 --date 2026-04-03

# 指定数据源和日期
python skills/ma_bullish/scripts/ma_analyzer.py --source baostock --stock 000001 --date 2026-04-03

# 分析指定板块
python skills/ma_bullish/scripts/ma_analyzer.py --sector 科技 --date 2026-04-03
python skills/ma_bullish/scripts/ma_analyzer.py --sector 医药 --date 2026-04-03

# 分析所有板块
python skills/ma_bullish/scripts/ma_analyzer.py --all-sectors --date 2026-04-03
```

### Python API

```python
from skills.ma_bullish.scripts.ma_analyzer import MABullishAnalyzer
from skills.ma_bullish.scripts.sector_analyzer import SectorAnalyzer

# 创建分析器（自动选择数据源）
analyzer = MABullishAnalyzer()

# 或指定数据源
analyzer = MABullishAnalyzer(data_source='baostock')

# 扫描全市场
results = analyzer.scan_all_stocks(top_n=20)

# 分析单只股票（最新数据）
result = analyzer.analyze_stock('000001', '平安银行')

# 分析指定日期
result = analyzer.analyze_stock('000001', '平安银行', analysis_date='2026-04-03')

# 板块分析
sector_analyzer = SectorAnalyzer(analyzer)
result = sector_analyzer.analyze_sector('科技', analysis_date='2026-04-03')
print(sector_analyzer.generate_sector_report(result))

# 分析所有板块
results = sector_analyzer.analyze_all_sectors(analysis_date='2026-04-03')
```

### OpenClaw Agent

```
@ma-bullish-agent 扫描均线多头排列股票
@ma-bullish-agent 分析 000001
@ma-bullish-agent 分析 000001 在 2026-04-03
@ma-bullish-agent 分析科技板块
@ma-bullish-agent 分析医药板块在 2026-04-03
```

## 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| 均线排列 | 35% | MA5 > MA10 > MA20，发散程度 |
| 价格位置 | 20% | 相对于均线的位置 |
| 成交量趋势 | 20% | 成交量是否放大 |
| 趋势强度 | 15% | 价格斜率 |
| 市场环境 | 10% | 大盘指数表现 |

## 评分标准

- **≥85分** - 🔴 强烈推荐，均线多头排列良好，成交量配合
- **75-84分** - 🟡 推荐，符合买入条件，可分批建仓
- **70-74分** - 🟢 关注，基本符合条件，等待更好买点
- **<70分** - ⚪ 暂缓，条件不充分，继续观察

## 支持板块

- **科技** - 计算机、电子、通信等
- **医药** - 医药生物、医疗器械等
- **金融** - 银行、证券、保险等
- **消费** - 食品饮料、家电、商贸等
- **新能源** - 光伏、风电、电动车等
- **军工** - 航空航天、船舶、军工电子等

## 数据源对比与优先级

系统会**自动按优先级选择最佳可用数据源**，也可手动指定。

| 优先级 | 数据源 | 费用 | 稳定性 | 数据质量 | 质量评分 |
|--------|--------|------|--------|---------|---------|
| 1 | **tushare** | 免费/付费 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 5/5 |
| 2 | **akshare** | 免费 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 4/5 |
| 3 | **baostock** | 免费 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 3/5 |
| 4 | **yfinance** | 免费 | ⭐⭐⭐ | ⭐⭐ | 2/5 |

### 自动降级机制
- 当主数据源获取失败时，自动尝试下一个优先级的数据源
- 支持重试机制，提高数据获取成功率
- 可手动指定数据源：`--source akshare`

## 风险管理

### 止损设置
- **技术止损** - MA20下方2%
- **ATR止损** - 2倍ATR
- **百分比止损** - 固定8%

### 止盈设置
- **目标1** - 10-15%
- **目标2** - 15-20%
- **目标3** - 20-25%

### 移动止损
- 盈利10%后激活
- 最高点回撤8%止盈

### 仓位管理
- 单只股票最大仓位30%
- 每笔交易风险2%
- 根据波动率动态调整

## 项目结构

```
ma-bullish-strategy/
├── README.md
├── SKILL.md
├── requirements.txt
├── setup.sh
├── config/
│   ├── strategy_config.yaml    # 策略配置
│   ├── scoring_weights.yaml    # 评分权重
│   └── risk_rules.yaml         # 风险规则
├── agents/
│   └── ma-bullish-agent.yaml   # Agent配置
├── crons/
│   └── ma-bullish-crons.yaml   # 定时任务
└── skills/ma_bullish/scripts/
    ├── ma_analyzer.py          # 主分析器
    ├── data_source_adapter.py  # 多数据源适配器
    ├── sector_analyzer.py      # 板块分析器
    ├── signal_generator.py     # 信号生成器
    ├── risk_manager.py         # 风险管理器
    ├── report_generator.py     # 报告生成器
    └── backtest.py             # 回测引擎
```

## 免责声明

⚠️ **本策略仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。**

## 更新日志

### v1.2.0
- ✅ 新增板块分析功能
- ✅ 支持科技、医药、金融、消费、新能源、军工等板块

### v1.1.0
- ✅ 新增指定日期分析功能
- ✅ 新增多数据源支持（akshare、baostock、tushare、yfinance）
- ✅ 优化数据获取稳定性

### v1.0.0
- ✅ 基础均线多头排列策略
- ✅ 五维度评分系统
- ✅ 风险管理模块
- ✅ 报告生成模块
- ✅ 回测引擎
