import argparse
from dataclasses import asdict
from datetime import datetime
import json
import re
from pathlib import Path

from paper_analyzer.data.schema import FetchAudit, FetchedPaper
from paper_analyzer.ingestion.email_reader import fetch_wos_emails
from paper_analyzer.ingestion.wos_parser import enrich_from_web, parse_wos_email
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
) -> list[FetchedPaper]:
    emails = fetch_wos_emails(since_date=since_date, max_emails=max_emails)
    papers: list[FetchedPaper] = []

    for message_id, _subject, html in emails:
        parsed = parse_wos_email(html, source_email_id=message_id)
        for paper in parsed:
            papers.append(paper if no_web else _enrich_or_keep(paper))

    parsed_paper_count = len(papers)
    papers = deduplicate_papers(papers)
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
        ),
        audit_output_path,
    )
    return papers


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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    papers = fetch_papers(
        since_date=args.since,
        max_emails=args.max_emails,
        no_web=args.no_web,
        output_path=args.output,
        audit_output_path=args.audit_output,
    )
    print(f"已获取论文 {len(papers)} 篇，保存到：{args.output}")


if __name__ == "__main__":
    main()
