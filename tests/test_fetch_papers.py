import json
import shutil
from pathlib import Path

from paper_analyzer.data.schema import FetchedPaper
from pipeline import fetch_papers as fetch_mod
from pipeline.fetch_papers import deduplicate_papers, load_fetched_papers, save_fetched_papers


def _make_tmp_dir(name: str) -> Path:
    path = Path("data/outputs/test_tmp") / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _email_stats(count: int) -> dict[str, int]:
    return {
        "inbox_email_count": count,
        "checked_email_count": count,
        "matched_wos_email_count": count,
        "skipped_seen_email_count": 0,
        "skipped_non_alert_email_count": 0,
    }


def test_deduplicate_papers_prefers_doi():
    papers = [
        FetchedPaper(title="A", abstract="x", doi="10.1/test"),
        FetchedPaper(title="Different title", abstract="y", doi="10.1/test"),
        FetchedPaper(title="A", abstract="z", doi=None),
    ]

    unique = deduplicate_papers(papers)

    assert len(unique) == 2
    assert unique[0].title == "A"
    assert unique[1].doi is None


def test_deduplicate_papers_by_normalized_title():
    papers = [
        FetchedPaper(title="A  Test Paper", abstract="x"),
        FetchedPaper(title="a test paper", abstract="y"),
    ]

    unique = deduplicate_papers(papers)

    assert len(unique) == 1
    assert unique[0].abstract == "x"


def test_save_and_load_fetched_papers():
    path = _make_tmp_dir("fetched_papers") / "fetched.json"
    papers = [
        FetchedPaper(
            title="Test",
            abstract="abstract",
            doi="10.1/test",
            link="https://example.com",
            authors="A; B",
            venue="Journal",
            source_email_id="<id@example.com>",
            fetch_method="email",
        )
    ]

    saved = save_fetched_papers(papers, str(path))
    loaded = load_fetched_papers(str(saved))

    assert json.loads(path.read_text(encoding="utf-8"))[0]["title"] == "Test"
    assert loaded == papers


def test_fetch_papers_writes_audit(monkeypatch):
    tmp_dir = _make_tmp_dir("fetch_audit")
    output_path = tmp_dir / "fetched.json"
    audit_path = tmp_dir / "audit.json"

    monkeypatch.setattr(
        fetch_mod,
        "fetch_wos_emails_with_stats",
        lambda since_date, max_emails, ignore_seen=False: (
            [
                ("<1@example.com>", "Web of Science Alert", "<html>1</html>"),
                ("<2@example.com>", "Web of Science Alert", "<html>2</html>"),
            ],
            _email_stats(2),
        ),
    )
    monkeypatch.setattr(
        fetch_mod,
        "parse_wos_email",
        lambda html, source_email_id: [
            FetchedPaper(title="Same Paper", abstract="a", doi="10.1/same", source_email_id=source_email_id),
            FetchedPaper(title="Same Paper Duplicate", abstract="b", doi="10.1/same", source_email_id=source_email_id),
        ],
    )

    papers = fetch_mod.fetch_papers(
        since_date="2026-04-01",
        max_emails=2,
        no_web=True,
        output_path=str(output_path),
        audit_output_path=str(audit_path),
    )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert len(papers) == 1
    assert audit["since_date"] == "2026-04-01"
    assert audit["max_emails"] == 2
    assert audit["no_web"] is True
    assert audit["email_count"] == 2
    assert audit["parsed_paper_count"] == 4
    assert audit["unique_paper_count"] == 1
    assert audit["duplicate_paper_count"] == 3
    assert audit["output_path"] == str(output_path)
    assert audit["checked_email_count"] == 2
    assert audit["matched_wos_email_count"] == 2
    assert [item["subject"] for item in audit["email_details"]] == [
        "Web of Science Alert",
        "Web of Science Alert",
    ]
    assert [item["email_parsed_paper_count"] for item in audit["email_details"]] == [2, 2]


def test_fetch_papers_keeps_email_content_when_web_enrich_fails(monkeypatch):
    tmp_dir = _make_tmp_dir("fetch_web_fallback")
    output_path = tmp_dir / "fetched.json"
    audit_path = tmp_dir / "audit.json"

    monkeypatch.setattr(
        fetch_mod,
        "fetch_wos_emails_with_stats",
        lambda since_date, max_emails, ignore_seen=False: (
            [("<1@example.com>", "Web of Science Alert", "<html>1</html>")],
            _email_stats(1),
        ),
    )
    monkeypatch.setattr(
        fetch_mod,
        "parse_wos_email",
        lambda html, source_email_id: [
            FetchedPaper(title="Fallback Paper", abstract="from email", source_email_id=source_email_id),
        ],
    )

    def fail_enrich(paper):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(fetch_mod, "enrich_from_web", fail_enrich)

    papers = fetch_mod.fetch_papers(
        max_emails=1,
        no_web=False,
        output_path=str(output_path),
        audit_output_path=str(audit_path),
    )

    assert len(papers) == 1
    assert papers[0].title == "Fallback Paper"
    assert papers[0].abstract == "from email"
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["title"] == "Fallback Paper"


