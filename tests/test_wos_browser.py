import pytest

from paper_analyzer.ingestion.wos_browser import _wait_for_wos_records, parse_wos_result_page


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
