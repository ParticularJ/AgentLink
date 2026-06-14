# 共享脚本

跨策略共享的公共工具脚本。

## 文件说明

| 文件 | 功能 |
|:---|:---|
| `batch_collector.py` | 批量数据收集器 |
| `data_collector.py` | 市场数据获取接口 |
| `run_and_save.py` | 运行结果自动保存 |
| `save_wrapper.py` | 文件保存包装器 |

## 使用方式

```python
from _shared.data_collector import DataCollector

collector = DataCollector()
data = collector.get_stock_data("000001")
```

## 免责声明

仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。
