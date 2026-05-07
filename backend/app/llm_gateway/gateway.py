"""
LLM Gateway — orchestrates the prompt manager, guardrails, telemetry, and
the underlying LLM provider into a single, cohesive call surface.

All agent nodes should go through this gateway rather than calling the
provider directly so that cross-cutting concerns (guardrails, telemetry) are
applied consistently.
"""

import logging
from typing import Any

from app.llm_gateway.prompt_manager import PromptManager
from app.llm_gateway.guardrails import Guardrails, GuardrailViolation
from app.llm_gateway.telemetry import Telemetry, InvocationRecord, Timer
from app.llm_gateway.providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class LLMGateway:
    """
    Single entry-point for all LLM interactions.

    Responsibilities:
    1. Render prompt templates via PromptManager
    2. Validate inputs with Guardrails
    3. Call the configured LLM provider
    4. Sanitise outputs with Guardrails
    5. Record telemetry via Telemetry
    """

    def __init__(self) -> None:
        self.prompt_manager = PromptManager()
        self.guardrails = Guardrails()
        self.telemetry = Telemetry()
        self.provider = OpenAIProvider()

    def invoke(
        self,
        prompt_name: str,
        system_prompt: str = "You are a helpful AI assistant.",
        **template_vars: str,
    ) -> str:
        """
        Render a prompt template, run guardrails, call the LLM, and return
        the sanitised response text.

        Parameters
        ----------
        prompt_name:
            Name of the registered prompt template.
        system_prompt:
            System message sent to the LLM (not templated).
        **template_vars:
            Variables substituted into the prompt template.

        Returns
        -------
        str
            Sanitised LLM response text.
        """
        # 1. Render the template
        user_message = self.prompt_manager.render(prompt_name, **template_vars)

        # 2. Validate the rendered prompt (input guardrails)
        try:
            user_message = self.guardrails.validate_input(user_message)
        except GuardrailViolation as exc:
            logger.warning("LLMGateway: input guardrail blocked prompt '%s': %s", prompt_name, exc)
            raise

        # 3. Call the provider and measure latency
        timer = Timer()
        result: dict[str, Any] = {}
        error: str | None = None
        success = False

        try:
            with timer:
                result = self.provider.complete(
                    system_prompt=system_prompt,
                    user_message=user_message,
                )
            success = True
        except Exception as exc:
            error = str(exc)
            logger.error("LLMGateway: provider error for prompt '%s': %s", prompt_name, exc)
            raise
        finally:
            # 4. Emit telemetry regardless of success/failure
            self.telemetry.record(
                InvocationRecord(
                    prompt_name=prompt_name,
                    model=result.get("model", "unknown"),
                    prompt_tokens=result.get("prompt_tokens", 0),
                    completion_tokens=result.get("completion_tokens", 0),
                    total_tokens=result.get("total_tokens", 0),
                    latency_ms=timer.elapsed_ms,
                    prompt_char_length=len(user_message),
                    success=success,
                    error=error,
                )
            )

        # 5. Sanitise output
        raw_text: str = result.get("text", "")
        return self.guardrails.sanitise_output(raw_text)
