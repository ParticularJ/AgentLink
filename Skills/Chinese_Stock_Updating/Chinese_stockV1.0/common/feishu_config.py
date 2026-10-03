#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书凭据统一加载 —— 源码里不再出现明文 App Secret。

模块名刻意不叫 secrets：那会遮蔽 Python 标准库的 secrets 模块，
进而影响 uuid / random / tempfile 等标准库调用。

查找顺序（先命中先用）
----------------------
1. 环境变量：FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_GROUP_ID / FEISHU_GROUP_ID_ALT
2. common/secrets.yaml（真实配置，已被 .gitignore 忽略）
3. common/secrets.example.yaml（占位模板，不含真实凭据）

用法
----
    from feishu_config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_GROUP_ID
    # 或需要严格校验时：
    from feishu_config import require_feishu; require_feishu()
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

try:
    import yaml
except ImportError:  # pragma: no cover - 允许在没有 pyyaml 的环境里仅靠环境变量运行
    yaml = None  # type: ignore[assignment]

_HERE = Path(__file__).resolve().parent

_CANDIDATES: List[Path] = []
_override = os.environ.get("FEISHU_SECRETS_FILE")
if _override:
    _CANDIDATES.append(Path(_override).expanduser())
_CANDIDATES += [_HERE / "secrets.yaml", _HERE / "secrets.example.yaml"]


def _parse_flat_yaml(text: str) -> Dict[str, str]:
    """无 pyyaml 时的兜底解析：只支持 secrets.yaml 用到的 "key: value" 扁平格式。"""
    data: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip("\"").strip("'")
        if key.strip():
            data[key.strip()] = value
    return data


def _load_file() -> Dict[str, str]:
    """读取第一个可解析的配置文件；没有 pyyaml 时用内置的扁平解析兜底。"""
    for path in _CANDIDATES:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        data = None
        if yaml is not None:
            try:
                data = yaml.safe_load(text)
            except Exception:
                data = None
        if not isinstance(data, dict):
            data = _parse_flat_yaml(text)
        if isinstance(data, dict) and data:
            return {str(k): str(v) for k, v in data.items() if v is not None}
    return {}


_FILE = _load_file()


def _get(env_key: str, yaml_key: str, default: str = "") -> str:
    value = os.environ.get(env_key)
    if value:
        return value.strip()
    value = _FILE.get(yaml_key)
    if value:
        return value.strip()
    return default


FEISHU_APP_ID: str = _get("FEISHU_APP_ID", "app_id")
FEISHU_APP_SECRET: str = _get("FEISHU_APP_SECRET", "app_secret")
FEISHU_GROUP_ID: str = _get("FEISHU_GROUP_ID", "group_id")
# 备用推送群（send_feishu.py 使用），未配置时回落到主群
FEISHU_GROUP_ID_ALT: str = _get("FEISHU_GROUP_ID_ALT", "group_id_alt") or FEISHU_GROUP_ID


def missing() -> List[str]:
    """返回缺失的必填项名称列表。"""
    required = (
        ("FEISHU_APP_ID", FEISHU_APP_ID),
        ("FEISHU_APP_SECRET", FEISHU_APP_SECRET),
        ("FEISHU_GROUP_ID", FEISHU_GROUP_ID),
    )
    return [name for name, value in required if not value]


def require_feishu() -> None:
    """缺失凭据时抛出带指引的异常，避免出现 401 这种难排查的报错。"""
    absent = missing()
    if absent:
        raise RuntimeError(
            "缺少飞书凭据: " + ", ".join(absent)
            + "；请设置同名环境变量，或创建 common/secrets.yaml"
            + "（模板见 common/secrets.example.yaml）"
        )
