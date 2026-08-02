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
from config import STOCK_GRADE, GRADE_CONFIG

#from alert_sender import AlertSender

for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        del os.environ[k]


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
        #self.alert_sender = AlertSender()
        
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
                        
                         # 兼容旧数据：缺失字段用默认值
                        last_add_date = item.get('last_add_date')
                        if last_add_date and isinstance(last_add_date, str):
                            last_add_date = datetime.strptime(last_add_date, '%Y-%m-%d').strftime('%Y-%m-%d')
                        else:
                            last_add_date = datetime.now().strftime('%Y-%m-%d')

                        init_shares = item.get('init_shares', item['shares'])    
                        if init_shares and isinstance(init_shares, (int, float)):
                            init_shares = int(init_shares)
                        else:
                            init_shares = item['shares']

                        real_cost = item.get('real_cost', item['real_cost'])    
                        if real_cost and isinstance(real_cost, (int, float)):
                            real_cost = int(real_cost)
                        else:
                            real_cost = item['cost']

                        holding = Holding(
                            code=item['code'],
                            name=item['name'],
                            cost=item['cost'],
                            real_cost=item['real_cost'],
                            shares=item['shares'],
                            init_shares=init_shares,
                            current_price=item.get('current_price', item['cost']),
                            highest_price=item.get('highest_price', item['cost']),
                            entry_date=entry_date,
                            strategy_name=item.get('strategy_name', 'unknown'),
                            score=item.get('score', 0),
                            #tech_indicators=item.get('tech_indicators', None),
                            stop_level_hit=item.get('stop_level_hit', [False, False, False]),
                            stop_lose_hit=item.get('stop_lose_hit', [False, False, False, False]),
                            add_count= item.get('add_count', 0),
                            last_add_date =  last_add_date
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
                'real_cost': holding.real_cost,
                'shares': holding.shares,
                'init_shares': holding.init_shares,
                'current_price': holding.current_price,
                'highest_price': holding.highest_price,
                'entry_date': holding.entry_date,
                'strategy_name': holding.strategy_name,
                'score': holding.score,
                'stop_level_hit': holding.stop_level_hit,
                'stop_lose_hit': holding.stop_lose_hit,
                'add_count': holding.add_count,
                'last_add_date': holding.last_add_date
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
                atr_stop = holding.real_cost - 2 *  holding.tech_indicators.atr14  # 入场价 - 2倍ATR
                art_stop_half = holding.real_cost - 2 *  holding.tech_indicators.atr14 * 0.65  # 半止损位
                print("atr_stop: ", atr_stop, ", art_stop_half: ", art_stop_half) 


                 # 更新最高价
                if current_data.price > holding.highest_price:
                    holding.highest_price = current_data.price
                    print(f"📈 {holding.name} 创新高: {holding.highest_price:.2f}")

                print(f"更新持仓: {holding.name} 价格:{holding.current_price:.2f} 评分:{holding.score:.1f}")

                # 更新真实的cost
                grade = STOCK_GRADE.get(holding.code, "L3_题材跟风")
                cfg = GRADE_CONFIG[grade]
                # 动态止盈目标
                p1 = round(holding.cost * (1 + cfg["profit_targets"][0] ), 2)
                p2 = round(holding.cost * (1 + cfg["profit_targets"][1] ), 2)
                p3 = round(holding.cost * (1 + cfg["profit_targets"][2] ), 2)
                real_cost = holding.cost
                if  holding.current_price > p1:  #  如果重新达到第一止盈点，art相关置为false,重新开始应对止损
                    real_cost = p1
                    holding.stop_lose_hit[2] = False
                    holding.stop_lose_hit[3] = False
                if  holding.current_price > p2:
                    real_cost = p2
                if  holding.current_price > p3:
                    real_cost = p3 
                holding.real_cost = real_cost
                print("real_cost: ", real_cost, ", init_cost: ", holding.cost)
    
    def afternoon_session(self):
        """尾盘会话(14:50)"""
        print(f"\n{'='*50}")
        print(f"尾盘策略分析 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*50}")
        
        # 1. 更新价格
        self.update_holdings_price()
        
        # 2. 保存数据
        self.save_holdings()
        self.save_cash_balance()
    
    
    
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
                existing.add_count += 1
                existing.last_add_date = datetime.now().strftime('%Y-%m-%d')
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
                    real_cost=price,
                    init_shares=shares,
                    shares=shares,
                    current_price=current_data.price if result else price,
                    highest_price=price,
                    entry_date=datetime.now().strftime('%Y-%m-%d'),
                    strategy_name=strategy_name,
                    score=0,
                    stop_level_hit=[False, False, False],
                    stop_lose_hit=[False, False, False, False],
                    add_count=0,
                    last_add_date=datetime.now().strftime('%Y-%m-%d')

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
            if price >= p2 and not existing.stop_level_hit[1]:
                existing.stop_level_hit[1] = True  # 标记已触及第二档止盈
                print(f"达到中档止盈目标: {price:.2f} >= {p2:.2f}")
            if price >= p1 and not existing.stop_level_hit[0] :
                existing.stop_level_hit[0] = True  # 标记已触及第一档止盈
                print(f"达到最低止盈目标: {price:.2f} >= {p1:.2f}")

            ## ====== 止损目标 ===== ###
           


            print("技术指标:", existing.tech_indicators)
            # if "RSI" in existing.strategy_name:
                # 当前价格跌破成本的6%达到第一档止损
            # print("亏损6%止损目标: ", existing.cost * 0.06, "亏损8%止损目标: ", existing.cost * 0.08)
            # if price <= existing.cost * 0.94 and not existing.stop_lose_hit[2]:
            #     existing.stop_lose_hit[2] = True  # 标记已触及第三档止损
            #     print(f"触及成本6%止损: {price:.2f} <= {existing.cost * 0.94:.2f}")
            # if price <= existing.cost * 0.92 and not existing.stop_lose_hit[3]:                  
            #     existing.stop_lose_hit[3] = True  # 标记已触及第四档止损
            #     print(f"触及成本8%止损: {price:.2f} <= {existing.cost * 0.92:.2f}")
            atr_stop = existing.real_cost - 2 *  existing.tech_indicators.atr14  # 入场价 - 2倍ATR
            art_stop_half = existing.real_cost - 2 *  existing.tech_indicators.atr14 * 0.65  # 半止损位

            if price <= art_stop_half and not existing.stop_lose_hit[2]:
                existing.stop_lose_hit[2] = True  # 标记已触及第三档止损
                print(f"触及成本art14止损50%: {price:.2f} <= {art_stop_half:.2f}")
            if price <= atr_stop and not existing.stop_lose_hit[3]:                  
                existing.stop_lose_hit[3] = True  # 标记已触及第四档止损
                print(f"触及成本art14止损100%: {price:.2f} <= {atr_stop:.2f}")


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
        schedule.every().day.at("09:15").do(self.afternoon_session)
        schedule.every().day.at("14:50").do(self.afternoon_session)
        
        print("定时任务已设置:")
        print("  - 09:15 早盘策略分析")
        print("  - 14:50 尾盘策略分析")
        print("="*50)
        
        # 立即执行一次分析
        now = datetime.now()
        if now.hour < 9 or (now.hour == 9 and now.minute < 15):
            self.afternoon_session()
            print("等待9:15执行早盘分析...")
        elif now.hour < 14 or (now.hour == 14 and now.minute < 55):
            self.afternoon_session()
        else:           
            print("当前时间已晚于尾盘,等待明日执行")
            self.afternoon_session()


if __name__ == "__main__":
    holdings_path = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json"
    
    if not os.path.exists(holdings_path):
        print("请修改 holdings.json 中的持仓信息,然后重新运行")
    else:
        strategy = StockTradingStrategy()
        strategy.run()
       #strategy.execute_trade(code="002436", action="sell", shares=900, price=138.20, strategy_name="突破新高")