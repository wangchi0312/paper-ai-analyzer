import os

from paper_analyzer.utils.config import load_full_text_config, load_llm_config, load_research_topic


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


def test_detect_email_provider_qq():
    from paper_analyzer.utils.config import _detect_email_provider

    assert _detect_email_provider("user@qq.com") == "qq"


def test_load_full_text_config_defaults_to_spis(monkeypatch):
    monkeypatch.delenv("FULL_TEXT_SOURCE", raising=False)
    monkeypatch.delenv("SPIS_BASE_URL", raising=False)
    monkeypatch.delenv("SPIS_WAIT_MINUTES", raising=False)
    monkeypatch.delenv("SPIS_POLL_INTERVAL_SECONDS", raising=False)
    import paper_analyzer.utils.config as config_mod

    config_mod._loaded = True
    cfg = load_full_text_config()

    assert cfg.source == "spis"
    assert cfg.spis_base_url == "https://spis.hnlat.com/"
    assert cfg.spis_wait_minutes == 30
    assert cfg.spis_poll_interval_seconds == 60


def test_detect_email_provider_163():
    from paper_analyzer.utils.config import _detect_email_provider

    assert _detect_email_provider("user@163.com") == "163"


def test_detect_email_provider_outlook():
    from paper_analyzer.utils.config import _detect_email_provider

    assert _detect_email_provider("user@outlook.com") == "outlook"
    assert _detect_email_provider("test@hotmail.com") == "outlook"


def test_detect_email_provider_gmail():
    from paper_analyzer.utils.config import _detect_email_provider

    assert _detect_email_provider("user@gmail.com") == "gmail"


def test_detect_email_provider_default():
    from paper_analyzer.utils.config import _detect_email_provider

    assert _detect_email_provider("user@unknown.com") == "qq"


def test_load_email_config_generic_env(monkeypatch):
    monkeypatch.setenv("EMAIL_ADDRESS", "test@163.com")
    monkeypatch.setenv("EMAIL_AUTH_CODE", "auth123")
    monkeypatch.delenv("QQ_EMAIL", raising=False)
    monkeypatch.delenv("QQ_EMAIL_AUTH_CODE", raising=False)
    import paper_analyzer.utils.config as config_mod
    config_mod._loaded = False

    cfg = config_mod.load_email_config()
    assert cfg.address == "test@163.com"
    assert cfg.auth_code == "auth123"
    assert cfg.imap_host == "imap.163.com"
    assert cfg.provider_key == "163"


def test_load_email_config_fallback_old_vars(monkeypatch):
    monkeypatch.setenv("QQ_EMAIL", "old@qq.com")
    monkeypatch.setenv("QQ_EMAIL_AUTH_CODE", "old_auth")
    monkeypatch.delenv("EMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("EMAIL_AUTH_CODE", raising=False)
    import paper_analyzer.utils.config as config_mod
    config_mod._loaded = False

    cfg = config_mod.load_email_config()
    assert cfg.address == "old@qq.com"
    assert cfg.imap_host == "imap.qq.com"


def test_load_email_config_manual_provider(monkeypatch):
    monkeypatch.setenv("EMAIL_ADDRESS", "user@gmail.com")
    monkeypatch.setenv("EMAIL_AUTH_CODE", "auth")
    import paper_analyzer.utils.config as config_mod
    config_mod._loaded = False

    cfg = config_mod.load_email_config(email_provider="outlook")
    assert cfg.imap_host == "outlook.office365.com"
    assert cfg.provider_key == "outlook"


def test_load_email_config_missing_address():
    import pytest
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("EMAIL_ADDRESS", "")
    monkeypatch.setenv("EMAIL_AUTH_CODE", "auth")
    monkeypatch.setenv("QQ_EMAIL", "")
    monkeypatch.setenv("QQ_EMAIL_AUTH_CODE", "")
    monkeypatch.delenv("EMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("EMAIL_AUTH_CODE", raising=False)
    monkeypatch.delenv("QQ_EMAIL", raising=False)
    monkeypatch.delenv("QQ_EMAIL_AUTH_CODE", raising=False)
    import paper_analyzer.utils.config as config_mod
    config_mod._loaded = True

    with pytest.raises(ValueError, match="EMAIL_ADDRESS"):
        config_mod.load_email_config()
    monkeypatch.undo()
