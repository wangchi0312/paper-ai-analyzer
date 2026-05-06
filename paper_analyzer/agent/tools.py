from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from paper_analyzer.agent.memory import AcademicMemory
from paper_analyzer.agent.state import ToolResult, utc_now_iso
from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.embedding.embedder import Embedder
from paper_analyzer.embedding.similarity import cosine_similarity
from paper_analyzer.ingestion.email_reader import fetch_wos_emails_with_stats
from paper_analyzer.ingestion.wos_parser import extract_alert_summary_links, parse_wos_email
from paper_analyzer.llm.analyzer import Analyzer
from paper_analyzer.pdf.parser import extract_text, extract_title
from paper_analyzer.pdf.text_selector import select_representative_text
from paper_analyzer.report.writer import write_outputs


@dataclass
class AgentTool:
    name: str
    description: str
    handler: Callable[..., ToolResult]
    requires_confirmation: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool:
        if name not in self._tools:
            raise KeyError(f"Unknown agent tool: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)


def build_default_registry(memory: AcademicMemory | None = None) -> ToolRegistry:
    memory = memory or AcademicMemory()
    registry = ToolRegistry()
    registry.register(AgentTool("analyze_pdf_tool", "解读用户上传的 PDF", lambda **kw: analyze_pdf_tool(memory=memory, **kw)))
    registry.register(AgentTool("screen_wos_alert_tool", "筛选 WoS Alert 候选论文，不下载全文", lambda **kw: screen_wos_alert_tool(memory=memory, **kw)))
    registry.register(AgentTool("search_memory_tool", "检索论文知识库和兴趣记忆", lambda **kw: search_memory_tool(memory=memory, **kw), requires_confirmation=False))
    registry.register(AgentTool("update_memory_tool", "根据用户反馈更新长期兴趣记忆", lambda **kw: update_memory_tool(memory=memory, **kw)))
    registry.register(AgentTool("generate_report_tool", "生成 Markdown 学术报告", generate_report_tool))
    return registry


def analyze_pdf_tool(
    pdf_path: str,
    memory: AcademicMemory,
    provider: str | None = None,
    research_topic: str | None = None,
    llm_max_chars: int = 12000,
    write_memory: bool = False,
    output_root: str = "data/outputs",
) -> ToolResult:
    started_at = utc_now_iso()
    try:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF 不存在：{path}")
        full_text = extract_text(str(path))
        selected_text, abstract = select_representative_text(full_text, max_chars=4000)
        if not selected_text:
            raise ValueError("无法从 PDF 中提取可用于解读的文本")

        analysis = Analyzer(provider=provider).analyze(full_text[:llm_max_chars], research_topic=research_topic)
        title = analysis.paper_title if analysis.paper_title and analysis.paper_title != "未识别" else extract_title(str(path))
        paper = _paper_from_analysis(title=title, pdf_path=str(path), abstract=abstract, full_text=full_text, analysis=analysis)
        output_dir = write_outputs([paper], output_root=output_root, research_topic=research_topic)

        wrote_memory = False
        if write_memory:
            memory.add_paper(
                text=f"{title}\n\n{abstract or selected_text[:1200]}\n\n{analysis.core_problem}\n{analysis.relevance_to_my_research}",
                metadata={
                    "title": title,
                    "doi": analysis.doi,
                    "venue": analysis.venue,
                    "pdf_path": str(path),
                    "source": "uploaded_pdf",
                    "analysis_summary": analysis.core_problem,
                },
            )
            wrote_memory = True

        return ToolResult(
            tool_name="analyze_pdf_tool",
            ok=True,
            message=f"已完成 PDF 解读：{title}",
            data={"title": title, "output_dir": str(output_dir), "analysis": analysis.__dict__},
            started_at=started_at,
            finished_at=utc_now_iso(),
            wrote_memory=wrote_memory,
        )
    except Exception as exc:
        return ToolResult(
            tool_name="analyze_pdf_tool",
            ok=False,
            message="PDF 解读失败",
            error=str(exc),
            started_at=started_at,
            finished_at=utc_now_iso(),
        )


def screen_wos_alert_tool(
    memory: AcademicMemory,
    since_date: str | None = None,
    max_emails: int = 20,
    top_k: int = 10,
    use_web: bool = False,
    profile_path: str = "data/processed/profile.npy",
    model_name: str = "all-MiniLM-L6-v2",
    write_memory: bool = False,
) -> ToolResult:
    started_at = utc_now_iso()
    try:
        emails, stats, _hit_seen_alert = fetch_wos_emails_with_stats(
            since_date=since_date,
            max_emails=max_emails,
            ignore_seen=True,
        )
        papers: list[FetchedPaper] = []
        alert_links = 0
        for message_id, _subject, html in emails:
            papers.extend(parse_wos_email(html, source_email_id=message_id))
            if use_web:
                alert_links += len(extract_alert_summary_links(html))

        ranked = _rank_fetched_papers(papers, top_k=top_k, profile_path=profile_path, model_name=model_name)
        wrote_memory = False
        if write_memory:
            for item in ranked:
                paper = item["paper"]
                memory.add_paper(
                    text=f"{paper.title}\n\n{paper.abstract}",
                    metadata={
                        "title": paper.title,
                        "doi": paper.doi or "",
                        "venue": paper.venue or "",
                        "source": "wos_alert",
                        "score": item["score"],
                    },
                )
            wrote_memory = bool(ranked)

        recommendations = [
            {
                "title": item["paper"].title,
                "doi": item["paper"].doi,
                "venue": item["paper"].venue,
                "score": item["score"],
                "reason": _recommendation_reason(item["paper"], item["score"]),
                "manual_pdf_advice": "建议用户手动下载 PDF 后上传给 Agent 深读。",
            }
            for item in ranked
        ]
        return ToolResult(
            tool_name="screen_wos_alert_tool",
            ok=True,
            message=f"已筛选 WoS 候选论文 {len(papers)} 篇，推荐 {len(recommendations)} 篇。",
            data={
                "recommendations": recommendations,
                "email_stats": stats,
                "alert_summary_link_count": alert_links,
            },
            started_at=started_at,
            finished_at=utc_now_iso(),
            wrote_memory=wrote_memory,
        )
    except Exception as exc:
        return ToolResult(
            tool_name="screen_wos_alert_tool",
            ok=False,
            message="WoS 候选筛选失败",
            error=str(exc),
            started_at=started_at,
            finished_at=utc_now_iso(),
        )


def search_memory_tool(query: str, memory: AcademicMemory, collection: str = "all", limit: int = 5) -> ToolResult:
    started_at = utc_now_iso()
    try:
        results = memory.search(query=query, collection=collection, limit=limit)
        return ToolResult(
            tool_name="search_memory_tool",
            ok=True,
            message=f"找到 {len(results)} 条相关记忆。",
            data={"results": results, "stats": memory.stats()},
            started_at=started_at,
            finished_at=utc_now_iso(),
        )
    except Exception as exc:
        return ToolResult(
            tool_name="search_memory_tool",
            ok=False,
            message="记忆检索失败",
            error=str(exc),
            started_at=started_at,
            finished_at=utc_now_iso(),
        )


def update_memory_tool(
    text: str,
    memory: AcademicMemory,
    memory_type: str = "topic_preference",
    evidence_source: str = "conversation",
    weight: float = 0.8,
    confidence: float = 0.8,
) -> ToolResult:
    started_at = utc_now_iso()
    try:
        item_id = memory.add_interest(
            text=text,
            memory_type=memory_type,
            evidence_source=evidence_source,
            weight=weight,
            confidence=confidence,
        )
        return ToolResult(
            tool_name="update_memory_tool",
            ok=True,
            message="已更新研究兴趣记忆。",
            data={"memory_id": item_id, "stats": memory.stats()},
            started_at=started_at,
            finished_at=utc_now_iso(),
            wrote_memory=True,
        )
    except Exception as exc:
        return ToolResult(
            tool_name="update_memory_tool",
            ok=False,
            message="记忆更新失败",
            error=str(exc),
            started_at=started_at,
            finished_at=utc_now_iso(),
        )


def generate_report_tool(
    title: str = "学术助手报告",
    items: list[dict[str, Any]] | None = None,
    output_root: str = "data/outputs",
) -> ToolResult:
    started_at = utc_now_iso()
    try:
        output_dir = Path(output_root) / datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir.mkdir(parents=True, exist_ok=True)
        lines = [f"# {title}", ""]
        for item in items or []:
            lines.extend([f"## {item.get('title', '未命名条目')}", "", str(item.get("summary", "")), ""])
        report_path = output_dir / "agent_report.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return ToolResult(
            tool_name="generate_report_tool",
            ok=True,
            message=f"已生成报告：{report_path}",
            data={"report_path": str(report_path), "output_dir": str(output_dir)},
            started_at=started_at,
            finished_at=utc_now_iso(),
        )
    except Exception as exc:
        return ToolResult(
            tool_name="generate_report_tool",
            ok=False,
            message="报告生成失败",
            error=str(exc),
            started_at=started_at,
            finished_at=utc_now_iso(),
        )


