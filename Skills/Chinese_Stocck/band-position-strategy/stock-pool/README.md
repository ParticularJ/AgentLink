# Band Position Stock Pool (波段仓股票池)

波段仓策略的独立股票池，包含技术形态筛选的标的。

## 文件说明

| 文件 | 说明 |
|:---|:---|
| `breakout_candidates.json` | 突破新高候选 |
| `ma_bullish_candidates.json` | 均线多头候选 |
| `divergence_candidates.json` | MACD背离候选 |
| `oversold_candidates.json` | RSI超卖候选 |
| `pattern_candidates.json` | 形态候选（晨星/缺口） |
| `volume_candidates.json` | 量能异常候选 |

## 数据流

```
多策略扫描
    ↓
各策略候选池
    ↓
信号强度评分
    ↓
综合排序
    ↓
Top 5-10 推荐
```

## 更新频率

- **每日扫描**：收盘后运行所有策略扫描
- **实时监控**：交易时段关键形态触发
