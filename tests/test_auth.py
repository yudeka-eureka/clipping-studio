import uuid
import pytest
import httpx
from fastapi.testclient import TestClient

from app.main import app, USER_TOKEN_COOKIE
from app import db


@pytest.fixture(autouse=True)
def mock_supabase_db(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mockproject.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "mock-secret-key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-aes256-mock")

    users_db: list[dict] = []

    def mock_supabase_request(method, path, params=None, json=None, headers=None, **kwargs):
        req = httpx.Request(method, f"https://mockproject.supabase.co{path}")
        if method == "GET":
            if params and "id" in params and "neq." in str(params.get("id")):
                exclude_id = params["id"].replace("neq.", "")
                matched = [u for u in users_db if str(u["id"]) != exclude_id]
                if "credential_token" in params:
                    tok = params["credential_token"].replace("eq.", "")
                    matched = [u for u in matched if u["credential_token"] == tok]
                return httpx.Response(200, json=matched, request=req)
            if params and "id" in params:
                val = params["id"].replace("eq.", "")
                matched = [u for u in users_db if str(u["id"]) == val]
                return httpx.Response(200, json=matched, request=req)
            if params and "username" in params:
                val = params["username"].replace("eq.", "")
                matched = [u for u in users_db if u["username"] == val]
                return httpx.Response(200, json=matched, request=req)
            if params and "email" in params:
                val = params["email"].replace("eq.", "")
                matched = [u for u in users_db if u["email"].lower() == val.lower()]
                return httpx.Response(200, json=matched, request=req)
            if params and "credential_token" in params:
                val = params["credential_token"].replace("eq.", "")
                matched = [u for u in users_db if u["credential_token"] == val]
                return httpx.Response(200, json=matched, request=req)
            return httpx.Response(200, json=users_db[:1], request=req)
        elif method == "POST":
            # Check unique
            if any(u["username"] == json["username"] for u in users_db):
                return httpx.Response(409, text="duplicate key value violates unique constraint 'users_username_key'", request=req)
            if any(u["email"].lower() == json["email"].lower() for u in users_db):
                return httpx.Response(409, text="duplicate key value violates unique constraint 'users_email_key'", request=req)
            new_id = len(users_db) + 1
            row = {
                "id": new_id,
                "username": json["username"],
                "email": json["email"],
                "password": json["password"],
                "credential_token": json["credential_token"],
                "created_at": "2026-10-27T12:00:00",
            }
            users_db.append(row)
            return httpx.Response(201, json=[row], request=req)
        elif method == "PATCH":
            if params and "id" in params:
                uid = params["id"].replace("eq.", "")
                for u in users_db:
                    if str(u["id"]) == uid:
                        u.update(json)
                        return httpx.Response(200, json=[u], request=req)
            return httpx.Response(200, json=[], request=req)
        return httpx.Response(404, request=req)

    monkeypatch.setattr(db, "_supabase_request", mock_supabase_request)
    db.init_db()
    return users_db


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
    assert user["credential_token"].startswith("cs_live_")
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
    token = reg.json()["user"]["credential_token"]
    assert token == reg.json()["user"]["token_credential"]

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
    old_token = reg.json()["user"]["credential_token"]

    # Regenerate token
    res_regen = client.post("/api/auth/token/regenerate")
    assert res_regen.status_code == 200
    new_token = res_regen.json()["credential_token"]
    assert new_token == res_regen.json()["token_credential"]
    assert new_token != old_token
    assert new_token.startswith("cs_live_")

    # Set custom token
    custom = f"my_custom_token_{uuid.uuid4().hex[:10]}"
    res_custom = client.patch("/api/auth/token", json={"token": custom})
    assert res_custom.status_code == 200
    assert res_custom.json()["credential_token"] == custom
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


def test_token_is_encrypted_with_aes256_in_database(mock_supabase_db):
    client = TestClient(app)
    uname = random_uname()
    res = client.post("/api/auth/register", json={
        "username": uname,
        "email": f"{uname}@example.com",
        "password": "strong_password_123",
    })
    assert res.status_code == 200
    user_data = res.json()["user"]
    plain_token = user_data["credential_token"]
    assert plain_token.startswith("cs_live_")

    # Periksa record langsung dari database Supabase
    users = [u for u in mock_supabase_db if u["username"] == uname]
    assert len(users) == 1
    row = users[0]
    raw_db_token = row["credential_token"]
    raw_pwd = row["password"]

    # Password di database HARUS ter-hash pbkdf2_sha256
    assert raw_pwd.startswith("pbkdf2_sha256$")
    assert "strong_password_123" not in raw_pwd

    # Token mentah di database HARUS terenkripsi AES-256 dan TIDAK sama dengan plaintext
    assert raw_db_token != plain_token
    assert raw_db_token.startswith(db.TOKEN_ENCRYPTION_PREFIX)
    assert plain_token not in raw_db_token

    # Fungsi dekripsi harus mengembalikan token asli
    decrypted = db.decrypt_token(raw_db_token)
    assert decrypted == plain_token
