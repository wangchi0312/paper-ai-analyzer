import html as html_lib
import re
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


def extract_alert_summary_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        text = anchor.get_text(" ", strip=True).lower()
        url = _extract_wos_url(href)
        if not url:
            continue
        if "destlinktype=alertsummary" in url.lower() or "view all" in text:
            links.append(url)
    return _deduplicate_links(links)


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

    raw_url = html_lib.unescape(tracking_url).strip()
    candidates = [raw_url]

    # 解析 snowplow 追踪链接：...?u=<encoded_url>&co=...
    parsed = urlparse(raw_url)
    qs = parse_qs(parsed.query)

    for key in ("u", "target", "referrer", "url"):
        for value in qs.get(key, []):
            if value:
                candidates.append(_unquote_repeated(value))

    for candidate in candidates:
        alert_url = _extract_nested_alert_url(candidate)
        if alert_url:
            return alert_url
        direct_url = _normalize_allowed_wos_url(candidate)
        if direct_url:
            return direct_url

    return None


def _extract_nested_alert_url(raw_url: str) -> str | None:
    text = _unquote_repeated(raw_url)

    direct_url = _normalize_allowed_wos_url(text)
    if direct_url:
        dest_url = _extract_destparams_url(direct_url)
        if dest_url:
            return dest_url

    for match in re.findall(r"https?://[^\s\"'<>]+", text):
        nested_url = _normalize_allowed_wos_url(match.rstrip(").,;"))
        if not nested_url:
            continue
        dest_url = _extract_destparams_url(nested_url)
        if dest_url:
            return dest_url
        if "alert-execution-summary" in nested_url.lower():
            return nested_url

    if "alert-execution-summary" not in text.lower():
        return None

    origin = "https://www.webofscience.com"
    origin_match = re.search(r"https?://(?:www\.)?webofscience\.com|https?://webofscience\.clarivate\.cn", text)
    if origin_match:
        origin = origin_match.group(0)

    path_match = re.search(r"(/wos/woscc/alert-execution-summary/[A-Za-z0-9-]+(?:\?[^&\s\"'<>]+)?)", text)
    if not path_match:
        return None
    return origin.rstrip("/") + path_match.group(1)


def _extract_destparams_url(url: str) -> str | None:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    for value in qs.get("destparams", []):
        decoded = _unquote_repeated(value)
        if "alert-execution-summary" not in decoded.lower():
            continue
        if decoded.startswith("/"):
            return f"{parsed.scheme}://{parsed.netloc}{decoded}"
        nested = _normalize_allowed_wos_url(decoded)
        if nested:
            return nested
    return None


def _normalize_allowed_wos_url(raw_url: str) -> str | None:
    url = _unquote_repeated(html_lib.unescape(raw_url).strip())
    if not url:
        return None
    if url.startswith("//"):
        url = f"https:{url}"
    if url.startswith(("www.webofscience.com", "www.webofknowledge.com", "webofscience.clarivate.cn")):
        url = f"https://{url}"
    if "undefinednull" in url.lower():
        return None

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = parsed.netloc.lower()
    allowed_hosts = {
        "www.webofscience.com",
        "webofscience.com",
        "www.webofknowledge.com",
        "webofknowledge.com",
        "webofscience.clarivate.cn",
    }
    if host not in allowed_hosts:
        return None
    return url


def _unquote_repeated(value: str, max_rounds: int = 5) -> str:
    current = value
    for _ in range(max_rounds):
        decoded = unquote(current)
        if decoded == current:
            return decoded
        current = decoded
    return current


def _deduplicate_links(links: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        unique.append(link)
    return unique


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
