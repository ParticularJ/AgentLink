import schedule
import time
import os
import json
import shutil
from datetime import datetime
from typing import List

from models import Holding, StockScore
from market_analyzer import MarketAnalyzer
from stock_analyzer import StockAnalyzer
from risk_controller import RiskController
from alert_sender import AlertSender

for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        del os.environ[k]


# ====================== 【止盈策略核心：静态龙头定级】======================
STOCK_GRADE = {
    # ==================== L1 行业绝对龙头 ====================
    # 先进封装（全球第三、国内第一）
    "600584": "L1_行业龙头",  # 长电科技
    
    # PCB覆铜板（国内绝对龙头）
    "600183": "L1_行业龙头",  # 生益科技

    # 创新药（国内绝对龙头）
    "600276": "L1_行业龙头",  # 恒瑞医药

    # 油运（远东MR成品油轮龙头）
    "601975": "L1_行业龙头",  # 招商南油

    # 特高压功率半导体（晶闸管国内市占65%+）
    "300831": "L1_行业龙头",  # 派瑞股份

    # 电子陶瓷/MLCC（光纤陶瓷插芯全球第一）
    "300408": "L1_行业龙头",  # 三环集团


    # ==================== L2 细分龙头/强二线 ====================
    # 军工/高压连接器（国内连接器龙头）
    "002179": "L2_细分龙头",  # 中航光电

    # 存储封测（DRAM国内第一梯队）
    "000021": "L2_细分龙头",  # 深科技

    # AIoT SoC芯片（国内第二，扫地机器人主控第一）
    "603893": "L2_细分龙头",  # 瑞芯微


    # ==================== L3 题材跟风/普通标的 ====================
    # 人形机器人/伺服（二线，无绝对龙头地位）
    "603728": "L3_题材跟风",  # 鸣志电器
}

GRADE_CONFIG = {
    "L1_行业龙头": {
        "profit_targets": [0.18, 0.40, 0.50],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.08,      # 8%止损（中档）
        "trailing_stop": 0.06,   # 6%回撤止盈
        "position_pct": 0.20,    # 单票上限20%
        "time_stop": {
            (10, 15): 0.03,
            (15, 20): 0.07,
            (20, 25): 0.12,
            (25, 999): 0.15,
        }
    },
    "L2_细分龙头": {
        "profit_targets": [0.12, 0.22, 0.38],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.07,      # 7%止损（中档）
        "trailing_stop": 0.05,   # 5%回撤止盈
        "position_pct": 0.15,    # 单票上限15%
         "time_stop": {
            (8, 12): 0.02,
            (12, 16): 0.05,
            (16, 20): 0.08,
            (20, 999): 0.10,
        }
    },
    "L3_题材跟风": {
        "profit_targets": [0.10, 0.18, 0.30],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.06,      # 6%止损（中档）
        "trailing_stop": 0.04,   # 4%回撤止盈
        "position_pct": 0.10,    # 单票上限10%
        "time_stop": {
            (5, 8): 0.01,
            (8, 12): 0.03,
            (12, 15): 0.05,
            (15, 999): 0.07,
        }
    },
}




