import os
from pathlib import Path
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.ingestion.wos_parser import _extract_wos_url


DEFAULT_BROWSER_PROFILE_DIR = "data/browser_profiles/wos"
CLARIVATE_EMAIL_ENV = "CLARIVATE_EMAIL"
CLARIVATE_PASSWORD_ENV = "CLARIVATE_PASSWORD"


class WosBrowserSession:
    def __init__(
        self,
        timeout_ms: int = 30000,
        headless: bool = False,
        max_pages: int = 20,
        browser_profile_dir: str | None = DEFAULT_BROWSER_PROFILE_DIR,
        manual_login_wait_seconds: int = 0,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.headless = headless
        self.max_pages = max_pages
        self.browser_profile_dir = browser_profile_dir
        self.manual_login_wait_seconds = manual_login_wait_seconds
        self._playwright = None
        self._context = None
        self._browser = None
        self._page = None

    def __enter__(self) -> "WosBrowserSession":
        _prepare_playwright_runtime()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("缺少 playwright，请先安装 playwright 并执行 playwright install chromium。") from exc

        self._playwright = sync_playwright().start()
        try:
            if self.browser_profile_dir:
                self._context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(Path(self.browser_profile_dir)),
                    headless=self.headless,
                )
                self._page = self._context.new_page()
            else:
                self._browser = self._playwright.chromium.launch(headless=self.headless)
                self._page = self._browser.new_page()
        except NotImplementedError as exc:
            self.__exit__(type(exc), exc, exc.__traceback__)
            raise RuntimeError(
                "Playwright 启动浏览器子进程失败。若在 Streamlit/Windows 中运行，"
                "请重启前端进程后再试；仍失败时改用命令行运行 fetch-papers 验证浏览器模式。"
            ) from exc
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None

    def fetch_alert(self, url: str, source_email_id: str | None = None) -> list[FetchedPaper]:
        if self._page is None:
            raise RuntimeError("浏览器会话尚未启动。")
        _goto_wos_url(self._page, url, timeout_ms=self.timeout_ms)
        _wait_for_wos_records_or_login(
            self._page,
            timeout_ms=self.timeout_ms,
            manual_login_wait_seconds=self.manual_login_wait_seconds,
        )
        return _collect_wos_records_across_pages(
            self._page,
            source_email_id=source_email_id,
            timeout_ms=self.timeout_ms,
            max_pages=self.max_pages,
        )


def fetch_wos_alert_with_browser(
    url: str,
    source_email_id: str | None = None,
    timeout_ms: int = 30000,
    headless: bool = False,
    max_pages: int = 20,
    browser_profile_dir: str | None = DEFAULT_BROWSER_PROFILE_DIR,
    manual_login_wait_seconds: int = 0,
) -> list[FetchedPaper]:
    with WosBrowserSession(
        timeout_ms=timeout_ms,
        headless=headless,
        max_pages=max_pages,
        browser_profile_dir=browser_profile_dir,
        manual_login_wait_seconds=manual_login_wait_seconds,
    ) as session:
        return session.fetch_alert(url, source_email_id=source_email_id)


def _goto_wos_url(page, url: str, timeout_ms: int) -> None:
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
    except Exception as exc:
        if not _is_ignorable_navigation_issue(exc):
            raise
        try:
            page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 10000))
        except Exception:
            pass
        _wait_briefly(page)


def _is_ignorable_navigation_issue(exc: Exception) -> bool:
    message = str(exc)
    return (
        "net::ERR_ABORTED" in message
        or "frame was detached" in message
        or "Timeout" in message
        or "TimeoutError" in message
    )


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
    for element in soup.find_all(_is_probable_wos_title_element):
        title = element.get_text(" ", strip=True)
        if not _is_probable_title(title):
            continue
        href = _find_nearby_record_href(element)
        papers.append(
            FetchedPaper(
                title=title,
                abstract="",
                link=_normalize_wos_href(href) if href else None,
                source_email_id=source_email_id,
                fetch_method="wos_browser",
            )
        )

    return _deduplicate_by_title(papers)


