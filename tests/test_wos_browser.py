import pytest

from paper_analyzer.ingestion.wos_browser import (
    _collect_wos_records_across_pages,
    _collect_wos_records_from_current_page,
    _click_next_page_number_by_dom,
    _goto_wos_url,
    _next_summary_page_url,
    _next_summary_page_url_from_page,
    _wait_for_wos_records,
    _wait_for_wos_records_or_login,
    parse_wos_result_page,
)


def test_parse_wos_result_page_extracts_record_links():
    html = """
    <html>
      <body>
        <a href="/wos/woscc/full-record/WOS:001234">A useful physics-informed neural network paper</a>
        <a href="/wos/woscc/full-record/WOS:001234">A useful physics-informed neural network paper</a>
        <a href="/help">Export</a>
      </body>
    </html>
    """

    papers = parse_wos_result_page(html, source_email_id="<id@example.com>")

    assert len(papers) == 1
    assert papers[0].title == "A useful physics-informed neural network paper"
    assert papers[0].link == "https://www.webofscience.com/wos/woscc/full-record/WOS:001234"
    assert papers[0].fetch_method == "wos_browser"


def test_parse_wos_result_page_extracts_data_ta_title_without_anchor():
    html = """
    <html>
      <body>
        <app-summary-record>
          <div data-ta="summary-record-title">
            A broad selector physics-informed neural network result title
          </div>
        </app-summary-record>
      </body>
    </html>
    """

    papers = parse_wos_result_page(html, source_email_id="<id@example.com>")

    assert len(papers) == 1
    assert papers[0].title == "A broad selector physics-informed neural network result title"
    assert papers[0].link is None


def test_parse_wos_result_page_extracts_nearby_href_from_title_container():
    html = """
    <html>
      <body>
        <div class="summary-record">
          <a href="/wos/woscc/full-record/WOS:009999">View record</a>
          <span class="summary-record-title">
            Container title physics-informed neural network paper
          </span>
        </div>
      </body>
    </html>
    """

    papers = parse_wos_result_page(html, source_email_id="<id@example.com>")

    assert len(papers) == 1
    assert papers[0].title == "Container title physics-informed neural network paper"
    assert papers[0].link == "https://www.webofscience.com/wos/woscc/full-record/WOS:009999"


def test_parse_wos_result_page_filters_facets_and_javascript_links():
    html = """
    <html>
      <body>
        <a class="summary-record-title" href="javascript:void(0)">
          COMPUTER METHODS IN APPLIED MECHANICS AND ENGINEERING arrow_drop_down
        </a>
        <div class="summary-record">
          <a href="javascript:void(0)">Facet dropdown item physics-informed</a>
          <span class="summary-record-title">
            Real paper title about physics-informed neural networks
          </span>
        </div>
      </body>
    </html>
    """

    papers = parse_wos_result_page(html, source_email_id="<id@example.com>")

    assert len(papers) == 1
    assert papers[0].title == "Real paper title about physics-informed neural networks"
    assert papers[0].link is None


def test_wait_for_wos_records_reports_login_or_empty_page():
    class FakePage:
        url = "https://access.clarivate.com/login?loginId=user@example.com&sid=secret"

        def wait_for_selector(self, selector, timeout):
            raise TimeoutError()

        def title(self):
            return "Sign in"

    with pytest.raises(RuntimeError) as exc_info:
        _wait_for_wos_records(FakePage(), timeout_ms=1000)
    message = str(exc_info.value)
    assert "Sign in" in message
    assert "access.clarivate.com/login" in message
    assert "user@example.com" not in message
    assert "sid=secret" not in message


def test_clarivate_password_reset_page_stops_login(monkeypatch):
    monkeypatch.setenv("CLARIVATE_EMAIL", "user@example.com")
    monkeypatch.setenv("CLARIVATE_PASSWORD", "secret")

    class FakePage:
        url = "https://access.clarivate.com/forgotpassword?loginId=user@example.com&passwordExpired=expired"

        def wait_for_selector(self, selector, timeout):
            raise TimeoutError()

        def title(self):
            return "Clarivate"

    with pytest.raises(RuntimeError, match="重置密码"):
        _wait_for_wos_records_or_login(FakePage(), timeout_ms=1000)


def test_wait_for_wos_records_allows_manual_login_wait(monkeypatch):
    monkeypatch.delenv("CLARIVATE_EMAIL", raising=False)
    monkeypatch.delenv("CLARIVATE_PASSWORD", raising=False)

    class FakePage:
        url = "https://access.clarivate.com/login"

        def __init__(self):
            self.calls = 0

        def wait_for_selector(self, selector, timeout):
            self.calls += 1
            if self.calls <= 4:
                raise TimeoutError()

        def title(self):
            return "Sign in"

    page = FakePage()

    _wait_for_wos_records_or_login(page, timeout_ms=1000, manual_login_wait_seconds=1)

    assert page.calls > 4


def test_goto_wos_url_ignores_gateway_navigation_abort():
    class FakePage:
        def __init__(self):
            self.waited = False

        def goto(self, url, wait_until, timeout):
            raise RuntimeError("Page.goto: net::ERR_ABORTED; maybe frame was detached?")

        def wait_for_load_state(self, state, timeout):
            self.waited = True

        def wait_for_timeout(self, timeout):
            pass

    page = FakePage()

    _goto_wos_url(page, "https://www.webofscience.com/api/gateway", timeout_ms=1000)

    assert page.waited is True


