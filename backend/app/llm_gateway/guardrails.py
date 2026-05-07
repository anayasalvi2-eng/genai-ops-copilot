"""
Guardrails — input validation and output sanitisation layer.

Applied by the LLM Gateway before sending a prompt and after receiving a
response.  Extend the rules here without touching provider or agent code.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
MAX_INPUT_LENGTH = 24000       # characters
MIN_INPUT_LENGTH = 3           # characters
MAX_OUTPUT_LENGTH = 10000      # characters

# Patterns that must not appear in user input (prompt-injection heuristics)
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?prior\s+(context|instructions?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a\s+)?(?!data|pipeline|engineer)", re.IGNORECASE),
]

# Patterns to scrub from LLM output (PII / secrets)
_OUTPUT_SCRUB_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Generic API keys / tokens (32+ hex chars)
    (re.compile(r"\b[A-Za-z0-9]{32,}\b"), "[REDACTED_TOKEN]"),
    # Email addresses
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[REDACTED_EMAIL]"),
]


class GuardrailViolation(ValueError):
    """Raised when a guardrail rule is violated."""


class Guardrails:
    """
    Stateless guardrail layer for input validation and output sanitisation.
    """

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def validate_input(self, text: str) -> str:
        """
        Validate and return the (possibly cleaned) input text.

        Raises:
            GuardrailViolation: if any rule is violated.
        """
        text = text.strip()

        if len(text) < MIN_INPUT_LENGTH:
            raise GuardrailViolation(
                f"Input too short (minimum {MIN_INPUT_LENGTH} characters)."
            )

        if len(text) > MAX_INPUT_LENGTH:
            raise GuardrailViolation(
                f"Input too long ({len(text)} chars). "
                f"Maximum allowed is {MAX_INPUT_LENGTH} characters."
            )

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning(
                    "Guardrails: potential prompt injection detected: '%s'",
                    pattern.pattern,
                )
                raise GuardrailViolation(
                    "Input contains disallowed instructions. Please rephrase your query."
                )

        logger.debug("Guardrails: input validation passed (%d chars)", len(text))
        return text

    # ------------------------------------------------------------------
    # Output sanitisation
    # ------------------------------------------------------------------

    def sanitise_output(self, text: str) -> str:
        """
        Scrub sensitive patterns from LLM output before returning to the caller.
        """
        if len(text) > MAX_OUTPUT_LENGTH:
            logger.warning(
                "Guardrails: output truncated from %d to %d chars",
                len(text),
                MAX_OUTPUT_LENGTH,
            )
            text = text[:MAX_OUTPUT_LENGTH] + "\n\n[Output truncated by guardrails]"

        for pattern, replacement in _OUTPUT_SCRUB_PATTERNS:
            text = pattern.sub(replacement, text)

        logger.debug("Guardrails: output sanitisation complete")
        return text
