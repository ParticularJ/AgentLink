# Core Position Strategy (核心仓策略)

基于赛道生命周期与基本面六维评分的核心仓位管理系统，持仓周期3-6个月，资金占比50%。

## Strategy Overview

| Dimension | Specification |
|:---|:---|
| **Investment Horizon** | Quarterly (3-6 months) |
| **Capital Allocation** | 50% of total capital |
| **Position Count** | 5-8 stocks |
| **Max Single Position** | ≤18% of core capital |
| **Stop Loss** | ATR Adaptive / Fixed -10% |
| **Take Profit** | 4-tier (15%/25%/40%/60%) |

## Strategy Flow

### Phase 1: Stock Selection (Quarterly)

```
Macro Liquidity Assessment
    ↓ (Expansion/Stable → Proceed; Contraction → Halt)
Sector Lifecycle Screening
    ↓ (Early Explosion 5-10% / Mid Explosion 10-20% only)
Individual Stock Initial Screening
    ↓ (6-dimension scoring + 8 veto conditions)
Initial Pool (50-60 stocks)
```

### Phase 2: Secondary Screening (Earnings Season)

```
Financial Report Scoring
    ↓ (Revenue/Profit/Cashflow/Margin/Forward 5 dimensions)
Risk Screening
    ↓ (Cash flow/Receivable/Inventory/Reduction red lines)
Earnings Surprise Verification
    ↓ (Price/Analyst/Volume/Northbound 4 dimensions)
Comprehensive Score = Initial×35% + Financial×40% + Expectation×25%
    ↓
Buy Candidate Pool (5-8 stocks)
```

### Phase 3: Daily Buy Timing

```
Market Environment Filter
    ↓ (Strong/Oscillating/Weak)
Buy Point Recognition
    ↓ (Pullback to MA20 preferred)
Buy Point Quality Scoring
    ↓ (Ideal/Normal/Marginal)
Position Size Calculation
    ↓ (Base × Score × Technical × Market)
6-Item Confirmation Checklist
    ↓ (All must pass)
Execute Buy (Batch strategy)
```

### Phase 4: Position Monitoring

```
Daily: Technical Monitoring (15 min)
    - MA20/Volume/RSI/MACD/Sector Strength/Volatility
Weekly: Fundamental Monitoring (30 min)
    - Industry dynamics/Company announcements/Research reports/Valuation/Northbound
Monthly: Portfolio Risk Control
    - 3-line defense: Individual/Sector/Portfolio stop loss
```

## Directory Structure

```
core-position-strategy/
├── README.md                          # This file
├── core-position-strategy/            # Core strategy engine V3.0
│   ├── SKILL.md                       # Skill definition
│   └── skills/scripts/
│       ├── models.py                  # Data models
│       ├── macro_filter.py            # Macro liquidity filter
│       ├── sector_scorer.py           # Sector 5-dimension scorer
│       ├── initial_scorer.py          # Stock 6-dimension initial screener
│       ├── secondary_scorer.py        # Financial report verification
│       ├── buy_signal.py              # Daily buy timing
│       ├── position_monitor.py        # Stop loss / Take profit / Add position
│       ├── portfolio_manager.py       # Portfolio management
│       ├── core_position_pipeline.py  # Main pipeline
│       └── test_core_position.py      # Unit tests (31 tests)
└── Medium-termHoldingStrategy/        # Mid-term holding execution
    └── skills/
        ├── SKILL.md                   # Trade executor
        ├── trade_executor.py          # Execution engine
        └── scripts/                   # Monitoring scripts
            ├── main.py
            ├── new_holding_monitor.py
            ├── stop_loss_engine.py
            ├── add_position_analyzer.py
            └── ...
```

## Key Features

- 🌍 **Macro Liquidity Matching**: 3-tier environment judgment
- 🎯 **Sector Lifecycle**: Only early/mid explosion phases
- 📊 **6-Dimension Scoring**: Heat, Position, Barrier, Certainty, Management, Consensus
- 🛡️ **8 Veto Conditions**: Management integrity, coverage, ROE, pledge ratio, etc.
- 📈 **Financial Verification**: 5-dimension scoring + 4-dimension surprise check
- 💰 **Smart Position Sizing**: Multi-coefficient calculation
- 📉 **ATR Adaptive Stop Loss**: Volatility-based dynamic stop
- 📊 **Tiered Take Profit**: 4-level profit taking
- ➕ **Add Position Strategy**: 2-tier threshold, never against sector
- 🛡️ **3-Line Risk Control**: Individual/Sector/Portfolio defense

## Usage

```python
from core-position-strategy.skills.scripts.core_position_pipeline import CorePositionPipeline

# Initialize pipeline
pipeline = CorePositionPipeline(total_capital=1000000.0, core_ratio=0.50)

# Run full selection process
result = pipeline.run_full_pipeline(
    macro_data={...},
    sectors_data=[...],
    stocks_data=[...],
    financial_reports={...},
    verifications={...},
    market_data={...},
    tech_data_map={...},
    stock_fundamentals={...}
)

# Daily monitoring
monitor_result = pipeline.run_daily_monitor(
    daily_tech_data={...},
    weekly_fundamental_data={...},
    market_data={...}
)
```

## Disclaimer

For research and educational purposes only. Not investment advice. Stock market carries risks.
