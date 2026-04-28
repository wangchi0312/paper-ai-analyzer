import shutil
from pathlib import Path

from pipeline.build_profile import find_pdf_paths


def _make_tmp_dir(name: str) -> Path:
    path = Path("data/outputs/test_tmp") / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def test_find_pdf_paths_non_recursive():
    tmp_path = _make_tmp_dir("non_recursive")
    (tmp_path / "a.pdf").write_text("x")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.pdf").write_text("x")

    paths = find_pdf_paths(tmp_path)

    assert [path.name for path in paths] == ["a.pdf"]


def test_find_pdf_paths_recursive_with_limit():
    tmp_path = _make_tmp_dir("recursive_limit")
    (tmp_path / "a.pdf").write_text("x")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.pdf").write_text("x")

    paths = find_pdf_paths(tmp_path, recursive=True, limit=1)

    assert len(paths) == 1
