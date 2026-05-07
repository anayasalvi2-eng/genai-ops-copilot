"""
LLM Gateway — enterprise-grade orchestration layer.

Responsibilities
----------------
1.  Render prompt templates (PromptManager)
2.  Input guardrails — injection, PII, length (Guardrails)
3.  Rate limiting — sliding-window per caller_id
4.  Budget enforcement (Telemetry.build_record)
5.  Provider selection & fallback chain  (LLM_PROVIDERS env var)
6.  Circuit breaker per provider (CLOSED → OPEN → HALF-OPEN)
7.  Model version-pinning warning (warn on floating aliases)
8.  Output guardrails — secrets, PII, content policy, grounding
9.  Durable audit log + cost telemetry (Telemetry)

Environment Variables
---------------------
LLM_PROVIDERS        Comma-separated provider names (default: openai)
                     Example: openai,ollama
OPENAI_MODEL         Pinned model name (default: gpt-4o-mini-2024-07-18)
OLLAMA_MODEL         Ollama model name (default: llama3)
OLLAMA_BASE_URL      Ollama base URL   (default: http://localhost:11434)
DAILY_BUDGET_USD     Hard daily USD cap (default: 5.00)
AUDIT_LOG_PATH       Path for audit JSONL (default: backend/audit_log.jsonl)
"""

import collections
import logging
import os
import threading
import time
from typing import Any

from app.llm_gateway.guardrails import Guardrails, GuardrailReport, GuardrailViolation
from app.llm_gateway.prompt_manager import PromptManager
from app.llm_gateway.telemetry import Telemetry, Timer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Floating model aliases that should be pinned in production
# ---------------------------------------------------------------------------
_FLOATING_ALIASES = {
    "gpt-4o", "gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "llama3", "mistral",
}

# ---------------------------------------------------------------------------
# Circuit-breaker settings
# ---------------------------------------------------------------------------
_CB_FAILURE_THRESHOLD = 3      # consecutive failures before OPEN
_CB_RECOVERY_SECONDS  = 30     # seconds before attempting HALF-OPEN

# ---------------------------------------------------------------------------
# Rate-limiter settings
# ---------------------------------------------------------------------------
_RATE_WINDOW_SECONDS = 60      # sliding window length
_RATE_MAX_CALLS      = 30      # max calls per caller_id per window


class _CircuitBreaker:
    """Per-provider circuit breaker (CLOSED → OPEN → HALF-OPEN → CLOSED)."""

    def __init__(self, provider_name: str) -> None:
        self.name = provider_name
        self._state = "CLOSED"   # CLOSED | OPEN | HALF-OPEN
        self._failures = 0
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        with self._lock:
            if self._state == "CLOSED":
                return True
            if self._state == "OPEN":
                if time.monotonic() - self._opened_at >= _CB_RECOVERY_SECONDS:
                    self._state = "HALF-OPEN"
                    logger.info("CircuitBreaker[%s]: HALF-OPEN (probing)", self.name)
                    return True
                return False
            # HALF-OPEN — allow one probe
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._state != "CLOSED":
                logger.info("CircuitBreaker[%s]: CLOSED (recovered)", self.name)
            self._state = "CLOSED"
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= _CB_FAILURE_THRESHOLD or self._state == "HALF-OPEN":
                self._state = "OPEN"
                self._opened_at = time.monotonic()
                logger.error(
                    "CircuitBreaker[%s]: OPEN after %d failures",
                    self.name, self._failures,
                )


class _RateLimiter:
    """Sliding-window rate limiter keyed by caller_id."""

    def __init__(self) -> None:
        self._windows: dict[str, collections.deque] = collections.defaultdict(
            lambda: collections.deque()
        )
        self._lock = threading.Lock()

    def check(self, caller_id: str) -> None:
        """Raise RateLimitError if the caller has exceeded the limit."""
        now = time.monotonic()
        with self._lock:
            dq = self._windows[caller_id]
            # Evict timestamps outside the window
            while dq and now - dq[0] > _RATE_WINDOW_SECONDS:
                dq.popleft()
            if len(dq) >= _RATE_MAX_CALLS:
                raise RateLimitError(
                    f"Rate limit exceeded: {_RATE_MAX_CALLS} calls per "
                    f"{_RATE_WINDOW_SECONDS}s for caller '{caller_id}'."
                )
            dq.append(now)


class RateLimitError(RuntimeError):
    """Raised when a caller exceeds the sliding-window rate limit."""


def _build_provider(name: str):
    """Instantiate a provider by name string."""
    name = name.strip().lower()
    if name == "openai":
        from app.llm_gateway.providers.openai_provider import OpenAIProvider
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18")
        _warn_if_floating(model, "openai")
        return OpenAIProvider(model=model)
    if name == "ollama":
        from app.llm_gateway.providers.ollama_provider import OllamaProvider
        model = os.getenv("OLLAMA_MODEL", "llama3")
        _warn_if_floating(model, "ollama")
        return OllamaProvider(model=model)
    raise ValueError(f"Unknown LLM provider '{name}'. Supported: openai, ollama")


