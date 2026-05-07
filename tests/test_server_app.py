from fastapi.testclient import TestClient

from paper_analyzer.server.app import create_app


def test_server_chat_returns_pending_action_for_wos_request():
    client = TestClient(create_app())

    response = client.post("/api/chat", json={"message": "帮我筛选 WoS 邮件里的文献"})

    assert response.status_code == 200
    data = response.json()
    assert data["pending_action"]["tool_name"] == "screen_wos_alert_tool"
    assert "不会下载 PDF" in data["message"]
    assert "最多" in data["message"]
    assert "封 WoS Alert 邮件" in data["message"]


def test_server_chat_uses_current_wos_limits(monkeypatch):
    monkeypatch.setenv("WOS_MAX_EMAILS", "2")
    monkeypatch.setenv("WOS_BROWSER_MAX_PAGES", "2")
    monkeypatch.setenv("WOS_USE_BROWSER", "true")
    client = TestClient(create_app())

    response = client.post("/api/chat", json={"message": "帮我筛选 WoS 邮件"})

    assert response.status_code == 200
    data = response.json()
    assert data["pending_action"]["tool_name"] == "screen_wos_alert_tool"
    assert data["pending_action"]["args"]["max_emails"] == 2
    assert data["pending_action"]["args"]["browser_max_pages"] == 2
    assert "最多 2 封 WoS Alert 邮件" in data["message"]


def test_server_upload_rejects_non_pdf():
    client = TestClient(create_app())

    response = client.post("/api/upload", files={"file": ("note.txt", b"hello", "text/plain")})

    assert response.status_code == 400


def test_server_can_cancel_job():
    client = TestClient(create_app())

    response = client.post(
        "/api/jobs",
        json={
            "action": {
                "tool_name": "generate_report_tool",
                "args": {"title": "test", "items": [{"title": "a", "summary": "b"}]},
                "summary": "生成报告",
                "requires_confirmation": True,
                "action_id": "x",
                "created_at": "2026-05-07T00:00:00Z",
            }
        },
    )

    assert response.status_code == 200
    cancel = client.post(f"/api/jobs/{response.json()['job_id']}/cancel")
    assert cancel.status_code == 200


def test_server_can_add_interest_memory():
    client = TestClient(create_app())

    response = client.post(
        "/api/memory/interest",
        json={
            "text": "我关注 PINN 求解 PDE",
            "memory_type": "positive_interest",
            "evidence_source": "wos_feedback",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["memory_id"]
    assert data["memory"]["interest_memory"] >= 1


def test_server_can_add_paper_memory():
    client = TestClient(create_app())

    response = client.post(
        "/api/memory/paper",
        json={
            "text": "A paper about PINN",
            "metadata": {"title": "PINN Paper", "doi": "10.1/test"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["memory_id"]
    assert data["memory"]["paper_corpus"] >= 1
