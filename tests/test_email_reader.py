from email.message import EmailMessage

from paper_analyzer.ingestion.email_reader import _get_html_body
from paper_analyzer.ingestion.wos_parser import extract_alert_summary_links


def test_get_html_body_single_part():
    msg = EmailMessage()
    msg.set_content("<p>Hello</p>", subtype="html")

    assert _get_html_body(msg) == "<p>Hello</p>\n"


def test_extract_alert_summary_links():
    html = """
    <a href="http://snowplow.apps.clarivate.com/r/tp2?u=https%3A%2F%2Fwww.webofscience.com%2Fapi%2Fgateway%3FDestLinkType%3DAlertSummary%26KeyQueryID%3Dabc">
      View all 71 citations
    </a>
    """

    links = extract_alert_summary_links(html)

    assert links == ["https://www.webofscience.com/api/gateway?DestLinkType=AlertSummary&KeyQueryID=abc"]
