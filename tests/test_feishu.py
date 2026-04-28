from paper_analyzer.notification import feishu
from paper_analyzer.notification.feishu import send_feishu_text


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
