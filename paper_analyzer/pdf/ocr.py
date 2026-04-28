from pathlib import Path
import shutil


OCR_INSTALL_HINT = (
    "OCR 需要安装 Tesseract 和 Poppler。"
    "Windows 可手动安装：Tesseract OCR 与 Poppler，并把可执行文件目录加入 PATH。"
)


def ocr_pdf(pdf_path: str, lang: str = "chi_sim+eng") -> str:
    if not shutil.which("tesseract"):
        raise RuntimeError(f"未检测到 tesseract。{OCR_INSTALL_HINT}")

    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("缺少 pdf2image 或 pytesseract，请先安装 requirements.txt。") from exc

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 不存在：{path}")

    try:
        images = convert_from_path(str(path))
    except Exception as exc:
        raise RuntimeError(f"PDF 转图片失败，可能缺少 Poppler。{OCR_INSTALL_HINT}") from exc

    texts = [pytesseract.image_to_string(image, lang=lang) for image in images]
    return "\n".join(texts).strip()
