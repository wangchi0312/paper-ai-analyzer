import re


ABSTRACT_PATTERN = re.compile(
    r"(?:^|\n)\s*(abstract|摘要)\s*[:：]?\s*(.+?)(?=\n\s*(keywords?|index terms|introduction|1\.?\s+introduction|引言|关键词)\b)",
    re.IGNORECASE | re.DOTALL,
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_abstract(full_text: str) -> str:
    match = ABSTRACT_PATTERN.search(full_text)
    if not match:
        return ""
    return normalize_text(match.group(2))


def select_representative_text(full_text: str, max_chars: int = 4000) -> tuple[str, str]:
    abstract = extract_abstract(full_text)
    if abstract:
        return abstract[:max_chars], abstract

    selected = normalize_text(full_text)[:max_chars]
    return selected, ""
