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
from paper_analyzer.ingestion.metadata_enricher import enrich_paper_metadata
from paper_analyzer.ingestion.wos_browser import WosBrowserSession
from paper_analyzer.ingestion.wos_parser import extract_alert_summary_links, parse_wos_email
from paper_analyzer.llm.analyzer import Analyzer
from paper_analyzer.pdf.parser import extract_text, extract_title
from paper_analyzer.pdf.text_selector import select_representative_text
from paper_analyzer.report.writer import write_outputs
from paper_analyzer.utils.text import normalize_title_key
from paper_analyzer.utils.text import emit_progress
from pipeline.fetch_papers import fetch_papers, load_paper_library


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
    progress_callback: Callable[[str], None] | None = None,
) -> ToolResult:
    started_at = utc_now_iso()
    try:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF 不存在：{path}")
        emit_progress(progress_callback, f"开始提取 PDF 文本：{path.name}")
        full_text = extract_text(str(path))
        selected_text, abstract = select_representative_text(full_text, max_chars=4000)
        if not selected_text:
            raise ValueError("无法从 PDF 中提取可用于解读的文本")

        emit_progress(progress_callback, "调用 LLM 进行论文解读")
        analysis = Analyzer(provider=provider).analyze(full_text[:llm_max_chars], research_topic=research_topic)
        title = analysis.paper_title if analysis.paper_title and analysis.paper_title != "未识别" else extract_title(str(path))
        paper = _paper_from_analysis(title=title, pdf_path=str(path), abstract=abstract, full_text=full_text, analysis=analysis)
        output_dir = write_outputs([paper], output_root=output_root, research_topic=research_topic)

        wrote_memory = False
        if write_memory:
            emit_progress(progress_callback, "写入论文记忆")
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

        emit_progress(progress_callback, f"PDF 解读完成：{title}")
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
    use_web: bool = True,
    use_browser: bool = True,
    browser_max_pages: int = 20,
    browser_manual_login_wait_seconds: int = 0,
    profile_path: str = "data/processed/profile.npy",
    model_name: str = "all-MiniLM-L6-v2",
    write_memory: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> ToolResult:
    started_at = utc_now_iso()
    try:
        emit_progress(progress_callback, "开始读取 WoS Alert 邮件")
        if use_web:
            papers = fetch_papers(
                since_date=since_date,
                max_emails=max_emails,
                no_web=False,
                ignore_seen=True,
                expand_alert_pages=True,
                use_browser=use_browser,
                browser_max_pages=browser_max_pages,
                browser_manual_login_wait_seconds=browser_manual_login_wait_seconds,
                browser_headless=not use_browser,
                progress_callback=progress_callback,
            )
            stats: dict[str, Any] = {}
            alert_links = 0
        else:
            emails, stats, _hit_seen_alert = fetch_wos_emails_with_stats(
                since_date=since_date,
                max_emails=max_emails,
                ignore_seen=True,
            )
            papers = []
            alert_links = 0
            for message_id, _subject, html in emails:
                papers.extend(parse_wos_email(html, source_email_id=message_id))
                alert_links += len(extract_alert_summary_links(html))

        emit_progress(progress_callback, f"开始计算 {len(papers)} 篇候选论文的推荐分")
        ranked = _rank_fetched_papers(papers, top_k=top_k, profile_path=profile_path, model_name=model_name)
        _enrich_recommendation_dois(
            ranked,
            use_browser=use_browser,
            browser_max_pages=browser_max_pages,
            browser_manual_login_wait_seconds=browser_manual_login_wait_seconds,
            progress_callback=progress_callback,
        )
        wrote_memory = False
        if write_memory:
            emit_progress(progress_callback, "写入 WoS 候选论文记忆")
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
                "doi": item["paper"].doi or "",
                "authors": item["paper"].authors or "",
                "venue": item["paper"].venue or "",
                "abstract": item["paper"].abstract or "",
                "link": item["paper"].link or "",
                "publisher_link": item["paper"].publisher_link or "",
                "wos_summary_url": item["paper"].wos_summary_url or "",
                "score": item["score"],
                "reason": _recommendation_reason(item["paper"], item["score"]),
                "doi_source": _recommendation_doi_source(item["paper"]),
                "doi_status": "found" if item["paper"].doi else "missing",
                "manual_pdf_advice": "建议手动下载 PDF 后上传给 Agent 深读。",
                "missing": {
                    "doi": not bool(item["paper"].doi),
                    "abstract": not bool((item["paper"].abstract or "").strip()),
                },
            }
            for item in ranked
        ]
        emit_progress(progress_callback, f"筛选完成：候选 {len(papers)} 篇，推荐 {len(recommendations)} 篇")
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
    return "缺少摘要，建议先打开 WoS 记录确认是否值得下载。"


