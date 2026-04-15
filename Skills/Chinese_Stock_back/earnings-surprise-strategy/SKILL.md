# Earnings Surprise Strategy

name: "earnings-surprise-strategy"
version: "v1.0.0"
description: "财报超预期策略 - 基于财报超预期的基本面量化交易策略"

# 策略配置
strategy:
  win_rate: 0.70
  holding_period: "2-4周"
  max_drawdown: 0.10
  
# 评分维度
scoring_dimensions:
  - earnings_surprise      # 业绩超预期程度 (30%)
  - growth_quality         # 增长质量 (25%)
  - market_reaction        # 市场反应 (25%)
  - valuation_safety       # 估值安全边际 (20%)

# 数据源配置
data_sources:
  primary: "akshare"
  fallback: "baostock"
  
# 运行配置
runtime:
  timeout_seconds: 300
  memory_limit: "512MB"
