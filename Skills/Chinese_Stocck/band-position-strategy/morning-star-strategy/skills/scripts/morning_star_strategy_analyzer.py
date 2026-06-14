# skills/scripts/morning_star_analyzer.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
早晨之星形态分析器
识别和分析早晨之星K线组合形态
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')
from colorama import Fore, Style, init

# 初始化颜色输出
init(autoreset=True)

# 导入数据源适配器
try:
    from data_source_adapter import DataSourceAdapter
except ImportError:
    # 尝试从 ma-bullish-strategy 导入共享的数据源适配器
    adapter_path = os.path.join(os.path.dirname(__file__), '../../../ma-bullish-strategy/skills/scripts')
    sys.path.insert(0, adapter_path)
    try:
        from data_source_adapter import DataSourceAdapter
    except ImportError:
        # 备选：从项目根目录相对导入
        sys.path.insert(0, os.path.join(os.getcwd(), 'ma-bullish-strategy/skills/scripts'))
        from data_source_adapter import DataSourceAdapter


class MorningStarAnalyzer:
    """早晨之星形态分析器"""
    
    def __init__(self, data_source: str = "auto"):
        self.name = "早晨之星形态策略"
        self.version = "v1.0.0"
        self.win_rate = 0.62
        
        # 形态参数
        self.body_ratio_threshold = 0.6  # 实体占比阈值
        self.shadow_ratio_threshold = 0.3  # 影线占比阈值
        
        # 评分权重
        self.weights = {
            'pattern_quality': 0.30,
            'volume_confirm': 0.25,
            'trend_context': 0.20,
            'position_quality': 0.15,
            'market_environment': 0.10
        }
        
        # 初始化数据源
        self.data_adapter = DataSourceAdapter()
        if not self.data_adapter.data_source:
            raise RuntimeError("没有可用的数据源")

    def scan_all_stocks(self, top_n: int = 20) -> List[Dict]:
        """扫描全市场，返回前N名 MACD 底背离候选"""
        try:
            # 延迟导入，避免与模块级别导入循环
            from morning_star_scanner import scan_all_stocks as scanner
        except ImportError:
            sys.path.insert(0, os.path.dirname(__file__))
            from morning_star_scanner import scan_all_stocks as scanner
        return scanner(self, top_n)


    def is_bearish_candle(self, row: pd.Series) -> bool:
        """判断是否阴线"""
        return row['close'] < row['open']

    def is_bullish_candle(self, row: pd.Series) -> bool:
        """判断是否阳线"""
        return row['close'] > row['open']

    def get_body_size(self, row: pd.Series) -> float:
        """获取实体大小"""
        return abs(row['close'] - row['open'])

    def get_upper_shadow(self, row: pd.Series) -> float:
        """获取上影线"""
        return max(row['open'], row['close']) - row['high']

    def get_lower_shadow(self, row: pd.Series) -> float:
        """获取下影线"""
        return row['low'] - min(row['open'], row['close'])

    def find_morning_star(self, df: pd.DataFrame) -> Dict | None:
        """
        判断【最近 3 天】是否形成早晨之星形态
        输入：df 最后3行 = 最近3天K线
        输出：今天的形态信号 / None
        """
        # 必须至少3天数据
        if len(df) < 3:
            return None

        # =======================
        # 只取最近3天
        # =======================
        day1 = df.iloc[-3]  # 第一天（前前天）
        day2 = df.iloc[-2]  # 第二天（昨天）
        day3 = df.iloc[-1]  # 第三天（今天）

        # =======================
        # 条件1：第一天 → 大阴线（处于下跌趋势中）
        # =======================
        # 1.1 必须是阴线
        if not self.is_bearish_candle(day1):
            print(f"Day1 - Not a bearish candle")
            return None

        # 1.2 实体占比要够大（真阴线，非十字星）
        body1 = self.get_body_size(day1)
        total_range1 = day1['high'] - day1['low']
        if total_range1 <= 0:
            return None
        body_ratio1 = body1 / total_range1
        print(f"Day1 - Body Ratio: {body_ratio1:.2f}")
        if body_ratio1 < 0.5:  # 阴线实体占比至少50%
            print(f"Day1 - Body ratio too small: {body_ratio1:.2f}")
            return None

        # 1.3 验证前期趋势（至少看前5根K线，确保处于下跌中）
        if len(df) >= 5:
            prev_close = df.iloc[-6]['close'] if len(df) >= 6 else df.iloc[-4]['open']
            recent_close = df.iloc[-4]['close'] if len(df) >= 6 else day1['open']
            trend_change = (recent_close - prev_close) / prev_close
            print(f"Pre-trend change: {trend_change:.2%}")
            if trend_change > 0.02:  # 前期不能是上涨趋势（允许小反弹）
                print(f"Day1 - Not in downtrend, prev trend: {trend_change:.2%}")
                return None

        # =======================
        # 条件2：第二天 → 星线（小实体 + 明显下影线 + 跳空低开）
        # =======================
        # 2.1 跳空低开（开盘价低于第一天收盘价）
        if day2['open'] >= day1['close'] * 0.98:  # 允许2%容差
            print(f"Day2 - No gap down: open={day2['open']}, day1_close={day1['close']}")
            return None

        # 2.2 星线实体必须小
        body2 = self.get_body_size(day2)
        total_range2 = day2['high'] - day2['low']
        if total_range2 <= 0:
            return None

        body_ratio2 = body2 / total_range2
        print(f"Day2 - Body Ratio: {body_ratio2:.2f}")
        if body_ratio2 > 0.3:  # 实体占比不超过30%（更严格）
            print(f"Day2 - Body too large: {body_ratio2:.2f}")
            return None

        # 2.3 下影线要明显（至少占总振幅50%）
        lower_shadow2 = self.get_lower_shadow(day2)
        lower_shadow_ratio = lower_shadow2 / total_range2
        print(f"Day2 - Lower Shadow Ratio: {lower_shadow_ratio:.2f}")
        if lower_shadow_ratio < 0.5:
            print(f"Day2 - Lower shadow too small: {lower_shadow_ratio:.2f}")
            return None

        # 2.4 星线收盘价应该在第一天收盘价附近或更低（不能反弹太多）
        if day2['close'] > day1['close'] * 1.01:  # 允许1%容差
            print(f"Day2 - Close too high vs day1")
            return None

        # =======================
        # 条件3：第三天 → 大阳线（强势反转确认）
        # =======================
        # 3.1 必须是阳线
        if not self.is_bullish_candle(day3):
            print(f"Day3 - Not a bullish candle")
            return None

        # 3.2 跳空高开（开盘价高于第二天收盘价）
        gap_up = (day3['open'] - day2['close']) / day2['close']
        print(f"Day3 - Gap up: {gap_up:.2%}")
        # 不强求跳空高开，但有跳空加分

        # 3.3 阳线实体占比要够大
        body3 = self.get_body_size(day3)
        total_range3 = day3['high'] - day3['low']
        if total_range3 <= 0:
            print(f"Day3 - Invalid total range")
            return None

        body_ratio3 = body3 / total_range3
        print(f"Day3 - Body Ratio: {body_ratio3:.2f}")
        if body_ratio3 < 0.5:  # 阳线实体至少50%
            print(f"Day3 - Body ratio too small: {body_ratio3:.2f}")
            return None

        # 3.4 上影线不能太长（不能冲高回落）
        upper_shadow3 = self.get_upper_shadow(day3)
        if total_range3 > 0:
            upper_shadow_ratio = upper_shadow3 / total_range3
            if upper_shadow_ratio > 0.3:  # 上影线不超过30%
                print(f"Day3 - Upper shadow too long: {upper_shadow_ratio:.2f}")
                return None

        # =======================
        # 条件4：穿透率（第三天收盘价必须吞没第一天实体50%以上）
        # =======================
        day1_body_range = abs(day1['open'] - day1['close'])
        if day1_body_range > 0:
            # 计算穿透第一根阴线实体的比例
            penetration = (day3['close'] - day1['close']) / day1_body_range
            print(f"Penetration rate: {penetration:.2%}")
            if penetration < 0.5:  # 至少穿透50%
                print(f"Penetration insufficient: {penetration:.2%}")
                return None
        else:
            return None

        # =======================
        # 条件5：整体反弹幅度
        # =======================
        # 用第一天收盘价作为基准更合理
        price_change = (day3['close'] - day1['close']) / day1['close']
        print(f"Price Change (from day1 close): {price_change:.2%}")
        if price_change < 0.02:  # 至少反弹2%
            print(f"Price recovery too small: {price_change:.2%}")
            return None

        # =======================
        # 条件6：量能确认（如果有成交量数据）
        # =======================
        volume_confirmation = False
        if 'volume' in df.columns:
            vol1 = day1.get('volume', 0)
            vol2 = day2.get('volume', 0)
            vol3 = day3.get('volume', 0)
            if vol3 > vol2 and vol3 > vol1:  # 第三天放量
                volume_confirmation = True
                print(f"Volume confirmation: True (day3 > day1 & day2)")
            else:
                print(f"Volume not confirmed, but pattern still valid")

        # =======================
        # 综合评分（可选）
        # =======================
        score = 0
        score += min(body_ratio1 * 40, 40)  # 第一天阴线越大越好
        score += min((1 - body_ratio2) * 20, 20)  # 星线越小越好
        score += min(lower_shadow_ratio * 20, 20)  # 下影线越长越好
        score += min(body_ratio3 * 40, 40)  # 第三天阳线越大越好
        score += min(penetration * 30, 30)  # 穿透率越高越好
        if gap_up > 0:
            score += 10  # 跳空高开加分
        if volume_confirmation:
            score += 10  # 放量加分
        score = min(score, 100)  # 归一化到100

        print(f"Pattern Score: {score:.0f}/100")

        # =======================
        # ✅ 最近3天 = 早晨之星
        # =======================
        return {
            'date': df.index[-1],
            'pattern_type': 'morning_star',
            'day1_open': day1['open'],
            'day1_close': day1['close'],
            'day2_open': day2['open'],
            'day2_close': day2['close'],
            'day2_low': day2['low'],
            'day3_open': day3['open'],
            'day3_close': day3['close'],
            'price_recovery': round(price_change * 100, 2),
            'penetration_rate': round(penetration * 100, 2),
            'body_ratio_day1': round(body_ratio1, 2),
            'body_ratio_day2': round(body_ratio2, 2),
            'body_ratio_day3': round(body_ratio3, 2),
            'gap_down': round((day2['open'] - day1['close']) / day1['close'] * 100, 2),
            'gap_up': round(gap_up * 100, 2),
            'volume_confirmed': volume_confirmation,
            'pattern_score': round(score, 0),
            'is_recent_signal': True
        }


    def calculate_score(self, df: pd.DataFrame, pattern: Dict, market_sentiment: int = None) -> Tuple[float, str]:
        """计算评分"""
        score = 0
        reasons = []
        
        # 1. 形态质量得分 (0-30)
        body_ratio3 = pattern['body_ratio3']
        if body_ratio3 > 0.8:
            score += 30
            reasons.append("第三天阳线实体饱满")
        elif body_ratio3 > 0.6:
            score += 25
            reasons.append("第三天阳线实体较大")
        else:
            score += 20
            reasons.append("早晨之星形态完整")
        
        # 2. 反弹幅度得分 (0-25)
        recovery = pattern['price_recovery']
        if recovery > 5:
            score += 25
            reasons.append(f"反弹幅度大({recovery:.1f}%)")
        elif recovery > 3:
            score += 20
            reasons.append(f"反弹幅度良好({recovery:.1f}%)")
        elif recovery > 2:
            score += 15
            reasons.append(f"反弹幅度一般({recovery:.1f}%)")
        
        # 3. 量能确认得分 (0-20)
        if pattern['index'] < len(df) - 1:
            vol_today = df.iloc[pattern['index']]['volume']
            vol_ma = df['volume'].rolling(window=20).mean().iloc[pattern['index']]
            vol_ratio = vol_today / vol_ma if vol_ma > 0 else 1
            
            if vol_ratio > 1.5:
                score += 20
                reasons.append("成交量放大配合")
            elif vol_ratio > 1.2:
                score += 15
                reasons.append("成交量温和放大")
            elif vol_ratio > 1.0:
                score += 10
                reasons.append("成交量有所放大")
        
        # 4. 趋势背景得分 (0-15)
        if pattern['index'] >= 5:
            # 检查之前是否是下跌趋势
            price_start = df.iloc[pattern['index']-5]['close']
            price_mid = df.iloc[pattern['index']-2]['close']
            price_end = df.iloc[pattern['index']]['close']
            
            if price_mid < price_start and price_end > price_mid:
                score += 15
                reasons.append("下跌后反弹，形态标准")
            else:
                score += 8
                reasons.append("形态有效")
        
        # 5. 市场环境得分 (0-10) - 使用全局市场情绪
        if market_sentiment is not None:
            score += market_sentiment
            if market_sentiment >= 8:
                reasons.append("市场环境良好")
            elif market_sentiment >= 5:
                reasons.append("市场环境一般")
            else:
                reasons.append("市场环境偏弱")
        else:
            score += 5
            reasons.append("市场环境中性")
        
        return score, "; ".join(reasons)

    def _calc_global_market_sentiment(self) -> int:
        """
        计算全局市场情绪得分 (0-10分)
        所有股票共享同一个市场情绪
        参考涨停板连板策略，基于大盘指数和成交量
        """
        try:
            score = 5  # 基础分
            index_changes = []
            
            # 获取上证指数数据
            df_sh = self.data_adapter.get_stock_data('000001')
            if df_sh is not None and len(df_sh) >= 2:
                latest = df_sh.iloc[-1]
                prev = df_sh.iloc[-2]
                sh_change = (latest['close'] - prev['close']) / prev['close'] * 100
                index_changes.append(sh_change)
                
                # 上证指数涨跌评分 (40%权重)
                if sh_change >= 1:
                    score += 2
                elif sh_change >= 0.5:
                    score += 1
                elif sh_change >= 0:
                    score += 0.5
                elif sh_change >= -0.5:
                    score -= 0.5
                else:
                    score -= 1
                
                # 成交量评分 (20%权重)
                if 'volume' in latest and 'volume' in prev and prev['volume'] > 0:
                    vol_ratio = latest['volume'] / prev['volume']
                    if vol_ratio >= 1.5:
                        score += 1
                    elif vol_ratio >= 1.2:
                        score += 0.5
                    elif vol_ratio < 0.8:
                        score -= 0.5
            
            # 获取深证成指数据
            df_sz = self.data_adapter.get_stock_data('399001')
            if df_sz is not None and len(df_sz) >= 2:
                latest = df_sz.iloc[-1]
                prev = df_sz.iloc[-2]
                sz_change = (latest['close'] - prev['close']) / prev['close'] * 100
                index_changes.append(sz_change)
                
                if sz_change >= 1:
                    score += 1.5
                elif sz_change >= 0:
                    score += 0.5
                elif sz_change < -1:
                    score -= 0.5
            
            # 获取创业板指数据
            df_cy = self.data_adapter.get_stock_data('399006')
            if df_cy is not None and len(df_cy) >= 2:
                latest = df_cy.iloc[-1]
                prev = df_cy.iloc[-2]
                cy_change = (latest['close'] - prev['close']) / prev['close'] * 100
                index_changes.append(cy_change)
                
                if cy_change >= 1.5:
                    score += 1.5
                elif cy_change >= 0.5:
                    score += 0.5
                elif cy_change < -1.5:
                    score -= 0.5
            
            # 获取科创板指数据
            df_kc = self.data_adapter.get_stock_data('000688')
            if df_kc is not None and len(df_kc) >= 2:
                latest = df_kc.iloc[-1]
                prev = df_kc.iloc[-2]
                kc_change = (latest['close'] - prev['close']) / prev['close'] * 100
                index_changes.append(kc_change)
                
                if kc_change >= 1.5:
                    score += 1
                elif kc_change >= 0:
                    score += 0.5
                elif kc_change < -1.5:
                    score -= 1
            
            # 计算平均涨跌
            if index_changes:
                avg_change = sum(index_changes) / len(index_changes)
                if avg_change >= 1:
                    score += 1
                elif avg_change < -0.5:
                    score -= 1
            
            final_score = max(0, min(10, round(score)))
            
            # 打印市场情绪详情
            print(f"{Fore.CYAN}📊 市场情绪分析:{Style.RESET_ALL}")
            if df_sh is not None:
                print(f"   上证涨跌: {sh_change:+.2f}%")
            if df_sz is not None:
                print(f"   深证涨跌: {sz_change:+.2f}%")
            if df_cy is not None:
                print(f"   创业板涨跌: {cy_change:+.2f}%")
            if df_kc is not None:
                print(f"   科创板涨跌: {kc_change:+.2f}%")
            if index_changes:
                print(f"   平均涨跌: {avg_change:+.2f}%")
            print(f"   市场情绪得分: {final_score}/10")
            
            return final_score
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 计算市场情绪失败: {e}{Style.RESET_ALL}")
            return 5

    def analyze_stock(self, stock_code: str, stock_name: str = None, market_sentiment: int = None) -> Optional[Dict]:
        """分析单只股票"""
        try:
            df = self.data_adapter.get_stock_data(stock_code)
            if df is None or len(df) < 20:
                return None
            
            # df = self.data_adapter.normalize_columns(df)
            
            patterns = self.find_morning_star(df)
            if not patterns:
                return None
            
            pattern = patterns[-1]
            # print("pattern: ", pattern)
            score, reasons = self.calculate_score(df, pattern, market_sentiment)
            
            current = df.iloc[-1]
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name or stock_code,
                'score': score,
                'reasons': reasons,
                'current_price': round(current['close'], 2),
                'price_recovery': round(pattern['price_recovery'], 2),
                'pattern_type': '早晨之星',
                'strategy': self.name,
                'win_rate': self.win_rate
            }
            
        except Exception as e:
            return None

    def batch_analyze(self, stock_list: List[tuple], top_n: int = 10) -> List[Dict]:
        """批量分析"""
        results = []
        
        for name, code in stock_list:
            try:
                result = self.analyze_stock(code, name)
                if result and result['score'] > 0:
                    results.append(result)
            except Exception:
                continue
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_n]


