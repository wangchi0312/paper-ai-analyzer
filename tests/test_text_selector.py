from paper_analyzer.pdf.text_selector import extract_abstract, select_representative_text


def test_extract_abstract_before_introduction():
    text = """
Title

Abstract
This paper studies literature tracking with embeddings.

Introduction
Details here.
"""
    assert extract_abstract(text) == "This paper studies literature tracking with embeddings."


def test_select_representative_text_fallback():
    selected, abstract = select_representative_text("a " * 3000, max_chars=20)
    assert abstract == ""
    assert len(selected) == 20
