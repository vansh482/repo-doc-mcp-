"""
LLM Provider Abstraction Layer.

This module implements the Strategy pattern for LLM providers. The idea is simple:
all LLM providers must implement the same interface (BaseLLMProvider), so the rest
of the codebase never needs to know WHICH LLM it's talking to.

    ┌──────────────────────────────────┐
    │       BaseLLMProvider            │   <── Abstract interface
    │  + generate(prompt, system) -> str│
    │  + count_tokens(text) -> int     │
    └──────────┬───────────────────────┘
               │
    ┌──────────┼──────────────┬────────────────┐
    ▼          ▼              ▼                 ▼
 Anthropic   OpenAI       Ollama         (future providers)

The factory function `create_llm_provider()` reads the config and returns
the right implementation. All consumers just call provider.generate().
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Optional

from src.config.settings import LLMConfig, LLMProvider


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers.

    Every provider must implement:
    - generate(): Send a prompt, get a response string
    - count_tokens(): Estimate token count (for chunking decisions)

    The generate() method accepts both a user prompt and an optional system prompt.
    System prompts are used to set the documentation "personality" — technical vs
    non-technical writing style, for example.
    """

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate a response from the LLM.

        Args:
            prompt: The user/main prompt (contains the code and instructions)
            system_prompt: Optional system-level instructions (writing style, etc.)

        Returns:
            The LLM's text response as a string.

        Raises:
            LLMError: If the API call fails after retries.
        """
        ...

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate — 1 token ≈ 4 characters for English text.
        Providers can override with more accurate counting."""
        return len(text) // 4


class LLMError(Exception):
    """Raised when an LLM API call fails."""
    pass


# ──────────────────────────────────────────────────────────────────────
# Anthropic (Claude) Provider
# ──────────────────────────────────────────────────────────────────────

class AnthropicProvider(BaseLLMProvider):
    """Claude API provider using the official Anthropic Python SDK.

    Requires: ANTHROPIC_API_KEY environment variable or config.api_key
    Models: claude-sonnet-4-20250514, claude-opus-4-20250514, claude-haiku-4-5-20251001, etc.
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            import anthropic
        except ImportError:
            raise ImportError("Install anthropic SDK: pip install anthropic")

        api_key = config.api_key or None  # SDK auto-reads ANTHROPIC_API_KEY env var
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        try:
            kwargs = {
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = await self.client.messages.create(**kwargs)
            return response.content[0].text

        except Exception as e:
            raise LLMError(f"Anthropic API error: {e}") from e

    def estimate_tokens(self, text: str) -> int:
        """Claude uses a similar tokenizer to GPT — ~4 chars per token is a
        reasonable estimate. For precise counting, you'd use the anthropic
        tokenizer, but it's not worth the dependency for estimation."""
        return len(text) // 4


# ──────────────────────────────────────────────────────────────────────
# OpenAI (GPT) Provider
# ──────────────────────────────────────────────────────────────────────

class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider using the official openai Python SDK.

    Requires: OPENAI_API_KEY environment variable or config.api_key
    Models: gpt-4o, gpt-4-turbo, gpt-3.5-turbo, etc.
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            import openai
        except ImportError:
            raise ImportError("Install openai SDK: pip install openai")

        api_key = config.api_key or None  # SDK auto-reads OPENAI_API_KEY env var
        self.client = openai.AsyncOpenAI(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await self.client.chat.completions.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=messages,
            )
            return response.choices[0].message.content

        except Exception as e:
            raise LLMError(f"OpenAI API error: {e}") from e

    def estimate_tokens(self, text: str) -> int:
        """OpenAI has tiktoken for precise counting, but we keep it simple."""
        try:
            import tiktoken
            enc = tiktoken.encoding_for_model(self.config.model)
            return len(enc.encode(text))
        except (ImportError, KeyError):
            return len(text) // 4


# ──────────────────────────────────────────────────────────────────────
# Ollama (Local LLM) Provider
# ──────────────────────────────────────────────────────────────────────

