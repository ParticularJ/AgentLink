#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
突破前期高点分析器 —— 双模式终极版（绿的谐波专用放行版）
修复：95%硬门槛误杀主升浪；放宽强趋势判定；提高高危线到98%
模式1：稳健二次突破（突破→回调→再突破 重仓）
模式2：强势新高主升（临近历史新高强趋势 轻仓）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


# 清空系统代理
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["FTP_PROXY"] = ""
os.environ["ALL_PROXY"] = ""
os.environ["SOCKS_PROXY"] = ""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# 导入数据源适配器
try:
    from data_source_adapter import DataSourceAdapter
except ImportError:
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../ma-bullish-strategy/skills/scripts')
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        sys.path.insert(0, os.path.join(os.getcwd(), 'ma-bullish-strategy/skills/scripts'))
        from data_source_adapter import DataSourceAdapter

# 2026-09-12 导入 Medium-termHoldingStrategy 的 get_stock_realtime
# 替代 pytdx（已失效）：腾讯实时行情 + 新浪/腾讯 K 线（含 MA5/10/20/60）
try:
    from data_source import get_stock_realtime
    _HAS_REALTIME = True
except ImportError:
    _mh_path = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', '..', '..', 'Medium-termHoldingStrategy', 'skills', 'scripts'
    ))
    if _mh_path not in sys.path:
        sys.path.insert(0, _mh_path)
    try:
        from data_source import get_stock_realtime
        _HAS_REALTIME = True
    except ImportError as _e:
        print(f"[WARN] get_stock_realtime 导入失败: {_e}，将只用 DataSourceAdapter")
        get_stock_realtime = None
        _HAS_REALTIME = False




