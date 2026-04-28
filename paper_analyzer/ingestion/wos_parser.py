from urllib.parse import unquote, urlparse, parse_qs

from bs4 import BeautifulSoup

from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.utils.logger import get_logger

logger = get_logger(__name__)


def parse_wos_email(html: str, source_email_id: str | None = None) -> list[FetchedPaper]:
    """Parse WoS Citation Alert email HTML and extract paper information."""
    soup = BeautifulSoup(html, "html.parser")

    papers = []

    # 找到 alert-record-container，里面每条引用是一个 table.container
    record_container = soup.find("table", id="alert-record-container")
    if not record_container:
        logger.warning("未找到 alert-record-container")
        return papers

    # 每条记录是一个直接的子 table.container
    record_tables = record_container.find_all("table", class_="container", recursive=False)
    # 如果 recursive=False 没找到（可能嵌套结构不同），尝试更深的搜索
    if not record_tables:
        # 实际结构：container > tr > td > table.container
        record_tables = record_container.find_all("table", class_="container")

    for table in record_tables:
        paper = _parse_record_table(table, source_email_id)
        if paper:
            papers.append(paper)

    logger.info("从邮件中解析出 %d 篇论文", len(papers))
    return papers


def _parse_record_table(table, source_email_id: str | None = None) -> FetchedPaper | None:
    title = ""
    link = None
    authors = None
    venue = None
    abstract = ""

    # 标题：在 <div style="...font-weight: 600;"> 内的 <a class="smallV110">
    title_div = table.find("div", style=lambda s: s and "font-weight: 600" in s)
    if title_div:
        title_link = title_div.find("a", class_="smallV110")
        if title_link:
            title = title_link.get_text(strip=True)
            raw_href = title_link.get("href", "")
            link = _extract_wos_url(raw_href)

    if not title:
        return None

    # 作者和期刊：在后续的 <span style="font-weight: normal;"> 中
    spans = table.find_all("span", style=lambda s: s and "font-weight: normal" in s)
    if len(spans) >= 1:
        authors = spans[0].get_text(strip=True)
    if len(spans) >= 2:
        venue = spans[1].get_text(strip=True)

    # 摘要：在 <div style="line-height: 18px; font-weight: normal;"> 中
    abstract_div = table.find("div", style=lambda s: s and "line-height: 18px" in s and "font-weight: normal" in s)
    if abstract_div:
        abstract = abstract_div.get_text(strip=True)

    return FetchedPaper(
        title=title,
        abstract=abstract,
        doi=None,
        link=link,
        authors=authors,
        venue=venue,
        source_email_id=source_email_id,
        fetch_method="email",
    )


def _extract_wos_url(tracking_url: str) -> str | None:
    """Extract the actual WoS URL from a Snowplow tracking redirect URL."""
    if not tracking_url:
        return None

    # 解析 snowplow 追踪链接：...?u=<encoded_url>&co=...
    parsed = urlparse(tracking_url)
    qs = parse_qs(parsed.query)

    encoded_url = qs.get("u", [None])[0]
    if encoded_url:
        return unquote(encoded_url)

    # 如果不是追踪链接，直接返回原始 URL
    if tracking_url.startswith("https://www.webofscience.com"):
        return tracking_url

    return None


def enrich_from_web(paper: FetchedPaper, timeout: int = 15) -> FetchedPaper:
    """Attempt to fetch more complete abstract from WoS page.

    Falls back to email content if the request fails.
    """
    if not paper.link:
        logger.debug("无链接，跳过网页抓取：%s", paper.title[:40])
        return paper

    try:
        import requests
    except ImportError:
        logger.warning("缺少 requests 包，无法抓取网页")
        return paper

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = requests.get(paper.link, headers=headers, timeout=timeout)

        if response.status_code != 200:
            logger.warning("网页请求失败 %d：%s", response.status_code, paper.title[:40])
            return paper

        page_soup = BeautifulSoup(response.text, "html.parser")

        # 尝试提取更完整的 abstract
        abstract_div = page_soup.find("div", class_="abstract-content")
        if not abstract_div:
            abstract_div = page_soup.find("p", class_="abstract")
        if not abstract_div:
            # 尝试 meta 标签
            meta_abstract = page_soup.find("meta", attrs={"name": "citation_abstract"})
            if meta_abstract:
                web_abstract = meta_abstract.get("content", "").strip()
                if web_abstract and len(web_abstract) > len(paper.abstract):
                    paper.abstract = web_abstract
                    paper.fetch_method = "web"
                    return paper
        if abstract_div:
            web_abstract = abstract_div.get_text(strip=True)
            if web_abstract and len(web_abstract) > len(paper.abstract):
                paper.abstract = web_abstract
                paper.fetch_method = "web"
                return paper

        logger.info("网页未找到更完整摘要，保留邮件内容：%s", paper.title[:40])
        return paper

    except requests.RequestException as exc:
        logger.warning("网页请求异常，保留邮件内容：%s — %s", paper.title[:40], exc)
        return paper