def _is_probable_wos_title_element(element) -> bool:
    if element.name not in {"a", "span", "div", "h2", "h3", "h4"}:
        return False
    attrs = " ".join(
        str(value)
        for key, value in element.attrs.items()
        if key in {"data-ta", "id", "class", "aria-label"}
    ).lower()
    title_markers = {
        "summary-record-title",
        "record-title",
        "title-link",
        "fullrta",
        "full-record",
        "summary-title",
        "app-summary-title",
    }
    return any(marker in attrs for marker in title_markers)


def _find_nearby_record_href(element) -> str | None:
    if element.name == "a" and _is_wos_record_href(element.get("href", "")):
        return element.get("href")
    link = element.find("a", href=True)
    if link and _is_wos_record_href(link.get("href", "")):
        return link.get("href")
    for parent in element.parents:
        if getattr(parent, "name", None) in {None, "body", "html"}:
            break
        link = parent.find("a", href=True)
        if link and _is_wos_record_href(link.get("href", "")):
            return link.get("href")
    return None


def _collect_wos_records_across_pages(
    page,
    source_email_id: str | None,
    timeout_ms: int,
    max_pages: int,
) -> list[FetchedPaper]:
    papers: list[FetchedPaper] = []
    seen_keys: set[str] = set()
    empty_growth_pages = 0
    for _ in range(max_pages):
        page_papers = _collect_wos_records_from_current_page(page, source_email_id=source_email_id)
        new_keys = {_paper_title_key(paper) for paper in page_papers} - seen_keys
        if new_keys:
            empty_growth_pages = 0
        else:
            empty_growth_pages += 1
        papers.extend(page_papers)
        seen_keys.update(new_keys)
        if empty_growth_pages >= 2:
            break
        if not _go_to_next_results_page(page, timeout_ms=timeout_ms):
            break
        try:
            _wait_for_wos_records(page, timeout_ms=timeout_ms)
        except RuntimeError:
            pass
    return _deduplicate_by_title(papers)


def _wait_for_wos_records_or_login(page, timeout_ms: int, manual_login_wait_seconds: int = 0) -> None:
    try:
        _wait_for_wos_records(page, timeout_ms=timeout_ms)
        return
    except RuntimeError as wait_exc:
        if manual_login_wait_seconds > 0:
            try:
                _wait_for_manual_login(page, wait_seconds=manual_login_wait_seconds)
                return
            except RuntimeError as manual_exc:
                if not _is_clarivate_auth_page(page) or not _has_clarivate_credentials():
                    raise manual_exc
        if not _is_clarivate_auth_page(page):
            raise wait_exc

    _login_to_clarivate(page, timeout_ms=timeout_ms)
    _wait_for_wos_records(page, timeout_ms=timeout_ms)


def _is_clarivate_auth_page(page) -> bool:
    parsed = urlparse(getattr(page, "url", ""))
    return parsed.netloc.lower() == "access.clarivate.com"


