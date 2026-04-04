# 涨停板连板分析 Skill

基于多维度量化分析的涨停板连板可能性评估系统。

## 功能

- 实时涨停数据抓取
- 五维度量化分析（封板强度、板块效应、资金流向、技术形态、市场情绪）
- 0-100分智能评分系统
- 交易日定时任务
- 历史数据保存

## 使用方法

### 命令行

```bash
# 分析当日所有涨停股
python skills/limit_up/scripts/analyzer.py --all

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

analyzer = LimitUpAnalyzer()
results = analyzer.analyze_all_limit_up()
```

### OpenClaw Agent

```
@limit-up-agent 分析 000001 的连板可能性
@limit-up-agent 查看今日涨停分析
```

## 评分标准

| 分数 | 等级 | 建议 |
|------|------|------|
| ≥85 | 极高 | 重点关注 |
| 75-84 | 高 | 可考虑打板 |
| 65-74 | 中等 | 需观察 |
| 55-64 | 低 | 谨慎参与 |
| <55 | 极低 | 建议观望 |

## 依赖

- akshare
- pandas
- colorama

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。
