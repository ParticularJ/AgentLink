# Core Position Recommendations (核心仓推荐记录)

核心仓策略的独立交易推荐记录。

## 文件说明

| 文件 | 说明 |
|:---|:---|
| `YYYYMMDD_morning_buy_recommendation.json` | 早盘买入推荐 |
| `YYYYMMDD_evening_buy_recommendation.json` | 尾盘买入推荐 |

## 记录格式

```json
{
  "date": "20250614",
  "strategy": "core-position",
  "recommendations": [
    {
      "code": "000001",
      "name": "平安银行",
      "signal": "STRONG_BUY",
      "score": 92,
      "position_pct": 0.15,
      "reason": "综合评分≥90，理想买点"
    }
  ]
}
```

## 保留策略

- 推荐记录保留至少90天
- 定期归档到历史库
