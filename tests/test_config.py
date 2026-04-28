import os

from paper_analyzer.utils.config import load_llm_config, load_research_topic


def test_load_research_topic_from_env(monkeypatch):
    monkeypatch.setenv("RESEARCH_TOPIC", "自定义研究主题")
    # Reset the singleton so it re-reads
    import paper_analyzer.utils.config as config_mod
    config_mod._loaded = False
    topic = load_research_topic()
    assert topic == "自定义研究主题"


def test_load_research_topic_default(monkeypatch):
    monkeypatch.delenv("RESEARCH_TOPIC", raising=False)
    import paper_analyzer.utils.config as config_mod
    config_mod._loaded = False
    topic = load_research_topic()
    assert "激活函数" in topic


def test_load_llm_config_deepseek(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.3")
    import paper_analyzer.utils.config as config_mod
    config_mod._loaded = False
    cfg = load_llm_config()
    assert cfg.provider == "deepseek"
    assert cfg.api_key == "test-key"
    assert cfg.temperature == 0.3


def test_load_llm_config_missing_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    import paper_analyzer.utils.config as config_mod
    config_mod._loaded = True  # skip dotenv so .env file doesn't re-populate
    import pytest
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        load_llm_config()


def test_load_llm_config_unsupported_provider():
    import pytest
    import paper_analyzer.utils.config as config_mod
    config_mod._loaded = True  # skip dotenv reload
    with pytest.raises(ValueError, match="不支持的 LLM provider"):
        load_llm_config("unknown_provider")
