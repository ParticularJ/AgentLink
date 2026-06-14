"""
股票交易执行器
封装 execute_trade 函数，提供简洁的买卖接口
路径: Medium-termHoldingStrategy/skills/trade_executor.py
"""

import sys
import os
import subprocess
from datetime import datetime

# 路径配置
SKILLS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(SKILLS_DIR, "scripts")
BASE_DIR = os.path.dirname(os.path.dirname(SKILLS_DIR))
sys.path.insert(0, SCRIPTS_DIR)

# 持仓和现金文件路径
HOLDINGS_FILE = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json"
CASH_FILE = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/cash_balance.json"

# 初始资金
INITIAL_CAPITAL = 1000000.0


def get_strategy():
    """获取策略实例（延迟导入，避免循环依赖）"""
    from main import StockTradingStrategy
    return StockTradingStrategy(
        holdings_file=HOLDINGS_FILE,
        cash_file=CASH_FILE,
        initial_capital=INITIAL_CAPITAL
    )


def get_monitor_script() -> str:
    """根据当前时间选择对应的 monitor 脚本"""
    now = datetime.now()
    hour = now.hour
    
    # 早盘时段: 09:15 - 11:30
    if 9 <= hour < 12:
        return os.path.join(BASE_DIR, "run_morning_monitor.sh")
    # 尾盘时段: 13:00 - 15:00
    elif 13 <= hour < 15:
        return os.path.join(BASE_DIR, "run_evening_monitor.sh")
    # 其他时段默认早盘
    else:
        return os.path.join(BASE_DIR, "run_morning_monitor.sh")


def run_monitor():
    """运行持仓监控脚本"""
    script = get_monitor_script()
    try:
        result = subprocess.run(
            ["bash", script],
            capture_output=True,
            text=True,
            timeout=120
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e)
        }


def execute_trade(code: str, action: str, shares: int, price: float, reason: str = "") -> dict:
    """
    执行股票交易
    
    Args:
        code: 股票代码，如 "600105"
        action: "buy" 或 "sell"
        shares: 股数
        price: 成交价格
        reason: 交易原因（可选）
    
    Returns:
        dict: {
            "success": bool,
            "message": str,
            "holdings": list,  # 更新后的持仓
            "cash": float,     # 更新后的现金
            "monitor": dict     # monitor 执行结果
        }
    """
    if action not in ("buy", "sell"):
        return {"success": False, "message": f"不支持的交易动作: {action}"}
    
    try:
        strategy = get_strategy()
        result = strategy.execute_trade(code, action, shares, price, reason)
        
        # 交易成功后自动运行 monitor
        monitor_result = None
        if result:
            monitor_result = run_monitor()
        
        return {
            "success": result,
            "message": "交易成功" if result else "交易失败",
            "holdings": [
                {
                    "code": h.code,
                    "name": h.name,
                    "shares": h.shares,
                    "cost": h.cost,
                    "current_price": h.current_price
                }
                for h in strategy.holdings
            ],
            "cash": strategy.available_cash,
            "monitor": monitor_result
        }
    except Exception as e:
        return {"success": False, "message": f"执行异常: {str(e)}"}


def verify_environment() -> dict:
    """验证执行环境是否正常"""
    try:
        strategy = get_strategy()
        return {
            "ok": True,
            "holdings_count": len(strategy.holdings),
            "available_cash": strategy.available_cash,
            "holdings_file": HOLDINGS_FILE,
            "cash_file": CASH_FILE
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}