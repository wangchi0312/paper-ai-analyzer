from pathlib import Path

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.downloader import safe_pdf_name
from paper_analyzer.fulltext.resolver import _candidate_pdf_urls


def test_safe_pdf_name():
    name = safe_pdf_name("A/B: Test Paper?", 3)
    assert name.startswith("03_")
    assert name.endswith(".pdf")
    assert "/" not in name


def test_candidate_pdf_urls_includes_direct_pdf_link(monkeypatch):
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._unpaywall_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._semantic_scholar_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._arxiv_candidates", lambda *args, **kwargs: [])

    paper = FetchedPaper(title="T", abstract="A", link="https://example.com/paper.pdf")

    candidates = _candidate_pdf_urls(paper)

    assert candidates == [("publisher", "https://example.com/paper.pdf")]


def test_candidate_pdf_urls_deduplicates(monkeypatch):
    monkeypatch.setattr(
        "paper_analyzer.fulltext.resolver._unpaywall_candidates",
        lambda *args, **kwargs: [("unpaywall", "https://example.com/paper.pdf")],
    )
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._semantic_scholar_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("paper_analyzer.fulltext.resolver._arxiv_candidates", lambda *args, **kwargs: [])

    paper = FetchedPaper(title="T", abstract="A", doi="10.1/test", link="https://example.com/paper.pdf")

    candidates = _candidate_pdf_urls(paper, unpaywall_email="a@example.com")

    assert candidates == [("publisher", "https://example.com/paper.pdf")]
