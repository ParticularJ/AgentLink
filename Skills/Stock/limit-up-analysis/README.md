# A股涨停板连板分析系统

基于多维度量化分析的涨停板连板可能性评估系统。

## 功能特性

- 📊 **实时涨停数据抓取**：自动获取当日涨停股票数据
- 🎯 **五维度量化分析**：封板强度、板块效应、资金流向、技术形态、市场情绪
- 📈 **智能评分系统**：0-100分量化评分，直观判断连板概率
- 🤖 **AI分析助手**：基于大模型的智能分析解读
- ⏰ **定时任务**：交易日自动抓取和分析
- 💾 **历史数据**：保存分析历史，支持回溯查看

## 项目结构

```
limit-up-analysis/
├── README.md                    # 项目说明
├── SKILL.md                     # OpenClaw Skill 文档
├── requirements.txt             # Python依赖
├── setup.sh                     # 安装脚本
├── config/
│   └── scoring_weights.yaml     # 评分权重配置
├── crons/
│   └── limit-up-crons.yaml      # 定时任务配置
├── agents/
│   └── limit-up-agent.yaml      # OpenClaw Agent配置
└── skills/
    └── limit_up/
        └── scripts/
            ├── analyzer.py      # 主分析器
            └── scorer.py        # 评分算法
```

## 安装

```bash
cd ~/.npm-global/lib/node_modules/openclaw/skills/Stock/limit-up-analysis

# 安装依赖
pip install -r requirements.txt

# 运行安装脚本
bash setup.sh
```

## 使用方法

### 1. 命令行分析

```bash
# 分析单只股票
python skills/limit_up/scripts/analyzer.py --code 000001

# 分析当日所有涨停股
python skills/limit_up/scripts/analyzer.py --all

# 分析并保存结果
python skills/limit_up/scripts/analyzer.py --all --save

# 查看历史分析
python skills/limit_up/scripts/analyzer.py --history 2024-01-15

# 显示前20名
python skills/limit_up/scripts/analyzer.py --all --top 20
```

### 2. 通过 OpenClaw 调用

```
@limit-up-agent 分析 000001 的连板可能性
@limit-up-agent 查看今日涨停分析
@limit-up-agent 分析板块 半导体
```

### 3. Python API

```python
from skills.limit_up.scripts.analyzer import LimitUpAnalyzer

analyzer = LimitUpAnalyzer()

# 分析单只股票
result = analyzer.analyze_stock("000001")
print(f"评分: {result['scores']['total']}")
print(f"建议: {result['recommendation']}")

# 分析当日所有涨停股
results = analyzer.analyze_all_limit_up()
for r in results[:10]:
    print(f"{r['code']} {r['name']}: {r['scores']['total']}分")
```

## 评分标准

| 分数 | 等级 | 连板概率 | 建议 |
|------|------|---------|------|
| ≥85 | 极高 | 龙头气质 | 重点关注，积极参与 |
| 75-84 | 高 | 可能性大 | 可考虑打板或低吸 |
| 65-74 | 中等 | 需观察 | 结合盘面判断 |
| 55-64 | 低 | 概率低 | 谨慎参与 |
| <55 | 极低 | 极难连板 | 建议观望 |

## 分析维度权重

| 维度 | 权重 | 关键指标 |
|------|------|---------|
| 封板强度分析 | 30% | 封单比、封板时间、炸板次数 |
| 板块效应分析 | 25% | 同板块涨停数、龙头地位、板块热度 |
| 资金流向分析 | 20% | 主力净流入、换手率 |
| 技术形态分析 | 15% | 突破形态、量价配合 |
| 市场情绪分析 | 10% | 连板高度、涨停数量 |

## 输出示例

```
═══════════════════════════════════════════════════════════
📈 股票: 000001 平安银行 (银行)
═══════════════════════════════════════════════════════════

【综合评分】 78/100 (高)
【连板数】 2板

【五维分析】
  封板强度: ██████████████████████████████ 85
  板块效应: ████████████████████████░░░░░░ 72
  资金流向: ████████████████████████████░░ 80
  技术形态: ████████████████████░░░░░░░░░░ 65
  市场情绪: ████████████████████████░░░░░░ 70

【操作建议】
  ✅ 关注 - 连板可能性大，可考虑打板
```

## 定时任务

系统配置以下定时任务（交易日自动执行）：

| 时间 | 任务 | 说明 |
|------|------|------|
| 9:30 | 早盘数据抓取 | 抓取并分析早盘涨停股票 |
| 13:00 | 午盘数据更新 | 更新午盘涨停股票数据 |
| 15:05 | 收盘数据汇总 | 生成收盘涨停分析报告 |
| 17:00 | 龙虎榜数据更新 | 更新龙虎榜数据 |
| 周日 00:00 | 历史数据清理 | 清理过期历史数据 |

## 配置文件

### 评分权重 (config/scoring_weights.yaml)
可自定义各维度权重和评分标准。

### 定时任务 (crons/limit-up-crons.yaml)
配置自动抓取和分析的时间，支持节假日休市设置。

## 数据存储

- 历史数据: `~/.openclaw/stock/data/history/`
- 缓存数据: `~/.openclaw/stock/data/cache/`
- 日志文件: `~/.openclaw/stock/logs/`

## 依赖

- Python 3.8+
- akshare: A股数据获取
- pandas: 数据处理
- numpy: 数值计算
- pyyaml: 配置管理
- colorama: 终端颜色输出

## 更新日志

### v1.0.0
- 初始版本发布
- 实现五维度量化分析模型
- 支持命令行和API调用
- 添加定时任务支持

## 免责声明

本系统仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。

## 许可证

MIT License
