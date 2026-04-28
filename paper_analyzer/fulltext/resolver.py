from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.downloader import download_pdf, safe_pdf_name
from paper_analyzer.fulltext.source import FullTextResult


def resolve_full_text(
    paper: FetchedPaper,
    output_dir: Path,
    index: int,
    unpaywall_email: str | None = None,
    timeout: int = 30,
) -> FullTextResult:
    output_path = output_dir / safe_pdf_name(paper.title, index)
    errors: list[str] = []

    for source, url in _candidate_pdf_urls(paper, unpaywall_email=unpaywall_email, timeout=timeout):
        try:
            path = download_pdf(url, output_path, timeout=timeout)
            return FullTextResult(success=True, path=str(path), source=source, url=url)
        except Exception as exc:
            errors.append(f"{source}: {exc}")

    reason = "；".join(errors) if errors else "未找到可下载全文链接"
    return FullTextResult(success=False, reason=reason)


def _candidate_pdf_urls(
    paper: FetchedPaper,
    unpaywall_email: str | None = None,
    timeout: int = 30,
) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    if paper.link and _looks_like_pdf_url(paper.link):
        candidates.append(("publisher", paper.link))

    if paper.doi:
        candidates.extend(_unpaywall_candidates(paper.doi, unpaywall_email=unpaywall_email, timeout=timeout))
        candidates.extend(_semantic_scholar_candidates(paper.doi, timeout=timeout))

    candidates.extend(_arxiv_candidates(paper.title, timeout=timeout))

    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for source, url in candidates:
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append((source, url))
    return unique


def _unpaywall_candidates(doi: str, unpaywall_email: str | None, timeout: int) -> list[tuple[str, str]]:
    if not unpaywall_email:
        return []
    url = f"https://api.unpaywall.org/v2/{quote(doi)}"
    try:
        response = requests.get(url, params={"email": unpaywall_email}, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    candidates: list[tuple[str, str]] = []
    best = data.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        candidates.append(("unpaywall", best["url_for_pdf"]))
    for location in data.get("oa_locations") or []:
        if location.get("url_for_pdf"):
            candidates.append(("unpaywall", location["url_for_pdf"]))
    return candidates


def _semantic_scholar_candidates(doi: str, timeout: int) -> list[tuple[str, str]]:
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi)}"
    try:
        response = requests.get(url, params={"fields": "openAccessPdf,title"}, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    pdf_url = (data.get("openAccessPdf") or {}).get("url")
    return [("semantic_scholar", pdf_url)] if pdf_url else []


def _arxiv_candidates(title: str, timeout: int) -> list[tuple[str, str]]:
    if not title.strip():
        return []
    try:
        response = requests.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": f'ti:"{title[:180]}"', "start": 0, "max_results": 1},
            timeout=timeout,
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    candidates: list[tuple[str, str]] = []
    for link in root.findall(".//atom:entry/atom:link", ns):
        if link.attrib.get("title") == "pdf" and link.attrib.get("href"):
            candidates.append(("arxiv", link.attrib["href"]))
    return candidates


def _looks_like_pdf_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.endswith(".pdf") or "/pdf" in lowered or "pdf" in lowered