def _login_to_clarivate(page, timeout_ms: int) -> None:
    current_url = getattr(page, "url", "")
    parsed = urlparse(current_url)
    if "forgotpassword" in parsed.path.lower() or "passwordexpired" in current_url.lower():
        raise RuntimeError("Clarivate 要求重置密码，无法自动登录；请先人工完成密码更新。")

    email = os.getenv(CLARIVATE_EMAIL_ENV, "").strip()
    password = os.getenv(CLARIVATE_PASSWORD_ENV, "")
    if not email or not password:
        raise RuntimeError(
            "Clarivate 登录页需要账号密码；请临时设置 CLARIVATE_EMAIL 和 CLARIVATE_PASSWORD，"
            "或在前端/CLI 设置手动登录等待时间后，在弹出的浏览器中完成机构登录。"
        )

    email_selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[name='username']",
        "input#username",
        "input#email",
    ]
    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input#password",
    ]
    continue_selectors = [
        "button:has-text('Continue')",
        "button:has-text('Next')",
        "button:has-text('继续')",
        "button:has-text('下一步')",
        "input[type='submit']",
    ]
    submit_selectors = [
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
        "button:has-text('Login')",
        "button:has-text('登录')",
        "input[type='submit']",
    ]

    _fill_first_visible(page, email_selectors, email, timeout_ms=timeout_ms, required=False)
    _click_first_visible(page, continue_selectors, timeout_ms=timeout_ms, required=False)
    _wait_briefly(page)
    _fill_first_visible(page, password_selectors, password, timeout_ms=timeout_ms, required=True)
    if not _click_first_visible(page, submit_selectors, timeout_ms=timeout_ms, required=False):
        page.keyboard.press("Enter")
    _wait_after_navigation_or_update(page, current_url=current_url, timeout_ms=timeout_ms)

    current_url = getattr(page, "url", "")
    if "forgotpassword" in current_url.lower() or "passwordexpired" in current_url.lower():
        raise RuntimeError("Clarivate 登录后要求重置密码，无法继续自动化。")


def _has_clarivate_credentials() -> bool:
    return bool(os.getenv(CLARIVATE_EMAIL_ENV, "").strip() and os.getenv(CLARIVATE_PASSWORD_ENV, ""))


def _wait_for_manual_login(page, wait_seconds: int) -> None:
    timeout_ms = max(1, wait_seconds) * 1000
    try:
        _wait_for_wos_records(page, timeout_ms=timeout_ms)
        return
    except RuntimeError as exc:
        raise RuntimeError(
            f"已等待 {wait_seconds} 秒，但仍未进入 WoS 记录页；"
            "请确认已在弹出的 Playwright Chromium 中完成学校/机构认证。"
        ) from exc


def _fill_first_visible(page, selectors: list[str], value: str, timeout_ms: int, required: bool) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 5)
            for index in range(count):
                item = locator.nth(index)
                if not item.is_visible() or not item.is_enabled():
                    continue
                item.fill(value, timeout=min(timeout_ms, 5000))
                return True
        except Exception:
            continue
    if required:
        raise RuntimeError("Clarivate 登录页未找到可填写的密码输入框。")
    return False


def _click_first_visible(page, selectors: list[str], timeout_ms: int, required: bool) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 5)
            for index in range(count):
                item = locator.nth(index)
                if not item.is_visible() or not item.is_enabled():
                    continue
                item.click(timeout=min(timeout_ms, 5000))
                return True
        except Exception:
            continue
    if required:
        raise RuntimeError("Clarivate 登录页未找到可点击的提交按钮。")
    return False


def _wait_briefly(page) -> None:
    try:
        page.wait_for_timeout(1000)
    except Exception:
        pass


def _collect_wos_records_from_current_page(
    page,
    source_email_id: str | None,
    max_scrolls: int = 180,
    settle_ms: int = 350,
) -> list[FetchedPaper]:
    papers: list[FetchedPaper] = []
    last_keys: set[str] = set()
    stable_rounds = 0
    for _ in range(max_scrolls):
        papers.extend(parse_wos_result_page(page.content(), source_email_id=source_email_id))
        keys = {_paper_title_key(paper) for paper in papers}
        moved = _scroll_next_record_batch(page)
        try:
            page.wait_for_timeout(settle_ms)
        except Exception:
            pass
        if keys == last_keys and not moved:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_keys = keys
        if stable_rounds >= 2:
            break
    papers.extend(parse_wos_result_page(page.content(), source_email_id=source_email_id))
    return _deduplicate_by_title(papers)