def test_goto_wos_url_ignores_networkidle_timeout():
    class FakePage:
        def __init__(self):
            self.waited = False

        def goto(self, url, wait_until, timeout):
            raise RuntimeError("Page.goto: Timeout 30000ms exceeded.")

        def wait_for_load_state(self, state, timeout):
            self.waited = True

        def wait_for_timeout(self, timeout):
            pass

    page = FakePage()

    _goto_wos_url(page, "https://www.webofscience.com/api/gateway", timeout_ms=1000)

    assert page.waited is True


def test_collect_wos_records_accumulates_virtualized_scroll_results():
    class FakePage:
        def __init__(self):
            self.index = 0
            self.pages = [
                """
                <a href="/wos/woscc/full-record/WOS:001">First virtualized physics-informed paper title</a>
                <a href="/wos/woscc/full-record/WOS:002">Second virtualized physics-informed paper title</a>
                """,
                """
                <a href="/wos/woscc/full-record/WOS:002">Second virtualized physics-informed paper title</a>
                <a href="/wos/woscc/full-record/WOS:003">Third virtualized physics-informed paper title</a>
                """,
                """
                <a href="/wos/woscc/full-record/WOS:004">Fourth virtualized physics-informed paper title</a>
                """,
            ]

        def content(self):
            return f"<html><body>{self.pages[self.index]}</body></html>"

        def evaluate(self, script):
            if self.index < len(self.pages) - 1:
                self.index += 1
                return True
            return False

        def wait_for_timeout(self, timeout):
            pass

    papers = _collect_wos_records_from_current_page(FakePage(), source_email_id="<id@example.com>")

    assert [paper.title for paper in papers] == [
        "First virtualized physics-informed paper title",
        "Second virtualized physics-informed paper title",
        "Third virtualized physics-informed paper title",
        "Fourth virtualized physics-informed paper title",
    ]


def test_collect_wos_records_still_parses_next_page_when_next_page_wait_fails(monkeypatch):
    import paper_analyzer.ingestion.wos_browser as wos_browser

    class FakePage:
        def __init__(self):
            self.page_index = 0

        def content(self):
            if self.page_index == 0:
                return """
                <html><body>
                  <a href="/wos/woscc/full-record/WOS:001">First page physics-informed paper title</a>
                </body></html>
                """
            return """
            <html><body>
              <a href="/wos/woscc/full-record/WOS:002">Second page physics-informed paper title</a>
            </body></html>
            """

        def evaluate(self, script):
            return False

        def wait_for_timeout(self, timeout):
            pass

    page = FakePage()

    def go_next(fake_page, timeout_ms):
        fake_page.page_index += 1
        return fake_page.page_index == 1

    monkeypatch.setattr(wos_browser, "_go_to_next_results_page", go_next)
    monkeypatch.setattr(
        wos_browser,
        "_wait_for_wos_records",
        lambda fake_page, timeout_ms: (_ for _ in ()).throw(RuntimeError("generic error")),
    )

    papers = _collect_wos_records_across_pages(
        page,
        source_email_id="<id@example.com>",
        timeout_ms=1000,
        max_pages=5,
    )

    assert [paper.title for paper in papers] == [
        "First page physics-informed paper title",
        "Second page physics-informed paper title",
    ]


def test_next_summary_page_url_increments_existing_page_number():
    url = "https://webofscience.clarivate.cn/wos/woscc/summary/abc-123/relevance/1"

    assert _next_summary_page_url(url) == "https://webofscience.clarivate.cn/wos/woscc/summary/abc-123/relevance/2"


def test_next_summary_page_url_appends_page_number_when_missing():
    url = "https://webofscience.clarivate.cn/wos/woscc/summary/abc-123/relevance"

    assert _next_summary_page_url(url) == "https://webofscience.clarivate.cn/wos/woscc/summary/abc-123/relevance/2"


def test_next_summary_page_url_from_page_uses_page_two_href_when_current_url_is_gateway():
    class FakePage:
        def evaluate(self, script):
            assert "/wos/woscc/summary/" in script
            return [
                "https://www.webofscience.com/wos/woscc/summary/abc-123/relevance/2",
                "https://www.webofscience.com/wos/woscc/summary/abc-123/relevance/3",
            ]

    assert (
        _next_summary_page_url_from_page(FakePage())
        == "https://www.webofscience.com/wos/woscc/summary/abc-123/relevance/2"
    )


def test_next_summary_page_url_from_page_derives_page_two_from_page_one_href():
    class FakePage:
        def evaluate(self, script):
            return ["https://www.webofscience.com/wos/woscc/summary/abc-123/relevance/1"]

    assert (
        _next_summary_page_url_from_page(FakePage())
        == "https://www.webofscience.com/wos/woscc/summary/abc-123/relevance/2"
    )


def test_click_next_page_number_by_dom_uses_page_script_result():
    class FakePage:
        def __init__(self):
            self.waited = False

        def evaluate(self, script):
            assert "targetPage" in script
            return True

        def wait_for_timeout(self, timeout):
            self.waited = True

    page = FakePage()

    assert _click_next_page_number_by_dom(page, timeout_ms=1000) is True
    assert page.waited is True
