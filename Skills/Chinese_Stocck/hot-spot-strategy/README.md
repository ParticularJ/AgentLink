# Hot Spot Strategy (热点仓策略)

Short-term trading strategy system capturing A-share emotional premium and capital momentum, holding period 3-8 days, capital allocation 20-30%.

## Strategy Overview

| Dimension | Specification |
|:---|:---|
| **Investment Horizon** | Daily/Weekly (3-8 days) |
| **Capital Allocation** | 20-30% of total capital |
| **Position Count** | ≤3 stocks |
| **Max Single Position** | ≤30% of hot spot capital |
| **Stop Loss** | Fixed -7% / ATR Dynamic / Moving -5% |
| **Take Profit** | 3-tier (5%/10%/20%) |

## Strategy Flow

### Phase 1: Market Scanning (Daily)

```
Market Environment Check
    ↓ (Strong/Oscillating → Proceed; Weak → Halt)
Sector Heat Ranking
    ↓ (Top sectors by volume/price change)
Stock Universe Filtering
    ↓ (Limit up stocks, hot sector leaders, new stocks)
```

### Phase 2: Strategy Scoring

```
Strategy 1: First Limit-Up
    - Time(30%) + Order Quality(25%) + Sector Effect(25%) + Turnover(20%)
    - Threshold: ≥75 points

Strategy 2: Limit-Up Retrace
    - Retrace Pct(25%) + Days(20%) + Volume Shrink(25%) + Stabilize(30%)
    - Threshold: ≥65 points

Strategy 3: Sector Leader
    - Lead(25%) + Strength(15%) + Heat(20%) + Drive(15%) + Turnover(15%) + Cap(10%)
    - Threshold: ≥70 points

Strategy 4: New Stock (T+0)
    - Industry(30%) + Turnover(25%) + Close(25%) + Valuation(20%)
    - Threshold: ≥80 points
```

### Phase 3: Cross-Validation & Ranking

```
Multi-Strategy Scoring
    ↓
Cross-Validation Bonus
    ↓ (Same stock in multiple strategies)
Risk Filtering
    ↓ (Veto conditions)
Final Ranking
    ↓
Top 3 Recommendations
```

### Phase 4: Execution & Monitoring

```
Buy Execution
    ↓
Intraday Monitoring (Real-time)
    - Price/Volume/MA5/ATR/Order book
Closing Monitoring (Daily)
    - Position P&L/Stop loss/Take profit/Add position
Special Signal Recognition
    - Explosive rise/Drop limit/Volume anomaly
```

## Directory Structure

```
hot-spot-strategy/
├── README.md                          # This file
├── hot-spot-strategy/                 # 4-strategy system
│   ├── SKILL.md                       # Skill definition
│   ├── README.md                      # Strategy details
│   ├── requirements.txt               # Python dependencies
│   ├── config/                        # Configuration
│   │   ├── strategy_config.yaml       # Strategy parameters
│   │   ├── scoring_weights.yaml       # Scoring weights
│   │   └── risk_rules.yaml           # Risk rules
│   ├── agents/                        # Agent config
│   │   └── hot-spot-agent.yaml
│   ├── crons/                         # Scheduled tasks
│   │   └── hot-spot-crons.yaml
│   └── skills/scripts/                # Strategy scripts
│       ├── models.py                  # Data models
│       ├── strategy_scorer.py         # 4-strategy scorer
│       ├── portfolio_manager.py       # Portfolio manager
│       ├── risk_manager.py            # Risk manager
│       ├── hot_spot_pipeline.py       # Main pipeline
│       └── test_hot_spot.py          # Unit tests
├── limit-up-retrace-strategy/         # Limit-up retrace
│   ├── SKILL.md
│   ├── README.md
│   ├── requirements.txt
│   ├── config/
│   └── skills/scripts/
│       ├── limit_up_retrace_scanner.py
│       └── limit_up_retrace_strategy_analyzer.py
└── limit-up-analysis/                 # Limit-up analysis
    ├── SKILL.md
    ├── README.md
    ├── config/
    └── skills/scripts/
```

## Four Strategy Systems

### Strategy 1: First Limit-Up
- **Target**: Capture breakthrough from quantitative to qualitative change
- **Dimensions**: Time(30%) + Order Quality(25%) + Sector Effect(25%) + Turnover(20%)
- **Threshold**: ≥75 points
- **Holding**: 3-5 days

### Strategy 2: Limit-Up Retrace
- **Target**: Technical rebound after profit-taking
- **Dimensions**: Retrace Pct(25%) + Days(20%) + Volume Shrink(25%) + Stabilize(30%)
- **Threshold**: ≥65 points
- **Holding**: 5-7 days, can add once

### Strategy 3: Sector Leader
- **Target**: Trend opportunity of sector leaders
- **Dimensions**: Lead(25%) + Strength(15%) + Heat(20%) + Drive(15%) + Turnover(15%) + Cap(10%)
- **Threshold**: ≥70 points
- **Holding**: 5-8 days, can add once

### Strategy 4: New Stock (T+0)
- **Target**: First-day new stock opportunity
- **Dimensions**: Industry(30%) + Turnover(25%) + Close(25%) + Valuation(20%)
- **Threshold**: ≥80 points
- **Holding**: Max 3 days

## Risk Control

### Stop Loss Rules
- **Fixed Stop**: Cost -7%
- **ATR Dynamic**: Entry -2×ATR(14)
- **Moving Stop**: -5% from highest (after >5% profit)
- **Time Stop**: 5 days without profit (3 for new stocks)
- **MA Stop**: Close below MA5

### Take Profit Rules
- **Normal Hot Stocks**: 5% sell 1/3, 10% sell 1/3, >20% remaining保本
- **Leader Stocks**: 5%/10%/20%/30% 4-tier分批
- **New Stocks**: 5-10% sell 1/2, >10% gradual清仓

### Circuit Breaker
- **Level 1**: Daily loss 1.5%, prohibit new positions
- **Level 2**: Daily loss 2%, force liquidation, stop trading
- **Continuous**: 2 consecutive Level 2, pause 3 days

## Usage

```python
from hot-spot-strategy.skills.scripts.hot_spot_pipeline import HotSpotPipeline
from hot-spot-strategy.skills.scripts.models import StrategyType

# Create pipeline
pipeline = HotSpotPipeline(total_capital=1000000.0)

# Prepare data
stocks_data = {
    StrategyType.FIRST_LIMIT_UP: [...],
    StrategyType.LIMIT_UP_RETRACE: [...],
    StrategyType.SECTOR_LEADER: [...],
    StrategyType.NEW_STOCK: [...],
}

# Generate recommendations
recommendations = pipeline.generate_recommendations(stocks_data)

# Execute buy
for rec in recommendations:
    position = pipeline.execute_buy(rec, entry_price=12.50)

# Monitor positions
signals = pipeline.monitor_positions(market_data)

# Execute sell
for signal in signals:
    if signal.action == "SELL":
        pipeline.execute_sell(signal)

# Daily review
summary = pipeline.daily_review()
```

## Disclaimer

For research and educational purposes only. Not investment advice. Stock market carries risks.
