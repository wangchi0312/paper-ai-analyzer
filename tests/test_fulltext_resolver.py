from pathlib import Path
import time

import pytest

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.downloader import safe_pdf_name
from paper_analyzer.fulltext.source import FullTextResult
from paper_analyzer.fulltext.resolver import (
    MAX_DOWNLOAD_CANDIDATES,
    _arxiv_candidates,
    _candidate_pdf_urls,
    _classify_download_error,
    _crossref_tdm_candidates,
    _detect_captcha_on_page,
    _extract_pdf_links,
    _failure_reason,
    _launch_persistent_publisher_context,
    _openalex_candidates,
    _publisher_browser_channel_candidates,
    _publisher_browser_profile_dir,
    _respect_publisher_request_interval,
    _total_budget_seconds,
    _verification_loop_seconds,
    _wait_for_manual_verification,
    resolve_full_text,
)


def _disable_api_pdf_sources(monkeypatch):
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._crossref_tdm_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._download_pdf_via_publisher_chain", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver.resolve_via_spis",
        lambda *args, **kwargs: FullTextResult(success=False, source="spis_not_found", reason="not found"),
    )


@pytest.fixture(autouse=True)
def disable_api_pdf_sources(monkeypatch):
    _disable_api_pdf_sources(monkeypatch)


def test_safe_pdf_name():
    name = safe_pdf_name("A/B: Test Paper?", 3)
    assert name.startswith("03_")
    assert name.endswith(".pdf")
    assert "/" not in name


def test_candidate_pdf_urls_includes_direct_pdf_link(monkeypatch):
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._publisher_page_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._openalex_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._unpaywall_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._semantic_scholar_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._arxiv_candidates", lambda *args, **kwargs: [])

    paper = FetchedPaper(title="T", abstract="A", link="https://example.com/paper.pdf")

    candidates = _candidate_pdf_urls(paper)

    assert candidates == [("publisher", "https://example.com/paper.pdf")]


def test_candidate_pdf_urls_deduplicates(monkeypatch):
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._publisher_page_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._openalex_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._unpaywall_candidates",
        lambda *args, **kwargs: [("unpaywall", "https://example.com/paper.pdf")],
    )
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._semantic_scholar_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._arxiv_candidates", lambda *args, **kwargs: [])

    paper = FetchedPaper(title="T", abstract="A", doi="10.1/test", link="https://example.com/paper.pdf")

    candidates = _candidate_pdf_urls(paper, unpaywall_email="a@example.com")

    assert candidates == [("publisher", "https://example.com/paper.pdf")]


def test_candidate_pdf_urls_includes_openalex(monkeypatch):
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._publisher_page_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._openalex_candidates",
        lambda *args, **kwargs: [("openalex", "https://oa.example/paper.pdf")],
    )
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._unpaywall_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._semantic_scholar_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._arxiv_candidates", lambda *args, **kwargs: [])

    paper = FetchedPaper(title="T", abstract="A", doi="10.1/test")

    assert _candidate_pdf_urls(paper) == [("openalex", "https://oa.example/paper.pdf")]


def test_candidate_pdf_urls_includes_crossref_tdm(monkeypatch):
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._publisher_page_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._openalex_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._unpaywall_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._semantic_scholar_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._arxiv_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._crossref_tdm_candidates",
        lambda *args, **kwargs: [("crossref_tdm", "https://publisher.example/tdm.pdf")],
    )

    paper = FetchedPaper(title="T", abstract="A", doi="10.1/test")

    assert _candidate_pdf_urls(paper) == [("crossref_tdm", "https://publisher.example/tdm.pdf")]


def test_crossref_tdm_candidates_selects_pdf_link(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "message": {
                    "link": [
                        {"URL": "https://example.com/fulltext.html", "content-type": "text/html"},
                        {
                            "URL": "https://example.com/paper.pdf",
                            "content-type": "application/pdf",
                            "intended-application": "text-mining",
                        },
                    ]
                }
            }

    monkeypatch.setattr("paper_analyzer.fulltext.resolver.requests.get", lambda *args, **kwargs: FakeResponse())

    assert _crossref_tdm_candidates("10.1/test", timeout=1) == [("crossref_tdm", "https://example.com/paper.pdf")]


