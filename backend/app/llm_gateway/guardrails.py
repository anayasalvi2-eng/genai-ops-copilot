"""
Guardrails — enterprise LLM governance and security layer.

Covers:
  1.  Input length limits
  2.  Prompt injection detection
  3.  PII detection and redaction (input + output)
  4.  Sensitive credential/secret leakage prevention (output)
  5.  Content policy filtering (output)
  6.  Response grounding verification (output vs. source observations)
  7.  Output length enforcement

All rules are purely regex/heuristic — no external API calls — so they
add negligible latency and work fully offline.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable limits
# ---------------------------------------------------------------------------
MAX_INPUT_LENGTH  = 24_000   # characters
MIN_INPUT_LENGTH  = 3
MAX_OUTPUT_LENGTH = 10_000

# ---------------------------------------------------------------------------
# 1. Prompt injection patterns
#    Flag attempts to override the system persona or hijack instructions.
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?",         re.I),
    re.compile(r"disregard\s+(all\s+)?prior\s+(context|instructions?)", re.I),
    re.compile(r"forget\s+(everything|all\s+instructions?)",           re.I),
    re.compile(r"you\s+are\s+now\s+",                                  re.I),
    re.compile(r"new\s+(system\s+)?persona",                           re.I),
    re.compile(r"<\s*system\s*>",                                      re.I),
    re.compile(r"jailbreak",                                           re.I),
    re.compile(r"act\s+as\s+(?!data|pipeline|engineer|sre|ops)",       re.I),
    re.compile(r"pretend\s+(you\s+are|to\s+be)",                       re.I),
    re.compile(r"override\s+(safety|guardrail|policy|instruction)",    re.I),
    re.compile(r"system\s*:\s*you",                                    re.I),
]

# ---------------------------------------------------------------------------
# 2. PII patterns — scrub from both input (before sending) and output
#    Replacement tokens are bracketed so they are obvious in logs.
# ---------------------------------------------------------------------------
_PII_SCRUB: list[tuple[re.Pattern, str]] = [
    # Email addresses
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[EMAIL]"),
    # US/UK phone numbers  (+1-555-123-4567 / 07700 900123)
    (re.compile(r"(\+?\d[\d\s\-().]{7,}\d)"), "[PHONE]"),
    # Credit/debit card numbers (4–4–4–4 or 16-digit run)
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[CARD]"),
    # US Social Security Numbers  (123-45-6789)
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    # UK National Insurance  (AB 12 34 56 C)
    (re.compile(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-Z]\b"), "[NIN]"),
    # Passport-style numbers  (A12345678)
    (re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"), "[PASSPORT]"),
]

# ---------------------------------------------------------------------------
# 3. Secret / credential leakage patterns — output only
#    These should NEVER appear in LLM responses.
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),          # OpenAI keys
    re.compile(r"\bghp_[A-Za-z0-9]{36}"),           # GitHub PAT
    re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*", re.I),  # Bearer tokens
    re.compile(r"(password|passwd|secret|api[_-]?key)\s*[=:]\s*\S+", re.I),
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),   # PEM keys
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),   # Long base64 blobs
]

# ---------------------------------------------------------------------------
# 4. Content policy — categories blocked in output
# ---------------------------------------------------------------------------
_CONTENT_POLICY_PATTERNS: list[re.Pattern] = [
    re.compile(r"how\s+to\s+(make|build|create)\s+(a\s+)?(bomb|weapon|exploit)", re.I),
    re.compile(r"(kill|harm|attack)\s+(the\s+)?(user|customer|client)", re.I),
    re.compile(r"(racist|sexist|discriminat)",                           re.I),
    re.compile(r"fabricat(e|ed|ing)\s+(regulatory|compliance|legal)",   re.I),
]


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------

@dataclass
class GuardrailReport:
    """Summary of all checks performed on a single invocation."""
    input_pii_redacted:    bool = False
    injection_blocked:     bool = False
    output_pii_redacted:   bool = False
    secrets_found:         bool = False
    content_policy_breach: bool = False
    grounding_issues:      list[str] = field(default_factory=list)
    input_hash:            str = ""
    output_hash:           str = ""

    def has_violations(self) -> bool:
        return (
            self.injection_blocked
            or self.secrets_found
            or self.content_policy_breach
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_pii_redacted":    self.input_pii_redacted,
            "injection_blocked":     self.injection_blocked,
            "output_pii_redacted":   self.output_pii_redacted,
            "secrets_found":         self.secrets_found,
            "content_policy_breach": self.content_policy_breach,
            "grounding_issues":      self.grounding_issues,
            "input_hash":            self.input_hash,
            "output_hash":           self.output_hash,
        }


class GuardrailViolation(ValueError):
    """Raised when a hard guardrail rule is violated (blocks the call)."""


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class Guardrails:
    """
    Enterprise LLM governance and security layer.

    Usage (via LLMGateway — do not call directly):
        text   = guardrails.validate_input(raw_prompt)
        report = GuardrailReport()
        output = guardrails.sanitise_output(raw_response, report)
    """

    # ------------------------------------------------------------------
    # INPUT  — called BEFORE sending the prompt to any provider
    # ------------------------------------------------------------------

    def validate_input(self, text: str, report: GuardrailReport | None = None) -> str:
        """
        1. Enforce length limits
        2. Scan for prompt injection  → hard block (raises GuardrailViolation)
        3. Redact PII                 → soft scrub, logged
        """
        text = text.strip()

        # Length guards
        if len(text) < MIN_INPUT_LENGTH:
            raise GuardrailViolation(
                f"Input too short (minimum {MIN_INPUT_LENGTH} chars)."
            )
        if len(text) > MAX_INPUT_LENGTH:
            raise GuardrailViolation(
                f"Input too long ({len(text):,} chars). "
                f"Maximum is {MAX_INPUT_LENGTH:,} characters."
            )

        # Prompt injection — hard block
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning(
                    "Guardrails [INJECTION BLOCKED] pattern=%s", pattern.pattern
                )
                if report:
                    report.injection_blocked = True
                raise GuardrailViolation(
                    "Input contains disallowed instructions. Please rephrase your query."
                )

        # PII redaction (soft — scrub and continue)
        original_len = len(text)
        for pattern, replacement in _PII_SCRUB:
            text = pattern.sub(replacement, text)
        if len(text) != original_len or "[EMAIL]" in text or "[PHONE]" in text:
            logger.info("Guardrails [PII REDACTED] from input")
            if report:
                report.input_pii_redacted = True

        if report:
            report.input_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        logger.debug("Guardrails: input validation passed (%d chars)", len(text))
        return text

    # ------------------------------------------------------------------
    # OUTPUT — called AFTER receiving the LLM response
    # ------------------------------------------------------------------

    def sanitise_output(
        self,
        text: str,
        report: GuardrailReport | None = None,
        observations: list[dict] | None = None,
    ) -> str:
        """
        1. Enforce output length
        2. Detect and block credential/secret leakage  → hard block
        3. Redact PII
        4. Check content policy                        → hard block
        5. Grounding verification (if observations provided)
        """
        # Length enforcement
        if len(text) > MAX_OUTPUT_LENGTH:
            logger.warning(
                "Guardrails [OUTPUT TRUNCATED] %d → %d chars",
                len(text), MAX_OUTPUT_LENGTH,
            )
            text = text[:MAX_OUTPUT_LENGTH] + "\n\n[Output truncated by security policy]"

        # Credential / secret leakage — hard block
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                logger.error(
                    "Guardrails [SECRET LEAK BLOCKED] pattern=%s", pattern.pattern
                )
                if report:
                    report.secrets_found = True
                raise GuardrailViolation(
                    "LLM response contained a potential secret or credential and was blocked."
                )

        # PII redaction
        for pattern, replacement in _PII_SCRUB:
            text = pattern.sub(replacement, text)
        if report and any(tok in text for tok in ("[EMAIL]", "[PHONE]", "[SSN]")):
            report.output_pii_redacted = True
            logger.info("Guardrails [PII REDACTED] from output")

        # Content policy
        for pattern in _CONTENT_POLICY_PATTERNS:
            if pattern.search(text):
                logger.error(
                    "Guardrails [CONTENT POLICY BREACH] pattern=%s", pattern.pattern
                )
                if report:
                    report.content_policy_breach = True
                raise GuardrailViolation(
                    "LLM response violated content policy and was blocked."
                )

        # Grounding check — verify key values from observations appear in response
        if observations:
            issues = self._check_grounding(text, observations)
            if issues:
                logger.warning("Guardrails [GROUNDING ISSUES] %s", issues)
                if report:
                    report.grounding_issues = issues
                # Soft — append a disclaimer rather than blocking
                text += (
                    "\n\n⚠️  *Grounding note: the following values from source data "
                    f"were not found in this response: {', '.join(issues)}*"
                )

        if report:
            report.output_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        logger.debug("Guardrails: output sanitisation complete")
        return text

    # ------------------------------------------------------------------
    # Grounding helper
    # ------------------------------------------------------------------

    @staticmethod
    def _check_grounding(response: str, observations: list[dict]) -> list[str]:
        """
        Extract key anchors (case IDs, trade refs, break IDs, dollar amounts)
        from observations and check they appear verbatim in the response.
        Returns a list of missing anchor strings.
        """
        _ANCHOR_KEYS = {
            "case_id", "trade_ref", "break_id", "trade_id",
        }
        missing: list[str] = []
        for obs in observations:
            result = obs.get("tool_result", {})
            if isinstance(result, str):
                # already clipped JSON string — skip deep inspection
                continue
            # Walk one level into common wrapper keys
            for wrapper in ("case", "break", "suite"):
                if wrapper in result and isinstance(result[wrapper], dict):
                    result = result[wrapper]
                    break
            for key, val in result.items():
                if key in _ANCHOR_KEYS and isinstance(val, str) and val:
                    if val not in response:
                        missing.append(val)
        return missing