class StockTradingStrategy:
    """股票交易策略主程序"""
    
    def __init__(self, holdings_file: str = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json",
                 cash_file: str = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/cash_balance.json",
                 initial_capital: float = 1000000.0):
        print("初始化股票交易策略系统...")
        self.holdings_file = holdings_file
        self.cash_file = cash_file
        self.initial_capital = initial_capital
        self.available_cash = initial_capital
        self.ma5 = 0
        self.ma10 = 0
        self.holdings: List[Holding] = []
        
        self.market_analyzer = MarketAnalyzer()
        self.stock_analyzer = StockAnalyzer()
        self.risk_controller = RiskController()
        self.alert_sender = AlertSender()
        
        self.load_data()
        
    def load_data(self):
        """加载所有数据"""
        print("正在加载数据...")
        self.load_holdings()
        self.load_cash_balance()
        print(f"系统初始化完成")
        print(f"初始资金: {self.initial_capital:,.2f}")
        print(f"可用现金: {self.available_cash:,.2f}")
        print(f"持仓数量: {len(self.holdings)}")
        
    def load_holdings(self):
        """加载持仓文件"""
        try:
            if os.path.exists(self.holdings_file):
                with open(self.holdings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print("加载持仓数据: ", data)
                    self.holdings = []
                    for item in data:                         
                        # 兼容旧数据：缺失字段用默认值
                        entry_date = item.get('entry_date')
                        if entry_date and isinstance(entry_date, str):
                            entry_date = datetime.strptime(entry_date, '%Y-%m-%d').strftime('%Y-%m-%d')
                        else:
                            entry_date = datetime.now().strftime('%Y-%m-%d')
                        

                        init_shares = item.get('init_shares', item['shares'])    
                        if init_shares and isinstance(init_shares, (int, float)):
                            init_shares = int(init_shares)
                        else:
                            init_shares = item['shares']


                        holding = Holding(
                            code=item['code'],
                            name=item['name'],
                            cost=item['cost'],
                            shares=item['shares'],
                            init_shares=init_shares,
                            current_price=item.get('current_price', item['cost']),
                            highest_price=item.get('highest_price', item['cost']),
                            entry_date=entry_date,
                            strategy_name=item.get('strategy_name', 'unknown'),
                            score=item.get('score', 0),
                            #tech_indicators=item.get('tech_indicators', None),
                            stop_level_hit=item.get('stop_level_hit', [False, False, False]),
                            stop_lose_hit=item.get('stop_lose_hit', [False, False, False, False])
                        )
                        self.holdings.append(holding)
                print(f"加载持仓成功,共{len(self.holdings)}只股票")
            else:
                print("未找到持仓文件,创建空持仓")
                self.save_holdings()
        except Exception as e:
            print(f"加载持仓失败: {e}")
    
    def load_cash_balance(self):
        """加载现金余额"""
        try:
            if os.path.exists(self.cash_file):
             
                with open(self.cash_file, 'r', encoding='utf-8') as f:
                    cash_data = json.load(f)
                    print(cash_data)
                    
                    self.available_cash = cash_data.get('available_cash')
                    self.initial_capital = cash_data.get('initial_capital')
                   
                    # print("tset: ", self.available_cash )
                    
            else:
                self.save_cash_balance()
        except Exception as e:
            print(f"加载现金余额失败: {e}")
   
    def backup_file(self, file_path: str):
        """备份已存在的 JSON 文件"""
        if os.path.exists(file_path):
            backup_dir = os.path.join(os.path.dirname(file_path), "backup")
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = os.path.join(backup_dir, f"{timestamp}_{os.path.basename(file_path)}")
            try:
                shutil.copy2(file_path, backup_path)
                print(f"已备份文件: {backup_path}")
            except Exception as e:
                print(f"备份文件失败: {e}")


    def save_cash_balance(self):

        self.backup_file(self.cash_file)  # 备份现金余额文件
        """保存现金余额"""
        cash_data = {
            'initial_capital': self.initial_capital,
            'available_cash': self.available_cash,
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(self.cash_file, 'w', encoding='utf-8') as f:
            json.dump(cash_data, f, ensure_ascii=False, indent=2)

    def save_holdings(self):
        self.backup_file(self.holdings_file)  # 备份持仓文件
        """保存持仓文件"""
        data = []
        for holding in self.holdings:
            data.append({
                'code': holding.code,
                'name': holding.name,
                'cost': holding.cost,
                'shares': holding.shares,
                'init_shares': holding.init_shares,
                'current_price': holding.current_price,
                'highest_price': holding.highest_price,
                'entry_date': holding.entry_date,
                'strategy_name': holding.strategy_name,
                'score': holding.score,
                'stop_level_hit': holding.stop_level_hit,
                'stop_lose_hit': holding.stop_lose_hit
            })
        print('保存持仓数据: ', data)
        #return
        with open(self.holdings_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def update_holdings_price(self):
        """更新持仓价格和评分"""
        for holding in self.holdings:
            result = self.stock_analyzer.fetch_stock_data(holding.code)
            if result:
                df_history, current_data = result
                tech = self.stock_analyzer.calculate_technical_indicators(df_history)
                score = self.stock_analyzer.calculate_comprehensive_score(
                    holding.code, current_data, tech
                )
                
                holding.current_price = current_data.price
                holding.score = score.total_score
                holding.tech_indicators = tech
                print(" holding.tech_indicators: ", holding.tech_indicators)
                 # 更新最高价
                if current_data.price > holding.highest_price:
                    holding.highest_price = current_data.price
                    print(f"📈 {holding.name} 创新高: {holding.highest_price:.2f}")

                print(f"更新持仓: {holding.name} 价格:{holding.current_price:.2f} 评分:{holding.score:.1f}")
    
    def check_risk_alerts(self) -> List:
        """检查所有持仓的风控预警"""
        alerts = []
        
        for holding in self.holdings:
            result = self.stock_analyzer.fetch_stock_data(holding.code)
            if result:
                df_history, current_data = result
                tech = self.stock_analyzer.calculate_technical_indicators(df_history)
                
                alert = self.risk_controller.check_ma_breakdown(
                    holding, current_data.price, tech, current_data.volume_ratio
                )
                
                if alert:
                    alerts.append(alert)
                    # 发送预警
                    self.alert_sender.send_alert(alert)
                    print(f"发送预警: {holding.name}")
        
        return alerts
    
    def calculate_position(self) -> dict:
        """计算准确的仓位信息"""
        # 计算持仓总市值
        position_value = sum(h.shares * h.current_price for h in self.holdings)
        
        # 总资产 = 持仓市值 + 可用现金
        total_asset = position_value + self.available_cash
        
        # 当前仓位比例
        current_position_ratio = position_value / total_asset if total_asset > 0 else 0
        
        # 已实现盈亏
        realized_pnl = total_asset - self.initial_capital
        
        # 浮动盈亏
        floating_pnl = sum(h.shares * (h.current_price - h.cost) for h in self.holdings)
        
        return {
            "position_value": position_value,
            "available_cash": self.available_cash,
            "total_asset": total_asset,
            "position_ratio": current_position_ratio,
            "realized_pnl": realized_pnl,
            "floating_pnl": floating_pnl,
            "total_pnl": realized_pnl + floating_pnl
        }

    def morning_session(self):
        """早盘会话(09:15)"""
        print(f"\n{'='*50}")
        print(f"早盘策略分析 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*50}")
        
        # 1. 更新持仓数据
        self.update_holdings_price()
        
        # 2. 计算准确的仓位信息
        position_info = self.calculate_position()
        
        # 3. 大盘分析并计算仓位建议
        position_advice = self.market_analyzer.calculate_position_limit()
        position_advice.current_position = position_info["position_ratio"]
        position_advice.available_position = max(0, position_advice.suggested_position - position_info["position_ratio"])
        
        # 4. 发送仓位建议（使用正确的方法签名）
        self.alert_sender.send_position_advice(
            advice=position_advice,
            current_position=position_info["position_ratio"],
            position_value=position_info["position_value"],
            total_asset=position_info["total_asset"],
            floating_pnl=position_info["floating_pnl"]
        )
        
        print(f"总资产: {position_info['total_asset']:,.2f}")
        print(f"当前仓位: {position_info['position_ratio']*100:.1f}%")
        print(f"建议仓位: {position_advice.suggested_position*100:.0f}%")
        
        # 5. 检查风控
        alerts = self.check_risk_alerts()
        
        # 6. 保存数据
        self.save_holdings()
        self.save_cash_balance()
    
    def afternoon_session(self):
        """尾盘会话(14:50)"""
        print(f"\n{'='*50}")
        print(f"尾盘策略分析 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*50}")
        
        # 1. 更新价格
        self.update_holdings_price()
        #return
        # 2. 计算仓位信息
       # position_info = self.calculate_position()
        
        # 3. 确认均线跌破
        # print("尾盘确认均线跌破信号...")
        #alerts = self.check_risk_alerts()
        
        # # 4. 再次输出仓位建议
        # position_advice = self.market_analyzer.calculate_position_limit()
        # position_advice.current_position = position_info["position_ratio"]
        # position_advice.available_position = max(0, position_advice.suggested_position - position_info["position_ratio"])
        
        # # 发送尾盘仓位建议
        # self.alert_sender.send_position_advice(
        #     advice=position_advice,
        #     current_position=position_info["position_ratio"],
        #     position_value=position_info["position_value"],
        #     total_asset=position_info["total_asset"],
        #     floating_pnl=position_info["floating_pnl"]
        # )
        
        # # 5. 生成次日计划
        # plan = self.generate_next_day_plan(position_advice, alerts, position_info)
        # self.alert_sender.send_custom_message(plan, "次日交易计划")
        # print(plan)
        
        # 6. 保存数据
        self.save_holdings()
        self.save_cash_balance()
    
    def generate_next_day_plan(self, position_advice, alerts, position_info) -> str:
        """生成次日交易计划"""
        plan = f"""
【次日交易计划】{datetime.now().strftime('%Y-%m-%d')}

📊 资产状况:
   ├─ 总资产: {position_info['total_asset']:,.2f}
   ├─ 持仓市值: {position_info['position_value']:,.2f}
   ├─ 浮动盈亏: {position_info['floating_pnl']:+,.2f}
   └─ 总盈亏: {position_info['total_pnl']:+,.2f}

📈 仓位状况:
   ├─ 大盘判断: {position_advice.market_state.value}
   ├─ 当前仓位: {position_info['position_ratio']*100:.1f}%
   └─ 建议仓位: {position_advice.suggested_position*100:.0f}%

"""
        if alerts:
            plan += "⚠️ 风险提示:\n"
            for alert in alerts:
                plan += f"  - {alert.name}: {alert.message}, 建议{alert.action}\n"
        else:
            plan += "✅ 当前持仓均处于安全区域\n"
        
        plan += f"""
📌 操作要点:
  1. 严格遵循仓位上限,不超{position_advice.suggested_position*100:.0f}%
  2. 重点关注跌破均线的个股
  3. 知行合一,及时执行风控措施

--- 策略自动生成 ---
"""
        return plan
    
    
    def execute_trade(self, code: str, action: str, shares: int, price: float, strategy_name: str = "") -> bool:
        
        # 1. 更新价格
        self.update_holdings_price()
        
        """执行交易"""
        if action == "buy":
            cost = shares * price
            if cost > self.available_cash:
                print(f"资金不足: 需要{cost:,.2f}, 可用{self.available_cash:,.2f}")
                return False
            
            self.available_cash -= cost
            
            existing = next((h for h in self.holdings if h.code == code), None)
            if existing:
                total_cost = existing.cost * existing.shares + cost
                total_shares = existing.shares + shares
                existing.cost = total_cost / total_shares
                existing.shares = total_shares
                existing.init_shares = total_shares
                print(f"加仓成功: {code} +{shares}股")
            else:
                # 获取股票名称
                name = code
                result = self.stock_analyzer.fetch_stock_data(code)
                if result:
                    _, current_data = result
                    name = current_data.name
                
                new_holding = Holding(
                    code=code,
                    name=name,
                    cost=price,
                    init_shares=shares,
                    shares=shares,
                    current_price=current_data.price if result else price,
                    highest_price=price,
                    entry_date=datetime.now().strftime('%Y%m%d'),
                    strategy_name=strategy_name,
                    score=0,
                    stop_level_hit=[False, False, False],
                    stop_lose_hit=[False, False, False, False]

                )
                print("new_holding: ", new_holding)
                self.holdings.append(new_holding)
                print(f"建仓成功: {name}({code}) {shares}股 # {price:.2f} - 策略: {strategy_name}")
            
        elif action == "sell":
            existing = next((h for h in self.holdings if h.code == code), None)
            if not existing or existing.shares < shares:
                print(f"持仓不足: 需要卖出{shares}股, 持有{existing.shares if existing else 0}股")
                return False
            
            proceeds = shares * price
            self.available_cash += proceeds
            
            existing.shares -= shares
            if existing.shares == 0:
                self.holdings.remove(existing)
            
            grade = STOCK_GRADE.get(code, "L3_题材跟风")
            cfg = GRADE_CONFIG[grade]
            # 动态止盈目标
            p1 = round(existing.cost * (1 + cfg["profit_targets"][0] ), 2)
            p2 = round(existing.cost * (1 + cfg["profit_targets"][1] ), 2)
            p3 = round(existing.cost * (1 + cfg["profit_targets"][2] ), 2)
            print("止盈目标: ", p1, p2, p3)
            if price >= p3 and not existing.stop_level_hit[2]:
                print(f"达到最高止盈目标: {price:.2f} >= {p3:.2f}")
                existing.stop_level_hit[2] = True  # 标记已触及第三档止盈
            elif price >= p2 and not existing.stop_level_hit[1]:
                existing.stop_level_hit[1] = True  # 标记已触及第二档止盈
                print(f"达到中档止盈目标: {price:.2f} >= {p2:.2f}")
            elif price >= p1 and not existing.stop_level_hit[0] :
                existing.stop_level_hit[0] = True  # 标记已触及第一档止盈
                print(f"达到最低止盈目标: {price:.2f} >= {p1:.2f}")

            ## ====== 止损目标 ===== ###
            print("技术指标:", existing.tech_indicators)
            if "RSI" in existing.strategy_name:
                # 当前价格跌破成本的6%达到第一档止损
                print("亏损6%止损目标: ", existing.cost * 0.06, "亏损8%止损目标: ", existing.cost * 0.08)
                if price <= existing.cost * 0.94 and not existing.stop_lose_hit[2]:
                    existing.stop_lose_hit[2] = True  # 标记已触及第三档止损
                    print(f"触及成本6%止损: {price:.2f} <= {existing.cost * 0.94:.2f}")
                if price <= existing.cost * 0.92 and not existing.stop_lose_hit[3]:                  
                    existing.stop_lose_hit[3] = True  # 标记已触及第四档止损
                    print(f"触及成本8%止损: {price:.2f} <= {existing.cost * 0.92:.2f}")

            if price <= existing.tech_indicators.ma5  and not existing.stop_lose_hit[0]:
                existing.stop_lose_hit[0] = True  # 标记已触及MA5止损
                print(f"触及MA5止损: {price:.2f} <= MA5 {existing.tech_indicators.ma5:.2f}")
            if price <= existing.tech_indicators.ma10 and not existing.stop_lose_hit[1]:
                existing.stop_lose_hit[1] = True  # 标记已触及MA10止损
                print(f"触及MA10止损: {price:.2f} <= MA10 {existing.tech_indicators.ma10:.2f}")

            print(f"卖出成功: {code} {shares}股 @ {price:.2f}")
            print("existing: ", existing)
        # 保存状态
        self.save_holdings()
        self.save_cash_balance()
        return True
    
    def run(self):
        """运行主程序"""
        print("股票策略系统启动...")
        print("="*50)
        
        # 设置定时任务
        schedule.every().day.at("09:15").do(self.morning_session)
        schedule.every().day.at("14:50").do(self.afternoon_session)
        
        print("定时任务已设置:")
        print("  - 09:15 早盘策略分析")
        print("  - 14:50 尾盘策略分析")
        print("="*50)
        
        # 立即执行一次分析
        now = datetime.now()
        if now.hour < 9 or (now.hour == 9 and now.minute < 15):
            print("等待9:15执行早盘分析...")
        elif now.hour < 14 or (now.hour == 14 and now.minute < 55):
            self.morning_session()
        else:           
            print("当前时间已晚于尾盘,等待明日执行")
            self.afternoon_session()

       #  self.morning_session()
        # 主循环
        # try:
        #     #while True:
        #         schedule.run_pending()
        #         time.sleep(1)
        # except KeyboardInterrupt:
        #     print("\n系统已停止")
        #     self.save_holdings()
        #     self.save_cash_balance()


if __name__ == "__main__":
    holdings_path = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json"
    
    if not os.path.exists(holdings_path):
        print("请修改 holdings.json 中的持仓信息,然后重新运行")
    else:
        strategy = StockTradingStrategy()
        strategy.run()
        #strategy.execute_trade(code="603986", action="buy", shares=300, price=33, strategy_name="突破新高")