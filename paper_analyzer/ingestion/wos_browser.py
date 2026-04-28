from bs4 import BeautifulSoup

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.ingestion.wos_parser import _extract_wos_url


def fetch_wos_alert_with_browser(
    url: str,
    source_email_id: str | None = None,
    timeout_ms: int = 30000,
    headless: bool = False,
) -> list[FetchedPaper]:
    _prepare_playwright_runtime()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("缺少 playwright，请先安装 playwright 并执行 playwright install chromium。") from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                _wait_for_wos_records(page, timeout_ms=timeout_ms)
                html = page.content()
            finally:
                browser.close()
    except NotImplementedError as exc:
        raise RuntimeError(
            "Playwright 启动浏览器子进程失败。若在 Streamlit/Windows 中运行，"
            "请重启前端进程后再试；仍失败时改用命令行运行 fetch-papers 验证浏览器模式。"
        ) from exc

    return parse_wos_result_page(html, source_email_id=source_email_id)


def _prepare_playwright_runtime() -> None:
    try:
        import asyncio
        import sys
    except Exception:
        return

    policy_class = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if sys.platform != "win32" or policy_class is None:
        return
    try:
        if not isinstance(asyncio.get_event_loop_policy(), policy_class):
            asyncio.set_event_loop_policy(policy_class())
    except Exception:
        return


def parse_wos_result_page(html: str, source_email_id: str | None = None) -> list[FetchedPaper]:
    soup = BeautifulSoup(html, "html.parser")
    papers: list[FetchedPaper] = []

    for link in soup.find_all("a", href=True):
        title = link.get_text(" ", strip=True)
        if not _is_probable_title(title):
            continue
        href = link.get("href", "")
        if not _is_wos_record_href(href):
            continue
        papers.append(
            FetchedPaper(
                title=title,
                abstract="",
                link=_normalize_wos_href(href),
                source_email_id=source_email_id,
                fetch_method="wos_browser",
            )
        )

    return _deduplicate_by_title(papers)


def _wait_for_wos_records(page, timeout_ms: int) -> None:
    selectors = [
        "a[href*='FullRecord']",
        "a[href*='full-record']",
        "a[href*='WOS:']",
        "[data-ta='summary-record-title-link']",
    ]
    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=timeout_ms // len(selectors))
            return
        except Exception:
            continue
    title = _safe_page_title(page)
    current_url = getattr(page, "url", "")
    raise RuntimeError(f"页面已打开但未发现 WoS 记录链接；title={title!r}；url={current_url!r}")


def _safe_page_title(page) -> str:
    try:
        return page.title()
    except Exception:
        return ""


def _is_probable_title(text: str) -> bool:
    if len(text) < 20:
        return False
    lowered = text.lower()
    bad = {"view record", "full text", "export", "save", "citation", "references"}
    return not any(item in lowered for item in bad)


def _is_wos_record_href(href: str) -> bool:
    lowered = href.lower()
    return "fullrecord" in lowered or "full-record" in lowered or "keyut=wos" in lowered or "wos:" in lowered


def _normalize_wos_href(href: str) -> str:
    extracted = _extract_wos_url(href)
    if extracted:
        return extracted
    if href.startswith("http"):
        return href
    return f"https://www.webofscience.com{href}"


def _deduplicate_by_title(papers: list[FetchedPaper]) -> list[FetchedPaper]:
    seen: set[str] = set()
    unique: list[FetchedPaper] = []
    for paper in papers:
        key = " ".join(paper.title.lower().split())
        if key in seen:
            continue
        seen.add(key)
        unique.append(paper)
    return unique
