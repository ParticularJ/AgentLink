import pandas as pd
import numpy as np
from typing import Optional, Tuple, List

from models import StockData, TechnicalIndicators, StockScore
from config import SCORE_WEIGHTS, BUY_THRESHOLD

# ── 加载数据源适配层 ────────────────────────────────────
import os
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try: del os.environ[k]
        except: pass

from data_source import get_stock_realtime, get_index_realtime


# 赛道观察池：核心 + 关注
WATCHLIST = {
    "存储芯片": {
        "core": ["301308", "603986", "688008"],
        "focus": ["300475", "002371", "688525", "688012", "001309", "688809", "688766"]
    },
    "AI芯片": {
        "core": ["688256", "688041", "002371"],
        "focus": ["688795", "688802", "603893", "300458", "300474", "688047", "603019", "601138", "000977"]
    },
    "算力租赁": {
        "core": ["603629", "300442"],
        "focus": ["603220", "603985"]
    },
    "半导体设备与材料": {
        "core": ["002371", "688012"],
        "focus": ["688072", "300655", "688630", "688700", "301200"]
    },
    "先进封装": {
        "core": ["600584"],
        "focus": ["002156", "000021"]
    },
    "光通信": {
        "core": ["300308", "601869", "600522"],
        "focus": ["688048", "300620", "688313", "688498", "600105", "002491", "300394"]
    },
    "PCB": {
        "core": ["002463", "300476", "002916"],
        "focus": ["688183", "603228", "002384", "688519", "002436", "603920", "603256", "600183", "002938", "301200", "688630", "688700"]
    },
    "电力电网_特高压": {
        "core": ["600089", "000400", "600406", "300274"],
        "focus": ["688676", "300831", "601179", "002028", "688330", "600131", "002518", "002121", "603556"]
    },
    "电力电网_新能源运营": {
        "core": ["600900", "001289"],
        "focus": ["600905", "601985"]
    },
    "燃气轮机": {
        "core": ["600875", "603308", "688239"],
        "focus": ["002353", "600893", "601727", "002595", "301548", "000534", "605060", "300034", "300855", "000738", "600475"]
    },
    "人形机器人": {
        "core": ["688017", "002050", "603728"],
        "focus": ["688160", "300580", "603662", "688165", "601689"]
    },
    "创新药": {
        "core": ["688235", "600276", "603259"],
        "focus": ["002821", "688076"]
    },
    "电池与储能": {
        "core": ["300274"],
        "focus": ["300014", "002466", "002074", "300390"]
    },
    "商业航天": {
        "core": ["600118", "001270", "600879"],
        "focus": ["600343", "688270", "688102", "688066", "002342", "300065", "002179"]
    },
    "工业金属": {
        "core": ["600362", "601600", "603993", "000960", "600111", "600549", "002428", "002149", "000060"],
        "focus": []
    },
    "贵金属": {
        "core": ["600547", "601899"],
        "focus": ["600489", "600988", "000603"]
    },
    "船舶油运": {
        "core": ["601872", "600026", "600150"],
        "focus": ["601975", "600428", "601989"]
    }
}

# 全局映射：代码 -> (板块名称, 类型core/focus)
CODE_TO_SECTOR = dict()
# 全局映射：板块名称 -> 该板块所有个股代码列表
SECTOR_ALL_STOCKS = dict()

# 自动构建映射
for sector_name, groups in WATCHLIST.items():
    all_codes = []
    # 处理 core
    for code in groups["core"]:
        CODE_TO_SECTOR[code] = (sector_name, "core")
        all_codes.append(code)
    # 处理 focus
    for code in groups["focus"]:
        CODE_TO_SECTOR[code] = (sector_name, "focus")
        all_codes.append(code)
    SECTOR_ALL_STOCKS[sector_name] = all_codes





