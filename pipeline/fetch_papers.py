import argparse
from dataclasses import asdict
from datetime import datetime
import json
import re
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from paper_analyzer.data.schema import FetchAudit, FetchedPaper
from paper_analyzer.ingestion.email_reader import fetch_wos_emails_with_stats
from paper_analyzer.ingestion.wos_browser import WosBrowserSession
from paper_analyzer.ingestion.wos_parser import enrich_from_web, extract_alert_summary_links, parse_wos_email
from paper_analyzer.utils.logger import get_logger


DEFAULT_FETCHED_PAPERS_PATH = "data/processed/fetched_papers.json"
DEFAULT_FETCH_AUDIT_PATH = "data/processed/fetch_audit.json"
logger = get_logger(__name__)


def fetch_papers(
    since_date: str | None = None,
    max_emails: int = 50,
    no_web: bool = False,
    output_path: str = DEFAULT_FETCHED_PAPERS_PATH,
    audit_output_path: str = DEFAULT_FETCH_AUDIT_PATH,
    ignore_seen: bool = False,
    expand_alert_pages: bool = False,
    use_browser: bool = False,
    browser_max_pages: int = 20,
    browser_manual_login_wait_seconds: int = 0,
    progress_callback: Callable[[str], None] | None = None,
) -> list[FetchedPaper]:
    _emit_progress(progress_callback, "开始连接邮箱并扫描 WoS Citation Alert 邮件")
    emails, email_stats = fetch_wos_emails_with_stats(
        since_date=since_date,
        max_emails=max_emails,
        ignore_seen=ignore_seen,
    )
    _emit_progress(
        progress_callback,
        f"已找到 {len(emails)} 封 Citation Alert；收件箱 {email_stats['inbox_email_count']} 封，检查 {email_stats['checked_email_count']} 封",
    )
    papers: list[FetchedPaper] = []
    alert_summary_link_count = 0
    expanded_paper_count = 0
    browser_expanded_paper_count = 0
    browser_new_unique_paper_count = 0
    browser_duplicate_paper_count = 0
    browser_expand_error_count = 0
    browser_expand_last_error: str | None = None
    email_details: list[dict] = []

    browser_context: WosBrowserSession | None = None
    browser_session: WosBrowserSession | None = None
    try:
        for email_index, (message_id, subject, html) in enumerate(emails, start=1):
            clean_subject = " ".join(subject.split())
            _emit_progress(progress_callback, f"解析第 {email_index}/{len(emails)} 封邮件：{clean_subject}")
            parsed = parse_wos_email(html, source_email_id=message_id)
            _emit_progress(progress_callback, f"邮件正文解析出 {len(parsed)} 篇论文")
            email_detail = _new_email_detail(message_id, subject, len(parsed))
            for paper in parsed:
                papers.append(paper if no_web else _enrich_or_keep(paper))
            if expand_alert_pages:
                summary_links = extract_alert_summary_links(html)
                alert_summary_link_count += len(summary_links)
                email_detail["alert_summary_link_count"] = len(summary_links)
                if summary_links:
                    _emit_progress(progress_callback, f"发现 {len(summary_links)} 个 WoS 完整结果页链接，开始扩展候选")
                for link_index, link in enumerate(summary_links, start=1):
                    link_detail = _new_link_detail(link_index, link)
                    expanded = _fetch_alert_summary_papers(link, source_email_id=message_id)
                    expanded_paper_count += len(expanded)
                    email_detail["requests_expanded_paper_count"] += len(expanded)
                    link_detail["requests_expanded_paper_count"] = len(expanded)
                    if use_browser and not expanded:
                        _emit_progress(progress_callback, f"浏览器扩展第 {link_index}/{len(summary_links)} 个 WoS 链接")
                        try:
                            if browser_session is None:
                                _emit_progress(progress_callback, "启动 Playwright Chromium；本次抓取会复用同一个浏览器窗口")
                                browser_context = WosBrowserSession(
                                    max_pages=browser_max_pages,
                                    manual_login_wait_seconds=browser_manual_login_wait_seconds,
                                )
                                browser_session = browser_context.__enter__()
                            browser_expanded = browser_session.fetch_alert(
                                link,
                                source_email_id=message_id,
                            )
                        except Exception as exc:
                            logger.warning("浏览器模式扩展 WoS 结果失败：%s (%s)", link, exc)
                            browser_expand_error_count += 1
                            browser_expand_last_error = _format_exception(exc)
                            email_detail["browser_expand_error_count"] += 1
                            email_detail["browser_expand_last_error"] = browser_expand_last_error
                            link_detail["browser_error"] = browser_expand_last_error
                            _emit_progress(progress_callback, f"浏览器扩展失败：{browser_expand_last_error}")
                            browser_expanded = []
                        browser_expanded_paper_count += len(browser_expanded)
                        new_unique, duplicate = _count_new_unique_papers(papers, browser_expanded)
                        browser_new_unique_paper_count += new_unique
                        browser_duplicate_paper_count += duplicate
                        email_detail["browser_expanded_paper_count"] += len(browser_expanded)
                        email_detail["browser_new_unique_paper_count"] += new_unique
                        email_detail["browser_duplicate_paper_count"] += duplicate
                        link_detail["browser_expanded_paper_count"] = len(browser_expanded)
                        link_detail["browser_new_unique_paper_count"] = new_unique
                        link_detail["browser_duplicate_paper_count"] = duplicate
                        expanded.extend(browser_expanded)
                        _emit_progress(progress_callback, f"浏览器返回 {len(browser_expanded)} 篇，其中新增 {new_unique} 篇，重复 {duplicate} 篇")
                    email_detail["alert_links"].append(link_detail)
                    for paper in expanded:
                        papers.append(paper if no_web else _enrich_or_keep(paper))
            email_details.append(email_detail)
    finally:
        if browser_context is not None:
            browser_context.__exit__(None, None, None)

    parsed_paper_count = len(papers)
    papers = deduplicate_papers(papers)
    _emit_progress(progress_callback, f"抓取完成：原始 {parsed_paper_count} 条，去重后 {len(papers)} 篇")
    save_fetched_papers(papers, output_path)
    save_fetch_audit(
        FetchAudit(
            fetched_at=datetime.now().isoformat(timespec="seconds"),
            since_date=since_date,
            max_emails=max_emails,
            no_web=no_web,
            email_count=len(emails),
            parsed_paper_count=parsed_paper_count,
            unique_paper_count=len(papers),
            duplicate_paper_count=parsed_paper_count - len(papers),
            output_path=output_path,
            alert_summary_link_count=alert_summary_link_count,
            expanded_paper_count=expanded_paper_count,
            inbox_email_count=email_stats["inbox_email_count"],
            checked_email_count=email_stats["checked_email_count"],
            matched_wos_email_count=email_stats["matched_wos_email_count"],
            skipped_seen_email_count=email_stats["skipped_seen_email_count"],
            skipped_non_alert_email_count=email_stats["skipped_non_alert_email_count"],
            browser_max_pages=browser_max_pages if use_browser else 0,
            browser_manual_login_wait_seconds=browser_manual_login_wait_seconds if use_browser else 0,
            browser_expanded_paper_count=browser_expanded_paper_count,
            browser_new_unique_paper_count=browser_new_unique_paper_count,
            browser_duplicate_paper_count=browser_duplicate_paper_count,
            browser_expand_error_count=browser_expand_error_count,
            browser_expand_last_error=browser_expand_last_error,
            email_details=email_details,
        ),
        audit_output_path,
    )
    _emit_progress(progress_callback, f"抓取审计已保存：{audit_output_path}")
    return papers


