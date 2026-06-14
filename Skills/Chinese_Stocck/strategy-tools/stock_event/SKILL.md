# 涨停板首次回调策略 Skill

基于涨停板后首次回调的技术分析策略，捕捉强势股涨停后回踩重要支撑位的二次启动机会。

## 功能特性

- 🔥 **涨停识别**：自动识别近期涨停股票（5个交易日内）
- 📊 **五维度评分**：涨停质量、回调质量、支撑强度、缩量程度、止跌信号
- 📈 **多数据源**：支持 akshare、tushare、baostock、yfinance
- 🎯 **精准买点**：识别涨停后首次回调的最佳买入时机
- 🛡️ **风险控制**：动态止损、移动止盈、仓位管理
- 📋 **报告生成**：详细分析报告、每日扫描结果

## 策略原理

### 买入条件

1. **涨停识别**：5个交易日内出现过涨停板
2. **回调幅度**：从涨停价回调<15%
3. **支撑位置**：回调至涨停价/5日线/前高附近
4. **缩量确认**：成交量萎缩至前3日均量的50%以下
5. **止跌信号**：出现十字星/小阳线/锤子线等止跌形态
6. **确认上涨**：随后出现放量上涨确认

### 卖出规则

- **止损**：跌破支撑位-3% 或 固定-7%
- **止盈**：前涨停价附近 或 涨幅10-20%
- **时间止损**：买入后3日无表现则离场

## 安装依赖

```bash
pip install pandas numpy pyyaml requests

# 安装数据源（至少一个）
pip install akshare      # 推荐
pip install baostock     # 备用
```

## 使用方法

### 命令行

```bash
# 扫描全市场
python3 skills/scripts/limit_up_retrace_scanner.py --scan --top 20

# 分析指定板块
python3 skills/scripts/limit_up_retrace_scanner.py --sector 科技
python3 skills/scripts/limit_up_retrace_scanner.py --sector 半导体

# 分析单只股票
python3 skills/scripts/limit_up_retrace_scanner.py --stock 000001 --name 平安银行

# 指定数据源
python3 skills/scripts/limit_up_retrace_scanner.py --source baostock --scan
```

### Python API

```python
from skills.scripts.limit_up_retrace_analyzer import LimitUpRetraceAnalyzer

# 创建分析器
analyzer = LimitUpRetraceAnalyzer(data_source='baostock')

# 分析单只股票
result = analyzer.analyze_stock('000001', '平安银行')

# 输出结果
print(f"信号: {result['signal']}")
print(f"得分: {result['score']}")
print(f"涨停日期: {result['limit_up_date']}")
print(f"回调幅度: {result['retrace_pct']}%")
```

### OpenClaw Agent

```
@limit-up-retrace-agent 分析 000001 的涨停回调机会
@limit-up-retrace-agent 扫描今日涨停回调股票
@limit-up-retrace-agent 分析科技板块
```

## 评分标准

| 分数 | 等级 | 操作建议 |
|------|------|---------|
| ≥85 | 强烈买入 | 积极配置，建议仓位15% |
| 75-84 | 买入 | 适度参与，建议仓位10% |
| 65-74 | 观望 | 等待确认信号 |
| <65 | 放弃 | 不符合条件 |

## 评分维度权重

| 维度 | 权重 | 关键指标 |
|------|------|---------|
| 涨停质量 | 25% | 封板强度、封单金额、炸板次数 |
| 回调质量 | 20% | 回调幅度、回调时间 |
| 支撑强度 | 20% | 支撑位类型、支撑力度 |
| 缩量程度 | 20% | 成交量萎缩比例 |
| 止跌信号 | 15% | K线形态（锤子线/十字星） |

## 依赖

- pandas: 数据处理
- numpy: 数值计算
- pyyaml: 配置管理
- akshare/baostock: A股数据获取

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。

## 更新日志

### v1.0.0
- ✅ 初始版本发布
- ✅ 实现涨停板首次回调核心逻辑
- ✅ 支持多数据源
- ✅ 添加五维度评分系统
- ✅ 集成风险管理和报告生成
