import re
from typing import Any


def is_unknown(value: str | None) -> bool:
    return not value or value.strip() in {"未识别", "未提供", "unknown", "Unknown", "N/A"}


def normalize_title(text: str) -> str:
    """Normalize title for similarity matching — keeps alphanumeric and CJK characters."""
    value = text.lower()
    value = re.sub(r"[^a-z0-9一-鿿]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_title_key(text: str) -> str:
    """Normalize title for dedup keys — simple whitespace normalization."""
    return re.sub(r"\s+", " ", text).strip().lower()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def emit_progress(callback, message: str) -> None:
    if callback is not None:
        callback(message)