def test_candidate_pdf_urls_limits_candidates(monkeypatch):
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._publisher_page_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._openalex_candidates",
        lambda *args, **kwargs: [("openalex", f"https://oa.example/{index}.pdf") for index in range(10)],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._unpaywall_candidates",
        lambda *args, **kwargs: [("unpaywall", "https://unpaywall.example/paper.pdf")],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._semantic_scholar_candidates",
        lambda *args, **kwargs: [("semantic_scholar", "https://semantic.example/paper.pdf")],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._arxiv_candidates",
        lambda *args, **kwargs: [("arxiv", "https://arxiv.example/paper.pdf")],
    )

    candidates = _candidate_pdf_urls(FetchedPaper(title="T", abstract="", doi="10.1/test"))

    assert len(candidates) == MAX_DOWNLOAD_CANDIDATES
    assert candidates == [
        ("unpaywall", "https://unpaywall.example/paper.pdf"),
        ("semantic_scholar", "https://semantic.example/paper.pdf"),
        ("openalex", "https://oa.example/0.pdf"),
        ("arxiv", "https://arxiv.example/paper.pdf"),
    ]


def test_openalex_title_lookup_rejects_mismatched_title(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "results": [
                    {
                        "display_name": "Completely Different Paper",
                        "open_access": {"oa_url": "https://oa.example/wrong.pdf"},
                        "locations": [],
                    }
                ]
            }

    monkeypatch.setattr("paper_analyzer.fulltext.resolver.requests.get", lambda *args, **kwargs: FakeResponse())

    candidates = _openalex_candidates(FetchedPaper(title="Physics Informed Neural Networks", abstract=""), timeout=1)

    assert candidates == []


