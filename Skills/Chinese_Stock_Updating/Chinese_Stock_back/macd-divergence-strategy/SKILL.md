# MACD底背离策略 Skill

基于MACD底背离信号的技术分析策略，捕捉股价下跌后的反转机会。

## 功能特性

- 📉 **底背离识别**：自动识别MACD底背离信号
- 📊 **五维度评分**：背离强度、MACD金叉、量能确认、K线形态、支撑位置
- 📈 **多数据源**：支持 akshare、tushare、baostock、yfinance
- 🎯 **精准抄底**：识别下跌末期的反转机会
- 🛡️ **风险控制**：动态止损、移动止盈、仓位管理
- 📋 **报告生成**：详细分析报告、每日扫描结果

## 策略原理

### 买入条件

1. **价格新低**：股价创20日新低
2. **MACD背离**：MACD柱状线或DIF线不创新低
3. **MACD金叉**：DIF线上穿DEA线确认
4. **量能配合**：成交量温和放大
5. **K线形态**：出现锤子线/启明星等止跌形态

### 卖出规则

- **止损**：跌破背离低点-3% 或 固定-8%
- **止盈**：前期高点附近 或 涨幅15-25%
- **时间止损**：买入后7日无表现则离场

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
python3 skills/scripts/macd_divergence_scanner.py --scan --top 20

# 分析指定板块
python3 skills/scripts/macd_divergence_scanner.py --sector 科技
python3 skills/scripts/macd_divergence_scanner.py --sector 医药

# 分析单只股票
python3 skills/scripts/macd_divergence_scanner.py --stock 000001 --name 平安银行

# 指定数据源
python3 skills/scripts/macd_divergence_scanner.py --source baostock --scan
```

### Python API

```python
from skills.scripts.macd_divergence_analyzer import MACDDivergenceAnalyzer

# 创建分析器
analyzer = MACDDivergenceAnalyzer(data_source='baostock')

# 分析单只股票
result = analyzer.analyze_stock('000001', '平安银行')

# 输出结果
print(f"信号: {result['signal']}")
print(f"得分: {result['score']}")
print(f"背离类型: {result['divergence_type']}")
print(f"MACD金叉: {result['golden_cross']}")
```

### OpenClaw Agent

```
@macd-divergence-agent 分析 000001 的底背离机会
@macd-divergence-agent 扫描今日底背离股票
@macd-divergence-agent 分析科技板块
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
| 背离强度 | 25% | 背离幅度、持续时间 |
| MACD金叉 | 20% | DIF上穿DEA确认 |
| 量能确认 | 20% | 成交量放大比例 |
| K线形态 | 20% | 锤子线/启明星等 |
| 支撑位置 | 15% | 前期低点/整数关口 |

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
- ✅ 实现MACD底背离核心逻辑
- ✅ 支持多数据源
- ✅ 添加五维度评分系统
- ✅ 集成风险管理和报告生成
