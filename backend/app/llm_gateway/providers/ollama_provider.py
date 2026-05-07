"""
Ollama Provider — wraps the Ollama local inference REST API.

Ollama runs models locally with zero API cost.
Install: https://ollama.com   |   Run: ollama serve

Configure via environment variables:
    OLLAMA_BASE_URL   (default: http://localhost:11434)
    OLLAMA_MODEL      (default: llama3)
"""

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3"


class OllamaProvider:
    """
    Stateless wrapper around the Ollama /api/chat REST endpoint.

    Returns the same normalised dict shape as OpenAIProvider so the
    LLMGateway can treat all providers interchangeably.
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model or os.getenv("OLLAMA_MODEL", _DEFAULT_MODEL)
        self.base_url = (
            base_url or os.getenv("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        ).rstrip("/")
        logger.info(
            "OllamaProvider: initialised with model=%s base_url=%s",
            self.model,
            self.base_url,
        )

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """
        Call the Ollama /api/chat endpoint (non-streaming).

        Returns:
            {
                "text":              str,
                "model":             str,
                "prompt_tokens":     int,
                "completion_tokens": int,
                "total_tokens":      int,
            }
        """
        payload = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            }
        ).encode("utf-8")

        url = f"{self.base_url}/api/chat"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"OllamaProvider: cannot reach Ollama at {self.base_url} — {exc}. "
                "Is Ollama running? Start it with: ollama serve"
            ) from exc

        text = body.get("message", {}).get("content", "")
        # Ollama returns prompt_eval_count / eval_count for token counts
        prompt_tokens = body.get("prompt_eval_count", 0)
        completion_tokens = body.get("eval_count", 0)

        return {
            "text": text,
            "model": f"ollama/{self.model}",
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
