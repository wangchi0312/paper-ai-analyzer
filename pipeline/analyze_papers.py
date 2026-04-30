import argparse
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from paper_analyzer.data.schema import FetchedPaper, Paper
from paper_analyzer.embedding.embedder import Embedder
from paper_analyzer.embedding.similarity import cosine_similarity
from paper_analyzer.llm.analyzer import Analyzer
from paper_analyzer.fulltext.resolver import resolve_full_text
from paper_analyzer.pdf.parser import extract_text, extract_title
from paper_analyzer.pdf.text_selector import select_representative_text
from paper_analyzer.report.writer import write_outputs


def analyze_papers(
    papers: list[FetchedPaper],
    profile_path: str = "data/processed/profile.npy",
    threshold: float = 0.5,
    provider: str | None = None,
    max_chars: int = 4000,
    llm_max_chars: int = 12000,
    output_root: str = "data/outputs",
    model_name: str = "all-MiniLM-L6-v2",
    skip_llm: bool = False,
    research_topic: str | None = None,
    top_k: int | None = None,
    download_full_text: bool = False,
    unpaywall_email: str | None = None,
    full_text_timeout: int = 10,
    manual_pdf_dir: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> Path:
    if not papers:
        raise ValueError("没有可分析的论文")
    if top_k is not None and top_k <= 0:
        raise ValueError("--top-k 必须大于 0")

    profile_file = Path(profile_path)
    if not profile_file.exists():
        raise FileNotFoundError(f"兴趣向量不存在，请先运行 build_profile.py：{profile_file}")

    _emit_progress(progress_callback, "加载兴趣向量并准备相似度计算")
    profile = np.load(profile_file)
    valid_inputs: list[tuple[int, FetchedPaper, str]] = []
    invalid_papers: dict[int, Paper] = {}
    for index, fetched in enumerate(papers):
        try:
            selected_text = _select_fetch_text(fetched, max_chars=max_chars)
        except ValueError as exc:
            paper = Paper(
                title=fetched.title,
                source_path=None,
                link=fetched.link,
                abstract=fetched.abstract,
                selected_text="",
                full_text="",
                source_email_id=fetched.source_email_id,
            )
            paper.stage_status = "invalid_input"
            paper.skipped_reason = str(exc)
            invalid_papers[index] = paper
            _emit_progress(progress_callback, f"[{index + 1}/{len(papers)}] 跳过：{exc}")
            continue
        valid_inputs.append((index, fetched, selected_text))
    if valid_inputs:
        embedder = Embedder(model_name=model_name)
        _emit_progress(progress_callback, f"正在计算 {len(valid_inputs)} 篇候选论文的 embedding 和相似度")
        embeddings = embedder.encode([selected_text for _index, _fetched, selected_text in valid_inputs])
    else:
        embeddings = []

    analyzer: Analyzer | None = None
    analyzed_by_index: dict[int, Paper] = dict(invalid_papers)
    scored_items = [
        (original_index, cosine_similarity(embedding, profile))
        for (original_index, _fetched, _selected_text), embedding in zip(valid_inputs, embeddings)
    ]
    score_by_index = dict(scored_items)
    llm_allowed_indexes = _select_top_k_indexes(scored_items, top_k)
    explicit_output_dir = None
    fulltext_dir = None
    if download_full_text:
        explicit_output_dir = Path(output_root) / datetime.now().strftime("%Y%m%d_%H%M%S")
        fulltext_dir = explicit_output_dir / "papers"
        _emit_progress(progress_callback, f"将为达到阈值且进入 top-k 的论文下载全文：{fulltext_dir}")

    for embedding_index, (original_index, fetched, selected_text) in enumerate(valid_inputs):
        display_index = original_index + 1
        embedding = embeddings[embedding_index]
        score = score_by_index[original_index]
        paper = Paper(
            title=fetched.title,
            source_path=None,
            link=fetched.link,
            abstract=fetched.abstract,
            selected_text=selected_text,
            full_text=selected_text,
            embedding=np.asarray(embedding, dtype=float).tolist(),
            score=score,
            source_email_id=fetched.source_email_id,
        )

        should_limit_to_top_k = top_k is not None and (download_full_text or not skip_llm)

        if score < threshold:
            paper.stage_status = "below_threshold"
            paper.skipped_reason = f"相似度 {score:.4f} 低于阈值 {threshold:.4f}"
            _emit_progress(progress_callback, f"[{display_index}/{len(papers)}] 跳过：相似度 {score:.4f} 低于阈值")
        elif should_limit_to_top_k and original_index not in llm_allowed_indexes:
            paper.stage_status = "outside_top_k"
            paper.skipped_reason = f"相似度 {score:.4f} 达到阈值，但未进入 top-{top_k}"
            _emit_progress(progress_callback, f"[{display_index}/{len(papers)}] 跳过：未进入 top-{top_k}")
        else:
            try:
                llm_text = _build_fetch_llm_text(fetched, max_chars=llm_max_chars)
                if download_full_text:
                    assert fulltext_dir is not None
                    _emit_progress(progress_callback, f"[{display_index}/{len(papers)}] 下载全文：{fetched.title[:80]}")
                    fulltext_result = resolve_full_text(
                        fetched,
                        output_dir=fulltext_dir,
                        index=display_index,
                        unpaywall_email=unpaywall_email,
                        timeout=full_text_timeout,
                        manual_pdf_dir=manual_pdf_dir,
                    )
                    paper.full_text_status = "downloaded" if fulltext_result.success else "failed"
                    paper.full_text_source = fulltext_result.source
                    paper.full_text_path = fulltext_result.path
                    if not fulltext_result.success:
                        paper.stage_status = "fulltext_failed"
                        paper.skipped_reason = f"全文获取失败：{fulltext_result.reason}"
                        _emit_progress(progress_callback, f"[{display_index}/{len(papers)}] 全文获取失败：{fulltext_result.reason}")
                        analyzed_by_index[original_index] = paper
                        continue
                    full_text = extract_text(fulltext_result.path)
                    if not full_text.strip():
                        paper.stage_status = "text_extract_failed"
                        paper.skipped_reason = "全文下载成功，但无法提取有效文本"
                        _emit_progress(progress_callback, f"[{display_index}/{len(papers)}] 全文下载成功，但无法提取有效文本")
                        analyzed_by_index[original_index] = paper
                        continue
                    paper.full_text = full_text
                    paper.selected_text = full_text[:max_chars]
                    llm_text = full_text[:llm_max_chars]
                if skip_llm:
                    paper.stage_status = "llm_skipped"
                    paper.skipped_reason = "用户指定跳过 LLM 分析"
                    _emit_progress(progress_callback, f"[{display_index}/{len(papers)}] 全文验证完成，按配置跳过 LLM")
                    analyzed_by_index[original_index] = paper
                    continue
                if analyzer is None:
                    _emit_progress(progress_callback, "初始化 LLM 分析器")
                    analyzer = Analyzer(provider=provider)
                _emit_progress(progress_callback, f"[{display_index}/{len(papers)}] 调用 LLM 深度解读")
                paper.analysis = analyzer.analyze(llm_text, research_topic=research_topic)
                _fill_analysis_metadata_from_fetch(paper.analysis, fetched)
                paper.stage_status = "completed"
            except Exception as exc:
                paper.stage_status = "llm_failed"
                paper.skipped_reason = f"LLM 分析未完成：{exc}"
                _emit_progress(progress_callback, f"[{display_index}/{len(papers)}] 分析未完成：{exc}")

        analyzed_by_index[original_index] = paper

    analyzed = [analyzed_by_index[index] for index in range(len(papers))]
    output_dir = write_outputs(
        analyzed,
        output_root=output_root,
        research_topic=research_topic,
        output_dir=explicit_output_dir,
    )
    _emit_progress(progress_callback, f"结果已写入：{output_dir}")
    return output_dir


def analyze_pdf(
    pdf_path: str,
    profile_path: str = "data/processed/profile.npy",
    threshold: float = 0.5,
    provider: str | None = None,
    max_chars: int = 4000,
    llm_max_chars: int = 12000,
    output_root: str = "data/outputs",
    model_name: str = "all-MiniLM-L6-v2",
    skip_llm: bool = False,
    research_topic: str | None = None,
) -> Path:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 不存在：{path}")

    profile_file = Path(profile_path)
    if not profile_file.exists():
        raise FileNotFoundError(f"兴趣向量不存在，请先运行 build_profile.py：{profile_file}")

    profile = np.load(profile_file)
    full_text = extract_text(str(path))
    selected_text, abstract = select_representative_text(full_text, max_chars=max_chars)
    if not selected_text:
        raise ValueError(f"无法提取可用于分析的文本：{path}")

    embedder = Embedder(model_name=model_name)
    embedding = embedder.encode(selected_text)
    score = cosine_similarity(embedding, profile)

    paper = Paper(
        title=extract_title(str(path)),
        source_path=str(path),
        abstract=abstract,
        selected_text=selected_text,
        full_text=full_text,
        embedding=np.asarray(embedding, dtype=float).tolist(),
        score=score,
    )

    if score < threshold:
        paper.stage_status = "below_threshold"
        paper.skipped_reason = f"相似度 {score:.4f} 低于阈值 {threshold:.4f}"
    elif skip_llm:
        paper.stage_status = "llm_skipped"
        paper.skipped_reason = "用户指定跳过 LLM 分析"
    else:
        try:
            paper.analysis = Analyzer(provider=provider).analyze(full_text[:llm_max_chars], research_topic=research_topic)
            paper.stage_status = "completed"
        except Exception as exc:
            paper.stage_status = "llm_failed"
            paper.skipped_reason = f"LLM 分析未完成：{exc}"

    return write_outputs([paper], output_root=output_root, research_topic=research_topic)


def _select_fetch_text(paper: FetchedPaper, max_chars: int) -> str:
    text = (paper.abstract or "").strip() or paper.title.strip()
    if not text:
        raise ValueError("邮件论文缺少标题和摘要，无法分析")
    return text[:max_chars]


def _emit_progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def _build_fetch_llm_text(paper: FetchedPaper, max_chars: int) -> str:
    parts = [
        f"标题：{paper.title}",
        f"作者：{paper.authors or '未提供'}",
        f"期刊/会议：{paper.venue or '未提供'}",
        f"DOI：{paper.doi or '未提供'}",
        f"链接：{paper.link or '未提供'}",
        "",
        "摘要：",
        (paper.abstract or "未提供").strip(),
    ]
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("邮件论文缺少标题和摘要，无法分析")
    return text[:max_chars]


def _fill_analysis_metadata_from_fetch(analysis, paper: FetchedPaper) -> None:
    if _is_unknown(analysis.paper_title):
        analysis.paper_title = paper.title
    if paper.venue and _is_unknown(analysis.venue):
        analysis.venue = paper.venue
    if paper.doi and _is_unknown(analysis.doi):
        analysis.doi = paper.doi
    if paper.authors:
        authors = _split_authors(paper.authors)
        if authors and _is_unknown(analysis.first_author):
            analysis.first_author = authors[0]
        if len(authors) > 1 and _is_unknown(analysis.second_author):
            analysis.second_author = authors[1]


def _split_authors(authors: str) -> list[str]:
    normalized = authors.replace("；", ";").replace("，", ";").replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _is_unknown(value: str | None) -> bool:
    return not value or value.strip() in {"未识别", "未提供", "unknown", "Unknown", "N/A"}


def _select_top_k_indexes(scored_items: list[tuple[int, float]], top_k: int | None) -> set[int]:
    if top_k is None:
        return {index for index, _score in scored_items}
    return {
        index
        for index, _score in sorted(scored_items, key=lambda item: item[1], reverse=True)[:top_k]
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="分析单篇新论文")
    parser.add_argument("--source", choices=["pdf", "fetch"], default="pdf", help="分析来源：本地 PDF 或邮件抓取结果")
    parser.add_argument("--pdf", help="待分析 PDF 路径")
    parser.add_argument("--fetched", default="data/processed/fetched_papers.json", help="fetch-papers 生成的论文列表")
    parser.add_argument("--profile", default="data/processed/profile.npy", help="兴趣向量路径")
    parser.add_argument("--threshold", type=float, default=0.5, help="LLM 分析触发阈值")
    parser.add_argument("--provider", default=None, help="LLM provider：deepseek/siliconflow/modelscope")
    parser.add_argument("--max-chars", type=int, default=4000, help="找不到 Abstract 时截取的最大字符数")
    parser.add_argument("--llm-max-chars", type=int, default=12000, help="传给 LLM 的全文前 N 个字符")
    parser.add_argument("--output-root", default="data/outputs", help="输出根目录")
    parser.add_argument("--model", default="all-MiniLM-L6-v2", help="sentence-transformers 模型名")
    parser.add_argument("--skip-llm", action="store_true", help="只计算相似度，不调用 LLM")
    parser.add_argument("--research-topic", default=None, help="研究主题，覆盖 .env 中的 RESEARCH_TOPIC")
    parser.add_argument("--top-k", type=int, default=None, help="只允许相似度最高的前 N 篇触发 LLM")
    parser.add_argument("--download-full-text", action="store_true", help="邮件批量模式下下载全文后再深度解读")
    parser.add_argument("--unpaywall-email", default=None, help="Unpaywall 查询邮箱，用于开放获取全文查找")
    parser.add_argument("--full-text-timeout", type=int, default=10, help="单次全文查找/下载请求超时秒数")
    parser.add_argument("--manual-pdf-dir", default=None, help="手动 PDF 兜底目录，按 DOI/标题匹配后用于全文解析")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.source == "fetch":
        from pipeline.fetch_papers import load_fetched_papers

        output_dir = analyze_papers(
            papers=load_fetched_papers(args.fetched),
            profile_path=args.profile,
            threshold=args.threshold,
            provider=args.provider,
            max_chars=args.max_chars,
            llm_max_chars=args.llm_max_chars,
            output_root=args.output_root,
            model_name=args.model,
            skip_llm=args.skip_llm,
            research_topic=args.research_topic,
            top_k=args.top_k,
            download_full_text=args.download_full_text,
            unpaywall_email=args.unpaywall_email,
            full_text_timeout=args.full_text_timeout,
            manual_pdf_dir=args.manual_pdf_dir,
        )
    else:
        if not args.pdf:
            raise ValueError("--source pdf 需要传入 --pdf")
        output_dir = analyze_pdf(
            pdf_path=args.pdf,
            profile_path=args.profile,
            threshold=args.threshold,
            provider=args.provider,
            max_chars=args.max_chars,
            llm_max_chars=args.llm_max_chars,
            output_root=args.output_root,
            model_name=args.model,
            skip_llm=args.skip_llm,
            research_topic=args.research_topic,
        )
    print(f"分析结果已保存：{output_dir}")


if __name__ == "__main__":
    main()
