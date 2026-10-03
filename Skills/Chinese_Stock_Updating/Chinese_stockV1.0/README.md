# 股票策略系统 (Chinese_stockV1.0)

A 股「选股推荐 + 持仓监控」一体化策略系统：
**11 个独立选股策略 → 板块行情门控 → 融合打分 → 飞书推送**，配合**持仓止损止盈引擎**与**交易执行器**。

---

## 目录结构

```
Chinese_stockV1.0/
├── common/                          # 【公共模块】全工程唯一路径 / 凭据来源
│   ├── paths.py                     #   ROOT 及各路径推导（可用环境变量覆盖）
│   ├── feishu_config.py             #   飞书凭据加载（环境变量 > secrets.yaml）
│   ├── secrets.yaml                 #   真实凭据（.gitignore 忽略，不入库）
│   └── secrets.example.yaml         #   凭据模板
├── scripts/                         # 【脚本层】shell 公共环境 + 可测试的 Python 任务
│   ├── _common.sh                   #   所有 run_*.sh 的公共前置（路径/解释器/代理）
│   └── trade_query.py               #   盘中交易询问卡片
├── run_*.sh                         # 【入口层】13 个定时任务包装脚本（无绝对路径）
├── strategy-fusion-advisor/          # 【决策层】板块行情判定 + 策略融合
│   ├── skills/scripts/
│   │   ├── market_phase_detector.py #   大盘 + 26 板块 5 档行情判定
│   │   ├── fusion_runner.py         #   策略调度 + 板块门控 + 融合打分
│   │   ├── send_feishu_card.py      #   推荐卡片推送
│   │   ├── news_watchlist_scanner.py#   股池利空盯盘
│   │   ├── test_news.py             #   LLM 新闻多空判定（推荐扣分）
│   │   ├── earnings_caculate.py     #   财报不及预期黑名单
│   │   └── llm_client.py            #   OpenAI 兼容 LLM 客户端
│   ├── recommendations/             #   market_phase.json + cache/ + 回测 CSV
│   ├── crons/                       #   定时任务声明
│   └── DESIGN.md                    #   v4.3 完整设计文档（推荐先读）
├── Medium-termHoldingStrategy/       # 【监控层】持仓止损止盈与交易执行
│   └── skills/
│       ├── trade_executor.py        #   唯一合法的买卖入口
│       └── scripts/
│           ├── main.py              #   持仓价格/评分刷新 + 交易落库
│           ├── stop_loss_engine.py  #   优先级 1~9 止损决策引擎
│           ├── position_monitor.py  #   5 层止损 + 4 阶止盈（V3.0）
│           ├── add_position_analyzer.py  # 加仓四级筛选
│           ├── send_holding_card.py #   持仓监控日报卡片
│           ├── market_sentiment.py  #   大盘情绪（决定能否卖/清仓）
│           ├── atr_calculator.py    #   ATR 止损位计算
│           ├── data_source.py       #   腾讯/新浪行情适配层
│           └── config.py            #   评分权重 / 龙头分级 / 止盈档位
├── <strategy>/                       # 【策略层】11 个选股策略（结构一致）
│   ├── config/*.yaml                #   评分权重 / 参数 / 风控规则
│   ├── skills/scripts/
│   │   ├── <name>_strategy_analyzer.py  # 核心分析器（fusion_runner 动态加载）
│   │   └── <name>_scanner.py            # 独立 CLI 扫描器（可选）
│   └── README.md
├── my_holdings/                      # 持仓 / 现金 / 备份 / 分析日志
├── my_stock_pool/                    # watchlist.yaml（个股→板块）+ watchlist_core.yaml
├── recommendations/                  # 每日推荐输出 YYYYMMDD_{MORNING,EVENING}_buy_recommendation.json
├── logs/                             # 运行日志（自动创建）
├── _archive/                         # 历史分叉版本归档（不参与运行，见其 README）
└── .gitignore
```

### 11 个策略

| 策略目录 | 说明 | 默认时段 |
|:---|:---|:---|
| `gap-fill-strategy` | 缺口回补 | EVENING（已启用） |
| `ma-bullish-strategy` | 均线多头排列 | EVENING（已启用） |
| `breakout-high-strategy` | 突破前期高点 | MORNING（已启用） |
| `macd-divergence-strategy` | MACD 底背离 | 预留 |
| `rsi-oversold-strategy` | RSI 超卖反弹 | 预留 |
| `volume-extreme-strategy` | 成交量地量见底 | 预留 |
| `volume-retrace-ma-strategy` | 缩量回踩均线 | 预留 |
| `morning-star-strategy` | 早晨之星 | 预留 |
| `limit-up-retrace-strategy` | 涨停板首次回调 | 预留 |
| `limit-up-analysis` | 涨停板连板分析 | 预留 |
| `earnings-surprise-strategy` | 财报超预期 | 预留 |

