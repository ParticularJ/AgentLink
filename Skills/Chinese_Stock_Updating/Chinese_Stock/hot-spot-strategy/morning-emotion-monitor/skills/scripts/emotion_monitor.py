"""
早盘情绪交易监控器 v2
=====================
专业A股交易员视角：
1. 集合竞价：观察多空博弈方向，9:20-9:25快照，9:25产生开盘价
2. 开盘头5分钟：确认缺口是否有效
3. 趋势段：按计划执行止盈止损

核心决策：竞价缺口方向 + 开盘头5分钟确认 = 真实信号
"""

import os, sys, json, time, re, yaml, requests, importlib.util
from datetime import datetime, time as dtime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

# ==================== 路径配置 ====================

BASE_DIR      = Path("/home/jarvis/.openclaw/workspace/skills/Chinese_Stock/hot-spot-strategy")
SCRIPTS_DIR   = Path(__file__).parent
HOLDINGS_PATH = Path("/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json")
BUY_WATCH_PATH_DEFAULT = None
RECOMMENDATION_DIRS = [
    BASE_DIR / "recommendations",
    Path("/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/recommendations"),
]

MT_CONFIG_PATH = BASE_DIR / "Medium-termHoldingStrategy" / "skills" / "scripts" / "config.py"
MT_CONFIG = None
try:
    spec = importlib.util.spec_from_file_location("mt_config", str(MT_CONFIG_PATH))
    if spec and spec.loader:
        MT_CONFIG = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(MT_CONFIG)
except Exception as e:
    print(f"{Fore.YELLOW}⚠️ 无法加载止盈配置 {MT_CONFIG_PATH}，将使用默认止盈值: {e}{Style.RESET_ALL}")

# ==================== 飞书推送 ====================
try:
    from simple_feishu import push_signals, push_status
    FEISHU_AVAILABLE = True
except Exception as e:
    FEISHU_AVAILABLE = False
    def push_signals(*a, **kw): return False
    def push_status(*a, **kw): return False
    print(f"{Fore.YELLOW}⚠️ 飞书推送模块不可用，将禁用推送功能: {e}{Style.RESET_ALL}")


# ==================== 交易阶段 ====================

T_AUCTION_START  = dtime(9, 15)   # 竞价开始（可撤）
T_AUCTION_REAL   = dtime(9, 20)   # 有效竞价起始（不可撤）
T_AUCTION_END    = dtime(9, 25)   # 竞价结束→产生开盘价
T_OPEN           = dtime(9, 30)   # 连续竞价开始
T_CONFIRM_END    = dtime(9, 35)   # 缺口确认窗口结束
T_TREND_END      = dtime(11, 30)  # 早盘趋势段结束
T_CLOSE          = dtime(15, 0)

# 竞价情绪级别
AUCTION_BULLISH  = "竞价强势"    # 竞价涨幅 > +2%
AUCTION_WEAK     = "竞价弱势"    # 竞价涨幅 < -2%
AUCTION_FLAT     = "竞价平稳"    # -2% ~ +2%

# 开盘确认方向
OPEN_GAP_UP_VALID    = "缺口高开有效"     # 竞价+开盘头5分钟守住缺口
OPEN_GAP_UP_FAILED   = "缺口高开失败"     # 高开后回落破开盘价
OPEN_GAP_DOWN_PANIC = "低开恐慌见底"     # 低开后缩量见底
OPEN_GAP_DOWN_BREAK = "低开继续下杀"     # 低开后放量破前低

# ==================== 颜色 ====================

C = {
    "竞价强势":  Fore.GREEN + Style.BRIGHT,
    "竞价弱势":  Fore.RED   + Style.BRIGHT,
    "竞价平稳":  Fore.WHITE,
    "亢奋":      Fore.MAGENTA + Style.BRIGHT,
    "冲高":      Fore.MAGENTA,
    "活跃":      Fore.GREEN,
    "回暖":      Fore.CYAN,
    "恐慌":      Fore.YELLOW + Style.BRIGHT,
    "极度恐慌":  Fore.RED + Style.BRIGHT,
    "谨慎":      Fore.YELLOW,
    "平稳":      Fore.WHITE,
    "正常":      Fore.WHITE,
    "高危":      Fore.RED,
}

def _c(tag, text):
    return f"{C.get(tag, Fore.WHITE)}{text}{Style.RESET_ALL}"


# ==================== 竞价追踪器（核心新增） ====================

class AuctionTracker:
    """
    集合竞价追踪器
    9:15-9:20: 每10秒记录一个快照（软参考）
    9:20-9:25: 每5秒记录一个快照（真实不可撤区间）
    9:25:     锁定最终竞价价格，计算竞价涨幅
    """

    SNAPSHOT_INTERVAL_SOFT   = 10   # 9:15-9:20 快照间隔
    SNAPSHOT_INTERVAL_REAL    = 5    # 9:20-9:25 快照间隔
    VALID_AUCTION_SNAPSHOTS  = 3     # 有效快照数量才认为竞价结果可信

    def __init__(self):
        self.reset()

    def reset(self):
        self.snapshots: List[Dict] = []       # {"time": datetime, "price": float, "pct": float}
        self.final_auction_price: Optional[float] = None
        self.final_auction_pct: Optional[float] = None
        self.final_auction_vol: Optional[float] = None
        self.auction_direction: str = "待定"   # 竞价强势/弱势/平稳
        self.is_locked: bool = False           # 9:25后锁定，不再记录
        self.price_drift_pct: float = 0.0     # 竞价过程中价格漂移量(9:15→9:20)
        # 首次快照价格（无论 soft/real），用于计算漂移
        self.first_snapshot_price: Optional[float] = None
        self.first_snapshot_time: Optional[datetime] = None
        self.final_auction_source: str = "snapshot"  # snapshot | open_fallback
        self.start_price: Optional[float] = None  # 9:15或首个快照价格(兼容旧名)
        self.lock_time: Optional[datetime] = None

    def is_in_auction(self, t: dtime = None) -> bool:
        if t is None:
            t = datetime.now().time()
        return T_AUCTION_START <= t < T_AUCTION_END

    def is_real_auction(self, t: dtime = None) -> bool:
        """9:20-9:25：真实不可撤竞价区间"""
        if t is None:
            t = datetime.now().time()
        return T_AUCTION_REAL <= t < T_AUCTION_END

    def record(self, quote: Dict):
        """
        记录竞价快照
        quote 需包含: price, close_prev, volume
        """
        if self.is_locked:
            return

        now = datetime.now()
        t = now.time()

        # 竞价结束后锁定
        if t >= T_AUCTION_END:
            self._lock(quote)
            return

        price      = quote.get("price", 0)
        close_prev = quote.get("close_prev", 0)
        vol        = quote.get("volume", 0)

        if close_prev <= 0 or price <= 0:
            return

        pct = (price - close_prev) / close_prev * 100

        snap = {
            "time":  now,
            "price": price,
            "pct":   pct,
            "vol":   vol,
        }

        # 记录首个快照作为基准（无论 soft 或 real），用于后续漂移计算
        if self.first_snapshot_price is None:
            self.first_snapshot_price = price
            self.first_snapshot_time = now
            # 保持向后兼容的属性名
            self.start_price = price

        # 在真实不可撤竞价区间计算相对于首个快照的漂移
        if self.first_snapshot_price and self.is_real_auction(t):
            try:
                self.price_drift_pct = (price - self.first_snapshot_price) / self.first_snapshot_price * 100
            except Exception:
                self.price_drift_pct = 0.0

        interval = self.SNAPSHOT_INTERVAL_REAL if self.is_real_auction(t) else self.SNAPSHOT_INTERVAL_SOFT

        # 时间过滤：避免重复记录
        if self.snapshots:
            last = self.snapshots[-1]
            if (now - last["time"]).total_seconds() < interval:
                return

        self.snapshots.append(snap)

        # 实时计算竞价方向（仅在真实竞价区间且有足够快照时）
        if self.is_real_auction(t) and len(self.snapshots) >= self.VALID_AUCTION_SNAPSHOTS:
            self._calc_auction_direction()

    def _lock(self, quote: Dict):
        """9:25竞价结束，锁定最终竞价价格"""
        if self.is_locked:
            return
        self.is_locked = True
        self.lock_time = datetime.now()

        price      = quote.get("price", 0)
        close_prev = quote.get("close_prev", 0)
        vol        = quote.get("volume", 0)

        # 优先使用最后一个快照的最终竞价；若无快照结果则回退到开盘价并记录来源
        if self.snapshots:
            last_snap = self.snapshots[-1]
            self.final_auction_price = last_snap.get("price")
            self.final_auction_pct = last_snap.get("pct")
            self.final_auction_vol = last_snap.get("vol", vol)
            self.final_auction_source = "snapshot"
        else:
            if close_prev > 0 and price > 0:
                self.final_auction_price = price
                self.final_auction_pct = (price - close_prev) / close_prev * 100
                self.final_auction_vol = vol
                self.final_auction_source = "open_fallback"

        self._calc_auction_direction()

    def _calc_auction_direction(self):
        """计算竞价方向"""
        # 优先采用最终竞价百分比，否则使用最新快照百分比
        pct = None
        if self.final_auction_pct is not None:
            pct = self.final_auction_pct
        elif self.snapshots:
            pct = self.snapshots[-1].get("pct")

        if pct is None:
            return

        if pct > 2:
            self.auction_direction = AUCTION_BULLISH
        elif pct < -2:
            self.auction_direction = AUCTION_WEAK
        else:
            self.auction_direction = AUCTION_FLAT

    def get_auction_info(self, close_prev: float) -> Dict:
        """
        获取竞价分析结果，供情绪引擎使用
        """
        pct = self.final_auction_pct
        if pct is None and self.snapshots:
            pct = self.snapshots[-1]["pct"]

        drift = self.price_drift_pct

        # 竞价量（最后一条快照的量）
        vol = self.snapshots[-1]["vol"] if self.snapshots else 0
        return {
            "is_auction_phase": self.is_in_auction(),
            "is_real_auction": self.is_real_auction(),
            "is_locked": self.is_locked,
            "auction_price": self.final_auction_price,
            "auction_pct": pct,
            "auction_direction": self.auction_direction,
            "price_drift_pct": drift,          # 竞价漂移（多空博弈痕迹）
            "auction_vol": vol,
            "snapshots_count": len(self.snapshots),
            "is_bullish": self.auction_direction == AUCTION_BULLISH,
            "is_weak": self.auction_direction == AUCTION_WEAK,
            "first_snapshot_price": self.first_snapshot_price,
            "first_snapshot_time": self.first_snapshot_time.strftime('%H:%M:%S') if self.first_snapshot_time else None,
            "final_auction_source": self.final_auction_source,
        }