class OllamaProvider(BaseLLMProvider):
    """Ollama provider for local/self-hosted LLMs.

    Ollama exposes an OpenAI-compatible API, so we use httpx to call it directly.
    This avoids depending on the openai SDK just for Ollama.

    Requires: Ollama running locally (default: http://localhost:11434)
    Models: llama3.1, codellama, mistral, deepseek-coder, etc.
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            import httpx
        except ImportError:
            raise ImportError("Install httpx: pip install httpx")

        self.base_url = config.base_url or "http://localhost:11434"
        self.httpx = httpx

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Call Ollama's /api/chat endpoint (OpenAI-compatible format)."""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            async with self.httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.config.model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": self.config.temperature,
                            "num_predict": self.config.max_tokens,
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["message"]["content"]

        except Exception as e:
            raise LLMError(f"Ollama API error: {e}") from e


# ──────────────────────────────────────────────────────────────────────
# AWS Bedrock Provider
# ──────────────────────────────────────────────────────────────────────

class BedrockProvider(BaseLLMProvider):
    """AWS Bedrock provider — uses your existing AWS SSO/IAM credentials.

    No API key needed. Auth comes from your AWS profile (SSO, env vars, or
    instance role). Uses the anthropic SDK's built-in Bedrock client.

    The model can be a standard model ID (e.g., 'anthropic.claude-3-5-sonnet-20241022-v2:0')
    or an inference profile ARN from your AWS account.
    """

    BEDROCK_MODEL_MAP = {
        "claude-sonnet-4-20250514": "anthropic.claude-sonnet-4-20250514-v1:0",
        "claude-haiku-4-5-20251001": "anthropic.claude-haiku-4-5-20251001-v1:0",
        "claude-3-5-sonnet": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
    }

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            from anthropic import AsyncAnthropicBedrock
        except ImportError:
            raise ImportError("Install anthropic SDK: pip install anthropic")

        import boto3

        kwargs = {}
        region = config.aws_region or os.environ.get("AWS_REGION", "us-west-2")
        kwargs["aws_region"] = region

        profile = config.aws_profile or os.environ.get("AWS_PROFILE")
        if profile:
            session = boto3.Session(profile_name=profile, region_name=region)
            credentials = session.get_credentials().get_frozen_credentials()
            kwargs["aws_access_key"] = credentials.access_key
            kwargs["aws_secret_key"] = credentials.secret_key
            if credentials.token:
                kwargs["aws_session_token"] = credentials.token

        self.client = AsyncAnthropicBedrock(**kwargs)

    def _resolve_model(self) -> str:
        model = self.config.model
        if model.startswith("arn:"):
            return model
        if model.startswith("anthropic."):
            return model
        return self.BEDROCK_MODEL_MAP.get(model, model)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        try:
            kwargs = {
                "model": self._resolve_model(),
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = await self.client.messages.create(**kwargs)
            return response.content[0].text

        except Exception as e:
            raise LLMError(f"AWS Bedrock API error: {e}") from e


# ──────────────────────────────────────────────────────────────────────
# Factory — creates the right provider based on config
# ──────────────────────────────────────────────────────────────────────

def create_llm_provider(config: LLMConfig) -> BaseLLMProvider:
    """Factory function that returns the appropriate LLM provider.

    Usage:
        config = LLMConfig(provider="anthropic", model="claude-sonnet-4-20250514")
        provider = create_llm_provider(config)
        response = await provider.generate("Explain this code...")

    This is the ONLY function the rest of the codebase should use to get
    an LLM provider. It handles all the wiring.
    """
    providers = {
        LLMProvider.ANTHROPIC: AnthropicProvider,
        LLMProvider.OPENAI: OpenAIProvider,
        LLMProvider.OLLAMA: OllamaProvider,
        LLMProvider.BEDROCK: BedrockProvider,
    }

    provider_class = providers.get(config.provider)
    if not provider_class:
        raise ValueError(
            f"Unknown LLM provider: {config.provider}. "
            f"Supported: {', '.join(p.value for p in LLMProvider)}"
        )

    return provider_class(config)
