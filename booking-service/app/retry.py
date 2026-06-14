import logging
import os
import time
from typing import Callable, TypeVar

import grpc

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
}

MAX_RETRIES = int(os.getenv("GRPC_MAX_RETRIES", "3"))
BASE_BACKOFF_MS = int(os.getenv("GRPC_BASE_BACKOFF_MS", "100"))


def call_with_retry(fn: Callable[[], T]) -> T:
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn()
        except grpc.RpcError as exc:
            last_error = exc
            code = exc.code()
            if code not in RETRYABLE_CODES or attempt == MAX_RETRIES:
                raise

            delay_ms = BASE_BACKOFF_MS * (2 ** (attempt - 1))
            logger.warning(
                "retryable grpc error code=%s attempt=%s/%s backoff_ms=%s",
                code,
                attempt,
                MAX_RETRIES,
                delay_ms,
            )
            time.sleep(delay_ms / 1000.0)

    if last_error:
        raise last_error
    raise RuntimeError("retry failed without error")