# ==================== 开盘头5分钟缺口确认器 ====================

class GapConfirmTracker:
    """
    追踪开盘头5分钟的缺口有效性
    9:30-9:35: 关键确认窗口
    """

    def __init__(self):
        self.has_recorded_open = False
        self.open_price: float = 0.0
        self.open_pct: float = 0.0
        self.close_prev: float = 0.0
        self.low_after_open: float = 0.0
        self.high_after_open: float = 0.0
        self.confirmed_direction: str = "待确认"
        self.gap_size: float = 0.0    # 缺口大小%

    def record_open(self, quote: Dict):
        """9:30记录开盘价"""
        if self.has_recorded_open:
            return
        self.open_price   = quote.get("price", 0)
        self.close_prev   = quote.get("close_prev", 0)
        self.low_after_open  = self.open_price
        self.high_after_open = self.open_price
        if self.close_prev > 0:
            self.open_pct = (self.open_price - self.close_prev) / self.close_prev * 100
            self.gap_size = self.open_pct
        self.has_recorded_open = True

    def update_range(self, quote: Dict):
        """9:30后持续更新日内高低"""
        if not self.has_recorded_open:
            return
        high = quote.get("high", 0)
        low  = quote.get("low", 0)
        if high > 0 and self.high_after_open > 0:
            self.high_after_open = max(self.high_after_open, high)
        if low > 0 and self.low_after_open > 0:
            self.low_after_open = min(self.low_after_open, low)

    def confirm(self, quote: Dict, auction_tracker: AuctionTracker) -> str:
        """
        缺口确认判断（在9:35时调用）
        返回方向确认结果
        """
        if not self.has_recorded_open:
            return "待确认"

        price = quote.get("price", 0)
        high  = quote.get("high", 0)
        low   = quote.get("low", 0)

        auction_pct = auction_tracker.final_auction_pct
        auction_dir = auction_tracker.auction_direction

        # 竞价高开 + 开盘后回调守在开盘价上方 = 缺口有效
        if auction_pct is not None and auction_pct > 1.5:
            if low > self.open_price * 0.998:   # 未跌破开盘价
                self.confirmed_direction = OPEN_GAP_UP_VALID
            elif price < self.open_price:
                self.confirmed_direction = OPEN_GAP_UP_FAILED

        # 竞价低开 + 缩量见底
        elif auction_pct is not None and auction_pct < -1.5:
            if price > self.open_price * 1.002:   # 反弹翻红
                self.confirmed_direction = OPEN_GAP_DOWN_PANIC
            elif price < self.low_after_open * 1.005 and auction_dir == AUCTION_WEAK:
                self.confirmed_direction = OPEN_GAP_DOWN_BREAK

        # 高开且当前价格跌破开盘价2%以上 = 高开失败
        elif self.open_pct > 1.5 and price < self.open_price * 0.98:
            self.confirmed_direction = OPEN_GAP_UP_FAILED

        # 低开后反弹翻红 = 恐慌见底
        elif self.open_pct < -1.5 and price > self.close_prev * 1.0:
            self.confirmed_direction = OPEN_GAP_DOWN_PANIC

        return self.confirmed_direction

    def get_gap_info(self) -> Dict:
        return {
            "has_recorded": self.has_recorded_open,
            "open_price": self.open_price,
            "open_pct": self.open_pct,
            "gap_size": self.gap_size,
            "confirmed_direction": self.confirmed_direction,
            "low_after_open": self.low_after_open,
            "high_after_open": self.high_after_open,
        }


# ==================== 数据适配器 ====================

