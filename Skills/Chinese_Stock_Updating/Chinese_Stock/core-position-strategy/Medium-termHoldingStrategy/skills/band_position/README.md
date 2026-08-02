# 波段交易系统

基于V5.0初筛逻辑和V4.0二次筛选逻辑的波段交易选股系统。

## 项目结构

```
band_position/
├── src/
│   ├── common/              # 公共模块
│   │   ├── models.py        # 数据模型定义
│   │   └── constants.py     # 常量配置
│   ├── phase1/              # 第一阶段：赛道与个股初筛
│   │   ├── market_environment.py  # 大盘环境评估
│   │   ├── track_discovery.py     # 赛道发现
│   │   ├── filters.py             # 强制过滤
│   │   ├── scoring.py             # 三因子评分
│   │   └── pipeline.py            # 完整流程管道
│   ├── phase2/              # 第二阶段：基本面二次筛选
│   │   ├── moat.py          # 护城河评估
│   │   ├── veto.py          # 一票否决
│   │   ├── financial.py     # 财报评分
│   │   ├── valuation.py     # 估值判断
│   │   ├── position.py      # 仓位计算
│   │   └── pipeline.py      # 完整流程管道
│   └── tests/               # 测试模块
│       ├── test_phase1.py   # 第一阶段测试
│       ├── test_phase2.py   # 第二阶段测试
│       └── test_integration.py  # 集成测试
├── data/                    # 数据目录
│   ├── phase1_output/       # 第一阶段输出
│   └── phase2_output/       # 第二阶段输出
├── run_tests.py             # 测试运行脚本
└── README.md                # 项目说明

```

## 核心功能

### 第一阶段：赛道与个股初筛

1. **大盘环境评估**
   - 指数趋势（40%）
   - 市场流动性（30%）
   - 市场情绪（20%）
   - 北向资金（10%）
   - 绿灯/黄灯/红灯三级体系

2. **赛道发现**
   - 政策驱动赛道
   - 资金驱动赛道
   - 产业驱动赛道
   - 三层漏斗 + 交叉验证

3. **强制过滤**
   - 财务雷区过滤
   - 过度涨幅过滤（动态阈值）
   - 流动性过滤

4. **三因子评分**
   - 产业动量（35分）
   - 个股弹性（35分）
   - 安全边际（30分）

5. **档位判定**
   - 第一档（核心配置）
   - 第二档（重点配置）
   - 第三档（剔除）

### 第二阶段：基本面二次筛选

1. **护城河评估**
   - 定价权/差异化壁垒
   - 客户粘性
   - 利润含金量
   - 定量评分卡（满分20分）

2. **一票否决**
   - 管理层违规
   - 审计意见非标
   - 北向资金持续流出
   - 大股东高比例质押
   - 近期大额解禁
   - 财报前涨幅过大

3. **财报评分**
   - 营收增速（8分）
   - 利润增速（8分）
   - 业绩趋势（8分）
   - 盈利质量（8分）
   - ROE（8分）
   - 季报超预期（10分）
   - 机构态度（10分）
   - 满分60分

4. **估值判断**
   - PEG法（科技成长/消费价值）
   - PB-ROE法（周期资源/制造工业）
   - PS法（亏损科技股）
   - 历史估值分位点
   - 机构持仓变化跟踪

5. **仓位计算**
   - 建议基准仓位
   - 估值仓位系数
   - 护城河调整系数
   - 止损位设定

## 使用方法

### 运行测试

```bash
python3 run_tests.py
```

### 使用第一阶段

```python
from src.phase1.pipeline import Phase1Pipeline
from src.phase1.track_discovery import TrackSourceData
from src.common.models import Stock

# 初始化
pipeline = Phase1Pipeline()

# 准备数据
market_params = {
    "rps50": 70, "rps120": 60,
    "ma20": 4000, "ma60": 3800, "current_index": 4100,
    "avg_daily_volume_5d": 12000,
    "rise_fall_ratio": 2.5, "limit_up_count": 60,
    "net_inflow_20d": 150,
}

stocks = [Stock(code="000001", name="平安银行", ...)]

# 执行
market_score, tracks, results, output_file = pipeline.run(
    market_params=market_params,
    policy_tracks=["AI芯片", "固态电池"],
    capital_data=[TrackSourceData(...)],
    industry_data=[TrackSourceData(...)],
    stocks=stocks,
)
```

### 使用第二阶段

```python
from src.phase2.pipeline import Phase2Pipeline

# 初始化
pipeline = Phase2Pipeline()

# 准备数据
stock_data = {
    "000001": {
        "moat": {"gross_margin": 30, ...},
        "veto": {"has_violation": False, ...},
        "financial": {"revenue_growth": 25, ...},
        "valuation": {"pe_ttm": 20, ...},
    }
}

# 执行
results, output_file = pipeline.run(
    phase1_results=phase1_results,
    stock_data=stock_data,
)
```

## 测试覆盖

- **第一阶段测试**：大盘环境、赛道发现、强制过滤、三因子评分
- **第二阶段测试**：护城河、一票否决、财报评分、估值、仓位
- **集成测试**：完整流程验证

## 版本信息

- 初筛逻辑：V5.0
- 二次筛选逻辑：V4.0
- 代码版本：1.0.0
