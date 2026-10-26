import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app, USER_TOKEN_COOKIE
from app import db


@pytest.fixture(autouse=True)
def init_database():
    db.init_db()


def random_uname():
    return f"user_{uuid.uuid4().hex[:8]}"


def test_register_success():
    client = TestClient(app)
    uname = random_uname()
    email = f"{uname}@example.com"
    res = client.post("/api/auth/register", json={
        "username": uname,
        "email": email,
        "password": "secretpassword123",
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["ok"] is True
    user = data["user"]
    assert user["username"] == uname
    assert user["email"] == email
    assert user["token_credential"].startswith("cs_live_")
    assert USER_TOKEN_COOKIE in res.cookies


def test_register_duplicate_username_and_email():
    client = TestClient(app)
    uname = random_uname()
    email = f"{uname}@example.com"
    res1 = client.post("/api/auth/register", json={
        "username": uname,
        "email": email,
        "password": "password123",
    })
    assert res1.status_code == 200

    # Duplicate username
    res2 = client.post("/api/auth/register", json={
        "username": uname,
        "email": f"diff_{email}",
        "password": "password123",
    })
    assert res2.status_code == 400
    assert "sudah digunakan" in res2.json()["detail"]

    # Duplicate email
    res3 = client.post("/api/auth/register", json={
        "username": f"diff_{uname}",
        "email": email,
        "password": "password123",
    })
    assert res3.status_code == 400
    assert "sudah terdaftar" in res3.json()["detail"]


def test_register_validation():
    client = TestClient(app)
    # Short password
    res = client.post("/api/auth/register", json={
        "username": random_uname(),
        "email": "test@example.com",
        "password": "123",
    })
    assert res.status_code == 400
    assert "minimal 6 karakter" in res.json()["detail"]

    # Invalid username
    res2 = client.post("/api/auth/register", json={
        "username": "a!",
        "email": "test@example.com",
        "password": "validpassword",
    })
    assert res2.status_code == 400


def test_login_success_and_failure():
    client = TestClient(app)
    uname = random_uname()
    email = f"{uname}@example.com"
    client.post("/api/auth/register", json={
        "username": uname,
        "email": email,
        "password": "correct_password_123",
    })

    # Login with username
    res_uname = client.post("/api/auth/login", json={
        "username_or_email": uname,
        "password": "correct_password_123",
    })
    assert res_uname.status_code == 200
    assert res_uname.json()["user"]["username"] == uname
    assert USER_TOKEN_COOKIE in res_uname.cookies

    # Login with email
    res_email = client.post("/api/auth/login", json={
        "username_or_email": email,
        "password": "correct_password_123",
    })
    assert res_email.status_code == 200
    assert res_email.json()["user"]["email"] == email

    # Login with wrong password
    res_wrong = client.post("/api/auth/login", json={
        "username_or_email": uname,
        "password": "wrong_password",
    })
    assert res_wrong.status_code == 401

    # Login with non-existent user
    res_none = client.post("/api/auth/login", json={
        "username_or_email": "non_existent_user_999",
        "password": "some_password",
    })
    assert res_none.status_code == 401


def test_auth_me_resolution():
    client = TestClient(app)
    uname = random_uname()
    email = f"{uname}@example.com"
    reg = client.post("/api/auth/register", json={
        "username": uname,
        "email": email,
        "password": "mypassword123",
    })
    token = reg.json()["user"]["token_credential"]

    # 1. Clean client (no cookie or header)
    clean_client = TestClient(app)
    res_anon = clean_client.get("/api/auth/me")
    assert res_anon.status_code == 200
    assert res_anon.json()["user"] is None

    # 2. Authenticated via cookie (from reg client)
    res_cookie = client.get("/api/auth/me")
    assert res_cookie.status_code == 200
    assert res_cookie.json()["user"]["username"] == uname

    # 3. Authenticated via Bearer token
    res_bearer = clean_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_bearer.status_code == 200
    assert res_bearer.json()["user"]["username"] == uname

    # 4. Authenticated via X-Auth-Token
    res_header = clean_client.get("/api/auth/me", headers={"X-Auth-Token": token})
    assert res_header.status_code == 200
    assert res_header.json()["user"]["username"] == uname


def test_token_regenerate_and_customization():
    client = TestClient(app)
    uname = random_uname()
    reg = client.post("/api/auth/register", json={
        "username": uname,
        "email": f"{uname}@example.com",
        "password": "password123",
    })
    old_token = reg.json()["user"]["token_credential"]

    # Regenerate token
    res_regen = client.post("/api/auth/token/regenerate")
    assert res_regen.status_code == 200
    new_token = res_regen.json()["token_credential"]
    assert new_token != old_token
    assert new_token.startswith("cs_live_")

    # Set custom token
    custom = f"my_custom_token_{uuid.uuid4().hex[:10]}"
    res_custom = client.patch("/api/auth/token", json={"token": custom})
    assert res_custom.status_code == 200
    assert res_custom.json()["token_credential"] == custom

    # Verify custom token works on /api/auth/me
    verify_client = TestClient(app)
    res_me = verify_client.get("/api/auth/me", headers={"Authorization": f"Bearer {custom}"})
    assert res_me.status_code == 200
    assert res_me.json()["user"]["username"] == uname


def test_logout():
    client = TestClient(app)
    uname = random_uname()
    client.post("/api/auth/register", json={
        "username": uname,
        "email": f"{uname}@example.com",
        "password": "password123",
    })
    res_me = client.get("/api/auth/me")
    assert res_me.json()["user"] is not None

    # Logout
    res_logout = client.post("/api/auth/logout")
    assert res_logout.status_code == 200

    # Cookie is invalidated / deleted
    res_me_after = client.get("/api/auth/me")
    assert res_me_after.json()["user"] is None
