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


def test_extract_alert_summary_links_from_malformed_clarivate_redirect():
    html = """
    <a href="http://snowplow.apps.clarivate.com/r/tp2?u=www.webofknowledge.comundefinednull%26referrer%3Dtarget%253Dhttps%25253a%25252f%25252fwebofscience.clarivate.cn%25252fwos%25252f%25253fisproductcode%25253dyes%252526init%25253dyes%252526destparams%25253d%2525252fwos%2525252fwoscc%2525252falert-execution-summary%2525252f1aff1f25-0321-4814-a4e4-f9d2167b2c12%2525253falertutfieldname%2525253ddata1%25252526relation%2525253dfalse%252526destapp%25253dwosnx">
      View all results
    </a>
    """

    links = extract_alert_summary_links(html)

    assert links == [
        "https://webofscience.clarivate.cn/wos/woscc/alert-execution-summary/1aff1f25-0321-4814-a4e4-f9d2167b2c12?alertutfieldname=data1"
    ]
