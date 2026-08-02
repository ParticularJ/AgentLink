#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心仓止损止盈系统 - PositionMonitor (V3.0同步版)
严格遵循《核心仓策略 V3.0》设计文档

功能：
- 5层止损：ATR自适应 / 固定止损 / 移动止损 / 均线止损 / 时间止损
- 4阶止盈：15%/25%/40%/60% 分阶段卖出 + 移动止盈
- 市场环境调整：牛市放宽30%，熊市收紧20%

适配波段仓 holdings.json 数据结构
"""
import os
import json
import sys
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from atr_calculator import calc_atr
from data_source import get_index_realtime
from config import STOCK_GRADE, GRADE_CONFIG


# ── 代理清除 ────────────────────────────────────────────
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try:
            del os.environ[k]
        except:
            pass

# ── 路径配置 ───────────────────────────────────────────
HOLDINGS_FILE = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json"
LOG_DIR = "/home/jarvis/.openclaw/logs/stock"
LOG_FILE = f"{LOG_DIR}/position_monitor.log"

# ── 数据源 ─────────────────────────────────────────────
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False


# ═══════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════

class MonitorSignalType(str, Enum):
    """监控信号类型"""
    STOP_LOSS = "STOP_LOSS"
    TIME_STOP = "TIME_STOP"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    ALERT = "ALERT"
    SECTOR_STOP = "SECTOR_STOP"
    PORTFOLIO_STOP = "PORTFOLIO_STOP"


class MonitorAction(str, Enum):
    """监控动作"""
    SELL = "SELL"
    REDUCE = "REDUCE"
    HOLD = "HOLD"
    BUY = "BUY"
    


class MarketStatus(str, Enum):
    """市场环境状态"""
    STRONG = "STRONG"      # 牛市
    WEAK = "WEAK"         # 熊市
    NEUTRAL = "NEUTRAL"   # 震荡市


@dataclass
class MonitorSignal:
    """监控信号"""
    stock_code: str
    signal_type: str
    signal_desc: str
    action: str
    suggested_ratio: float = 0.0
    price: float = 0.0
    urgency: str = "normal"  # urgent / normal / low
    # 附加数据
    profit_pct: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0


@dataclass
class PositionData:
    """
    标准化的持仓数据结构（从 holdings.json 转换）
    所有价格单位：元
    """
    code: str           # 6位股票代码
    name: str
    shares: int         # 当前持仓股数
    cost: float         # 平均成本价
    real_cost: float    # 根据动态浮赢后的价格
    current_price: float  # 当前价格
    highest_price: float  # 持仓期间最高价
    entry_date: str     # 入场日期 YYYY-MM-DD
    entry_atr: float    # 入场时ATR（14日）
    # 计算字段
    unrealized_pct: float = 0.0   # 浮盈%
    hold_days: int = 0           # 持仓天数
    drawdown_pct: float = 0.0    # 回撤%
    # 扩展字段（用于止盈）
    sold_records: List[dict] = field(default_factory=list)  # 历史卖出记录
    moving_stop_price: float = 0.0  # 移动止盈价位
    # 风险参数
    fixed_stop_loss_pct: float = 0.10   # 固定止损比例（默认-10%）
    trailing_stop_pct: float = 0.06     # 移动止损回撤比例（默认-6%）
    trailing_stop_triggered: bool = False  # 移动止损是否已触发
    stop_level_hit: List[bool] = field(default_factory=list)  # 止损层级触发状态
    stop_lose_hit: List[bool] = field(default_factory=list)  # 止损各档位是否触发，MA5,MA10, -6%, -8%

    @classmethod
    def from_holding(cls, h: dict, current_price: float = None) -> "PositionData":
        """从 holdings.json 的一条记录构建 PositionData"""
        cp = current_price or float(h.get('current_price', 0))
        cost = float(h['cost'])
        real_cost = float(h['real_cost'])
        hp = float(h.get('highest_price', cp))
        entry_str = h.get('entry_date', '')
        stop_level_hit = h.get('stop_level_hit', [False, False, False])
        stop_lose_hit = h.get('stop_lose_hit', [False, False, False, False])
        print(stop_level_hit)
        print(stop_lose_hit)

        # 计算浮盈和回撤
        unrealized_pct = (cp - cost) / cost * 100 if cost > 0 else 0
        drawdown_pct = (hp - cp) / hp * 100 if hp > 0 else 0
        
        # 计算持仓天数
        hold_days = 0
        if entry_str:
            try:
                entry_dt = datetime.strptime(entry_str, "%Y-%m-%d")
                hold_days = (datetime.now() - entry_dt).days
            except:
                pass
        
        return cls(
            code=h.get('code', ''),
            name=h.get('name', h.get('code', '')),
            shares=int(h.get('shares', 0)),
            cost=cost,
            real_cost= real_cost,
            current_price=cp,
            highest_price=hp,
            entry_date=entry_str,
            entry_atr=float(h.get('entry_atr', 0)),
            unrealized_pct=unrealized_pct,
            hold_days=hold_days,
            drawdown_pct=drawdown_pct,
            stop_level_hit=stop_level_hit,
            sold_records=h.get('sold_records', []),
            moving_stop_price=float(h.get('moving_stop_price', 0)),
            fixed_stop_loss_pct=float(h.get('fixed_stop_loss_pct', 0.10)),
            trailing_stop_pct=float(h.get('trailing_stop_pct', 0.06)),
            trailing_stop_triggered=h.get('trailing_stop_triggered', False),
            stop_lose_hit=stop_lose_hit
        )


@dataclass  
class MarketContext:
    """市场环境上下文"""
    status: MarketStatus = MarketStatus.NEUTRAL
    vix: float = 20.0
    sh300_trend: str = "neutral"  # up / down / neutral
    market_sentiment: str = "正常"  # 极端恐慌 / 恐慌 / 偏弱 / 正常

    @classmethod
    def get_market_sentiment(cls):
        idx_data = get_index_realtime()
        # 提取涨跌幅
        sh = idx_data["sh"]["chg_pct"]
        sz = idx_data["sz"]["chg_pct"]
        cy = idx_data["cy"]["chg_pct"]
        hs300 = idx_data["hs300"]["chg_pct"]
        zz500 = idx_data["zz500"]["chg_pct"]
        zz1000 = idx_data["zz1000"]["chg_pct"]
        kc50 = idx_data["kc50"]["chg_pct"]
        # 主流7指数，剔除独立北证bz50
        main_list = [sh, sz, cy, hs300, zz500, zz1000, kc50]

        cnt_red = sum(1 for x in main_list if x > 0)   # 收红指数数量
        cnt_green = sum(1 for x in main_list if x < 0) # 收绿指数数量
        cy_vs_sh = cy - sh  # 创业板相对上证强弱，判断小票弹性

        # ========== 1. 极端暴涨（全线大涨，小票爆发力极强） ==========
        all_strong_rise = all(x >= 1.5 for x in main_list)
        cond1 = cy >= 4.0 and hs300 >= 2.0 and zz1000 >= 2.0 and all_strong_rise
        cond2 = cy_vs_sh >= 2.5 and all(x > 1.0 for x in main_list)
        if cond1 or cond2:
            MarketContext.market_sentiment = "极端暴涨"
            return MarketContext.market_sentiment

        # ========== 2. 强势大涨（普涨，小票明显强于权重） ==========
        most_rise = cnt_red >= 6
        cond_a = cy >= 3.0 and hs300 >= 1.2 and zz500 >= 1.2 and zz1000 >= 1.2 and most_rise
        cond_b = (sz - sh) >= 1.5 and cnt_red >= 5
        cond_c = hs300 >= 2.0 and cnt_red >= 5
        if cond_a or cond_b or cond_c:
            MarketContext.market_sentiment = "强势大涨"
            return MarketContext.market_sentiment

        # ========== 3. 温和强势（小幅普涨，震荡偏多） ==========
        strong_cy = cy >= 2.5
        rise_cnt = sum(1 for x in main_list if x > 0)
        cond_x = 4 <= rise_cnt <= 6 and not strong_cy
        cond_y = (sz - sh) >= 0.8 and rise_cnt >= 4
        if cond_x or cond_y:
            MarketContext.market_sentiment = "温和强势"
            return MarketContext.market_sentiment

        # ========== 4. 极端恐慌（原有逻辑不变） ==========
        cond1 = cy <= -4.0 and hs300 <= -2.5 and zz1000 <= -2.0
        all_heavy_drop = all(x <= -1.5 for x in main_list)
        cond2 = sz <= -3.5 and sh <= -2.0 and all_heavy_drop
        cond3 = cy_vs_sh <= -2.5 and all(x < -1.0 for x in main_list)
        if cond1 or cond2 or cond3:
            MarketContext.market_sentiment = "极端恐慌"
            return MarketContext.market_sentiment

        # ========== 5. 恐慌（原有逻辑不变） ==========
        cond_a = cy <= -3.0 and hs300 < -1.5 and zz500 < -1.5 and zz1000 < -1.5
        cond_b = (sz - sh) <= -1.5 and cnt_green >= 6
        cond_c = hs300 <= -2.5 and cnt_green >= 5
        if cond_a or cond_b or cond_c:
            MarketContext.market_sentiment = "恐慌"
            return MarketContext.market_sentiment

        # ========== 6. 偏弱（原有逻辑不变） ==========
        heavy_cy = cy <= -3.0
        mid_drop = sum(1 for x in main_list if x < 0)
        cond_x = 4 <= mid_drop <= 6 and not heavy_cy
        cond_y = (sz - sh) <= -0.8 and mid_drop >= 4
        if cond_x or cond_y:
            MarketContext.market_sentiment = "偏弱"
            return MarketContext.market_sentiment

        # ========== 7. 中性正常（涨跌均衡，震荡行情） ==========
        MarketContext.market_sentiment = "正常震荡"
        return MarketContext.market_sentiment


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def _get_stock_grade(code6: str) -> str:
    """获取股票等级（L1_行业龙头 / L2_细分龙头 / L3_题材跟风）"""
    return STOCK_GRADE.get(code6, "L3_题材跟风")


def _get_first_profit_target(code6: str) -> list:
    """
    获取第1档止盈目标（%），用于第2仓(sno=2)浮盈门槛。
    逻辑：
      sno=1 → 固定 5%
      sno=2 → 该股 Grade 第1档止盈目标（从 STOCK_GRADE + GRADE_CONFIG 读取）
    """
    grade = _get_stock_grade(code6)
    cfg = GRADE_CONFIG.get(grade, GRADE_CONFIG["L3_题材跟风"])
    print("cfg: ", cfg['profit_targets'])
    return cfg["profit_targets"]



def compute_rsi(closes: pd.Series, period: int = 14) -> float:
    """计算RSI(14)"""
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def _fetch_kline_akshare(code: str, days: int = 120) -> Optional[pd.DataFrame]:
    """akshare保底K线获取"""
    if not AKSHARE_AVAILABLE:
        return None
    
    try:
        prefix = code[:2]
        num = code[2:]
        if prefix == 'sh':
            ts_code = f"sh{num}"
        else:
            ts_code = f"sz{num}"
        
        df = ak.stock_zh_a_hist(symbol=ts_code, period='daily',
                               start_date='20200101', end_date='20300101',
                               adjust='qfq')
        if df is None or df.empty:
            return None
        
        col_rename = {
            '日期': 'day', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume'
        }
        df.rename(columns=col_rename, inplace=True)
        
        if 'day' in df.columns:
            df['day'] = pd.to_datetime(df['day'])
        
        for col in ['open', 'close', 'high', 'low']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        if 'volume' in df.columns:
            df['volume'] = df['volume'].astype(float)
        
        # 计算均线
        close = df['close'].values
        for n in [5, 10, 20, 60]:
            df[f'ma{n}'] = pd.Series(close).rolling(n).mean().values
        
        return df.tail(days)
    except Exception:
        return None


def _fetch_kline_sina(code: str, days: int = 120) -> Optional[pd.DataFrame]:
    """新浪K线获取（备用）"""
    try:
        import requests
        url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
        params = {
            'symbol': code,
            'scale': '240',  # 日线
            'datalen': str(days)
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        
        if not data:
            return None
        
        df = pd.DataFrame(data)
        df['day'] = pd.to_datetime(df['day'])
        for col in ['open', 'close', 'high', 'low']:
            df[col] = df[col].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        close = df['close'].values
        for n in [5, 10, 20, 60]:
            df[f'ma{n}'] = pd.Series(close).rolling(n).mean().values
        
        return df
    except Exception:
        return None


def fetch_kline(code: str, days: int = 120) -> Optional[pd.DataFrame]:
    """获取K线数据（优先新浪，失败用akshare）"""
    df = _fetch_kline_sina(code, days)
    if df is not None and len(df) >= 20:
        return df
    
    df2 = _fetch_kline_akshare(code, days)
    if df2 is not None and len(df2) >= 20:
        return df2
    
    return None


def get_stock_realtime(code: str) -> Optional[dict]:
    """获取个股实时价格"""
    try:
        import requests
        url = f"https://hq.sinajs.cn/list={code}"
        headers = {'Referer': 'http://finance.sina.com.cn'}
        resp = requests.get(url, headers=headers, timeout=5)
        data = resp.content.decode('gbk')
        
        parts = data.split('"')[1].split(',')
        if len(parts) > 10:
            return {
                'code': code,
                'name': parts[0],
                'current': float(parts[3]),
                'open': float(parts[1]),
                'high': float(parts[4]),
                'low': float(parts[5]),
                'volume': float(parts[8]),
            }
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════
# 核心监控器
# ═══════════════════════════════════════════════════════════

class PositionMonitor:
    """持仓监控器 - 止损止盈核心逻辑"""
    
    def __init__(self, market: MarketContext = None):
        self.market = market or MarketContext()
        self._log_init()
    
    def _log_init(self):
        os.makedirs(LOG_DIR, exist_ok=True)
    
    def _log(self, msg: str):
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = f"[{ts}] {msg}"
        print(line)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    
    # ═══════════════════════════════════════════════════
    # 止损检查（5层防线，按优先级）
    # ═══════════════════════════════════════════════════
    
    def check_stop_loss(self, pos: PositionData,
                       current_price: float = None,
                       ma10: float = 0,
                       ma5: float = 0,
                       atr14: float = None,
                       atr5: float = None) -> List[MonitorSignal]:
        """
        检查所有止损条件
        
        优先级顺序：
        1. ATR自适应止损（最新，优先触发）
        2. 固定止损 -10%（已取消）
        3. 移动止损 -6%（浮盈后启用）
        4. 均线止损（跌破5/10日线，当前已取消）
        5. 时间止损（持有≥20天未盈利）
        
        Returns:
            止损信号列表（按优先级排序）
        """
        signals = []
        cp = current_price or pos.current_price
         # 计算当前股的止盈目标
        profit_percent = _get_first_profit_target(pos.code)
        profit_step1 = profit_percent[0] * 100
        profit_step2 = profit_percent[1] * 100
        profit_step3 = profit_percent[2] * 100
        print("profit_percent: ", profit_step1, profit_step2, profit_step3)

        # 更新最高价
        if cp > pos.highest_price:
            pos.highest_price = cp
        
        # 计算浮盈
        unrealized_pct = (cp - pos.cost) / pos.cost * 100 if pos.cost > 0 else 0
        pos.unrealized_pct = unrealized_pct
        
        # 计算回撤
        if pos.highest_price > 0:
            drawdown_pct = (pos.highest_price - cp) / pos.highest_price * 100
            pos.drawdown_pct = drawdown_pct
        
        # 计算出出股份
          # 判断是否为科技股（科创板688开头 或 创业板300/301开头）
        is_tech = pos.code.startswith(('688'))

        # 确定取整单位
        round_unit = 200 if is_tech else 100

        # 向上取整到对应单位
        import math
        sell_all_shares = math.ceil( pos.shares / round_unit) * round_unit
        sell_half_shares = math.ceil( pos.shares *0.5 / round_unit) * round_unit
        
        atr_profit = atr14 / pos.cost *100

        pecent = atr14 * 2 / pos.cost  * 100
        percent_half = 0.65 * pecent
        loss_pecent = (cp - pos.real_cost)/pos.real_cost * 100 

        print("pecent: ", pecent, ", pec_half: ", percent_half, ", lose_percent: ", loss_pecent)

        print("浮赢第三档" , pos.stop_level_hit[2], "成本价： ", pos.cost, ", 卖出所有: ", sell_all_shares, ", 卖出一半: ", sell_half_shares, 'atr_profit: ', atr_profit)
        # 计算移动回撤比例
        if pos.unrealized_pct >= atr_profit and pos.unrealized_pct <= profit_step1:
            pos.trailing_stop_pct = pos.unrealized_pct * 0.45 / 100  # 浮盈10%-第一止盈，回撤比例45%
        elif pos.unrealized_pct > profit_step1 and pos.unrealized_pct <= profit_step2 and pos.stop_level_hit[0]:
            pos.trailing_stop_pct = pos.unrealized_pct * 0.55 / 100  # 浮盈第一止盈-第二止盈，已经止盈，回撤比例 盈利*55%
        elif pos.unrealized_pct > profit_step1 and pos.unrealized_pct <= profit_step2 and not pos.stop_level_hit[0]:
            pos.trailing_stop_pct = pos.unrealized_pct * 0.35 / 100  # 浮盈第一止盈-第二止盈，未止盈，回撤比例 盈利*35%
        elif pos.unrealized_pct > profit_step2 and pos.unrealized_pct <= profit_step3 and pos.stop_level_hit[1]:
            pos.trailing_stop_pct = pos.unrealized_pct * 0.70 / 100  # 浮盈第二止盈-第三止盈，已止盈，回撤比例 盈利*70%
        elif pos.unrealized_pct > profit_step2 and pos.unrealized_pct <= profit_step3 and not pos.stop_level_hit[1]:
            pos.trailing_stop_pct = pos.unrealized_pct * 0.25 / 100  # 浮盈第二止盈-第三止盈，未止盈，回撤比例 盈利*25%
        elif pos.unrealized_pct > profit_step3 and pos.stop_level_hit[2]:
            pos.trailing_stop_pct = pos.unrealized_pct * 0.80 / 100  # 浮盈超过第三止盈，已止盈，回撤比例 盈利*80%
        elif pos.unrealized_pct > profit_step3 and not pos.stop_level_hit[2]:
            pos.trailing_stop_pct = pos.unrealized_pct * 0.15 / 100  # 浮盈超过第三止盈，未止盈，回撤比例 盈利*15%

        print(f"[止损检查] {pos.name} 当前价: {cp:.2f}, atr浮盈: {atr_profit:.2f}%, 浮盈: {unrealized_pct:.2f}%, 回撤: {pos.drawdown_pct:.2f}%， 移动止损: {pos.trailing_stop_pct*100:.2f}%, 成本价调整后: {pos.cost}, {pos.real_cost}")

        # ── 1. ATR自适应止损 ───────────────────────────
        if atr14 is None:
            atr14 = pos.entry_atr
        
        if atr14 > 0:
            atr_stop = pos.real_cost - 2 * atr14  # 入场价 - 2倍ATR
            art_stop_half = pos.real_cost - 2 * atr14 * 0.65  # 半止损位
            print("atr_stop:", atr_stop, "atr14:", atr14, "art_stop_half:", art_stop_half)
            if cp <= atr_stop and not pos.stop_lose_hit[3]:
                signals.append(MonitorSignal(
                    stock_code=pos.code,
                    signal_type=MonitorSignalType.STOP_LOSS.value,
                    signal_desc=f"ATR自适应止损100%：现价{cp:.2f} ≤ 止损位{atr_stop:.2f}（ATR={atr14:.2f}），卖出{sell_all_shares}股, 共{pos.shares}股",
                    action=MonitorAction.SELL.value,
                    suggested_ratio=1.0,
                    price=cp,
                    urgency="urgent",
                    profit_pct=unrealized_pct,
                    stop_price=atr_stop,
                ))
                return signals  # 最高优先级，直接返回
            elif cp <= art_stop_half and not pos.stop_lose_hit[2]:  # 半止损位
                print("art_stop_half:", art_stop_half, "atr14:", atr14, "art_stop_half:", art_stop_half)
                signals.append(MonitorSignal(
                    stock_code=pos.code,
                    signal_type=MonitorSignalType.STOP_LOSS.value,
                    signal_desc=f"ATR自适应止损50%：现价{cp:.2f} ≤ 止损位{art_stop_half:.2f}），卖出{sell_half_shares}股, 共{pos.shares}股",
                    action=MonitorAction.SELL.value,
                    suggested_ratio=0.5,
                    price=cp,
                    urgency="urgent",
                    profit_pct=unrealized_pct,
                    stop_price=art_stop_half,
                ))
                return signals  # 最高优先级，直接返回
        # print("signals: ",signals)

        # # ── 2. 固定止损 -10% ─────────────────────────
        # fixed_stop_price = pos.cost * (1 - pos.fixed_stop_loss_pct)
        # print("fixed_stop_price:", fixed_stop_price)
        # if cp <= fixed_stop_price:
        #     signals.append(MonitorSignal(
        #         stock_code=pos.code,
        #         signal_type=MonitorSignalType.STOP_LOSS.value,
        #         signal_desc=f"固定止损：现价{cp:.2f} ≤ 止损价{fixed_stop_price:.2f}（-{pos.fixed_stop_loss_pct*100:.0f}%）",
        #         action=MonitorAction.SELL.value,
        #         suggested_ratio=1.0,
        #         price=cp,
        #         urgency="urgent",
        #         profit_pct=unrealized_pct,
        #         stop_price=fixed_stop_price,
        #     ))
        #     print("signals: ",signals)
        #     return signals
            
       

        # ── 3. 达到第一止盈点后，启动移动止损（浮盈后启用）──────────────
        if unrealized_pct >=atr_profit:
            print("启用移动止损检查，回撤比例:", pos.trailing_stop_pct*100, "pos.drawdown_pct:", pos.drawdown_pct)
            if pos.drawdown_pct >= pos.trailing_stop_pct * 100:
                signals.append(MonitorSignal(
                    stock_code=pos.code,
                    signal_type=MonitorSignalType.TRAILING_STOP.value,
                    signal_desc=f"移动浮赢止损50%：回撤{pos.drawdown_pct:.1f}%≥{pos.trailing_stop_pct*100:.1f}%，卖出{sell_half_shares}股, 共{pos.shares}股",
                    action=MonitorAction.SELL.value,
                    suggested_ratio=1.0,
                    price=cp,
                    urgency="urgent",
                    profit_pct=unrealized_pct,
                    stop_price=cp,
                ))
                print("signals: ",signals)
                return signals
        
        # # ── 4. 均线止损：跌破5日线减半，跌破10日线全卖 ───────────────────
        # print("ma5:", ma5, "unrealized_pct:", unrealized_pct, "art5:", pos.cost-atr5)
        # if ma5 > 0 and cp < ma5 and unrealized_pct < 0 and cp < pos.cost - atr5 : # 价格跌破5日线且未盈利且跌破ATR5
        #     signals.append(MonitorSignal(
        #         stock_code=pos.code,
        #         signal_type=MonitorSignalType.STOP_LOSS.value,
        #         signal_desc=f"均线止损50%：现价{cp:.2f} < 5日线{ma5:.2f}",
        #         action=MonitorAction.SELL.value,
        #         suggested_ratio=1.0,
        #         price=cp,
        #         urgency="urgent",
        #         profit_pct=unrealized_pct,
        #         stop_price=ma5,
        #     ))
        #     return signals
        # elif ma10 > 0 and cp < ma10 and unrealized_pct < 0 :
        #     signals.append(MonitorSignal(
        #         stock_code=pos.code,
        #         signal_type=MonitorSignalType.STOP_LOSS.value,
        #         signal_desc=f"均线止损100%：现价{cp:.2f} < 10日线{ma10:.2f}",
        #         action=MonitorAction.SELL.value,
        #         suggested_ratio=1.0,
        #         price=cp,
        #         urgency="urgent",
        #         profit_pct=unrealized_pct,
        #         stop_price=ma10,
        #     ))
        #     return signals
        
        # ── 5. 时间止损：持有≥10天未盈利 ─────────────
        # hold_days = pos.hold_days or (datetime.now() - datetime.strptime(pos.entry_date, "%Y-%m-%d")).days if pos.entry_date else 0
        # if hold_days >= 20 and unrealized_pct <= 0:
        #     signals.append(MonitorSignal(
        #         stock_code=pos.code,
        #         signal_type=MonitorSignalType.TIME_STOP.value,
        #         signal_desc=f"时间止损：持有{hold_days}天未盈利",
        #         action=MonitorAction.SELL.value,
        #         suggested_ratio=1.0,
        #         price=cp,
        #         urgency="normal",
        #         profit_pct=unrealized_pct,
        #     ))     
        # return signals
        return signals
    # ═══════════════════════════════════════════════════
    # 止盈检查（4阶分阶段）
    # ═══════════════════════════════════════════════════
    
    def check_take_profit(self, pos: PositionData,
                         current_price: float = None) -> List[MonitorSignal]:
        """
        检查止盈条件
        
        止盈层级（根据市场环境动态调整）：
        - 15%区间：卖出33.3%
        - 25%区间：卖出33.3%
        - 40%区间：移动止损至+20%，不卖出
        - 60%区间：移动止损至+40%，不卖出
        
        市场调整系数：
        - 牛市(STRONG)：放宽30%
        - 熊市(WEAK)：收紧20%
        - 震荡市(NEUTRAL)：标准
        
        Returns:
            止盈信号列表
        """
        signals = []
        cp = current_price or pos.current_price
        
        unrealized_pct = (cp - pos.cost) / pos.cost * 100 if pos.cost > 0 else 0
        pos.unrealized_pct = unrealized_pct
        
        # 市场环境调整系数
        env_adj = self._get_profit_adjustment()
        
        # 标准止盈层级
        levels = [
            {"pct": 15, "sell_ratio": 0.333, "label": "15%区间"},
            {"pct": 25, "sell_ratio": 0.333, "label": "25%区间"},
            {"pct": 40, "sell_ratio": 0.0, "label": "40%区间", "move_stop": 20},
           # {"pct": 60, "sell_ratio": 0.0, "label": "60%区间", "move_stop": 40},
        ]
        
        for level,index in zip(levels, range(len(levels))):
            target_pct = level["pct"] * env_adj
            
            # # 检查是否已触发过该层级
            # triggered = any(
            #     r.get('take_profit_level', 0) >= target_pct
            #     for r in pos.sold_records
            # )
            triggered = pos.stop_level_hit[index]
            print(f"Index: {index}, Triggered: {triggered}")

            if not triggered and unrealized_pct >= target_pct:
                if level.get("move_stop"):
                    # 移动止损至成本+X%
                    new_stop = pos.cost * (1 + level["move_stop"] / 100)
                    if new_stop > pos.moving_stop_price:
                        pos.moving_stop_price = new_stop
                        signals.append(MonitorSignal(
                            stock_code=pos.code,
                            signal_type=MonitorSignalType.TAKE_PROFIT.value,
                            signal_desc=f"浮盈{unrealized_pct:.1f}%，移动止损至成本+{level['move_stop']}%（{new_stop:.2f}）",
                            action=MonitorAction.HOLD.value,
                            suggested_ratio=0,
                            price=cp,
                            urgency="normal",
                            profit_pct=unrealized_pct,
                            stop_price=new_stop,
                        ))
                else:
                    # 正常止盈卖出
                    signals.append(MonitorSignal(
                        stock_code=pos.code,
                        signal_type=MonitorSignalType.TAKE_PROFIT.value,
                        signal_desc=f"触发{level['label']}止盈，浮盈{unrealized_pct:.1f}%（需卖出{level['sell_ratio']*100:.1f}%）",
                        action=MonitorAction.SELL.value,
                        suggested_ratio=level["sell_ratio"],
                        price=cp,
                        urgency="normal",
                        profit_pct=unrealized_pct,
                        target_price=cp,
                    ))
        
        return signals
    
    def _get_profit_adjustment(self) -> float:
        """根据市场环境调整止盈阈值"""
        status = self.market.status
        if status == MarketStatus.STRONG:
            return 1.30  # 牛市放宽30%
        elif status == MarketStatus.WEAK:
            return 0.80  # 熊市收紧20%
        else:
            return 1.0   # 震荡市标准
    
    # ═══════════════════════════════════════════════════
    # 综合监控（止损+止盈）
    # ═══════════════════════════════════════════════════
    
    def monitor_position(self, pos: PositionData,
                        current_price: float = None) -> Dict:
        """
        综合监控：止损 + 止盈
        
        Returns:
            {
                'has_signal': bool,
                'signals': [MonitorSignal],
                'action': str,  # SELL / REDUCE / HOLD / BUY
                'profit_pct': float,
                'summary': str
            }
        """
        cp = current_price or pos.current_price
        
        # 获取K线数据计算ATR和均线
        df = fetch_kline(self._to_sina_code(pos.code), days=80)
        
        atr14 = 0
        atr5 = 0
        atr = 0
        ma20 = 0
        ma10 = 0
        ma5 = 0
        if df is not None and len(df) >= 60:
            atr14 = calc_atr(df, period=14)
            atr5 = calc_atr(df, period=5)
            print("atr14:", atr14, "atr5:", atr5)
            ma20 = float(df['ma20'].iloc[-1])
            ma10 = float(df['ma10'].iloc[-1])
            ma5 = float(df['ma5'].iloc[-1])
        # 合并检查止损和止盈
        all_signals = []
        
        # 止损信号（优先处理）
        stop_signals = self.check_stop_loss(pos, cp, ma10, ma5, atr14, atr5)
        print("stop_signals: ", stop_signals)
        all_signals.extend(stop_signals)
        
        # 止盈信号
       # profit_signals = self.check_take_profit(pos, cp)
        #all_signals.extend(profit_signals)
        
        # 确定最终动作
        if not all_signals:
            action = MonitorAction.HOLD.value
            summary = f"持仓正常，浮盈{pos.unrealized_pct:.2f}%"
        else:
            # 找最紧急的信号
            urgent_signal = None
            for s in all_signals:
                if s.urgency == "urgent":
                    urgent_signal = s
                    break
            if urgent_signal is None:
                urgent_signal = all_signals[0]
            
            action = urgent_signal.action
            summary = urgent_signal.signal_desc
        
        return {
            'has_signal': len(all_signals) > 0,
            'signals': all_signals,
            'action': action,
            'profit_pct': pos.unrealized_pct,
            'summary': summary,
            'atr': atr,
            'ma20': ma20,
            'ma10': ma10,
            'ma5': ma5,
        }
    
    def _to_sina_code(self, code: str) -> str:
        """转换为新浪格式"""
        code = code.strip().lstrip('sh').lstrip('sz')
        if code.startswith(('6', '5', '8', '9')):
            return f"sh{code}"
        return f"sz{code}"
    
    # ═══════════════════════════════════════════════════
    # 批量监控
    # ═══════════════════════════════════════════════════
    
    def monitor_all(self, holdings: List[dict] = None,
                    market: MarketContext = None) -> Dict[str, Dict]:
        """
        批量监控所有持仓
        
        Args:
            holdings: 持仓列表（None时从holdings.json读取）
            market: 市场环境
            
        Returns:
            {code: monitor_result}
        """
        print("market context:", market)
        if market:
            self.market = market
        else:
            self.market_sentiment = MarketContext.get_market_sentiment()

        print("市场情绪:", self.market_sentiment)



        if holdings is None:
            if not os.path.exists(HOLDINGS_FILE):
                return {}
            with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
                holdings = json.load(f)
        
        results = {}
        for h in holdings:
            try:
                code = h.get('code', '')
                name = h.get('name', code)
                
                # 获取实时价格
                realtime = get_stock_realtime(self._to_sina_code(code))
                current_price = realtime['current'] if realtime else float(h.get('current_price', 0))
                
                # 构建持仓数据
                pos = PositionData.from_holding(h, current_price)
                
                # 监控
                result = self.monitor_position(pos, current_price)
                print("result: ", result)
                result['name'] = name
                result['current_price'] = current_price
                result['cost'] = pos.cost
                result['shares'] = pos.shares
                result['highest_price'] = pos.highest_price
                
                results[code] = result
                
            except Exception as e:
                self._log(f"监控 {h.get('code','?')} 失败: {e}")
        
        return results
    
    # ═══════════════════════════════════════════════════
    # 飞书推送
    # ═══════════════════════════════════════════════════
    
    def build_feishu_card(self, results: Dict[str, Dict],
                         title: str = "止损处理") -> dict:
        """构建飞书监控卡片"""
        from datetime import datetime
        
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 分类
        urgent = []   # 需要紧急处理的
        normal = []   # 正常持仓
        profit = []   # 止盈信号
        hold = []     # 观望
        
        for code, r in results.items():
            item = {
                'code': code,
                'name': r.get('name', code),
                'profit_pct': r.get('profit_pct', 0),
                'action': r.get('action', 'HOLD'),
                'summary': r.get('summary', ''),
                'current_price': r.get('current_price', 0),
            }
            
            if r.get('action') == 'SELL':
                urgent.append(item)
            elif '止盈' in r.get('summary', ''):
                profit.append(item)
            elif r.get('action') == 'REDUCE':
                normal.append(item)
            else:
                hold.append(item)
        
        lines = []
        lines.append(f"**📊 {title}** | {date_str}")
        lines.append("")
        
        # 大盘信号
        print("市场情绪:", self.market_sentiment)
        if self.market_sentiment == "极端恐慌":
            lines.append("⚠️ **市场极端恐慌，🚫禁止清仓**\n")
        elif self.market_sentiment == "恐慌":
            lines.append("⚠️ **市场恐慌，禁止清仓，最多减仓30%**\n")



        # 紧急信号
        if urgent:
            lines.append(f"🚨 **紧急处理 ({len(urgent)}只)**")
            for item in urgent:
                lines.append(f"{item['name']}({item['code']}) 浮盈={item['profit_pct']:+.2f}%")
                lines.append(f"  → {item['summary']}")
            lines.append("")
        
        # # 止盈信号
        # if profit:
        #     lines.append(f"💰 **止盈信号 ({len(profit)}只)**")
        #     for item in profit:
        #         lines.append(f"{item['name']}({item['code']}) 浮盈={item['profit_pct']:+.2f}%")
        #         lines.append(f"  → {item['summary']}")
        #     lines.append("")
        
        # 正常监控
        if normal:
            lines.append(f"⚠️ **建议减仓 ({len(normal)}只)**")
            for item in normal:
                lines.append(f"{item['name']}({item['code']}) 浮盈={item['profit_pct']:+.2f}%")
            lines.append("")
        
        # 持仓正常
        if hold:
            lines.append(f"✅ **持仓正常 ({len(hold)}只)**")
            hold_sorted = sorted(hold, key=lambda x: x['profit_pct'], reverse=True)
            for item in hold_sorted[:5]:  # 只显示浮盈前5
                lines.append(f"{item['name']}({item['code']}) 浮盈={item['profit_pct']:+.2f}%")
            if len(hold) > 5:
                lines.append(f"... 还有{len(hold)-5}只")
            lines.append("")
        
        # 汇总
        total = len(results)
        lines.append(f"📋 汇总：{total}只持仓 | 🚨{len(urgent)}只紧急 | 💰{len(profit)}只止盈")
        lines.append("")
        lines.append("⚠️ 仅供参考，不构成投资建议")
        
        elements = [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}]
        
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 {title} | {date_str}"},
                "template": "blue"
            },
            "elements": elements
        }


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

def main():
    """
    运行方式：
      python3 position_monitor.py              # 仅监控+打印
      python3 position_monitor.py --feishu     # 监控+打印+飞书推送
    """
    import sys
    
    feishu_mode = "--feishu" in sys.argv
    
    print("=" * 60)
    print("📊 持仓监控（止损止盈V3.0）")
    print("=" * 60)
    
    monitor = PositionMonitor()
    
    # 读取持仓
    if not os.path.exists(HOLDINGS_FILE):
        print(f"[ERROR] 持仓文件不存在: {HOLDINGS_FILE}")
        return
    
    with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
        holdings = json.load(f)
    
    print(f"\n[INFO] 读取到 {len(holdings)} 条持仓记录")
    
    # 批量监控
    results = monitor.monitor_all(holdings)
    
    # 打印结果
    print("\n" + "-" * 60)
    print("📋 监控结果")
    print("-" * 60)
    
    for code, r in results.items():
        profit = r.get('profit_pct', 0)
        action = r.get('action', 'HOLD')
        summary = r.get('summary', '')
        
        status_icon = "✅" if action == "HOLD" else "🚨" if action == "SELL" else "⚠️"
        
        print(f"\n{status_icon} {r.get('name','?')}({code})")
        print(f"   浮盈: {profit:+.2f}% | 动作: {action}")
        print(f"   {summary}")
        
        if r.get('atr'):
            print(f"   ATR={r['atr']:.3f} | MA20={r.get('ma20', 0):.2f}")
    
    # 汇总
    urgent_count = sum(1 for r in results.values() if r.get('action') == 'SELL')
    profit_count = sum(1 for r in results.values() if '止盈' in r.get('summary', ''))
    
    print("\n" + "=" * 60)
    print(f"📋 汇总：{len(results)}只持仓 | 🚨{urgent_count}只紧急 | 💰{profit_count}只止盈")
    print("=" * 60)
    
    # 飞书推送
    if feishu_mode:
        print("\n[INFO] 飞书推送...")
        try:
            from add_position_analyzer import _get_tenant_token, _send_feishu_card
            
            card = monitor.build_feishu_card(results, "持仓监控日报")
            token = _get_tenant_token()
            
            FEISHU_APP_ID = "cli_a93eb458ceb81cc0"
            FEISHU_APP_SECRET = "1i18JU…MpV8"
            FEISHU_GROUP_ID = "oc_0ac1e4e8d09f939d887f4992bba2886b"
            
            resp = _send_feishu_card(token, card, FEISHU_GROUP_ID)
            code_resp = resp.get('code', -1)
            msg_resp = resp.get('msg', '') or resp.get('message', '')
            
            if code_resp == 0:
                print(f"✅ 飞书推送成功")
            else:
                print(f"❌ 飞书推送失败: {msg_resp}")
        except Exception as e:
            print(f"❌ 飞书推送异常: {e}")


if __name__ == "__main__":
    main()