if __name__ == '__main__':
    analyzer = MorningStarAnalyzer()
    
    test_stocks = [('平安银行', '000001'), ('万科A', '000002')]
    
    print(f"{analyzer.name} {analyzer.version} 测试")
    print("=" * 70)
    print("\n【评分维度说明】")
    print("  1. 形态质量得分 (0-30分)：第三天阳线实体饱满度")
    print("  2. 反弹幅度得分 (0-25分)：三天整体反弹幅度")
    print("  3. 量能确认得分 (0-20分)：成交量是否放大配合")
    print("  4. 趋势背景得分 (0-15分)：是否下跌后反弹")
    print("  5. 市场环境得分 (0-10分)：基于大盘指数（所有股票共享）")
    print("=" * 70)
    
    # 先计算全局市场情绪（所有股票共享）
    print(f"\n{Fore.CYAN}📊 计算全局市场情绪...{Style.RESET_ALL}")
    market_sentiment = analyzer._calc_global_market_sentiment()
    
    for name, code in test_stocks:
        result = analyzer.analyze_stock(code, name, market_sentiment)
        if result:
            print(f"\n【{name}({code})】")
            print(f"  综合评分: {result['score']:.1f}分")
            print(f"  反弹幅度: {result['price_recovery']:.2f}%")
            print(f"  评分详情: {result['reasons']}")
        else:
            print(f"\n【{name}({code})】: 未发现早晨之星形态")
