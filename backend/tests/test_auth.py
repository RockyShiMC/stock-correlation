import importlib

import pytest
from fastapi.testclient import TestClient

USER, PASSWORD = "tester", "test-password-123"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_USERNAME", USER)
    monkeypatch.setenv("APP_PASSWORD", PASSWORD)
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    import app.auth
    import app.main
    app.auth._failures.clear()
    importlib.reload(app.main)
    with TestClient(app.main.app) as c:
        yield c


def login(client, password=PASSWORD):
    return client.post("/login", json={"username": USER, "password": password})


def test_api_requires_login(client):
    assert client.get("/search", params={"q": "x"}).status_code == 401
    assert client.get("/analysis/abc").status_code == 401
    assert client.post("/analysis", json={}).status_code == 401


def test_pages_redirect_to_login(client):
    for path in ("/", "/stock.html", "/analysis.html"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303, path
        assert r.headers["location"] == "/login.html?next=" + path.replace("/", "%2F")
    r = client.get("/stock.html?symbol=GOOGL&market=US", follow_redirects=False)
    assert r.headers["location"] == "/login.html?next=%2Fstock.html%3Fsymbol%3DGOOGL%26market%3DUS"


def test_login_page_is_public(client):
    assert client.get("/login.html").status_code == 200
    assert client.get("/style.css").status_code == 200
    assert client.get("/common.js", follow_redirects=False).status_code == 303


def test_wrong_password_rejected_then_locked(client):
    for _ in range(5):
        assert login(client, "wrong").status_code == 401
    assert login(client).status_code == 429  # 锁定期间正确密码也拒绝


def test_login_session_and_logout(client):
    assert login(client).status_code == 200
    assert client.get("/me").json() == {"user": USER}
    page = client.get("/")
    assert page.status_code == 200 and "选择标的" in page.text
    assert client.get("/analysis/nonexistent").status_code == 404  # 已登录，走到接口本身
    assert client.post("/logout").status_code == 200
    assert client.get("/me").status_code == 401


def test_missing_config_fails_fast(monkeypatch):
    import app.auth
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    with pytest.raises(app.auth.AuthConfigError):
        app.auth.settings()
