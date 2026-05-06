import os
from dataclasses import dataclass

from dotenv import load_dotenv

_loaded = False


def _ensure_dotenv() -> None:
    global _loaded
    if not _loaded:
        load_dotenv()
        _loaded = True


@dataclass
class LLMConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.2


DEFAULT_RESEARCH_TOPIC = "激活函数、自适应激活函数、物理信息神经网络（PINNs）、偏微分方程求解、科学机器学习"

PROVIDER_ENV_PREFIX = {
    "deepseek": "DEEPSEEK",
    "siliconflow": "SILICONFLOW",
    "modelscope": "MODELSCOPE",
}

EMAIL_PROVIDER_CONFIGS = {
    "qq": {
        "imap_host": "imap.qq.com",
        "imap_port": 993,
        "label": "QQ邮箱",
        "auth_help": "QQ邮箱 → 设置 → 账户 → POP3/IMAP服务 → 生成授权码",
    },
    "163": {
        "imap_host": "imap.163.com",
        "imap_port": 993,
        "label": "163邮箱",
        "auth_help": "163邮箱 → 设置 → POP3/SMTP/IMAP → 开启IMAP → 生成授权码",
    },
    "outlook": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "label": "Outlook",
        "auth_help": "Microsoft 账户 → 安全 → 应用密码（需开启两步验证）",
    },
    "gmail": {
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "label": "Gmail",
        "auth_help": "Google 账户 → 安全 → 应用专用密码（需开启两步验证）",
    },
}


def load_research_topic() -> str:
    _ensure_dotenv()
    return os.getenv("RESEARCH_TOPIC", "").strip() or DEFAULT_RESEARCH_TOPIC


def load_llm_config(provider: str | None = None) -> LLMConfig:
    _ensure_dotenv()
    selected_provider = (provider or os.getenv("LLM_PROVIDER") or "deepseek").lower()
    prefix = PROVIDER_ENV_PREFIX.get(selected_provider)
    if not prefix:
        raise ValueError(f"不支持的 LLM provider：{selected_provider}")

    api_key = os.getenv(f"{prefix}_API_KEY", "")
    base_url = os.getenv(f"{prefix}_BASE_URL", "")
    model = os.getenv(f"{prefix}_MODEL", "")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    if not api_key:
        raise ValueError(f"缺少 {prefix}_API_KEY，请在 .env 中配置。")
    if not base_url:
        raise ValueError(f"缺少 {prefix}_BASE_URL，请在 .env 中配置。")
    if not model:
        raise ValueError(f"缺少 {prefix}_MODEL，请在 .env 中配置。")

    return LLMConfig(
        provider=selected_provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
    )


@dataclass
class EmailConfig:
    address: str
    auth_code: str
    imap_host: str = "imap.qq.com"
    imap_port: int = 993
    provider_key: str = "qq"
    auth_help: str = ""

    @property
    def search_sender(self) -> str:
        return "clarivate.com"


@dataclass
class FullTextConfig:
    source: str = "spis"
    spis_base_url: str = "https://spis.hnlat.com/"
    spis_wait_minutes: int = 30
    spis_poll_interval_seconds: int = 60
    spis_title_match_threshold: float = 0.82


def _detect_email_provider(address: str) -> str:
    lowered = address.lower()
    if "qq.com" in lowered:
        return "qq"
    if "163.com" in lowered:
        return "163"
    if "outlook" in lowered or "hotmail" in lowered or "live.com" in lowered:
        return "outlook"
    if "gmail" in lowered or "googlemail" in lowered:
        return "gmail"
    return "qq"


def load_mirror_site_config() -> dict:
    _ensure_dotenv()
    urls_raw = os.getenv("MIRROR_SITE_URL", "").strip()
    urls = [u.strip() for u in urls_raw.split(",") if u.strip()] if urls_raw else []
    return {
        "mirror_site_urls": urls,
        "mirror_site_enabled": os.getenv("MIRROR_SITE_ENABLED", "false").strip().lower() in ("true", "1", "yes"),
    }


def load_email_config(email_provider: str | None = None) -> EmailConfig:
    _ensure_dotenv()
    address = os.getenv("EMAIL_ADDRESS", "").strip()
    auth_code = os.getenv("EMAIL_AUTH_CODE", "").strip()
    if not address:
        address = os.getenv("QQ_EMAIL", "").strip()
    if not auth_code:
        auth_code = os.getenv("QQ_EMAIL_AUTH_CODE", "").strip()
    if not address:
        raise ValueError("缺少 EMAIL_ADDRESS (或 QQ_EMAIL)，请在 .env 中配置。")
    if not auth_code:
        raise ValueError("缺少 EMAIL_AUTH_CODE (或 QQ_EMAIL_AUTH_CODE)，请在 .env 中配置。")

    provider_key = (email_provider or os.getenv("EMAIL_PROVIDER") or _detect_email_provider(address)).lower()
    provider_config = EMAIL_PROVIDER_CONFIGS.get(provider_key)
    if not provider_config:
        raise ValueError(f"不支持的邮箱运营商：{provider_key}，支持：{list(EMAIL_PROVIDER_CONFIGS.keys())}")

    return EmailConfig(
        address=address,
        auth_code=auth_code,
        imap_host=provider_config["imap_host"],
        imap_port=provider_config["imap_port"],
        provider_key=provider_key,
        auth_help=provider_config["auth_help"],
    )


def load_full_text_config() -> FullTextConfig:
    _ensure_dotenv()
    return FullTextConfig(
        source=os.getenv("FULL_TEXT_SOURCE", "spis").strip().lower() or "spis",
        spis_base_url=os.getenv("SPIS_BASE_URL", "https://spis.hnlat.com/").strip() or "https://spis.hnlat.com/",
        spis_wait_minutes=_env_int("SPIS_WAIT_MINUTES", 30, minimum=0),
        spis_poll_interval_seconds=_env_int("SPIS_POLL_INTERVAL_SECONDS", 60, minimum=5),
        spis_title_match_threshold=_env_float("SPIS_TITLE_MATCH_THRESHOLD", 0.82, minimum=0.0, maximum=1.0),
    )


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value
