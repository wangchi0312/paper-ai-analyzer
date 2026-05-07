from pathlib import Path

from paper_analyzer.server import config as config_mod


def test_save_config_updates_only_allowed_env_keys(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("KEEP_ME=yes\nDEEPSEEK_API_KEY=old\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "ENV_PATH", env_path)
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    saved = config_mod.save_config(
        {
            "email_address": "user@example.com",
            "llm_provider": "deepseek",
            "llm_api_key": "",
            "llm_base_url": "https://api.deepseek.com",
            "llm_model": "deepseek-chat",
            "research_topic": "PINN",
            "wos_use_browser": False,
            "wos_max_emails": 12,
            "wos_browser_max_pages": 4,
        }
    )

    text = env_path.read_text(encoding="utf-8")
    assert "KEEP_ME=yes" in text
    assert "DEEPSEEK_API_KEY=old" in text
    assert "EMAIL_ADDRESS=user@example.com" in text
    assert "FULL_TEXT_SOURCE=manual" in text
    assert "WOS_USE_BROWSER=false" in text
    assert "WOS_MAX_EMAILS=12" in text
    assert "WOS_BROWSER_MAX_PAGES=4" in text
    assert saved["full_text_source"] == "manual"
    assert saved["wos_use_browser"] is False
    assert saved["wos_max_emails"] == 12
    assert saved["wos_browser_max_pages"] == 4
