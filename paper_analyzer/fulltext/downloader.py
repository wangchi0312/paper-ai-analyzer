import re
from pathlib import Path


def download_pdf(url: str, output_path: Path, timeout: int = 30) -> Path:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("缺少 requests 包，无法下载全文。") from exc

    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/pdf,text/html,application/xhtml+xml",
        },
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()

    content = response.content
    content_type = response.headers.get("content-type", "").lower()
    if b"%PDF" not in content[:1024] and "pdf" not in content_type:
        raise RuntimeError(f"下载结果不是 PDF：content-type={content_type or 'unknown'}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return output_path


def safe_pdf_name(title: str, index: int) -> str:
    safe_title = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", title, flags=re.UNICODE).strip("_")
    safe_title = safe_title[:80] or "paper"
    return f"{index:02d}_{safe_title}.pdf"
