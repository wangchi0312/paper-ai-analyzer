from difflib import SequenceMatcher
from pathlib import Path
import re
import time
from urllib.parse import quote, urljoin, urlparse
import xml.etree.ElementTree as ET

import requests

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.downloader import download_pdf, safe_pdf_name
from paper_analyzer.fulltext.manual import resolve_manual_pdf
from paper_analyzer.fulltext.source import FullTextResult


MAX_CANDIDATES_PER_SOURCE = 1
MAX_DOWNLOAD_CANDIDATES = 4
TITLE_MATCH_THRESHOLD = 0.88
SOURCE_PRIORITY = {
    "publisher": 0,
    "unpaywall": 1,
    "semantic_scholar": 2,
    "openalex": 3,
    "arxiv": 4,
    "publisher_page": 5,
}


def resolve_full_text(
    paper: FetchedPaper,
    output_dir: Path,
    index: int,
    unpaywall_email: str | None = None,
    timeout: int = 30,
    manual_pdf_dir: str | None = None,
) -> FullTextResult:
    output_path = output_dir / safe_pdf_name(paper.title, index)
    errors: list[str] = []
    deadline = time.monotonic() + _total_budget_seconds(timeout)

    manual_result = resolve_manual_pdf(paper, manual_pdf_dir, output_dir=output_dir, index=index)
    if manual_result and manual_result.success:
        return manual_result
    if manual_result and manual_result.reason:
        errors.append(f"manual_upload: {manual_result.reason}")

    candidate_timeout = _remaining_timeout(deadline, timeout)
    candidates = _candidate_pdf_urls(
        paper,
        unpaywall_email=unpaywall_email,
        timeout=candidate_timeout,
        deadline=deadline,
    )
    if _deadline_expired(deadline) and not candidates:
        errors.append("budget: 全文下载超时")
    for source, url in candidates[:MAX_DOWNLOAD_CANDIDATES]:
        if _deadline_expired(deadline):
            errors.append("budget: 全文下载超时")
            break
        try:
            path = download_pdf(url, output_path, timeout=_remaining_timeout(deadline, timeout))
            return FullTextResult(success=True, path=str(path), source=source, url=url)
        except Exception as exc:
            errors.append(f"{source}: {_classify_download_error(exc)}")

    reason = _failure_reason(errors)
    return FullTextResult(success=False, reason=reason)


def _candidate_pdf_urls(
    paper: FetchedPaper,
    unpaywall_email: str | None = None,
    timeout: int = 30,
    deadline: float | None = None,
) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    if paper.link and _looks_like_pdf_url(paper.link):
        candidates.append(("publisher", paper.link))

    if paper.doi:
        if not _deadline_expired(deadline):
            candidates.extend(_openalex_candidates(paper, timeout=_remaining_timeout(deadline, timeout)))
        if not _deadline_expired(deadline):
            candidates.extend(_unpaywall_candidates(paper.doi, unpaywall_email=unpaywall_email, timeout=_remaining_timeout(deadline, timeout)))
        if not _deadline_expired(deadline):
            candidates.extend(_semantic_scholar_candidates(paper.doi, timeout=_remaining_timeout(deadline, timeout)))
    elif paper.title:
        if not _deadline_expired(deadline):
            candidates.extend(_openalex_candidates(paper, timeout=_remaining_timeout(deadline, timeout)))

    if not _deadline_expired(deadline):
        candidates.extend(_arxiv_candidates(paper.title, timeout=_remaining_timeout(deadline, timeout)))

    if paper.doi and not _deadline_expired(deadline):
        candidates.extend(_doi_landing_page_candidates(paper.doi, timeout=_remaining_timeout(deadline, timeout)))
    if not _deadline_expired(deadline):
        candidates.extend(_publisher_page_candidates(paper.link, timeout=_remaining_timeout(deadline, timeout)))

    return _rank_candidate_urls(candidates)


def _openalex_candidates(paper: FetchedPaper, timeout: int) -> list[tuple[str, str]]:
    params: dict[str, str | int] = {
        "per-page": 3,
        "select": "doi,display_name,open_access,locations",
    }
    title_lookup = not paper.doi
    if paper.doi:
        params["filter"] = f"doi:{_strip_doi_url(paper.doi)}"
    else:
        params["search"] = paper.title
    try:
        response = requests.get("https://api.openalex.org/works", params=params, timeout=timeout)
        response.raise_for_status()
        results = response.json().get("results", [])
    except Exception:
        return []
    if not results:
        return []

    candidates: list[tuple[str, str]] = []
    for item in results:
        if title_lookup and not _safe_title_match(paper.title, item.get("display_name", "")):
            continue
        oa_url = (item.get("open_access") or {}).get("oa_url")
        if oa_url and _looks_like_pdf_url(oa_url):
            candidates.append(("openalex", oa_url))
        for location in item.get("locations") or []:
            pdf_url = location.get("pdf_url")
            landing_url = location.get("landing_page_url")
            if pdf_url:
                candidates.append(("openalex", pdf_url))
            elif landing_url and _looks_like_pdf_url(landing_url):
                candidates.append(("openalex", landing_url))
            if len(candidates) >= 2:
                break
        if candidates:
            break
    return candidates


def _doi_landing_page_candidates(doi: str, timeout: int) -> list[tuple[str, str]]:
    landing_url = f"https://doi.org/{quote(_strip_doi_url(doi), safe='/')}"
    return _publisher_page_candidates(landing_url, timeout=timeout, source="publisher_page")


