# Hot Spot Recommendations (热点仓推荐记录)

热点仓策略的独立交易推荐记录。

## 文件说明

| 文件 | 说明 |
|:---|:---|
| `YYYYMMDD_morning_buy_recommendation.json` | 早盘推荐 |
| `YYYYMMDD_evening_buy_recommendation.json` | 尾盘推荐 |
| `YYYYMMDD_sell_recommendation.json` | 卖出推荐 |

## 记录格式

```json
{
  "date": "20250614",
  "strategy": "hot-spot",
  "recommendations": [
    {
      "code": "000001",
      "name": "平安银行",
      "strategy_type": "FIRST_LIMIT_UP",
      "score": 85,
      "position_pct": 0.20,
      "holding_days": 3,
      "reason": "首次涨停板，封单质量高"
    }
  ]
}
```

## 保留策略

- 推荐记录保留至少90天
- 每日复盘报告归档
