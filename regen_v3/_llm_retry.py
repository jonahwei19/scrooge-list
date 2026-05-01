"""Anthropic client retry helper for regen_v3 LLM calls.

The seed/hidden_upper/tier_reasoning modules each make a single LLM call per
subject. Without retries, a transient `RateLimitError` (HTTP 429 — frequent
when running 4 workers in parallel) or `InternalServerError` (HTTP 5xx)
fails the call and the worker returns an empty result for the subject,
producing a record with a missing tier_reasoning or hidden_upper section.

Pattern: exponential backoff with jitter, max 4 attempts. We re-raise the
final exception so callers can record it as `verification_error` per their
existing convention.
"""
from __future__ import annotations

import random
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# Default retry policy. Conservative: 4 attempts over ~30s tops.
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 16.0


def _is_retryable(exc: BaseException) -> bool:
    """Match anthropic.RateLimitError, anthropic.InternalServerError, and the
    transport-level errors that surface as connection resets. Importing the
    SDK at module load time would force every import path to pay the SDK
    import cost; we duck-type by class name + status code so this helper
    stays cheap to import."""
    name = type(exc).__name__
    if name in {"RateLimitError", "InternalServerError", "APIConnectionError",
                "APITimeoutError", "ServiceUnavailableError"}:
        return True
    # anthropic.APIStatusError carries .status_code; retry on 429 + 5xx.
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and (status == 429 or 500 <= status < 600):
        return True
    return False


def with_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> T:
    """Run `fn()` with exponential-backoff retry on retryable errors. Re-raise
    the final exception. Non-retryable exceptions (auth, malformed-request,
    etc.) propagate immediately."""
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except BaseException as e:
            if not _is_retryable(e) or attempt == max_attempts - 1:
                raise
            last_exc = e
            delay = min(base_delay * (2 ** attempt), max_delay)
            delay = delay * (0.5 + random.random())  # jitter [0.5x, 1.5x]
            time.sleep(delay)
    # Unreachable — last iteration always returns or raises.
    assert last_exc is not None
    raise last_exc