def _new_email_detail(message_id: str, subject: str, parsed_count: int) -> dict:
    return {
        "message_id": message_id,
        "subject": subject,
        "email_parsed_paper_count": parsed_count,
        "alert_summary_link_count": 0,
        "requests_expanded_paper_count": 0,
        "browser_expanded_paper_count": 0,
        "browser_new_unique_paper_count": 0,
        "browser_duplicate_paper_count": 0,
        "browser_expand_error_count": 0,
        "browser_expand_last_error": None,
        "alert_links": [],
    }


def _new_link_detail(link_index: int, link: str) -> dict:
    return {
        "index": link_index,
        "url_summary": _summarize_url(link),
        "requests_expanded_paper_count": 0,
        "browser_expanded_paper_count": 0,
        "browser_new_unique_paper_count": 0,
        "browser_duplicate_paper_count": 0,
        "browser_error": None,
    }


def _emit_progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def deduplicate_papers(papers: list[FetchedPaper]) -> list[FetchedPaper]:
    seen: set[str] = set()
    unique: list[FetchedPaper] = []

    for paper in papers:
        key = _paper_key(paper)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(paper)

    return unique


def _enrich_or_keep(paper: FetchedPaper) -> FetchedPaper:
    try:
        return enrich_from_web(paper)
    except Exception as exc:
        logger.warning("网页补全失败，保留邮件内容：%s (%s)", paper.title, exc)
        return paper


