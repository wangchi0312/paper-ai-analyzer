import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from paper_analyzer.data.schema import FetchedPaper
from pipeline.fetch_papers import (
    PAPER_LIBRARY_PATH,
    _append_to_paper_library,
    deduplicate_papers,
    load_paper_library,
    reset_paper_library,
    save_fetched_papers,
)


def _make_paper(title: str, doi: str | None = None, fetch_date: str | None = None) -> FetchedPaper:
    return FetchedPaper(
        title=title,
        abstract="test abstract",
        doi=doi,
        fetch_date=fetch_date,
    )


class TestAppendToPaperLibrary:
    def test_first_append_creates_library(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp()) / "paper_library.json"
        monkeypatch.setattr(
            "pipeline.fetch_papers.PAPER_LIBRARY_PATH", str(tmp)
        )
        papers = [_make_paper("Paper A", doi="10.1000/1")]
        added = _append_to_paper_library(papers)
        assert added == 1
        assert tmp.exists()
        loaded = load_paper_library(str(tmp))
        assert len(loaded) == 1
        assert loaded[0].fetch_date == datetime.now().strftime("%Y-%m-%d")

    def test_second_append_deduplicates(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp()) / "paper_library.json"
        monkeypatch.setattr(
            "pipeline.fetch_papers.PAPER_LIBRARY_PATH", str(tmp)
        )
        first = [_make_paper("Paper A", doi="10.1000/1")]
        _append_to_paper_library(first)
        second = [_make_paper("Paper A", doi="10.1000/1"), _make_paper("Paper B")]
        added = _append_to_paper_library(second)
        assert added == 1
        loaded = load_paper_library(str(tmp))
        assert len(loaded) == 2

    def test_title_dedup_when_no_doi(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp()) / "paper_library.json"
        monkeypatch.setattr(
            "pipeline.fetch_papers.PAPER_LIBRARY_PATH", str(tmp)
        )
        _append_to_paper_library([_make_paper("Deep Learning for NLP")])
        added = _append_to_paper_library([_make_paper("Deep  Learning  for  NLP")])
        assert added == 0


class TestLoadPaperLibrary:
    def test_load_empty_when_no_file(self):
        papers = load_paper_library("nonexistent/path.json")
        assert papers == []

    def test_load_with_since_filter(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp()) / "paper_library.json"
        monkeypatch.setattr(
            "pipeline.fetch_papers.PAPER_LIBRARY_PATH", str(tmp)
        )
        papers = [
            FetchedPaper(title="Old", abstract="", fetch_date="2025-01-01"),
            FetchedPaper(title="New", abstract="", fetch_date="2026-01-01"),
        ]
        save_fetched_papers(papers, str(tmp), append_to_library=False)
        filtered = load_paper_library(str(tmp), since="2025-06-01")
        assert len(filtered) == 1
        assert filtered[0].title == "New"


class TestResetPaperLibrary:
    def test_reset_removes_file(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp()) / "paper_library.json"
        monkeypatch.setattr(
            "pipeline.fetch_papers.PAPER_LIBRARY_PATH", str(tmp)
        )
        _append_to_paper_library([_make_paper("Paper A")])
        assert tmp.exists()
        reset_paper_library(str(tmp))
        assert not tmp.exists()


class TestDeduplicatePapers:
    def test_dedup_by_doi(self):
        papers = [
            _make_paper("A", doi="10.1000/1"),
            _make_paper("A duplicate", doi="10.1000/1"),
            _make_paper("B", doi="10.1000/2"),
        ]
        unique = deduplicate_papers(papers)
        assert len(unique) == 2

    def test_dedup_by_normalized_title(self):
        papers = [
            _make_paper("Deep Learning for NLP"),
            _make_paper("Deep  Learning  for  NLP"),
            _make_paper("Machine Learning"),
        ]
        unique = deduplicate_papers(papers)
        assert len(unique) == 2