def _warn_if_floating(model: str, provider: str) -> None:
    """Emit a WARNING when a floating model alias is used instead of a pinned version."""
    base = model.split("-")[0] if "-" in model else model
    if model in _FLOATING_ALIASES or base in _FLOATING_ALIASES:
        logger.warning(
            "LLMGateway [MODEL PINNING]: provider=%s model='%s' is a floating alias. "
            "Pin to a specific version (e.g. gpt-4o-mini-2024-07-18) to avoid "
            "unexpected behaviour changes.",
            provider, model,
        )


class LLMGateway:
    """
    Single entry-point for all LLM interactions.

    All agent nodes should call  gateway.invoke(...)  so that governance,
    security, rate limiting, and fallback are applied consistently.
    """

    def __init__(self) -> None:
        self.prompt_manager = PromptManager()
        self.guardrails     = Guardrails()
        self.telemetry      = Telemetry()
        self._rate_limiter  = _RateLimiter()

        # Build ordered provider list from LLM_PROVIDERS env var
        provider_names = os.getenv("LLM_PROVIDERS", "openai").split(",")
        self._providers: list[tuple[str, Any]] = []
        self._circuit_breakers: dict[str, _CircuitBreaker] = {}
        for name in provider_names:
            name = name.strip().lower()
            if not name:
                continue
            try:
                provider = _build_provider(name)
                self._providers.append((name, provider))
                self._circuit_breakers[name] = _CircuitBreaker(name)
                logger.info("LLMGateway: registered provider '%s'", name)
            except Exception as exc:
                logger.warning(
                    "LLMGateway: skipping provider '%s' — %s", name, exc
                )

        if not self._providers:
            raise RuntimeError("LLMGateway: no providers could be initialised.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def invoke(
        self,
        prompt_name: str,
        system_prompt: str = "You are a helpful AI assistant.",
        caller_id: str = "default",
        observations: list[dict] | None = None,
        **template_vars: str,
    ) -> str:
        """
        Render a prompt template, run guardrails, call the LLM with fallback,
        and return the sanitised response text.

        Parameters
        ----------
        prompt_name:
            Name of the registered prompt template.
        system_prompt:
            System message (not templated).
        caller_id:
            Identifier for rate-limit tracking (e.g. request ID, user ID).
        observations:
            MCP tool results used for grounding verification.
        **template_vars:
            Variables substituted into the prompt template.
        """
        # ── Rate limit ───────────────────────────────────────────────
        self._rate_limiter.check(caller_id)

        # ── Render template ──────────────────────────────────────────
        user_message = self.prompt_manager.render(prompt_name, **template_vars)

        # ── Input guardrails ─────────────────────────────────────────
        report = GuardrailReport()
        try:
            user_message = self.guardrails.validate_input(user_message, report)
        except GuardrailViolation as exc:
            logger.warning(
                "LLMGateway: input guardrail blocked '%s': %s", prompt_name, exc
            )
            raise

        # ── Provider fallback loop ───────────────────────────────────
        last_exc: Exception | None = None
        result: dict[str, Any] = {}
        used_provider: str = "unknown"

        for pname, provider in self._providers:
            cb = self._circuit_breakers[pname]
            if not cb.is_available():
                logger.warning(
                    "LLMGateway: provider '%s' circuit OPEN — skipping", pname
                )
                continue

            timer = Timer()
            success = False
            error: str | None = None

            try:
                with timer:
                    result = provider.complete(
                        system_prompt=system_prompt,
                        user_message=user_message,
                    )
                cb.record_success()
                success = True
                used_provider = pname
                break  # success — stop trying more providers
            except Exception as exc:
                error = str(exc)
                last_exc = exc
                cb.record_failure()
                logger.warning(
                    "LLMGateway: provider '%s' failed for '%s': %s",
                    pname, prompt_name, exc,
                )
            finally:
                # Emit telemetry for every attempt (success or failure)
                rec = self.telemetry.build_record(
                    prompt_name=prompt_name,
                    model=result.get("model", pname),
                    prompt_tokens=result.get("prompt_tokens", 0),
                    completion_tokens=result.get("completion_tokens", 0),
                    total_tokens=result.get("total_tokens", 0),
                    latency_ms=timer.elapsed_ms,
                    prompt_char_length=len(user_message),
                    success=success,
                    error=error,
                    extra={"provider": pname, "caller_id": caller_id},
                    input_text=user_message,
                    output_text=result.get("text", ""),
                )
                self.telemetry.record(rec)

        if not success:
            raise RuntimeError(
                f"LLMGateway: all providers failed for prompt '{prompt_name}'. "
                f"Last error: {last_exc}"
            ) from last_exc

        logger.debug(
            "LLMGateway: prompt='%s' provider='%s' model='%s'",
            prompt_name, used_provider, result.get("model"),
        )

        # ── Output guardrails ─────────────────────────────────────────
        raw_text: str = result.get("text", "")
        return self.guardrails.sanitise_output(raw_text, report, observations)

