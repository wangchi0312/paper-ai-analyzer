from datetime import datetime

from paper_analyzer.data.schema import Paper


def build_weekly_report(
    papers: list[Paper],
    research_topic: str | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Build a reader-facing weekly literature report from analyzed papers."""
    now = generated_at or datetime.now()
    analyzed = [paper for paper in papers if paper.analysis is not None]
    skipped = [paper for paper in papers if paper.analysis is None]
    ranked = sorted(papers, key=lambda paper: paper.score if paper.score is not None else -1, reverse=True)
    highlights = sorted(analyzed, key=lambda paper: paper.score if paper.score is not None else -1, reverse=True)

    lines = [
        "# 文献追踪周报",
        "",
        f"- 生成时间：{now.strftime('%Y-%m-%d %H:%M')}",
        f"- 研究主题：{research_topic or '未配置'}",
        f"- 本次候选论文：{len(papers)} 篇",
        f"- 深度解读论文：{len(analyzed)} 篇",
        f"- 跳过论文：{len(skipped)} 篇",
        "",
        "## 一、本周概览",
        "",
        _overview_text(papers, analyzed),
        "",
        "## 二、重点推荐",
        "",
    ]

    if highlights:
        for index, paper in enumerate(highlights[:5], start=1):
            analysis = paper.analysis
            assert analysis is not None
            lines.extend(
                [
                    f"### {index}. {paper.title}",
                    "",
                    f"- 相关性分数：{_score_text(paper)}",
                    f"- 来源：{analysis.venue}",
                    f"- DOI：{analysis.doi}",
                    f"- 链接：{paper.link or '未提供'}",
                    f"- 核心问题：{analysis.core_problem}",
                    f"- 主要贡献：{analysis.field_contribution}",
                    f"- 与我研究的关联：{analysis.relevance_to_my_research}",
                    f"- 建议关注点：{analysis.highlights}",
                    "",
                ]
            )
    else:
        lines.extend(["本次没有完成 LLM 深度解读的论文。", ""])

    lines.extend(
        [
            "## 三、候选论文排序",
            "",
            "| 排名 | 相关性 | 标题 | 状态 |",
            "|---:|---:|---|---|",
        ]
    )
    for index, paper in enumerate(ranked, start=1):
        status = "已深度解读" if paper.analysis else (paper.skipped_reason or "未分析")
        lines.append(f"| {index} | {_score_text(paper)} | {_escape_table(paper.title)} | {_escape_table(status)} |")

    lines.extend(["", "## 四、逐篇深度解读", ""])
    if analyzed:
        for index, paper in enumerate(highlights, start=1):
            analysis = paper.analysis
            assert analysis is not None
            lines.extend(
                [
                    f"### {index}. {paper.title}",
                    "",
                    f"- 作者：{analysis.first_author}；通讯作者：{analysis.corresponding_author}",
                    f"- 发表信息：{analysis.publication_year}，{analysis.venue}",
                    f"- 方法：{analysis.key_methods}",
                    f"- 发现：{analysis.core_findings}",
                    f"- 结论：{analysis.main_conclusions}",
                    f"- 局限：{analysis.limitations}",
                    "",
                ]
            )
    else:
        lines.extend(["暂无。", ""])

    return "\n".join(lines).strip() + "\n"


def _overview_text(papers: list[Paper], analyzed: list[Paper]) -> str:
    if not papers:
        return "本次没有可汇总的论文。"
    if not analyzed:
        return "本次完成了候选论文筛选，但没有进入深度解读的论文；建议降低阈值或增大 top-k 后重试。"

    top_methods = [paper.analysis.key_methods for paper in analyzed if paper.analysis and paper.analysis.key_methods != "未识别"]
    if top_methods:
        return f"本次最值得关注的方向集中在：{'；'.join(top_methods[:3])}。建议优先阅读重点推荐中的前几篇论文。"
    return "本次已完成高相关论文深度解读，建议优先阅读重点推荐中的前几篇论文。"


def _score_text(paper: Paper) -> str:
    return "无" if paper.score is None else f"{paper.score:.4f}"


def _escape_table(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
