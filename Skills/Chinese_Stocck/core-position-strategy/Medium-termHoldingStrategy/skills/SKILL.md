# Stock Trade Executor

股票交易执行器 - 封装 Medium-termHoldingStrategy 的 execute_trade 函数。

## 路径

```
/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/Medium-termHoldingStrategy/skills/trade_executor.py
```

## 强制执行规则

**所有买卖操作必须通过 execute_trade()，禁止直接修改 holdings.json 或 cash_balance.json！**

违者视为操作失败，需重新通过 trade_executor 执行。

## 触发条件

用户说以下关键词时激活：
- "买入" / "建仓" / "加仓"
- "卖出" / "清仓" / "减仓"

## 输入参数

从用户消息中解析：
| 参数 | 来源 | 说明 |
|-----|------|------|

| code | 从对话中解析 | 股票代码，如 600105 |
| action | 根据触发词判断 | buy / sell |
| shares | 从对话中解析 | 股数 |
| price | 从对话中解析 | 成交价格 |
| strategy_name | 从对话中解析 | 策略名称 |

## 用户回复格式示例

| 操作 | 回复格式 |
|-----|---------|
| 买入 | `买入 600105 100 # 50.0 - 突破新高策略` |
| 卖出 | `卖出 600105 50 # 55.0 - 止损策略` |

参数解析规则：
- 第1个词：buy/sell → action
- 第2个词：股票代码
- 第3个词：股数
- 第4个词：价格（#分隔）
- 第5个词：策略名称（-分隔）

- # 后面的数字：价格（单位：元）
- - 后面的文本：策略名称

## 调用方式

```python
from trade_executor import execute_trade

result = execute_trade(
    code="600105",
    action="buy",
    shares=100,
    price=50.0,
    strategy_name="突破新高"
)

# 返回结果
{
    "success": True/False,
    "message": "交易成功/失败原因",
    "holdings": [...],  # 更新后的持仓
    "cash": 999400.0    # 更新后的现金
}
```

## 执行流程

1. **读取 SKILL.md** - 确认执行规范
2. **参数解析** - 从用户消息中提取 code/shares/price
3. **执行交易** - 调用 `execute_trade()`
4. **运行监控脚本** - 执行完成后运行对应时间的 monitor.sh：
   - 早盘时段（09:15-11:30）：`sh /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/run_morning_monitor.sh`
   - 尾盘时段（13:00-15:00）：`sh /home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/run_evening_monitor.sh`
5. **结果回报** - 告知成功/失败，列出更新后的持仓和现金

## 配置文件

- 持仓文件：`/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json`
- 现金文件：`/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/cash_balance.json`

## 注意事项

- **交易后必须运行 monitor.sh 确认状态**
- 依赖 `schedule` 库，需确保已安装
- 现金余额不足时返回失败
- 卖出数量不得超过持仓
- 执行后自动更新 holdings.json 和 cash_balance.json