def test_fetch_papers_passes_ignore_seen(monkeypatch):
    tmp_dir = _make_tmp_dir("fetch_ignore_seen")
    output_path = tmp_dir / "fetched.json"
    audit_path = tmp_dir / "audit.json"
    calls = []

    def fake_fetch_wos_emails_with_stats(since_date, max_emails, ignore_seen=False):
        calls.append(ignore_seen)
        return ([("<1@example.com>", "Web of Science Alert", "<html>1</html>")], _email_stats(1))

    monkeypatch.setattr(fetch_mod, "fetch_wos_emails_with_stats", fake_fetch_wos_emails_with_stats)
    monkeypatch.setattr(
        fetch_mod,
        "parse_wos_email",
        lambda html, source_email_id: [
            FetchedPaper(title="Paper", abstract="abstract", source_email_id=source_email_id),
        ],
    )

    fetch_mod.fetch_papers(
        ignore_seen=True,
        no_web=True,
        output_path=str(output_path),
        audit_output_path=str(audit_path),
    )

    assert calls == [True]


def test_fetch_papers_expands_alert_summary_pages(monkeypatch):
    tmp_dir = _make_tmp_dir("fetch_expand_alert")
    output_path = tmp_dir / "fetched.json"
    audit_path = tmp_dir / "audit.json"

    monkeypatch.setattr(
        fetch_mod,
        "fetch_wos_emails_with_stats",
        lambda since_date, max_emails, ignore_seen=False: (
            [("<1@example.com>", "Web of Science Alert", "<html>email</html>")],
            _email_stats(1),
        ),
    )
    monkeypatch.setattr(
        fetch_mod,
        "parse_wos_email",
        lambda html, source_email_id: [
            FetchedPaper(title="Email Paper", abstract="email", source_email_id=source_email_id),
        ],
    )
    monkeypatch.setattr(
        fetch_mod,
        "extract_alert_summary_links",
        lambda html: ["https://www.webofscience.com/api/gateway?DestLinkType=AlertSummary"],
    )
    monkeypatch.setattr(
        fetch_mod,
        "_fetch_alert_summary_papers",
        lambda url, source_email_id: [
            FetchedPaper(title="Expanded Paper", abstract="expanded", source_email_id=source_email_id),
        ],
    )

    papers = fetch_mod.fetch_papers(
        no_web=True,
        expand_alert_pages=True,
        output_path=str(output_path),
        audit_output_path=str(audit_path),
    )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert [paper.title for paper in papers] == ["Email Paper", "Expanded Paper"]
    assert audit["alert_summary_link_count"] == 1
    assert audit["expanded_paper_count"] == 1


def test_fetch_papers_uses_browser_when_requests_expansion_empty(monkeypatch):
    tmp_dir = _make_tmp_dir("fetch_browser_expand")
    output_path = tmp_dir / "fetched.json"
    audit_path = tmp_dir / "audit.json"

    monkeypatch.setattr(
        fetch_mod,
        "fetch_wos_emails_with_stats",
        lambda since_date, max_emails, ignore_seen=False: (
            [("<1@example.com>", "Web of Science Alert", "<html>email</html>")],
            _email_stats(1),
        ),
    )
    monkeypatch.setattr(
        fetch_mod,
        "parse_wos_email",
        lambda html, source_email_id: [
            FetchedPaper(title="Email Paper", abstract="email", source_email_id=source_email_id),
        ],
    )
    monkeypatch.setattr(fetch_mod, "extract_alert_summary_links", lambda html: ["https://wos.example/summary"])
    monkeypatch.setattr(fetch_mod, "_fetch_alert_summary_papers", lambda url, source_email_id: [])

    browser_max_pages_seen = []
    manual_login_wait_seconds_seen = []

    def browser_fetch(url, source_email_id, max_pages, manual_login_wait_seconds=0):
        browser_max_pages_seen.append(max_pages)
        manual_login_wait_seconds_seen.append(manual_login_wait_seconds)
        return [FetchedPaper(title="Browser Paper", abstract="", source_email_id=source_email_id)]

    monkeypatch.setattr(
        fetch_mod,
        "fetch_wos_alert_with_browser",
        browser_fetch,
    )

    papers = fetch_mod.fetch_papers(
        no_web=True,
        expand_alert_pages=True,
        use_browser=True,
        browser_max_pages=12,
        browser_manual_login_wait_seconds=180,
        output_path=str(output_path),
        audit_output_path=str(audit_path),
    )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert [paper.title for paper in papers] == ["Email Paper", "Browser Paper"]
    assert audit["browser_expanded_paper_count"] == 1
    assert audit["browser_new_unique_paper_count"] == 1
    assert audit["browser_duplicate_paper_count"] == 0
    assert audit["browser_max_pages"] == 12
    assert audit["browser_manual_login_wait_seconds"] == 180
    assert audit["browser_expand_error_count"] == 0
    assert audit["browser_expand_last_error"] is None
    assert browser_max_pages_seen == [12]
    assert manual_login_wait_seconds_seen == [180]
    assert audit["email_details"][0]["email_parsed_paper_count"] == 1
    assert audit["email_details"][0]["browser_expanded_paper_count"] == 1
    assert audit["email_details"][0]["browser_new_unique_paper_count"] == 1
    assert audit["email_details"][0]["alert_links"][0]["url_summary"] == "wos.example/summary"


