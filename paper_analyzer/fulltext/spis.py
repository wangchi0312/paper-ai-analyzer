from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
import time
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.downloader import safe_pdf_name
from paper_analyzer.fulltext.source import FullTextResult
from paper_analyzer.ingestion.email_reader import PdfEmailAttachment, fetch_pdf_attachments_since
from paper_analyzer.utils.config import EmailConfig, FullTextConfig, load_email_config, load_full_text_config
from paper_analyzer.utils.logger import get_logger
from paper_analyzer.utils.text import normalize_title

logger = get_logger(__name__)


@dataclass
class SpisSearchResult:
    title: str
    url: str
    doi: str | None = None
    download_url: str | None = None
    article_index: int | None = None


def resolve_via_spis(
    paper: FetchedPaper,
    output_dir: Path,
    index: int,
    config: FullTextConfig | None = None,
    email_config: EmailConfig | None = None,
) -> FullTextResult:
    config = config or load_full_text_config()
    output_path = output_dir / safe_pdf_name(paper.title, index)
    if not _spis_queries(paper):
        return FullTextResult(success=False, source="spis_not_found", reason="SPIS search skipped: missing DOI and title")

    logger.info("SPIS search: %s", " | ".join(_spis_queries(paper)))
    direct_result = download_spis_direct_pdf(
        paper=paper,
        output_path=output_path,
        base_url=config.spis_base_url,
        title_match_threshold=config.spis_title_match_threshold,
    )
    if direct_result.success:
        return direct_result

    email_config = email_config or load_email_config()
    submitted_at = datetime.now(timezone.utc)
    try:
        detail_url, submit_status = submit_spis_request(
            paper=paper,
            recipient_email=email_config.address,
            base_url=config.spis_base_url,
            title_match_threshold=config.spis_title_match_threshold,
        )
    except Exception as exc:
        return FullTextResult(success=False, source="spis_submit_failed", reason=f"SPIS submit failed: {exc}")

    if submit_status == "not_found":
        return FullTextResult(success=False, source="spis_not_found", reason="SPIS did not find a safe matching result")
    if submit_status not in {"submitted", "already_requested"}:
        return FullTextResult(success=False, source="spis_submit_failed", reason=f"SPIS submit status: {submit_status}")

    logger.info("SPIS request %s, waiting for PDF email: %s", submit_status, detail_url or "")
    wait_seconds = max(0, config.spis_wait_minutes * 60)
    poll_seconds = max(5, config.spis_poll_interval_seconds)
    attachment = wait_for_spis_pdf_email(
        paper=paper,
        submitted_after=submitted_at,
        timeout_seconds=wait_seconds,
        poll_interval_seconds=poll_seconds,
        email_config=email_config,
    )
    if attachment is None:
        return FullTextResult(
            success=False,
            source="spis_email_timeout",
            url=detail_url,
            reason="SPIS request submitted but no matching PDF email arrived before timeout",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(attachment.payload)
    return FullTextResult(success=True, path=str(output_path), source="spis_email", url=detail_url)


def build_spis_search_url(query: str, base_url: str = "https://spis.hnlat.com/") -> str:
    return urljoin(_base_with_slash(base_url), f"scholar/list?val={quote(query.strip(), safe='')}")


def parse_spis_search_results(html: str, base_url: str = "https://spis.hnlat.com/") -> list[SpisSearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SpisSearchResult] = []
    seen_urls: set[str] = set()
    for article_index, article in enumerate(soup.select("article")):
        title_el = article.select_one(".d-t[title], .d-t")
        if title_el is None:
            continue
        title = _clean_spis_title(title_el.get("title") or title_el.get_text(" ", strip=True))
        if not title:
            continue
        source_anchor = article.select_one("a.link-site_icon[href]")
        detail_or_source_url = urljoin(_base_with_slash(base_url), source_anchor.get("href")) if source_anchor else ""
        download_anchor = article.select_one("a[href*='downloadLog']")
        download_url = urljoin(_base_with_slash(base_url), download_anchor.get("href")) if download_anchor else None
        result_key = detail_or_source_url or download_url or title
        if result_key in seen_urls:
            continue
        seen_urls.add(result_key)
        results.append(
            SpisSearchResult(
                title=title,
                url=detail_or_source_url,
                doi=_extract_doi(article.get_text(" ", strip=True)),
                download_url=download_url,
                article_index=article_index,
            )
        )

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href") or ""
        if "/scholar/detail/" not in href:
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if not title:
            continue
        url = urljoin(_base_with_slash(base_url), href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        container = anchor.find_parent(["li", "div", "article", "section"]) or anchor.parent
        text = container.get_text(" ", strip=True) if container else title
        results.append(SpisSearchResult(title=title, url=url, doi=_extract_doi(text)))
    return results


def select_spis_result(
    paper: FetchedPaper,
    results: list[SpisSearchResult],
    title_match_threshold: float = 0.82,
) -> SpisSearchResult | None:
    if not results:
        return None
    paper_doi = _normalize_doi(paper.doi)
    if paper_doi:
        for result in results:
            if _normalize_doi(result.doi) == paper_doi:
                return result
    if len(results) == 1:
        return results[0]
    scored = [(_title_similarity(paper.title, result.title), result) for result in results]
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] >= title_match_threshold:
        return scored[0][1]
    return None


def submit_spis_request(
    paper: FetchedPaper,
    recipient_email: str,
    base_url: str = "https://spis.hnlat.com/",
    title_match_threshold: float = 0.82,
) -> tuple[str | None, str]:
    try:
        from paper_analyzer.ingestion.wos_browser import _prepare_playwright_runtime
        from playwright.sync_api import sync_playwright

        _prepare_playwright_runtime()
    except Exception as exc:
        raise RuntimeError(f"Playwright is unavailable: {exc}") from exc

    queries = _spis_queries(paper)
    if not queries:
        return None, "not_found"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            for query in queries:
                page.goto(build_spis_search_url(query, base_url), wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1500)
                results = parse_spis_search_results(page.content(), base_url=base_url)
                selected = select_spis_result(paper, results, title_match_threshold=title_match_threshold)
                if selected is None:
                    continue
                logger.info("SPIS delivery: %s", selected.title)
                status = submit_spis_result_delivery_form(page, selected, recipient_email)
                if status != "not_found":
                    return selected.url, status
                if selected.url:
                    logger.info("SPIS detail fallback: %s", selected.url)
                    page.goto(selected.url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1500)
                    status = submit_spis_detail_form(page, recipient_email)
                    return selected.url, status
            return None, "not_found"
        finally:
            browser.close()


def download_spis_direct_pdf(
    paper: FetchedPaper,
    output_path: Path,
    base_url: str = "https://spis.hnlat.com/",
    title_match_threshold: float = 0.82,
    timeout: int = 60,
) -> FullTextResult:
    try:
        from paper_analyzer.ingestion.wos_browser import _prepare_playwright_runtime
        from playwright.sync_api import sync_playwright

        _prepare_playwright_runtime()
    except Exception as exc:
        return FullTextResult(success=False, source="spis_direct_failed", reason=f"Playwright is unavailable: {exc}")

    queries = _spis_queries(paper)
    if not queries:
        return FullTextResult(success=False, source="spis_not_found", reason="SPIS search skipped: missing DOI and title")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True, ignore_https_errors=True)
        page = context.new_page()
        try:
            found_match = False
            last_url = None
            for query in queries:
                page.goto(build_spis_search_url(query, base_url), wait_until="domcontentloaded", timeout=timeout * 1000)
                page.wait_for_timeout(1500)
                results = parse_spis_search_results(page.content(), base_url=base_url)
                selected = select_spis_result(paper, results, title_match_threshold=title_match_threshold)
                if selected is None:
                    continue
                found_match = True
                if not selected.download_url:
                    last_url = selected.url
                    continue

                target_url = _extract_download_target(selected.download_url) or selected.download_url
                last_url = target_url
                saved = _download_pdf_with_requests_stream(target_url, output_path, total_timeout=max(timeout, 600))
                if saved:
                    return FullTextResult(success=True, path=str(output_path), source="spis_direct", url=target_url)

                saved = _download_pdf_with_playwright_request(context, target_url, output_path, timeout=timeout)
                if saved:
                    return FullTextResult(success=True, path=str(output_path), source="spis_direct", url=target_url)

                saved = _download_pdf_by_browser_navigation(page, target_url, output_path, timeout=timeout)
                if saved:
                    return FullTextResult(success=True, path=str(output_path), source="spis_direct", url=target_url)

            if not found_match:
                return FullTextResult(success=False, source="spis_not_found", reason="SPIS did not find a safe matching result")
            return FullTextResult(success=False, source="spis_no_direct_download", url=last_url, reason="SPIS direct download unavailable or did not return a PDF")
        except Exception as exc:
            return FullTextResult(success=False, source="spis_direct_failed", reason=f"SPIS direct download failed: {exc}")
        finally:
            browser.close()


