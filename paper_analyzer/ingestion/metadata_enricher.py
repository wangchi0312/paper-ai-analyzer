import re
from difflib import SequenceMatcher
from html import unescape
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.utils.logger import get_logger


logger = get_logger(__name__)

TITLE_MATCH_THRESHOLD = 0.88


def enrich_paper_metadata(paper: FetchedPaper, timeout: int = 10) -> FetchedPaper:
    """Enrich paper metadata from public scholarly APIs.

    The function is intentionally conservative: title-based matches must be
    highly similar, and empty external fields never overwrite existing WoS/email
    fields.
    """
    if not paper.title.strip() and not (paper.doi or "").strip():
        return paper

    try:
        import requests
    except ImportError:
        logger.warning("缺少 requests 包，无法调用公开元数据源")
        return paper

    for source, lookup in (
        ("openalex", _lookup_openalex),
        ("crossref", _lookup_crossref),
        ("semantic_scholar", _lookup_semantic_scholar),
    ):
        try:
            metadata = lookup(requests, paper, timeout)
        except Exception as exc:
            logger.debug("公开元数据源 %s 查询失败：%s", source, exc)
            continue
        if not metadata:
            continue
        if not _is_safe_match(paper, metadata):
            continue
        if _merge_metadata(paper, metadata):
            _append_fetch_method(paper, source)
    return paper


def _lookup_openalex(requests, paper: FetchedPaper, timeout: int) -> dict[str, str] | None:
    params: dict[str, str | int] = {
        "per-page": 3,
        "select": "display_name,doi,authorships,primary_location,host_venue,abstract_inverted_index",
    }
    if paper.doi:
        params["filter"] = f"doi:{_strip_doi_url(paper.doi)}"
    else:
        params["search"] = paper.title
    response = requests.get("https://api.openalex.org/works", params=params, timeout=timeout)
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        return None
    item = results[0]
    venue = _openalex_venue(item)
    authors = _join_texts(
        [
            authorship.get("author", {}).get("display_name", "")
            for authorship in item.get("authorships", [])[:12]
        ]
    )
    return {
        "title": _clean_text(item.get("display_name")),
        "doi": _strip_doi_url(item.get("doi")),
        "authors": authors,
        "venue": venue,
        "abstract": _openalex_abstract(item.get("abstract_inverted_index")),
    }


def _lookup_crossref(requests, paper: FetchedPaper, timeout: int) -> dict[str, str] | None:
    if paper.doi:
        url = f"https://api.crossref.org/works/{quote(_strip_doi_url(paper.doi), safe='')}"
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        item = response.json().get("message", {})
    else:
        response = requests.get(
            "https://api.crossref.org/works",
            params={
                "query.bibliographic": paper.title,
                "rows": 3,
                "select": "DOI,title,abstract,author,container-title",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        items = response.json().get("message", {}).get("items", [])
        if not items:
            return None
        item = items[0]

    authors = _join_texts([_crossref_author_name(author) for author in item.get("author", [])[:12]])
    title = _first_text(item.get("title"))
    venue = _first_text(item.get("container-title"))
    return {
        "title": title,
        "doi": _strip_doi_url(item.get("DOI")),
        "authors": authors,
        "venue": venue,
        "abstract": _strip_markup(item.get("abstract", "")),
    }


def _lookup_semantic_scholar(requests, paper: FetchedPaper, timeout: int) -> dict[str, str] | None:
    fields = "title,abstract,externalIds,authors,venue,url"
    if paper.doi:
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{_strip_doi_url(paper.doi)}"
        response = requests.get(url, params={"fields": fields}, timeout=timeout)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        item = response.json()
    else:
        response = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": paper.title, "limit": 3, "fields": fields},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        if not data:
            return None
        item = data[0]

    external_ids = item.get("externalIds") or {}
    authors = _join_texts([author.get("name", "") for author in item.get("authors", [])[:12]])
    return {
        "title": _clean_text(item.get("title")),
        "doi": _strip_doi_url(external_ids.get("DOI")),
        "authors": authors,
        "venue": _clean_text(item.get("venue")),
        "abstract": _clean_text(item.get("abstract")),
    }


def _merge_metadata(paper: FetchedPaper, metadata: dict[str, str]) -> bool:
    changed = False
    for field in ("doi", "authors", "venue"):
        value = _strip_doi_url(metadata.get(field)) if field == "doi" else _clean_text(metadata.get(field))
        if value and not _clean_text(getattr(paper, field)):
            setattr(paper, field, value)
            changed = True

    abstract = _clean_text(metadata.get("abstract"))
    if abstract and len(abstract) > len(_clean_text(paper.abstract)):
        paper.abstract = abstract
        changed = True
    return changed


def _is_safe_match(paper: FetchedPaper, metadata: dict[str, str]) -> bool:
    if paper.doi and metadata.get("doi"):
        return _strip_doi_url(paper.doi).lower() == _strip_doi_url(metadata["doi"]).lower()
    source_title = _normalize_title(paper.title)
    candidate_title = _normalize_title(metadata.get("title", ""))
    if not source_title or not candidate_title:
        return False
    if source_title == candidate_title:
        return True
    return SequenceMatcher(None, source_title, candidate_title).ratio() >= TITLE_MATCH_THRESHOLD


def _append_fetch_method(paper: FetchedPaper, source: str) -> None:
    current = paper.fetch_method or ""
    if source in current.split("+"):
        return
    paper.fetch_method = f"{current}+{source}" if current else source


def _openalex_venue(item: dict[str, Any]) -> str:
    primary_source = (item.get("primary_location") or {}).get("source") or {}
    venue = _clean_text(primary_source.get("display_name"))
    if venue:
        return venue
    host_venue = item.get("host_venue") or {}
    return _clean_text(host_venue.get("display_name"))


def _openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not isinstance(inverted_index, dict):
        return ""
    words_by_position: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for position in positions:
            words_by_position[int(position)] = word
    return " ".join(words_by_position[index] for index in sorted(words_by_position))


def _crossref_author_name(author: dict[str, Any]) -> str:
    given = _clean_text(author.get("given"))
    family = _clean_text(author.get("family"))
    return " ".join(part for part in [given, family] if part)


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        return _clean_text(value[0] if value else "")
    return _clean_text(value)


def _join_texts(values: list[str]) -> str:
    return "; ".join(value for value in (_clean_text(item) for item in values) if value)


def _strip_markup(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return BeautifulSoup(unescape(text), "html.parser").get_text(" ", strip=True)


def _strip_doi_url(value: Any) -> str:
    text = _clean_text(value)
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _normalize_title(title: str) -> str:
    text = _clean_text(title).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
