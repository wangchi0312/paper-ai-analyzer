from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.ingestion.wos_parser import _extract_wos_url


DEFAULT_BROWSER_PROFILE_DIR = "data/browser_profiles/wos"


def fetch_wos_alert_with_browser(
    url: str,
    source_email_id: str | None = None,
    timeout_ms: int = 30000,
    headless: bool = False,
    max_pages: int = 20,
    browser_profile_dir: str | None = DEFAULT_BROWSER_PROFILE_DIR,
) -> list[FetchedPaper]:
    _prepare_playwright_runtime()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("缺少 playwright，请先安装 playwright 并执行 playwright install chromium。") from exc

    try:
        with sync_playwright() as playwright:
            if browser_profile_dir:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(Path(browser_profile_dir)),
                    headless=headless,
                )
                try:
                    page = context.new_page()
                    page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                    _wait_for_wos_records(page, timeout_ms=timeout_ms)
                    papers = _collect_wos_records_across_pages(
                        page,
                        source_email_id=source_email_id,
                        timeout_ms=timeout_ms,
                        max_pages=max_pages,
                    )
                finally:
                    context.close()
            else:
                browser = playwright.chromium.launch(headless=headless)
                try:
                    page = browser.new_page()
                    page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                    _wait_for_wos_records(page, timeout_ms=timeout_ms)
                    papers = _collect_wos_records_across_pages(
                        page,
                        source_email_id=source_email_id,
                        timeout_ms=timeout_ms,
                        max_pages=max_pages,
                    )
                finally:
                    browser.close()
    except NotImplementedError as exc:
        raise RuntimeError(
            "Playwright 启动浏览器子进程失败。若在 Streamlit/Windows 中运行，"
            "请重启前端进程后再试；仍失败时改用命令行运行 fetch-papers 验证浏览器模式。"
        ) from exc

    return papers


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


def _collect_wos_records_across_pages(
    page,
    source_email_id: str | None,
    timeout_ms: int,
    max_pages: int,
) -> list[FetchedPaper]:
    papers: list[FetchedPaper] = []
    for _ in range(max_pages):
        _scroll_to_load_records(page)
        papers.extend(parse_wos_result_page(page.content(), source_email_id=source_email_id))
        if not _go_to_next_results_page(page, timeout_ms=timeout_ms):
            break
        _wait_for_wos_records(page, timeout_ms=timeout_ms)
    return _deduplicate_by_title(papers)


def _scroll_to_load_records(page, max_scrolls: int = 10, settle_ms: int = 800) -> None:
    last_count = -1
    stable_rounds = 0
    for _ in range(max_scrolls):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(settle_ms)
            count = _record_link_count(page)
        except Exception:
            return
        if count == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_count = count
        if stable_rounds >= 2:
            return


def _record_link_count(page) -> int:
    selector = "a[href*='FullRecord'], a[href*='full-record'], a[href*='WOS:'], [data-ta='summary-record-title-link']"
    try:
        return page.locator(selector).count()
    except Exception:
        return 0


def _go_to_next_results_page(page, timeout_ms: int) -> bool:
    selectors = [
        "button[aria-label*='Next']:not([disabled])",
        "a[aria-label*='Next']",
        "button[title*='Next']:not([disabled])",
        "a[title*='Next']",
        "button:has-text('Next')",
        "a:has-text('Next')",
        "button:has-text('下一页')",
        "a:has-text('下一页')",
    ]
    current_url = getattr(page, "url", "")
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 5)
            for index in range(count):
                item = locator.nth(index)
                if not item.is_visible() or not item.is_enabled():
                    continue
                item.click(timeout=min(timeout_ms, 5000))
                _wait_after_navigation_or_update(page, current_url=current_url, timeout_ms=timeout_ms)
                return True
        except Exception:
            continue
    return False


def _wait_after_navigation_or_update(page, current_url: str, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
    except Exception:
        pass
    try:
        page.wait_for_timeout(1200)
    except Exception:
        pass
    if getattr(page, "url", "") == current_url:
        return


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
    current_url = _summarize_page_url(getattr(page, "url", ""))
    raise RuntimeError(f"页面已打开但未发现 WoS 记录链接；title={title!r}；url={current_url!r}")


def _summarize_page_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    return f"{parsed.netloc}{parsed.path}"


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
