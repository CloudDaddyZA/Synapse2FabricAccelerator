"""Retry helpers backed by tenacity for transient Azure/REST failures."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

T = TypeVar("T")

# Transient conditions worth retrying.
TRANSIENT_ERRORS = (ConnectionError, TimeoutError)


def with_retry(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int = 5,
    backoff_seconds: int = 2,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> T:
    """Call ``func`` with exponential backoff retry on transient failures."""
    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=backoff_seconds, max=60),
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
        reraise=True,
    )
    for attempt in retryer:
        with attempt:
            if logger and attempt.retry_state.attempt_number > 1:
                logger.warning(
                    "Retry %s/%s for %s",
                    attempt.retry_state.attempt_number,
                    max_attempts,
                    getattr(func, "__name__", "call"),
                )
            return func(*args, **kwargs)
    raise RuntimeError("with_retry exhausted without returning")  # pragma: no cover
