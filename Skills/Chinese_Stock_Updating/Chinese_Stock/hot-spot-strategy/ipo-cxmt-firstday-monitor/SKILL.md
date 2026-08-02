# CXMT首日作战矩阵监控

## 用途

监控长鑫科技(CXMT)科创板上市首日实时行情，按《第六部分：首日作战矩阵》规则生成操作建议。

## 触发词

`CXMT首日` / `长鑫科技监控` / `首日作战`

## 核心规则来源

> 《长鑫科技CXMT完整投资指导》第六部分：首日作战矩阵

## 四阶段操作规则

| 阶段 | 时间窗口 | 条件 | 操作 | 金额 |
|-----|---------|------|------|------|
| 集合竞价 | 9:15-9:25 | 涨幅≤50% | 限价买入 | 15万 |
| | | 50%<涨幅≤80% | 买入(谨慎) | 5万 |
| | | 涨幅>80% | 放弃 | 0 |
| 开盘瞬间 | 9:30 | 涨幅≤50% | 不追加 | — |
| | | 50%<涨幅≤80% | 试探买入 | 5万 |
| | | 涨幅>80% | 等第5天回踩 | 0 |
| 冲高回落 | 9:32-10:00 | 涨幅≤80%且回踩均线 | 买入 | 10万 |
| 尾盘确认 | 14:50-15:00 | 收涨+换手>50%+开盘≤80% | 尾盘加仓 | 10万 |
| | | 冲高回落剧烈或>80% | 不加仓 | 0 |

## 四条活命铁律

1. **涨幅>80%(>12.6元)一股不买** — 295亿募资体量决定高开必遭巨量抛压
2. **首日仓位≤40万** — 占总资金40%，留足后手
3. **DRAM涨幅<10%减仓/<0%清仓** — Q3已降至13%-18%，趋势放缓需警惕
4. **账户-8%硬止损** — 科创板前5日无涨跌幅限制

## 使用方式

```bash
cd /home/jarvis/.openclaw/workspace/skills/Chinese_Stock/hot-spot-strategy/ipo-cxmt-firstday-monitor/skills/scripts

# 单次查询
python3 cxmt_firstday_monitor.py --code 588000 --price 10.0 --once

# 实时监控循环(默认10秒刷新)
python3 cxmt_firstday_monitor.py --code 588000 --price 10.0

# 自定义参数
python3 cxmt_firstday_monitor.py --code 588000 --price 9.0 --threshold 12.0 --fund 2000000 --interval 5
```

## 关键参数

| 参数 | 说明 | 默认值 |
|-----|------|-------|
| `--code` | CXMT股票代码(科创板) | 588000(需上市后更新) |
| `--price` | 发行价格(元) | 10.0 |
| `--threshold` | 80%涨幅对应价格 | 12.6 |
| `--fund` | 总资金(元) | 1000000 |
| `--interval` | 刷新间隔(秒) | 10 |
| `--dram-q3` | Q3 DRAM涨幅%(更新预警) | — |

## 输出文件

- 交易日志: `~/.openclaw/stock/data/cxmt_logs/YYYYMMDD_cxmt_trades.json`
- 持仓数据: `~/.openclaw/stock/data/my_holdings/holdings.json`

## 数据依赖

- 实时行情: 东方财富 push2ex.eastmoney.com 接口
- 持仓数据: 与现有 `Chinese_Stock/my_holdings/holdings.json` 共用
