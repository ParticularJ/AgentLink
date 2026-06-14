"""
消息推送模块
支持：飞书、钉钉、企业微信、Server酱
"""

import os
import json
import urllib.request
import urllib.error
from typing import Optional

try:
    from config import WEBHOOK_CONFIG, FEISHU_WEBHOOK
except ImportError:
    WEBHOOK_CONFIG = {
        "dingtalk": os.getenv("DINGTALK_WEBHOOK", ""),
        "wecom": os.getenv("WECOM_WEBHOOK", ""),
        "serverchan": os.getenv("SERVERCHAN_KEY", "")
    }
    FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")

# 延迟导入避免循环依赖
try:
    from models import PositionAdvice
except ImportError:
    PositionAdvice = None


class AlertSender:
    """预警消息发送器"""

    def __init__(self):
        self.dingtalk_webhook = WEBHOOK_CONFIG.get("dingtalk", "")
        self.wecom_webhook = WEBHOOK_CONFIG.get("wecom", "")
        self.serverchan_key = WEBHOOK_CONFIG.get("serverchan", "")
        self.feishu_webhook = FEISHU_WEBHOOK

    # ── 格式化方法 ────────────────────────────────────────

    def format_alert_message(self, alert) -> str:
        """格式化预警消息"""
        risk_emoji = {
            "LOW": "🟡",
            "MEDIUM": "🟠",
            "HIGH": "🔴",
            "CONFIRM": "✅"
        }
        # 处理 alert.risk_level 可能是字符串或枚举
        risk_level = alert.risk_level
        if hasattr(risk_level, 'value'):
            risk_level = risk_level.value
        
        emoji = risk_emoji.get(risk_level, "⚪")
        
        message = (
            f"{emoji} **风控预警**\n\n"
            f"📌 {alert.name}({alert.code})\n"
            f"⚠️ {alert.message}\n"
            f"💰 当前价: {alert.current_price:.2f} | 均线: {alert.ma_value:.2f}\n"
            f"🔧 建议: {alert.action}\n"
            f"🕐 {alert.timestamp.strftime('%H:%M:%S')}"
        )
        return message

    def format_position_message(self, advice, current_position: float = 0,
                                position_value: float = 0, total_asset: float = 0,
                                floating_pnl: float = 0) -> str:
        """格式化仓位建议消息（支持完整参数）"""
        # 处理大盘状态
        market_state = advice.market_state
        if hasattr(market_state, 'value'):
            market_state = market_state.value
        
        state_emoji = {
            "强势主升": "🚀",
            "震荡偏多": "📈",
            "弱势震荡": "📊",
            "下跌趋势": "📉",
            "系统性风险": "🚨"
        }
        emoji = state_emoji.get(market_state, "📊")

        message = (
            f"{emoji} **仓位建议**\n\n"
            f"📊 大盘状态: {market_state}\n"
            f"🎯 建议仓位: {advice.suggested_position*100:.0f}%\n"
            f"💵 当前仓位: {current_position*100:.1f}%\n"
            f"➕ 可用加仓: {advice.available_position*100:.0f}%\n"
            f"💰 总资产: {total_asset:,.2f}\n"
            f"📊 持仓市值: {position_value:,.2f}\n"
            f"💹 浮动盈亏: {floating_pnl:+,.2f}\n"
            f"📝 {advice.reason}"
        )
        return message

    def format_position_message_simple(self, position_advice, current_position: float) -> str:
        """格式化仓位建议消息（简单版本，兼容旧调用）"""
        market_state = position_advice.market_state
        if hasattr(market_state, 'value'):
            market_state = market_state.value
        
        state_emoji = {
            "强势主升": "🚀",
            "震荡偏多": "📈",
            "弱势震荡": "📊",
            "下跌趋势": "📉",
            "系统性风险": "🚨"
        }
        emoji = state_emoji.get(market_state, "📊")

        return (
            f"{emoji} **仓位建议**\n\n"
            f"📊 大盘状态: {market_state}\n"
            f"🎯 建议仓位: {position_advice.suggested_position*100:.0f}%\n"
            f"💵 当前仓位: {current_position*100:.1f}%\n"
            f"➕ 可用加仓: {position_advice.available_position*100:.0f}%\n"
            f"📝 {position_advice.reason}"
        )

    def format_rebalance_message(self, rebalance_info: dict) -> str:
        """格式化调仓建议消息"""
        if not rebalance_info.get("need_rebalance"):
            return f"✅ 调仓信号：无\n{rebalance_info.get('action', '持有')}"

        sell = rebalance_info.get("sell_holding")
        return (
            f"🔄 **调仓建议**\n\n"
            f"📤 卖出: {sell.name}({sell.code}) 评分:{rebalance_info.get('sell_score', 0):.1f}\n"
            f"📥 买入: {rebalance_info.get('buy_code')} 评分:{rebalance_info.get('buy_score', 0):.1f}\n"
            f"📊 评分差: {rebalance_info.get('score_gap', 0):.1f}\n"
            f"🔧 操作: {rebalance_info.get('action', '调仓换股')}"
        )

    # ── 发送方法 ─────────────────────────────────────────

    def _send_feishu(self, msg: str, title: str = "") -> bool:
        """发送飞书消息"""
        if not self.feishu_webhook:
            return False
        try:
            payload = {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": title or "股票策略提醒",
                            "content": [
                                [{"tag": "text", "text": msg}]
                            ]
                        }
                    }
                }
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.feishu_webhook, data=data, 
                                        headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception:
            return False

    def _send_dingtalk(self, msg: str, title: str = "") -> bool:
        """发送钉钉消息"""
        if not self.dingtalk_webhook:
            return False
        try:
            url = self.dingtalk_webhook
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title or msg[:20],
                    "text": msg
                }
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception:
            return False

    def _send_wecom(self, msg: str) -> bool:
        """发送企业微信消息"""
        if not self.wecom_webhook:
            return False
        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {"content": msg}
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.wecom_webhook, data=data, 
                                        headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception:
            return False

    def _send_serverchan(self, msg: str, title: str = "") -> bool:
        """发送Server酱消息"""
        if not self.serverchan_key:
            return False
        try:
            url = f"https://sctapi.ftqq.com/{self.serverchan_key}.send"
            payload = {
                "title": title or "持仓监控预警",
                "desp": msg
            }
            data = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception:
            return False

    def send_custom_message(self, message: str, title: str = "") -> bool:
        """发送自定义消息到所有配置的渠道"""
        print(f"\n{'='*50}")
        print(f"【{title}】")
        print(message)
        print(f"{'='*50}\n")
        
        # 尝试各渠道推送
        success = False
        if self.feishu_webhook:
            if self._send_feishu(message, title):
                success = True
        if self.dingtalk_webhook:
            if self._send_dingtalk(message, title):
                success = True
        if self.wecom_webhook:
            if self._send_wecom(message):
                success = True
        if self.serverchan_key:
            if self._send_serverchan(message, title):
                success = True
        
        return success

    def send_alert(self, alert) -> bool:
        """发送预警消息"""
        message = self.format_alert_message(alert)
        title = f"风控预警-{alert.name}"
        return self.send_custom_message(message, title)

    def send_position_advice(self, advice, current_position: float = 0,
                            position_value: float = 0, total_asset: float = 0,
                            floating_pnl: float = 0) -> bool:
        """发送仓位建议"""
        # 使用完整版本的格式化方法
        message = self.format_position_message(advice, current_position, 
                                              position_value, total_asset, floating_pnl)
        return self.send_custom_message(message, "仓位管理建议")
    
    def send_position_advice_simple(self, position_advice, current_position: float) -> bool:
        """发送仓位建议（简化版，兼容旧代码）"""
        message = self.format_position_message_simple(position_advice, current_position)
        return self.send_custom_message(message, "仓位管理建议")

    def send_rebalance_advice(self, rebalance_info: dict) -> bool:
        """发送调仓建议"""
        message = self.format_rebalance_message(rebalance_info)
        title = "调仓建议" if rebalance_info.get("need_rebalance") else "持仓建议"
        return self.send_custom_message(message, title)


# 测试代码
if __name__ == "__main__":
    # 创建模拟数据用于测试
    from unittest.mock import Mock
    
    class MockAlert:
        def __init__(self):
            self.name = "贵州茅台"
            self.code = "600519"
            self.risk_level = "MEDIUM"
            self.message = "跌破10日线,波段趋势转弱"
            self.current_price = 1680.00
            self.ma_value = 1695.00
            self.action = "减仓1/3"
            self.timestamp = __import__('datetime').datetime.now()
    
    class MockAdvice:
        def __init__(self):
            self.market_state = Mock()
            self.market_state.value = "震荡偏多"
            self.suggested_position = 0.65
            self.available_position = 0.20
            self.reason = "大盘状态:震荡偏多"
    
    sender = AlertSender()
    
    # 测试预警消息
    alert = MockAlert()
    sender.send_alert(alert)
    
    # 测试仓位建议
    advice = MockAdvice()
    sender.send_position_advice(advice, 0.45, 450000, 1000000, 5000)
    
    print("\n消息推送模块测试完成")