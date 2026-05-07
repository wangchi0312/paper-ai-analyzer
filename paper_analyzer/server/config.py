from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ENV_PATH = Path(".env")
ALLOWED_ENV_KEYS = {
    "EMAIL_ADDRESS",
    "EMAIL_AUTH_CODE",
    "EMAIL_PROVIDER",
    "LLM_PROVIDER",
    "LLM_TEMPERATURE",
    "RESEARCH_TOPIC",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "SILICONFLOW_API_KEY",
    "SILICONFLOW_BASE_URL",
    "SILICONFLOW_MODEL",
    "MODELSCOPE_API_KEY",
    "MODELSCOPE_BASE_URL",
    "MODELSCOPE_MODEL",
    "FULL_TEXT_SOURCE",
    "WOS_USE_BROWSER",
    "WOS_MAX_EMAILS",
    "WOS_BROWSER_MAX_PAGES",
}


def read_public_config() -> dict[str, Any]:
    load_dotenv(ENV_PATH, override=False)
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
    prefix = _provider_prefix(provider)
    return {
        "email_address": os.getenv("EMAIL_ADDRESS") or os.getenv("QQ_EMAIL", ""),
        "email_provider": os.getenv("EMAIL_PROVIDER", "auto"),
        "email_auth_code_configured": bool(os.getenv("EMAIL_AUTH_CODE") or os.getenv("QQ_EMAIL_AUTH_CODE")),
        "llm_provider": provider,
        "llm_api_key_configured": bool(os.getenv(f"{prefix}_API_KEY")),
        "llm_base_url": os.getenv(f"{prefix}_BASE_URL", ""),
        "llm_model": os.getenv(f"{prefix}_MODEL", ""),
        "llm_temperature": os.getenv("LLM_TEMPERATURE", "0.2"),
        "research_topic": os.getenv("RESEARCH_TOPIC", ""),
        "full_text_source": os.getenv("FULL_TEXT_SOURCE", "manual"),
        "wos_use_browser": _read_bool("WOS_USE_BROWSER", True),
        "wos_max_emails": _read_int("WOS_MAX_EMAILS", 20),
        "wos_browser_max_pages": _read_int("WOS_BROWSER_MAX_PAGES", 20),
    }


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("llm_provider") or "deepseek").lower()
    prefix = _provider_prefix(provider)
    updates: dict[str, str] = {
        "LLM_PROVIDER": provider,
        "FULL_TEXT_SOURCE": "manual",
    }
    _put_if_present(updates, "EMAIL_ADDRESS", payload.get("email_address"))
    _put_if_nonempty(updates, "EMAIL_AUTH_CODE", payload.get("email_auth_code"))
    _put_if_present(updates, "EMAIL_PROVIDER", payload.get("email_provider"))
    _put_if_present(updates, "RESEARCH_TOPIC", payload.get("research_topic"))
    _put_if_present(updates, "LLM_TEMPERATURE", payload.get("llm_temperature"))
    _put_if_present(updates, "WOS_USE_BROWSER", _format_bool(payload.get("wos_use_browser")))
    _put_if_present(updates, "WOS_MAX_EMAILS", payload.get("wos_max_emails"))
    _put_if_present(updates, "WOS_BROWSER_MAX_PAGES", payload.get("wos_browser_max_pages"))
    _put_if_nonempty(updates, f"{prefix}_API_KEY", payload.get("llm_api_key"))
    _put_if_present(updates, f"{prefix}_BASE_URL", payload.get("llm_base_url"))
    _put_if_present(updates, f"{prefix}_MODEL", payload.get("llm_model"))
    _write_env_updates(updates)
    os.environ.update(updates)
    return read_public_config()


def _write_env_updates(updates: dict[str, str]) -> None:
    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    output: list[str] = []
    seen: set[str] = set()
    for line in existing_lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key and key in ALLOWED_ENV_KEYS and key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _put_if_present(updates: dict[str, str], key: str, value: Any) -> None:
    if value is None:
        return
    updates[key] = str(value).strip()


def _put_if_nonempty(updates: dict[str, str], key: str, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        updates[key] = text


def _provider_prefix(provider: str) -> str:
    mapping = {
        "deepseek": "DEEPSEEK",
        "siliconflow": "SILICONFLOW",
        "modelscope": "MODELSCOPE",
    }
    return mapping.get(provider.lower(), "DEEPSEEK")


def _read_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _format_bool(value: Any) -> str | None:
    if value is None:
        return None
    return "true" if bool(value) else "false"
