import argparse
from pathlib import Path

import numpy as np

from paper_analyzer.data.schema import FetchedPaper, Paper
from paper_analyzer.embedding.embedder import Embedder
from paper_analyzer.embedding.similarity import cosine_similarity
from paper_analyzer.llm.analyzer import Analyzer
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
) -> Path:
    if not papers:
        raise ValueError("没有可分析的论文")
    if top_k is not None and top_k <= 0:
        raise ValueError("--top-k 必须大于 0")

    profile_file = Path(profile_path)
    if not profile_file.exists():
        raise FileNotFoundError(f"兴趣向量不存在，请先运行 build_profile.py：{profile_file}")

    profile = np.load(profile_file)
    analysis_inputs = [_select_fetch_text(paper, max_chars=max_chars) for paper in papers]
    embedder = Embedder(model_name=model_name)
    embeddings = embedder.encode(analysis_inputs)

    analyzer: Analyzer | None = None
    analyzed: list[Paper] = []
    scored_items = [
        (index, cosine_similarity(embedding, profile))
        for index, embedding in enumerate(embeddings)
    ]
    llm_allowed_indexes = _select_top_k_indexes(scored_items, top_k)

    for index, (fetched, selected_text, embedding) in enumerate(zip(papers, analysis_inputs, embeddings)):
        score = scored_items[index][1]
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

        if score < threshold:
            paper.skipped_reason = f"相似度 {score:.4f} 低于阈值 {threshold:.4f}"
        elif skip_llm:
            paper.skipped_reason = "用户指定跳过 LLM 分析"
        elif top_k is not None and index not in llm_allowed_indexes:
            paper.skipped_reason = f"相似度 {score:.4f} 达到阈值，但未进入 top-{top_k}"
        else:
            try:
                if analyzer is None:
                    analyzer = Analyzer(provider=provider)
                paper.analysis = analyzer.analyze(selected_text[:llm_max_chars], research_topic=research_topic)
            except Exception as exc:
                paper.skipped_reason = f"LLM 分析未完成：{exc}"

        analyzed.append(paper)

    return write_outputs(analyzed, output_root=output_root, research_topic=research_topic)


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
        paper.skipped_reason = f"相似度 {score:.4f} 低于阈值 {threshold:.4f}"
    elif skip_llm:
        paper.skipped_reason = "用户指定跳过 LLM 分析"
    else:
        try:
            paper.analysis = Analyzer(provider=provider).analyze(full_text[:llm_max_chars], research_topic=research_topic)
        except Exception as exc:
            paper.skipped_reason = f"LLM 分析未完成：{exc}"

    return write_outputs([paper], output_root=output_root, research_topic=research_topic)


def _select_fetch_text(paper: FetchedPaper, max_chars: int) -> str:
    text = (paper.abstract or "").strip() or paper.title.strip()
    if not text:
        raise ValueError("邮件论文缺少标题和摘要，无法分析")
    return text[:max_chars]


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