class QuoteAdapter:
    """实时行情适配器"""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._cache_ts: Dict[str, float] = {}

    @staticmethod
    def _tx_prefix(code: str) -> str:
        """
        将股票代码转换为腾讯接口需要的 (prefix, raw_code)
        上海: 60xxxx, 68xxxx, 510xxxx, 512xxxx, 515xxxx, 588xxxx
        深圳: 00xxxx, 30xxxx, 002xxx, 003xxx, 1xxxxx(深圳ETF), 15xxxx, 16xxxx
        """
        c = code.lower()
        if c.startswith(("sh", "sz", "bj")):
            return c[:2], c[2:]
        if c.startswith("68"):
            return "sh", c
        if c.startswith(("00", "30")):
            return "sz", c
        if c.startswith("60"):
            return "sh", c
        # 深圳ETF: 1xxxxx (159xxx, 160xxx, 161xxx等)
        if c.startswith(("1", "2")) and len(c) == 6:
            return "sz", c
        return "sh", c

    def get_one(self, code: str, force: bool = False) -> Optional[Dict]:
        cache_ttl = 5.0
        if not force and code in self._cache and time.time() - self._cache_ts.get(code, 0) < cache_ttl:
            return self._cache[code]
        try:
            prefix, raw = self._tx_prefix(code)
            url = f"https://qt.gtimg.cn/q={prefix}{raw}"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com/"}, timeout=5)
            txt = r.text.strip()
            if "none_match" in txt or not txt:
                return None
            m = re.search(r'"([^"]+)"', txt)
            if not m:
                return None
            f = m.group(1).split("~")
            if len(f) < 45:
                return None
            price = float(f[3])
            cp = float(f[4])
            q = {
                "code": code,
                "name": f[1],
                "price": price,
                "open": float(f[5]),
                "high": float(f[33]),
                "low": float(f[34]),
                "close_prev": cp,
                "volume": float(f[6]) * 100,
                "turnover": float(f[38]) if f[38] else 0.0,
                "bid1": float(f[9]),
                "bid1_vol": float(f[10]) * 100,
                "ask1": float(f[19]),
                "ask1_vol": float(f[20]) * 100,
                "up_down_pct": ((price - cp) / cp * 100) if cp > 0 else 0.0,
            }
            self._cache[code] = q
            self._cache_ts[code] = time.time()
            return q
        except Exception as e:
            print(f"{Fore.RED}行情[{code}]: {e}{Style.RESET_ALL}")
            return None

    def get_batch(self, codes: List[str]) -> Dict[str, Dict]:
        if not codes:
            return {}
        parts = []
        code_map = {}
        for code in codes:
            prefix, raw = self._tx_prefix(code)
            key = "%s%s" % (prefix, raw)
            parts.append(key)
            code_map[key] = code
        url = "https://qt.gtimg.cn/q=" + ",".join(parts)
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com/"}, timeout=8)
            results = {}
            for line in r.text.strip().splitlines():
                line = line.strip()
                if not line or "none_match" in line:
                    continue
                m = re.match(r'v_([a-z]{2}\d+)="([^"]+)"', line)
                if not m:
                    continue
                key = m.group(1)
                data = m.group(2)
                fields = data.split("~")
                if len(fields) < 45:
                    continue
                original = code_map.get(key, key)
                price = float(fields[3])
                cp = float(fields[4])
                results[original] = {
                    "code": original,
                    "name": fields[1],
                    "price": price,
                    "open": float(fields[5]),
                    "high": float(fields[33]),
                    "low": float(fields[34]),
                    "close_prev": cp,
                    "volume": float(fields[6]) * 100,
                    "turnover": float(fields[38]) if fields[38] else 0.0,
                    "bid1": float(fields[9]),
                    "bid1_vol": float(fields[10]) * 100,
                    "ask1": float(fields[19]),
                    "ask1_vol": float(fields[20]) * 100,
                    "up_down_pct": ((price - cp) / cp * 100) if cp > 0 else 0.0,
                }
            return results
        except Exception as e:
            print("%s批量行情失败: %s%s" % (Fore.RED, e, Style.RESET_ALL))
            return {}
            return {}


# ==================== 持仓/观察名单管理 ====================

class HoldingsMgr:
    def __init__(self, path=None):
        self.path = Path(path) if path else HOLDINGS_PATH
        self.holdings: List[Dict] = []
        self._load()
    def _load(self):
        if self.path.exists():
            with open(self.path) as f:
                self.holdings = json.load(f) or []
    def get_all(self):
        return self.holdings
    def get(self, code):
        for h in self.holdings:
            if h.get("code") == code:
                return h
        return None
    def reload(self):
        self._load()

class WatchListMgr:
    def __init__(self, path=None):
        self.path = Path(path) if path else BUY_WATCH_PATH_DEFAULT
        if self.path and self.path.name == "buy_watch.yaml":
            print(f"{Fore.YELLOW}⚠️ 已忽略 buy_watch.yaml 监控，改为从推荐目录加载买入名单{Style.RESET_ALL}")
            self.path = None
        self.list: List[Dict] = []
        self._load()

    def _find_latest_recommendation(self, directory: Path) -> Optional[Path]:
        if not directory.exists() or not directory.is_dir():
            return None
        candidates = list(directory.glob('*morning_buy_recommendation.json'))
        if not candidates:
            candidates = list(directory.glob('*.json'))
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _load_recommendation_file(self, file_path: Path) -> List[Dict]:
        try:
            with open(file_path) as f:
                data = json.load(f)
        except Exception:
            return []
        recs = data.get("recommendations", []) if isinstance(data, dict) else []
        result = []
        for r in recs:
            code = str(r.get("code", "")).strip()
            if not code:
                continue
            name = str(r.get("name", code)).strip()
            result.append({
                "code": code,
                "name": name,
                "trigger_mode": "auction_strong",
                "trigger_value": 1.5,
                "max_position": 50000,
                "phase": "all",
                "source": str(file_path.name),
            })
        return result

    def _load(self):
        self.list = []
        if self.path:
            if self.path.exists() and self.path.is_file():
                if self.path.suffix in {".yaml", ".yml"}:
                    with open(self.path) as f:
                        data = yaml.safe_load(f)
                    if data and isinstance(data, dict):
                        watchlist = data.get("watchlist", {})
                        if isinstance(watchlist, dict):
                            for category, bucket in watchlist.items():
                                if not isinstance(bucket, dict):
                                    continue
                                for section in ("core", "focus"):
                                    items = bucket.get(section, [])
                                    if isinstance(items, list):
                                        for item in items:
                                            if isinstance(item, (list, tuple)) and len(item) >= 2:
                                                name, code = item[0], item[1]
                                                self.list.append({
                                                    "name": str(name),
                                                    "code": str(code),
                                                    "category": str(category),
                                                    "section": section,
                                                    "trigger_mode": "auction_strong",
                                                    "trigger_value": 1.5,
                                                    "max_position": 50000,
                                                    "phase": "all",
                                                })
                elif self.path.suffix == ".json":
                    self.list.extend(self._load_recommendation_file(self.path))
            elif self.path and self.path.exists() and self.path.is_dir():
                latest = self._find_latest_recommendation(self.path)
                if latest:
                    self.list.extend(self._load_recommendation_file(latest))
        else:
            seen = set()
            for directory in RECOMMENDATION_DIRS:
                latest = self._find_latest_recommendation(directory)
                if latest:
                    for item in self._load_recommendation_file(latest):
                        if item["code"] not in seen:
                            self.list.append(item)
                            seen.add(item["code"])
        print(f"{Fore.GREEN}✅ 买入名单已加载: {len(self.list)}支{Style.RESET_ALL}")

    def get_all(self):
        return self.list

    def get_codes(self):
        return [w.get("code", "") for w in self.list if w.get("code")]

    def reload(self):
        self._load()


# ==================== 竞价信号分类器 ====================

