"""
Tests for the LLM Provider abstraction layer.

These tests validate the provider factory pattern works correctly
and that the base interface is properly defined. We use a MockProvider
for testing to avoid needing real API keys.
"""

import pytest

from src.config.settings import LLMConfig, LLMProvider
from src.llm.providers import (
    AnthropicProvider,
    BaseLLMProvider,
    LLMError,
    OllamaProvider,
    OpenAIProvider,
    create_llm_provider,
)


# ──────────────────────────────────────────────────────────────────────
# Mock Provider for Testing
# ──────────────────────────────────────────────────────────────────────

class MockLLMProvider(BaseLLMProvider):
    """A mock LLM provider that returns predefined responses.
    Used in tests to avoid real API calls."""

    def __init__(self, config: LLMConfig, responses: dict[str, str] | None = None):
        super().__init__(config)
        self.responses = responses or {}
        self.call_history: list[dict] = []

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        self.call_history.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
        })
        # Return a predefined response or a default
        for keyword, response in self.responses.items():
            if keyword.lower() in prompt.lower():
                return response
        return "Mock response for: " + prompt[:50]


# ──────────────────────────────────────────────────────────────────────
# Factory Tests
# ──────────────────────────────────────────────────────────────────────

class TestCreateLLMProvider:
    """Test that the factory function creates the correct provider type."""

    def test_creates_anthropic_provider(self):
        config = LLMConfig(provider=LLMProvider.ANTHROPIC, api_key="test-key")
        provider = create_llm_provider(config)
        assert isinstance(provider, AnthropicProvider)

    def test_creates_openai_provider(self):
        config = LLMConfig(provider=LLMProvider.OPENAI, api_key="test-key")
        provider = create_llm_provider(config)
        assert isinstance(provider, OpenAIProvider)

    def test_creates_ollama_provider(self):
        config = LLMConfig(provider=LLMProvider.OLLAMA, model="llama3.1")
        provider = create_llm_provider(config)
        assert isinstance(provider, OllamaProvider)

    def test_invalid_provider_raises(self):
        with pytest.raises(Exception):
            LLMConfig(provider="nonexistent")


# ──────────────────────────────────────────────────────────────────────
# Base Provider Tests
# ──────────────────────────────────────────────────────────────────────

class TestBaseLLMProvider:
    """Test the base class functionality (token estimation, etc.)."""

    def test_token_estimation(self):
        config = LLMConfig(provider=LLMProvider.ANTHROPIC, api_key="test")
        provider = MockLLMProvider(config)
        # ~4 chars per token heuristic
        text = "a" * 400
        tokens = provider.estimate_tokens(text)
        assert tokens == 100  # 400 chars / 4

    @pytest.mark.asyncio
    async def test_mock_provider_tracks_calls(self):
        config = LLMConfig(provider=LLMProvider.ANTHROPIC, api_key="test")
        provider = MockLLMProvider(config, responses={"hello": "Hi there!"})

        result = await provider.generate("hello world")
        assert result == "Hi there!"
        assert len(provider.call_history) == 1
        assert provider.call_history[0]["prompt"] == "hello world"

    @pytest.mark.asyncio
    async def test_mock_provider_with_system_prompt(self):
        config = LLMConfig(provider=LLMProvider.ANTHROPIC, api_key="test")
        provider = MockLLMProvider(config)

        await provider.generate("test prompt", system_prompt="Be helpful")
        assert provider.call_history[0]["system_prompt"] == "Be helpful"
