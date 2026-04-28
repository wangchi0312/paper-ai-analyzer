from datetime import datetime

from paper_analyzer.data.schema import Paper, PaperAnalysis
from paper_analyzer.report.weekly import build_weekly_report


def test_build_weekly_report_with_analysis():
    paper = Paper(
        title="Adaptive PINN",
        link="https://example.com",
        score=0.91,
        analysis=PaperAnalysis.from_dict(
            {
                "first_author": "A",
                "corresponding_author": "C",
                "publication_year": "2026",
                "paper_title": "Adaptive PINN",
                "venue": "Journal",
                "doi": "10.1/test",
                "core_problem": "solve PDEs",
                "key_methods": "adaptive activation",
                "core_findings": "better convergence",
                "main_conclusions": "works well",
                "field_contribution": "improves PINNs",
                "relevance_to_my_research": "directly relevant",
                "highlights": "useful baseline",
                "limitations": "small benchmark",
                "core_hypotheses": ["H"],
            }
        ),
    )

    report = build_weekly_report(
        [paper],
        research_topic="PINNs",
        generated_at=datetime(2026, 4, 28, 10, 30),
    )

    assert "# 文献追踪周报" in report
    assert "生成时间：2026-04-28 10:30" in report
    assert "研究主题：PINNs" in report
    assert "Adaptive PINN" in report
    assert "0.9100" in report
    assert "directly relevant" in report


def test_build_weekly_report_without_analysis():
    paper = Paper(title="Skipped", score=0.4, skipped_reason="相似度低")

    report = build_weekly_report([paper], research_topic="PINNs")

    assert "深度解读论文：0 篇" in report
    assert "本次没有完成 LLM 深度解读的论文" in report
    assert "相似度低" in report