class BreakoutHighAnalyzer:
    """突破前期高点分析器 —— 双模式实战版（绿的谐波放行）"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "双模式突破高点策略（新高主升放行版）"
        self.version = "v2.2"
        self.win_rate = 0.72
        
        # 基础突破参数
        self.lookback_days = 10
        self.breakout_threshold = 0.005  # 0.5% 小幅新高算有效突破
        self.volume_multiplier = 1.6
        
        # 历史高位区间定义（改：高危线上调到98%）
        self.high_risk_zone = 0.95    # 95%以上 才严格过滤
        self.trend_break_zone = 0.95  # 90%-98% 趋势强可放行
        
        # 强势新高主升 准入硬条件
        self.strong_trend_break_ratio = 0.01   # 单日突破≥4%
        self.strong_trend_vol_ratio = 0.8      # 量比≥1.2
        self.max_drawback_5d = 0.22           # 5日最大回撤≤8% - >22%
        self.strong_daily_up = 0.08             # 单日涨幅≥8% 直接强突破
        
        self.weights = {
        'breakout_strength': 0.22,    # ✅ 第二重要：突破力度
        'volume_confirm': 0.33,       # ✅ 最重要：量能真假
        'trend_cooperation': 0.22,    # ✅ 第三重要：趋势强弱
        'pattern_quality': 0.10,      # ✅ 次要：形态配合
        'pullback_confirmation': 0.08,# ✅ 次要：结构稳健性
        'market_environment': 0.05    # ✅ 极轻：几乎不影响
        }
        
        # 2026-09-12：DataSourceAdapter (pytdx) 已失效，改用 get_stock_realtime
        # 保留 data_adapter 作为 fallback（仅在 _HAS_REALTIME 不可用时 init）
        self.data_adapter = None
        if not _HAS_REALTIME or get_stock_realtime is None:
            self.data_adapter = DataSourceAdapter()
            if not self.data_adapter.data_source:
                raise RuntimeError("没有可用的数据源")

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        #print("df[MA5]: ", df['MA5'])
        df['MA60'] = df['close'].rolling(window=60).mean()
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        df['volume_ma20'] = df['volume'].rolling(window=20).mean()
        df['entity_high'] = df[['open', 'close']].max(axis=1)  # 实体的最高点
        df['upper_shadow'] = (df['high'] - df['entity_high']) / df['high']
       # print("df['upper_shadow']: ", df['upper_shadow'])
        return df
    
    def _analyze_trend(self, df: pd.DataFrame, idx: int) -> Dict:
        """均线趋势分析 —— 不崩盘、合理区分强弱版"""
        if idx < 20:
            return {'score': 0, 'direction': '数据不足', 'ma_bullish': False, 'ma5_slope': 0}
        
        current = df.iloc[idx]

        pre_ma5 = df['MA5'].iloc[idx - 1]

         #计算MA5单日绝对斜率
        ma5_slope = current['MA5'] - pre_ma5

        close_stand_ma5 = current['close'] > current['MA5']
        ma5_over_ma20 = current['MA5'] > current['MA20']
        # 附加兜底：MA10向上，防止单边下跌中途反弹诱多
        # pre_ma10 = df['MA10'].iloc[idx-1]
        # ma10_up = current['MA10'] > pre_ma10
        ma_short_bull = close_stand_ma5 and ma5_over_ma20 
        # # ✅ 短期多头（你原来的逻辑，保留，保证大部分股票能拿到趋势分）
        # ma_short_bull = (current['MA5'] > current['MA10'] and 
        #                 current['MA10'] > current['MA20'])
        #print("ma_short_bull: ", ma_short_bull)
        # ✅ 仅做加分项，不做门槛（不会批量变低分）
        
        # 最终趋势判定：短期顺了就算多头（保证分数正常）
        ma_bullish = ma_short_bull

        # 标准：MA5 环比昨日斜率（主流趋势判断口径）
        score = 0
        direction = ""
        print("ma5_slope: ", ma5_slope, "ma_bullish: ", ma_bullish, "ma5_5days_ago: ", pre_ma5,"current['MA5']: ", current['MA5'])

        # ✅ 分级合理，不会批量低分
        if ma_short_bull:
            if ma5_slope > 2:
                score = 85
                direction = '短期加速上涨'
            elif 0.5 < ma5_slope <= 2:
                score = 100
                direction = '强势主升'
            elif 0 < ma5_slope <= 0.5:
                score = 90
                direction = '温和多头'
            elif -0.5 < ma5_slope <= 0:
                # 小幅负斜率：高位正常休整
                score = 85
                direction = '多头休整(高位震荡)'
            else:
                # 斜率 < -0.5：均线明显走弱
                score = 70
                direction = '多头转弱'

        return {
            'score': score, 
            'direction': direction,
            'ma_bullish': ma_bullish, 
            'ma5_slope': round(ma5_slope, 2)
        }
    def _get_5d_max_drawback(self, df: pd.DataFrame, idx: int) -> float:
        """
        近5日区间最高价 → 当日最高价 回落幅度
        风控：盘中冲高乏力、连续冲高越来越弱、假突破
        """
        if idx < 5:
            return 0.0
        recent = df.iloc[idx-5:idx+1]
        high_series = recent["close"]
        peak_high = high_series.max()
        current_high = high_series.iloc[-1]
        return (peak_high - current_high) / peak_high

    def _analyze_pullback(self, df: pd.DataFrame, breakout: Dict, idx: int) -> Dict:
        """
        回踩确认分析
        核心逻辑：20日内曾冲高前高 + 中途出现回调休整 → 判定为健康突破
        过滤：一路单边上涨、无回调的连续拉升行情
        """
        prev_high = breakout['highest_price']
        prev_high_idx = breakout['highest_price_idx']


        window = 20  # 和prev_high保持一致：20日窗口
        start = max(0, idx - window)
        
        # 1. 整个20日区间的高低价
        win_high_series = df['high'].iloc[start:idx]
        win_low_series = df['low'].iloc[start:idx]
        win_max = win_high_series.max()
        win_min = win_low_series.min()
        
        # 条件1：20日内曾经冲高到阶段前高（有前期试盘/冲高动作）
        has_pre_break = (win_high_series >= prev_high).any()
        #print("win_high_series: ", win_high_series, has_pre_break)
        has_callback = False

         # 2. 计算回调阈值，判断区间内是否出现有效回落
        if breakout['high_ratio'] >= 0.98:
            line = 0.985
        else:
            line = 0.97
        
        if idx - prev_high_idx >= 3:  # 冲高和回调至少间隔3天，避免假突破
            has_callback = win_min < win_max * line


        real_pullback_confirm = has_pre_break and has_callback
        print("has_callback: ", has_callback)

        breakout_pct = breakout['breakout_ratio'] * 100
        print("breakout_pct: ", breakout_pct)
        # 原有分级打分不变
        if breakout_pct >=5 and real_pullback_confirm:
            confirmed=True; score=95; status='二次突破+回踩确认(重仓首选)'
        elif breakout_pct >=3 and real_pullback_confirm:
            confirmed=True; score=85; status='有效突破+回踩确认'
        elif breakout_pct >=2 and real_pullback_confirm:
            confirmed=True; score=70; status='标准突破+回踩确认'
        elif breakout_pct >=5:
            confirmed=False; score=78; status='单日强突无回调'
        elif breakout_pct >=3:
            confirmed=False; score=40; status='温和突破无回调'
        else:
            confirmed=False; score=30; status='突破偏弱'
      
        return {
            'score': score, 'confirmed': confirmed,
            'pullback_pct': round(breakout_pct,2), 'status': status,
            'real_pullback_confirm': real_pullback_confirm
        }

    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        try:
            from scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from scanner import scan_all_stocks as scanner
        return scanner(self, top_n)
           
    def find_breakout(self, df: pd.DataFrame) -> Optional[Dict]:
        """突破识别 + 区分高位趋势加速与高位诱多（绿的谐波放行）"""
        if len(df) < self.lookback_days +5:
            print('数据不足，无法分析')
            return None
        
        df = self._calculate_indicators(df)
       # print(df)
       # print("test")
        #print("test: ", df['MA5'], df['MA10'], df['MA20'], df['MA60'], df['upper_shadow'], df['volume'], df['volume_ma5'], df['volume_ma20'], df['previous_high']  )
        i = len(df)-1
        # print("i : ", i )
        current = df.iloc[i]
        current_high = current['close']
        current_close = current['close']
        #print("current_high: ", current_high, "current_close: ",current_close)
        # 10日阶段高点
        high_window = df['close'].iloc[max(0, i-self.lookback_days):i]
        stage_high = high_window.max()
        # print("stage_high: ", stage_high, high_window.idxmax())
        # 全段历史最高价
        history_total_high = df['close'].max()
        print("history_total_high: ", history_total_high, "stage_high: ", stage_high, "current_high: ", current_high)
        high_ratio = current_close / history_total_high
        # print("history_total_high: ", history_total_high)
        # 基础突破判定
        if current_high < stage_high * (1 + self.breakout_threshold):
            print('未突破前期高点', f"当前高点: {current_high:.2f}, 阶段高点: {stage_high:.2f}")
            return None

        # 单日涨幅（用于强突破判定）
        daily_up_pct = (current_close - df['close'].iloc[i-1]) / df['close'].iloc[i-1] if i>=1 else 0

        # 1. 绝对高危区：98%以上 无强趋势才过滤（改：98%）
        if high_ratio >= self.high_risk_zone:
            # # 改：放宽趋势判定 + 单日大涨直接放行
            # trend_ok = (current['MA5'] > current['MA10']) and (current['MA5'] > current['MA20'])

            close_stand_ma5 = current_close > current['MA5']
            ma5_over_ma20 = current['MA5'] > current['MA20']
            # 附加兜底：MA10向上，防止单边下跌中途反弹诱多
           # pre_ma10 = df['MA10'].iloc[i-1] if i>=1 else 0
           # print(df['MA10'].iloc[i-1]," ", df['MA10'].iloc[i])
           # ma10_up = current['MA10'] > pre_ma10
            trend_ok = close_stand_ma5 and ma5_over_ma20


            vol_ratio_val = (current['volume'] / df['volume'].iloc[i-5:i].mean()) 
            print("vol_ratio_val: ", vol_ratio_val)
            vol_ok = vol_ratio_val >= (self.strong_trend_vol_ratio)
            print("self._get_5d_max_drawback(df, i): ", self._get_5d_max_drawback(df, i))
            if high_ratio >= 0.98:
                draw_ok = self._get_5d_max_drawback(df, i) <= 0.24
            else:
                draw_ok = self._get_5d_max_drawback(df, i) <= 0.18
            break_ok = ((current_close - stage_high)/stage_high)>=self.strong_trend_break_ratio#or (daily_up_pct >= self.strong_daily_up)
            print("current_close - stage_high)/stage_high: ", (current_close - stage_high)/stage_high, "daily_up_pct: ", daily_up_pct)
            
            print(trend_ok, vol_ok, draw_ok, break_ok)
            if not (trend_ok and vol_ok and draw_ok and break_ok):
                fail_reasons = []
                if not trend_ok: fail_reasons.append("趋势不达标")
                if not vol_ok: fail_reasons.append(f"量比不足({vol_ratio_val:.2f}<{self.strong_trend_vol_ratio-0.03})")
                if not draw_ok: fail_reasons.append(f"回撤过大({self._get_5d_max_drawback(df,i):.1%})")
                if not break_ok: fail_reasons.append("突破幅度不足")
                print(f"🚫 高位过滤: {'; '.join(fail_reasons)}")
                return None
            else:
                print(f"✅ 距历史新高近但强趋势主升浪，放行")

        # 区间标记
        near_history = False
        trend_high_accelerate = False
        if high_ratio >= self.trend_break_zone:
            near_history = True
            if high_ratio >= self.trend_break_zone and ((current['MA5'] > current['MA10']) and (current['MA5'] > current['MA20'])):
                trend_high_accelerate = True

        # 量能计算
        vol_avg = df['volume'].iloc[max(0, i-20):i].mean()
        vol_ratio = current['volume'] / vol_avg if vol_avg>0 else 0
        momentum_5d = (current_close - df['close'].iloc[i-5])/df['close'].iloc[i-5] if i>=5 else 0

        trend_res = self._analyze_trend(df, i)
        breakout_base = {
            'breakout_price': current_close,
            'highest_price': stage_high,
            'highest_price_idx':high_window.idxmax(),
            'breakout_ratio': (current_close - stage_high)/stage_high,
            'current_high': current_high,
            'upper_shadow_ratio': round(current['upper_shadow'],3),
            'high_ratio': round(high_ratio,3)

        }
        pull_res = self._analyze_pullback(df, breakout_base, i)

        # -------- 新增：趋势新高主升浪标记（拓荆专用） --------
       # 新版：趋势新高主升浪标记（放在 pull_res 赋值之后）
        is_trend_new_high = (
            trend_res['ma_bullish']
            and trend_res['ma5_slope'] > 1    # 0.5 → 1.0
            and high_ratio >= 0.95
            and breakout_base['breakout_ratio'] >= 0.012
        )

        return {
            'index': i,
            'date': df.index[i],
            'breakout_price': current_close,
            'highest_20d': stage_high,
            'breakout_ratio': breakout_base['breakout_ratio'],
            'upper_shadow_ratio':breakout_base['upper_shadow_ratio'],
            'volume_ratio': vol_ratio,
            'momentum_5d': momentum_5d,
            'ma_bullish': trend_res['ma_bullish'],
            'ma5_slope': trend_res['ma5_slope'],
            'trend_direction': trend_res['direction'],
            'is_trend_new_high': is_trend_new_high,
            'pullback_confirmed': pull_res['confirmed'],
            'pullback_status': pull_res['status'],
            'near_history_high': near_history,
            'trend_high_accelerate': trend_high_accelerate,
            'history_high': round(history_total_high,2),
            'high_ratio': round(high_ratio,3)
        }

    def calculate_score(self, breakout: Dict, market_data=None) -> Tuple[float, str]:
        """六维评分 + 趋势新高加分/扣分区分"""
        reasons = []
        # 统一提取标记与基础变量
        is_trend = breakout.get('is_trend_new_high', False)
        ratio = breakout['breakout_ratio']
        print("breakout_ratio: ", ratio)
        vol_ratio = breakout['volume_ratio']
        print("vol_ratio: ", vol_ratio)
        ma_bullish = breakout.get('ma_bullish', False)
        ma5_slope = breakout.get('ma5_slope', 0)
        upper_shadow_ratio =  breakout.get('upper_shadow_ratio', 0.0)
       # ===================== 形态标签 & 基础档位 =====================

        # 标记四大盘口类型
        pattern_type = ""
        # 1 光头无长上影
        if upper_shadow_ratio < 0.05:
            if vol_ratio > 1.0:
                pattern_type = "放量强势突破"
            else:
                pattern_type = "缩量控盘突破"
        # 2 中等上影
        elif 0.05 <= upper_shadow_ratio < 0.15:
            if vol_ratio > 1.0:
                pattern_type = "放量正常突破"
            else:
                pattern_type = "缩量弱突破"
        # 3 长上影
        else:
            if vol_ratio > 1.0:
                pattern_type = "放量分歧突破"
            else:
                pattern_type = "缩量诱多突破"
        print("pattern_type: ", upper_shadow_ratio, pattern_type, vol_ratio, is_trend)


        if ratio > 0.04:
            if pattern_type in ("放量强势突破", "缩量控盘突破"):
                # 缩量控盘形态额外加高2分溢价
                if pattern_type == "缩量控盘突破":
                    br = 92
                    reasons.append("突破力度极强，缩量光头筹码锁定，形态极佳")
                else:
                    br = 90
                    reasons.append("突破力度极强，放量光头形态健康")
            elif pattern_type in ("放量分歧突破", "缩量诱多突破"):
                br = 78
                reasons.append("盘中强突，长上影分歧抛压大")
            elif pattern_type == "放量正常突破":
                br = 85
                reasons.append("突破力度极强，中等上影换手良性")
            else: # 缩量弱突破
                br = 82
                reasons.append("突破力度极强，中等上影缩量承接偏弱")
        elif ratio > 0.02:
            if pattern_type in ("放量强势突破", "缩量控盘突破"):
                if pattern_type == "缩量控盘突破":
                    br = 84
                    reasons.append("突破力度较强，缩量控盘站稳前高")
                else:
                    br = 82
                    reasons.append("突破力度较强，放量收盘站稳")
            elif pattern_type in ("放量分歧突破", "缩量诱多突破"):
                br = 68
                reasons.append("突破力度较强，冲高回落存在分歧")
            elif pattern_type == "放量正常突破":
                br = 80
                reasons.append("突破力度较强，换手温和")
            else: # 缩量弱突破
                br = 76
                reasons.append("突破力度较强，缩量支撑一般")
        elif ratio > 0.01:
            if pattern_type in ("放量强势突破", "缩量控盘突破"):
                if pattern_type == "缩量控盘突破":
                    br = 72
                    reasons.append("突破力度良好，控盘趋势扎实")
                else:
                    br = 70
                    reasons.append("突破力度良好，放量形态扎实")
            elif pattern_type in ("放量分歧突破", "缩量诱多突破"):
                br = 52  # 原48小幅上调，缩小断层
                reasons.append("突破幅度一般，长上影承压明显")
            elif pattern_type == "放量正常突破":
                br = 65
                reasons.append("突破力度良好，小幅换手分歧")
            else: # 缩量弱突破
                br = 61
                reasons.append("突破力度一般，缩量支撑偏弱")
        elif ratio > 0.005:
            br = 55
            reasons.append("小幅突破，临界有效，高度有限")
        else:
            br = 45
            reasons.append("几乎未突破，假突破风险高")


        # 2.量能确认
        if vol_ratio>1.2:
            vr=95; reasons.append("成交量大幅放大")
        elif vol_ratio>1.0:
            vr=85; reasons.append("成交量明显放大")
        elif vol_ratio>0.7:
            vr=60; reasons.append("成交量温和放大")
        else:
            vr=30; reasons.append("成交量未明显放大")


       # 3. 量价形态综合 pr
        if pattern_type == "缩量控盘突破":
            pr = 92
            reasons.append("缩量光头新高，筹码高度锁定，主升优质形态")
        elif pattern_type == "放量强势突破":
            pr = 88
            reasons.append("放量光头突破，资金合力进攻，量价共振")
        elif pattern_type == "放量正常突破":
            pr = 68
            reasons.append("中等上影+放量，换手良性小幅分歧")
        elif pattern_type == "缩量弱突破":
            pr = 60
            reasons.append("中等上影+缩量，承接力度偏弱")
        elif pattern_type == "放量分歧突破":
            pr = 42
            reasons.append("放量长上影，场内分歧巨大，抛压较重")
        elif pattern_type == "缩量诱多突破":
            pr = 28
            reasons.append("缩量长上影，冲高无承接，诱多风险高")


        print("ma5_slope: ", ma5_slope, "ma_bullish: ", ma_bullish, "is_trend: ", is_trend)
        # 3.趋势配合（原逻辑完全保留）
        if ma_bullish and ma5_slope>1:
            tr=95
            reasons.append("均线多头向上，趋势陡峭，主升力度强")
        elif ma_bullish:
            tr=80
            reasons.append("均线多头排列，整体趋势向好")
        elif breakout.get('momentum_5d',0)>0:                                                                   
            tr=55
            reasons.append("短期动量偏强，中期趋势一般")
        else:                                                       
            tr=40
            reasons.append("趋势偏弱，上行动力不足")
            # 新增：趋势主升浪不再重复追加趋势描述
        if not is_trend:
            reasons.append(f"{breakout.get('trend_direction','')}")
        ts = tr * self.weights['trend_cooperation']

        # 5.回踩结构得分
        pull_status = breakout.get('pullback_status','')
        if '回踩确认' in pull_status:
            par=88
            reasons.append("前期回踩充分，支撑有效，突破可靠性高")
        elif '强突' in pull_status:
            par=82
            reasons.append("无明显回踩，直接强势上攻，进攻意愿足")
        elif '突破' in pull_status:
            par=65
            reasons.append("阶段性突破成型，结构中等偏稳")
        else:
            par=40
            reasons.append("回踩/突破结构混乱，形态支撑不足")
        # 权重加权计算
        bs = br * self.weights['breakout_strength']
        vs = vr * self.weights['volume_confirm']
        ps = pr * self.weights['pattern_quality']
        pas = par * self.weights['pullback_confirmation']
        # 6.市场环境
        ms = 50 * self.weights['market_environment']
        total = bs + vs + ts + ps + pas + ms
        
        # 通用硬扣分
        if total >=75 and vol_ratio <1.0:
            total -=8
        if total >=80 and not ma_bullish:
            total -=10
        
        # 高位区间差异化处理
        near_high = breakout.get('near_history_high',False)
        trend_acc = breakout.get('trend_high_accelerate',False)
        high_ratio = breakout.get('high_ratio', 0.0)
        print("near_high: ", near_high, "trend_acc: ", trend_acc, "high_ratio: ", high_ratio, "is_trend: ", is_trend)
        if near_high and not is_trend:
            if high_ratio >= self.high_risk_zone:
                # 98% 以上：只对“无量+无趋势”严扣，放量强趋势只轻扣
                if trend_acc and breakout['volume_ratio'] >= 0.8:
                    total -= 2
                    reasons.append("历史新高·强趋势加速(极小扣)")
                else:
                    total -= 8
                    reasons.append("历史新高·无量弱势(强扣，规避诱多)")
            elif high_ratio >= 0.90:
                # 90%~95%：强趋势不扣，弱趋势扣
                if trend_acc:
                    reasons.append("90%~95%·强趋势(不扣分)")
                else:
                    total -= 3
                    reasons.append("90%~95%·无趋势(轻扣)")
            elif trend_acc:
                # 高位+长上影 额外加扣
                if upper_shadow_ratio >= 0.08:
                    total -= 4
                    reasons.append("90%~95%高位+长上影分歧，额外扣分")
                else:
                    reasons.append("90%~95%·趋势加速主升(不扣分)")
            else:
                # 90%~95% 无趋势 → 小扣
                total -= 3
                reasons.append("90%~95%·高位震荡(轻扣)")
        else:
            if near_high:
                reasons.append("接近历史新高，需关注后续走势")
     
        # 中段小幅加分
        if 0.50 < high_ratio < 0.90:
            total += 3
            reasons.append("距离历史高点存在空间，上方抛压较小，+3分")
        # 低位大幅远离前高，仅均线多头加分
        elif high_ratio <= 0.50 and ma_bullish:
            total += 6
            reasons.append("大幅远离历史高点，套牢盘少，多头趋势，+6分")
        
        return round(total,1), "; ".join(reasons)

    def _calculate_market_environment_score(self, breakout, market_data=None):
        return {'score':50, 'reason':'市场中性'}

    def analyze_stock(self, stock_code: str, stock_name: str=None) -> Optional[Dict]:
        """单只个股完整分析（2026-09-12 改用 get_stock_realtime）"""
        try:
            realtime = None  # 实时行情
            df = None
            # 优先用 get_stock_realtime（腾讯实时 + 新浪/腾讯 K 线）
            if _HAS_REALTIME and get_stock_realtime is not None:
                try:
                    df, realtime = get_stock_realtime(stock_code)
                    if df is not None and len(df) > 0:
                        df = df.rename(columns={'day': 'date'})
                except Exception as _e:
                    print(f"[get_stock_realtime 失败] {stock_code}: {_e}，回退到 adapter")
                    df = None

            # fallback：DataSourceAdapter
            if (df is None or len(df) < self.lookback_days + 5) and self.data_adapter is not None:
                df = self.data_adapter.get_stock_data(stock_code)
                if df is not None and len(df) >= self.lookback_days + 5:
                    name_map = [
                        ('收盘价', 'close'), ('Close', 'close'), ('CLOSE', 'close'),
                        ('最高价', 'high'), ('High', 'high'), ('HIGH', 'high'),
                        ('成交量', 'volume'), ('Volume', 'volume'), ('vol', 'volume')
                    ]
                    for old, new in name_map:
                        if old in df.columns and new not in df.columns:
                            df[new] = df[old]

            if df is None or len(df) < self.lookback_days + 5:
                return None

            print("stock name: ", stock_name, " code: ", stock_code)
            breakout = self.find_breakout(df)
            print("breakout: ", breakout)
            if not breakout:
                return None

            score, reasons = self.calculate_score(breakout)
            print("score: ", score, "reasons: ", reasons)
            current = df.iloc[-1]

            # 标注操作模式
            mode_tag = "稳健重仓" if breakout['pullback_confirmed'] else "趋势轻仓"

            result = {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'score': score,
                'reasons': reasons,
                'operate_mode': mode_tag,
                'current_price': round(current['close'], 2),
                'breakout_price': round(breakout['breakout_price'], 2),
                'highest_20d': round(breakout['highest_20d'], 2),
                'history_high': breakout['history_high'],
                'high_ratio': breakout['high_ratio'],
                'breakout_ratio': round(breakout['breakout_ratio'] * 100, 2),
                'volume_ratio': round(breakout['volume_ratio'], 2),
                'ma_bullish': breakout['ma_bullish'],
                'trend_direction': breakout['trend_direction'],
                'pullback_confirmed': breakout['pullback_confirmed'],
                'pullback_status': breakout['pullback_status'],
                'strategy': self.name,
                'win_rate': self.win_rate,
            }

            # 实时行情补充
            if realtime:
                result['realtime'] = {
                    'open': realtime.get('open'),
                    'high': realtime.get('high'),
                    'low': realtime.get('low'),
                    'chg_pct': realtime.get('chg_pct'),
                    'volume_ratio': realtime.get('volume_ratio'),
                    'turnover': realtime.get('turnover'),
                }
                if realtime.get('price'):
                    result['current_price'] = realtime['price']

            return result
        except Exception as e:
            return None





if __name__ == '__main__':
    analyzer = BreakoutHighAnalyzer()
    # 测试标的：包含稳健票+趋势新高票（绿的谐波已放行）
    test_stocks = [
       # ('鸣志电器','603728'),
       # ('中航光电','002179'),
         #('绿的谐波','688017'),
        #('科士达','002518'),
       # ('中国西电','601179'),
       # #  ('生益科技','600183'),
         # ('三环集团','300408'),
          #('双星新材','002585'),
         # ('兴森科技','002436'),
         # ('南亚新材','688519')
         #('长电科技','600584')
        # ('深科技','000021'),
        # ('凯莱英','002821'),
        # ('恒瑞医药','600276'),
        # ('药明康德','603259'),
         #('德明利', '001309')
         #('中远海能', '600026')
         # ('招商轮船', '601872'),
         #('招金黄金','000506')
         #('佰维存储','688525')
         #('中科曙光', '603019'),
         ('润泽科技', '300442'),
        ('迈为股份', '300751')
    ]
    # import tushare as ts

    # pro = ts.pro_api("1e0a173e009efcce67d97a14b9e5639302ee100db8f1014de1520183")
    # df = pro.daily(ts_code="688087.SH", start_date="20260101", end_date="20260607")
   # import finshare as fs

    #df = fs.get_historical_data("688087.SZ", start="2026-06-01", end="2026-06-07")
    #print(df.columns)
    print(f"===== {analyzer.name} {analyzer.version} =====")
    for name, code in test_stocks:
        res = analyzer.analyze_stock(code, name)
        if res:
            print(f"\n【{name}】得分:{res['score']} | 操作模式:{res['operate_mode']}")
            print(f"现价:{res['current_price']} 历史新高:{res['history_high']} 高位占比:{res['high_ratio']*100:.1f}%")
            print(f"突破幅度:{res['breakout_ratio']}% 量比:{res['volume_ratio']}")
            print(f"结构状态:{res['pullback_status']}")
            print(f"逻辑:{res['reasons']}")
        else:
            print(f"\n【{name}】未满足入场条件")