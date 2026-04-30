from pathlib import Path
import shutil

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.manual import find_manual_pdf, resolve_manual_pdf


def _make_tmp_dir(name: str) -> Path:
    path = Path("data/outputs/test_tmp") / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def test_find_manual_pdf_by_title_filename():
    tmp_dir = _make_tmp_dir("manual_pdf_title")
    pdf_path = tmp_dir / "A reliable physics informed neural network paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    match = find_manual_pdf(
        FetchedPaper(title="A reliable physics-informed neural network paper", abstract=""),
        tmp_dir,
    )

    assert match == pdf_path


def test_find_manual_pdf_by_doi_filename():
    tmp_dir = _make_tmp_dir("manual_pdf_doi")
    pdf_path = tmp_dir / "10.1234_test-paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    match = find_manual_pdf(
        FetchedPaper(title="Unrelated title", abstract="", doi="10.1234/test-paper"),
        tmp_dir,
    )

    assert match == pdf_path


def test_resolve_manual_pdf_copies_to_output_dir():
    tmp_dir = _make_tmp_dir("manual_pdf_resolve")
    manual_dir = tmp_dir / "manual"
    output_dir = tmp_dir / "papers"
    manual_dir.mkdir()
    pdf_path = manual_dir / "Manual fallback paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    result = resolve_manual_pdf(
        FetchedPaper(title="Manual fallback paper", abstract=""),
        str(manual_dir),
        output_dir=output_dir,
        index=1,
    )

    assert result is not None
    assert result.success is True
    assert result.source == "manual_upload"
    assert Path(result.path).exists()
    assert Path(result.path).parent == output_dir
