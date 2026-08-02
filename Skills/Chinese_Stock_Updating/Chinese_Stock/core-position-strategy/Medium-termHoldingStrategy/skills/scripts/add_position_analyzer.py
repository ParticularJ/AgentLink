#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加仓信号分析器 - AddPositionAnalyzer
四级筛选体系：
  第一级：浮盈检查（首次≥5%，二次加仓≥12%）
  第二级：趋势健康（收盘>MA20、MA20向上、多头排列）
  第三级：止盈冲突筛查（任一满足禁止加仓）
  第四级：六大加仓信号（满足任意一条即触发）
"""
import os
import json
import sys
import pandas as pd
import numpy as np
from typing import Tuple, Optional, List, Dict
from dataclasses import dataclass, field
from enum import Enum

# ── 代理清除 ────────────────────────────────────────────
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        try:
            del os.environ[k]
        except:
            pass

from data_source import fetch_kline_sina, get_stock_realtime

# ── akshare 保底数据源 ────────────────────────────────
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

# ── 配置文件路径 ─────────────────────────────────────────
# ====================== 【止盈策略核心：静态龙头定级】======================
STOCK_GRADE = {
    # L1 行业绝对龙头
    "600584": "L1_行业龙头",  # 长电科技(封测全行业龙头)
    "600183": "L1_行业龙头",  # 生益科技(覆铜板全行业龙头)
    "600276": "L1_行业龙头",  # 恒瑞医药(创新药全行业龙头)
    "601975": "L1_行业龙头",  # 招商南油(油运央企龙头)
    "300831": "L1_行业龙头",  # 派瑞股份(功率器件细分龙头)
    "300408": "L1_行业龙头",  # 三环集团(MLCC瓷件+通用陶瓷全产业链龙头)
    "002859": "L1_行业龙头",  # 洁美科技【新增】纸质载带全球龙头、MLCC耗材全球隐形冠军
    # L2 细分龙头/强二线
    "603267": "L2_细分龙头",  # 鸿远电子【新增】军工航天高可靠MLCC细分龙头
    "002179": "L2_细分龙头",  # 中航光电(连接器细分龙头)
    "000021": "L2_细分龙头",  # 深科技(存储封测细分龙头)
    "603893": "L2_细分龙头",  # 瑞芯微(消费IC细分龙头)
    # L3 题材跟风/普通标的
    "603728": "L3_题材跟风",  # 鸣志电器
}

GRADE_CONFIG = {
    "L1_行业龙头": {
        "profit_targets": [0.18, 0.40, 0.50],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.08,
        "trailing_stop": 0.06,
        "position_pct": 0.20,
    },
    "L2_细分龙头": {
        "profit_targets": [0.12, 0.22, 0.38],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.07,
        "trailing_stop": 0.05,
        "position_pct": 0.15,
    },
    "L3_题材跟风": {
        "profit_targets": [0.10, 0.18, 0.30],
        "sell_ratio": [0.3, 0.4, 0.3],
        "stop_loss": -0.06,
        "trailing_stop": 0.04,
        "position_pct": 0.10,
    },
}


HOLDINGS_FILE = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json"
CASH_FILE = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/cash_balance.json"
ANALYSIS_LOG_DIR = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/analysis_logs"
ADD_COOLDOWN_DAYS = 5   # 加仓冷却期：同一股票5日内不允许重复加仓

# ====================== 飞书推送配置 ======================
FEISHU_APP_ID = "cli_a93eb458ceb81cc0"
FEISHU_APP_SECRET = "1i18JUKuFhQEejUOkNividRbMdJBMpV8"
FEISHU_GROUP_ID = "oc_0ac1e4e8d09f939d887f4992bba2886b"

# 日志
LOG_DIR = "/home/jarvis/.openclaw/logs/stock"
LOG_FILE = f"{LOG_DIR}/add_position_push.log"


# ═══════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════

class AddSignal(str, Enum):
    """加仓信号枚举"""
    BREAK_60_HIGH = "突破60日/波段新高"
    MA_PULLBACK = "均线回踩不破"
    PLATFORM_BREAK = "平台突破"
    VOLUME_PRICE_RISE = "量价齐升"
    SECTOR_RESONANCE = "板块共振"
    GAP_ACCELERATION = "缺口加速"


@dataclass
class LevelResult:
    """单级结果"""
    passed: bool
    score: float          # 该级得分（0-100）
    detail: str           # 详细说明


@dataclass
class AddPositionReport:
    """加仓分析报告"""
    code: str
    name: str
    current_price: float
    cost: float
    holding_days: int

    # 四级结果
    level1: LevelResult = None  # 浮盈检查
    level2: LevelResult = None  # 趋势健康
    level3: LevelResult = None  # 止盈冲突
    level4: LevelResult = None  # 加仓信号

    # 综合评分
    total_score: float = 0.0    # 1-4级综合得分（满分100）
    can_add: bool = False       # 是否可以加仓
    add_signal: List[str] = field(default_factory=list)  # 触发的加仓信号列表
    reason: str = ""            # 分析理由
    action: str = ""            # 建议操作


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def compute_rsi(closes: pd.Series, period: int = 14) -> float:
    """计算RSI(14)"""
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def detect_upper_shadow_ratio(row: dict) -> float:
    """计算上影线占比 = (最高价 - 收盘) / (最高价 - 最低价)"""
    high = row.get('high', 0)
    close = row.get('close', 0)
    low = row.get('low', 0)
    body = high - low
    if body <= 0:
        return 0.0
    upper = high - close
    return upper / body


def is_high_volume_stall(df: pd.DataFrame, lookback: int = 5) -> bool:
    """
    高位放量滞涨：
    连续 lookback 日成交量放大，但涨幅收窄或滞涨
    判断：成交量 > 20日均量1.5倍 且 涨幅 < 1%
    """
    if len(df) < lookback + 20:
        return False
    vol_avg_20 = df['volume'].iloc[-lookback-20:-lookback].mean()
    recent = df.iloc[-lookback:]
    for _, row in recent.iterrows():
        vol = row['volume']
        chg = abs(row.get('change_pct', row.get('pct_change', 0)))
        if vol > vol_avg_20 * 1.5 and chg < 1.0:
            return True
    return False


def is_long_upper_shadow(df: pd.DataFrame, threshold: float = 0.6) -> bool:
    """
    长上影：当日上影线占比 > threshold (默认0.6，即60%以上)
    且当日涨幅 > 2%
    """
    if len(df) < 1:
        return False
    row = df.iloc[-1].to_dict()
    ratio = detect_upper_shadow_ratio(row)
    chg = abs(row.get('change_pct', row.get('pct_change', 0)))
    return ratio > threshold and chg > 2.0


def is_high_doji(df: pd.DataFrame, body_threshold: float = 0.2) -> bool:
    """
    高位十字星：K线实体占比 < body_threshold，且涨跌幅绝对值 > 2%
    """
    if len(df) < 1:
        return False
    row = df.iloc[-1].to_dict()
    high = row.get('high', 0)
    low = row.get('low', 0)
    close = row.get('close', 0)
    open_ = row.get('open', close)
    body = abs(close - open_)
    total_range = high - low
    if total_range <= 0:
        return False
    body_ratio = body / total_range
    chg = abs(row.get('change_pct', row.get('pct_change', 0)))
    return body_ratio < body_threshold and chg > 2.0


def get_sector_of_stock(code: str) -> Optional[str]:
    """获取个股所属板块（目前仅做简单匹配，后续可扩展）"""
    # 这里可接入 stock_analyzer.py 的 SECTOR_ALL_STOCKS / CODE_TO_SECTOR
    # 为简化，先返回 None，由外部传入
    return None


def pct_change_from_to(from_price, to_price) -> float:
    """百分比变化"""
    if from_price <= 0:
        return 0.0
    return (to_price - from_price) / from_price * 100


# ═══════════════════════════════════════════════════════════
# 核心分析器
# ═══════════════════════════════════════════════════════════


def _fetch_kline_akshare(code: str, days: int = 120) -> Optional[pd.DataFrame]:
    """akshare保底K线获取"""
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
        close = df['close'].values
        for n in [5, 10, 20, 60]:
            df[f'ma{n}'] = pd.Series(close).rolling(n).mean().values
        return df.tail(days)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# 持仓数据读写（不修改原始 holdings.json）
# ═══════════════════════════════════════════════════════════

def load_holdings_from_file(path: str = HOLDINGS_FILE) -> List[dict]:
    """读取原始持仓文件（只读，不修改）"""
    if not os.path.exists(path):
        print(f"[警告] 持仓文件不存在: {path}")
        return []
    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    return raw


def save_holdings(holdings: List[dict], path: str = HOLDINGS_FILE) -> None:
    """
    保存持仓（先备份 → 原子写入 holdings.json）。
    操作 holdings.json 前必调此函数。
    """
    atomic_write_json(path, holdings)


def load_cash_balance(path: str = CASH_FILE) -> dict:
    """读取现金余额文件（只读）"""
    if not os.path.exists(path):
        print(f"[警告] 现金文件不存在: {path}")
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_cash_balance(data: dict, path: str = CASH_FILE) -> None:
    """
    保存现金余额（先备份 → 原子写入 cash_balance.json）。
    操作 cash_balance.json 前必调此函数。
    """
    atomic_write_json(path, data)


# ═══════════════════════════════════════════════════════════
# 加仓执行（带冷却期检查）
# ═══════════════════════════════════════════════════════════

def get_holding_by_code(code: str, holdings: List[dict] = None) -> Optional[dict]:
    """根据代码查找持仓（支持6位码或sh/sz前缀）"""
    if holdings is None:
        holdings = load_holdings_from_file()
    code6 = code.lstrip('sh').lstrip('sz')
    for h in holdings:
        if h.get('code', '').lstrip('sh').lstrip('sz') == code6:
            return h
    return None


def can_add_position(code: str, holdings: List[dict] = None) -> Tuple[bool, str]:
    """
    检查某只股票是否满足加仓条件（冷却期检查）。
    返回 (can_add, reason)
    - can_add=True：可以加仓
    - can_add=False：reason 说明原因
    """
    from datetime import datetime, timedelta
    if holdings is None:
        holdings = load_holdings_from_file()

    h = get_holding_by_code(code, holdings)
    if h is None:
        return False, f"未找到持仓记录: {code}"

    last_add = h.get('last_add_date', '')
    if not last_add:
        return True, "无加仓记录，随时可加仓"

    try:
        last_dt = datetime.strptime(last_add, "%Y-%m-%d")
        days_diff = (datetime.now() - last_dt).days
        if days_diff < ADD_COOLDOWN_DAYS:
            remaining = ADD_COOLDOWN_DAYS - days_diff
            return False, f"加仓冷却期内，还需等待 {remaining} 天（{last_add} 加过仓）"
        return True, f"上次加仓 {days_diff} 天前，已过冷却期"
    except Exception:
        return True, "last_add_date 格式异常，忽略"


def execute_add(code: str, new_shares: int, new_cost: float,
               cash_data: dict = None) -> dict:
    """
    执行加仓并更新 holdings.json + cash_balance.json。

    参数：
      code:        股票代码（6位或 sh/sz 前缀）
      new_shares:  新增买入的股数
      new_cost:    买入成交均价（新补充的份额用这个价格）
      cash_data:   现金余额字典（若为 None，自动读取）

    返回：
      执行结果字典 {"success": bool, "message": str, "report": dict}

    流程：
      1. 读取 holdings + cash（只读）
      2. 冷却期检查（5日）
      3. 四级信号复核
      4. 现金扣减 + 持仓更新
      5. 写入 backup + holdings.json + cash_balance.json
    """
    from datetime import datetime
    holdings = load_holdings_from_file()
    if cash_data is None:
        cash_data = load_cash_balance()

    # ── 冷却期检查 ──────────────────────────────
    can_add, cooldown_msg = can_add_position(code, holdings)
    if not can_add:
        return {"success": False, "message": cooldown_msg, "report": None}

    h = get_holding_by_code(code, holdings)
    if h is None:
        return {"success": False, "message": f"未找到持仓: {code}", "report": None}

    # ── 四级信号复核 ───────────────────────────────
    analyzer = AddPositionAnalyzer()
    report = analyzer.analyze(
        code=h['code'],
        name=h.get('name', h['code']),
        cost=float(h['cost']),
        current_price=float(h['current_price']),
        highest_price=float(h.get('highest_price', h['current_price'])),
        add_count=h.get('_add_count', 0),
        holding_days=_infer_holding_days(h),
    )

    if not report.can_add:
        return {"success": False,
                "message": f"四级信号复核未通过：{report.action}",
                "report": report}

    # ── 计算现金需求 ─────────────────────────────
    code6 = code.lstrip('sh').lstrip('sz')
    # 取当前市场价（简化：直接用 current_price，实际应以成交价为准）
    price_per_share = float(h['current_price'])
    need_cash = new_shares * price_per_share
    available_cash = float(cash_data.get('cash_balance', 0))

    if need_cash > available_cash:
        return {"success": False,
                "message": f"现金不足：需 {need_cash:.2f}，可用 {available_cash:.2f}",
                "report": report}

    # ── 更新持仓 ───────────────────────────────
    # 合并新老份额的成本
    old_shares = int(h['shares'])
    old_cost_total = float(h['cost']) * old_shares
    new_cost_total = new_cost * new_shares
    merged_shares = old_shares + new_shares
    merged_cost = (old_cost_total + new_cost_total) / merged_shares

    # 更新 highest_price（如果新价格更高）
    current_price = float(h['current_price'])
    highest_price = float(h.get('highest_price', current_price))
    if current_price > highest_price:
        highest_price = current_price

    # 标记 stop_level_hit[0] = True（代表已触发过二次加仓）
    stop_level_hit = h.get('stop_level_hit', [False, False, False])
    if len(stop_level_hit) < 1:
        stop_level_hit = [False, False, False]
    stop_level_hit[0] = True

    # 构建更新后的持仓（注意：不改原始 holdings.json，由 caller 决定是否保存）
    updated_h = dict(h)
    updated_h['shares'] = merged_shares
    updated_h['cost'] = round(merged_cost, 3)
    updated_h['highest_price'] = round(highest_price, 3)
    updated_h['stop_level_hit'] = stop_level_hit
    updated_h['last_add_date'] = datetime.now().strftime('%Y-%m-%d')
    # add_count 加1（加仓次数字段）
    updated_h['add_count'] = int(h.get('add_count', 0)) + 1

    # ── 更新现金 ───────────────────────────────
    updated_cash = dict(cash_data)
    updated_cash['cash_balance'] = round(available_cash - need_cash, 2)

    # ── 写入（带备份） ─────────────────────────
    # 找出并替换持仓列表中的这只股票
    new_holdings = []
    for item in holdings:
        code_check = item.get('code', '').lstrip('sh').lstrip('sz')
        if code_check == code6:
            new_holdings.append(updated_h)
        else:
            new_holdings.append(item)

    save_holdings(new_holdings)
    save_cash_balance(updated_cash)

    result_msg = (
        f"✅ 加仓成功\n"
        f"   股票：{updated_h['name']}({code6})\n"
        f"   新增：+{new_shares} 股 @ {new_cost:.2f}\n"
        f"   合并持仓：{merged_shares} 股，新成本={merged_cost:.3f}\n"
        f"   扣减现金：{need_cash:.2f}，剩余现金：{updated_cash['cash_balance']:.2f}\n"
        f"   加仓日期：{updated_h['last_add_date']}"
    )

    print(result_msg)
    return {"success": True, "message": result_msg, "report": report,
            "updated_holdings": new_holdings, "updated_cash": updated_cash,
            "updated_h": updated_h}


def _get_stock_grade(code6: str) -> str:
    """获取股票等级（L1_行业龙头 / L2_细分龙头 / L3_题材跟风）"""
    return STOCK_GRADE.get(code6, "L3_题材跟风")


def _get_first_profit_target(code6: str) -> float:
    """
    获取第1档止盈目标（%），用于第2仓(sno=2)浮盈门槛。
    逻辑：
      sno=1 → 固定 5%
      sno=2 → 该股 Grade 第1档止盈目标（从 STOCK_GRADE + GRADE_CONFIG 读取）
    """
    grade = _get_stock_grade(code6)
    cfg = GRADE_CONFIG.get(grade, GRADE_CONFIG["L3_题材跟风"])
    return cfg["profit_targets"][0] * 100  # 转为 %



def _build_sno(h: dict) -> int:
    """
    生成加仓序号（sno），基于 add_count（加仓次数）字段：
    - add_count == 0 → 首次建仓：sno=1
    - add_count == 1 → 二次加仓：sno=2
    - add_count >= 2 → 已达最大加仓次数
    """
    return int(h.get('add_count', 0)) + 1


def _infer_holding_days(h: dict) -> int:
    """从 entry_date 推断持仓天数"""
    ed = h.get('entry_date', '')
    if not ed:
        return 0
    try:
        from datetime import datetime
        return (datetime.now() - datetime.strptime(ed, "%Y-%m-%d")).days
    except Exception:
        return 0


def _to_sina_code(code: str) -> str:
    """将 6 位股票代码转换为新浪格式 sh/sz 前缀"""
    code = code.strip().lstrip('sh').lstrip('sz')
    if code.startswith(('6', '5')):
        return f'sh{code}'
    elif code.startswith(('0', '3', '4')):
        return f'sz{code}'
    elif code.startswith('8') or code.startswith('9'):
        return f'sh{code}'   # 科创板
    return f'sz{code}'



# ═══════════════════════════════════════════════════════════
# 备份工具（操作 holdings / cash_balance 前先备份）
# ═══════════════════════════════════════════════════════════

def _backup_filename(base_name: str) -> str:
    """生成备份文件名：20260604_233802_holdings.json"""
    from datetime import datetime
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{ts}_{base_name}"


def backup_before_write(target_path: str) -> bool:
    """
    写入任意 .json 文件前，先复制一份到同目录的 backup/ 子目录。
    备份文件名格式：20260604_233802_holdings.json
    返回 True=备份成功（或文件不存在，无需备份），False=备份失败但仍可继续。
    """
    import shutil
    backup_dir = os.path.join(os.path.dirname(target_path), 'backup')
    if not os.path.exists(target_path):
        print(f"[备份跳过] 文件不存在: {target_path}")
        return True
    os.makedirs(backup_dir, exist_ok=True)
    ts_name = _backup_filename(os.path.basename(target_path))
    backup_path = os.path.join(backup_dir, ts_name)
    try:
        shutil.copy2(target_path, backup_path)
        print(f"[备份] {target_path}\n     → {backup_path}")
        return True
    except Exception as e:
        print(f"[备份警告] 备份失败: {e}（继续执行写入）")
        return False


def atomic_write_json(path: str, data, indent: int = 2) -> None:
    """
    原子写入 JSON：先备份 → 写临时文件 → 原子替换。
    保证 holdings.json 永远不会因写入崩溃而丢失。
    """
    backup_before_write(path)
    import tempfile, os
    dir_ = os.path.dirname(path) or '.'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                     dir=dir_, suffix='.json', delete=False) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=indent)
        tmp_path = tmp.name
    os.replace(tmp_path, path)
    print(f"[写入] {path}")


# ── 分析记录日志 ─────────────────────────────────────────
ANALYSIS_LOG_DIR = "/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/analysis_logs"


def log_analysis_batch(reports: List["AddPositionReport"], tag: str = "") -> str:
    """
    将本次分析结果写入 analysis_logs/ 目录（JSONL 格式，按日分行）。
    每行一条 JSON，方便后续查询和回溯。
    """
    import shutil
    os.makedirs(ANALYSIS_LOG_DIR, exist_ok=True)
    from datetime import datetime
    date_str = datetime.now().strftime('%Y%m%d')
    log_file = os.path.join(ANALYSIS_LOG_DIR, f"{date_str}.jsonl")

    lines = []
    for r in reports:
        meta = getattr(r, '_meta', {})
        lines.append(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "tag": tag,
            "code": meta.get('raw_code', r.code),
            "name": r.name,
            "sno": meta.get('sno', '?'),
            "cost": r.cost,
            "current_price": r.current_price,
            "profit_pct": round((r.current_price / r.cost - 1) * 100, 2),
            "total_score": round(r.total_score, 1),
            "can_add": r.can_add,
            "add_signal": r.add_signal,
            "action": r.action,
            "level1_pass": r.level1.passed,
            "level2_pass": r.level2.passed,
            "level3_pass": r.level3.passed,
            "level4_pass": r.level4.passed,
            "level1_score": r.level1.score,
            "level2_score": r.level2.score,
            "level3_score": r.level3.score,
            "level4_score": r.level4.score,
        }, ensure_ascii=False))

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")

    print(f"[记录] 分析日志 → {log_file}（{len(lines)} 条）")
    return log_file


# ====================== 飞书推送工具 ======================

def _feishu_log(msg: str):
    """写日志到文件 + 打印"""
    from datetime import datetime
    import os
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def _feishu_log_error(msg: str):
    """写错误日志"""
    import traceback
    from datetime import datetime
    import os
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [ERROR] {msg}\n{traceback.format_exc()}"
    print(line, file=sys.stderr)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def _get_tenant_token() -> str:
    """获取飞书 tenant token"""
    import requests as _req
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = _req.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10)
    resp.raise_for_status()
    return resp.json()["tenant_access_token"]


def _send_feishu_card(token: str, card: dict, receive_id: str = FEISHU_GROUP_ID) -> dict:
    """发送飞书交互卡片"""
    import requests as _req
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": json.dumps(card)
    }
    resp = _req.post(url, params={"receive_id_type": "chat_id"}, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()

def _lv_explain(detail: str) -> str:
    """从 LevelResult.detail 字符串提取简短失败原因"""
    if "✅通过" in detail or "✅ PASS" in detail:
        return "通过"
    if "：" in detail:
        return detail.split("：")[1].split("，")[0]
    if "禁止" in detail:
        parts = detail.split("，")
        return parts[0] if parts else detail[:20]
    return detail[:20]



def _build_add_position_card(reports: List["AddPositionReport"],
                          date_str: str = "",
                          title: str = "加仓信号分析") -> dict:
    """
    从 AddPositionReport 列表构建飞书卡片。
    - 展示 L1~L4 四级结论（用中文说明）
    - 不展示综合评分
    """
    from datetime import datetime as _dt
    if not date_str:
        date_str = _dt.now().strftime("%Y-%m-%d")

    can_add = [r for r in reports if r.can_add]
    no_add  = [r for r in reports if not r.can_add]

    lines = []

    # ── 头部 ──────────────────────────────────────────
    lines.append(f"**📊 {title}** | {date_str}")
    lines.append("")

    # ── L1~L4 说明图例 ────────────────────────────────
    lines.append("**🔎 四级信号说明**")
    lines.append("L1 浮盈检查：首次加仓需浮盈>5%，二次加仓需达第1档止盈目标")
    lines.append("L2 趋势健康：收盘>MA20 + MA20向上 + 5/10/20多头排列")
    lines.append("L3 止盈冲突：回撤≥5% / RSI≥85 / 高位放量滞涨/长上影/十字星 → 禁止")
    lines.append("L4 加仓信号：突破新高/均线回踩/平台突破/量价齐升/板块共振/缺口加速")
    lines.append("")

    # ── ✅ 可加仓 ─────────────────────────────────────
    if can_add:
        lines.append(f"✅ **可加仓 ({len(can_add)}只)**")
        lines.append("")
        for r in can_add:
            meta = _meta(r)
            sno  = meta.get('sno', '?')
            last_add = meta.get('last_add_date', '无记录')
            profit_pct = (r.current_price / r.cost - 1) * 100
            signals = ' / '.join(r.add_signal) if r.add_signal else '无'
            lines.append(
                f"**{r.name}({meta.get('raw_code', r.code)})** "
                f"浮盈={profit_pct:+.2f}% | {last_add}"
            )
            lines.append(
                f"  L1✅浮盈 L2✅趋势 L3✅冲突 L4✅信号 "
                f"| 触发: {signals}"
            )
            lines.append("")
    else:
        lines.append("✅ **可加仓 (0只)**  当前无符合加仓条件持仓")
        lines.append("")

    # ── ❌ 暂停加仓 ───────────────────────────────────
    if no_add:
        lines.append(f"❌ **暂停加仓 ({len(no_add)}只)**")
        lines.append("")
        for r in no_add:
            meta = _meta(r)
            sno  = meta.get('sno', '?')
            profit_pct = (r.current_price / r.cost - 1) * 100
            # 找第一个失败级别
            fail_tag  = ""
            fail_desc = ""
            for lv in [r.level1, r.level2, r.level3, r.level4]:
                if not lv.passed:
                    fail_desc = _lv_explain(lv.detail)
                    if lv is r.level1:
                        fail_tag = "L1❌浮盈不足"
                    elif lv is r.level2:
                        fail_tag = "L2❌趋势不健康"
                    elif lv is r.level3:
                        fail_tag = "L3❌止盈冲突"
                    else:
                        fail_tag = "L4❌无加仓信号"
                    break
            lines.append(
                f"**{r.name}({meta.get('raw_code', r.code)})** "
                f"浮盈={profit_pct:+.2f}% | {fail_tag}"
            )
            lines.append(f"  → {fail_desc}")
            lines.append("")
    else:
        lines.append("❌ **暂停加仓 (0只)**")
        lines.append("")

    # ── 汇总 ──────────────────────────────────────────
    lines.append("---")
    lines.append(
        f"📋 汇总：{len(reports)}只持仓 | ✅{len(can_add)}只可加仓"
    )
    lines.append("")
    lines.append("⚠️ 仅供参考，不构成投资建议")

    # 元素
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}]

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📊 {title} | {date_str}"},
            "template": "blue"
        },
        "elements": elements
    }
    return card


def send_reports_to_feishu(reports: List["AddPositionReport"],
                           title: str = "加仓信号分析") -> dict:
    """
    将加仓分析报告批量推送到飞书群。
    返回推送结果字典 {"success": bool, "message": str}
    """
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        card = _build_add_position_card(reports, date_str, title)
        token = _get_tenant_token()
        resp = _send_feishu_card(token, card)
        code = resp.get('code', -1)
        msg = resp.get('msg', '') or resp.get('message', '')
        if code == 0:
            _feishu_log(f"飞书推送成功: {len(reports)}只持仓")
            return {"success": True, "message": f"推送成功 {len(reports)}只", "code": code}
        else:
            _feishu_log_error(f"飞书推送失败: code={code} msg={msg}")
            return {"success": False, "message": f"推送失败: {msg}", "code": code}
    except Exception as e:
        _feishu_log_error(f"飞书推送异常: {e}")
        return {"success": False, "message": str(e)}



class AddPositionAnalyzer:
    """加仓信号分析器"""

    def __init__(self, sector_data: Optional[Dict[str, dict]] = None):
        """
        sector_data: 板块数据字典，格式 {板块名: {'change_pct': float}}
                     用于第四级「板块共振」判断
        """
        self.sector_data = sector_data or {}

    def _load_kline(self, code: str, days: int = 120) -> Optional[pd.DataFrame]:
        """加载K线数据，依次尝试新浪→akshare保底"""
        df = fetch_kline_sina(code, days)
        if df is not None and not df.empty and len(df) >= 20:
            return df
        if AKSHARE_AVAILABLE:
            df2 = _fetch_kline_akshare(code, days)
            if df2 is not None and not df2.empty and len(df2) >= 20:
                return df2
        return None

    # ─────────────────────────────────────────────────
    # 第一级：浮盈检查
    # ─────────────────────────────────────────────────
    def analyze_level1(self, cost: float, current_price: float,
                       sno: int, code6: str = "") -> LevelResult:
        """
        浮盈检查
        sno = 1: 首次加仓，浮盈需 > 5%
        sno = 2: 二次加仓，浮盈需 > 5%（需 stop_level_hit[0] == True）
        sno >= 3: 已达最大加仓次数，禁止再加仓
        """
        profit_pct = pct_change_from_to(cost, current_price)
        # sno=1 → 首次加仓（浮盈>5%），sno=2 → 二次加仓（浮盈>5%），sno>=3 → 禁止
        if sno >= 3:
            passed = False
            score = 0.0
            detail = f"已达最大加仓次数（sno={sno}），禁止再加仓"
            return LevelResult(passed=passed, score=score, detail=detail)

        # 浮盈门槛：sno=1 固定 5%，sno=2 动态查 grade 第1档止盈目标
        if sno == 1:
            threshold = 5.0
            label = "第1仓"
        elif sno == 2:
            threshold = _get_first_profit_target(code6) + 5.0 # 在第1档止盈目标基础上加5%作为二次加仓门槛
            label = "第2仓"
        else:
            threshold = 5.0
            label = f"第{sno}仓"

        passed = profit_pct > threshold  # 严格大于
        score = min(100.0, profit_pct / threshold * 100) if profit_pct >= 0 else 0.0
        threshold_label = f"{threshold:.0f}%" if sno == 1 else f"{threshold:.0f}%(动态)"
        detail = (
            f"{label}浮盈检查：成本={cost:.2f}，现价={current_price:.2f}，"
            f"浮盈={profit_pct:.2f}%（需>{threshold_label}），{'✅通过' if passed else '❌未通过'}"
        )
        return LevelResult(passed=passed, score=score, detail=detail)

    # ─────────────────────────────────────────────────
    # 第二级：趋势健康
    # ─────────────────────────────────────────────────
    def analyze_level2(self, df: pd.DataFrame) -> LevelResult:
        """
        趋势健康三项（全部达标才算通过）：
        1. 收盘价 > 20日均线
        2. 20日均线向上（MA20斜率 > 0）
        3. 5日 > 10日 > 20日 多头排列
        """
        if df is None or len(df) < 25:
            return LevelResult(passed=False, score=0.0,
                               detail="数据不足（需≥25日）")

        closes = df['close']
        ma5 = closes.rolling(5).mean()
        ma10 = closes.rolling(10).mean()
        ma20 = closes.rolling(20).mean()
        ma60 = closes.rolling(60).mean() if len(df) >= 60 else None

        current_close = float(closes.iloc[-1])
        current_ma5 = float(ma5.iloc[-1])
        current_ma10 = float(ma10.iloc[-1])
        current_ma20 = float(ma20.iloc[-1])
        past_ma20_5 = float(ma20.iloc[-6]) if len(ma20) >= 6 else current_ma20

        # 条件1
        cond1 = current_close > current_ma20

        # 条件2：MA20向上（5日斜率）
        ma20_slope = (current_ma20 - past_ma20_5) / (past_ma20_5 if past_ma20_5 != 0 else 1)
        cond2 = ma20_slope > 0.005  # 向上

        # 条件3：多头排列
        cond3 = current_ma5 > current_ma10 > current_ma20

        passed = cond1 and cond2 and cond3
        score = sum([cond1, cond2, cond3]) / 3 * 100

        detail_parts = [
            f"收盘价>{'✅' if cond1 else '❌'}MA20({current_ma20:.2f})，现价={current_close:.2f}",
            f"MA20向上{'✅' if cond2 else '❌'}（斜率={ma20_slope:.4f}）",
            f"多头排列{'✅' if cond3 else '❌'}（MA5={current_ma5:.2f}>MA10={current_ma10:.2f}>MA20={current_ma20:.2f}）",
        ]
        detail = "趋势健康检查：" + " | ".join(detail_parts) + f" | {'✅全部通过' if passed else '❌未全部通过'}"

        return LevelResult(passed=passed, score=score, detail=detail)

    # ─────────────────────────────────────────────────
    # 第三级：止盈冲突筛查
    # ─────────────────────────────────────────────────
    def analyze_level3(self, df: pd.DataFrame, highest_price: float,
                      current_price: float) -> LevelResult:
        """
        止盈冲突，任一满足则禁止加仓：
        1. 持仓从高点回撤 ≥ 5%
        2. RSI(14) ≥ 85
        3. 高位放量滞涨 / 长上影 / 高位十字星
        """
        if df is None or len(df) < 20:
            return LevelResult(passed=False, score=0.0,
                               detail="数据不足（需≥20日）")

        signals = []

        # 条件1：回撤检查
        if highest_price > 0:
            drawdown = (1 - current_price / highest_price) * 100
            cond1 = drawdown >= 5.0
            if cond1:
                signals.append(f"从高点回撤{drawdown:.1f}%≥5%")
        else:
            drawdown = 0.0
            cond1 = False

        # 条件2：RSI检查
        rsi = compute_rsi(df['close'], 14)
        cond2 = rsi >= 85.0
        if cond2:
            signals.append(f"RSI(14)={rsi:.1f}≥85")

        # 条件3：高位放量滞涨
        cond3_vol = is_high_volume_stall(df)
        if cond3_vol:
            signals.append("高位放量滞涨")

        # 条件3续：长上影
        cond3_shadow = is_long_upper_shadow(df)
        if cond3_shadow:
            signals.append("长上影K线")

        # 条件3续续：高位十字星
        cond3_doji = is_high_doji(df)
        if cond3_doji:
            signals.append("高位十字星")

        has_conflict = cond1 or cond2 or cond3_vol or cond3_shadow or cond3_doji

        # 得分：冲突项越少越高
        conflict_count = sum([cond1, cond2, cond3_vol, cond3_shadow, cond3_doji])
        score = max(0.0, 100 - conflict_count * 25)

        if has_conflict:
            detail = f"止盈冲突筛查：{' / '.join(signals)}，❌禁止加仓"
        else:
            detail = f"止盈冲突筛查：无冲突项，✅可继续"

        return LevelResult(passed=not has_conflict, score=score, detail=detail)

    # ─────────────────────────────────────────────────
    # 第四级：六大加仓信号
    # ─────────────────────────────────────────────────
    def analyze_level4(self, df: pd.DataFrame, code: str,
                       sector_change_pct: Optional[float] = None) -> Tuple[LevelResult, List[str]]:
        """
        六大加仓信号（满足任意一条即触发加仓）：
        1. 突破新高：突破60日/波段高点，成交量>20日均量1.5倍
        2. 均线回踩：回踩10/20日线不破，次日收阳线
        3. 平台突破：横盘≥5日放量突破平台上沿
        4. 量价齐升：连续2日放量上涨，单日涨幅≥2%
        5. 板块共振：个股所属板块当日涨≥2%，个股领涨
        6. 缺口加速：回补缺口后3日内创出阶段新高
        """
        if df is None or len(df) < 65:
            return LevelResult(passed=False, score=0.0,
                               detail="数据不足（需≥65日）"), []

        signals_triggered: List[str] = []
        scores_by_signal = []

        closes = df['close']
        vols = df['volume']
        ma5 = closes.rolling(5).mean()
        ma10 = closes.rolling(10).mean()
        ma20 = closes.rolling(20).mean()
        ma60 = closes.rolling(60).mean()
        vol_avg20 = vols.rolling(20).mean()

        current_close = float(closes.iloc[-1])
        current_vol = float(vols.iloc[-1])
        prev_close = float(closes.iloc[-2])

        # ── 信号1：突破新高 ───────────────────────────
        sig1_scores = []
        # 突破60日高点
        high_60 = float(closes.iloc[-60:].max())
        vol_avg_20_val = float(vol_avg20.iloc[-1])
        if current_close > high_60 and current_vol > vol_avg_20_val * 1.5:
            sig1_scores.append(100.0)
            signals_triggered.append(f"{AddSignal.BREAK_60_HIGH.value}（突破60日高={high_60:.2f}，量比={current_vol/vol_avg_20_val:.2f}x）")

        # 突破20日波段高点
        high_20 = float(closes.iloc[-20:].max())
        if current_close > high_20 and current_vol > vol_avg_20_val * 1.5:
            sig1_scores.append(100.0)
            signals_triggered.append(f"突破20日波段高点={high_20:.2f}，量比={current_vol/vol_avg_20_val:.2f}x）")

        # ── 信号2：均线回踩 ─────────────────────────
        # 回踩10/20日线不破（当日最低价 < MA10/MA20），且次日收阳
        current_low = float(df['low'].iloc[-1])
        current_ma10 = float(ma10.iloc[-1])
        current_ma20 = float(ma20.iloc[-1])
        # 今日是否回踩
        if len(df) >= 2:
            prev_row = df.iloc[-2]
            prev_low = float(prev_row['low'])
            prev_close_2 = float(prev_row['close'])
            # 昨日（回踩日）最低价踩到10/20日线
            if (prev_low <= current_ma10 or prev_low <= current_ma20) and prev_close_2 > prev_low:
                # 今日收阳（今日是回踩后的次日）
                if current_close > prev_close_2:
                    sig2_score = 100.0
                    sig1_scores.append(sig2_score)
                    signals_triggered.append(
                        f"{AddSignal.MA_PULLBACK.value}（回踩{'10日' if prev_low <= current_ma10 else '20日'}线，次日收阳）"
                    )

        # ── 信号3：平台突破 ─────────────────────────
        # 横盘≥5日，震荡幅度 < 3%，之后放量突破上沿
        platform_days = 5
        range_thresh = 0.03
        if len(df) >= platform_days + 5:
            platform = closes.iloc[-(platform_days + 5):-5]
            platform_high = float(platform.max())
            platform_low = float(platform.min())
            platform_range = (platform_high - platform_low) / platform_low
            break_vol = float(vols.iloc[-1])
            break_price = float(closes.iloc[-1])
            vol_avg_5 = float(vols.iloc[-6:-1].mean())
            if platform_range < range_thresh and break_price > platform_high and break_vol > vol_avg_5 * 1.5:
                sig1_scores.append(100.0)
                signals_triggered.append(
                    f"{AddSignal.PLATFORM_BREAK.value}（横盘{platform_days}日幅={platform_range:.2%}，突破量比={break_vol/vol_avg_5:.2f}x）"
                )

        # ── 信号4：量价齐升 ─────────────────────────
        # 连续2日放量上涨，单日涨幅≥2%
        if len(df) >= 2:
            day1 = df.iloc[-2]
            day2 = df.iloc[-1]
            vol_avg_2 = float(vols.iloc[-5:-2].mean())  # 近5日均量（排除近2日）
            chg1 = float(day1.get('pct_change', day1.get('change_pct',
                        (float(day1['close']) / float(day1['open']) - 1) * 100)))
            chg2 = float(day2.get('pct_change', day2.get('change_pct',
                        (float(day2['close']) / float(day2['open']) - 1) * 100)))
            vol1 = float(day1['volume'])
            vol2 = float(day2['volume'])
            if (vol1 > vol_avg_2 * 1.3 and vol2 > vol_avg_2 * 1.3 and
                    chg1 >= 2.0 and chg2 >= 2.0):
                sig1_scores.append(100.0)
                signals_triggered.append(
                    f"{AddSignal.VOLUME_PRICE_RISE.value}（连续2日涨幅={chg1:.2f}%/{chg2:.2f}%，量比={max(vol1,vol2)/vol_avg_2:.2f}x）"
                )

        # ── 信号5：板块共振 ─────────────────────────
        if sector_change_pct is not None and sector_change_pct >= 2.0:
            # 个股当日涨幅
            stock_chg = float(df.iloc[-1].get('pct_change',
                           df.iloc[-1].get('change_pct', 0)))
            if stock_chg >= sector_change_pct:  # 个股领涨
                sig1_scores.append(100.0)
                signals_triggered.append(
                    f"{AddSignal.SECTOR_RESONANCE.value}（板块涨{sector_change_pct:.1f}%，个股涨{stock_chg:.2f}%）"
                )

        # ── 信号6：缺口加速 ─────────────────────────
        # 回补缺口后3日内创出阶段新高
        if len(df) >= 5:
            # 找近30日内最大缺口（向上跳空缺口后被回补）
            gaps = []
            for i in range(2, min(31, len(df))):
                open_today = float(df['open'].iloc[-i])
                close_yesterday = float(closes.iloc[-i])
                if open_today > close_yesterday * 1.01:  # 向上跳空 > 1%
                    gaps.append(i)
            for gap_idx in gaps:
                # 检查缺口后3日内是否创出新高
                gap_high_zone = closes.iloc[-gap_idx:-gap_idx + 3] if -gap_idx + 3 < 0 else None
                if gap_high_zone is not None and len(gap_high_zone) >= 2:
                    recent_max = float(closes.iloc[-gap_idx + 3]) if -gap_idx + 3 < 0 else float(closes.iloc[-1])
                    prev_max = float(gap_high_zone.max())
                    if recent_max > prev_max:
                        sig1_scores.append(100.0)
                        signals_triggered.append(
                            f"{AddSignal.GAP_ACCELERATION.value}（{gap_idx}日前缺口回补后创出阶段新高）"
                        )
                        break

        # 汇总
        triggered = len(signals_triggered) > 0
        score = max(sig1_scores) if sig1_scores else 0.0

        if triggered:
            detail = f"加仓信号：{' + '.join(signals_triggered)}，✅触发加仓"
        else:
            detail = "加仓信号：六大信号均未触发，❌不触发加仓"

        return LevelResult(passed=triggered, score=score, detail=detail), signals_triggered

    # ─────────────────────────────────────────────────
    # 综合分析入口
    # ─────────────────────────────────────────────────
    def analyze(self, code: str, name: str, cost: float,
                current_price: float, highest_price: float,
                sno: int,
                holding_days: int = 0,
                sector_change_pct: Optional[float] = None,
                # 辅助字段（用于推断或日志）
                entry_date: Optional[str] = None,
                init_shares: Optional[int] = None,
                current_shares: Optional[int] = None) -> AddPositionReport:
        """
        综合四级分析
        sno: 加仓序号（1=首次建仓，2=二次加仓，>=3=禁止再加仓）
        code6: 6位股票代码（用于查 Grade 动态门槛）
        holding_days: 持仓天数
        sector_change_pct: 板块当日涨跌幅（%），用于板块共振判断
        """
        df = self._load_kline(code, days=120)

        # 第一级
        code6_for_grade = code.lstrip("sh").lstrip("sz")
        lv1 = self.analyze_level1(cost, current_price, sno, code6_for_grade)

        # 第二级
        lv2 = self.analyze_level2(df)

        # 第三级
        lv3 = self.analyze_level3(df, highest_price, current_price)

        # 第四级
        lv4, signals = self.analyze_level4(df, code, sector_change_pct)

        # 综合评分 = 四级等权平均（满分100）
        total = (lv1.score + lv2.score + lv3.score + lv4.score) / 4

        # 是否可以加仓：1级通过 and 2级通过 and 3级通过 and 4级通过
        can_add = lv1.passed and lv2.passed and lv3.passed and lv4.passed

        # ── 补充：如果 highest_price == current_price，说明最高价未单独维护
        # 此时 L3 回撤检查会失真，给出提示 ──
        drawdown_hint = ""
        if highest_price == current_price:
            drawdown_hint = (
                "\n⚠️ 注：highest_price=current_price，最高价未单独维护，"
                "L3回撤检查结果仅供参考。"
            )

        # 汇总理由
        reason_lines = [
            f"【第一级·浮盈】{lv1.detail}",
            f"【第二级·趋势】{lv2.detail}",
            f"【第三级·冲突】{lv3.detail}{drawdown_hint}",
            f"【第四级·信号】{lv4.detail}",
        ]
        reason = "\n".join(reason_lines)

        if can_add:
            action = f"✅ 建议加仓（已触发：{'、'.join(signals)}）"
        elif not lv1.passed:
            action = f"❌ 浮盈不足，暂不加仓（浮盈{lv1.score:.0f}/需{lv1.score:.0f})"
        elif not lv2.passed:
            action = "❌ 趋势不健康，暂不加仓"
        elif not lv3.passed:
            action = "❌ 止盈冲突，禁止加仓"
        else:
            action = "❌ 无加仓信号，观望"

        return AddPositionReport(
            code=code,
            name=name,
            current_price=current_price,
            cost=cost,
            holding_days=holding_days,
            level1=lv1,
            level2=lv2,
            level3=lv3,
            level4=lv4,
            total_score=total,
            can_add=can_add,
            add_signal=signals,
            reason=reason,
            action=action,
        )

    # ─────────────────────────────────────────────────
    # 批量分析（支持多只持仓）
    # ─────────────────────────────────────────────────
    def batch_analyze(self, holdings: Optional[List[dict]] = None,
                      sector_data: Optional[Dict[str, dict]] = None,
                      auto_infer_add_count: bool = True) -> List[AddPositionReport]:
        """
        分析持仓加仓信号。

        若 holdings 为 None，自动从 HOLDINGS_FILE 读取原始持仓文件。
        只读文件，不修改原始数据。

        holdings 原始字段说明（对应 holdings.json）：
          code, name, cost, shares, init_shares, current_price,
          highest_price, entry_date, strategy_name, score,
          stop_level_hit, stop_lose_hit

        自动新增字段（不写入 holdings.json，仅内存）：
          _sno:          加仓序号（1=首仓，2=已加仓）
          _sina_code:    新浪格式代码 sh/sz 前缀
          _holding_days: 持仓天数
          _add_count:    已加仓次数（推断）
        """
        # ── 读取原始持仓（只读）────────────────────────────
        if holdings is None:
            holdings = load_holdings_from_file(HOLDINGS_FILE)

        self.sector_data = sector_data or {}
        reports = []

        for h in holdings:
            try:
                code_raw = h.get("code", "")
                code_sina = _to_sina_code(code_raw)
                name = h.get("name", code_raw)
                cost = float(h["cost"])
                current_price = float(h["current_price"])
                highest_price = float(h.get("highest_price", current_price))
                holding_days = _infer_holding_days(h)

                # add_count 字段：正式记录加仓次数（若无，推断后存入 _add_count 用于本次分析）
                add_count_raw = h.get("add_count")
                if add_count_raw is None and auto_infer_add_count:
                    # 无 add_count 字段时，从 stop_level_hit[0] 推断历史加仓次数
                    stop = h.get("stop_level_hit", [])
                    add_count = 1 if (stop and stop[0] is True) else 0
                else:
                    add_count = int(add_count_raw) if add_count_raw is not None else 0

                # 内存中的扩展字段（不写回原文件）
                sno = add_count + 1  # sno = add_count + 1

                # 构造带扩展字段的持仓副本
                h_ext = dict(h)
                h_ext["_sno"] = sno
                h_ext["_sina_code"] = code_sina
                h_ext["_holding_days"] = holding_days
                h_ext["_add_count"] = int(add_count)

                report = self.analyze(
                    code=code_sina,
                    name=name,
                    cost=cost,
                    current_price=current_price,
                    highest_price=highest_price,
                    sno=int(add_count) + 1,
                    holding_days=holding_days,
                    sector_change_pct=h_ext.get("sector_change_pct"),
                    entry_date=h.get("entry_date"),
                    init_shares=h.get("init_shares"),
                    current_shares=h.get("shares"),
                )
                # 附加扩展元数据（不改变 AddPositionReport 结构）
                report._meta = {
                    "sno": sno,
                    "sina_code": code_sina,
                    "raw_code": code_raw,
                    "init_shares": h.get("init_shares"),
                    "current_shares": h.get("shares"),
                    "strategy": h.get("strategy_name", ""),
                }
                reports.append(report)
            except Exception as e:
                print(f"分析 {h.get('code','?')} 失败: {e}")
        # 写入分析日志
        try:
            log_analysis_batch(reports, tag="add_position_check")
        except Exception as e:
            print(f"[警告] 分析日志写入失败: {e}")
        return reports


# ═══════════════════════════════════════════════════════════
# 格式化输出
# ═══════════════════════════════════════════════════════════

def _meta(report: AddPositionReport) -> dict:
    """兼容：提取 report._meta 或空字典"""
    return getattr(report, '_meta', {})


def format_report(report: AddPositionReport) -> str:
    """格式化加仓分析报告为文本"""
    profit_pct = (report.current_price / report.cost - 1) * 100
    meta = _meta(report)
    sno = meta.get('sno', '?')
    raw_code = meta.get('raw_code', report.code)
    last_add = meta.get('last_add_date', '无记录')

    # 冷却期提示
    can_add_cooldown, cooldown_msg = can_add_position(raw_code)
    cooldown_info = "" if can_add_cooldown else f" ⏳ {cooldown_msg}"

    lines = [
        "=" * 60,
        f"📊 加仓信号分析：{report.name}({raw_code})  [第{sno}仓]{cooldown_info}",
        f"   成本={report.cost:.2f} | 现价={report.current_price:.2f} | "
        f"浮盈={profit_pct:+.2f}% | {report.holding_days}日 | 上次加仓:{last_add}",
        f"   综合评分={report.total_score:.1f}/100",
        f"   {'✅ 可加仓' if report.can_add else '❌ 暂停加仓'} | {report.action}",
        "-" * 60,
        f"  L1浮盈检查  → {'✅ PASS' if report.level1.passed else '❌ FAIL'}（{report.level1.score:.0f}）  {report.level1.detail.split('，')[1] if '，' in report.level1.detail else report.level1.detail}",
        f"  L2趋势健康  → {'✅ PASS' if report.level2.passed else '❌ FAIL'}（{report.level2.score:.0f}）  {'多头排列✅' if '✅' in report.level2.detail else '❌'}",
        f"  L3冲突筛查  → {'✅ PASS' if report.level3.passed else '❌ FAIL'}（{report.level3.score:.0f}）  {report.level3.detail.split('：')[1].split('，')[0] if '：' in report.level3.detail else ''}",
        f"  L4加仓信号  → {'✅ PASS' if report.level4.passed else '❌ FAIL'}（{report.level4.score:.0f}）  {report.level4.detail.split('：')[1] if '：' in report.level4.detail else report.level4.detail}",
    ]

    if report.add_signal:
        lines.append("  已触发信号：" + " / ".join(report.add_signal))

    lines += [
        "-" * 60,
        report.reason,
        "=" * 60,
    ]
    return "\n".join(lines)


def format_batch(reports: List[AddPositionReport]) -> str:
    """批量格式化"""
    lines = ["=" * 60, "📋 持仓加仓信号批量分析报告", "=" * 60]
    for r in reports:
        lines.append(format_report(r))
        lines.append("")  # 空行分隔
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 入口（调试用）
# ═══════════════════════════════════════════════════════════

def main():
    """
    支持两种运行方式：
      python3 add_position_analyzer.py              → 仅分析+打印
      python3 add_position_analyzer.py --feishu     → 分析+打印+飞书推送
      python3 add_position_analyzer.py --feishu "标题" → 自定义标题
    """
    import sys as _sys
    feishu_mode = "--feishu" in _sys.argv
    title_override = None
    for i, a in enumerate(_sys.argv):
        if a == "--feishu" and i + 1 < len(_sys.argv) and not _sys.argv[i + 1].startswith("-"):
            title_override = _sys.argv[i + 1]

    print("=" * 60)
    print("📊 加仓信号分析工具（从 holdings.json 读取）")
    print("=" * 60)

    raw_holdings = load_holdings_from_file(HOLDINGS_FILE)
    print(f"\n[INFO] 读取到 {len(raw_holdings)} 条持仓记录")
    for h in raw_holdings:
        print(f"  - {h['name']}({h['code']}) 成本={h['cost']:.2f} "
              f"现价={h['current_price']:.2f} "
              f"浮盈={(h['current_price']/h['cost']-1)*100:.2f}%")

    print("\n[INFO] 开始四级加仓信号分析...")
    analyzer = AddPositionAnalyzer()
    reports = analyzer.batch_analyze(raw_holdings)

    print("\n" + format_batch(reports))

    # 操作建议汇总
    print("\n" + "=" * 60)
    print("📋 操作建议汇总")
    print("=" * 60)
    can_add = [r for r in reports if r.can_add]
    if can_add:
        print("\n✅ 可加仓：")
        for r in can_add:
            meta = _meta(r)
            print(f"  {r.name}({meta.get('raw_code', r.code)}) "
                  f"第{meta.get('sno', '?')}仓 综合={r.total_score:.1f} "
                  f"触发:{','.join(r.add_signal)}")
    else:
        print("\n❌ 当前无符合加仓条件的持仓")

    no_add = [r for r in reports if not r.can_add]
    if no_add:
        print("\n❌ 暂停加仓：")
        for r in no_add:
            meta = _meta(r)
            for lv in [r.level1, r.level2, r.level3, r.level4]:
                if not lv.passed:
                    reason = lv.detail.split("：")[1].split("，")[0]                         if "：" in lv.detail else lv.detail
                    print(f"  {r.name}({meta.get('raw_code', r.code)}) → {reason}")
                    break

    # API 说明
    print("\n[API]  save_holdings(holdings_list)  # 备份+原子写入 holdings.json")
    print("[API]  save_cash_balance(data_dict)    # 备份+原子写入 cash_balance.json")
    print("[API]  load_cash_balance()             # 读取现金余额")
    print("[API]  log_analysis_batch(reports, tag) # 写入分析日志")
    print("[API]  send_reports_to_feishu(reports) # 推送到飞书")
    print("[NOTE] 若需调整 highest_price / add_count 等字段，")
    print("        请调用 save_holdings(更新后的列表) 进行保存（自动备份）。")

    # 飞书推送
    if feishu_mode:
        print("\n[INFO] 开始飞书推送...")
        title = title_override or "加仓信号分析"
        result = send_reports_to_feishu(reports, title=title)
        print(f"[FEISHU] {'✅ ' + result['message'] if result['success'] else '❌ ' + result['message']}")


if __name__ == "__main__":
    main()
    print("=" * 60)
    print("📊 加仓信号分析工具（从 holdings.json 读取）")
    print("=" * 60)

    # 加载原始持仓（只读，不修改 holdings.json）
    raw_holdings = load_holdings_from_file(HOLDINGS_FILE)
    print(f"\n[INFO] 读取到 {len(raw_holdings)} 条持仓记录")
    for h in raw_holdings:
        print(f"  - {h['name']}({h['code']}) 成本={h['cost']:.2f} 现价={h['current_price']:.2f} "
              f"浮盈={(h['current_price']/h['cost']-1)*100:.2f}%")

    print("\n[INFO] 开始四级加仓信号分析...")
    analyzer = AddPositionAnalyzer()
    reports = analyzer.batch_analyze(raw_holdings)

    print("\n" + format_batch(reports))

    # 操作建议汇总
    print("\n" + "=" * 60)
    print("📋 操作建议汇总")
    print("=" * 60)
    can_add = [r for r in reports if r.can_add]
    if can_add:
        print("\n✅ 可加仓：")
        for r in can_add:
            meta = _meta(r)
            print(f"  {r.name}({meta.get('raw_code',r.code)}) 第{meta.get('sno','?')}仓 "
                  f"综合={r.total_score:.1f} 触发:{','.join(r.add_signal)}")
    else:
        print("\n❌ 当前无符合加仓条件的持仓")

    no_add = [r for r in reports if not r.can_add]
    if no_add:
        print("\n❌ 暂停加仓：")
        for r in no_add:
            meta = _meta(r)
            # 找第一个失败级别
            for lv in [r.level1, r.level2, r.level3, r.level4]:
                if not lv.passed:
                    reason = lv.detail.split('：')[1].split('，')[0] if '：' in lv.detail else lv.detail
                    print(f"  {r.name}({meta.get('raw_code',r.code)}) → {reason}")
                    break

    # 保存接口演示（供外部调用参考）
    print("\n[API]  save_holdings(holdings_list)  # 备份+原子写入 holdings.json")
    print("[API]  save_cash_balance(data_dict)    # 备份+原子写入 cash_balance.json")
    print("[API]  load_cash_balance()             # 读取现金余额")
    print("[API]  log_analysis_batch(reports, tag='xxx')  # 写入分析日志")

    print("\n[NOTE] 若需调整 highest_price / add_count 等字段，")
    print("        请调用 save_holdings(更新后的列表) 进行保存（自动备份）。")