def _enrich_recommendation_dois(
    ranked: list[dict[str, Any]],
    use_browser: bool,
    browser_max_pages: int,
    browser_manual_login_wait_seconds: int,
    progress_callback: Callable[[str], None] | None,
) -> None:
    missing = [item["paper"] for item in ranked if not (item["paper"].doi or "").strip()]
    if not missing:
        return

    emit_progress(progress_callback, f"推荐结果中有 {len(missing)} 篇缺 DOI，开始定向补全")
    library_by_title = _paper_library_by_title()

    browser_session: WosBrowserSession | None = None
    browser_context: WosBrowserSession | None = None
    try:
        if use_browser:
            browser_context = WosBrowserSession(
                max_pages=max(1, browser_max_pages),
                headless=False,
                manual_login_wait_seconds=browser_manual_login_wait_seconds,
            )
            browser_session = browser_context.__enter__()

        for paper in missing:
            title = paper.title or "未命名论文"
            if _enrich_from_local_library(paper, library_by_title):
                emit_progress(progress_callback, f"已从历史论文库补到 DOI：{title}")
                continue

            if browser_session is not None and paper.link and "full-record" in (paper.link or "").lower():
                before_doi = paper.doi
                try:
                    emit_progress(progress_callback, f"为推荐论文补 DOI：{title}")
                    browser_session.enrich_paper_from_full_record(paper)
                except Exception as exc:
                    emit_progress(progress_callback, f"Full Record DOI 补全失败：{title} ({exc})")
                else:
                    if paper.doi and paper.doi != before_doi:
                        _append_fetch_method_tag(paper, "full_record")
                        emit_progress(progress_callback, f"已从 Full Record 补到 DOI：{title}")
                        continue

            try:
                before_doi = paper.doi
                enrich_paper_metadata(paper)
                if paper.doi and paper.doi != before_doi:
                    emit_progress(progress_callback, f"已从公开元数据补到 DOI：{title}")
                elif not paper.doi:
                    emit_progress(progress_callback, f"仍未补到 DOI：{title}")
            except Exception as exc:
                emit_progress(progress_callback, f"公开元数据 DOI 补全失败：{title} ({exc})")
    finally:
        if browser_context is not None:
            browser_context.__exit__(None, None, None)


def _append_fetch_method_tag(paper: FetchedPaper, tag: str) -> None:
    current = (paper.fetch_method or "").split("+") if paper.fetch_method else []
    if tag not in current:
        paper.fetch_method = "+".join([*current, tag]) if current else tag


def _recommendation_doi_source(paper: FetchedPaper) -> str:
    if not (paper.doi or "").strip():
        return "missing"
    methods = set(filter(None, (paper.fetch_method or "").split("+")))
    if "full_record" in methods:
        return "full_record"
    if "local_library" in methods:
        return "local_library"
    for source in ("crossref", "openalex", "semantic_scholar"):
        if source in methods:
            return source
    if methods & {"wos_browser", "web", "email"}:
        return "wos"
    return "unknown"


def _paper_library_by_title() -> dict[str, FetchedPaper]:
    try:
        library = load_paper_library()
    except Exception:
        return {}
    by_title: dict[str, FetchedPaper] = {}
    for paper in library:
        key = normalize_title_key(paper.title)
        if not key or not (paper.doi or "").strip():
            continue
        current = by_title.get(key)
        if current is None or len((paper.abstract or "")) > len((current.abstract or "")):
            by_title[key] = paper
    return by_title


def _enrich_from_local_library(paper: FetchedPaper, library_by_title: dict[str, FetchedPaper]) -> bool:
    match = library_by_title.get(normalize_title_key(paper.title))
    if match is None or not (match.doi or "").strip():
        return False
    paper.doi = match.doi
    if match.authors and not paper.authors:
        paper.authors = match.authors
    if match.venue and not paper.venue:
        paper.venue = match.venue
    if match.publisher_link and not paper.publisher_link:
        paper.publisher_link = match.publisher_link
    _append_fetch_method_tag(paper, "local_library")
    return True


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
