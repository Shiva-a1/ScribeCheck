from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_and_config():
    assert client.get("/api/health").json() == {"ok": True}
    assert client.get("/api/config").json()["auth_mode"] == "dev"


def test_requests_without_a_token_are_rejected():
    assert client.get("/api/exams").status_code == 401
    assert client.get("/api/student/exams").status_code == 401


def test_dev_login_issues_a_token():
    assert "token" in client.post("/api/dev/login", json={"email": "Someone@UFL.edu"}).json()
