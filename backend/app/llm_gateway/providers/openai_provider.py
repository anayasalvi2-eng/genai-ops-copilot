"""
OpenAI Provider — wraps the OpenAI chat completions API.

Reads the API key from the OPENAI_API_KEY environment variable.
Model is configurable; defaults to gpt-4o-mini.
"""

import os
import logging
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider:
    """
    Thin, stateless wrapper around openai.OpenAI.

    Returns a dict containing the response text and usage metadata so the
    calling gateway can record telemetry without coupling to the openai SDK.
    """

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY environment variable is not set. "
                "Copy .env.example to .env and add your key."
            )
        self.model = model
        self._client = OpenAI(api_key=api_key)

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """
        Call chat completions and return a normalised response dict.

        Returns:
            {
                "text":             str,
                "model":            str,
                "prompt_tokens":    int,
                "completion_tokens": int,
                "total_tokens":     int,
            }
        """
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )

        choice = response.choices[0]
        usage = response.usage

        return {
            "text": choice.message.content or "",
            "model": response.model,
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }
