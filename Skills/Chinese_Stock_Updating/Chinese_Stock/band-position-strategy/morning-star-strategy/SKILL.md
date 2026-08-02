# 早晨之星形态策略 Skill

基于早晨之星K线组合的技术分析策略，捕捉下跌趋势末端的反转机会。

## 功能特性

- ⭐ **早晨之星识别**：自动识别标准的早晨之星K线组合
- 📊 **四维度评分**：形态完整性、位置确认、成交量确认、后续确认
- 📈 **多数据源**：支持 akshare、tushare、baostock、yfinance
- 🎯 **精准抄底**：识别下跌末端的反转信号
- 🛡️ **风险控制**：动态止损、移动止盈、仓位管理
- 📋 **报告生成**：详细分析报告、每日扫描结果

## 策略原理

### 早晨之星形态定义

早晨之星是由三根K线组成的底部反转形态：

1. **第一根：大阴线**
   - 实体较长，跌幅≥3%
   - 显示空方力量强劲

2. **第二根：十字星**
   - 实体很小，上下影线可长可短
   - 显示多空力量趋于平衡
   - 通常向下跳空低开

3. **第三根：大阳线**
   - 实体较长，涨幅≥3%
   - 收盘价深入第一根阴线实体内部
   - 显示多方力量开始占优

### 买入条件

- 形态出现在下跌趋势末端
- 第一根阴线跌幅≥3%
- 第二根十字星实体比例≤20%
- 第三根阳线涨幅≥3%
- 第三根收盘价深入第一根实体50%以上
- 成交量配合（下跌放量、十字星缩量、上涨放量）

### 卖出规则

- **止损**：跌破形态最低点-3% 或 固定-7%
- **止盈**：前期高点附近 或 涨幅15-25%
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
python3 skills/scripts/morning_star_scanner.py --scan --top 20

# 分析指定板块
python3 skills/scripts/morning_star_scanner.py --sector 科技
python3 skills/scripts/morning_star_scanner.py --sector 医药

# 分析单只股票
python3 skills/scripts/morning_star_scanner.py --stock 000001 --name 平安银行

# 指定数据源
python3 skills/scripts/morning_star_scanner.py --source baostock --scan
```

### Python API

```python
from skills.scripts.morning_star_analyzer import MorningStarAnalyzer

# 创建分析器
analyzer = MorningStarAnalyzer(data_source='baostock')

# 分析单只股票
result = analyzer.analyze_stock('000001', '平安银行')

# 输出结果
print(f"信号: {result['signal']}")
print(f"得分: {result['score']}")
print(f"形态日期: {result['pattern_date']}")
print(f"第一根跌幅: {result['first_candle_decline']}%")
print(f"第三根涨幅: {result['third_candle_advance']}%")
```

### OpenClaw Agent

```
@morning-star-agent 分析 000001 的早晨之星形态
@morning-star-agent 扫描今日早晨之星
@morning-star-agent 分析科技板块
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
| 形态完整性 | 35% | 三根K线是否符合标准 |
| 位置确认 | 25% | 是否在下跌趋势末端 |
| 成交量确认 | 20% | 是否满足量价配合 |
| 后续确认 | 20% | 形态后是否继续上涨 |

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
- ✅ 实现早晨之星形态识别
- ✅ 支持多数据源
- ✅ 添加四维度评分系统
- ✅ 集成风险管理和报告生成
