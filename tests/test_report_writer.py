import json
from pathlib import Path

from paper_analyzer.data.schema import Paper, PaperAnalysis
from paper_analyzer.report.writer import write_outputs


def test_write_outputs():
    paper = Paper(
        title="Example",
        source_path="example.pdf",
        abstract="abstract",
        selected_text="selected",
        full_text="full",
        embedding=[0.1, 0.2],
        score=0.8,
        analysis=PaperAnalysis(
            first_author="A",
            first_author_affiliation="Lab A",
            second_author="B",
            second_author_affiliation="Lab B",
            corresponding_author="C",
            corresponding_author_affiliation="Lab C",
            publication_year="2026",
            paper_title="Example Paper",
            venue="Journal",
            doi="10.0000/example",
            core_problem="problem",
            core_hypotheses=["hypothesis 1", "hypothesis 2"],
            research_approach="approach",
            key_methods="methods",
            data_source_and_scale="data",
            core_findings="findings",
            main_conclusions="conclusions",
            field_contribution="contribution",
            relevance_to_my_research="relevance",
            highlights="highlights",
            limitations="limitations",
        ),
    )

    output_dir = write_outputs([paper], output_root=str(Path("data/outputs/test_report_writer")))

    assert (output_dir / "results.json").exists()
    assert (output_dir / "report.md").exists()
    assert (output_dir / "weekly_report.md").exists()

    results = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    assert results[0]["title"] == "Example"
    assert "embedding" not in results[0]
    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "# 文献总结（精简版）" in report
    assert "## 10. 启发与不足" in report
    weekly_report = (output_dir / "weekly_report.md").read_text(encoding="utf-8")
    assert "# 文献追踪周报" in weekly_report
    assert "## 二、重点推荐" in weekly_report
