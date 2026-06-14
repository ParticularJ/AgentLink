# Stock Trading Strategy System

A complete A-share trading system based on three position strategies: Core Position, Hot Spot, and Band Position.

## System Architecture

```
Chinese_Stocck/
├── README.md                          # This file
├── core-position-strategy/            # Long-term holding (Quarterly)
│   ├── README.md                      # Strategy overview
│   ├── core-position-strategy/        # Core engine V3.0
│   └── Medium-termHoldingStrategy/    # Mid-term execution
├── hot-spot-strategy/                 # Short-term trading (Daily/Weekly)
│   ├── README.md                      # Strategy overview
│   ├── hot-spot-strategy/             # 4-strategy system
│   ├── limit-up-retrace-strategy/     # Limit-up retrace
│   └── limit-up-analysis/             # Limit-up analysis
├── band-position-strategy/            # Medium-short term (Weekly/Monthly)
│   ├── README.md                      # Strategy overview
│   ├── scripts/                       # Trading scripts
│   ├── breakout-high-strategy/        # Breakout high
│   ├── earnings-surprise-strategy/    # Earnings surprise
│   ├── gap-fill-strategy/             # Gap fill
│   ├── ma-bullish-strategy/           # MA bullish
│   ├── macd-divergence-strategy/      # MACD divergence
│   ├── morning-star-strategy/         # Morning star
│   ├── rsi-oversold-strategy/         # RSI oversold
│   ├── volume-extreme-strategy/       # Volume extreme
│   └── volume-retrace-ma-strategy/    # Volume retrace MA
├── strategy-tools/                    # Cross-strategy tools
│   ├── strategy-fusion-advisor/       # Signal fusion
│   ├── strategy-optimizer/            # Strategy optimization
│   ├── stock_earnings_analysis/       # Earnings analysis
│   └── stock_event/                   # Event monitoring
└── shared-components/                 # Shared data & config
    ├── _shared/                       # Shared scripts
    ├── my_holdings/                   # Holdings data
    ├── my_stock_pool/                 # Stock pools
    └── recommendations/               # Recommendations
```

## Three Strategies Comparison

| Dimension | Core Position | Hot Spot | Band Position |
|:---|:---|:---|:---|
| **Investment Horizon** | Quarterly (3-6 months) | Daily/Weekly (3-8 days) | Weekly/Monthly (2-8 weeks) |
| **Stock Selection** | Sector lifecycle + Fundamentals | Limit-up + Emotion + Capital | Technical pattern + Event driven |
| **Position Count** | 5-8 stocks | ≤3 stocks | 5-10 stocks |
| **Capital Allocation** | 50% | 20-30% | 20-30% |
| **Stop Loss** | ATR Adaptive / Fixed -10% | Fixed -7% / Moving -5% | Technical level -5% to -8% |
| **Take Profit** | 4-tier (15/25/40/60%) | 3-tier (5/10/20%) | Target price / Moving stop |
| **Core Capability** | Sector judgment + Financial verification | Emotion sensing + Capital tracking | Technical recognition + Event capture |

## Quick Start

### Core Position Strategy
```python
from core-position-strategy.core-position-strategy.skills.scripts.core_position_pipeline import CorePositionPipeline

pipeline = CorePositionPipeline(total_capital=1000000.0, core_ratio=0.50)
result = pipeline.run_full_pipeline(...)
```

### Hot Spot Strategy
```python
from hot-spot-strategy.hot-spot-strategy.skills.scripts.hot_spot_pipeline import HotSpotPipeline

pipeline = HotSpotPipeline(total_capital=1000000.0)
recommendations = pipeline.generate_recommendations(stocks_data)
```

### Band Position Strategy
Each band strategy runs independently, see individual README files.

## Data Flow

```
Market Data → shared-components/_shared/ → Strategy Modules
                                    ↓
                           Trading Signals → shared-components/my_holdings/
                                    ↓
                           Recommendations → shared-components/recommendations/
```

## Disclaimer

For research and educational purposes only. Not investment advice. Stock market carries risks.

## Changelog

### v2.0.0 (2025-06-14)
- ✅ Restructured directories by three strategies
- ✅ Added Core Position Strategy V3.0
- ✅ Unified shared components management
- ✅ Updated all strategy documentation
- ✅ Renamed directories to English
- ✅ Cleaned up cache files

### v1.0.0
- ✅ Hot Spot Strategy 4-system implementation
- ✅ Band Position multi-strategy implementation
- ✅ Basic holdings and recommendation system