class AuctionSignalClassifier:
    """
    基于竞价结果+开盘头5分钟确认的专业信号分类

    决策树:
    1. 竞价方向 → 确定开盘基调（多/空/中性）
    2. 开盘缺口大小 → 确定操作策略
    3. 开盘后5分钟走势 → 确认/否定信号
    4. 综合给出: 买入/卖出/观望 + 置信度
    """

    @staticmethod
    def classify(
        auction_info: Dict,
        gap_info: Dict,
        quote: Dict,
        phase: str,
    ) -> Dict:
        """
        返回信号详情
        {
            "signal": BUY/SELL/WATCH,
            "action": "买入/卖出/观望",
            "reason": "...",
            "confidence": 0.0-1.0,
            "urgency": HIGH/MEDIUM/LOW,
            "emotion": "...",
            "tags": ["竞价高开", "缺口有效"],
        }
        """
        auction_pct   = auction_info.get("auction_pct")
        auction_dir   = auction_info.get("auction_direction", "待定")
        is_locked     = auction_info.get("is_locked", False)
        price_drift   = auction_info.get("price_drift_pct", 0)
        auction_price = auction_info.get("auction_price")

        open_pct      = gap_info.get("open_pct", 0)
        open_price    = gap_info.get("open_price", 0)
        gap_confirmed = gap_info.get("confirmed_direction", "待确认")
        gap_size      = gap_info.get("gap_size", 0)

        price         = quote.get("price", 0)
        close_prev    = quote.get("close_prev", 0)
        current_pct   = quote.get("up_down_pct", 0)
        high          = quote.get("high", 0)
        low           = quote.get("low", 0)
        turnover      = quote.get("turnover", 0)
        bid1          = quote.get("bid1", 0)
        ask1          = quote.get("ask1", 0)

        if close_prev <= 0:
            return {"signal": "WATCH", "action": "观望", "reason": "数据异常", "confidence": 0.0,
                    "urgency": "LOW", "emotion": "无法判断", "tags": []}

        tags = []
        signal = "WATCH"
        action = "观望"
        urgency = "LOW"
        confidence = 0.0
        emotion = "平稳"
        reason = ""

        # ========================
        # 情形A: 竞价强势 (+2%以上)
        # ========================
        if auction_dir == AUCTION_BULLISH:
            tags.append("竞价强势")
            if auction_pct and auction_pct > 5:
                tags.append("竞价亢奋")

            # 高开后守住开盘价 → 有效缺口，回踩买入
            if gap_confirmed == OPEN_GAP_UP_VALID:
                signal = "BUY"
                action = "回踩买入"
                confidence = 0.85
                urgency = "MEDIUM"
                emotion = "回暖"
                reason = f"竞价强势+缺口有效，回踩{open_price:.2f}买入"
                tags.append("缺口有效")

            # 高开后跌破开盘价 → 高开失败，观望
            elif gap_confirmed == OPEN_GAP_UP_FAILED:
                signal = "WATCH"
                action = "观望"
                urgency = "LOW"
                emotion = "谨慎"
                reason = f"竞价高开{auction_pct:.1f}%后回落失败，谨慎"
                tags.append("高开失败")

            # 缺口待确认（开盘阶段）
            elif gap_confirmed == "待确认":
                if phase in ("集合竞价", "等待开盘"):
                    signal = "WATCH"
                    action = "等待开盘确认"
                    urgency = "LOW"
                    emotion = "竞价强势"
                    reason = f"竞价强势(+{auction_pct:.1f}%)，等待9:30后确认"
                    confidence = 0.0
                else:
                    # 9:30后，看开盘价位置
                    if open_pct > 1.5:
                        if low > open_price * 0.998:
                            signal = "BUY"
                            action = "支撑买入"
                            confidence = 0.7
                            urgency = "MEDIUM"
                            emotion = "回暖"
                            reason = f"竞价强势({auction_pct:.1f}%)，开盘支撑确认"
                            tags.append("开盘支撑")
                        else:
                            signal = "WATCH"
                            action = "观望"
                            urgency = "LOW"
                            emotion = "谨慎"
                            reason = "高开后跌破开盘价，高开有效性存疑"
                            tags.append("高开存疑")

        # ========================
        # 情形B: 竞价弱势 (-2%以下)
        # ========================
        elif auction_dir == AUCTION_WEAK:
            tags.append("竞价弱势")
            if auction_pct and auction_pct < -5:
                tags.append("竞价恐慌")

            # 低开后反弹翻红 → 恐慌见底，低吸
            if gap_confirmed == OPEN_GAP_DOWN_PANIC:
                signal = "BUY"
                action = "恐慌低吸"
                confidence = 0.80
                urgency = "HIGH"
                emotion = "恐慌"
                reason = f"竞价恐慌({auction_pct:.1f}%)后企稳，恐慌低吸"
                tags.append("恐慌见底")

            # 低开后继续下杀 → 趋势走坏，止损或不做
            elif gap_confirmed == OPEN_GAP_DOWN_BREAK:
                signal = "SELL"
                action = "止损/出局"
                confidence = 0.90
                urgency = "HIGH"
                emotion = "极度恐慌"
                reason = f"竞价弱势({auction_pct:.1f}%)，低开后继续下杀，止损"
                tags.append("继续破底")

            # 竞价弱势 + 开盘未继续大跌但翻红 → 部分反弹机会
            elif gap_confirmed == "待确认":
                if phase in ("集合竞价", "等待开盘"):
                    signal = "WATCH"
                    action = "等待开盘"
                    urgency = "LOW"
                    emotion = "竞价弱势"
                    reason = f"竞价弱势({auction_pct:.1f}%)，等待9:30后确认"
                    confidence = 0.0
                else:
                    # 开盘跌幅不大，且当前有支撑迹象
                    if current_pct > -3 and current_pct < 0:
                        signal = "BUY"
                        action = "轻仓试探"
                        confidence = 0.55
                        urgency = "MEDIUM"
                        emotion = "恐慌"
                        reason = f"竞价低开但未崩，试探买入"
                        tags.append("低开试探")
                    elif current_pct <= -5:
                        signal = "WATCH"
                        action = "等待确认"
                        urgency = "LOW"
                        emotion = "极度恐慌"
                        reason = "恐慌延续，等止跌信号"
                        tags.append("等待止跌")

        # ========================
        # 情形C: 竞价平稳 (-2%~+2%)
        # ========================
        else:
            tags.append("竞价平稳")
            emotion = "平稳"

            # 竞价平稳 + 高开高走
            if open_pct > 1.5 and current_pct > open_pct * 0.9:
                signal = "WATCH"
                action = "等待回调"
                urgency = "LOW"
                emotion = "活跃"
                reason = "竞价平稳，高开后强势，等回调再买"
                tags.append("强势高开")

            # 竞价平稳 + 低开后反弹
            elif open_pct < -1.5 and current_pct > -1.0:
                signal = "BUY"
                action = "回调买入"
                confidence = 0.60
                urgency = "MEDIUM"
                emotion = "回暖"
                reason = "竞价平稳，低开后企稳，回调买入"
                tags.append("低开后企稳")

            # 竞价平稳 + 开盘在平盘附近 → 全天震荡，等趋势
            else:
                signal = "WATCH"
                action = "观望"
                urgency = "LOW"
                emotion = "平稳"
                reason = "竞价平稳，开盘平开，全天方向待定"
                tags.append("平开震荡")

        return {
            "signal": signal,
            "action": action,
            "reason": reason,
            "confidence": confidence,
            "urgency": urgency,
            "emotion": emotion,
            "tags": tags,
            "auction_pct": auction_pct,
            "open_pct": open_pct,
            "gap_confirmed": gap_confirmed,
        }


# ==================== 持仓卖出评估 ====================
# 核心原则: 不止损，冲高卖，等反弹
# 逻辑:
#   1. 不到目标价位不卖（+3%起才开始考虑）
#   2. 冲高回落到原点必卖（坐过山车宁可少赚）
#   3. 竞价恐慌低开，等反弹再卖，不杀在最低
#   4. 滞涨就卖（不贪）

