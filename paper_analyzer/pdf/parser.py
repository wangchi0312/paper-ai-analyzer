from pathlib import Path
import re

from paper_analyzer.pdf.ocr import ocr_pdf
from paper_analyzer.utils.logger import get_logger


logger = get_logger(__name__)


def extract_text(pdf_path: str, ocr_threshold: int = 100, ocr_lang: str = "chi_sim+eng") -> str:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 不存在：{path}")

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("缺少 PyMuPDF，请先安装 requirements.txt。") from exc

    parts: list[str] = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            parts.append(page.get_text())

    text = "\n".join(parts).strip()
    if len(text) >= ocr_threshold:
        return text

    logger.info("PDF 文本较短，尝试 OCR：%s", path)
    try:
        ocr_text = ocr_pdf(str(path), lang=ocr_lang)
    except Exception as exc:
        if text:
            logger.warning("OCR 不可用，返回 PyMuPDF 提取到的短文本：%s", exc)
            return text
        raise RuntimeError(f"无法提取 PDF 文本：{exc}") from exc

    return ocr_text or text


def extract_title(pdf_path: str) -> str:
    path = Path(pdf_path)
    try:
        import fitz

        with fitz.open(str(path)) as doc:
            title = (doc.metadata or {}).get("title", "").strip()
            if _is_trustworthy_metadata_title(title):
                return title
            page_title = _extract_title_from_first_page(doc)
            if page_title:
                return page_title
    except Exception as exc:
        logger.debug("标题提取失败，回退到文件名：%s", exc)

    return path.stem


def _is_trustworthy_metadata_title(title: str) -> bool:
    normalized = _normalize_line(title).lower()
    if len(normalized) < 8:
        return False

    bad_fragments = [
        "instructions for use",
        "document class",
        "elsart",
        "elsevier",
        "microsoft word",
        "untitled",
        "manuscript",
    ]
    return not any(fragment in normalized for fragment in bad_fragments)


def _extract_title_from_first_page(doc) -> str:
    if len(doc) == 0:
        return ""

    page = doc[0]
    page_height = page.rect.height
    lines = []

    data = page.get_text("dict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = _normalize_line(" ".join(span.get("text", "") for span in spans))
            if not _is_title_candidate_line(text):
                continue

            y0 = min((span.get("bbox", [0, 0, 0, 0])[1] for span in spans), default=0)
            if y0 > page_height * 0.45:
                continue

            size = max((span.get("size", 0) for span in spans), default=0)
            lines.append({"text": text, "size": size, "y0": y0})

    if not lines:
        return ""

    lines = sorted(lines, key=lambda item: item["y0"])
    title_lines = [lines[0]]
    previous = lines[0]

    for line in lines[1:]:
        if _looks_like_author_line(line["text"]):
            break
        if abs(line["size"] - previous["size"]) > 1.0:
            break
        if line["y0"] - previous["y0"] > 30:
            break
        title_lines.append(line)
        previous = line

    title = _normalize_line(" ".join(line["text"] for line in title_lines))
    return title[:300]


def _normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_title_candidate_line(text: str) -> bool:
    if len(text) < 8:
        return False

    lowered = text.lower()
    bad_prefixes = (
        "abstract",
        "highlights",
        "keywords",
        "doi:",
        "http:",
        "https:",
        "arxiv:",
        "received",
        "accepted",
        "published",
        "journal",
        "copyright",
    )
    if lowered.startswith(bad_prefixes):
        return False

    bad_phrases = (
        "preprint not peer reviewed",
        "not peer reviewed",
    )
    if any(phrase in lowered for phrase in bad_phrases):
        return False

    if "@" in text:
        return False

    return True


def _looks_like_author_line(text: str) -> bool:
    if "," not in text:
        return False

    words = re.findall(r"[A-Za-z]+", text)
    if len(words) < 4:
        return False

    short_words = sum(1 for word in words if len(word) <= 3)
    return short_words >= 1
