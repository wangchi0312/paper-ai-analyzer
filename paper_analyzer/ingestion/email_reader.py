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
    emails, _stats, _hit_seen = fetch_wos_emails_with_stats(
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
) -> tuple[list[tuple[str, str, str]], dict[str, int], bool]:
    if config is None:
        config = load_email_config()

    seen_path = Path(seen_emails_path)
    seen_ids = set() if ignore_seen else _load_seen_message_ids(seen_path)
    stats = {
        "inbox_email_count": 0,
        "checked_email_count": 0,
        "matched_wos_email_count": 0,
        "skipped_seen_email_count": 0,
        "skipped_non_alert_email_count": 0,
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

        # 从最新邮件开始往前扫描，收集未处理的 Citation Alert。
        # 正式版：遇到已处理的邮件立即停止，不再往前扫描。
        # 测试阶段：使用 --ignore-seen 完全忽略 seen 机制，返回最新 N 封。
        wos_ids: list[bytes] = []
        scan_limit = min(len(all_ids), 2000)
        check_ids = all_ids[-scan_limit:]
        stats["checked_email_count"] = len(check_ids)
        hit_seen_alert = False

        for mid in reversed(check_ids):
            status, msg_data = imap.fetch(mid, "(BODY[HEADER.FIELDS (SUBJECT FROM MESSAGE-ID)])")
            if status != "OK":
                continue
            header_text = msg_data[0][1].decode("utf-8", errors="replace").lower()
            if "web of science" not in header_text and "clarivate" not in header_text:
                continue
            stats["matched_wos_email_count"] += 1
            msg_id_raw = msg_data[0][1].decode("utf-8", errors="replace")
            msg_id_match = _extract_message_id(msg_id_raw)
            if not ignore_seen and msg_id_match and msg_id_match in seen_ids:
                stats["skipped_seen_email_count"] += 1
                hit_seen_alert = True
                break  # 正式版：遇到已处理邮件立即停止
            wos_ids.append(mid)
            # 收集足够多候选后再退出 header 扫描（非 Alert 系统通知可能占一定比例）
            if len(wos_ids) >= max(max_emails * 20, 200):
                break

        logger.info("找到 %d 封未处理的 WoS 邮件（跳过 %d 封已处理）", len(wos_ids), stats["skipped_seen_email_count"])

        results = []
        new_seen_ids = set()

        for mid in wos_ids:
            if len(results) >= max_emails:
                break
            status, msg_data = imap.fetch(mid, "(RFC822)")
            if status != "OK":
                logger.warning("获取邮件 %s 失败", mid)
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = _decode_header_value(msg.get("Subject", ""))
            message_id = msg.get("Message-ID", "")
            html = _get_html_body(msg)

            if not html:
                logger.warning("邮件无 HTML 正文：%s", subject[:60])
                continue
            if not _looks_like_wos_alert_email(subject, html):
                stats["skipped_non_alert_email_count"] += 1
                logger.info("跳过非 Citation Alert 邮件：%s", subject[:60])
                continue

            results.append((message_id, subject, html))
            if message_id:
                new_seen_ids.add(message_id)
            logger.info("获取邮件：%s", subject[:60])

        # 保存已处理邮件 ID
        if new_seen_ids and not ignore_seen:
            seen_ids.update(new_seen_ids)
            _save_seen_message_ids(seen_path, seen_ids)
            logger.info("已保存 %d 个已处理邮件 ID", len(new_seen_ids))

        return results, stats, hit_seen_alert

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


def _looks_like_wos_alert_email(subject: str, html: str) -> bool:
    lowered_subject = subject.lower()
    lowered_html = html.lower()
    if "password reset" in lowered_subject or "password changed" in lowered_subject:
        return False
    alert_markers = [
        "alert-record-container",
        "destlinktype=alertsummary",
        "alert-execution-summary",
        "view all",
    ]
    return any(marker in lowered_html for marker in alert_markers)
