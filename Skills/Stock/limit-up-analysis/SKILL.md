# 涨停板连板分析 Skill

基于多维度量化分析的涨停板连板可能性评估系统。

## 功能特性

- 📊 **实时涨停数据抓取**：自动获取当日涨停股票数据
- 🎯 **五维度量化分析**：封板强度、板块效应、资金流向、技术形态、市场情绪
- 📈 **智能评分系统**：0-100分量化评分，直观判断连板概率
- 📡 **多数据源支持**：支持 akshare、tushare、baostock、yfinance（自动优先级选择）
- 🤖 **AI分析助手**：基于大模型的智能分析解读
- ⏰ **定时任务**：交易日自动抓取和分析
- 💾 **历史数据**：保存分析历史，支持回溯查看

## 数据源配置

系统支持多数据源，会自动按优先级选择最佳可用数据源：

| 优先级 | 数据源 | 质量评分 | 说明 |
|--------|--------|---------|------|
| 1 | **tushare** | 5/5 | 数据最全面稳定，需要token |
| 2 | **akshare** | 4/5 | 免费，数据丰富，推荐 |
| 3 | **baostock** | 3/5 | 免费，数据稳定 |
| 4 | **yfinance** | 2/5 | 有限支持A股 |

### 安装数据源
```bash
pip install tushare      # 质量最高(5/5)，需要token
pip install akshare      # 质量高(4/5)，推荐，免费
pip install baostock     # 质量中(3/5)，免费，稳定
pip install yfinance     # 质量低(2/5)，有限支持A股
```

## 使用方法

### 命令行

```bash
# 分析当日所有涨停股（自动选择数据源）
python skills/limit_up/scripts/analyzer.py --all

# 指定数据源分析
python skills/limit_up/scripts/analyzer.py --source akshare --all

# 分析单只股票
python skills/limit_up/scripts/analyzer.py --code 000001

# 保存结果
python skills/limit_up/scripts/analyzer.py --all --save

# 显示前20名
python skills/limit_up/scripts/analyzer.py --all --top 20

# 查看历史
python skills/limit_up/scripts/analyzer.py --history 2024-01-15
```

### Python API

```python
from skills.limit_up.scripts.analyzer import LimitUpAnalyzer

# 创建分析器（自动选择最佳数据源）
analyzer = LimitUpAnalyzer()

# 或指定数据源
analyzer = LimitUpAnalyzer(data_source='akshare')

# 分析当日所有涨停股
results = analyzer.analyze_all_limit_up()

# 分析单只股票
result = analyzer.analyze_stock("000001")
```

### OpenClaw Agent

```
@limit-up-agent 分析 000001 的连板可能性
@limit-up-agent 查看今日涨停分析
@limit-up-agent 使用akshare分析今日涨停
```

## 评分标准

| 分数 | 等级 | 建议 |
|------|------|------|
| ≥85 | 极高 | 重点关注 |
| 75-84 | 高 | 可考虑打板 |
| 65-74 | 中等 | 需观察 |
| 55-64 | 低 | 谨慎参与 |
| <55 | 极低 | 建议观望 |

## 分析维度权重

| 维度 | 权重 | 关键指标 |
|------|------|---------|
| 封板强度分析 | 30% | 封单比、封板时间、炸板次数 |
| 板块效应分析 | 25% | 同板块涨停数、龙头地位、板块热度 |
| 资金流向分析 | 20% | 主力净流入、换手率 |
| 技术形态分析 | 15% | 突破形态、量价配合 |
| 市场情绪分析 | 10% | 连板高度、涨停数量 |

## 依赖

- akshare / tushare / baostock / yfinance: A股数据获取
- pandas: 数据处理
- numpy: 数值计算
- pyyaml: 配置管理
- colorama: 终端颜色输出

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。

## 更新日志

### v1.1.0
- ✅ 新增多数据源支持（akshare、tushare、baostock、yfinance）
- ✅ 新增数据源优先级自动选择机制
- ✅ 新增自动降级机制

### v1.0.0
- ✅ 初始版本发布
- ✅ 实现五维度量化分析模型
- ✅ 支持命令行和API调用
- ✅ 添加定时任务支持
