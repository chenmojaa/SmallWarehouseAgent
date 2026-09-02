"""LLM factory - LangChain multi-provider with per-request overrides + retry/backoff.

`invoke_with_retry` wraps any LangChain chat model's `.invoke()` and `.stream()`
methods with exponential backoff on transient failures (rate limit, 5xx,
connection errors). Non-retryable errors (4xx except 429, parse errors) bubble
up immediately so the caller can decide.

Retry policy (per HD_LLM_MAX_RETRIES, default 3):
  attempt 1 -> 0.6s
  attempt 2 -> 1.2s
  attempt 3 -> 2.4s
  jitter: ±20% on each delay so concurrent retries don't synchronize.

Multiplied cap: 0.6 * (1 + jitter) ~= 0.5-0.7s, total worst-case ~5s.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from app.config import settings

OPENAI_COMPAT_BASE_URLS: dict[str, str] = {
  "deepseek":    "https://api.deepseek.com/v1",
  "zhipu":       "https://open.bigmodel.cn/api/paas/v4",
  "moonshot":    "https://api.moonshot.cn/v1",
  "siliconflow": "https://api.siliconflow.cn/v1",
  "ollama":      "http://localhost:11434/v1",
}

NATIVE_PROVIDERS: set[str] = {"anthropic", "openai"}
ALL_PROVIDERS = sorted(NATIVE_PROVIDERS | set(OPENAI_COMPAT_BASE_URLS.keys()))

# Providers that understand OpenAI-style reasoning_effort in extra_body.
# Anthropic uses a separate `thinking` field; DeepSeek accepts `reasoning_effort`.
_REASONING_EFFORT_PROVIDERS: set[str] = {"openai", "deepseek"}

# Anthropic extended-thinking budget per reasoning level.
_ANTHROPIC_THINK_BUDGET: dict[str, int] = {
  "low": 1024,
  "medium": 4096,
  "high": 8192,
  "xhigh": 16384,
}


def _resolve_base_url(provider: str, base_url: str | None) -> str | None:
  if base_url:
    return base_url
  if provider in OPENAI_COMPAT_BASE_URLS:
    return (settings.llm_api_base or "").strip() or OPENAI_COMPAT_BASE_URLS[provider]
  return None


def _resolve_api_key(api_key: str | None) -> str | None:
  return (api_key or settings.llm_api_key or "").strip() or None


def _build_model(provider=None, model=None, api_key=None, base_url=None, reasoning_level=None):
  p = (provider or settings.llm_provider).strip()
  m = (model or settings.llm_model).strip()
  key = _resolve_api_key(api_key)
  resolved_url = _resolve_base_url(p, base_url)

  extra: dict[str, Any] = {}
  if reasoning_level and p in _REASONING_EFFORT_PROVIDERS:
    extra["reasoning_effort"] = reasoning_level

  if p == "anthropic":
    anthropic_kwargs: dict[str, Any] = {"model": m, "max_tokens": 4096}
    if key:
      anthropic_kwargs["api_key"] = key
    if resolved_url:
      anthropic_kwargs["base_url"] = resolved_url
    if reasoning_level:
      budget = _ANTHROPIC_THINK_BUDGET.get(reasoning_level, _ANTHROPIC_THINK_BUDGET["medium"])
      anthropic_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
    return ChatAnthropic(**anthropic_kwargs)

  kwargs: dict[str, Any] = {"model": m}
  if key:
    kwargs["api_key"] = key
  if resolved_url:
    kwargs["base_url"] = resolved_url
  if extra:
    kwargs["extra_body"] = extra
  return ChatOpenAI(**kwargs)


def list_providers():
  return ALL_PROVIDERS


# --------------------------------------------------------------------------- #
# Retry wrapper
# --------------------------------------------------------------------------- #

# Errors we consider transient and worth retrying. Anything not in this set
# (ValueError, JSON parse, content filter, 4xx) bubbles up immediately so the
# caller can decide without burning latency.
_RETRYABLE_EXC_NAMES = {
  "RateLimitError",          # openai 429
  "APITimeoutError",
  "TimeoutError",
  "APIConnectionError",
  "ServiceUnavailableError", # 503
  "InternalServerError",     # 500
  "BadGatewayError",         # 502
  "GatewayTimeoutError",     # 504
  "APIError",                # generic 5xx base
  "ConnectionError",         # python builtin
}
_RETRYABLE_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
  """Inspect the exception to decide whether to retry."""
  cls_name = type(exc).__name__
  if cls_name in _RETRYABLE_EXC_NAMES:
    return True
  # Some LangChain wrappers stash HTTP status on the exception.
  status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
  if isinstance(status, int) and status in _RETRYABLE_STATUSES:
    return True
  # openai SDK 1.x attaches .response.status_code
  resp = getattr(exc, "response", None)
  if resp is not None and getattr(resp, "status_code", None) in _RETRYABLE_STATUSES:
    return True
  return False


def _backoff_delay(attempt: int) -> float:
  """Exponential backoff with ±20% jitter. attempt=1 is the first retry."""
  base = 0.6 * (2 ** (attempt - 1))
  jitter = base * 0.2 * (random.random() * 2 - 1)
  return max(0.0, base + jitter)


def invoke_with_retry(chat, payload, *, max_retries: int | None = None, on_retry=None):
  """Call `chat.invoke(payload)` with exponential backoff on transient errors.

  Args:
    chat: a LangChain BaseChatModel
    payload: string or list of messages
    max_retries: override default retry budget (HD_LLM_MAX_RETRIES, default 3)
    on_retry: optional callable(attempt: int, exc: Exception, delay: float)
              invoked right before each sleep so callers can log / emit events.

  Returns whatever `.invoke()` returns. Re-raises the final exception if every
  attempt fails or the exception is non-retryable.
  """
  retries = max_retries if max_retries is not None else max(0, int(getattr(settings, "llm_max_retries", 3)))
  last_exc: BaseException | None = None
  for attempt in range(0, retries + 1):
    try:
      return chat.invoke(payload)
    except Exception as e:
      last_exc = e
      if not _is_retryable(e) or attempt >= retries:
        raise
      delay = _backoff_delay(attempt + 1)
      if on_retry is not None:
        try: on_retry(attempt + 1, e, delay)
        except Exception: pass
      logging.getLogger(__name__).warning(
        "llm retry %d/%d after %.2fs: %s",
        attempt + 1, retries, delay, type(e).__name__,
      )
      time.sleep(delay)
  # Unreachable, but keep type-checkers happy.
  raise last_exc  # pragma: no cover