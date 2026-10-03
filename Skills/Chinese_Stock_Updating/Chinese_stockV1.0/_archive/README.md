# _archive —— 历史版本归档（不参与运行）

这里存放的是**同一份文件的历史分叉版本**，它们都已被 `_archive/` 之外的正式文件取代。
保留的目的只有一个：万一需要回溯某个被移除的策略/参数时不必从零重写。

> 正式代码**不会** import、也不会读取本目录中的任何文件。
> 如果确认不再需要，可以整个目录直接删除。

| 归档文件 | 曾对应的正式文件 | 差异与归档原因 |
|:---|:---|:---|
| `market_phase_detector_copy.py` | `strategy-fusion-advisor/skills/scripts/market_phase_detector.py` | 2026-09-11 前后的分叉版本：多出 `judge_power_grid_v9` / `judge_securities_v9` / `judge_low_altitude_v9` 三个专用判定，以及「低空经济」板块（26 板块）。现役版本为 25 板块、这三个板块改为 `no_chase` 处理。判定以最新产物 `market_phase.json`（2026-09-12，25 板块）为准。 |
| `limit_up_analysis_analyzer copy.py` | `limit-up-analysis/skills/scripts/limit_up_analysis_analyzer.py` | 旧版多出 `_get_index_code` / `_get_market_index_data`（指数行情辅助）。 |
| `breakout_high_strategy_analyzer copy.py` | `breakout-high-strategy/skills/scripts/breakout_high_strategy_analyzer.py` | 旧版的数据列名兼容映射（中文列名 → close/high/volume）实现。 |
| `watchlist copy.yaml` | `my_stock_pool/watchlist.yaml` | 更早月份的股票池快照。 |
| `watchlist_all.yaml` | `my_stock_pool/watchlist.yaml` | 同名同长度的另一版股票池（全量口径），未被任何代码引用。 |
| `watchlist_copy.yaml` | `my_stock_pool/watchlist.yaml` | 20 行的草稿片段，未被任何代码引用。 |
| `scanne.py.bk` | `breakout-high-strategy/skills/scripts/scanner.py` | 文件名拼写错误的遗留备份。 |

## 代码中引用股票池的位置

- `my_stock_pool/watchlist.yaml`：`market_phase_detector.py` 构建「个股 → 板块」映射
- `my_stock_pool/watchlist_core.yaml`：`news_watchlist_scanner.py`（新闻盯盘）

其余 `watchlist*.yaml` 均无代码引用，已全部归档。
