# 测试套件

## 运行

```bash
# 零依赖入口（仅用标准库 unittest，部署机上也能跑）
python tests/run_tests.py          # 全部用例
python tests/run_tests.py -v       # 详细输出
python tests/run_tests.py -k "test_holdings.py"   # 只跑某类文件

# 装了 pytest 的环境也可以直接
pytest tests
```

## 设计约定

1. **离线可跑**：不联网、不依赖 akshare/pytdx/baostock。
   缺失的重型依赖由 `tests/support.py` 打桩（test double），
   保证被测模块能被 import，而真正需要联网的调用在测试里不会被触发。
2. **只用 unittest**：pytest 也能收集，但没有 pytest 也不会跑不了。
3. **纯函数优先**：凡是能脱离网络与文件系统验证的逻辑，都单独测。

## 用例分布

| 文件 | 覆盖内容 |
|:---|:---|
| `test_paths.py` | 路径推导、环境变量覆盖、嵌套入口的 ROOT 一致性 |
| `test_feishu_config.py` | 凭据加载优先级（env > secrets.yaml > 模板）、无 pyyaml 兜底解析 |
| `test_holdings.py` | 代码规范化、读写、备份、原子写入、损坏文件容错 |
| `test_watchlist.py` | 股票池解析（含 `level:` 标量、空列表、非法条目等历史脏数据） |
| `test_indicators_grade.py` | RSI/涨跌幅/上影线、分级与止盈目标 |
| `test_fusion.py` | 融合打分、共振加分、板块门控、仓位计算、ETF 推荐 |
| `test_stop_loss.py` | 止损优先级 1~4、状态更新、Action 结构 |
| `test_strategy_modules.py` | 各 analyzer 可导入、均线判定正确、fusion 能动态加载策略 |
| `test_code_standards.py` | 编码规范护栏（见下） |

## 编码规范护栏

`test_code_standards.py` 把本轮重构确立的约定固化下来，防止回退：

- 代码里不出现 `/home/jarvis` 之类绝对路径；
- 不出现 `./my_stock_pool/...` 这类依赖当前工作目录的数据路径；
- 源码中不出现明文飞书 App Secret（只允许存在于 `.gitignore` 忽略的 `common/secrets.yaml`）；
- 不出现裸 `except:`；
- 静默 `except: pass` 数量不得超过基线（棘轮：只减不增）；
- 所有消费 `common` 的脚本使用同一套引导代码；
- 股票池 / 持仓 / 飞书 token 不允许各写一份实现；
- `common/` 不得反向依赖策略目录；
- 若本机装了 pyflakes，则要求全量零告警。

> 这些断言依赖「在测试源码里写出被禁止的模式」来检查，
> 因此扫描时会跳过 `tests/` 目录本身。

## 曾经的「已知问题」——已修复

上一轮把两处策略口径问题写成了特征化测试（固化现状、等决策）。
本轮已按最合理的方式修改，特征化测试相应改为**断言新行为**：

| 位置 | 改动 | 对应用例 |
|:---|:---|:---|
| `fusion_runner` 共振加分 | 对外分数仍截断在 100，但新增未截断的 `rank_score` / `base_score_raw` 用于排序，共振不再被吞掉 | `test_resonance_is_not_lost_after_the_cap`、`test_ranking_prefers_more_resonance_on_tie` |
| `stop_loss_engine` 优先级 9 | 去掉恒真的 `loss_pct >= clear_stop_pct*0.8`，把「持仓>10 日且浮盈<5% 清仓」的语义显式化并提为常量 | `test_priority9_time_stop_current_behaviour` |

两处改动的回测依据见 [../backtests/README.md](../backtests/README.md)。
