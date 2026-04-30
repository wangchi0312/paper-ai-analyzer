from pathlib import Path
import time

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.downloader import safe_pdf_name
from paper_analyzer.fulltext.resolver import (
    MAX_DOWNLOAD_CANDIDATES,
    _arxiv_candidates,
    _candidate_pdf_urls,
    _classify_download_error,
    _extract_pdf_links,
    _failure_reason,
    _openalex_candidates,
    _total_budget_seconds,
    resolve_full_text,
)


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
    )

    assert result.success is True
    assert result.source == "unpaywall"
    assert attempts == ["https://example.com/not-pdf", "https://example.com/paper.pdf"]


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
