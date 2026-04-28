"""一次性脚本：连接 QQ 邮箱，搜索 WoS Citation Alert 邮件，保存 HTML 正文到本地。"""

import imaplib
import email
from email.header import decode_header
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

IMAP_HOST = "imap.qq.com"
IMAP_PORT = 993
EMAIL_ADDR = os.getenv("QQ_EMAIL", "")
AUTH_CODE = os.getenv("QQ_EMAIL_AUTH_CODE", "")

OUTPUT_DIR = Path("data/debug_emails")


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


def _get_html_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/html":
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return None


def main():
    if not EMAIL_ADDR or not AUTH_CODE:
        print("错误：请在 .env 中配置 QQ_EMAIL 和 QQ_EMAIL_AUTH_CODE")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"连接 {IMAP_HOST}:{IMAP_PORT} ...")
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(EMAIL_ADDR, AUTH_CODE)
    print("登录成功")

    imap.select("INBOX")

    # QQ 邮箱 IMAP 搜索不可靠，改为获取最近 N 封邮件后按主题过滤
    print("获取最近 200 封邮件，按主题过滤 ...")
    status, data = imap.search(None, "ALL")
    if status != "OK":
        print("搜索失败")
        imap.logout()
        return

    all_ids = data[0].split()
    print(f"收件箱共 {len(all_ids)} 封邮件")

    # 先取最近的 200 封，检查主题
    recent_ids = all_ids[-200:]
    wos_ids = []
    for mid in recent_ids:
        status, msg_data = imap.fetch(mid, "(BODY[HEADER.FIELDS (SUBJECT FROM)])")
        if status != "OK":
            continue
        header_text = msg_data[0][1].decode("utf-8", errors="replace").lower()
        if "web of science" in header_text or "clarivate" in header_text:
            wos_ids.append(mid)

    mail_ids = wos_ids
    print(f"找到 {len(mail_ids)} 封 WoS 相关邮件")

    if not mail_ids:
        print("未找到任何相关邮件。尝试列出最近的 10 封邮件发件人：")
        status, data = imap.search(None, "ALL")
        if status == "OK":
            all_ids = data[0].split()
            for mid in all_ids[-10:]:
                status, msg_data = imap.fetch(mid, "(BODY[HEADER.FIELDS (FROM SUBJECT)])")
                if status == "OK":
                    header_text = msg_data[0][1].decode("utf-8", errors="replace")
                    print(f"  {mid.decode()}: {header_text.strip()}")
        imap.logout()
        return

    # 只取最近 3 封
    for mid in mail_ids[-3:]:
        print(f"\n获取邮件 {mid.decode()} ...")
        status, msg_data = imap.fetch(mid, "(RFC822)")
        if status != "OK":
            print(f"  获取失败")
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = _decode_header_value(msg.get("Subject", ""))
        from_addr = _decode_header_value(msg.get("From", ""))
        date = msg.get("Date", "")
        message_id = msg.get("Message-ID", "")

        print(f"  主题：{subject}")
        print(f"  发件人：{from_addr}")
        print(f"  日期：{date}")
        print(f"  Message-ID：{message_id}")

        html = _get_html_body(msg)
        if html:
            safe_name = subject[:80].replace("/", "_").replace("\\", "_").replace(":", "_").replace("\n", " ").replace("\r", " ").strip()
            output_path = OUTPUT_DIR / f"{mid.decode()}_{safe_name}.html"
            output_path.write_text(html, encoding="utf-8")
            print(f"  HTML 已保存：{output_path}")
            print(f"  HTML 长度：{len(html)} 字符")
        else:
            print("  未找到 HTML 正文，尝试保存纯文本...")
            text = None
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        text = payload.decode(charset, errors="replace")
                        break
            if text:
                output_path = OUTPUT_DIR / f"{mid.decode()}_plain.txt"
                output_path.write_text(text, encoding="utf-8")
                print(f"  纯文本已保存：{output_path}")
            else:
                print("  无法提取任何正文内容")
                # 保存整个原始邮件
                output_path = OUTPUT_DIR / f"{mid.decode()}_raw.eml"
                output_path.write_bytes(raw_email)
                print(f"  原始邮件已保存：{output_path}")

    imap.logout()
    print("\n完成")


if __name__ == "__main__":
    main()
