# my_holdings skill

手动录入持仓信息，生成 `YYYYMMDD_holdings.json` 文件。

## 使用方法

```bash
python3 ~/.npm-global/lib/node_modules/openclaw/skills/Stock/Chinese_Stock/my_holdings/scripts/holdings_editor.py
```

## 输出文件

生成的持仓文件保存在 `Chinese_Stock/my_holdings/` 目录：

```
20260412_holdings.json
```

## buy_reason 可选值

| buy_reason | 含义 | 策略类型 |
|-----------|------|---------|
| `limit_up` | 涨停连板 | 激进 |
| `breakout_high` | 突破新高 | 激进 |
| `gap_fill` | 缺口填充 | 稳健 |
| `ma_bullish` | 均线多头 | 稳健 |
| `macd_divergence` | MACD底背离 | 保守 |
| `rsi_oversold` | RSI超卖 | 保守 |
| `morning_star` | 早晨之星 | 保守 |
| `volume_extreme` | 地量见底 | 保守 |
| `a_stock_1430` | 尾盘超短 | 超短 |
