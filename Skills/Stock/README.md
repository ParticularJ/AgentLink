# Stock - 股票交易策略 Skills

本目录包含各种股票交易策略的 OpenClaw Skills。

## 现有策略

### 1. 涨停板连板分析 (limit-up-analysis)

基于多维度量化分析的涨停板连板可能性评估系统。

**功能特性：**
- 📊 实时涨停数据抓取
- 🎯 五维度量化分析（封板强度、板块效应、资金流向、技术形态、市场情绪）
- 📈 0-100分智能评分系统
- ⏰ 交易日定时任务
- 💾 历史数据保存

**使用方法：**
```bash
cd limit-up-analysis
python skills/limit_up/scripts/analyzer.py --all
```

**详细文档：** [limit-up-analysis/README.md](limit-up-analysis/README.md)

---

## 添加新策略

要添加新的交易策略 skill，请创建独立的子目录：

```
Stock/
├── limit-up-analysis/      # 连板分析策略
├── your-strategy/          # 你的新策略
│   ├── README.md
│   ├── requirements.txt
│   ├── setup.sh
│   └── scripts/
│       └── analyzer.py
└── README.md               # 本文件
```

每个策略应该是独立的，包含：
- 独立的 README.md 文档
- 独立的依赖文件 (requirements.txt)
- 独立的安装脚本 (setup.sh)
- 独立的分析脚本

## 免责声明

所有策略仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。
