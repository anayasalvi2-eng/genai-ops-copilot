"""
Telemetry — structured logging of LLM invocation metrics.

In a production environment these events would be forwarded to a metrics
backend (Prometheus, Datadog, OpenTelemetry Collector, etc.).  Here we emit
structured log lines that can be ingested by any log aggregation platform.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("llm_gateway.telemetry")


@dataclass
class InvocationRecord:
    """Immutable record of a single LLM invocation."""

    prompt_name: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    prompt_char_length: int
    success: bool
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": "llm_invocation",
            "prompt_name": self.prompt_name,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "prompt_char_length": self.prompt_char_length,
            "success": self.success,
            "error": self.error,
            **self.extra,
        }


class Telemetry:
    """
    Records and emits LLM invocation telemetry.

    Usage
    -----
    with Telemetry().timer() as t:
        result = provider.complete(...)
    Telemetry().record(prompt_name, result, t.elapsed_ms, ...)
    """

    def record(self, record: InvocationRecord) -> None:
        """Emit the invocation record as a structured log entry."""
        logger.info("TELEMETRY %s", record.as_dict())


class Timer:
    """Context manager for measuring wall-clock latency."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        self.elapsed_ms = round((time.perf_counter() - self._start) * 1000, 2)
