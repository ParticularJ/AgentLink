# 波段仓推荐记录

波段仓策略的独立交易推荐记录。

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
  "strategy": "band-position",
  "recommendations": [
    {
      "code": "000001",
      "name": "平安银行",
      "sub_strategy": "突破新高",
      "entry_price": 12.50,
      "target_price": 15.00,
      "stop_loss": 11.80,
      "position_pct": 0.10,
      "reason": "突破历史新高，量能配合"
    }
  ]
}
```

## 保留策略

- 推荐记录保留至少90天
- 每月策略绩效回顾