def submit_spis_detail_form(page, recipient_email: str) -> str:
    body_text = _page_body_text(page).lower()
    if "已求助" in body_text or "已提交" in body_text:
        return "already_requested"

    email_input = page.locator("input.email-input, input[placeholder*='邮箱'], input[type='email']").last
    if email_input.count() == 0:
        return "submit_failed"
    email_input.fill(recipient_email)

    checkbox = page.locator("input.hidden-checkbox[type='checkbox'], input[type='checkbox']").first
    if checkbox.count() > 0:
        try:
            checkbox.check(force=True)
        except Exception:
            checkbox.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); }")

    button = page.locator("button.modal-ok, button.doc-delivery-btn, button:has-text('确定'), button:has-text('确认')").last
    if button.count() == 0:
        return "submit_failed"
    button.click(timeout=15000)
    page.wait_for_timeout(2500)

    text = _page_body_text(page).lower()
    if any(marker in text for marker in ("已提交", "提交成功", "请求成功", "求助成功")):
        return "submitted"
    if any(marker in text for marker in ("已求助", "请勿重复", "重复提交")):
        return "already_requested"
    return "submitted"


def submit_spis_result_delivery_form(page, selected: SpisSearchResult, recipient_email: str) -> str:
    article = _locate_spis_article(page, selected)
    if article is None:
        return "not_found"
    delivery = article.locator(".action-button.delivery").first
    if delivery.count() == 0:
        return "not_found"
    delivery.click(timeout=15000)
    page.wait_for_timeout(1200)
    return submit_spis_detail_form(page, recipient_email)


