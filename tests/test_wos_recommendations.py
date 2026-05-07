from pathlib import Path

from paper_analyzer.agent.memory import AcademicMemory
from paper_analyzer.agent.tools import screen_wos_alert_tool
from paper_analyzer.data.schema import FetchedPaper


def test_screen_wos_alert_returns_doi_and_abstract(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "paper_analyzer.agent.tools.fetch_papers",
        lambda **kwargs: [
            FetchedPaper(
                title="Useful PINN Paper",
                abstract="This abstract explains why the method is useful for physics informed neural networks.",
                doi="10.1234/example",
                authors="Alice; Bob",
                venue="Journal of Scientific ML",
                link="https://wos.example/full-record",
                publisher_link="https://publisher.example/paper",
            )
        ],
    )

    result = screen_wos_alert_tool(
        memory=AcademicMemory(str(tmp_path / "memory")),
        top_k=1,
        use_web=True,
        profile_path=str(tmp_path / "missing.npy"),
    )

    rec = result.data["recommendations"][0]
    assert result.ok is True
    assert rec["doi"] == "10.1234/example"
    assert rec["doi_source"] == "wos"
    assert rec["abstract"].startswith("This abstract")
    assert rec["authors"] == "Alice; Bob"
    assert rec["publisher_link"] == "https://publisher.example/paper"
    assert rec["manual_pdf_advice"]


def test_screen_wos_alert_enriches_missing_doi_from_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "paper_analyzer.agent.tools.fetch_papers",
        lambda **kwargs: [
            FetchedPaper(
                title="Useful PINN Paper",
                abstract="This abstract explains why the method is useful for physics informed neural networks.",
                doi=None,
                authors="",
                venue="",
                link="https://wos.example/full-record",
                publisher_link="",
                fetch_method="wos_browser",
            )
        ],
    )
    monkeypatch.setattr("paper_analyzer.agent.tools.WosBrowserSession", None)

    def fake_enrich(paper):
        paper.doi = "10.5678/from-crossref"
        paper.fetch_method = "wos_browser+crossref"
        return paper

    monkeypatch.setattr("paper_analyzer.agent.tools.enrich_paper_metadata", fake_enrich)

    result = screen_wos_alert_tool(
        memory=AcademicMemory(str(tmp_path / "memory")),
        top_k=1,
        use_web=True,
        use_browser=False,
        profile_path=str(tmp_path / "missing.npy"),
    )

    rec = result.data["recommendations"][0]
    assert rec["doi"] == "10.5678/from-crossref"
    assert rec["doi_source"] == "crossref"
    assert rec["doi_status"] == "found"


def test_screen_wos_alert_enriches_missing_doi_from_full_record(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "paper_analyzer.agent.tools.fetch_papers",
        lambda **kwargs: [
            FetchedPaper(
                title="Useful PINN Paper",
                abstract="This abstract explains why the method is useful for physics informed neural networks.",
                doi=None,
                authors="",
                venue="",
                link="https://wos.example/full-record/WOS:1",
                publisher_link="",
                fetch_method="wos_browser",
            )
        ],
    )
    monkeypatch.setattr("paper_analyzer.agent.tools.enrich_paper_metadata", lambda paper: paper)

    class FakeBrowserSession:
        def __init__(self, max_pages, headless=False, manual_login_wait_seconds=0):
            self.max_pages = max_pages

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def enrich_paper_from_full_record(self, paper):
            paper.doi = "10.9999/from-full-record"
            return paper

    monkeypatch.setattr("paper_analyzer.agent.tools.WosBrowserSession", FakeBrowserSession)

    result = screen_wos_alert_tool(
        memory=AcademicMemory(str(tmp_path / "memory")),
        top_k=1,
        use_web=True,
        use_browser=True,
        profile_path=str(tmp_path / "missing.npy"),
    )

    rec = result.data["recommendations"][0]
    assert rec["doi"] == "10.9999/from-full-record"
    assert rec["doi_source"] == "full_record"
    assert rec["doi_status"] == "found"