class SellSignalEvaluator:
    """
    情绪股卖出评估器

    目标: 让利润奔跑，但不让利润回吐
    - 不设止损线（情绪股止损=割在最低）
    - 按各股级别配置的止盈点分档卖出
    - 冲高回落立即卖（不等涨幅）
    - 竞价低开后反弹乏力立即卖
    """

    DEFAULT_PROFIT_TIERS = [
        (3.0,  0.33),   # +3%  卖1/3
        (5.0,  0.33),   # +5%  再卖1/3
        (8.0,  0.34),   # +8%  清仓
    ]

    def __init__(self, stop_loss_pct=-999, take_profit_pct=999):
        # 禁用传统止损止盈，用新逻辑
        pass

    def _get_profit_tiers(self, code: str) -> List[Tuple[float, float]]:
        if not MT_CONFIG:
            return self.DEFAULT_PROFIT_TIERS

        stock_grade = getattr(MT_CONFIG, "STOCK_GRADE", {}).get(code, "L3_题材跟风")
        grade_cfg = getattr(MT_CONFIG, "GRADE_CONFIG", {}).get(stock_grade)
        if not grade_cfg:
            grade_cfg = getattr(MT_CONFIG, "GRADE_CONFIG", {}).get("L3_题材跟风")
        if not grade_cfg:
            return self.DEFAULT_PROFIT_TIERS

        profit_targets = grade_cfg.get("profit_targets", [])
        sell_ratio = grade_cfg.get("sell_ratio", [])
        if not profit_targets or not sell_ratio or len(profit_targets) != len(sell_ratio):
            return self.DEFAULT_PROFIT_TIERS

        return [(round(pt * 100, 2), sr) for pt, sr in zip(profit_targets, sell_ratio)]

    def eval(self, holding: Dict, quote: Dict,
             auction_info: Dict, gap_info: Dict) -> Optional[Dict]:
        """
        评估持仓是否触发卖出
        新逻辑优先级:
          1. 冲高回落（最高点回落≥2%即卖）
          2. 竞价低开后反弹无力（不杀跌，等反弹）
          3. 固定涨幅分档卖出
        """
        code   = holding.get("code", "")
        name   = holding.get("name", "unknown")
        cost   = holding.get("cost", 0)
        shares = holding.get("shares", 0)
        # 持仓历史最高价（跨时间追踪）
        peak_price = holding.get("peak_price", cost)

        price       = quote.get("price", 0)
        high        = quote.get("high", 0)
        open_price  = quote.get("open", 0)
        current_pct = quote.get("up_down_pct", 0)   # 今日涨幅%

        if cost <= 0 or shares <= 0 or price <= 0:
            return None

        gain_vs_cost = (price - cost) / cost * 100   # 相对成本涨幅%
        open_pct     = gap_info.get("open_pct", 0)   # 开盘缺口%
        gap_conf     = gap_info.get("confirmed_direction", "待确认")
        auction_dir  = auction_info.get("auction_direction", "待定")
        auction_pct  = auction_info.get("auction_pct", 0)

        # ---- 更新持仓峰值 ----
        if high > peak_price:
            peak_price = high

        # ---- 优先级1: 冲高回落（核心逻辑）----
        # 最高点到现在回落超过2%，且当前仍有收益 → 立即卖
        if peak_price > cost and price < peak_price * 0.98:
            pullback_pct = (peak_price - price) / peak_price * 100
            # 计算 peak_price 对应的持仓收益
            peak_gain = (peak_price - cost) / cost * 100
            if gain_vs_cost > 0:
                # 有收益但从高位回落 → 卖（锁定利润）
                sold_amt = int(shares * 0.5)
                return {
                    "type": "SELL", "code": code, "name": name,
                    "action": "冲高回落",
                    "price": price, "shares": sold_amt,
                    "amount": sold_amt * price,
                    "reason": (f"从最高{peak_price:.2f}(+{peak_gain:.1f}%)"
                               f"回落{pullback_pct:.1f}%，当前+{gain_vs_cost:.1f}%，卖半仓"),
                    "gain_vs_cost": gain_vs_cost,
                    "signal_type": "spike_fade",
                    "urgency": "HIGH",
                }

        # ---- 优先级2: 竞价极度恐慌低开后的处理 ----
        # 竞价< -5% 低开，等反弹不杀跌
        if auction_pct < -5 and gain_vs_cost < -3:
            # 竞价崩盘低开，不止损，等反弹
            return {
                "type": "SELL", "code": code, "name": name,
                "action": "持有(等反弹)",
                "price": price, "shares": 0, "amount": 0,
                "reason": (f"竞价恐慌({auction_pct:.1f}%)低开，"
                           f"持仓{gain_vs_cost:.1f}%，不杀跌等反弹"),
                "gain_vs_cost": gain_vs_cost,
                "signal_type": "wait_rebound",
                "urgency": "LOW",
            }

        # 竞价弱势 + 持仓已回落到成本附近 → 卖（不贪）
        if auction_dir == AUCTION_WEAK and gain_vs_cost < 1.0 and gain_vs_cost > -2.0:
            sold_amt = shares
            return {
                "type": "SELL", "code": code, "name": name,
                "action": "反弹卖出",
                "price": price, "shares": sold_amt,
                "amount": sold_amt * price,
                "reason": (f"竞价弱势({auction_pct:.1f}%)，"
                           f"反弹到成本附近+{gain_vs_cost:.1f}%，不贪卖出"),
                "gain_vs_cost": gain_vs_cost,
                "signal_type": "weak_rebound_sell",
                "urgency": "MEDIUM",
            }

        # ---- 优先级3: 固定涨幅分档卖出 ----
        for threshold, fraction in self._get_profit_tiers(code):
            if gain_vs_cost >= threshold:
                to_sell_amt = int(shares * fraction)
                if to_sell_amt < 100:
                    continue

                action = ("清仓" if fraction >= 0.5 else f"分批卖出(+{threshold:.0f}%)")
                reason = (f"+{gain_vs_cost:.1f}%达到目标{threshold:.0f}%，卖出{fraction*100:.0f}%仓位"
                          if fraction < 1.0 else f"+{gain_vs_cost:.1f}%达到目标{threshold:.0f}%清仓")

                return {
                    "type": "SELL", "code": code, "name": name,
                    "action": action,
                    "price": price, "shares": to_sell_amt,
                    "amount": to_sell_amt * price,
                    "reason": reason,
                    "gain_vs_cost": gain_vs_cost,
                    "signal_type": "profit_take",
                    "urgency": "MEDIUM",
                }

        return None


# ==================== 核心监控器 ====================

