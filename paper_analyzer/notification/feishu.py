import base64
import hashlib
import hmac
import time

import requests


MAX_TEXT_CHARS = 12000


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

    chunks = split_feishu_text(text, max_chars=MAX_TEXT_CHARS)
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"（第 {index}/{total} 部分）\n\n" if total > 1 else ""
        _post_feishu_text(
            webhook_url=webhook_url,
            text=prefix + chunk,
            secret=secret,
            timeout=timeout,
        )


def split_feishu_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""
    for block in _split_markdown_blocks(text):
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(block) <= max_chars:
            current = block
        else:
            chunks.extend(_split_long_block(block, max_chars=max_chars))

    if current:
        chunks.append(current)
    return chunks


def _post_feishu_text(
    webhook_url: str,
    text: str,
    secret: str | None,
    timeout: int,
) -> None:
    payload = {
        "msg_type": "text",
        "content": {"text": text},
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


def _split_markdown_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and current:
            blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def _split_long_block(block: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(block):
        chunks.append(block[start : start + max_chars])
        start += max_chars
    return chunks
