from datetime import datetime, timezone

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.fulltext.spis import (
    build_spis_search_url,
    download_spis_direct_pdf,
    parse_spis_search_results,
    select_pdf_attachment_for_paper,
    select_spis_result,
    submit_spis_detail_form,
    _extract_download_target,
)
from paper_analyzer.ingestion.email_reader import PdfEmailAttachment


def test_build_spis_search_url_encodes_doi():
    url = build_spis_search_url("10.1016/j.ress.2026.112694")

    assert url == "https://spis.hnlat.com/scholar/list?val=10.1016%2Fj.ress.2026.112694"


def test_parse_spis_search_results_extracts_detail_link_and_doi():
    html = """
    <div class="paper">
      <a href="/scholar/detail/g-abc">The prediction of limit wheel profile</a>
      <span>https://doi.org/10.1016/j.ress.2026.112694</span>
    </div>
    """

    results = parse_spis_search_results(html)

    assert len(results) == 1
    assert results[0].title == "The prediction of limit wheel profile"
    assert results[0].url == "https://spis.hnlat.com/scholar/detail/g-abc"
    assert results[0].doi == "10.1016/j.ress.2026.112694"


def test_parse_spis_search_results_extracts_article_card_download():
    html = """
    <article class="article">
      <div class="d-t jump" title="1、Hybrid two-stage reconstruction of multiscale subsurface flow">title</div>
      <div class="button-action-group">
        <div class="action-button download">
          <a href="/api/article/downloadLog?link=https%3A%2F%2Farxiv.org%2Fpdf%2F2501.13271%3F&title=x">下载</a>
        </div>
      </div>
    </article>
    """

    results = parse_spis_search_results(html)

    assert results[0].title == "Hybrid two-stage reconstruction of multiscale subsurface flow"
    assert results[0].download_url.startswith("https://spis.hnlat.com/api/article/downloadLog")


def test_extract_download_target_reads_link_param():
    target = _extract_download_target(
        "https://spis.hnlat.com/api/article/downloadLog?link=https%3A%2F%2Farxiv.org%2Fpdf%2F2501.13271%3F&title=x"
    )

    assert target == "https://arxiv.org/pdf/2501.13271?"


def test_select_spis_result_prefers_doi_then_title():
    paper = FetchedPaper(
        title="The prediction of limit wheel profile using geometric-constrained residual Bayesian neural networks",
        abstract="",
        doi="10.1016/j.ress.2026.112694",
    )
    results = parse_spis_search_results(
        """
        <div><a href="/scholar/detail/g-wrong">Different title</a><span>10.1/wrong</span></div>
        <div><a href="/scholar/detail/g-right">Another title</a><span>10.1016/j.ress.2026.112694</span></div>
        """
    )

    assert select_spis_result(paper, results).url.endswith("g-right")


def test_select_spis_result_uses_title_similarity_for_multiple_results():
    paper = FetchedPaper(title="Physics informed neural network solver", abstract="")
    results = parse_spis_search_results(
        """
        <div><a href="/scholar/detail/g-1">Completely unrelated article</a></div>
        <div><a href="/scholar/detail/g-2">Physics informed neural network solver for equations</a></div>
        """
    )

    assert select_spis_result(paper, results).url.endswith("g-2")


def test_select_pdf_attachment_for_paper_matches_doi():
    paper = FetchedPaper(title="Some Paper", abstract="", doi="10.1016/j.ress.2026.112694")
    attachment = _attachment(subject="Document delivery 10.1016/j.ress.2026.112694", filename="paper.pdf")

    assert select_pdf_attachment_for_paper(paper, [attachment]) is attachment


def test_select_pdf_attachment_for_paper_matches_title_keywords():
    paper = FetchedPaper(title="Geometric constrained residual Bayesian neural networks", abstract="")
    attachment = _attachment(subject="Document delivery", filename="bayesian-neural-networks.pdf")

    assert select_pdf_attachment_for_paper(paper, [attachment]) is attachment


def test_submit_spis_detail_form_uses_expected_controls():
    page = FakePage()

    status = submit_spis_detail_form(page, "user@example.com")

    assert status == "submitted"
    assert page.email_value == "user@example.com"
    assert page.checkbox_checked is True
    assert page.clicked is True


def _attachment(subject: str, filename: str) -> PdfEmailAttachment:
    return PdfEmailAttachment(
        subject=subject,
        sender="spis@example.com",
        message_id="<1>",
        received_at=datetime.now(timezone.utc),
        filename=filename,
        payload=b"%PDF-1.4\n",
        body_text="",
    )


class FakePage:
    def __init__(self):
        self.email_value = ""
        self.checkbox_checked = False
        self.clicked = False
        self.clicks = 0

    def locator(self, selector):
        if selector == "body":
            return FakeLocator(self, "body")
        if "placeholder" in selector or "type='email'" in selector:
            return FakeLocator(self, "email")
        if "checkbox" in selector:
            return FakeLocator(self, "checkbox")
        if "doc-delivery-btn" in selector or "确认" in selector:
            return FakeLocator(self, "button")
        return FakeLocator(self, "missing")

    def wait_for_timeout(self, _timeout):
        pass


class FakeLocator:
    def __init__(self, page, kind):
        self.page = page
        self.kind = kind
        self.first = self
        self.last = self

    def count(self):
        return 0 if self.kind == "missing" else 1

    def inner_text(self, timeout):
        return "提交成功" if self.page.clicked else "文献求助"

    def fill(self, value):
        self.page.email_value = value

    def check(self, force=False):
        self.page.checkbox_checked = True

    def click(self, timeout=0):
        self.page.clicked = True