def _publisher_page_candidates(
    url: str | None,
    timeout: int,
    source: str = "publisher_page",
) -> list[tuple[str, str]]:
    if not url or _looks_like_wos_url(url) or _looks_like_pdf_url(url):
        return []
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return []
    content_type = response.headers.get("content-type", "").lower()
    if "pdf" in content_type or response.content[:1024].lstrip().startswith(b"%PDF"):
        return [(source, response.url)]
    if "html" not in content_type and "text/" not in content_type:
        return []
    return [(source, link) for link in _extract_pdf_links(response.text, response.url)[:3]]


def _extract_pdf_links(html: str, base_url: str) -> list[str]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        text = anchor.get_text(" ", strip=True).lower()
        combined = " ".join(
            str(value).lower()
            for value in [
                href,
                text,
                anchor.get("aria-label", ""),
                anchor.get("title", ""),
                anchor.get("class", ""),
            ]
        )
        if "pdf" not in combined and "full text" not in combined:
            continue
        candidate = urljoin(base_url, href)
        if _looks_like_pdf_url(candidate) or "pdf" in combined:
            links.append(candidate)
    return _deduplicate_urls(links)


def _unpaywall_candidates(doi: str, unpaywall_email: str | None, timeout: int) -> list[tuple[str, str]]:
    if not unpaywall_email:
        return []
    url = f"https://api.unpaywall.org/v2/{quote(_strip_doi_url(doi), safe='')}"
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
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(_strip_doi_url(doi), safe='')}"
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
            params={"search_query": f'ti:"{title[:180]}"', "start": 0, "max_results": 3},
            timeout=timeout,
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    candidates: list[tuple[str, str]] = []
    for entry in root.findall(".//atom:entry", ns):
        entry_title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        if not _safe_title_match(title, entry_title):
            continue
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf" and link.attrib.get("href"):
                candidates.append(("arxiv", link.attrib["href"]))
        if candidates:
            break
    return candidates


def _rank_candidate_urls(candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen_urls: set[str] = set()
    per_source_count: dict[str, int] = {}
    unique: list[tuple[int, int, str, str]] = []
    for order, (source, url) in enumerate(candidates):
        if not url or url in seen_urls:
            continue
        if per_source_count.get(source, 0) >= MAX_CANDIDATES_PER_SOURCE:
            continue
        seen_urls.add(url)
        per_source_count[source] = per_source_count.get(source, 0) + 1
        unique.append((SOURCE_PRIORITY.get(source, 99), order, source, url))
    unique.sort(key=lambda item: (item[0], item[1]))
    return [(source, url) for _, _, source, url in unique[:MAX_DOWNLOAD_CANDIDATES]]

def _looks_like_pdf_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.endswith(".pdf") or "/pdf" in lowered or "pdf" in lowered


def _safe_title_match(source_title: str, candidate_title: str) -> bool:
    source = _normalize_title(source_title)
    candidate = _normalize_title(candidate_title)
    if not source or not candidate:
        return False
    if source == candidate:
        return True
    return SequenceMatcher(None, source, candidate).ratio() >= TITLE_MATCH_THRESHOLD


def _normalize_title(title: str) -> str:
    text = title.lower()
    text = re.sub(r"[^a-z0-9一-鿿]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_wos_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "webofscience" in host or "webofknowledge" in host or "clarivate" in host


def _strip_doi_url(doi: str) -> str:
    value = doi.strip()
    lowered = value.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if lowered.startswith(prefix):
            return value[len(prefix):].strip()
    return value


def _deduplicate_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


def _classify_download_error(exc: Exception) -> str:
    if isinstance(exc, requests.Timeout):
        return f"下载超时：{exc}"
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        if status in {401, 402, 403}:
            return f"需要订阅或付费：HTTP {status}"
        if status == 404:
            return "全文链接失效：HTTP 404"
        return f"网络/HTTP 错误：HTTP {status or 'unknown'}"
    message = str(exc)
    if "不是 PDF" in message:
        lowered = message.lower()
        if any(marker in lowered for marker in ["html", "text/html", "login", "subscribe", "purchase"]):
            return f"需要订阅或付费，或当前链接不是 PDF：{message}"
        return f"下载结果不是 PDF：{message}"
    if isinstance(exc, requests.RequestException):
        return f"网络请求失败：{exc}"
    return message or type(exc).__name__


def _failure_reason(errors: list[str]) -> str:
    if not errors:
        return "未找到开放获取全文链接；可能需要订阅/付费或手动上传 PDF"
    if any("全文下载超时" in error or "下载超时" in error for error in errors):
        return "全文下载超时；可增大全文下载超时秒数后重试"
    if any("需要订阅或付费" in error for error in errors):
        return "需要订阅或付费，当前环境未能直接下载 PDF；可使用学校 VPN/机构登录后重试，或手动上传 PDF"
    return "；".join(errors)


def _total_budget_seconds(timeout: int) -> int:
    return max(15, min(max(timeout, 1) * 6, 90))


def _remaining_timeout(deadline: float | None, configured_timeout: int) -> int:
    if deadline is None:
        return max(1, configured_timeout)
    remaining = int(deadline - time.monotonic())
    return max(1, min(max(1, configured_timeout), remaining))


def _deadline_expired(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline
