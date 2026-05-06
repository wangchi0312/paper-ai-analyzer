from difflib import SequenceMatcher
import os
from pathlib import Path
import time
from urllib.parse import quote, urljoin, urlparse
import xml.etree.ElementTree as ET

import requests

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.downloader import download_pdf, safe_pdf_name
from paper_analyzer.utils.text import normalize_title
from paper_analyzer.fulltext.manual import ManualPdfIndex, build_manual_pdf_index, resolve_manual_pdf
from paper_analyzer.fulltext.source import FullTextResult
from paper_analyzer.fulltext.spis import resolve_via_spis
from paper_analyzer.utils.config import load_full_text_config


MAX_CANDIDATES_PER_SOURCE = 1
MAX_DOWNLOAD_CANDIDATES = 4
TITLE_MATCH_THRESHOLD = 0.88
SOURCE_PRIORITY = {
    "publisher": 0,
    "crossref_tdm": 1,
    "unpaywall": 2,
    "semantic_scholar": 3,
    "openalex": 4,
    "arxiv": 5,
    "publisher_page": 6,
}
DEFAULT_BROWSER_PROFILE_DIR = "data/browser_profiles/wos"
PUBLISHER_BROWSER_PROFILE_DIR_ENV = "PUBLISHER_BROWSER_PROFILE_DIR"
PUBLISHER_BROWSER_CHANNEL_ENV = "PUBLISHER_BROWSER_CHANNEL"
DEFAULT_MANUAL_VERIFICATION_WAIT_SECONDS = 300
DEFAULT_PUBLISHER_REQUEST_INTERVAL_SECONDS = 10
DEFAULT_VERIFICATION_LOOP_SECONDS = 60
_LAST_PUBLISHER_ACCESS_AT: float | None = None


def resolve_full_text(
    paper: FetchedPaper,
    output_dir: Path,
    index: int,
    unpaywall_email: str | None = None,
    timeout: int = 30,
    manual_pdf_dir: str | None = None,
    manual_pdf_index: ManualPdfIndex | FullTextResult | None = None,
    enable_api_fallback: bool = False,
    full_text_source: str | None = None,
    manual_verification_wait_seconds: int = DEFAULT_MANUAL_VERIFICATION_WAIT_SECONDS,
    publisher_request_interval_seconds: int = DEFAULT_PUBLISHER_REQUEST_INTERVAL_SECONDS,
) -> FullTextResult:
    output_path = output_dir / safe_pdf_name(paper.title, index)
    errors: list[str] = []
    deadline = time.monotonic() + _total_budget_seconds(timeout)

    manual_result = resolve_manual_pdf(paper, manual_pdf_dir, output_dir=output_dir, index=index, manual_pdf_index=manual_pdf_index)
    if manual_result and manual_result.success:
        return manual_result
    if manual_result and manual_result.reason:
        errors.append(f"manual_upload: {manual_result.reason}")

    configured_source = (full_text_source or load_full_text_config().source or "manual").lower()
    if configured_source in {"spis", "auto"}:
        spis_result = resolve_via_spis(paper, output_dir=output_dir, index=index)
        if spis_result.success:
            return spis_result
        errors.append(f"{spis_result.source or 'spis'}: {spis_result.reason or 'failed'}")
        if configured_source == "spis" and not enable_api_fallback:
            return spis_result

    # 浏览器完整链路：只要有DOI/链接/摘要页URL之一就尝试
    if configured_source in {"publisher", "auto"} and (paper.publisher_link or paper.wos_summary_url or paper.link or paper.doi) and not _deadline_expired(deadline):
        browser_result = _download_pdf_via_publisher_chain(
            paper, output_path,
            timeout=_remaining_timeout(deadline, timeout),
            manual_verification_wait_seconds=manual_verification_wait_seconds,
            publisher_request_interval_seconds=publisher_request_interval_seconds,
        )
        if browser_result is not None:
            if browser_result.success:
                return browser_result
            errors.append(f"publisher_chain: {browser_result.reason}")

    if not enable_api_fallback:
        reason = _failure_reason(errors)
        if not errors:
            reason = "未能通过 WoS/出版商浏览器链路获取 PDF；开放获取/API 兜底默认关闭"
        return FullTextResult(success=False, reason=reason)

    # 显式开启后再使用 API 来源回退（OpenAlex / Unpaywall / Semantic Scholar / arXiv 等）
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

    # 鏂板锛氫紭鍏堝皾璇曚粠 publisher_link 涓嬭浇 PDF
    if getattr(paper, "publisher_link", None):
        candidates.append(("publisher_page", paper.publisher_link))

    if paper.link and _looks_like_pdf_url(paper.link):
        candidates.append(("publisher", paper.link))

    if paper.doi:
        if not _deadline_expired(deadline):
            candidates.extend(_crossref_tdm_candidates(paper.doi, timeout=_remaining_timeout(deadline, timeout)))
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


def _crossref_tdm_candidates(doi: str, timeout: int) -> list[tuple[str, str]]:
    url = f"https://api.crossref.org/works/{quote(_strip_doi_url(doi), safe='')}"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        links = response.json().get("message", {}).get("link", []) or []
    except Exception:
        return []

    candidates: list[tuple[str, str]] = []
    for item in links:
        content_type = str(item.get("content-type") or "").lower()
        intended = str(item.get("intended-application") or "").lower()
        link_url = item.get("URL") or item.get("url") or ""
        if not link_url:
            continue
        if "pdf" not in content_type and not _looks_like_pdf_url(link_url):
            continue
        if intended and "text-mining" not in intended and "similarity-checking" not in intended:
            continue
        candidates.append(("crossref_tdm", link_url))
    return candidates


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

def _download_pdf_via_publisher_chain(
    paper: FetchedPaper,
    output_path: Path,
    timeout: int = 30,
    manual_verification_wait_seconds: int = DEFAULT_MANUAL_VERIFICATION_WAIT_SECONDS,
    publisher_request_interval_seconds: int = DEFAULT_PUBLISHER_REQUEST_INTERVAL_SECONDS,
) -> FullTextResult | None:
    """WoS Full Record → 期刊页 → View PDF → 下载 PDF 的完整浏览器链路。"""
    publisher_url = paper.publisher_link
    wos_full_record_url = paper.link
    doi = paper.doi
    if not publisher_url and not wos_full_record_url and not paper.wos_summary_url and not doi:
        return None
    try:
        from paper_analyzer.ingestion.wos_browser import (
            _prepare_playwright_runtime,
            _extract_doi_from_full_record,
            _extract_publisher_link_from_full_record,
            _extract_dest_url_from_gateway,
        )
        from playwright.sync_api import sync_playwright
        _prepare_playwright_runtime()
    except ImportError:
        return None
    except Exception:
        return None

    pw = None
    browser = None
    try:
        import random as _random
        pw = sync_playwright().start()
        browser = _launch_persistent_publisher_context(pw)
        page = browser.new_page()

        # 随机延迟 2-5 秒，模拟人类行为
        page.wait_for_timeout(_random.randint(2000, 5000))

        # 步骤0: 如果没有 publisher_link，先进入已通过兴趣筛选的单篇 Full Record 查找
        if not publisher_url and wos_full_record_url:
            _respect_publisher_request_interval(publisher_request_interval_seconds)
            page.goto(wos_full_record_url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(2500)
            if _detect_captcha_on_page(page) and not _wait_for_manual_verification(
                page,
                wait_seconds=manual_verification_wait_seconds,
            ):
                return FullTextResult(
                    success=False,
                    reason="WoS Full Record 页面触发验证，人工验证等待超时",
                )
            publisher_url = _extract_publisher_link_from_full_record(page)
            if not doi:
                doi = _extract_doi_from_full_record(page)
            page.wait_for_timeout(_random.randint(1000, 2500))

        # 步骤0 兜底: 如果没有 publisher_link，从 WoS 摘要页找
        if not publisher_url and paper.wos_summary_url and paper.title:
            _respect_publisher_request_interval(publisher_request_interval_seconds)
            page.goto(paper.wos_summary_url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(3000)
            if _detect_captcha_on_page(page) and not _wait_for_manual_verification(
                page,
                wait_seconds=manual_verification_wait_seconds,
            ):
                return FullTextResult(
                    success=False,
                    reason="WoS 摘要页触发验证，人工验证等待超时",
                )
            publisher_url = _find_publisher_link_on_summary_page(
                page, paper.title, timeout=timeout
            )
            page.wait_for_timeout(_random.randint(1000, 3000))

        if not publisher_url and doi:
            publisher_url = f"https://doi.org/{doi}"

        if not publisher_url:
            return FullTextResult(
                success=False,
                reason="未能获取出版商链接：摘要页无链接且无 DOI",
            )

        # 步骤1: 访问出版商文章页
        page.wait_for_timeout(_random.randint(1000, 3000))
        _respect_publisher_request_interval(publisher_request_interval_seconds)
        page.goto(publisher_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        page.wait_for_timeout(_random.randint(3000, 6000))

        if _detect_captcha_on_page(page) and not _wait_for_manual_verification(
            page,
            wait_seconds=manual_verification_wait_seconds,
        ):
            return FullTextResult(
                success=False,
                reason="出版商页面触发验证码，人工验证等待超时",
            )

        # 步骤2: 点击 View PDF（按钮可能是a/button/span）
        page.wait_for_timeout(_random.randint(1000, 3000))
        view_pdf = page.locator("a:has-text('View PDF'), button:has-text('View PDF'), span:has-text('View PDF'), a:has-text('PDF'), button:has-text('PDF')").first
        if view_pdf.count() == 0:
            return FullTextResult(
                success=False,
                reason="出版商页面未找到 View PDF 按钮",
            )

        # 点击可能在新标签页打开PDF，也可能在当前页导航
        pdf_page = None
        try:
            page.wait_for_timeout(_random.randint(500, 2000))
            with page.context.expect_page(timeout=min(timeout * 1000, 8000)) as new_page_info:
                view_pdf.click(timeout=min(timeout * 1000, 10000))
            pdf_page = new_page_info.value
            pdf_page.wait_for_load_state("domcontentloaded", timeout=min(timeout * 1000, 15000))
            pdf_page.wait_for_timeout(3000)
            if _detect_captcha_on_page(pdf_page) and not _wait_for_manual_verification(
                pdf_page,
                wait_seconds=manual_verification_wait_seconds,
            ):
                return FullTextResult(
                    success=False,
                    reason="PDF 预览页触发验证码，人工验证等待超时",
                )
        except Exception:
            # 没有新页面，可能是在当前页内嵌PDF或直接下载
            page.wait_for_timeout(_random.randint(3000, 6000))

        # 步骤3: 在 PDF 预览页或当前页获取 PDF
        page_to_check = pdf_page if pdf_page is not None else page

        pdf_url = _extract_pdf_url_from_preview(page_to_check)
        if pdf_url:
            response = page_to_check.goto(pdf_url, wait_until="commit", timeout=timeout * 1000)
            if response is not None:
                body = response.body()
                if b"%PDF" in body[:1024]:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(body)
                    return FullTextResult(
                        success=True, path=str(output_path),
                        source="publisher_chain", url=pdf_url,
                    )

        # 步骤3备选: 点击保存/下载按钮触发下载事件
        try:
            save_btn = page_to_check.locator(
                "button[aria-label='Download'], button:has-text('Save'), a:has-text('Save'), "
                "button:has-text('Download'), a:has-text('Download')"
            ).first
            if save_btn.count() > 0:
                with page_to_check.expect_download(timeout=timeout * 1000) as dl:
                    save_btn.click()
                download = dl.value
                output_path.parent.mkdir(parents=True, exist_ok=True)
                download.save_as(str(output_path))
                return FullTextResult(
                    success=True, path=str(output_path),
                    source="publisher_chain",
                )
        except Exception:
            pass

        return FullTextResult(
            success=False,
            reason="PDF 预览页未能获取 PDF 文件",
        )
    except Exception as exc:
        return FullTextResult(
            success=False,
            reason=f"浏览器下载链路失败：{exc}",
        )
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass


def _extract_pdf_url_from_preview(page) -> str | None:
    """从 Elsevier PDF 预览页提取 PDF 资源 URL。"""
    for selector in ("embed", "object", "iframe"):
        try:
            el = page.locator(selector).first
            if el.count() > 0:
                src = el.get_attribute("src")
                if src and "pdf" in src.lower():
                    if not src.startswith("http"):
                        src = urljoin(page.url, src)
                    return src
        except Exception:
            continue
        return None


def _publisher_browser_profile_dir() -> str:
    return os.getenv(PUBLISHER_BROWSER_PROFILE_DIR_ENV, "").strip() or DEFAULT_BROWSER_PROFILE_DIR


def _publisher_browser_channel_candidates() -> list[str | None]:
    configured = os.getenv(PUBLISHER_BROWSER_CHANNEL_ENV, "auto").strip().lower()
    if configured in {"", "auto"}:
        return ["chrome", "msedge", None]
    if configured in {"chrome", "msedge"}:
        return [configured, None]
    if configured in {"chromium", "none", "bundled"}:
        return [None]
    return ["chrome", "msedge", None]


def _launch_persistent_publisher_context(playwright):
    profile_dir = _publisher_browser_profile_dir()
    last_exc: Exception | None = None
    for channel in _publisher_browser_channel_candidates():
        kwargs = {
            "user_data_dir": profile_dir,
            "headless": False,
        }
        if channel is not None:
            kwargs["channel"] = channel
        try:
            return playwright.chromium.launch_persistent_context(**kwargs)
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("无法启动出版商下载浏览器")


def _find_publisher_link_on_summary_page(
    page, paper_title: str, timeout: int = 15
) -> str | None:
    """在 WoS 摘要页滚动并搜索所有 Full text at publisher 链接。"""
    from bs4 import BeautifulSoup
    from paper_analyzer.ingestion.wos_browser import _extract_dest_url_from_gateway

    # 滚动加载，让链接渲染出来
    for _ in range(8):
        page.evaluate("window.scrollBy(0, 600)")
        page.wait_for_timeout(1000)

    soup = BeautifulSoup(page.content(), "html.parser")
    pub_hrefs: list[str] = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if "Full text at publisher" in text:
            href = a.get("href", "")
            dest = _extract_dest_url_from_gateway(href) or href
            if dest and dest not in pub_hrefs:
                pub_hrefs.append(dest)

    if pub_hrefs:
        return pub_hrefs[0]

    return None


def _respect_publisher_request_interval(interval_seconds: int) -> None:
    global _LAST_PUBLISHER_ACCESS_AT
    interval = max(0, interval_seconds)
    now = time.monotonic()
    if _LAST_PUBLISHER_ACCESS_AT is not None:
        wait_seconds = interval - (now - _LAST_PUBLISHER_ACCESS_AT)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
    _LAST_PUBLISHER_ACCESS_AT = time.monotonic()


def _wait_for_manual_verification(page, wait_seconds: int) -> bool:
    """等待用户在有头浏览器中完成验证码/Cloudflare/机构验证。"""
    if wait_seconds <= 0:
        return False
    deadline = time.monotonic() + wait_seconds
    loop_started_at = time.monotonic()
    while time.monotonic() < deadline:
        try:
            page.wait_for_timeout(2000)
        except Exception:
            time.sleep(2)
        if not _detect_captcha_on_page(page):
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            return True
        if time.monotonic() - loop_started_at >= _verification_loop_seconds():
            return False
    return not _detect_captcha_on_page(page)


def _verification_loop_seconds() -> int:
    raw = os.getenv("PUBLISHER_VERIFICATION_LOOP_SECONDS", "").strip()
    if raw:
        try:
            return max(10, int(raw))
        except ValueError:
            pass
    return DEFAULT_VERIFICATION_LOOP_SECONDS


def _detect_captcha_on_page(page) -> bool:
    """检测页面是否触发验证码。"""
    text_parts: list[str] = []
    try:
        text_parts.append(page.locator("body").inner_text(timeout=3000))
    except Exception:
        pass
    try:
        text_parts.append(page.title())
    except Exception:
        pass
    body = " ".join(text_parts).lower()
    markers = (
        "captcha",
        "are you a robot",
        "verify you are human",
        "checking if the site connection is secure",
        "checking your browser",
        "just a moment",
        "cloudflare",
        "人机验证",
        "请完成安全验证",
        "验证您是真人",
    )
    if any(m in body for m in markers):
        return True
    try:
        if page.locator("iframe[src*='recaptcha']").count() > 0:
            return True
        if page.locator("iframe[src*='hcaptcha']").count() > 0:
            return True
        if page.locator("iframe[src*='challenges.cloudflare.com']").count() > 0:
            return True
        if page.locator("[class*='cf-turnstile'], [id*='cf-challenge'], [class*='cf-challenge']").count() > 0:
            return True
    except Exception:
        pass
    return False


def _deadline_expired(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _looks_like_pdf_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.endswith(".pdf") or "/pdf" in lowered or "pdf" in lowered


def _safe_title_match(source_title: str, candidate_title: str) -> bool:
    source = normalize_title(source_title)
    candidate = normalize_title(candidate_title)
    if not source or not candidate:
        return False
    if source == candidate:
        return True
    return SequenceMatcher(None, source, candidate).ratio() >= TITLE_MATCH_THRESHOLD


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