class MorningEmotionMonitor:
    """
    早盘情绪交易监控器 v2

    阶段流程:
    9:15-9:25  竞价追踪 → AuctionTracker记录快照
    9:25        竞价结束 → 计算竞价缺口方向，生成竞价信号
    9:30        开盘     → GapConfirmTracker记录开盘价
    9:30-9:35  缺口确认 → GapConfirmTracker确认缺口有效性
    9:35+       趋势确认 → 结合竞价信号+缺口确认，发出最终操作信号
    """

    def __init__(self, holdings_path=None, buy_watch_path=None):
        self.holdings_mgr  = HoldingsMgr(holdings_path)
        self.watch_mgr     = WatchListMgr(buy_watch_path)
        self.quote_adapter = QuoteAdapter()
        self.sell_eval     = SellSignalEvaluator()

        # 各标的追踪器（key: code）
        self.auction_trackers: Dict[str, AuctionTracker] = {}
        self.gap_trackers: Dict[str, GapConfirmTracker] = {}

        # 信号冷却
        self.cooldown_sec = 120
        self.buy_cooldown: Dict[str, float] = {}
        self.sell_cooldown: Dict[str, float] = {}
        self.sell_push_record: Dict[Tuple[str, str], float] = {}
        self.signals_sent = {"buy": 0, "sell": 0}

        # 飞书
        self.feishu_enabled = False
        self.last_feishu_push = 0
        self._auction_brief_sent = False

        # 锁定期标记（竞价结束后锁定一次诊断）
        self.auction_summary_done: set = set()

    def _get_tracker(self, code: str) -> Tuple[AuctionTracker, GapConfirmTracker]:
        if code not in self.auction_trackers:
            self.auction_trackers[code] = AuctionTracker()
            self.gap_trackers[code] = GapConfirmTracker()
        return self.auction_trackers[code], self.gap_trackers[code]

    def _get_phase(self) -> str:
        t = datetime.now().time()
        if t < T_AUCTION_START:  return "盘前"
        if t < T_AUCTION_REAL:   return "竞价(可撤)"
        if t < T_AUCTION_END:    return "竞价(有效)"
        if t < T_OPEN:           return "等待开盘"
        if t < T_CONFIRM_END:    return "缺口确认"
        if t < T_TREND_END:      return "趋势确认"
        if t < dtime(12,0):      return "午盘"
        if t < T_CLOSE:          return "下午"
        return "收盘"

    def _is_in_auction(self) -> bool:
        t = datetime.now().time()
        return T_AUCTION_START <= t < T_AUCTION_END

    def _is_in_confirm_window(self) -> bool:
        t = datetime.now().time()
        return T_OPEN <= t <= T_CONFIRM_END

    # ---------- 核心评估 ----------

    def eval(self, quotes: Dict[str, Dict]) -> Dict[str, List[Dict]]:
        """
        对所有标的进行评估
        """
        now = time.time()
        phase = self._get_phase()
        buy_signals = []
        sell_signals = []
        holding_recommendations = []

        all_codes = set(quotes.keys())

        for code in all_codes:
            quote = quotes[code]
            auction_t, gap_t = self._get_tracker(code)

            # ---- 竞价追踪 ----
            if self._is_in_auction():
                auction_t.record(quote)
            elif not auction_t.is_locked:
                # 竞价结束瞬间，锁定
                auction_t._lock(quote)
                # 如果没有竞价快照，用开盘价补充
                if auction_t.final_auction_price is None:
                    auction_t.final_auction_price = quote.get("open", quote.get("price"))
                    auction_t.final_auction_pct = quote.get("up_down_pct", 0)
                    auction_t._calc_auction_direction()

            # ---- 缺口追踪 ----
            if T_OPEN <= datetime.now().time() <= T_CONFIRM_END:
                if not gap_t.has_recorded_open and quote.get("open", 0) > 0:
                    gap_t.record_open(quote)
                gap_t.update_range(quote)

            # ---- 获取各维度信息 ----
            close_prev = quote.get("close_prev", 0)
            auction_info = auction_t.get_auction_info(close_prev)
            gap_info     = gap_t.get_gap_info()
            auction_dir  = auction_info.get("auction_direction", "待定")

            # ---- 评估买入标的 ----
            watch_item = next((w for w in self.watch_mgr.get_all() if w.get("code") == code), None)
            if watch_item and code not in self.buy_cooldown:
                sig = self._eval_buy(watch_item, quote, auction_info, gap_info, phase)
                if sig:
                    buy_signals.append(sig)
                    self.buy_cooldown[code] = now + self.cooldown_sec
                    self.signals_sent["buy"] += 1

            # ---- 评估持仓建议 ----
            holding = self.holdings_mgr.get(code)
            if holding:
                rec = self._eval_holding_recommendation(holding, quote, auction_info, gap_info)
                if rec:
                    holding_recommendations.append(rec)

            # ---- 评估卖出标的(持仓) ----
            if holding and (code not in self.sell_cooldown or now - self.sell_cooldown.get(code, 0) > self.cooldown_sec):
                sig = self.sell_eval.eval(holding, quote, auction_info, gap_info)
                if sig:
                    sell_signals.append(sig)
                    self.sell_cooldown[code] = now
                    self.signals_sent["sell"] += 1

        return {"buy": buy_signals, "sell": sell_signals, "holding_recommendations": holding_recommendations}

    def _eval_buy(self, watch: Dict, quote: Dict,
                  auction_info: Dict, gap_info: Dict, phase: str) -> Optional[Dict]:
        """
        评估买入信号
        竞价阶段: 记录但不触发，等9:25确认
        9:25-9:30: 竞价结束，根据竞价方向决策
        9:30+:    结合缺口确认结果决策
        """
        code   = watch.get("code", "")
        name   = watch.get("name", "")
        price  = quote.get("price", 0)
        cp     = quote.get("close_prev", 0)
        current_pct = quote.get("up_down_pct", 0)
        max_amt = watch.get("max_position", 50000)

        if cp <= 0 or price <= 0:
            return None

        auction_dir = auction_info.get("auction_direction", "待定")
        auction_pct = auction_info.get("auction_pct")
        gap_conf    = gap_info.get("confirmed_direction", "待确认")
        open_pct    = gap_info.get("open_pct", 0)
        trigger_mode = watch.get("trigger_mode", "pct_vs_close")
        trigger_val  = watch.get("trigger_value", 0)
        watch_phase  = watch.get("phase", "all")

        # ---- 价格触发 ----
        triggered, trigger_price = self._calc_trigger(trigger_mode, trigger_val, cp, price)
        if not triggered:
            return None

        # ---- 竞价阶段: 9:15-9:25，不触发，等确认 ----
        if phase in ("竞价(可撤)", "竞价(有效)", "等待开盘"):
            if auction_dir == AUCTION_WEAK and auction_pct and auction_pct < -3:
                # 竞价恐慌，等开盘确认
                return {
                    "type": "BUY", "code": code, "name": name,
                    "action": "等待确认(竞价恐慌)",
                    "price": price, "trigger_price": trigger_price,
                    "shares": 0, "amount": 0,
                    "reason": f"竞价恐慌({auction_pct:.1f}%)，等开盘确认后买入",
                    "confidence": 0.0, "urgency": "LOW",
                    "emotion": "恐慌", "auction_dir": auction_dir,
                    "tags": ["竞价恐慌", "等确认"],
                }
            return None

        # ---- 竞价弱势 + 恐慌 → 激进买入 ----
        if auction_dir == AUCTION_WEAK and auction_pct and auction_pct < -2:
            if gap_conf == OPEN_GAP_DOWN_PANIC or (gap_conf == "待确认" and current_pct > -3):
                shares = max_amt // price
                return {
                    "type": "BUY", "code": code, "name": name,
                    "action": "恐慌低吸",
                    "price": price, "trigger_price": trigger_price,
                    "shares": shares, "amount": shares * price,
                    "reason": f"竞价弱势({auction_pct:.1f}%)，恐慌见底，触发买入",
                    "confidence": 0.75, "urgency": "HIGH",
                    "emotion": "恐慌", "auction_dir": auction_dir,
                    "tags": ["竞价恐慌", "低吸"],
                }

        # ---- 竞价强势 + 回调支撑确认 ----
        if auction_dir == AUCTION_BULLISH and auction_pct and auction_pct > 1.5:
            if gap_conf == OPEN_GAP_UP_VALID:
                shares = max_amt // price
                return {
                    "type": "BUY", "code": code, "name": name,
                    "action": "缺口支撑买入",
                    "price": price, "trigger_price": trigger_price,
                    "shares": shares, "amount": shares * price,
                    "reason": f"竞价强势({auction_pct:.1f}%)+缺口有效，支撑买入",
                    "confidence": 0.80, "urgency": "MEDIUM",
                    "emotion": "回暖", "auction_dir": auction_dir,
                    "tags": ["竞价强势", "缺口有效"],
                }
            elif gap_conf == OPEN_GAP_UP_FAILED:
                return None  # 高开失败，不买

        # ---- 竞价平稳 + 价格触发 + 情绪回暖 ----
        if auction_dir == AUCTION_FLAT:
            if current_pct > -1.0 and current_pct < 2.0:
                shares = max_amt // price
                return {
                    "type": "BUY", "code": code, "name": name,
                    "action": "平稳回调买入",
                    "price": price, "trigger_price": trigger_price,
                    "shares": shares, "amount": shares * price,
                    "reason": f"竞价平稳，价格触 发{trigger_mode}={trigger_val}，平稳买入",
                    "confidence": 0.60, "urgency": "MEDIUM",
                    "emotion": "回暖", "auction_dir": auction_dir,
                    "tags": ["竞价平稳", "回调买入"],
                }

        # ---- 竞价强势追入（auction_strong 模式）----
        # 条件：trigger_mode=auction_strong + 竞价强势+2% + 缺口守住开盘价
        # 目的：不踏空，等回踩开盘价确认后立即买
        if trigger_mode == "auction_strong":
            if auction_dir == AUCTION_BULLISH and auction_pct and auction_pct >= trigger_val:
                if gap_conf == OPEN_GAP_UP_VALID:
                    # 竞价强势 + 缺口守住开盘价 → 直接买
                    shares = max_amt // price
                    return {
                        "type": "BUY", "code": code, "name": name,
                        "action": "竞价追入",
                        "price": price, "trigger_price": trigger_price,
                        "shares": shares, "amount": shares * price,
                        "reason": f"竞价强势({auction_pct:.1f}%)+缺口有效，不踏空直接买",
                        "confidence": 0.75, "urgency": "HIGH",
                        "emotion": "回暖", "auction_dir": auction_dir,
                        "tags": ["竞价强势", "追入"],
                    }
                elif gap_conf == "待确认":
                    # 竞价强势+缺口未确认，等9:35确认
                    return {
                        "type": "BUY", "code": code, "name": name,
                        "action": "等待确认(竞价强势)",
                        "price": price, "trigger_price": trigger_price,
                        "shares": 0, "amount": 0,
                        "reason": f"竞价强势({auction_pct:.1f}%)，等待9:35缺口确认",
                        "confidence": 0.0, "urgency": "LOW",
                        "emotion": "回暖", "auction_dir": auction_dir,
                        "tags": ["竞价强势", "等确认"],
                    }
                elif gap_conf == OPEN_GAP_UP_FAILED:
                    return None  # 高开失败，不买

        return None

    def _calc_trigger(self, mode: str, val: Any, close_prev: float, price: float) -> Tuple[bool, float]:
        if mode == "pct_vs_close":
            tp = close_prev * (1 + val / 100)
            triggered = (val < 0 and price <= tp) or (val > 0 and price >= tp)
            return triggered, tp
        elif mode == "fixed_price":
            triggered = abs(price - val) / val < 0.005
            return triggered, val
        elif mode == "range_price":
            if isinstance(val, (list, tuple)) and len(val) == 2:
                lo, hi = val
                return lo <= price <= hi, price
        elif mode == "auction_strong":
            # 竞价强势模式：价格触发本身不重要，看竞价方向
            # 只要有价格就开始监控，实际触发在 eval_buy 里的竞价逻辑
            return True, price
        return False, price

    def _eval_holding_recommendation(self, holding: Dict, quote: Dict,
                                     auction_info: Dict, gap_info: Dict) -> Optional[Dict]:
        """基于持仓成本、竞价情况和缺口确认，给出持仓建议。"""
        code = holding.get("code", "")
        name = holding.get("name", code)
        cost = holding.get("cost", 0)
        shares = holding.get("shares", 0)
        if cost <= 0 or shares <= 0:
            return None

        price = quote.get("price", 0)
        if price <= 0:
            return None

        gain_vs_cost = (price - cost) / cost * 100 if cost > 0 else 0
        auction_dir = auction_info.get("auction_direction", "待定")
        auction_pct = auction_info.get("auction_pct") or 0
        gap_conf = gap_info.get("confirmed_direction", "待确认")

        recommendation = {
            "code": code,
            "name": name,
            "price": price,
            "cost": cost,
            "gain_vs_cost": gain_vs_cost,
            "auction_direction": auction_dir,
            "auction_pct": auction_pct,
            "gap_confirmed": gap_conf,
        }

        if auction_dir == AUCTION_WEAK and auction_pct < -2 and gain_vs_cost <= 1.0:
            recommendation.update({
                "action": "考虑卖出/减仓",
                "reason": f"竞价弱势({auction_pct:.1f}%)且收益不高({gain_vs_cost:+.1f}%)，建议减仓观望",
                "urgency": "HIGH",
            })
            return recommendation

        if gain_vs_cost > 8 and price < quote.get("high", price) * 0.98:
            recommendation.update({
                "action": "考虑部分获利了结",
                "reason": f"已盈利{gain_vs_cost:+.1f}%，且出现回落，可考虑分批卖出",
                "urgency": "MEDIUM",
            })
            return recommendation

        if auction_dir == AUCTION_BULLISH and auction_pct >= 2:
            if gap_conf == OPEN_GAP_UP_VALID:
                recommendation.update({
                    "action": "考虑加仓",
                    "reason": f"竞价强势({auction_pct:.1f}%)且缺口有效，可在回踩后适当加仓",
                    "urgency": "MEDIUM",
                })
            else:
                recommendation.update({
                    "action": "继续持有",
                    "reason": f"竞价强势({auction_pct:.1f}%)，但缺口尚未确认，继续观察",
                    "urgency": "LOW",
                })
            return recommendation

        if auction_dir == AUCTION_WEAK and auction_pct < -2:
            recommendation.update({
                "action": "观望不加仓",
                "reason": f"竞价弱势({auction_pct:.1f}%)，暂时不加仓，等待确认",
                "urgency": "LOW",
            })
            return recommendation

        recommendation.update({
            "action": "继续持有",
            "reason": f"当前竞价{auction_dir}({auction_pct:+.1f}%)，维持观察即可",
            "urgency": "LOW",
        })
        return recommendation

    def _print_holding_recommendations(self, recs: List[Dict]):
        if not recs:
            return
        print(f"\n{Fore.MAGENTA}📌 持仓建议{Style.RESET_ALL}")
        for rec in recs:
            print(
                f"{Fore.MAGENTA}{rec['name']}({rec['code']}) "
                f"现价{rec['price']:.2f} 成本{rec['cost']:.2f} "
                f"收益{rec['gain_vs_cost']:+.1f}% "
                f"| 建议:{rec['action']} "
                f"| {rec['reason']}{Style.RESET_ALL}"
            )

    # ---------- 监控循环 ----------

    def run(self, interval=15, duration_min=300, feishu=False, once=False):
        self.feishu_enabled = feishu

        all_codes = list(set(
            self.watch_mgr.get_codes() +
            [h.get("code","") for h in self.holdings_mgr.get_all()]
        ))
        all_codes = [c for c in all_codes if c]

        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"📡 早盘情绪交易监控 v2 【专业竞价版】")
        print(f"   标的数量: {len(all_codes)}支")
        print(f"   买入标的: {len(self.watch_mgr.get_all())}支")
        print(f"   持仓标的: {len(self.holdings_mgr.get_all())}支")
        print("   卖出: 冲高卖+分档止盈 | 不止损")
        print(f"{'='*60}{Style.RESET_ALL}\n")

        if not all_codes:
            print(f"{Fore.RED}❌ 无监控标的{Style.RESET_ALL}")
            return

        quotes = self.quote_adapter.get_batch(all_codes)
        self._print_overview(quotes)
        sigs = self.eval(quotes)
        self._print_signals(sigs)
        self._print_holding_recommendations(sigs.get("holding_recommendations", []))

        if once and self.feishu_enabled:
            actionable = self._filter_actionable_signals(sigs)
            if actionable["buy"] or actionable["sell"]:
                push_signals(actionable, self._get_phase())

        phase = self._get_phase()
        if once:
            if self.feishu_enabled and datetime.now().time() >= T_AUCTION_END:
                if not self._auction_brief_sent:
                    self._auction_brief_sent = True
                    self._send_auction_brief(quotes)
            return

        start = time.time()
        end   = start + duration_min * 60
        while time.time() < end:
            now = datetime.now()
            phase = self._get_phase()
            t = now.time()

            # 非交易时段睡眠
            if not (dtime(9,5) <= t <= dtime(15,10)):
                time.sleep(interval)
                continue

            quotes = self.quote_adapter.get_batch(all_codes)
            if not quotes:
                print(f"{Fore.YELLOW}[{now.strftime('%H:%M:%S')}] 行情获取失败...{Style.RESET_ALL}")
                time.sleep(interval)
                continue

            sigs = self.eval(quotes)
            self._print_status(now, phase, quotes, sigs)
            if sigs.get("buy") or sigs.get("sell"):
                self._print_signals(sigs)
                if self.feishu_enabled:
                    actionable = self._filter_actionable_signals(sigs)
                    if actionable["buy"] or actionable["sell"]:
                        push_signals(actionable, phase)
            if sigs.get("holding_recommendations"):
                self._print_holding_recommendations(sigs["holding_recommendations"])

            # ---- 9:25 竞价结束 → 发简报（所有标的第一次确认后只发一次）----
            if t >= T_AUCTION_END and self.feishu_enabled:
                if not self._auction_brief_sent:
                    self._auction_brief_sent = True
                    self._send_auction_brief(quotes)

            time.sleep(interval)

    def _can_push_sell_signal(self, sig: Dict, now: float) -> bool:
        if sig.get("type") != "SELL":
            return True
        sig_type = sig.get("signal_type", "")
        code = sig.get("code", "")
        if not code:
            return True

        if sig_type == "spike_fade":
            cooldown = 3600
        elif sig_type == "profit_take":
            cooldown = 900
        elif sig_type == "weak_rebound_sell":
            cooldown = 1800
        else:
            cooldown = 300

        key = (code, sig_type)
        last = self.sell_push_record.get(key, 0)
        if now - last < cooldown:
            return False
        self.sell_push_record[key] = now
        return True

    def _filter_actionable_signals(self, sigs: Dict) -> Dict[str, List[Dict]]:
        now = time.time()
        actionable = {"buy": [], "sell": []}
        actionable["buy"] = [s for s in sigs.get("buy", []) if s.get("shares", 0) > 0]
        for s in sigs.get("sell", []):
            if s.get("shares", 0) <= 0:
                continue
            if self._can_push_sell_signal(s, now):
                actionable["sell"].append(s)
        return actionable

    def _send_auction_brief(self, quotes: Dict):
        """竞价结束时发送全量标的状态简报"""
        lines = []
        for code, q in quotes.items():
            name    = q.get("name", code)
            price   = q.get("price", 0)
            cp      = q.get("close_prev", 0)
            cur_pct = q.get("up_down_pct", 0)
            auction_t, gap_t = self._get_tracker(code)
            a_info  = auction_t.get_auction_info(cp)
            g_info  = gap_t.get_gap_info()

            a_dir  = a_info.get("auction_direction", "待定")
            a_pct  = a_info.get("auction_pct")
            open_p = g_info.get("open_pct", 0)
            gap_c  = g_info.get("confirmed_direction", "待确认")

            emoji_dir = {"强势": "🟢", "弱势": "🔴", "平稳": "🟡", "待定": "⚪"}.get(a_dir, "⚪")
            a_str = f"{a_pct:+.1f}%" if a_pct is not None else "--"
            o_str = f"{open_p:+.1f}%" if open_p else "--"
            lines.append(
                f"{emoji_dir} **{name}({code})**\n"
                f"   现价:{price:.2f} {cur_pct:+.1f}% | 竞价{a_dir}{a_str} | 开盘{o_str} | {gap_c}"
            )

        holding_lines = []
        holding_recs = []
        for h in self.holdings_mgr.get_all():
            hc  = h.get("code", "")
            q   = quotes.get(hc, {})
            if not q:
                continue
            cost   = h.get("cost", 0)
            price  = q.get("price", 0)
            gain   = (price - cost) / cost * 100 if cost > 0 else 0
            holding_lines.append(
                f"   {h.get('name', hc)}({hc}) {gain:+.1f}%"
            )
            auction_t, gap_t = self._get_tracker(hc)
            auction_info = auction_t.get_auction_info(q.get("close_prev", 0))
            gap_info = gap_t.get_gap_info()
            rec = self._eval_holding_recommendation(h, q, auction_info, gap_info)
            if rec:
                holding_recs.append(
                    f"   {rec['name']}({rec['code']}) {rec['action']} | {rec['reason']}"
                )

        card = {
            "config": {"wide_screen_mode": True},
            "elements": [{
                "tag": "markdown",
                "content": (
                    f"**📊 竞价简报 · 9:25**\n\n"
                    + "\n".join(lines)
                    + (f"\n\n**📦 持仓状态**\n" + "\n".join(holding_lines) if holding_lines else "")
                    + (f"\n\n**📌 持仓建议**\n" + "\n".join(holding_recs) if holding_recs else "")
                    + f"\n\n---\n*生成时间: {datetime.now().strftime('%H:%M:%S')}*"
                )
            }]
        }
        from simple_feishu import _send_card
        _send_card(card)

    def _print_overview(self, quotes: Dict):
        """打印标的全景"""
        print(f"{Fore.CYAN}{'─'*70}")
        print(f"{'代码':<8}{'名称':<10}{'昨收':>7}{'现价':>7}{'现涨%':>7}"
              f"{'竞价方向':^10}{'竞价%':>7}{'开盘%':>7}{'缺口确认':^12}")
        print(f"{'─'*70}")
        for code, q in quotes.items():
            auction_t, gap_t = self._get_tracker(code)
            cp     = q.get("close_prev", 0)
            price  = q.get("price", 0)
            cur_pct = q.get("up_down_pct", 0)
            a_info = auction_t.get_auction_info(cp)
            g_info = gap_t.get_gap_info()
            a_dir  = a_info.get("auction_direction","待定")
            a_pct  = a_info.get("auction_pct")
            o_pct  = g_info.get("open_pct", 0)
            gap_c  = g_info.get("confirmed_direction","待确认")

            a_color = (Fore.GREEN if "强" in a_dir else
                       Fore.RED   if "弱" in a_dir else Fore.WHITE)
            gap_color = (Fore.GREEN if "有效" in gap_c or "见底" in gap_c else
                         Fore.RED   if "失败" in gap_c or "下杀" in gap_c else Fore.YELLOW)

            auction_pct_str = (f"{a_pct:>+7.1f}%" if a_pct is not None else f"{'--':>7}")
            print(
                f"{code:<8}{q.get('name',''):<10}"
                f"{cp:>7.2f}{price:>7.2f}{cur_pct:>+7.1f}%"
                f"{a_color}{a_dir:^10}{Style.RESET_ALL}"
                f"{auction_pct_str}"
                f"{o_pct:>+7.1f}%"
                f"{gap_color}{gap_c:^12}{Style.RESET_ALL}"
            )
        print(f"{Fore.CYAN}{'─'*70}{Style.RESET_ALL}")

    def _print_signals(self, sigs: Dict):
        for s in sigs.get("buy", []):
            conf_bar = "█" * int(s.get("confidence", 0) * 10)
            print(
                f"\n{ Fore.GREEN }📥 买入信号 "
                f"{s['name']}({s['code']}) "
                f"{s.get('action','')} "
                f"@{s.get('price',0):.2f} "
                f"{s.get('shares',0)}股 "
                f"[{s.get('reason','')}] "
                f"置信:{conf_bar}{s.get('confidence',0)*100:.0f}% "
                f"{''.join(s.get('tags',[]))}{Style.RESET_ALL}"
            )
        for s in sigs.get("sell", []):
            urgency = "🔴" if s.get("urgency") == "HIGH" else "🟡"
            print(
                f"\n{ Fore.RED }{urgency} 卖出信号 "
                f"{s['name']}({s['code']}) "
                f"{s.get('action','')} "
                f"@{s.get('price',0):.2f} "
                f"{s.get('shares',0)}股 "
                f"成本:{s.get('gain_vs_cost',0):+.1f}% "
                f"[{s.get('reason','')}]{Style.RESET_ALL}"
            )

    def _print_status(self, now: datetime, phase: str, quotes: Dict, sigs: Dict):
        emoji = {
            "盘前":"🌙","竞价(可撤)":"🔔","竞价(有效)":"🔔",
            "等待开盘":"⏰","缺口确认":"🚀","趋势确认":"📈",
            "午盘":"☀️","下午":"🌤️","收盘":"📊",
        }.get(phase,"⏳")
        cnt = len(sigs.get("buy",[])) + len(sigs.get("sell",[]))
        sig_str = f"{Fore.RED}{cnt}个信号!{Style.RESET_ALL}" if cnt else "无信号"
        print(
            f"{Fore.CYAN}[{now.strftime('%H:%M:%S')}]{Style.RESET_ALL} "
            f"{emoji} {phase:<10} {sig_str} | 监控:{len(quotes)}支"
        )


# ==================== CLI ====================

def main():
    import argparse
    p = argparse.ArgumentParser(description="早盘情绪交易监控 v2")
    p.add_argument("--holdings",   default=str(HOLDINGS_PATH))
    p.add_argument("--buy-watch",   default=None)
    p.add_argument("--interval",    type=int, default=15)
    p.add_argument("--duration",    type=int, default=300)
    p.add_argument("--once",         action="store_true")
    p.add_argument("--feishu",       action="store_true")
    args = p.parse_args()

    m = MorningEmotionMonitor(
        holdings_path=args.holdings,
        buy_watch_path=args.buy_watch,
    )
    m.run(interval=args.interval, duration_min=args.duration, feishu=args.feishu, once=args.once)

if __name__ == "__main__":
    main()
