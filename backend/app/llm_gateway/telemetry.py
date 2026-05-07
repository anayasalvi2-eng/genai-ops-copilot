"""
Telemetry — durable structured logging of LLM invocation metrics.

Features
--------
* Structured log lines (JSON-compatible) for any log aggregation platform
* Append-only JSONL audit log written to disk  (AUDIT_LOG_PATH env var)
* Cost tracking per model  (COST_PER_1K_TOKENS lookup table)
* Daily budget cap with hard enforcement  (DAILY_BUDGET_USD env var)
* Privacy: input/output stored only as SHA-256 hashes in the audit log
"""

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger("llm_gateway.telemetry")

# ---------------------------------------------------------------------------
# Cost table  (USD per 1 000 tokens, input + output combined for simplicity)
# Update as provider pricing changes.
# ---------------------------------------------------------------------------
COST_PER_1K_TOKENS: dict[str, float] = {
    "gpt-4o":                0.005,
    "gpt-4o-mini":           0.00015,
    "gpt-4o-mini-2024-07-18": 0.00015,
    "gpt-4-turbo":           0.01,
    "gpt-4":                 0.03,
    "gpt-3.5-turbo":         0.0005,
    # Ollama is free (local)
    "ollama/llama3":         0.0,
    "ollama/mistral":        0.0,
    "ollama/phi3":           0.0,
}

_UNKNOWN_MODEL_COST = 0.001   # conservative fallback for unknown models

# ---------------------------------------------------------------------------
# Audit log path  (default: backend/audit_log.jsonl)
# ---------------------------------------------------------------------------
_DEFAULT_LOG_PATH = str(
    Path(__file__).resolve().parent.parent.parent / "audit_log.jsonl"
)


def _get_cost(model: str, total_tokens: int) -> float:
    """Return the USD cost for *total_tokens* on *model*."""
    # Normalise: strip sub-model date suffixes for lookup e.g. gpt-4o-mini-2024-07-18
    rate = COST_PER_1K_TOKENS.get(model)
    if rate is None:
        # Try prefix matching for versioned aliases
        for key in COST_PER_1K_TOKENS:
            if model.startswith(key):
                rate = COST_PER_1K_TOKENS[key]
                break
    if rate is None:
        rate = _UNKNOWN_MODEL_COST
        logger.warning("Telemetry: no cost entry for model=%s, using %.4f", model, rate)
    return round(rate * total_tokens / 1000, 6)


@dataclass
class InvocationRecord:
    """Immutable record of a single LLM invocation."""

    prompt_name:      str
    model:            str
    prompt_tokens:    int
    completion_tokens: int
    total_tokens:     int
    latency_ms:       float
    prompt_char_length: int
    success:          bool
    cost_usd:         float = 0.0
    error:            str | None = None
    extra:            dict[str, Any] = field(default_factory=dict)
    # Hashed inputs/outputs — never store plaintext in audit records
    input_hash:       str = ""
    output_hash:      str = ""
    timestamp:        str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "event":              "llm_invocation",
            "timestamp":          self.timestamp,
            "prompt_name":        self.prompt_name,
            "model":              self.model,
            "prompt_tokens":      self.prompt_tokens,
            "completion_tokens":  self.completion_tokens,
            "total_tokens":       self.total_tokens,
            "latency_ms":         self.latency_ms,
            "prompt_char_length": self.prompt_char_length,
            "cost_usd":           self.cost_usd,
            "success":            self.success,
            "error":              self.error,
            "input_hash":         self.input_hash,
            "output_hash":        self.output_hash,
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

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Daily cost accumulator — reset when the date rolls over
        self._current_date: date = date.today()
        self._daily_cost_usd: float = 0.0
        # Config from environment
        self._budget: float = float(os.getenv("DAILY_BUDGET_USD", "5.00"))
        self._log_path = os.getenv("AUDIT_LOG_PATH", _DEFAULT_LOG_PATH)
        logger.info(
            "Telemetry: daily_budget=%.2f audit_log=%s",
            self._budget, self._log_path,
        )

    # ------------------------------------------------------------------
    # Budget enforcement
    # ------------------------------------------------------------------

    def _check_budget(self, cost_usd: float) -> None:
        """
        Add *cost_usd* to today's total and raise BudgetExceededError if the
        daily cap would be breached.  Thread-safe.
        """
        with self._lock:
            today = date.today()
            if today != self._current_date:
                # New day — reset accumulator
                logger.info(
                    "Telemetry: daily reset. Previous day cost=%.4f USD",
                    self._daily_cost_usd,
                )
                self._daily_cost_usd = 0.0
                self._current_date = today

            projected = self._daily_cost_usd + cost_usd
            if projected > self._budget:
                raise BudgetExceededError(
                    f"Daily LLM budget of ${self._budget:.2f} USD would be exceeded "
                    f"(current=${self._daily_cost_usd:.4f}, this call=${cost_usd:.4f})."
                )
            self._daily_cost_usd = projected

    def daily_cost(self) -> float:
        """Return today's accumulated spend in USD."""
        with self._lock:
            return self._daily_cost_usd

    # ------------------------------------------------------------------
    # Record emission
    # ------------------------------------------------------------------

    def record(self, record: InvocationRecord) -> None:
        """
        1. Emit a structured log line.
        2. Append a privacy-safe JSONL record to the audit log.
        """
        logger.info("TELEMETRY %s", record.as_dict())
        self._append_audit(record)

    def _append_audit(self, record: InvocationRecord) -> None:
        """Append one JSONL line to the audit log.  Creates the file if absent."""
        try:
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record.as_dict()) + "\n")
        except OSError as exc:
            logger.warning("Telemetry: audit log write failed: %s", exc)

    # ------------------------------------------------------------------
    # Convenience factory
    # ------------------------------------------------------------------

    def build_record(
        self,
        *,
        prompt_name: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        latency_ms: float,
        prompt_char_length: int,
        success: bool,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
        input_text: str = "",
        output_text: str = "",
    ) -> InvocationRecord:
        """
        Build an InvocationRecord, compute cost, enforce budget (if success),
        and return the record.  Raises BudgetExceededError before a call if
        this would exceed the daily cap.
        """
        cost = _get_cost(model, total_tokens)
        if success:
            self._check_budget(cost)

        in_hash  = hashlib.sha256(input_text.encode()).hexdigest()[:16]  if input_text  else ""
        out_hash = hashlib.sha256(output_text.encode()).hexdigest()[:16] if output_text else ""

        return InvocationRecord(
            prompt_name=prompt_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            prompt_char_length=prompt_char_length,
            success=success,
            cost_usd=cost,
            error=error,
            extra=extra or {},
            input_hash=in_hash,
            output_hash=out_hash,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )


class BudgetExceededError(RuntimeError):
    """Raised when the daily LLM cost budget would be exceeded."""


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