def test_arxiv_rejects_mismatched_title(monkeypatch):
    xml = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Completely Different Paper</title>
        <link title="pdf" href="https://arxiv.org/pdf/1234" />
      </entry>
    </feed>
    """

    class FakeResponse:
        text = xml

        def raise_for_status(self):
            pass

    monkeypatch.setattr("paper_analyzer.fulltext.resolver.requests.get", lambda *args, **kwargs: FakeResponse())

    assert _arxiv_candidates("Physics Informed Neural Networks", timeout=1) == []


def test_resolve_full_text_reports_candidate_discovery_timeout(monkeypatch):
    monkeypatch.setattr("paper_analyzer.fulltext.resolver.resolve_manual_pdf", lambda *args, **kwargs: None)
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._total_budget_seconds", lambda timeout: 1)

    def expire_deadline(*args, **kwargs):
        time.sleep(1.1)
        return []

    monkeypatch.setattr("paper_analyzer.fulltext.resolver._candidate_pdf_urls", expire_deadline)

    result = resolve_full_text(
        FetchedPaper(title="Timeout Paper", abstract=""),
        output_dir=Path("data/outputs/test_tmp/fulltext_timeout"),
        index=1,
        timeout=1,
        enable_api_fallback=True,
    )

    assert result.success is False
    assert result.reason == "全文下载超时；可增大全文下载超时秒数后重试"


def test_extract_pdf_links_from_publisher_page():
    html = """
    <html><body>
      <a href="/article">Article</a>
      <a href="/content/paper.pdf" aria-label="Download PDF">PDF</a>
      <a href="https://example.com/fulltext">Full text</a>
    </body></html>
    """

    links = _extract_pdf_links(html, "https://publisher.example/article")

    assert links[0] == "https://publisher.example/content/paper.pdf"


def test_failure_reason_marks_subscription_required():
    reason = _failure_reason(["publisher_page: 需要订阅或付费：HTTP 403"])

    assert "需要订阅或付费" in reason
    assert "手动上传 PDF" in reason


def test_failure_reason_prefers_timeout_message():
    reason = _failure_reason(["openalex: 下载超时：read timed out"])

    assert reason == "全文下载超时；可增大全文下载超时秒数后重试"


def test_total_budget_scales_with_timeout():
    assert _total_budget_seconds(1) == 15
    assert _total_budget_seconds(10) == 60
    assert _total_budget_seconds(30) == 90


def test_detect_captcha_on_page_marks_cloudflare_challenge():
    class FakeLocator:
        def __init__(self, text=""):
            self.text = text

        def inner_text(self, timeout):
            return self.text

        def count(self):
            return 0

    class FakePage:
        def locator(self, selector):
            if selector == "body":
                return FakeLocator("Just a moment... Checking if the site connection is secure")
            return FakeLocator()

        def title(self):
            return "Just a moment..."

    assert _detect_captcha_on_page(FakePage()) is True


def test_wait_for_manual_verification_returns_after_challenge_disappears():
    class FakeLocator:
        def __init__(self, page):
            self.page = page

        def inner_text(self, timeout):
            return "captcha" if self.page.checks == 0 else "article page"

        def count(self):
            return 0

    class FakePage:
        def __init__(self):
            self.checks = 0

        def wait_for_timeout(self, timeout):
            self.checks += 1

        def wait_for_load_state(self, state, timeout):
            pass

        def locator(self, selector):
            return FakeLocator(self)

        def title(self):
            return ""

    assert _wait_for_manual_verification(FakePage(), wait_seconds=1) is True


def test_wait_for_manual_verification_stops_on_loop_guard(monkeypatch):
    import paper_analyzer.fulltext.resolver as resolver

    clock = {"now": 100.0}
    monkeypatch.setenv("PUBLISHER_VERIFICATION_LOOP_SECONDS", "10")
    monkeypatch.setattr(resolver.time, "monotonic", lambda: clock["now"])

    class FakeLocator:
        def inner_text(self, timeout):
            return "请验证您是真人"

        def count(self):
            return 0

    class FakePage:
        def wait_for_timeout(self, timeout):
            clock["now"] += timeout / 1000

        def locator(self, selector):
            return FakeLocator()

        def title(self):
            return "请验证您是真人"

    assert _wait_for_manual_verification(FakePage(), wait_seconds=300) is False
    assert clock["now"] <= 112


def test_verification_loop_seconds_reads_env(monkeypatch):
    monkeypatch.setenv("PUBLISHER_VERIFICATION_LOOP_SECONDS", "25")

    assert _verification_loop_seconds() == 25


def test_respect_publisher_request_interval_sleeps_between_calls(monkeypatch):
    import paper_analyzer.fulltext.resolver as resolver

    clock = {"now": 100.0}
    sleeps = []
    monkeypatch.setattr(resolver, "_LAST_PUBLISHER_ACCESS_AT", None)
    monkeypatch.setattr(resolver.time, "monotonic", lambda: clock["now"])

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(resolver.time, "sleep", fake_sleep)

    _respect_publisher_request_interval(10)
    clock["now"] += 3
    _respect_publisher_request_interval(10)

    assert sleeps == [7]


def test_publisher_browser_profile_dir_reads_env(monkeypatch):
    monkeypatch.setenv("PUBLISHER_BROWSER_PROFILE_DIR", "data/browser_profiles/publisher")

    assert _publisher_browser_profile_dir() == "data/browser_profiles/publisher"


def test_publisher_browser_channel_auto_prefers_real_browsers(monkeypatch):
    monkeypatch.setenv("PUBLISHER_BROWSER_CHANNEL", "auto")

    assert _publisher_browser_channel_candidates() == ["chrome", "msedge", None]


def test_launch_persistent_publisher_context_falls_back_to_bundled_chromium(monkeypatch):
    calls = []

    class FakeChromium:
        def launch_persistent_context(self, **kwargs):
            calls.append(kwargs)
            if kwargs.get("channel") == "chrome":
                raise RuntimeError("chrome missing")
            return "context"

    class FakePlaywright:
        chromium = FakeChromium()

    monkeypatch.setenv("PUBLISHER_BROWSER_PROFILE_DIR", "data/browser_profiles/publisher")
    monkeypatch.setenv("PUBLISHER_BROWSER_CHANNEL", "chrome")

    assert _launch_persistent_publisher_context(FakePlaywright()) == "context"
    assert calls == [
        {"user_data_dir": "data/browser_profiles/publisher", "headless": False, "channel": "chrome"},
        {"user_data_dir": "data/browser_profiles/publisher", "headless": False},
    ]


def test_classify_download_error_marks_non_pdf_html_as_subscription():
    error = RuntimeError("下载结果不是 PDF：content-type=text/html")

    assert "需要订阅或付费" in _classify_download_error(error)




def test_classify_download_error_marks_subscription_http_status(monkeypatch):
    import requests

    response = requests.Response()
    response.status_code = 403
    error = requests.HTTPError(response=response)

    assert "需要订阅或付费" in _classify_download_error(error)


def test_classify_download_error_marks_rate_limit_as_http_error():
    import requests

    response = requests.Response()
    response.status_code = 429
    error = requests.HTTPError(response=response)

    assert _classify_download_error(error) == "网络/HTTP 错误：HTTP 429"


def test_resolve_full_text_continues_after_non_pdf_candidate(monkeypatch):
    attempts = []

    monkeypatch.setattr("paper_analyzer.fulltext.resolver.resolve_manual_pdf", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._candidate_pdf_urls",
        lambda *args, **kwargs: [
            ("openalex", "https://example.com/not-pdf"),
            ("unpaywall", "https://example.com/paper.pdf"),
        ],
    )

    def fake_download(url, output_path, timeout=10):
        attempts.append(url)
        if "not-pdf" in url:
            raise RuntimeError("下载结果不是 PDF：content-type=text/html")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4\n")
        return output_path

    monkeypatch.setattr("paper_analyzer.fulltext.resolver.download_pdf", fake_download)

    result = resolve_full_text(
        FetchedPaper(title="Fallback PDF", abstract=""),
        output_dir=Path("data/outputs/test_tmp/fulltext_non_pdf"),
        index=1,
        enable_api_fallback=True,
    )

    assert result.success is True
    assert result.source == "unpaywall"
    assert attempts == ["https://example.com/not-pdf", "https://example.com/paper.pdf"]


def test_resolve_full_text_keeps_api_fallback_disabled_by_default(monkeypatch):
    monkeypatch.setattr("paper_analyzer.fulltext.resolver.resolve_manual_pdf", lambda *args, **kwargs: None)

    def fail_candidates(*args, **kwargs):
        raise AssertionError("API candidates should be skipped by default")

    monkeypatch.setattr("paper_analyzer.fulltext.resolver._candidate_pdf_urls", fail_candidates)

    result = resolve_full_text(
        FetchedPaper(title="Browser First", abstract=""),
        output_dir=Path("data/outputs/test_tmp/fulltext_browser_first"),
        index=1,
        full_text_source="publisher",
    )

    assert result.success is False
    assert "开放获取/API 兜底默认关闭" in result.reason


def test_resolve_full_text_does_not_use_spis_by_default(monkeypatch):
    seen = []

    monkeypatch.setattr("paper_analyzer.fulltext.resolver.resolve_manual_pdf", lambda *args, **kwargs: None)

    def fake_spis(paper, output_dir, index):
        seen.append((paper.title, output_dir, index))
        return FullTextResult(success=False, source="spis_email_timeout", reason="timeout")

    monkeypatch.setattr("paper_analyzer.fulltext.resolver.resolve_via_spis", fake_spis)

    result = resolve_full_text(
        FetchedPaper(title="SPIS Paper", abstract=""),
        output_dir=Path("data/outputs/test_tmp/fulltext_spis"),
        index=2,
    )

    assert result.success is False
    assert result.source is None
    assert seen == []


def test_resolve_full_text_prefers_manual_pdf(monkeypatch):
    tmp_dir = Path("data/outputs/test_tmp/fulltext_resolver_manual")
    if tmp_dir.exists():
        import shutil

        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    manual_dir = tmp_dir / "manual"
    manual_dir.mkdir()
    manual_pdf = manual_dir / "Manual paper.pdf"
    manual_pdf.write_bytes(b"%PDF-1.4\n")

    def fail_candidates(*args, **kwargs):
        raise AssertionError("online candidates should not be queried after manual match")

    monkeypatch.setattr("paper_analyzer.fulltext.resolver._candidate_pdf_urls", fail_candidates)

    result = resolve_full_text(
        FetchedPaper(title="Manual paper", abstract=""),
        output_dir=tmp_dir / "papers",
        index=1,
        manual_pdf_dir=str(manual_dir),
    )

    assert result.success is True
    assert result.source == "manual_upload"
    assert Path(result.path).exists()




def test_classify_download_error_http_403():
    import requests

    exc = requests.HTTPError("403 Forbidden")
    resp = requests.Response()
    resp.status_code = 403
    exc.response = resp
    reason = _classify_download_error(exc)
    assert "订阅或付费" in reason or "403" in reason


def test_classify_download_error_http_429():
    import requests

    exc = requests.HTTPError("429 Too Many Requests")
    resp = requests.Response()
    resp.status_code = 429
    exc.response = resp
    reason = _classify_download_error(exc)
    assert "429" in reason


def test_resolve_full_text_non_pdf_content(monkeypatch):
    import requests
    from paper_analyzer.fulltext.source import FullTextResult

    # 模拟所有在线源均返回非 PDF 链接
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._publisher_page_candidates",
        lambda *a, **kw: [("publisher_page", "https://example.com/paper.html")],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._openalex_candidates",
        lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._unpaywall_candidates",
        lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._semantic_scholar_candidates",
        lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._arxiv_candidates",
        lambda *a, **kw: [],
    )
    # 下载时返回 HTML 而非 PDF，触发"不是 PDF"错误
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver.download_pdf",
        lambda url, output_path, timeout: (_ for _ in ()).throw(
            RuntimeError("下载结果不是 PDF：content-type=text/html")
        ),
    )

    result = resolve_full_text(
        FetchedPaper(title="Test Paper", abstract="", doi="10.1000/1"),
        output_dir=Path("/tmp"),
        index=1,
        timeout=3,
        full_text_source="auto",
        enable_api_fallback=True,
    )
    assert result.success is False
    assert "PDF" in result.reason or "付费" in result.reason or "开放获取" in result.reason


def test_resolve_full_text_all_sources_return_no_candidates(monkeypatch):
    from paper_analyzer.fulltext.source import FullTextResult

    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver.resolve_manual_pdf",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._publisher_page_candidates",
        lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._openalex_candidates",
        lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._unpaywall_candidates",
        lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._semantic_scholar_candidates",
        lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._arxiv_candidates",
        lambda *a, **kw: [],
    )

    result = resolve_full_text(
        FetchedPaper(title="No Sources Paper", abstract=""),
        output_dir=Path("/tmp"),
        index=1,
        timeout=3,
    )
    assert result.success is False