def _scroll_next_record_batch(page) -> bool:
    try:
        page.mouse.wheel(0, 450)
    except Exception:
        pass
    script = """
    () => {
      const elementVisible = (el) =>
        el === document.scrollingElement || el === document.documentElement || el === document.body ||
        !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const candidates = Array.from(new Set([
        ...Array.from(document.querySelectorAll('*')).filter((el) => {
          const style = window.getComputedStyle(el);
          return el.scrollHeight > el.clientHeight + 20 &&
            ['auto', 'scroll', 'overlay'].includes(style.overflowY) &&
            elementVisible(el);
        }),
        document.scrollingElement,
        document.documentElement,
        document.body
      ].filter(Boolean))).sort((a, b) => {
        const aRoom = Math.max(0, a.scrollHeight - a.clientHeight - a.scrollTop);
        const bRoom = Math.max(0, b.scrollHeight - b.clientHeight - b.scrollTop);
        return bRoom - aRoom;
      });
      for (const el of candidates) {
        if (el.scrollHeight <= el.clientHeight + 20) continue;
        const before = el.scrollTop;
        const step = Math.min(450, Math.max(Math.floor(el.clientHeight * 0.35), 180));
        el.scrollTop = Math.min(el.scrollTop + step, el.scrollHeight);
        if (el.scrollTop !== before) return true;
      }
      const beforeWindow = window.scrollY;
      window.scrollBy(0, Math.min(450, Math.max(Math.floor(window.innerHeight * 0.35), 180)));
      return window.scrollY !== beforeWindow;
    }
    """
    try:
        return bool(page.evaluate(script))
    except Exception:
        try:
            page.evaluate("window.scrollBy(0, Math.max(window.innerHeight * 0.85, 500))")
            return True
        except Exception:
            return False


def _record_link_count(page) -> int:
    selector = "a[href*='FullRecord'], a[href*='full-record'], a[href*='WOS:'], [data-ta='summary-record-title-link']"
    try:
        return page.locator(selector).count()
    except Exception:
        return 0


