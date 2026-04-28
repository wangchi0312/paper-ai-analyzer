import imaplib
import email
import email.message
from email.header import decode_header
from pathlib import Path

from paper_analyzer.utils.config import EmailConfig, load_email_config
from paper_analyzer.utils.logger import get_logger

logger = get_logger(__name__)


def _decode_header_value(value):
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _get_html_body(msg: email.message.Message) -> str | None:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        if msg.get_content_type() == "text/html":
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return None


def _load_seen_message_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("message_ids", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def _save_seen_message_ids(path: Path, message_ids: set[str]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"message_ids": sorted(message_ids)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_wos_emails(
    since_date: str | None = None,
    max_emails: int = 50,
    config: EmailConfig | None = None,
    seen_emails_path: str = "data/processed/seen_emails.json",
    ignore_seen: bool = False,
) -> list[tuple[str, str, str]]:
    """Fetch WoS Citation Alert emails from QQ mailbox.

    Returns list of (message_id, subject, html_body) tuples.
    """
    emails, _stats = fetch_wos_emails_with_stats(
        since_date=since_date,
        max_emails=max_emails,
        config=config,
        seen_emails_path=seen_emails_path,
        ignore_seen=ignore_seen,
    )
    return emails


def fetch_wos_emails_with_stats(
    since_date: str | None = None,
    max_emails: int = 50,
    config: EmailConfig | None = None,
    seen_emails_path: str = "data/processed/seen_emails.json",
    ignore_seen: bool = False,
) -> tuple[list[tuple[str, str, str]], dict[str, int]]:
    if config is None:
        config = load_email_config()

    seen_path = Path(seen_emails_path)
    seen_ids = set() if ignore_seen else _load_seen_message_ids(seen_path)
    stats = {
        "inbox_email_count": 0,
        "checked_email_count": 0,
        "matched_wos_email_count": 0,
        "skipped_seen_email_count": 0,
    }

    imap = None
    try:
        imap = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
        imap.login(config.address, config.auth_code)
        logger.info("IMAP 登录成功：%s", config.address)

        imap.select("INBOX")

        # QQ 邮箱 IMAP 搜索不可靠，获取全部邮件 ID 后按主题过滤
        status, data = imap.search(None, "ALL")
        if status != "OK":
            raise RuntimeError("IMAP 搜索失败")

        all_ids = data[0].split()
        stats["inbox_email_count"] = len(all_ids)
        logger.info("收件箱共 %d 封邮件", len(all_ids))

        # 先用 HEADER 粗筛
        wos_ids = []
        # WoS Alert 不一定密集出现在最近邮件里，默认扩大扫描窗口。
        scan_limit = max(max_emails * 20, max_emails)
        check_ids = all_ids[-min(len(all_ids), scan_limit, 2000) :]
        stats["checked_email_count"] = len(check_ids)

        for mid in check_ids:
            status, msg_data = imap.fetch(mid, "(BODY[HEADER.FIELDS (SUBJECT FROM MESSAGE-ID)])")
            if status != "OK":
                continue
            header_text = msg_data[0][1].decode("utf-8", errors="replace").lower()
            if "web of science" in header_text or "clarivate" in header_text:
                stats["matched_wos_email_count"] += 1
                # 提取 Message-ID 检查是否已处理
                msg_id_raw = msg_data[0][1].decode("utf-8", errors="replace")
                msg_id_match = _extract_message_id(msg_id_raw)
                if not ignore_seen and msg_id_match and msg_id_match in seen_ids:
                    stats["skipped_seen_email_count"] += 1
                    logger.debug("跳过已处理邮件：%s", msg_id_match)
                    continue
                wos_ids.append(mid)

        logger.info("找到 %d 封未处理的 WoS 邮件", len(wos_ids))

        # 只取最近 max_emails 封
        wos_ids = wos_ids[-max_emails:]

        results = []
        new_seen_ids = set()

        for mid in wos_ids:
            status, msg_data = imap.fetch(mid, "(RFC822)")
            if status != "OK":
                logger.warning("获取邮件 %s 失败", mid)
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = _decode_header_value(msg.get("Subject", ""))
            message_id = msg.get("Message-ID", "")
            html = _get_html_body(msg)

            if html:
                results.append((message_id, subject, html))
                if message_id:
                    new_seen_ids.add(message_id)
                logger.info("获取邮件：%s", subject[:60])
            else:
                logger.warning("邮件无 HTML 正文：%s", subject[:60])

        # 保存已处理邮件 ID
        if new_seen_ids and not ignore_seen:
            seen_ids.update(new_seen_ids)
            _save_seen_message_ids(seen_path, seen_ids)
            logger.info("已保存 %d 个已处理邮件 ID", len(new_seen_ids))

        return results, stats

    except Exception as exc:
        logger.error("IMAP 操作失败：%s", exc)
        raise
    finally:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass


def _extract_message_id(header_text: str) -> str | None:
    import re

    match = re.search(r"Message-ID:\s*(<[^>]+>)", header_text, re.IGNORECASE)
    return match.group(1) if match else None