def wait_for_spis_pdf_email(
    paper: FetchedPaper,
    submitted_after: datetime,
    timeout_seconds: int,
    poll_interval_seconds: int,
    email_config: EmailConfig | None = None,
) -> PdfEmailAttachment | None:
    deadline = time.monotonic() + max(0, timeout_seconds)
    while True:
        attachments = fetch_pdf_attachments_since(submitted_after, config=email_config)
        logger.info("SPIS email poll found %d PDF attachment candidates", len(attachments))
        match = select_pdf_attachment_for_paper(paper, attachments)
        if match is not None:
            return match
        if time.monotonic() >= deadline:
            return None
        time.sleep(min(max(5, poll_interval_seconds), max(0.0, deadline - time.monotonic())))


def select_pdf_attachment_for_paper(
    paper: FetchedPaper,
    attachments: list[PdfEmailAttachment],
) -> PdfEmailAttachment | None:
    if not attachments:
        return None
    doi = _normalize_doi(paper.doi)
    if doi:
        for attachment in attachments:
            haystack = _attachment_haystack(attachment)
            if doi in haystack:
                return attachment
    title_tokens = _title_keywords(paper.title)
    if title_tokens:
        for attachment in attachments:
            haystack = _attachment_haystack(attachment)
            hits = sum(1 for token in title_tokens if token in haystack)
            if hits >= min(3, len(title_tokens)):
                return attachment
    if len(attachments) == 1:
        return attachments[0]
    return None


def _spis_query(paper: FetchedPaper) -> str:
    return (_normalize_doi(paper.doi) or paper.title or "").strip()


