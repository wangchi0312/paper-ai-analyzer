import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        description="文献追踪助手",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-profile", help="构建研究兴趣向量")
    build_parser.add_argument("--input", default="data/profile_pdfs", help="兴趣样本 PDF 目录")
    build_parser.add_argument("--output", default="data/processed/profile.npy", help="输出 profile.npy 路径")
    build_parser.add_argument("--max-chars", type=int, default=4000, help="找不到 Abstract 时截取的最大字符数")
    build_parser.add_argument("--model", default="all-MiniLM-L6-v2", help="sentence-transformers 模型名")
    build_parser.add_argument("--recursive", action="store_true", help="递归读取子目录中的 PDF")
    build_parser.add_argument("--limit", type=int, default=None, help="限制处理 PDF 数量")

    analyze_parser = subparsers.add_parser("analyze", help="分析单篇新论文")
    analyze_parser.add_argument("--source", choices=["pdf", "fetch"], default="pdf", help="分析来源：本地 PDF 或邮件抓取结果")
    analyze_parser.add_argument("--pdf", help="待分析 PDF 路径")
    analyze_parser.add_argument("--fetched", default="data/processed/fetched_papers.json", help="fetch-papers 生成的论文列表")
    analyze_parser.add_argument("--profile", default="data/processed/profile.npy", help="兴趣向量路径")
    analyze_parser.add_argument("--threshold", type=float, default=0.5, help="LLM 分析触发阈值")
    analyze_parser.add_argument("--provider", default=None, help="LLM provider：deepseek/siliconflow/modelscope")
    analyze_parser.add_argument("--max-chars", type=int, default=4000, help="找不到 Abstract 时截取的最大字符数")
    analyze_parser.add_argument("--llm-max-chars", type=int, default=12000, help="传给 LLM 的全文前 N 个字符")
    analyze_parser.add_argument("--output-root", default="data/outputs", help="输出根目录")
    analyze_parser.add_argument("--model", default="all-MiniLM-L6-v2", help="sentence-transformers 模型名")
    analyze_parser.add_argument("--skip-llm", action="store_true", help="只计算相似度，不调用 LLM")
    analyze_parser.add_argument("--research-topic", default=None, help="研究主题，覆盖 .env 中的 RESEARCH_TOPIC")
    analyze_parser.add_argument("--top-k", type=int, default=None, help="邮件批量模式下只允许相似度最高的前 N 篇触发 LLM")

    fetch_parser = subparsers.add_parser("fetch-papers", help="从 WoS Citation Alert 邮件获取论文")
    fetch_parser.add_argument("--since", default=None, help="只获取该日期之后的邮件，格式 YYYY-MM-DD")
    fetch_parser.add_argument("--max", type=int, default=50, dest="max_emails", help="最多检查的邮件数量")
    fetch_parser.add_argument("--no-web", action="store_true", help="跳过网页补全，只使用邮件内容")
    fetch_parser.add_argument("--output", default="data/processed/fetched_papers.json", help="抓取结果保存路径")
    fetch_parser.add_argument("--audit-output", default="data/processed/fetch_audit.json", help="抓取审计保存路径")

    run_parser = subparsers.add_parser("run", help="获取邮件论文并批量分析")
    run_parser.add_argument("--since", default=None, help="只获取该日期之后的邮件，格式 YYYY-MM-DD")
    run_parser.add_argument("--max", type=int, default=50, dest="max_emails", help="最多检查的邮件数量")
    run_parser.add_argument("--no-web", action="store_true", help="跳过网页补全，只使用邮件内容")
    run_parser.add_argument("--audit-output", default="data/processed/fetch_audit.json", help="抓取审计保存路径")
    run_parser.add_argument("--profile", default="data/processed/profile.npy", help="兴趣向量路径")
    run_parser.add_argument("--threshold", type=float, default=0.5, help="LLM 分析触发阈值")
    run_parser.add_argument("--provider", default=None, help="LLM provider：deepseek/siliconflow/modelscope")
    run_parser.add_argument("--max-chars", type=int, default=4000, help="邮件论文分析文本最大字符数")
    run_parser.add_argument("--llm-max-chars", type=int, default=12000, help="传给 LLM 的全文前 N 个字符")
    run_parser.add_argument("--output-root", default="data/outputs", help="输出根目录")
    run_parser.add_argument("--model", default="all-MiniLM-L6-v2", help="sentence-transformers 模型名")
    run_parser.add_argument("--skip-llm", action="store_true", help="只计算相似度，不调用 LLM")
    run_parser.add_argument("--research-topic", default=None, help="研究主题，覆盖 .env 中的 RESEARCH_TOPIC")
    run_parser.add_argument("--top-k", type=int, default=None, help="只允许相似度最高的前 N 篇触发 LLM")

    args = parser.parse_args()

    if args.command == "build-profile":
        from pipeline.build_profile import build_profile

        output = build_profile(
            input_dir=args.input,
            output_path=args.output,
            max_chars=args.max_chars,
            model_name=args.model,
            recursive=args.recursive,
            limit=args.limit,
        )
        print(f"兴趣向量已保存：{output}")
    elif args.command == "analyze":
        from pipeline.analyze_papers import analyze_papers, analyze_pdf

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
    elif args.command == "fetch-papers":
        from pipeline.fetch_papers import fetch_papers

        papers = fetch_papers(
            since_date=args.since,
            max_emails=args.max_emails,
            no_web=args.no_web,
            output_path=args.output,
            audit_output_path=args.audit_output,
        )
        print(f"已获取论文 {len(papers)} 篇，保存到：{args.output}")
    elif args.command == "run":
        from pipeline.analyze_papers import analyze_papers
        from pipeline.fetch_papers import fetch_papers

        papers = fetch_papers(
            since_date=args.since,
            max_emails=args.max_emails,
            no_web=args.no_web,
            audit_output_path=args.audit_output,
        )
        output_dir = analyze_papers(
            papers=papers,
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
        print(f"分析结果已保存：{output_dir}")


if __name__ == "__main__":
    main()