def test_fetch_papers_counts_browser_duplicates(monkeypatch):
    tmp_dir = _make_tmp_dir("fetch_browser_duplicate")
    output_path = tmp_dir / "fetched.json"
    audit_path = tmp_dir / "audit.json"

    monkeypatch.setattr(
        fetch_mod,
        "fetch_wos_emails_with_stats",
        lambda since_date, max_emails, ignore_seen=False: (
            [("<1@example.com>", "Web of Science Alert", "<html>email</html>")],
            _email_stats(1),
        ),
    )
    monkeypatch.setattr(
        fetch_mod,
        "parse_wos_email",
        lambda html, source_email_id: [
            FetchedPaper(title="Same Paper", abstract="email", source_email_id=source_email_id),
        ],
    )
    monkeypatch.setattr(fetch_mod, "extract_alert_summary_links", lambda html: ["https://wos.example/summary"])
    monkeypatch.setattr(fetch_mod, "_fetch_alert_summary_papers", lambda url, source_email_id: [])
    monkeypatch.setattr(
        fetch_mod,
        "fetch_wos_alert_with_browser",
        lambda url, source_email_id, max_pages, manual_login_wait_seconds=0: [
            FetchedPaper(title="Same Paper", abstract="", source_email_id=source_email_id),
        ],
    )

    papers = fetch_mod.fetch_papers(
        no_web=True,
        expand_alert_pages=True,
        use_browser=True,
        output_path=str(output_path),
        audit_output_path=str(audit_path),
    )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert [paper.title for paper in papers] == ["Same Paper"]
    assert audit["browser_expanded_paper_count"] == 1
    assert audit["browser_new_unique_paper_count"] == 0
    assert audit["browser_duplicate_paper_count"] == 1
    assert audit["email_details"][0]["browser_duplicate_paper_count"] == 1


def test_fetch_papers_records_browser_error_type(monkeypatch):
    tmp_dir = _make_tmp_dir("fetch_browser_error")
    output_path = tmp_dir / "fetched.json"
    audit_path = tmp_dir / "audit.json"

    monkeypatch.setattr(
        fetch_mod,
        "fetch_wos_emails_with_stats",
        lambda since_date, max_emails, ignore_seen=False: (
            [("<1@example.com>", "Web of Science Alert", "<html>email</html>")],
            _email_stats(1),
        ),
    )
    monkeypatch.setattr(fetch_mod, "parse_wos_email", lambda html, source_email_id: [])
    monkeypatch.setattr(fetch_mod, "extract_alert_summary_links", lambda html: ["https://wos.example/summary"])
    monkeypatch.setattr(fetch_mod, "_fetch_alert_summary_papers", lambda url, source_email_id: [])

    class EmptyError(Exception):
        def __str__(self) -> str:
            return ""

    def raise_empty_error(url, source_email_id, max_pages, manual_login_wait_seconds=0):
        raise EmptyError()

    monkeypatch.setattr(fetch_mod, "fetch_wos_alert_with_browser", raise_empty_error)

    fetch_mod.fetch_papers(
        no_web=True,
        expand_alert_pages=True,
        use_browser=True,
        output_path=str(output_path),
        audit_output_path=str(audit_path),
    )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["browser_expand_error_count"] == 1
    assert audit["browser_expand_last_error"].startswith("EmptyError:")


def test_format_exception_sanitizes_urls():
    exc = RuntimeError(
        "failed at https://access.clarivate.com/login?loginId=user@example.com&sid=secret"
    )

    message = fetch_mod._format_exception(exc)

    assert "access.clarivate.com/login" in message
    assert "user@example.com" not in message
    assert "sid=secret" not in message