def _go_to_next_results_page(page, timeout_ms: int) -> bool:
    _scroll_to_pagination_area(page)
    selectors = [
        "button[data-ta*='pagination'][data-ta*='next']:not([disabled])",
        "a[data-ta*='pagination'][data-ta*='next']",
        "button[data-ta*='next']:not([disabled])",
        "a[data-ta*='next']",
        "button[aria-label*='Go to next page']:not([disabled])",
        "a[aria-label*='Go to next page']",
        "button[aria-label*='Next page']:not([disabled])",
        "a[aria-label*='Next page']",
        "button[class*='next']:not([disabled])",
        "a[class*='next']",
        "button[aria-label*='Next']:not([disabled])",
        "button[aria-label*='next']:not([disabled])",
        "button[aria-label*='下一']:not([disabled])",
        "a[aria-label*='Next']",
        "a[aria-label*='next']",
        "a[aria-label*='下一']",
        "button[title*='Next']:not([disabled])",
        "button[title*='next']:not([disabled])",
        "button[title*='下一']:not([disabled])",
        "a[title*='Next']",
        "a[title*='next']",
        "a[title*='下一']",
        "button:has-text('Next')",
        "button:has-text('next')",
        "button:has-text('>')",
        "button:has-text('›')",
        "a:has-text('Next')",
        "a:has-text('next')",
        "a:has-text('>')",
        "a:has-text('›')",
        "button:has-text('下一页')",
        "button:has-text('下一')",
        "a:has-text('下一页')",
        "a:has-text('下一')",
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
    if _click_next_page_number_by_dom(page, timeout_ms=timeout_ms):
        _wait_after_navigation_or_update(page, current_url=current_url, timeout_ms=timeout_ms)
        return True
    if _click_next_button_by_dom(page, timeout_ms=timeout_ms):
        _wait_after_navigation_or_update(page, current_url=current_url, timeout_ms=timeout_ms)
        return True
    if _goto_next_summary_url(page, current_url=current_url, timeout_ms=timeout_ms):
        _wait_after_navigation_or_update(page, current_url=current_url, timeout_ms=timeout_ms)
        return True
    return False


def _scroll_to_pagination_area(page) -> None:
    script = """
    () => {
      const scrollables = [
        document.scrollingElement,
        document.documentElement,
        document.body,
        ...Array.from(document.querySelectorAll('*')).filter((el) => {
          const style = window.getComputedStyle(el);
          return el.scrollHeight > el.clientHeight + 20 &&
            ['auto', 'scroll', 'overlay'].includes(style.overflowY);
        })
      ].filter(Boolean);
      for (const el of scrollables) {
        el.scrollTop = el.scrollHeight;
      }
      window.scrollTo(0, document.body.scrollHeight || document.documentElement.scrollHeight || 0);
    }
    """
    try:
        page.evaluate(script)
        page.wait_for_timeout(500)
    except Exception:
        pass


def _goto_next_summary_url(page, current_url: str | None = None, timeout_ms: int = 30000) -> bool:
    current_url = current_url or getattr(page, "url", "")
    next_url = _next_summary_page_url(current_url) or _next_summary_page_url_from_page(page)
    if not next_url:
        return False
    try:
        _goto_wos_url(page, next_url, timeout_ms=timeout_ms)
        return getattr(page, "url", "") != current_url
    except Exception:
        return False


def _next_summary_page_url_from_page(page) -> str | None:
    hrefs = _summary_hrefs_from_page(page)
    numbered_hrefs = [
        (_summary_page_number(href), href)
        for href in hrefs
        if "/wos/woscc/summary/" in urlparse(href).path
    ]
    next_page_hrefs = [(number, href) for number, href in numbered_hrefs if number and number > 1]
    if next_page_hrefs:
        return sorted(next_page_hrefs, key=lambda item: item[0])[0][1]
    for _, href in numbered_hrefs:
        next_url = _next_summary_page_url(href)
        if next_url:
            return next_url
    return None


def _summary_hrefs_from_page(page) -> list[str]:
    script = """
    () => Array.from(document.querySelectorAll('a[href*="/wos/woscc/summary/"]'))
      .map((a) => a.href || a.getAttribute('href'))
      .filter(Boolean)
    """
    try:
        return list(page.evaluate(script) or [])
    except Exception:
        return []


def _next_summary_page_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "/wos/woscc/summary/" not in parsed.path:
        return None
    match = re.search(r"(/wos/woscc/summary/[^/]+/[^/?#]+/)(\d+)(/?)$", parsed.path)
    if match:
        page_num = int(match.group(2))
        path = f"{match.group(1)}{page_num + 1}{match.group(3)}"
    else:
        match = re.search(r"(/wos/woscc/summary/[^/]+/[^/?#]+)(/?)$", parsed.path)
        if not match:
            return None
        path = f"{match.group(1).rstrip('/')}/2"
    return parsed._replace(path=path).geturl()


def _summary_page_number(url: str) -> int | None:
    parsed = urlparse(url)
    match = re.search(r"/wos/woscc/summary/[^/]+/[^/?#]+/(\d+)(?:/)?$", parsed.path)
    if not match:
        return None
    return int(match.group(1))


def _click_next_button_by_dom(page, timeout_ms: int) -> bool:
    script = """
    () => {
      const labels = ['next', '下一', '>', '›', '»'];
      const candidates = Array.from(document.querySelectorAll('button, a'));
      for (const el of candidates) {
        const text = [
          el.innerText,
          el.textContent,
          el.getAttribute('aria-label'),
          el.getAttribute('title'),
          el.getAttribute('data-ta'),
          el.className
        ].filter(Boolean).join(' ').toLowerCase();
        const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('disabled');
        const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
        if (!disabled && visible && labels.some((label) => text.includes(label))) {
          el.click();
          return true;
        }
      }
      return false;
    }
    """
    try:
        clicked = bool(page.evaluate(script))
        if clicked:
            page.wait_for_timeout(min(timeout_ms, 1200))
        return clicked
    except Exception:
        return False


def _click_next_page_number_by_dom(page, timeout_ms: int) -> bool:
    script = """
    () => {
      const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const disabled = (el) => el.disabled || el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('disabled');
      const candidates = Array.from(document.querySelectorAll('button, a')).filter((el) => visible(el));
      const textOf = (el) => [
        el.innerText,
        el.textContent,
        el.getAttribute('aria-label'),
        el.getAttribute('title')
      ].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();

      let currentPage = null;
      for (const el of candidates) {
        const text = textOf(el);
        const exactNumber = text.match(/^\\d+$/);
        const labelNumber = text.match(/(?:page|第)\\s*(\\d+)/i);
        const number = exactNumber ? parseInt(exactNumber[0], 10) : (labelNumber ? parseInt(labelNumber[1], 10) : null);
        const marker = [
          el.getAttribute('aria-current'),
          el.getAttribute('aria-selected'),
          el.className
        ].filter(Boolean).join(' ').toLowerCase();
        if (number && (marker.includes('page') || marker.includes('true') || marker.includes('active') || marker.includes('current') || marker.includes('selected'))) {
          currentPage = number;
          break;
        }
      }
      if (!currentPage) currentPage = 1;
      const targetPage = currentPage + 1;

      for (const el of candidates) {
        if (disabled(el)) continue;
        const text = textOf(el);
        const exactNumber = text.match(/^\\d+$/);
        const labelNumber = text.match(/(?:page|第)\\s*(\\d+)/i);
        const number = exactNumber ? parseInt(exactNumber[0], 10) : (labelNumber ? parseInt(labelNumber[1], 10) : null);
        if (number === targetPage) {
          el.click();
          return true;
        }
      }
      return false;
    }
    """
    try:
        clicked = bool(page.evaluate(script))
        if clicked:
            page.wait_for_timeout(min(timeout_ms, 1200))
        return clicked
    except Exception:
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
        "[data-ta*='summary-record-title']",
        "[data-ta*='record-title']",
        "[id*='FullRTa']",
        "[class*='summary-record-title']",
        "[class*='title-link']",
    ]
    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=timeout_ms // len(selectors))
            return
        except Exception:
            continue
    if _looks_like_loaded_wos_summary_page(page):
        return
    title = _safe_page_title(page)
    current_url = _summarize_page_url(getattr(page, "url", ""))
    raise RuntimeError(f"页面已打开但未发现 WoS 记录链接；title={title!r}；url={current_url!r}")


