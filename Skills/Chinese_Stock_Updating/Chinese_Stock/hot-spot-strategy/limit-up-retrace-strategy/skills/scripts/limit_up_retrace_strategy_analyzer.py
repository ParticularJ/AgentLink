#!/usr/bin/env python3
"""
涨停板首次回调策略分析器 v2.1.0 实盘优化版
核心逻辑：首板/连板后首次缩量回调 + 止跌信号确认，适配A股全板块规则
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import yaml

# 导入数据源适配器
try:
    from data_source_adapter import DataSourceAdapter
except ImportError:
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../data-strategy/skills/scripts')
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        sys.path.insert(0, os.path.join(os.getcwd(), 'data-strategy/skills/scripts'))
        from data_source_adapter import DataSourceAdapter


class LimitUpRetraceAnalyzer:
    """涨停板首次回调分析器 - 实盘优化版"""

    def __init__(self, data_source: str = "auto", config: Optional[Dict] = None):
        self.name = "涨停板首次回调策略"
        self.version = "v2.1.0"

        # 初始化数据源
        self.data_adapter = DataSourceAdapter()
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")

        # ========== 可配置策略参数（默认值为经过回测的较优参数）==========
        default_config = {
            # 涨停回溯范围
            "lookback_days": 10,               # 查找近N天内的涨停
            # 回调范围约束
            "min_retrace_pct": 5.0,            # 最小回调幅度（低于则视为洗盘不充分）
            "max_retrace_pct": 20.0,           # 最大回调幅度（超过则视为破位）
            "min_retrace_days": 1,             # 最小回调天数
            "max_retrace_days": 7,             # 最大回调天数（超过则资金热度消退）
            # 过滤条件
            "enable_trend_filter": True,       # 开启趋势过滤（20日均线向上）
            "enable_liquidity_filter": True,   # 开启流动性过滤
            "min_avg_amount": 50000000,        # 近5日日均成交额下限（单位：元，默认5000万）
            # 信号阈值
            "strong_buy_score": 85,            # 强烈买入分数线
            "buy_score": 75,                   # 买入分数线
            "watch_score": 65,                 # 关注分数线
            # 风控参数
            "stop_loss_pct": 3.0,              # 止损幅度（回调低点下浮比例）
            "take_profit_pct": None,           # 止盈幅度，None则默认以涨停价为第一止盈位
        }
        # 合并用户配置
        self.config = default_config
        if config:
            self.config.update(config)

    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名候选标的"""
        try:
            from limit_up_retrace_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from limit_up_retrace_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)

    # ===================== 核心工具方法 =====================
    def _get_limit_up_threshold(self, stock_code: str, stock_name: str = None) -> float:
        """根据股票代码/名称判断所属板块，返回对应涨停阈值"""
        code = stock_code.replace('.', '').replace('sh', '').replace('sz', '').strip()

        # ST股优先判断（5%涨跌幅）
        if stock_name and ('ST' in stock_name or 'st' in stock_name):
            return 4.5

        # 按代码前缀判断板块
        if code.startswith('688') or code.startswith('689'):  # 科创板
            return 19.0
        elif code.startswith('300') or code.startswith('301'):  # 创业板
            return 19.0
        elif code.startswith('8') or code.startswith('4'):  # 北交所
            return 29.0
        else:  # 沪深主板
            return 9.5

    def _is_first_retrace(self, df: pd.DataFrame, zt_idx: int) -> bool:
        """判断是否为涨停后的首次回调
        核心标准：涨停后无收盘价超过涨停收盘价，无新高，持续回落
        """
        post_zt = df.iloc[zt_idx + 1:]
        if len(post_zt) == 0:
            return False

        zt_close = df.iloc[zt_idx]['close']

        # 涨停后未出现收盘价突破涨停价、未刷新阶段高点
        max_post_close = post_zt['close'].max()

        return max_post_close < zt_close

    # ===================== 评分体系（重构版） =====================
    def _calculate_retrace_score(self, retrace_pct: float) -> float:
        """回调幅度得分 (0-35分) 8%-15%为最优区间"""
        if retrace_pct < self.config['min_retrace_pct']:
            return 0.0  # 回调不足，洗盘不充分
        elif 5 <= retrace_pct < 8:
            return (retrace_pct - 5) * 10  # 0~30分线性递增
        elif 8 <= retrace_pct <= 15:
            return 35.0  # 最优区间
        elif 15 < retrace_pct <= self.config['max_retrace_pct']:
            return max(0, 35 - (retrace_pct - 15) * 7)  # 35~0分快速递减
        else:
            return 0.0  # 回调过深，破位走弱

    def _calculate_shrink_score(self, shrink_pct: float) -> float:
        """缩量得分 (0-25分) 40%-60%为最优缩量区间"""
        if shrink_pct < 0:  # 放量回调，资金出逃，直接0分
            return 0.0
        elif 0 <= shrink_pct < 30:
            return shrink_pct * 0.7  # 0~21分线性递增
        elif 30 <= shrink_pct < 40:
            return 21 + (shrink_pct - 30) * 0.4  # 21~25分
        elif 40 <= shrink_pct <= 60:
            return 25.0  # 最优区间
        elif 60 < shrink_pct <= 75:
            return 25 - (shrink_pct - 60) * 0.67  # 25~15分递减（过度缩量流动性不足）
        else:
            return 10.0  # 极度缩量，启动难度大，保底低分

    def _calculate_stop_signal_score(self, df: pd.DataFrame) -> Tuple[float, str]:
        """止跌信号得分 (0-20分) 结合近3根K线组合+量能双重校验，过滤诱多假信号"""
        if len(df) < 3:
            return 0.0, '数据不足'

        # 取最近3根K线：k1前前，k2前一日，k3当日
        k1 = df.iloc[-3]
        k2 = df.iloc[-2]
        k3 = df.iloc[-1]

        # 计算单根K线基础形态信息
        def get_kline_info(k):
            amp = k['high'] - k['low']
            if amp <= 0:
                # 一字停牌无波动，直接返回空形态
                return 0, 0, 0, 0, False, k['volume']
            body = abs(k['close'] - k['open'])
            upper_shadow = k['high'] - max(k['open'], k['close'])
            lower_shadow = min(k['open'], k['close']) - k['low']
            is_yang = k['close'] > k['open']
            vol = k['volume']
            return body, amp, upper_shadow, lower_shadow, is_yang, vol

        b3, amp3, us3, ls3, y3, v3 = get_kline_info(k3)
        b2, amp2, us2, ls2, y2, v2 = get_kline_info(k2)
        _, amp1, _, _, _, v1 = get_kline_info(k1)

        # 1. 标准缩量阳包阴（最强反转，满分20）
        if not y2 and y3:
            # 形态覆盖：阳线收盘超过阴线开盘，阳线开盘低于阴线收盘
            cover_cond = (k3['close'] > k2['open']) and (k3['open'] < k2['close'])
            # 缩量约束：阳线量能小于前一日阴线，抛压衰竭
            vol_cond = v3 < v2
            if cover_cond and vol_cond:
                return 20.0, '缩量阳包阴'

        # 2. 连续2根缩量小阳线，低点逐步抬高（稳健企稳）
        if y2 and y3:
            small_body_2 = (b2 < amp2 * 0.3) and (b3 < amp3 * 0.3)
            low_up = k3['low'] > k2['low']
            shrink_vol = v2 < v1 and v3 < v2
            if small_body_2 and low_up and shrink_vol:
                return 17.0, '双小阳缩量企稳'

        # 3. 锤子线 + 次日收小阳确认（单根锤子容易诱多，增加次日验证）
        hammer_single = (ls3 > b3 * 2) and (us3 < b3 * 0.5) and amp3 > 0
        # 前一根收阳确认支撑有效
        if hammer_single and y2 and v3 < v2:
            return 14.0, '锤子线次日确认'

        # 4. 缩量十字星
        if amp3 > 0 and b3 < amp3 * 0.1 and v3 < v2:
            return 11.0, '缩量十字星'

        # 5. 单日缩量小阳线（最弱止跌信号）
        if y3 and b3 < amp3 * 0.3 and v3 < v2:
            return 8.0, '单日缩量小阳线'

        # 无有效止跌组合，删除多余print打印
        return 0.0, '无明显止跌信号'

    def _calculate_recent_strength_score(self, retrace_pct: float, days_since_zt: int) -> float:
        """近期强度得分 (0-20分) 时间越近、回调越浅，资金热度越高"""
        if days_since_zt <= 3 and retrace_pct <= 10:
            return 20.0
        elif days_since_zt <= 5 and retrace_pct <= 15:
            return 14.0
        elif days_since_zt <= 7 and retrace_pct <= 18:
            return 8.0
        else:
            return 0.0

    # ===================== 主分析逻辑 =====================
    def analyze_stock(self, stock_code: str, stock_name: str = None) -> Optional[Dict]:
        """
        分析单只股票是否出现涨停后首次回调买入信号
        Args:
            stock_code: 股票代码
            stock_name: 股票名称（用于ST判断）
        Returns:
            分析结果字典，不符合条件返回None
        """
        try:
            # 1. 获取历史数据（至少30个交易日，保证均线和量能统计有效）
            df = self._get_stock_data(stock_code)
           
            if df is None or len(df) < 30:
                return None

            # 2. 计算技术指标
            df = self._calculate_indicators(df)
            # print(df)
            # 3. 前置过滤：趋势过滤 + 流动性过滤
            if not self._pass_base_filter(df, stock_code):
                print("基础指标不达标")
                return None

            # 4. 获取对应板块的涨停阈值
            zt_threshold = self._get_limit_up_threshold(stock_code, stock_name)

            # 5. 识别近期涨停
            limit_up_info = self._find_recent_limit_up(df, zt_threshold)
            if not limit_up_info:
                return None

            zt_idx = limit_up_info['index']

            # 6. 校验：是否为首次回调
            if not self._is_first_retrace(df, zt_idx):
                print("非首次回调")
                return None

            # 7. 分析回调情况
            retrace_info = self._analyze_retrace(df, limit_up_info)
            if not retrace_info['is_retracing']:
                print("非有效回调")
                return None

            # 8. 分析量能（缩量程度）
            volume_info = self._analyze_volume(df, limit_up_info)
            print(volume_info)
            # 9. 分析止跌信号
            stop_score, stop_signal = self._calculate_stop_signal_score(df)
            print("stop_score: ", stop_score, ", stop_signal: ", stop_signal)

            # 10. 分析支撑位与压力位
            support_info = self._analyze_support(df, limit_up_info, retrace_info)
            print("support_info: ", support_info)
            # 11. 计算综合得分
            retrace_score = self._calculate_retrace_score(retrace_info['retrace_pct'])
            shrink_score = self._calculate_shrink_score(volume_info['shrink_pct'])
            recent_strength_score = self._calculate_recent_strength_score(
                retrace_info['retrace_pct'], retrace_info['days_since_zt']
            )
            total_score = retrace_score + shrink_score + stop_score + recent_strength_score
            print("total_score: ", total_score)
            # 12. 信号分级判断
            if total_score < self.config['watch_score']:
                return None

            if total_score >= self.config['strong_buy_score']:
                signal = '强烈买入'
            elif total_score >= self.config['buy_score']:
                signal = '买入'
            else:
                signal = '关注'

            # 13. 计算止盈止损位
            risk_info = self._calculate_risk_levels(df, limit_up_info, retrace_info)

            latest = df.iloc[-1]

            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'signal': signal,
                'score': round(total_score, 2),
                'current_price': round(latest['close'], 2),
                # 涨停基础信息
                'limit_up_date': limit_up_info['date'],
                'limit_up_price': round(limit_up_info['price'], 2),
                'limit_up_high': round(limit_up_info['high'], 2),
                # 回调核心数据
                'retrace_pct': round(retrace_info['retrace_pct'], 2),
                'days_since_zt': retrace_info['days_since_zt'],
                # 量能与形态
                'volume_shrink_pct': round(volume_info['shrink_pct'], 1),
                'stop_signal': stop_signal,
                # 支撑压力
                'main_support': round(support_info['main_support_price'], 2),
                'main_support_type': support_info['main_support_type'],
                'pressure_price': round(limit_up_info['close'], 2),
                # 风控点位
                'stop_loss_price': round(risk_info['stop_loss'], 2),
                'take_profit_price': round(risk_info['take_profit'], 2),
                'risk_reward_ratio': round(risk_info['risk_reward_ratio'], 2),
                # 分项得分明细
                'details': {
                    'retrace_score': round(retrace_score, 1),
                    'shrink_score': round(shrink_score, 1),
                    'stop_signal_score': round(stop_score, 1),
                    'recent_strength_score': round(recent_strength_score, 1),
                    'retrace': retrace_info,
                    'volume': volume_info,
                    'support': support_info
                }
            }

        except Exception as e:
            print(f"分析{stock_code}失败: {e}")
            return None

    # ===================== 辅助计算方法 =====================
    def _get_stock_data(self, stock_code: str) -> Optional[pd.DataFrame]:
        """获取股票历史数据（默认前复权）"""
        try:
            df = self.data_adapter.get_stock_data(stock_code)
            if df is None or df.empty:
                return None
            # 确保按日期升序排列
            df = df.sort_values('date').reset_index(drop=True)
            return df
        except Exception as e:
            print(f"获取{stock_code}数据失败: {e}")
            return None

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标：均线、均量、成交额"""
        # 价格均线
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        # 成交量均线
        df['vol_ma5'] = df['volume'].rolling(window=5).mean()
        # 计算涨跌幅
        df['pct_change'] = df['close'].pct_change() * 100
        # 估算成交额（若无amount字段）
        if 'amount' not in df.columns:
            df['amount'] = df['close'] * df['volume']
        df['amount_ma5'] = df['amount'].rolling(window=5).mean() *100
        return df

    def _pass_base_filter(self, df: pd.DataFrame, stock_code: str) -> bool:
        """基础过滤：趋势 + 流动性"""
        latest = df.iloc[-1]

        # 趋势过滤：20日均线向上 + 股价在20日均线上方
        if self.config['enable_trend_filter']:
            if pd.isna(latest['MA20']):
                return False
            # 20日均线拐头向上
            ma20_prev = df.iloc[-5]['MA20']
            if latest['MA20'] <= ma20_prev:
                return False
            # 股价站在20日均线上方
            if latest['close'] < latest['MA20']:
                return False
        print("20日均线向上 + 股价在20日均线上方", latest['amount_ma5'])
        # 流动性过滤：近5日日均成交额达标
        if self.config['enable_liquidity_filter']:
            if pd.isna(latest['amount_ma5']) or latest['amount_ma5'] < self.config['min_avg_amount']:
                return False

        return True

    def _find_recent_limit_up(self, df: pd.DataFrame, threshold: float) -> Optional[Dict]:
        """查找近期符合阈值的涨停"""
        lookback = self.config['lookback_days']

        for i in range(1, min(lookback + 1, len(df) - 1)):
            idx = len(df) - i
            if idx < 1:
                continue

            row = df.iloc[idx]
            prev_row = df.iloc[idx - 1]

            # 计算涨幅
            if 'pct_change' in row and not pd.isna(row['pct_change']):
                change_pct = row['pct_change']
            else:
                change_pct = (row['close'] - prev_row['close']) / prev_row['close'] * 100

            # 涨停判断
            if change_pct >= threshold:
                return {
                    'date': row.get('date', idx),
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'price': row['close'],  # 兼容原字段
                    'change_pct': change_pct,
                    'volume': row['volume'],
                    'index': idx
                }

        return None

    def _analyze_retrace(self, df: pd.DataFrame, limit_up_info: Dict) -> Dict:
        """分析回调情况（以涨停日最高价为基准）"""
        latest = df.iloc[-1]
        zt_high = limit_up_info['high']  # 用最高价作为回调基准，更准确
        current_price = latest['close']
        zt_idx = limit_up_info['index']

        # 涨停后所有行情
        post_zt = df.iloc[zt_idx+1:]
        retrace_low = post_zt['low'].min() if len(post_zt) > 0 else current_price

        # 波段高点 = max(涨停当日最高价, 涨停后所有交易日盘中最高价)
        if len(post_zt) > 0:
            wave_high = max(zt_high, post_zt['high'].max())
        else:
            wave_high = zt_high


        # 计算回调幅度
        retrace_pct = (wave_high - current_price) / wave_high * 100
        # 计算距涨停天数
        days_since_zt = len(df) - zt_idx - 1
        print("retrace_pct: ", retrace_pct, ", days: ", days_since_zt)
        # 判断是否为有效回调
        is_retracing = (
            self.config['min_retrace_pct'] <= retrace_pct <= self.config['max_retrace_pct']
            and self.config['min_retrace_days'] <= days_since_zt <= self.config['max_retrace_days']
        )


        return {
            'is_retracing': is_retracing,
            'retrace_pct': retrace_pct,
            'days_since_zt': days_since_zt,
            'zt_high': zt_high,
            'zt_close': limit_up_info['close'],
            'current_price': current_price,
            'retrace_low': retrace_low
        }

    def _analyze_volume(self, df: pd.DataFrame, limit_up_info: Dict) -> Dict:
        zt_idx = limit_up_info['index']
        zt_day_vol = limit_up_info['volume']
        base_vol = zt_day_vol if zt_day_vol > 0 else 1

        post_zt = df.iloc[zt_idx + 1:]
        latest_vol = df.iloc[-1]['volume']

        if len(post_zt) == 0:
            post_avg_vol = base_vol
            shrink_pct = 0
        else:
            post_avg_vol = post_zt['volume'].mean()
            shrink_pct = (1 - post_avg_vol / base_vol) * 100

        # 单根当日相对涨停量
        single_shrink_pct = (1 - latest_vol / base_vol) * 100

        return {
            'shrink_pct': shrink_pct,          # 整体回调缩量率（主指标）
            'single_shrink_pct': single_shrink_pct, # 今日单根缩量率
            'post_avg_vol': post_avg_vol,
            'base_vol': base_vol,
            'zt_day_vol': zt_day_vol,
            'latest_vol': latest_vol
        }

    def _analyze_support(self, df: pd.DataFrame, limit_up_info: Dict, retrace_info: Dict) -> Dict:
        """分析有效支撑位，替代原错误的涨停价支撑"""
        latest = df.iloc[-1]
        current_price = latest['close']
        zt_open = limit_up_info['open']
        zt_close = limit_up_info['close']

        # 候选支撑位列表（价格，类型）
        support_candidates = [
            (zt_open, '涨停开盘价'),
            (((zt_high := limit_up_info['high']) + retrace_info['retrace_low']) / 2, '回调半分位'),
            (latest['MA5'], '5日均线'),
            (latest['MA10'], '10日均线'),
        ]

        # 筛选出当前价格下方的支撑位，找最近的一个
        valid_supports = [(price, typ) for price, typ in support_candidates if price < current_price]
        if not valid_supports:
            return {
                'main_support_price': retrace_info['retrace_low'],
                'main_support_type': '回调低点',
                'all_supports': support_candidates
            }

        # 取距离当前价格最近的支撑
        main_support = max(valid_supports, key=lambda x: x[0])

        return {
            'main_support_price': main_support[0],
            'main_support_type': main_support[1],
            'all_supports': support_candidates
        }

    def _calculate_risk_levels(self, df: pd.DataFrame, limit_up_info: Dict, retrace_info: Dict) -> Dict:
        """计算止盈止损位与盈亏比"""
        current_price = df.iloc[-1]['close']
        retrace_low = retrace_info['retrace_low']

        # 止损位：回调最低点下浮配置的止损比例
        stop_loss = retrace_low * (1 - self.config['stop_loss_pct'] / 100)

        # 止盈位：默认第一止盈为涨停收盘价
        if self.config['take_profit_pct']:
            take_profit = current_price * (1 + self.config['take_profit_pct'] / 100)
        else:
            take_profit = limit_up_info['close']

        # 盈亏比
        risk = current_price - stop_loss
        reward = take_profit - current_price
        rr_ratio = reward / risk if risk > 0 else 0

        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_reward_ratio': rr_ratio
        }


if __name__ == '__main__':
    # 测试示例
    analyzer = LimitUpRetraceAnalyzer(
        data_source='baostock',
        config={
            "min_avg_amount": 30000000,  # 测试放宽流动性到3000万
        }
    )
    result = analyzer.analyze_stock('001270', '铖昌科技')
    if result:
        print(f"股票: {result['stock_name']} ({result['stock_code']})")
        print(f"信号: {result['signal']} | 综合得分: {result['score']}")
        print(f"涨停日期: {result['limit_up_date']} | 回调天数: {result['days_since_zt']}天")
        print(f"当前价: {result['current_price']} | 回调幅度: {result['retrace_pct']}%")
        print(f"缩量比例: {result['volume_shrink_pct']}% | 止跌信号: {result['stop_signal']}")
        print(f"支撑位: {result['main_support']} ({result['main_support_type']})")
        print(f"止损价: {result['stop_loss_price']} | 止盈价: {result['take_profit_price']}")
        print(f"盈亏比: {result['risk_reward_ratio']}")
    else:
        print("当前不符合涨停首次回调策略条件")