import sys
import types

from paper_analyzer.llm.client import OpenAICompatibleClient
from paper_analyzer.utils.config import LLMConfig


class _Delta:
    def __init__(self, content: str | None):
        self.content = content


class _Choice:
    def __init__(self, content: str | None):
        self.delta = _Delta(content)


class _Chunk:
    def __init__(self, content: str | None):
        self.choices = [_Choice(content)]


def test_openai_compatible_client_reads_stream(monkeypatch):
    calls = {}

    class FakeCompletions:
        def create(self, **kwargs):
            calls.update(kwargs)
            return [_Chunk("{"), _Chunk('"ok"'), _Chunk(": true}")]

    class FakeOpenAI:
        def __init__(self, api_key: str, base_url: str):
            self.chat = types.SimpleNamespace(
                completions=FakeCompletions(),
            )

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))

    client = OpenAICompatibleClient(
        LLMConfig(
            provider="deepseek",
            api_key="test-key",
            base_url="https://example.com",
            model="test-model",
        )
    )

    assert client.complete("prompt") == '{"ok": true}'
    assert calls["stream"] is True