def _looks_like_loaded_wos_summary_page(page) -> bool:
    title = _safe_page_title(page).lower()
    current_url = _summarize_page_url(getattr(page, "url", "")).lower()
    if "/wos/woscc/summary/" not in current_url and "alerting results" not in title:
        return False
    try:
        body = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        body = ""
    return "web of science core collection" in title or "web of science core collection" in body


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
    if "arrow_drop_down" in lowered or "javascript:void" in lowered:
        return False
    bad = {
        "view record",
        "full text",
        "export",
        "save",
        "citation network",
        "cited references",
        "marked list",
        "web of science core collection",
        "alerting results for",
        "sort by",
        "results per page",
    }
    return not any(item in lowered for item in bad)


def _is_wos_record_href(href: str) -> bool:
    lowered = href.lower()
    if not lowered or lowered.startswith("javascript:") or lowered.startswith("#"):
        return False
    return "fullrecord" in lowered or "full-record" in lowered or "keyut=wos" in lowered or "wos:" in lowered


def _normalize_wos_href(href: str) -> str:
    extracted = _extract_wos_url(href)
    if extracted:
        return extracted
    if href.lower().startswith(("javascript:", "#")):
        return ""
    if href.startswith("http"):
        return href
    return f"https://www.webofscience.com{href}"


def _deduplicate_by_title(papers: list[FetchedPaper]) -> list[FetchedPaper]:
    seen: set[str] = set()
    unique: list[FetchedPaper] = []
    for paper in papers:
        key = _paper_title_key(paper)
        if key in seen:
            continue
        seen.add(key)
        unique.append(paper)
    return unique


def _paper_title_key(paper: FetchedPaper) -> str:
    return " ".join(paper.title.lower().split())
