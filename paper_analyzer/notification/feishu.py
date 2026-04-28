import base64
import hashlib
import hmac
import time

import requests


MAX_TEXT_CHARS = 18000


def send_feishu_text(
    webhook_url: str,
    text: str,
    secret: str | None = None,
    timeout: int = 10,
) -> None:
    if not webhook_url.strip():
        raise ValueError("缺少飞书 webhook URL")
    if not text.strip():
        raise ValueError("缺少要推送的文本内容")

    payload = {
        "msg_type": "text",
        "content": {"text": _truncate_text(text)},
    }
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = _build_feishu_sign(timestamp, secret)

    response = requests.post(webhook_url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if data.get("code", 0) != 0:
        raise RuntimeError(f"飞书推送失败：{data}")


def _build_feishu_sign(timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"),
        b"",
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _truncate_text(text: str) -> str:
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[:MAX_TEXT_CHARS] + "\n\n（内容过长，已截断；完整周报请在本地前端查看。）"
