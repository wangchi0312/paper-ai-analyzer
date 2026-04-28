from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PaperAnalysis:
    first_author: str
    first_author_affiliation: str
    second_author: str
    second_author_affiliation: str
    corresponding_author: str
    corresponding_author_affiliation: str
    publication_year: str
    paper_title: str
    venue: str
    doi: str
    core_problem: str
    core_hypotheses: list[str]
    research_approach: str
    key_methods: str
    data_source_and_scale: str
    core_findings: str
    main_conclusions: str
    field_contribution: str
    relevance_to_my_research: str
    highlights: str
    limitations: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PaperAnalysis":
        return cls(
            first_author=_as_text(data.get("first_author")),
            first_author_affiliation=_as_text(data.get("first_author_affiliation")),
            second_author=_as_text(data.get("second_author")),
            second_author_affiliation=_as_text(data.get("second_author_affiliation")),
            corresponding_author=_as_text(data.get("corresponding_author")),
            corresponding_author_affiliation=_as_text(data.get("corresponding_author_affiliation")),
            publication_year=_as_text(data.get("publication_year")),
            paper_title=_as_text(data.get("paper_title")),
            venue=_as_text(data.get("venue")),
            doi=_as_text(data.get("doi")),
            core_problem=_as_text(data.get("core_problem")),
            core_hypotheses=_as_text_list(data.get("core_hypotheses")),
            research_approach=_as_text(data.get("research_approach")),
            key_methods=_as_text(data.get("key_methods")),
            data_source_and_scale=_as_text(data.get("data_source_and_scale")),
            core_findings=_as_text(data.get("core_findings")),
            main_conclusions=_as_text(data.get("main_conclusions")),
            field_contribution=_as_text(data.get("field_contribution")),
            relevance_to_my_research=_as_text(data.get("relevance_to_my_research")),
            highlights=_as_text(data.get("highlights")),
            limitations=_as_text(data.get("limitations")),
        )


@dataclass
class FetchedPaper:
    title: str
    abstract: str
    doi: str | None = None
    link: str | None = None
    authors: str | None = None
    venue: str | None = None
    source_email_id: str | None = None
    fetch_method: str = "email"


@dataclass
class FetchAudit:
    fetched_at: str
    since_date: str | None
    max_emails: int
    no_web: bool
    email_count: int
    parsed_paper_count: int
    unique_paper_count: int
    duplicate_paper_count: int
    output_path: str
    alert_summary_link_count: int = 0
    expanded_paper_count: int = 0
    inbox_email_count: int = 0
    checked_email_count: int = 0
    matched_wos_email_count: int = 0
    skipped_seen_email_count: int = 0
    skipped_non_alert_email_count: int = 0
    browser_max_pages: int = 0
    browser_manual_login_wait_seconds: int = 0
    browser_expanded_paper_count: int = 0
    browser_new_unique_paper_count: int = 0
    browser_duplicate_paper_count: int = 0
    browser_expand_error_count: int = 0
    browser_expand_last_error: str | None = None
    email_details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Paper:
    title: str
    source_path: str | None = None
    link: str | None = None
    abstract: str = ""
    selected_text: str = ""
    full_text: str = ""
    embedding: list[float] = field(default_factory=list)
    score: float | None = None
    analysis: PaperAnalysis | None = None
    skipped_reason: str | None = None
    source_email_id: str | None = None
    full_text_path: str | None = None
    full_text_source: str | None = None
    full_text_status: str | None = None

    def to_dict(self, include_full_text: bool = False, include_embedding: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_full_text:
            data.pop("full_text", None)
        if not include_embedding:
            data.pop("embedding", None)
        return data


def _as_text(value: Any) -> str:
    if value is None:
        return "未识别"
    if isinstance(value, list):
        text = "；".join(str(item).strip() for item in value if str(item).strip())
        return text or "未识别"
    text = str(value).strip()
    return text or "未识别"


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        result = [str(item).strip() for item in value if str(item).strip()]
        return result or ["未识别"]
    text = _as_text(value)
    return [text]