def _format_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {_sanitize_error_text(message)}"
    return f"{type(exc).__name__}: {_sanitize_error_text(repr(exc))}"


def _sanitize_error_text(text: str) -> str:
    return re.sub(r"https?://[^\s'\"，；)]+", lambda match: _summarize_url(match.group(0)), text)


def _count_new_unique_papers(existing: list[FetchedPaper], candidates: list[FetchedPaper]) -> tuple[int, int]:
    seen = {_paper_key(paper) for paper in existing if _paper_key(paper)}
    new_unique = 0
    duplicate = 0
    for paper in candidates:
        key = _paper_key(paper)
        if not key:
            duplicate += 1
            continue
        if key in seen:
            duplicate += 1
            continue
        seen.add(key)
        new_unique += 1
    return new_unique, duplicate


def _summarize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    return f"{parsed.netloc}{parsed.path}"


def _fetch_alert_summary_papers(url: str, source_email_id: str | None = None) -> list[FetchedPaper]:
    try:
        import requests
    except ImportError:
        logger.warning("缺少 requests 包，无法扩展 WoS 完整结果页")
        return []

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=30,
            allow_redirects=True,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("WoS 完整结果页请求失败：%s (%s)", url, exc)
        return []

    papers = parse_wos_email(response.text, source_email_id=source_email_id)
    if not papers:
        logger.warning("WoS 完整结果页未解析出论文，可能需要登录或页面为前端渲染：%s", url)
    return papers


def save_fetched_papers(papers: list[FetchedPaper], output_path: str = DEFAULT_FETCHED_PAPERS_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(paper) for paper in papers], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def save_fetch_audit(audit: FetchAudit, output_path: str = DEFAULT_FETCH_AUDIT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(audit), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_fetched_papers(path: str = DEFAULT_FETCHED_PAPERS_PATH) -> list[FetchedPaper]:
    fetched_path = Path(path)
    if not fetched_path.exists():
        raise FileNotFoundError(f"抓取结果不存在，请先运行 fetch-papers：{fetched_path}")

    data = json.loads(fetched_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"抓取结果格式错误，应为数组：{fetched_path}")

    return [FetchedPaper(**item) for item in data]


def _paper_key(paper: FetchedPaper) -> str:
    doi = (paper.doi or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    return f"title:{_normalize_title(paper.title)}"


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().lower()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 WoS Citation Alert 邮件获取论文信息")
    parser.add_argument("--since", default=None, help="只获取该日期之后的邮件，格式 YYYY-MM-DD")
    parser.add_argument("--max", type=int, default=50, dest="max_emails", help="最多检查的邮件数量")
    parser.add_argument("--no-web", action="store_true", help="跳过网页补全，只使用邮件内容")
    parser.add_argument("--output", default=DEFAULT_FETCHED_PAPERS_PATH, help="抓取结果保存路径")
    parser.add_argument("--audit-output", default=DEFAULT_FETCH_AUDIT_PATH, help="抓取审计保存路径")
    parser.add_argument("--ignore-seen", action="store_true", help="重新扫描已处理过的 WoS 邮件")
    parser.add_argument("--expand-alert-pages", action="store_true", help="进入 WoS View all 完整结果页扩展候选论文")
    parser.add_argument("--use-browser", action="store_true", help="requests 无法解析完整结果页时使用 Playwright 浏览器模式")
    parser.add_argument("--browser-max-pages", type=int, default=20, help="浏览器模式最多翻页数")
    parser.add_argument("--browser-manual-login-wait-seconds", type=int, default=0, help="浏览器模式遇到登录页时等待人工完成登录的秒数")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    papers = fetch_papers(
        since_date=args.since,
        max_emails=args.max_emails,
        no_web=args.no_web,
        output_path=args.output,
        audit_output_path=args.audit_output,
        ignore_seen=args.ignore_seen,
        expand_alert_pages=args.expand_alert_pages,
        use_browser=args.use_browser,
        browser_max_pages=args.browser_max_pages,
        browser_manual_login_wait_seconds=args.browser_manual_login_wait_seconds,
    )
    print(f"已获取论文 {len(papers)} 篇，保存到：{args.output}")


if __name__ == "__main__":
    main()
