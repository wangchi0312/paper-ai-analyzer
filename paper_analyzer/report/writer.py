from datetime import datetime
import json
from pathlib import Path

from paper_analyzer.data.schema import Paper, PaperAnalysis


def write_outputs(papers: list[Paper], output_root: str = "data/outputs") -> Path:
    output_dir = Path(output_root) / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    results_path = output_dir / "results.json"
    report_path = output_dir / "report.md"

    results = [paper.to_dict() for paper in papers]
    results_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path.write_text(_build_markdown(papers), encoding="utf-8")

    return output_dir


def _build_markdown(papers: list[Paper]) -> str:
    lines = ["# 文献总结（精简版）", ""]
    for index, paper in enumerate(papers, start=1):
        if len(papers) > 1:
            lines.extend([f"<!-- Paper {index}: {paper.title} -->", ""])

        score = "无" if paper.score is None else f"{paper.score:.4f}"
        lines.append(f"**相关性分数**：{score}")
        lines.append("")

        if paper.analysis:
            lines.extend(_analysis_markdown(paper.analysis))
        else:
            lines.extend(
                [
                    "## 1. 基本信息",
                    f"- **论文标题**：{paper.title}",
                    "",
                    "## 分析状态",
                    f"- 跳过原因：{paper.skipped_reason or '未分析'}",
                ]
            )

        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _analysis_markdown(analysis: PaperAnalysis) -> list[str]:
    hypotheses = analysis.core_hypotheses or ["未识别"]
    hypothesis_lines = [f"{idx}. {item}" for idx, item in enumerate(hypotheses, start=1)]

    return [
        "## 1. 基本信息",
        f"- **第一作者**：{_author_line(analysis.first_author, analysis.first_author_affiliation)}",
        f"- **第二作者**：{_author_line(analysis.second_author, analysis.second_author_affiliation)}",
        f"- **通讯作者**：{_author_line(analysis.corresponding_author, analysis.corresponding_author_affiliation)}",
        f"- **发表年份**：{analysis.publication_year}",
        f"- **论文标题**：{analysis.paper_title}",
        f"- **期刊/会议名称**：{analysis.venue}",
        f"- **DOI**：{analysis.doi}",
        "",
        "---",
        "",
        "## 2. 核心问题",
        "本研究要解决的关键科学/技术问题：",
        f"> {analysis.core_problem}",
        "",
        "---",
        "",
        "## 3. 核心假设/理论",
        "作者提出的核心研究假设或理论构想：",
        *hypothesis_lines,
        "",
        "---",
        "",
        "## 4. 研究思路",
        "整体研究设计（理论/仿真/实验/案例等）：",
        f"> {analysis.research_approach}",
        "",
        "---",
        "",
        "## 5. 方法与数据",
        f"- 关键方法/模型：{analysis.key_methods}",
        f"- 数据来源与规模：{analysis.data_source_and_scale}",
        "",
        "---",
        "",
        "## 6. 核心发现",
        "最重要、最创新的科学发现：",
        f"> {analysis.core_findings}",
        "",
        "---",
        "",
        "## 7. 主要结论",
        "作者基于证据得出的最终结论：",
        f"> {analysis.main_conclusions}",
        "",
        "---",
        "",
        "## 8. 领域贡献",
        "对本领域的理论/方法/应用贡献：",
        f"> {analysis.field_contribution}",
        "",
        "---",
        "",
        "## 9. 与我的研究关联",
        "和我的研究主题/综述方向的核心交集：",
        f"> {analysis.relevance_to_my_research}",
        "",
        "---",
        "",
        "## 10. 启发与不足",
        f"- 亮点/启发：{analysis.highlights}",
        f"- 局限/疑问：{analysis.limitations}",
    ]


def _author_line(name: str, affiliation: str) -> str:
    return f"{name} / {affiliation}"
