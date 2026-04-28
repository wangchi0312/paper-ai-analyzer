from paper_analyzer.pdf.parser import _is_title_candidate_line, _is_trustworthy_metadata_title


def test_reject_template_metadata_title():
    assert not _is_trustworthy_metadata_title("Instructions for use of the document class elsart")


def test_accept_real_metadata_title():
    assert _is_trustworthy_metadata_title("Adaptive activation functions accelerate convergence in PINNs")


def test_reject_preprint_marker_as_title_line():
    assert not _is_title_candidate_line("Preprint not peer reviewed")
