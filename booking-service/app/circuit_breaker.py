import logging
import os
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int,
        open_timeout_seconds: float,
        window_seconds: float,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.open_timeout_seconds = open_timeout_seconds
        self.window_seconds = window_seconds
        self._state = CircuitState.CLOSED
        self._failure_timestamps: list[float] = []
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_from_open()
            return self._state

    def before_call(self) -> None:
        with self._lock:
            self._maybe_transition_from_open()

            if self._state == CircuitState.OPEN:
                raise CircuitBreakerOpenError("circuit breaker is OPEN")

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    raise CircuitBreakerOpenError("circuit breaker is HALF_OPEN, probe in flight")
                self._half_open_probe_in_flight = True

    def on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.CLOSED)
            self._failure_timestamps.clear()
            self._half_open_probe_in_flight = False

    def on_failure(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._failure_timestamps.append(now)
            cutoff = now - self.window_seconds
            self._failure_timestamps = [ts for ts in self._failure_timestamps if ts >= cutoff]

            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.OPEN)
                self._half_open_probe_in_flight = False
                return

            if len(self._failure_timestamps) >= self.failure_threshold:
                self._transition(CircuitState.OPEN)
            self._half_open_probe_in_flight = False

    def _maybe_transition_from_open(self) -> None:
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return
        if time.monotonic() - self._opened_at >= self.open_timeout_seconds:
            self._transition(CircuitState.HALF_OPEN)

    def _transition(self, new_state: CircuitState) -> None:
        if self._state == new_state:
            return
        logger.warning("circuit breaker transition %s -> %s", self._state.value, new_state.value)
        self._state = new_state
        if new_state == CircuitState.OPEN:
            self._opened_at = time.monotonic()
        elif new_state == CircuitState.CLOSED:
            self._opened_at = None
            self._failure_timestamps.clear()
            self._half_open_probe_in_flight = False


def create_circuit_breaker() -> CircuitBreaker:
    return CircuitBreaker(
        failure_threshold=int(os.getenv("CB_FAILURE_THRESHOLD", "5")),
        open_timeout_seconds=float(os.getenv("CB_OPEN_TIMEOUT_SECONDS", "20")),
        window_seconds=float(os.getenv("CB_WINDOW_SECONDS", "30")),
    )
