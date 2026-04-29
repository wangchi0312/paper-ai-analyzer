import json
import shutil
from pathlib import Path

import numpy as np

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.source import FullTextResult
from pipeline import analyze_papers as analyze_mod


class FakeEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def encode(self, texts):
        if isinstance(texts, str):
            return np.array([1.0, 0.0])
        return np.array([[1.0, 0.0] for _ in texts])


class RankedFakeEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def encode(self, texts):
        return np.array(
            [
                [1.0, 0.0],
                [0.8, 0.6],
                [0.6, 0.8],
            ]
        )


class FakeAnalyzer:
    def __init__(self, provider=None):
        self.provider = provider

    def analyze(self, text, research_topic=None):
        from paper_analyzer.data.schema import PaperAnalysis

        return PaperAnalysis.from_dict(
            {
                "first_author": "A",
                "paper_title": text,
                "core_hypotheses": ["H"],
            }
        )


class MetadataAwareFakeAnalyzer:
    def __init__(self, provider=None):
        self.provider = provider

    def analyze(self, text, research_topic=None):
        from paper_analyzer.data.schema import PaperAnalysis

        assert "标题：Metadata Paper" in text
        assert "作者：Alice; Bob" in text
        assert "期刊/会议：Journal X" in text
        assert "DOI：10.1/meta" in text
        return PaperAnalysis.from_dict(
            {
                "paper_title": "未识别",
                "first_author": "未识别",
                "second_author": "未识别",
                "venue": "未识别",
                "doi": "未识别",
                "core_hypotheses": ["H"],
            }
        )


def _make_tmp_dir(name: str) -> Path:
    path = Path("data/outputs/test_tmp") / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def test_analyze_fetched_papers_skip_llm(monkeypatch):
    tmp_path = _make_tmp_dir("analyze_fetched")
    profile_path = tmp_path / "profile.npy"
    np.save(profile_path, np.array([1.0, 0.0]))
    monkeypatch.setattr(analyze_mod, "Embedder", FakeEmbedder)

    papers = [
        FetchedPaper(
            title="Fetched Paper",
            abstract="This is an abstract.",
            link="https://example.com/paper",
            source_email_id="<id@example.com>",
        )
    ]

    output_dir = analyze_mod.analyze_papers(
        papers=papers,
        profile_path=str(profile_path),
        output_root=str(tmp_path / "outputs"),
        skip_llm=True,
    )

    results = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    assert results[0]["title"] == "Fetched Paper"
    assert results[0]["source_path"] is None
    assert results[0]["link"] == "https://example.com/paper"
    assert results[0]["score"] == 1.0
    assert results[0]["skipped_reason"] == "用户指定跳过 LLM 分析"


def test_analyze_fetched_papers_skip_llm_ignores_top_k(monkeypatch):
    tmp_path = _make_tmp_dir("analyze_fetched_skip_top_k")
    profile_path = tmp_path / "profile.npy"
    np.save(profile_path, np.array([1.0, 0.0]))
    monkeypatch.setattr(analyze_mod, "Embedder", RankedFakeEmbedder)

    papers = [
        FetchedPaper(title="Top 1", abstract="top one"),
        FetchedPaper(title="Top 2", abstract="top two"),
        FetchedPaper(title="Top 3", abstract="top three"),
    ]

    output_dir = analyze_mod.analyze_papers(
        papers=papers,
        profile_path=str(profile_path),
        threshold=0.0,
        output_root=str(tmp_path / "outputs"),
        skip_llm=True,
        top_k=1,
    )

    results = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    assert [item["skipped_reason"] for item in results] == ["用户指定跳过 LLM 分析"] * 3


