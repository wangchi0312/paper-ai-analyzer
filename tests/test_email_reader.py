from email.message import EmailMessage

from paper_analyzer.ingestion.email_reader import _get_html_body


def test_get_html_body_single_part():
    msg = EmailMessage()
    msg.set_content("<p>Hello</p>", subtype="html")

    assert _get_html_body(msg) == "<p>Hello</p>\n"
