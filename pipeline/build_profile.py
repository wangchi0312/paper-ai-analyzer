import argparse
import json
from pathlib import Path

import numpy as np

from paper_analyzer.embedding.embedder import Embedder
from paper_analyzer.pdf.parser import extract_text, extract_title
from paper_analyzer.pdf.text_selector import select_representative_text


def build_profile(
    input_dir: str,
    output_path: str = "data/processed/profile.npy",
    max_chars: int = 4000,
    model_name: str = "all-MiniLM-L6-v2",
    recursive: bool = False,
    limit: int | None = None,
) -> Path:
    pdf_dir = Path(input_dir)
    if not pdf_dir.exists():
        raise FileNotFoundError(f"输入目录不存在：{pdf_dir}")

    pdf_paths = find_pdf_paths(pdf_dir, recursive=recursive, limit=limit)
    if not pdf_paths:
        raise ValueError(f"输入目录没有 PDF：{pdf_dir}")

    embedder = Embedder(model_name=model_name)
    selected_texts: list[str] = []
    metadata: list[dict] = []
    skipped: list[str] = []

    for pdf_path in pdf_paths:
        print(f"处理兴趣样本：{pdf_path}")
        try:
            full_text = extract_text(str(pdf_path))
            selected_text, abstract = select_representative_text(full_text, max_chars=max_chars)
            if not selected_text:
                raise ValueError("无法提取可用于 embedding 的文本")
        except Exception as exc:
            print(f"  跳过（提取失败）：{exc}")
            skipped.append(str(pdf_path))
            continue

        selected_texts.append(selected_text)
        metadata.append(
            {
                "title": extract_title(str(pdf_path)),
                "source_path": str(pdf_path),
                "has_abstract": bool(abstract),
                "selected_chars": len(selected_text),
            }
        )

    if not selected_texts:
        raise ValueError(f"所有 PDF 均提取失败，无法构建兴趣向量。跳过的文件：{skipped}")

    embeddings = embedder.encode(selected_texts)
    profile = np.mean(np.asarray(embeddings, dtype=float), axis=0)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.save(output, profile)

    metadata_path = output.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output


def find_pdf_paths(input_dir: Path, recursive: bool = False, limit: int | None = None) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdf_paths = sorted(input_dir.glob(pattern))
    if limit is not None:
        if limit <= 0:
            raise ValueError("--limit 必须大于 0")
        pdf_paths = pdf_paths[:limit]
    return pdf_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建论文研究兴趣向量")
    parser.add_argument("--input", default="data/profile_pdfs", help="兴趣样本 PDF 目录")
    parser.add_argument("--output", default="data/processed/profile.npy", help="输出 profile.npy 路径")
    parser.add_argument("--max-chars", type=int, default=4000, help="找不到 Abstract 时截取的最大字符数")
    parser.add_argument("--model", default="all-MiniLM-L6-v2", help="sentence-transformers 模型名")
    parser.add_argument("--recursive", action="store_true", help="递归读取子目录中的 PDF")
    parser.add_argument("--limit", type=int, default=None, help="限制处理 PDF 数量，适合先小规模试跑")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = build_profile(
        input_dir=args.input,
        output_path=args.output,
        max_chars=args.max_chars,
        model_name=args.model,
        recursive=args.recursive,
        limit=args.limit,
    )
    print(f"兴趣向量已保存：{output}")


if __name__ == "__main__":
    main()