class StockAnalyzer:
    """个股分析器（使用腾讯+新浪数据源，替代 akshare）"""

    def __init__(self):
        self.stock_cache = {}
        # 缓存每日板块评分 key:板块名 val:0~10分数
        self.sector_daily_score = {}

    def refresh_sector_strength(self):
        """刷新所有赛道板块每日强度评分（提速版：去重+缓存，只拉一次股票）"""
        self.sector_daily_score.clear()

        # 步骤1：收集所有不重复股票
        all_unique_codes = set()
        for codes in SECTOR_ALL_STOCKS.values():
            all_unique_codes.update(codes)

        # 步骤2：一次性拉取所有数据并缓存（只拉一次！）
        stock_price_cache = {}
        for code in all_unique_codes:
            try:
                df_hist, cur = get_stock_realtime(code)
                if cur and "chg_pct" in cur:
                    stock_price_cache[code] = cur["chg_pct"]
            except:
                continue

        # 步骤3：计算每个板块强度
        for sector_name, code_list in SECTOR_ALL_STOCKS.items():
            if not code_list:
                self.sector_daily_score[sector_name] = 5.0
                continue

            pct_list = []
            for code in code_list:
                if code in stock_price_cache:
                    pct_list.append(stock_price_cache[code])

            if not pct_list:
                self.sector_daily_score[sector_name] = 5.0
                continue

            avg_pct = sum(pct_list) / len(pct_list)
            if avg_pct > 3.0:
                score = 9.5
            elif avg_pct > 1.5:
                score = 8.0
            elif avg_pct > 0.0:
                score = 6.5
            elif avg_pct > -1.5:
                score = 5.0
            elif avg_pct > -3.0:
                score = 3.5
            else:
                score = 1.5

            self.sector_daily_score[sector_name] = round(score, 1)



    def fetch_stock_data(self, code: str) -> Optional[Tuple[pd.DataFrame, StockData]]:
        """获取个股实时数据和历史数据"""
        try:
            df_history, cur = get_stock_realtime(code)
            if cur is None or df_history is None:
                return None

            # 转换为 StockData 模型
            current_data = StockData(
                code=cur['code'],
                name=cur['name'],
                price=cur['price'],
                open=cur['open'],
                high=cur['high'],
                low=cur['low'],
                volume=cur['volume'],
                turnover=cur['turnover'],
                change_pct=cur['chg_pct'],
                volume_ratio=cur['volume_ratio'],
            )

            # df_history 来自新浪 K线，列名是 [day, open, close, high, low, volume]
            # 需要映射为 akshare 格式（收盘→收盘等）
            return df_history, current_data

        except Exception as e:
            print(f"获取股票{code}数据失败: {e}")
            return None

    def calculate_technical_indicators(self, df: pd.DataFrame) -> TechnicalIndicators:
        """计算技术指标（兼容新浪K线DataFrame格式）"""
        close = df['close'].values

        # 计算均线
        ma5 = float(pd.Series(close).rolling(5).mean().iloc[-1]) if len(close) >= 5 else close[-1]
        ma10 = float(pd.Series(close).rolling(10).mean().iloc[-1]) if len(close) >= 10 else close[-1]
        ma20 = float(pd.Series(close).rolling(20).mean().iloc[-1]) if len(close) >= 20 else close[-1]
        ma60 = float(pd.Series(close).rolling(60).mean().iloc[-1]) if len(close) >= 60 else close[-1]

        # MACD
        def calc_macd(data, fast=12, slow=26, signal=9):
            if len(data) < slow:
                return 0.0, 0.0, 0.0
            ema_fast = pd.Series(data).ewm(span=fast, adjust=False).mean()
            ema_slow = pd.Series(data).ewm(span=slow, adjust=False).mean()
            macd = ema_fast - ema_slow
            macd_signal = macd.ewm(span=signal, adjust=False).mean()
            macd_hist = macd - macd_signal
            return float(macd.iloc[-1]), float(macd_signal.iloc[-1]), float(macd_hist.iloc[-1])

        macd, macd_signal, macd_hist = calc_macd(close)

        # KDJ
        low_list = pd.Series(df['low'].values).rolling(window=9).min()
        high_list = pd.Series(df['high'].values).rolling(window=9).max()
        rsv = (df['close'] - low_list) / (high_list - low_list) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d
        k_val = float(k.iloc[-1])
        d_val = float(d.iloc[-1])
        j_val = float(j.iloc[-1])

        return TechnicalIndicators(
            ma5=ma5, ma10=ma10, ma20=ma20, ma60=ma60,
            macd=macd, macd_signal=macd_signal, macd_hist=macd_hist,
            kdj_k=k_val, kdj_d=d_val, kdj_j=j_val
        )

    def score_technical(self, tech: TechnicalIndicators, current_price: float) -> float:
        """技术形态评分 (0-10)"""
        score = 0

        above_ma5 = current_price > tech.ma5
        above_ma10 = current_price > tech.ma10
        above_ma20 = current_price > tech.ma20
        above_ma60 = current_price > tech.ma60

        ma_score = sum([above_ma5, above_ma10, above_ma20, above_ma60]) / 4 * 10
        score += ma_score * 0.4

          # --- 修复5：均线趋势强化（只认向上发散，过滤横盘）---
        ma5, ma10, ma20, ma60 = tech.ma5, tech.ma10, tech.ma20, tech.ma60

        # 完全多头 + 向上发散 → 最强
        if ma5 > ma10 > ma20 > ma60:
            ma_arrange = 10
        # 短期多头，但中期没跟上 → 降分
        elif ma5 > ma10 > ma20:
            ma_arrange = 7
        # 仅站上短期均线 → 中性
        elif ma5 > ma10:
            ma_arrange = 4
        # 空头排列 → 低分
        else:
            ma_arrange = 2

        score += ma_arrange * 0.3

        if tech.macd_hist > 0 and tech.macd > tech.macd_signal:
            # 红柱加长，加速上涨 -> 满分
            macd_score = 10
        elif tech.macd_hist > 0:
            # 虽然是红柱，但可能是衰减阶段 -> 降一分
            macd_score = 6  
        # 如果是绿柱(空头)
        elif tech.macd_hist > -0.5:
            # 绿柱很短，快要金叉 -> 给点同情分
            macd_score = 4
        else:
            # 绿柱很长，下跌趋势 -> 最低分
            macd_score = 2

        score += macd_score * 0.15

       # --- 修复3：升级KDJ评分 加入金叉/死叉逻辑 ---
        k = tech.kdj_k
        d = tech.kdj_d
        # 高位超买 + 死叉趋势，直接压低
        if k > 80:
            kdj_score = 2
        # 50以上多头区间，且金叉向上，最强
        elif k > 50 and k > d:
            kdj_score = 10
        # 50以上但走平/拐头，偏弱
        elif k > 50:
            kdj_score = 6
        # 20~50 中性区间
        elif k > 20:
            # 低位金叉加分
            if k > d:
                kdj_score = 5
            else:
                kdj_score = 4
        # 20以下超跌，不轻易抄底，给低分
        else:
            kdj_score = 2

        score += kdj_score * 0.15

        return score

    def score_money_flow(self, code: str, latest_data: StockData) -> float:
        """
        升级强化版资金流向评分(0-10)
        规则：放量真走强加分、无量虚涨降分、缩量回调宽容、放量杀跌重扣分、高位巨量不追高
        """
        pct = latest_data.change_pct
        vr = latest_data.volume_ratio

        # 1. 极端高位巨量分歧，不追高
        if pct > 15 and vr > 2.5:
            return 4.0

        # 2. 强力放量主升（真资金进场）
        if pct > 7 and vr > 2.0:
            return 9.5
        elif pct > 4 and vr > 1.5:
            return 8.5
        elif pct > 2 and vr > 1.2:
            return 7.0

        # 3. 无量虚涨（缩量冲高，骗线概率大）
        elif pct > 2 and vr <= 1.0:
            return 4.5
        elif pct > 0 and vr > 1.0:
            return 6.0
        elif pct > 0 and vr <= 1.0:
            return 4.0

        # 4. 小幅回调 区分缩量良性 / 放量走弱
        elif pct > -2:
            if vr < 0.9:
                # 缩量小跌，正常洗盘
                return 4.5
            else:
                # 放量小跌，资金流出
                return 3.0

        # 5. 中度下跌
        elif pct > -5:
            if vr < 0.9:
                return 3.5
            else:
                return 2.0

        # 6. 大跌暴跌
        else:
            return 1.5
    
    def score_sector(self, code: str) -> tuple[float, str]:
        """动态板块强度评分：基于你自定义赛道 + 核心标的加分"""
        # 不在自选赛道池，给偏低分，过滤杂毛
        if code not in CODE_TO_SECTOR:
            return 4.0,  "none"

        sector_name, tag = CODE_TO_SECTOR[code]
        # 取该板块当日强度分
        base_score = self.sector_daily_score.get(sector_name, 5.0)
        print("板块: {}, 强度评分: {}, 类型: {}".format(sector_name, base_score, tag))
        # 核心标的额外 +1分，封顶10
        if tag == "core":
            final_score = min(10.0, base_score + 1.0)
        else:
            final_score = base_score

        return final_score,sector_name

    def score_fundamental(self, code: str) -> float:
        """
        简易基本面评分（0~10）
        不需要财报，仅用实时数据：市值规模 + 稳定性 + 流动性
        大市值、稳定、高流通 → 高分
        小市值、波动大、低流通 → 低分
        """
        try:
            # 从缓存或实时获取数据
            if code not in self.stock_cache:
                df, data = self.fetch_stock_data(code)
                if data is None:
                    return 5.0
                self.stock_cache[code] = data
            else:
                data = self.stock_cache[code]

            price = data.price
            volume = data.volume
            change_pct = data.change_pct
            turnover = data.turnover

            # ============== 1. 规模评分（大公司更稳）==============
            cap_score = 4.0
            try:
                # 简易近似市值：价格 * 成交量（相对大小区分）
                cap_approx = price * volume
                if cap_approx > 5e8:
                    cap_score = 9.0
                elif cap_approx > 2e8:
                    cap_score = 7.5
                elif cap_approx > 5e7:
                    cap_score = 6.0
                elif cap_approx > 1e7:
                    cap_score = 4.5
                else:
                    cap_score = 2.0
            except:
                cap_score = 5.0

            # ============== 2. 稳定性评分（波动小→更稳健）==============
            pct_abs = abs(change_pct)
            if pct_abs <= 2.0:
                stab_score = 9.0
            elif pct_abs <= 4.0:
                stab_score = 7.0
            elif pct_abs <= 6.0:
                stab_score = 5.0
            else:
                stab_score = 3.0

            # ============== 3. 流动性评分（换手率健康）==============
            liq_score = 5.0
            if 1.0 < turnover < 7.0:
                liq_score = 8.0
            elif turnover > 10.0:
                liq_score = 4.0
            elif turnover < 0.5:
                liq_score = 3.0

            # ============== 最终综合基本面得分（0~10）==============
            final = (cap_score * 0.5 + stab_score * 0.3 + liq_score * 0.2)
            final = max(2.0, min(10.0, final))
            return round(final, 1)

        except Exception as e:
            return 5.0

    def score_volume(self, latest_data: StockData) -> float:
        """
        升级量能配合评分(0-10)
        逻辑：温和放量最优、暴量不追高、良性缩量留容错、极度缩量压低
        只判量能活跃度与结构，不看涨跌，和资金流评分互补不重复
        """
        vr = latest_data.volume_ratio

        # 1. 暴量过高：分歧大、容易出货，不给满分
        if vr > 3.0:
            return 7.5
        # 2. 健康完美放量
        elif vr > 2.5:
            return 9.5
        elif vr > 1.8:
            return 9.0
        elif vr > 1.3:
            return 7.5
        # 3. 均量附近，正常活跃度
        elif vr > 0.9:
            return 5.5
        # 4. 轻微缩量：良性洗盘可接受
        elif vr > 0.6:
            return 4.0
        # 5. 极度缩量：死水无资金
        else:
            return 2.0

    def score_sentiment(self, code: str, latest_data: StockData) -> float:
        """情绪热度评分（升级：结合大盘强度，防逆势陷阱）"""
        stock_pct = latest_data.change_pct

        # 获取大盘（上证指数）当日涨跌幅
        market_pct = 0.0
        try:
            index_data = get_index_realtime()  # 直接用你现有函数
            if index_data and "chg_pct" in index_data:
                market_pct = index_data["chg_pct"]
        except:
            pass

        # 真实强度 = 个股相对大盘的超额收益
        real_strength = stock_pct - market_pct

        # 打分（只看真实强度，规避逆势风险）
        if real_strength > 8:
            return 10
        elif real_strength > 4:
            return 8
        elif real_strength > 1:
            return 7
        elif real_strength > -1:
            return 5
        elif real_strength > -3:
            return 3
        else:
            return 1

    def calculate_comprehensive_score(self, code: str, latest_data: StockData,
                                     tech: TechnicalIndicators) -> StockScore:
        """计算综合评分"""
        technical_score = self.score_technical(tech, latest_data.price)
        money_flow_score = self.score_money_flow(code, latest_data)
        sector_score, sector_name = self.score_sector(code)
        print("sector_score:", sector_score, "sector_name:", sector_name)
        fundamental_score = self.score_fundamental(code)
        #print("技术评分: {:.1f}, 资金评分: {:.1f}, 板块评分: {:.1f}, 基本面评分: {:.1f}".format(technical_score, money_flow_score, sector_score, fundamental_score))
        volume_score = self.score_volume(latest_data)
        sentiment_score = self.score_sentiment(code, latest_data)

        total_score = (
            technical_score * SCORE_WEIGHTS["technical"] +
            money_flow_score * SCORE_WEIGHTS["money_flow"] +
            sector_score * SCORE_WEIGHTS["sector"] +
            fundamental_score * SCORE_WEIGHTS["fundamental"] +
            volume_score * SCORE_WEIGHTS["volume"] +
            sentiment_score * SCORE_WEIGHTS["sentiment"]
        ) * 10

        return StockScore(
            total_score=total_score,
            sector_name=sector_name,
            technical_score=technical_score * 10,
            money_flow_score=money_flow_score * 10,
            sector_score=sector_score * 10,
            fundamental_score=fundamental_score * 10,
            volume_score=volume_score * 10,
            sentiment_score=sentiment_score * 10
        )