def log_tool_result(result: ToolResult, log_path: str = "data/conversations/tool_calls.jsonl") -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")


def _rank_fetched_papers(
    papers: list[FetchedPaper],
    top_k: int,
    profile_path: str,
    model_name: str,
) -> list[dict[str, Any]]:
    if not papers:
        return []
    profile_file = Path(profile_path)
    if profile_file.exists():
        import numpy as np

        profile = np.load(profile_file)
        embedder = Embedder(model_name=model_name)
        texts = [(paper.abstract or paper.title or "").strip() for paper in papers]
        embeddings = embedder.encode(texts)
        scored = [
            {"paper": paper, "score": float(cosine_similarity(embedding, profile))}
            for paper, embedding in zip(papers, embeddings)
        ]
    else:
        scored = [{"paper": paper, "score": 0.0} for paper in papers]
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[: max(1, top_k)]


def _recommendation_reason(paper: FetchedPaper, score: float) -> str:
    if score > 0:
        return f"与当前兴趣向量相似度为 {score:.3f}，摘要主题值得进一步核对。"
    if paper.abstract:
        return "尚未构建兴趣向量，先基于 WoS 摘要列为候选。"
    return "缺少摘要，建议先打开记录确认是否值得下载。"


def _paper_from_analysis(title, pdf_path, abstract, full_text, analysis):
    from paper_analyzer.data.schema import Paper

    paper = Paper(
        title=title,
        source_path=pdf_path,
        abstract=abstract,
        selected_text=full_text[:4000],
        full_text=full_text,
        analysis=analysis,
        stage_status="completed",
    )
    return paper
