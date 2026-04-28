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

    @property
    def search_sender(self) -> str:
        return "clarivate.com"


def load_email_config() -> EmailConfig:
    _ensure_dotenv()
    address = os.getenv("QQ_EMAIL", "").strip()
    auth_code = os.getenv("QQ_EMAIL_AUTH_CODE", "").strip()
    if not address:
        raise ValueError("缺少 QQ_EMAIL，请在 .env 中配置。")
    if not auth_code:
        raise ValueError("缺少 QQ_EMAIL_AUTH_CODE，请在 .env 中配置。")
    return EmailConfig(address=address, auth_code=auth_code)