def test_analyze_fetched_papers_downloads_full_text_with_skip_llm(monkeypatch):
    tmp_path = _make_tmp_dir("analyze_fetched_download_skip_llm")
    profile_path = tmp_path / "profile.npy"
    np.save(profile_path, np.array([1.0, 0.0]))
    monkeypatch.setattr(analyze_mod, "Embedder", FakeEmbedder)
    monkeypatch.setattr(
        analyze_mod,
        "resolve_full_text",
        lambda paper, output_dir, index, unpaywall_email, timeout=10: FullTextResult(
            success=True,
            path=str(output_dir / "paper.pdf"),
            source="test",
            url="https://example.com/paper.pdf",
        ),
    )
    monkeypatch.setattr(analyze_mod, "extract_text", lambda path: "downloaded full text")

    class FailingAnalyzer:
        def __init__(self, provider=None):
            raise AssertionError("LLM should not be initialized")

    monkeypatch.setattr(analyze_mod, "Analyzer", FailingAnalyzer)

    output_dir = analyze_mod.analyze_papers(
        papers=[FetchedPaper(title="PDF Paper", abstract="abstract")],
        profile_path=str(profile_path),
        threshold=0.0,
        output_root=str(tmp_path / "outputs"),
        download_full_text=True,
        skip_llm=True,
    )

    results = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    assert results[0]["analysis"] is None
    assert results[0]["full_text_status"] == "downloaded"
    assert results[0]["full_text_source"] == "test"
    assert results[0]["selected_text"] == "downloaded full text"
    assert results[0]["skipped_reason"] == "用户指定跳过 LLM 分析"


def test_analyze_fetched_papers_download_skip_llm_respects_top_k(monkeypatch):
    tmp_path = _make_tmp_dir("analyze_fetched_download_skip_top_k")
    profile_path = tmp_path / "profile.npy"
    np.save(profile_path, np.array([1.0, 0.0]))
    monkeypatch.setattr(analyze_mod, "Embedder", RankedFakeEmbedder)

    downloaded_titles = []

    def fake_resolve_full_text(paper, output_dir, index, unpaywall_email, timeout=10):
        downloaded_titles.append(paper.title)
        return FullTextResult(
            success=True,
            path=str(output_dir / f"{index}.pdf"),
            source="test",
            url="https://example.com/paper.pdf",
        )

    monkeypatch.setattr(analyze_mod, "resolve_full_text", fake_resolve_full_text)
    monkeypatch.setattr(analyze_mod, "extract_text", lambda path: "downloaded full text")

    output_dir = analyze_mod.analyze_papers(
        papers=[
            FetchedPaper(title="Top 1", abstract="top one"),
            FetchedPaper(title="Top 2", abstract="top two"),
            FetchedPaper(title="Top 3", abstract="top three"),
        ],
        profile_path=str(profile_path),
        threshold=0.0,
        output_root=str(tmp_path / "outputs"),
        download_full_text=True,
        skip_llm=True,
        top_k=1,
    )

    results = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    assert downloaded_titles == ["Top 1"]
    assert results[0]["full_text_status"] == "downloaded"
    assert results[1]["skipped_reason"] == "相似度 0.8000 达到阈值，但未进入 top-1"
    assert results[2]["skipped_reason"] == "相似度 0.6000 达到阈值，但未进入 top-1"


def test_analyze_fetched_papers_passes_full_text_timeout(monkeypatch):
    tmp_path = _make_tmp_dir("analyze_fetched_download_timeout")
    profile_path = tmp_path / "profile.npy"
    np.save(profile_path, np.array([1.0, 0.0]))
    monkeypatch.setattr(analyze_mod, "Embedder", FakeEmbedder)
    seen_timeouts = []

    def fake_resolve_full_text(paper, output_dir, index, unpaywall_email, timeout=10):
        seen_timeouts.append(timeout)
        return FullTextResult(success=False, reason="not found")

    monkeypatch.setattr(analyze_mod, "resolve_full_text", fake_resolve_full_text)

    analyze_mod.analyze_papers(
        papers=[FetchedPaper(title="Timeout Paper", abstract="abstract")],
        profile_path=str(profile_path),
        threshold=0.0,
        output_root=str(tmp_path / "outputs"),
        download_full_text=True,
        full_text_timeout=4,
    )

    assert seen_timeouts == [4]


def test_analyze_fetched_papers_top_k_limits_llm(monkeypatch):
    tmp_path = _make_tmp_dir("analyze_fetched_top_k")
    profile_path = tmp_path / "profile.npy"
    np.save(profile_path, np.array([1.0, 0.0]))
    monkeypatch.setattr(analyze_mod, "Embedder", RankedFakeEmbedder)
    monkeypatch.setattr(analyze_mod, "Analyzer", FakeAnalyzer)

    papers = [
        FetchedPaper(title="Top 1", abstract="top one"),
        FetchedPaper(title="Top 2", abstract="top two"),
        FetchedPaper(title="Top 3", abstract="top three"),
    ]

    output_dir = analyze_mod.analyze_papers(
        papers=papers,
        profile_path=str(profile_path),
        threshold=0.0,
        output_root=str(tmp_path / "outputs"),
        top_k=2,
    )

    results = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    assert results[0]["analysis"] is not None
    assert results[1]["analysis"] is not None
    assert results[2]["analysis"] is None
    assert results[2]["skipped_reason"] == "相似度 0.6000 达到阈值，但未进入 top-2"


def test_analyze_fetched_papers_uses_metadata_for_llm_and_backfill(monkeypatch):
    tmp_path = _make_tmp_dir("analyze_fetched_metadata")
    profile_path = tmp_path / "profile.npy"
    np.save(profile_path, np.array([1.0, 0.0]))
    monkeypatch.setattr(analyze_mod, "Embedder", FakeEmbedder)
    monkeypatch.setattr(analyze_mod, "Analyzer", MetadataAwareFakeAnalyzer)

    papers = [
        FetchedPaper(
            title="Metadata Paper",
            abstract="abstract",
            doi="10.1/meta",
            authors="Alice; Bob",
            venue="Journal X",
        )
    ]

    output_dir = analyze_mod.analyze_papers(
        papers=papers,
        profile_path=str(profile_path),
        threshold=0.0,
        output_root=str(tmp_path / "outputs"),
    )

    results = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    analysis = results[0]["analysis"]
    assert analysis["paper_title"] == "Metadata Paper"
    assert analysis["first_author"] == "Alice"
    assert analysis["second_author"] == "Bob"
    assert analysis["venue"] == "Journal X"
    assert analysis["doi"] == "10.1/meta"


def test_analyze_fetched_papers_downloads_full_text_before_llm(monkeypatch):
    tmp_path = _make_tmp_dir("analyze_fetched_fulltext")
    profile_path = tmp_path / "profile.npy"
    np.save(profile_path, np.array([1.0, 0.0]))
    monkeypatch.setattr(analyze_mod, "Embedder", FakeEmbedder)
    monkeypatch.setattr(analyze_mod, "Analyzer", MetadataAwareFakeAnalyzer)
    monkeypatch.setattr(
        analyze_mod,
        "resolve_full_text",
        lambda paper, output_dir, index, unpaywall_email, timeout=10: FullTextResult(
            success=True,
            path=str(output_dir / "paper.pdf"),
            source="test",
            url="https://example.com/paper.pdf",
        ),
    )
    monkeypatch.setattr(
        analyze_mod,
        "extract_text",
        lambda path: "标题：Metadata Paper\n作者：Alice; Bob\n期刊/会议：Journal X\nDOI：10.1/meta\nfull text body",
    )

    output_dir = analyze_mod.analyze_papers(
        papers=[
            FetchedPaper(
                title="Metadata Paper",
                abstract="abstract",
                doi="10.1/meta",
                authors="Alice; Bob",
                venue="Journal X",
            )
        ],
        profile_path=str(profile_path),
        threshold=0.0,
        output_root=str(tmp_path / "outputs"),
        download_full_text=True,
    )

    results = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    assert results[0]["full_text_status"] == "downloaded"
    assert results[0]["full_text_source"] == "test"
    assert results[0]["full_text_path"].endswith("paper.pdf")
    assert results[0]["analysis"]["paper_title"] == "Metadata Paper"


def test_analyze_fetched_papers_skips_llm_when_full_text_download_fails(monkeypatch):
    tmp_path = _make_tmp_dir("analyze_fetched_fulltext_fail")
    profile_path = tmp_path / "profile.npy"
    np.save(profile_path, np.array([1.0, 0.0]))
    monkeypatch.setattr(analyze_mod, "Embedder", FakeEmbedder)
    monkeypatch.setattr(
        analyze_mod,
        "resolve_full_text",
        lambda paper, output_dir, index, unpaywall_email, timeout=10: FullTextResult(success=False, reason="not found"),
    )

    output_dir = analyze_mod.analyze_papers(
        papers=[FetchedPaper(title="No PDF", abstract="abstract")],
        profile_path=str(profile_path),
        threshold=0.0,
        output_root=str(tmp_path / "outputs"),
        download_full_text=True,
    )

    results = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    assert results[0]["analysis"] is None
    assert results[0]["full_text_status"] == "failed"
    assert results[0]["skipped_reason"] == "全文获取失败：not found"
