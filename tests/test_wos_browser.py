from paper_analyzer.ingestion.wos_browser import parse_wos_result_page


def test_parse_wos_result_page_extracts_record_links():
    html = """
    <html>
      <body>
        <a href="/wos/woscc/full-record/WOS:001234">A useful physics-informed neural network paper</a>
        <a href="/wos/woscc/full-record/WOS:001234">A useful physics-informed neural network paper</a>
        <a href="/help">Export</a>
      </body>
    </html>
    """

    papers = parse_wos_result_page(html, source_email_id="<id@example.com>")

    assert len(papers) == 1
    assert papers[0].title == "A useful physics-informed neural network paper"
    assert papers[0].link == "https://www.webofscience.com/wos/woscc/full-record/WOS:001234"
    assert papers[0].fetch_method == "wos_browser"
