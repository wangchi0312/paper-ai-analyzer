from paper_analyzer.data.schema import Paper, PaperAnalysis


def _sample_analysis() -> PaperAnalysis:
    return PaperAnalysis(
        first_author="Zhang San",
        first_author_affiliation="PKU",
        second_author="Li Si",
        second_author_affiliation="THU",
        corresponding_author="Zhang San",
        corresponding_author_affiliation="PKU",
        publication_year="2024",
        paper_title="Test Paper",
        venue="NeurIPS",
        doi="10.1234/test",
        core_problem="test problem",
        core_hypotheses=["hypothesis 1", "hypothesis 2"],
        research_approach="experimental",
        key_methods="CNN",
        data_source_and_scale="synthetic, 10K",
        core_findings="test finding",
        main_conclusions="test conclusion",
        field_contribution="test contribution",
        relevance_to_my_research="test relevance",
        highlights="test highlight",
        limitations="test limitation",
    )


def test_paper_analysis_from_dict():
    data = {
        "first_author": "Zhang San",
        "first_author_affiliation": "PKU",
        "second_author": "Li Si",
        "second_author_affiliation": "THU",
        "corresponding_author": "Zhang San",
        "corresponding_author_affiliation": "PKU",
        "publication_year": "2024",
        "paper_title": "Test Paper",
        "venue": "NeurIPS",
        "doi": "10.1234/test",
        "core_problem": "test problem",
        "core_hypotheses": ["hypothesis 1"],
        "research_approach": "experimental",
        "key_methods": "CNN",
        "data_source_and_scale": "synthetic, 10K",
        "core_findings": "test finding",
        "main_conclusions": "test conclusion",
        "field_contribution": "test contribution",
        "relevance_to_my_research": "test relevance",
        "highlights": "test highlight",
        "limitations": "test limitation",
    }
    analysis = PaperAnalysis.from_dict(data)
    assert analysis.first_author == "Zhang San"
    assert analysis.core_hypotheses == ["hypothesis 1"]


def test_paper_analysis_from_dict_missing_fields():
    data = {"first_author": "Zhang San"}
    analysis = PaperAnalysis.from_dict(data)
    assert analysis.first_author == "Zhang San"
    assert analysis.venue == "未识别"
    assert analysis.core_hypotheses == ["未识别"]


def test_paper_analysis_from_dict_none_values():
    data = {"first_author": None, "venue": None}
    analysis = PaperAnalysis.from_dict(data)
    assert analysis.first_author == "未识别"
    assert analysis.venue == "未识别"


def test_paper_to_dict_excludes_full_text_and_embedding_by_default():
    paper = Paper(
        title="Test",
        source_path="/tmp/test.pdf",
        abstract="abst",
        selected_text="text",
        full_text="long text",
        embedding=[0.1, 0.2],
        score=0.8,
        analysis=_sample_analysis(),
    )
    d = paper.to_dict()
    assert "full_text" not in d
    assert "embedding" not in d
    assert d["title"] == "Test"
    assert d["score"] == 0.8


def test_paper_to_dict_includes_full_text_when_requested():
    paper = Paper(
        title="Test",
        source_path="/tmp/test.pdf",
        abstract="abst",
        selected_text="text",
        full_text="long text",
        embedding=[0.1],
    )
    d = paper.to_dict(include_full_text=True)
    assert d["full_text"] == "long text"
    assert "embedding" not in d


def test_paper_to_dict_includes_embedding_when_requested():
    paper = Paper(
        title="Test",
        source_path="/tmp/test.pdf",
        abstract="abst",
        selected_text="text",
        full_text="long text",
        embedding=[0.1, 0.2],
    )
    d = paper.to_dict(include_embedding=True)
    assert d["embedding"] == [0.1, 0.2]
    assert "full_text" not in d


def test_paper_analysis_roundtrip():
    analysis = _sample_analysis()
    paper = Paper(
        title="Test",
        source_path="/tmp/test.pdf",
        abstract="abst",
        selected_text="text",
        full_text="long text",
        embedding=[],
        score=0.9,
        analysis=analysis,
    )
    d = paper.to_dict(include_full_text=True, include_embedding=True)
    assert d["analysis"]["first_author"] == "Zhang San"
    assert d["analysis"]["core_hypotheses"] == ["hypothesis 1", "hypothesis 2"]
