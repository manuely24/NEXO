from types import SimpleNamespace

import pytest

from nexo.llm.gemini_provider import GeminiProvider


def test_gemini_provider_uses_official_client_without_network(monkeypatch):
    provider = GeminiProvider(api_key="test-key")
    captured = {}

    def generate_content(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(text='{"actions": []}')

    monkeypatch.setattr(provider.client.models, "generate_content", generate_content)

    result = provider.generate("safe prompt")

    assert result == '{"actions": []}'
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["contents"] == "safe prompt"
    assert captured["config"]["response_mime_type"] == "application/json"


def test_gemini_provider_requires_local_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiProvider()