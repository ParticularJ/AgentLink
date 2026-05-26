from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Iterator
from dotenv import load_dotenv
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)


# # 1. 初始化本地vLLM（你的Qwen3-VL服务）
# llm_client = OpenAI(
#     base_url="https://api.minimaxi.com/v1/chat/completions",
#     api_key="sk-cp-Q4vO3oqDg_YBCtLc3PU_dnQmqMsBGfEW9xgoWEz_hrLGG5rPwB2tWrgqEQS8dBXX3jgym2t8gvpuAMWHaBeZtKxhpz6Yz1y_W3SMfiR4bvJSRlf0KlRtxnM"
# )
# MODEL_NAME = "MiniMax-M2.7"


@dataclass(frozen=True)
class LLMClientConfig:
    # Example: "https://api.openai.com/v1" or "http://localhost:8000/v1"
    api_base: str
    api_key: str
    model: str
    chat_completions_path: str = "/chat/completions"
    timeout_s: int = 300


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def load_client_config(
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMClientConfig:
    # Base URL must be the OpenAI-compatible root (…/v1), not …/v1/chat/completions.
    base = (
        api_base
        or _env("OPENAI_BASE_URL")
        or _env("LLM_API_BASE")
        or "https://api.minimaxi.com/v1"
    ).rstrip("/")
    key = (
        api_key
        or _env("OPENAI_API_KEY")
        or _env("MINIMAX_API_KEY")
        or "sk-cp-Q4vO3oqDg_YBCtLc3PU_dnQmqMsBGfEW9xgoWEz_hrLGG5rPwB2tWrgqEQS8dBXX3jgym2t8gvpuAMWHaBeZtKxhpz6Yz1y_W3SMfiR4bvJSRlf0KlRtxnM"
    )
    mdl = model or _env("LLM_MODEL") or "MiniMax-M2.7"
    return LLMClientConfig(
        api_base=base,
        api_key=key,
        model=mdl,
        chat_completions_path=_env("MODEL_CHAT_COMPLETIONS_PATH", "/chat/completions"),
        timeout_s=int(_env("MODEL_TIMEOUT_S", "30")),
    )


def _build_url(cfg: LLMClientConfig) -> str:
    base = cfg.api_base.rstrip("/")
    path = cfg.chat_completions_path
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout_s: int) -> dict[str, Any]:
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"LLM HTTPError {exc.code}: {raw[:2000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM URLError: {exc}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned non-JSON response: {raw[:2000]}") from exc


_REDACTED_THINKING_END = "</think>"


def _strip_redacted_thinking_block(content: str) -> str:
    """MiniMax-M2 may prefix assistant text with <think>...</think>."""
    if _REDACTED_THINKING_END in content:
        content = content.split(_REDACTED_THINKING_END, 1)[-1]
    return content.strip()


def _find_matching_brace(s: str, open_idx: int) -> int | None:
    """Index of `}` that closes `{` at open_idx, respecting JSON string escapes."""
    depth = 0
    in_string = False
    escape = False
    for i in range(open_idx, len(s)):
        ch = s[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _first_parseable_json_object(text: str) -> str | None:
    start = 0
    while True:
        i = text.find("{", start)
        if i < 0:
            return None
        end = _find_matching_brace(text, i)
        if end is not None:
            chunk = text[i : end + 1]
            try:
                json.loads(chunk)
                return chunk
            except json.JSONDecodeError:
                pass
        start = i + 1


def _normalize_assistant_content(raw: str) -> str:
    """
    Return plain assistant-visible text: drop MiniMax thinking wrapper if present;
    if the remainder is (or contains) a single JSON object, return that JSON string only.
    """
    text = _strip_redacted_thinking_block(raw)
    if not text:
        return text
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    extracted = _first_parseable_json_object(text)
    if extracted is not None:
        return extracted
    return text


def _extract_chat_content(data: dict[str, Any]) -> str:
    # OpenAI-compatible response shape:
    # { "choices": [ { "message": { "content": "..." } } ] }
    choices = data.get("choices") or []
    if not choices:
        # Fallback for other servers
        for k in ("output_text", "text", "content"):
            if k in data and isinstance(data[k], str):
                return _normalize_assistant_content(data[k])
        raise RuntimeError(f"LLM response has no choices: keys={list(data.keys())}")

    first = choices[0]
    if "message" in first and isinstance(first["message"], dict):
        content = first["message"].get("content")
        if isinstance(content, str):
            return _normalize_assistant_content(content)
    # Some servers may return { "choices": [ {"text": "..."} ] }
    content = first.get("text")
    if isinstance(content, str):
        return _normalize_assistant_content(content)

    raise RuntimeError("LLM response missing expected content fields")


def build_chat_messages(prompt: str, system_prompt: str | None = None) -> list[dict[str, str]]:
    if system_prompt:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
    return [{"role": "user", "content": prompt}]


def generate_text(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    timeout_s: int | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> str:
    """
    OpenAI-compatible: POST {api_base}/chat/completions.

    Returns: assistant message text content.
    """
    cfg = load_client_config(api_base=api_base, api_key=api_key, model=model)
    timeout_s = timeout_s or cfg.timeout_s
    url = _build_url(cfg)

    messages = build_chat_messages(prompt, system_prompt=system_prompt)
    # print("messages: ", messages)
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)

    headers = {
        "Content-Type": "application/json",
    }
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    data = _post_json(url, payload, headers=headers, timeout_s=timeout_s)
    #print("data : ", data )
    return _extract_chat_content(data)


def _iter_sse_data_lines(resp: Any) -> Iterator[str]:
    """
    Very small SSE parser:
    - reads lines
    - yields decoded strings after 'data: ' prefix
    - stops on '[DONE]' (OpenAI convention)
    """
    for raw_line in resp:
        if not raw_line:
            continue
        try:
            line = raw_line.decode("utf-8", errors="replace").strip()
        except Exception:
            continue
        if not line:
            continue
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if not data:
            continue
        yield data


def stream_text(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    timeout_s: int | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> Iterable[str]:
    """
    Streams assistant deltas (text chunks).

    Yields: small text segments to append.
    """
    cfg = load_client_config(api_base=api_base, api_key=api_key, model=model)
    timeout_s = timeout_s or cfg.timeout_s
    url = _build_url(cfg)

    messages = build_chat_messages(prompt, system_prompt=system_prompt)
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)

    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            for data_str in _iter_sse_data_lines(resp):
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                chunk = delta.get("content")
                if isinstance(chunk, str) and chunk:
                    yield chunk
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"LLM stream HTTPError {exc.code}: {raw[:2000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM stream URLError: {exc}") from exc


__all__ = [
    "LLMClientConfig",
    "load_client_config",
    "build_chat_messages",
    "generate_text",
    "stream_text",
]

