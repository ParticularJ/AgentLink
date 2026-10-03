#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书开放平台推送的统一实现。

原来 3 个脚本各自写了一遍 get_tenant_token / send_card / send_card_with_retry：
  - strategy-fusion-advisor/skills/scripts/send_feishu.py        （无重试）
  - strategy-fusion-advisor/skills/scripts/send_feishu_card.py   （有重试）
  - strategy-fusion-advisor/skills/scripts/news_watchlist_scanner.py（重复一遍）

凭据统一来自 common/feishu_config.py（环境变量 > secrets.yaml），
日志通过可选的 logger 回调注入，避免本模块反向依赖具体脚本。
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Optional

try:
    from feishu_config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_GROUP_ID
except ImportError:
    from .feishu_config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_GROUP_ID

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
MSG_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

Logger = Optional[Callable[[str], None]]


def _emit(logger: Logger, msg: str) -> None:
    (logger or print)(msg)


def _requests():
    """延迟导入 requests，让纯逻辑测试无需安装网络依赖。"""
    try:
        import requests  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("飞书推送需要 requests，请先 pip install requests") from e
    return requests


def get_tenant_token(app_id: Optional[str] = None,
                     app_secret: Optional[str] = None,
                     logger: Logger = None) -> str:
    """获取 tenant_access_token（单次尝试）。"""
    requests = _requests()
    resp = requests.post(
        TOKEN_URL,
        json={"app_id": app_id or FEISHU_APP_ID, "app_secret": app_secret or FEISHU_APP_SECRET},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json().get("tenant_access_token", "")
    if not token:
        raise RuntimeError(f"获取 tenant_access_token 失败: {resp.text}")
    return token


def get_tenant_token_with_retry(max_retries: int = 3,
                                retry_interval: int = 5,
                                logger: Logger = None) -> str:
    """带重试的 token 获取；全部失败时抛最后一个异常。"""
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            token = get_tenant_token(logger=logger)
            if attempt > 1:
                _emit(logger, f"获取token重试第{attempt}次成功")
            return token
        except Exception as e:  # noqa: BLE001 - 网络异常种类多，统一重试
            last_error = e
            _emit(logger, f"获取token异常 (第{attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(retry_interval)
    raise RuntimeError(f"获取token全部重试失败: {last_error}")


def send_card(card: Dict[str, Any],
              receive_id: Optional[str] = None,
              logger: Logger = None) -> Dict[str, Any]:
    """发送 interactive card（单次尝试）。"""
    requests = _requests()
    resp = requests.post(
        MSG_URL,
        params={"receive_id_type": "chat_id"},
        headers={"Content-Type": "application/json"},
        json={
            "receive_id": receive_id or FEISHU_GROUP_ID,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def send_text(text: str,
              receive_id: Optional[str] = None,
              logger: Logger = None) -> Dict[str, Any]:
    """发送纯文本消息（单次尝试）。"""
    requests = _requests()
    token = get_tenant_token(logger=logger)
    resp = requests.post(
        MSG_URL,
        params={"receive_id_type": "chat_id"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "receive_id": receive_id or FEISHU_GROUP_ID,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def send_card_with_token(token: str,
                        card: Dict[str, Any],
                        receive_id: Optional[str] = None,
                        logger: Logger = None) -> Dict[str, Any]:
    """用已获取的 token 发送卡片（调用方已有 token 时使用）。"""
    requests = _requests()
    resp = requests.post(
        MSG_URL,
        params={"receive_id_type": "chat_id"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "receive_id": receive_id or FEISHU_GROUP_ID,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def send_text_with_token(token: str,
                         text: str,
                         receive_id: Optional[str] = None,
                         logger: Logger = None) -> Dict[str, Any]:
    """用已获取的 token 发送纯文本。"""
    requests = _requests()
    resp = requests.post(
        MSG_URL,
        params={"receive_id_type": "chat_id"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "receive_id": receive_id or FEISHU_GROUP_ID,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def send_card_with_retry(token: str,
                         card: Dict[str, Any],
                         receive_id: Optional[str] = None,
                         max_retries: int = 3,
                         retry_interval: int = 5,
                         logger: Logger = None) -> Dict[str, Any]:
    """带重试地发送卡片；返回最后一次响应，全部失败时抛异常。"""
    requests = _requests()
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                MSG_URL,
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "receive_id": receive_id or FEISHU_GROUP_ID,
                    "msg_type": "interactive",
                    "content": json.dumps(card, ensure_ascii=False),
                },
                timeout=15,
            )
            data = resp.json()
            if data.get("code") == 0:
                if attempt > 1:
                    _emit(logger, f"发送卡片重试第{attempt}次成功")
                return data
            last_error = RuntimeError(f"code={data.get('code')} msg={data.get('msg')}")
            _emit(logger, f"发送卡片失败 (第{attempt}/{max_retries}): {last_error}")
        except Exception as e:  # noqa: BLE001
            last_error = e
            _emit(logger, f"发送卡片异常 (第{attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            time.sleep(retry_interval)
    raise RuntimeError(f"发送卡片全部重试失败: {last_error}")
