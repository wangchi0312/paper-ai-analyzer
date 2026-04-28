from paper_analyzer.notification import feishu
from paper_analyzer.notification.feishu import send_feishu_text, split_feishu_text


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


def test_send_feishu_text_posts_text_payload(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return FakeResponse({"code": 0})

    monkeypatch.setattr(feishu.requests, "post", fake_post)

    send_feishu_text("https://example.com/webhook", "hello", timeout=3)

    assert calls[0][0] == "https://example.com/webhook"
    assert calls[0][1]["msg_type"] == "text"
    assert calls[0][1]["content"]["text"] == "hello"
    assert calls[0][2] == 3


def test_send_feishu_text_with_secret_adds_signature(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append(json)
        return FakeResponse({"code": 0})

    monkeypatch.setattr(feishu.requests, "post", fake_post)
    monkeypatch.setattr(feishu.time, "time", lambda: 123)

    send_feishu_text("https://example.com/webhook", "hello", secret="secret")

    payload = calls[0]
    assert payload["timestamp"] == "123"
    assert payload["sign"]


def test_send_feishu_text_sends_multiple_chunks(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append(json["content"]["text"])
        return FakeResponse({"code": 0})

    monkeypatch.setattr(feishu.requests, "post", fake_post)
    monkeypatch.setattr(feishu, "MAX_TEXT_CHARS", 20)

    send_feishu_text("https://example.com/webhook", "## A\n" + "x" * 30 + "\n## B\n" + "y" * 10)

    assert len(calls) > 1
    assert calls[0].startswith("（第 1/")
    assert calls[-1].startswith(f"（第 {len(calls)}/{len(calls)} 部分）")
    assert "内容过长，已截断" not in "\n".join(calls)


def test_split_feishu_text_prefers_heading_boundaries():
    chunks = split_feishu_text("# T\n\n## A\nshort\n\n## B\n" + "x" * 10, max_chars=20)

    assert len(chunks) == 2
    assert chunks[1].startswith("## B")