启用/停用只需改 `strategy-fusion-advisor/skills/scripts/fusion_runner.py` 顶部的
`EVENING_STRATEGIES` / `MORNING_STRATEGIES` 两个列表。

---

## 快速开始

### 1. 安装依赖

```bash
pip install pandas numpy pyyaml requests akshare
# 可选：pytdx（最快的 A 股日线数据源）、tushare、baostock
```

### 2. 配置凭据（不要在源码里写明文 Secret）

```bash
cp common/secrets.example.yaml common/secrets.yaml
# 填入 app_id / app_secret / group_id
```

也可以完全用环境变量，优先级高于配置文件：

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export FEISHU_GROUP_ID=oc_xxx
```

### 3. 运行

所有入口都在根目录，**不含任何绝对路径**，可放在任意位置执行：

```bash
./run_morning_fusion.sh          # 早盘融合选股
./run_evening_push.sh            # 尾盘推荐推送
./run_morning_monitor.sh         # 持仓监控
./run_add_position.sh            # 加仓信号
```

指定 Python 解释器（部署机常用）：

```bash
STOCK_PYTHON=/opt/conda/envs/vllm/bin/python ./run_morning_fusion.sh
```

---

## 每日时刻表

| 时间 | 脚本 | 作用 |
|:---|:---|:---|
| 08:00 | `run_morning_fusion.sh` | 早盘融合选股（次日买入） |
| 08:00 | `run_news_monitor.sh` | 股池利空盯盘 |
| 08:30 | `run_morning_push.sh` | 早盘推荐推送 |
| 09:15 | `run_morning_holding.sh` | 持仓价格/评分刷新 |
| 09:20 | `run_morning_monitor.sh` | 持仓监控日报 |
| 10:00 | `run_morning_trade_query.sh` | 盘中交易询问 |
| 14:20 | `run_evening_fusion.sh` | 尾盘融合选股（当日买入） |
| 14:35 | `run_evening_push.sh` | 尾盘推荐推送 |
| 14:40 | `run_add_position.sh` | 加仓信号检查 |
| 14:50 | `run_evening_monitor.sh` | 持仓监控日报 |
| 14:50 | `run_evening_holding.sh` | 持仓落库 |
| 14:50 | `run_new_monitor.sh` | 止损止盈引擎 |
| 15:00 | `run_afternoon_trade_query.sh` | 盘中交易询问 |

---

## 架构与数据流

```
my_stock_pool/watchlist.yaml
        │
        ▼
market_phase_detector.py  ──►  MARKET_PHASE_FILE (market_phase.json)
  大盘 4 档 + 26 板块 5 档       │
                                ▼
11 个策略 analyzer ──► fusion_runner.scan_strategy()  [按板块 phase 门控]
                                │
                                ▼
                      fuse_recommendations()  [融合打分]
         best_score + 共振加分(+22/+30) + 新闻惩罚 + 持仓板块加分
                                │
                                ▼
                      + STRONG_UP 板块 ETF 补充推荐
                                │
                                ▼
                      按大盘仓位上限等比缩放
                                │
                                ▼
        RECO_DIR/YYYYMMDD_{MORNING,EVENING}_buy_recommendation.json
                                │
                                ▼
                      send_feishu_card.py ──► 飞书群

持仓链路：
  trade_executor.execute_trade()  ← 用户指令（唯一合法买卖入口）
        │ 写 HOLDINGS_FILE / CASH_FILE（写前自动备份到 backup/）
        ▼
  stop_loss_engine / position_monitor / add_position_analyzer
        │
        ▼
  飞书卡片 + ANALYSIS_LOG_DIR/YYYYMMDD.jsonl