def _spis_queries(paper: FetchedPaper) -> list[str]:
    values = [_normalize_doi(paper.doi), (paper.title or "").strip()]
    queries: list[str] = []
    for value in values:
        if value and value not in queries:
            queries.append(value)
    return queries


def _locate_spis_article(page, selected: SpisSearchResult):
    articles = page.locator("article")
    if selected.article_index is not None and selected.article_index < articles.count():
        return articles.nth(selected.article_index)
    wanted = normalize_title(selected.title)
    for index in range(articles.count()):
        article = articles.nth(index)
        try:
            title_el = article.locator(".d-t").first
            title = title_el.get_attribute("title") or title_el.inner_text(timeout=1000)
        except Exception:
            title = ""
        if wanted and normalize_title(_clean_spis_title(title)) == wanted:
            return article
    return None


def _download_pdf_with_playwright_request(context, url: str, output_path: Path, timeout: int) -> bool:
    try:
        response = context.request.get(url, timeout=timeout * 1000)
        if not response.ok:
            return False
        body = response.body()
        content_type = (response.headers.get("content-type") or "").lower()
        if not _looks_like_pdf(body, content_type):
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(body)
        return True
    except Exception:
        return False


def _download_pdf_by_browser_navigation(page, url: str, output_path: Path, timeout: int) -> bool:
    try:
        response = page.goto(url, wait_until="commit", timeout=timeout * 1000)
        page.wait_for_timeout(1500)
        if response is None:
            return False
        body = response.body()
        content_type = (response.headers.get("content-type") or "").lower()
        if not _looks_like_pdf(body, content_type):
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(body)
        return True
    except Exception:
        return False


def _looks_like_pdf(body: bytes, content_type: str) -> bool:
    return body[:1024].lstrip().startswith(b"%PDF")


def _download_pdf_with_requests_stream(url: str, output_path: Path, total_timeout: int = 600) -> bool:
    tmp_path = output_path.with_suffix(output_path.suffix + ".part")
    deadline = time.monotonic() + max(30, total_timeout)
    try:
        with requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/pdf,*/*",
            },
            timeout=(15, 45),
            allow_redirects=True,
            stream=True,
        ) as response:
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            first_bytes = b""
            with tmp_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if time.monotonic() > deadline:
                        return False
                    if not chunk:
                        continue
                    if len(first_bytes) < 1024:
                        first_bytes += chunk
                    fh.write(chunk)
            if not _looks_like_pdf(first_bytes, response.headers.get("content-type", "")):
                return False
            tmp_path.replace(output_path)
            return True
    except Exception:
        return False
    finally:
        if tmp_path.exists() and not output_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def _extract_download_target(download_url: str) -> str | None:
    parsed = urlparse(download_url)
    params = parse_qs(parsed.query)
    values = params.get("link") or params.get("url")
    if not values:
        return None
    return unquote(values[0]).strip() or None


def _clean_spis_title(title: str) -> str:
    import re

    value = " ".join(BeautifulSoup(title, "html.parser").get_text(" ", strip=True).split())
    value = re.sub(r"^\s*\d+\s*[、.]\s*", "", value)
    return value.strip()


def _page_body_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=3000)
    except Exception:
        return ""


def _base_with_slash(base_url: str) -> str:
    return base_url if base_url.endswith("/") else base_url + "/"


def _extract_doi(text: str) -> str | None:
    import re

    match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, flags=re.IGNORECASE)
    return match.group(0) if match else None


def _normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    value = doi.strip()
    lowered = value.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if lowered.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return value.lower()


def _title_similarity(source_title: str, candidate_title: str) -> float:
    source = normalize_title(source_title)
    candidate = normalize_title(candidate_title)
    if not source or not candidate:
        return 0.0
    if source == candidate:
        return 1.0
    return SequenceMatcher(None, source, candidate).ratio()


def _title_keywords(title: str) -> list[str]:
    normalized = normalize_title(title)
    return [token for token in normalized.split() if len(token) >= 4][:8]


def _attachment_haystack(attachment: PdfEmailAttachment) -> str:
    return " ".join(
        [
            attachment.subject,
            attachment.sender,
            attachment.filename,
            attachment.body_text,
        ]
    ).lower()
