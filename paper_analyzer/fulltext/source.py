from dataclasses import dataclass


@dataclass
class FullTextResult:
    success: bool
    path: str | None = None
    source: str | None = None
    url: str | None = None
    reason: str | None = None
