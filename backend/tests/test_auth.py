import uuid


def _email():
    return f"auth-{uuid.uuid4().hex[:8]}@test.bhoomitra.in"


def test_register_login_me(client):
    email = _email()
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "Register@2026x", "full_name": "Reg User"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "Register@2026x"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] and body["refresh_token"] and body["token_type"] == "bearer"
    assert "bhoomitra_refresh" in r.cookies
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}).json()
    assert me["email"] == email and me["roles"] == ["public_user"]
    assert "search.use" in me["permissions"] and "document.create" not in me["permissions"]


def test_weak_password_rejected(client):
    r = client.post("/api/v1/auth/register", json={"email": _email(), "password": "short", "full_name": "Weak"})
    assert r.status_code in (400, 422)


def test_wrong_password_and_lockout(client):
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "Correct@2026x", "full_name": "Lock User"})
    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"email": email, "password": "Wrong@2026x"})
        assert r.status_code == 401
        assert "password" not in r.json()["error"]["message"].lower() or "invalid" in r.json()["error"]["message"].lower()
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "Correct@2026x"})
    assert r.status_code in (401, 423), "account should be locked after 5 failures"


def test_refresh_rotation_and_reuse_detection(client):
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "Rotate@2026x", "full_name": "Rot User"})
    rt = client.post("/api/v1/auth/login", json={"email": email, "password": "Rotate@2026x"}).json()["refresh_token"]
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert r1.status_code == 200
    new_rt = r1.json()["refresh_token"]
    assert new_rt != rt
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert r2.status_code == 401 and r2.json()["error"]["code"] == "token_reuse"
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": new_rt})
    assert r3.status_code == 401, "whole token family must be revoked after reuse"


def test_logout_and_password_change_invalidates(client):
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "Change@2026x", "full_name": "Chg User"})
    tok = client.post("/api/v1/auth/login", json={"email": email, "password": "Change@2026x"}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    r = client.post("/api/v1/auth/password/change", json={"current_password": "Change@2026x", "new_password": "Changed@2027y"}, headers=h)
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 401, "old access token must be invalid after password change"
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 401
    tok2 = client.post("/api/v1/auth/login", json={"email": email, "password": "Changed@2027y"}).json()
    h2 = {"Authorization": f"Bearer {tok2['access_token']}"}
    assert client.post("/api/v1/auth/logout", json={"refresh_token": tok2["refresh_token"]}, headers=h2).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tok2["refresh_token"]}).status_code == 401


def test_forgot_and_reset_password(client):
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "Forgot@2026x", "full_name": "Fgt User"})
    r = client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert r.status_code == 200
    token = r.json().get("detail", {}).get("reset_token")
    assert token, "reset token is returned in test env"
    r = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "Reset@2027y"})
    assert r.status_code == 200, r.text
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "Reset@2027y"}).status_code == 200
    assert client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "Reset@2028z"}).status_code in (400, 401, 422), "token is single-use"


def test_security_headers_and_request_id(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-request-id")
