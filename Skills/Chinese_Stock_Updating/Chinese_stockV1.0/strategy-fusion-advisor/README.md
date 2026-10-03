# 策略融合投资顾问

融合多个选股策略的输出，叠加「大盘 + 板块行情门控」后给出最优组合。

完整设计与回测记录见 [DESIGN.md](DESIGN.md)。

## 运行

```bash
# 尾盘买（当日 14:30 前）
python skills/scripts/fusion_runner.py --session EVENING --top 5

# 早盘买（次日 16:00 后）
python skills/scripts/fusion_runner.py --session MORNING --top 5
```

推荐用根目录的包装脚本（自带路径推导与代理清理）：

```bash
bash ../../run_evening_fusion.sh
bash ../../run_morning_fusion.sh
```

## 输出

| 文件 | 内容 |
|:---|:---|
| `<repo>/recommendations/YYYYMMDD_EVENING_BUY_recommendation.json` | 尾盘推荐 |
| `<repo>/recommendations/YYYYMMDD_MORNING_BUY_recommendation.json` | 早盘推荐 |
| `recommendations/market_phase.json` | 大盘 + 各板块行情状态快照 |
| `recommendations/cache/stable_phase.json` | 跨进程的稳定 phase 缓存 |

## 策略分组

分组定义在 `skills/scripts/fusion_runner.py` 顶部：

| 时段 | 当前启用 | 预留（注释中，改一行即可开启） |
|:---|:---|:---|
| EVENING（尾盘买） | 缺口填充、均线多头 | 涨停回踩、MACD 底背离、RSI 超卖、地量见底、缩量回踩均线 |
| MORNING（早盘买次日） | 突破新高 | 涨停分析/打板、业绩超预期、早晨之星 |

## 依赖

```bash
pip install -r requirements.txt
```

## 免责声明

本工具仅供参考学习，不构成投资建议。股市有风险，投资需谨慎。