```

---

## 路径与配置约定

**核心原则：代码里不出现任何绝对路径。**

所有路径由 `common/paths.py` 从文件位置向上推导得到，可用环境变量覆盖：

| 环境变量 | 作用 | 默认值 |
|:---|:---|:---|
| `STOCK_ROOT` | 仓库根目录 | 自动推导（含 `my_holdings/` 与 `strategy-fusion-advisor/` 的那一层） |
| `STOCK_PYTHON` | Python 解释器（shell 层） | `python3` |
| `STOCK_HOLDINGS_FILE` | 持仓文件 | `<root>/my_holdings/holdings.json` |
| `STOCK_CASH_FILE` | 现金文件 | `<root>/my_holdings/cash_balance.json` |
| `STOCK_ANALYSIS_LOG_DIR` | 加仓分析日志目录 | `<root>/my_holdings/analysis_logs` |
| `STOCK_RECO_DIR` | 推荐输出目录 | `<root>/recommendations` |
| `STOCK_WATCHLIST_FILE` | 股票池 | `<root>/my_stock_pool/watchlist.yaml` |
| `STOCK_LOG_DIR` | 日志目录 | `<root>/logs` |

在任意脚本中取得路径：

```python
import os, sys
_root = os.path.abspath(os.path.dirname(__file__))
while not os.path.exists(os.path.join(_root, "common", "paths.py")) and _root != os.path.dirname(_root):
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "common"))
from paths import HOLDINGS_FILE, CASH_FILE, LOG_DIR
```

自检：`python common/paths.py` 会打印所有解析结果。

---

## 关键算法速查

### 板块行情门控（`PHASE_SECTOR_FILTER_*`）

| 板块 phase | 个股 | ETF |
|:---|:---|:---|
| STRONG_UP（单边上行） | run（正常买） | run |
| WAVE_UP（波段） | reserve（预留不买） | reserve |
| RANGE（震荡） | reserve | reserve |
| STRONG_DOWN（下行） | block（一票不买） | run_low（需 base_score ≥ 85） |
| WEAK_DOWN / UNKNOWN | block | block |

### 融合打分

```
best_score        = max(各策略得分)
consistency_bonus = 0 / +22（2 个策略共振）/ +30（≥3 个策略共振）
base_score        = best_score + consistency_bonus + penalty + 持仓同板块加分(+5)
combined          = base_score × 0.8 + 加权贡献 × 0.2
建议仓位          = clamp(0.20 − 排名×0.03 + (combined−80)/100×0.10, 8%, 25%)
```

### 止损优先级（`stop_loss_engine.py`）

```
1 绝对亏损清仓 → 2 绝对亏损减半 → 3 极端恐慌禁止卖出 → 4 恐慌区禁止清仓
→ 5 利润模式清仓 → 6 利润模式减半 → 7 MA5 → 8 MA10 → 9 时间止损
外加：假跌破例外（每日 1 次）、纠错买入（每月 ≤ 2 次）
```

---

## 测试

```bash
python tests/run_tests.py        # 130 个用例，离线可跑
python tests/run_tests.py -v
```

覆盖路径/凭据/持仓/股票池等基础设施、融合打分、止损优先级、各策略分析器，
以及一组「编码规范护栏」用例（禁止硬编码路径、明文凭据、裸 except、重复实现等）。
详见 [tests/README.md](tests/README.md)。

---

## 回测（2026 年 10 月池，2025-09-30 → 2026-09-30）

十月股票池已整理为 [my_stock_pool/watchlist_2026-10.yaml](my_stock_pool/watchlist_2026-10.yaml)：
**用的是现有 sector_key，所以切换池子不需要改任何代码**，
回测/实盘只要设 `STOCK_WATCHLIST_FILE` 指向该文件即可
（`common/paths.py` 与板块映射都读同一个环境变量）。

整理时的三处归一（详见文件内注释）：

| 项 | 处理 | 说明 |
|:---|:---|:---|
| 中国船舶（600150） | 归入 `shipping_tanker`（航运） | 检测器没有「船舶制造」板块，属近似映射 |
| 低空经济（600580 / 002085） | 保留 `low_altitude_economy` | 该组**未映射**到任何检测器板块 → 现行门控下永远无法开仓 |
| 药明生物（2269.HK） | 未纳入 | 非 A 股，数据源与策略都只覆盖 A 股 |

**买入持有基线**（等权，前复权）

| 组合 | 收益 | 上涨占比 |
|:---|---:|---:|
| 个股池（81 只） | **+27.32%** | 54.3% |
| ETF 池（39 只） | +1.16% | 43.6% |
| 沪深300 | -6.10% | — |

**策略回测**（T+5 / -5% 止损 / 每日取 5 名）

| 口径 | 笔数 | 胜率 | 均值 | 止损占比 |
|:---|---:|---:|---:|---:|
| 门控开（生产口径） | 724 | 42.3% | +0.98% | 44.6% |
| 门控关（对照） | 787 | 37.9% | +1.15% | 54.0% |

> 数据必须用**前复权**：新浪的未复权序列会把基金份额折算记成 -60% 级别的假跌，
> 一度让整池收益被低估 5 个百分点以上。完整方法、坑与逐月数据见 [backtests/README.md](backtests/README.md)。

---

## 已修复的策略口径问题（含回测依据）

上一轮重构发现的两处问题已经修改，并用 2026 年 9 月（及更长的对照区间）的真实日线数据做了回测。
完整方法与结果见 [backtests/README.md](backtests/README.md)。

### 1. 共振加分被截断吞掉（已修）

**问题**：入选门槛本身就是 80 分，再叠加 `+22 / +30` 的共振加分必然 ≥102，
原实现在计算前就 `min(100, ...)`，于是「2 个策略共振」与「3 个策略共振」得到**完全相同**的分数，
大量候选并列 100 分时 top-N 退化为按插入顺序截取。

**改法**：拆成两个口径，互不干扰——

| 字段 | 用途 | 是否截断 |
|:---|:---|:---|
| `base_score` / `combined_score` | 对外契约（门槛判定、展示、仓位），保持 0~100 | 是 |
| `base_score_raw` / `rank_score` | 只用于排序，保留共振与贡献的全部区分度 | 否 |

排序改为 `key=(rank_score, strategy_count)`，并列时共振更多的排前面。

**回测结论**：在 9 月及 7–9 月区间，修复前后选出的标的**完全一致**——
因为样本里没有出现共振密集或同分并列的情形。
这个修复消除的是并列时的任意性，不会改变稀疏信号下的结果。

### 2. 时间止损的条件恒真（已修）

**问题**：原实现把两个负数拿来比较——

```python
loss_pct = -hs.current_profit_pct            # 浮盈 +0.7% -> -0.007
time_stop_threshold = hs.clear_stop_pct * 0.8  # -0.10 * 0.8 = -0.08
if loss_pct >= time_stop_threshold: ...        # -0.007 >= -0.08 -> 恒为真
```

而模块文档写的是「且亏损≥原止损×0.8」。代码与文档不一致，且那个比较毫无作用。

**改法**：判断哪种口径更合理，然后让代码和文档都对齐它。
该规则的名字虽然是「时间止损」，但它的作用是**资金效率**——
把长期不赚钱的仓位换出来；若真要求大幅亏损，它会与优先级 2 的减半线完全重叠而永远不触发。

因此**保留「持仓超过 TIME_STOP_DAYS 且浮盈不足 TIME_STOP_MIN_PROFIT 即清仓」的语义**，
去掉恒真比较、把参数提为 `TIME_STOP_DAYS` / `TIME_STOP_MIN_PROFIT` 常量，并改正文档。

**回测结论**（前复权数据，2025-10 → 2026-07 信号 + T+40 持有，664 笔）：

| 变体 | 胜率 | 均值 | 累计(收益点) | 最大回撤 | 收益/回撤 | 触发时间止损 |
|:---|---:|---:|---:|---:|---:|---:|
| 关闭时间止损 | 23.0% | **+6.48%** | +4304 | -631.6 | 6.82 | 0 |
| 开启时间止损 | **32.8%** | +5.66% | +3756 | **-514.5** | **7.30** | 148 |

这是一个**权衡**：胜率提高近 10 个百分点、被扫止损的仓位减少 13 个百分点、回撤收窄 18.5%，
但单笔均值与累计收益下降约 13%（部分被砍的仓位后来涨回去了）。
**收益/回撤比从 6.82 提升到 7.30**，风险调整后略优。

因此改动的定位是**让代码与文档一致、并把参数交出来**（`TIME_STOP_DAYS` / `TIME_STOP_MIN_PROFIT`，
设 `TIME_STOP_DAYS = None` 即关闭），至于默认开还是关，取决于更看重胜率/回撤还是单笔期望——

---

## 常见问题

**Q: 换机器后脚本全部跑不起来？**
A: 不应该。所有路径都是相对的。若仍失败，检查 `python common/paths.py` 输出的 ROOT 是否正确，
   或显式设置 `STOCK_ROOT` / `STOCK_PYTHON`。

**Q: 飞书推送报 401 / 提示缺少凭据？**
A: `common/secrets.yaml` 不存在或字段为空。复制 `secrets.example.yaml` 填写，或设置环境变量。

**Q: `_archive/` 是什么？**
A: 同一文件的历史分叉版本（例如被移除的 3 个板块专用判定）。正式代码不会读取它，确认无用可整目录删除。

**Q: 某个策略没跑？**
A: 检查它是否在 `fusion_runner.py` 的 `EVENING_STRATEGIES` / `MORNING_STRATEGIES` 中被注释掉了。

---

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。
