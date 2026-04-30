from difflib import SequenceMatcher
from pathlib import Path
import re
import shutil

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.downloader import safe_pdf_name
from paper_analyzer.fulltext.source import FullTextResult


TITLE_MATCH_THRESHOLD = 0.86


def resolve_manual_pdf(
    paper: FetchedPaper,
    manual_pdf_dir: str | None,
    output_dir: Path,
    index: int,
) -> FullTextResult | None:
    if not manual_pdf_dir:
        return None
    root = Path(manual_pdf_dir)
    if not root.exists() or not root.is_dir():
        return FullTextResult(success=False, reason=f"手动 PDF 目录不存在：{root}")

    match = find_manual_pdf(paper, root)
    if match is None:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / safe_pdf_name(paper.title, index)
    if match.resolve() != target.resolve():
        shutil.copy2(match, target)
    return FullTextResult(success=True, path=str(target), source="manual_upload", url=str(match))


def find_manual_pdf(paper: FetchedPaper, root: Path) -> Path | None:
    pdf_paths = sorted(path for path in root.rglob("*.pdf") if path.is_file())
    if not pdf_paths:
        return None

    doi_key = _normalize_doi(paper.doi or "")
    if doi_key:
        for path in pdf_paths:
            if doi_key in _normalize_identifier(path.stem):
                return path

    best_path: Path | None = None
    best_score = 0.0
    title_key = _normalize_title(paper.title)
    if not title_key:
        return None

    for path in pdf_paths:
        score = _title_similarity(title_key, _normalize_title(path.stem))
        if score > best_score:
            best_score = score
            best_path = path
    if best_path and best_score >= TITLE_MATCH_THRESHOLD:
        return best_path

    for path in pdf_paths:
        sample = _pdf_metadata_sample(path)
        if doi_key and doi_key in _normalize_identifier(sample):
            return path
        score = _title_similarity(title_key, _normalize_title(sample))
        if score > best_score:
            best_score = score
            best_path = path

    if best_path and best_score >= TITLE_MATCH_THRESHOLD:
        return best_path
    return None


def _pdf_metadata_sample(path: Path, max_chars: int = 8000) -> str:
    try:
        import fitz
    except ImportError:
        return path.stem
    try:
        with fitz.open(str(path)) as doc:
            parts = [path.stem]
            title = (doc.metadata or {}).get("title") or ""
            if title:
                parts.append(title)
            for page in doc[: min(len(doc), 2)]:
                parts.append(page.get_text("text"))
            return "\n".join(parts)[:max_chars]
    except Exception:
        return path.stem


def _title_similarity(source: str, candidate: str) -> float:
    if not source or not candidate:
        return 0.0
    if source in candidate or candidate in source:
        shorter = min(len(source), len(candidate))
        longer = max(len(source), len(candidate))
        return shorter / longer
    return SequenceMatcher(None, source, candidate).ratio()


def _normalize_title(value: str) -> str:
    text = value.lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_doi(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return _normalize_identifier(text)


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())
