# 缩量回踩重要均线策略 Skill

基于缩量回踩重要均线的技术分析策略，捕捉强势股回调后的二次启动机会。

## 功能特性

- 🔍 **智能识别**：自动识别缩量回踩MA20/MA30/MA60的股票
- 📊 **五维度评分**：趋势强度、回踩质量、缩量程度、止跌信号、支撑强度
- 📈 **多数据源**：支持 akshare、tushare、baostock、yfinance
- 🎯 **精准买点**：识别缩量止跌后的最佳买入时机
- 🛡️ **风险控制**：动态止损、移动止盈、仓位管理
- 📋 **报告生成**：详细分析报告、每日扫描结果

## 策略原理

### 买入条件

1. **趋势判断**：股票处于上升趋势（MA20 > MA60）
2. **回踩均线**：股价回调至MA20/MA30/MA60附近（±3%）
3. **缩量确认**：成交量萎缩至前5日均量的60%以下
4. **止跌信号**：出现十字星/小阳线/锤子线等止跌形态
5. **支撑有效**：均线斜率向上，支撑力度强

### 卖出规则

- **止损**：跌破回踩均线-3% 或 固定-5%
- **止盈**：前高附近 或 涨幅15-25%
- **时间止损**：买入后5日无表现则离场

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
python3 skills/scripts/retrace_scanner.py --scan --top 20

# 指定数据源扫描
python3 skills/scripts/retrace_scanner.py --source baostock --scan

# 分析指定板块
python3 skills/scripts/retrace_scanner.py --sector 科技
python3 skills/scripts/retrace_scanner.py --sector 半导体

# 分析单只股票
python3 skills/scripts/retrace_scanner.py --stock 000001 --name 平安银行
```

### Python API

```python
from skills.scripts.retrace_analyzer import VolumeRetraceAnalyzer

# 创建分析器
analyzer = VolumeRetraceAnalyzer(data_source='baostock')

# 分析单只股票
result = analyzer.analyze_stock('000001', '平安银行')

# 输出结果
print(f"信号: {result['signal']}")
print(f"得分: {result['score']}")
print(f"回踩均线: {result['retrace_ma']}")
print(f"缩量程度: {result['volume_shrink']}%")
```

### OpenClaw Agent

```
@volume-retrace-agent 分析 000001 的回踩机会
@volume-retrace-agent 扫描今日回踩股票
@volume-retrace-agent 分析科技板块
```

## 评分标准

| 分数 | 等级 | 操作建议 |
|------|------|---------|
| ≥80 | 强烈买入 | 积极配置，建议仓位20% |
| 70-79 | 买入 | 适度参与，建议仓位15% |
| 60-69 | 观望 | 等待确认信号 |
| <60 | 放弃 | 不符合买入条件 |

## 评分维度权重

| 维度 | 权重 | 关键指标 |
|------|------|---------|
| 趋势强度 | 25% | MA20斜率、均线多头排列 |
| 回踩质量 | 20% | 回踩精度、回调幅度 |
| 缩量程度 | 20% | 成交量萎缩比例 |
| 止跌信号 | 20% | K线形态（锤子线/十字星） |
| 支撑强度 | 15% | 均线斜率、测试次数 |

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
- ✅ 实现缩量回踩核心逻辑
- ✅ 支持多数据源
- ✅ 添加五维度评分系统
- ✅ 集成风险管理和报告生成
