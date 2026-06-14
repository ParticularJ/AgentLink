# 策略融合投资顾问

融合11个交易策略的推荐结果，按时段分组输出最优投资组合。

## 运行方式

### 尾盘买（14:30）
```bash
python3 skills/scripts/fusion_runner.py --session EVENING --top 5
```

### 早盘买次日（16:00）
```bash
python3 skills/scripts/fusion_runner.py --session MORNING --top 5
```

## 输出文件

`recommendations/YYYYMMDD_EVENING_BUY_recommendation.json`
`recommendations/YYYYMMDD_MORNING_BUY_recommendation.json`

## 融合策略分组

### 尾盘买（EVENING）
- 缺口填充、涨停回踩、MACD底背离、RSI超卖、地量见底、缩量回踩均线、均线多头

### 早盘买（MORNING）
- 突破新高、涨停分析/打板、业绩超预期、早晨之星

## 安装依赖

```bash
pip install -r requirements.txt
```

## 目录结构

```
strategy-fusion-advisor/
├── crons/                    # 定时任务配置
├── skills/scripts/
│   └── fusion_runner.py      # 主入口
├── SKILL.md
├── README.md
└── requirements.txt
```

## 免责声明

本工具仅供参考学习，不构成投资建议。股市有风险，投资需谨慎。
