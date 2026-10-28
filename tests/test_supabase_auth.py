"""Pengujian unit dan integrasi untuk Supabase Provider (User & Credential Token)."""
import json
import pytest
import httpx
from fastapi.testclient import TestClient
from app.main import app, USER_TOKEN_COOKIE
from app import db


@pytest.fixture(autouse=True)
def set_supabase_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mockproject.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "mock-secret-key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-aes256-mock")


def test_supabase_config_secret_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret-key-123")
    cfg = db.get_supabase_config()
    assert cfg["url"] == "https://example.supabase.co"
    assert cfg["key"] == "test-secret-key-123"

    # Test SUPABASE_SERVICE_ROLE_KEY alias
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key-456")
    cfg2 = db.get_supabase_config()
    assert cfg2["key"] == "test-service-key-456"

    # Test SUPABASE_SECRET alias
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SECRET", "test-secret-alias-789")
    cfg3 = db.get_supabase_config()
    assert cfg3["key"] == "test-secret-alias-789"


def test_supabase_init_db_success(monkeypatch, capsys):
    def mock_request(method, path, **kwargs):
        req = httpx.Request(method, f"https://mockproject.supabase.co{path}")
        return httpx.Response(200, json=[], request=req)

    monkeypatch.setattr(db, "_supabase_request", mock_request)
    db.init_db()
    captured = capsys.readouterr().out
    assert "Tabel users siap terhubung" in captured


def test_supabase_init_db_rls_warning(monkeypatch, capsys):
    def mock_request(method, path, **kwargs):
        req = httpx.Request(method, f"https://mockproject.supabase.co{path}")
        return httpx.Response(401, json={"code": "42501", "message": "RLS policy error"}, headers={"content-type": "application/json"}, request=req)

    monkeypatch.setattr(db, "_supabase_request", mock_request)
    db.init_db()
    captured = capsys.readouterr().out
    assert "RLS aktif" in captured


def test_supabase_register_success(monkeypatch):
    client = TestClient(app)

    db_store = []

    def mock_supabase_request(method, path, params=None, json=None, headers=None, **kwargs):
        url = f"https://mockproject.supabase.co{path}"
        req = httpx.Request(method, url)
        if method == "GET":
            # Cek username atau email
            if params and "username" in params:
                val = params["username"].replace("eq.", "")
                matched = [u for u in db_store if u["username"] == val]
                return httpx.Response(200, json=matched, request=req)
            if params and "email" in params:
                val = params["email"].replace("eq.", "")
                matched = [u for u in db_store if u["email"] == val]
                return httpx.Response(200, json=matched, request=req)
            return httpx.Response(200, json=[], request=req)
        elif method == "POST":
            new_id = len(db_store) + 1
            row = {
                "id": new_id,
                "username": json["username"],
                "email": json["email"],
                "password": json["password"],
                "credential_token": json["credential_token"],
                "created_at": "2026-10-27T12:00:00",
            }
            db_store.append(row)
            return httpx.Response(201, json=[row], request=req)
        return httpx.Response(404, request=req)

    monkeypatch.setattr(db, "_supabase_request", mock_supabase_request)

    res = client.post("/api/auth/register", json={
        "username": "supa_user_1",
        "email": "supa1@example.com",
        "password": "mypassword123",
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    u = body["user"]
    assert u["username"] == "supa_user_1"
    assert u["email"] == "supa1@example.com"
    assert u["credential_token"].startswith("cs_live_")
    assert u["token_credential"] == u["credential_token"]
    assert "password" not in u
    assert USER_TOKEN_COOKIE in res.cookies

    # Pastikan data tersimpan di DB terenkripsi
    stored = db_store[0]
    assert stored["password"].startswith("pbkdf2_sha256$")
    assert stored["credential_token"].startswith(db.TOKEN_ENCRYPTION_PREFIX)


def test_supabase_register_duplicate(monkeypatch):
    client = TestClient(app)

    db_store = [{
        "id": 1,
        "username": "existing_user",
        "email": "existing@example.com",
        "password": "hash",
        "credential_token": "token",
        "created_at": "2026-10-27T12:00:00",
    }]

    def mock_supabase_request(method, path, params=None, json=None, headers=None, **kwargs):
        req = httpx.Request(method, f"https://mockproject.supabase.co{path}")
        if method == "GET":
            if params and "username" in params:
                val = params["username"].replace("eq.", "")
                matched = [u for u in db_store if u["username"] == val]
                return httpx.Response(200, json=matched, request=req)
            if params and "email" in params:
                val = params["email"].replace("eq.", "")
                matched = [u for u in db_store if u["email"] == val]
                return httpx.Response(200, json=matched, request=req)
        return httpx.Response(200, json=[], request=req)

    monkeypatch.setattr(db, "_supabase_request", mock_supabase_request)

    # Duplikat username
    res1 = client.post("/api/auth/register", json={
        "username": "existing_user",
        "email": "other@example.com",
        "password": "password123",
    })
    assert res1.status_code == 400
    assert "sudah digunakan" in res1.json()["detail"]

    # Duplikat email
    res2 = client.post("/api/auth/register", json={
        "username": "other_user",
        "email": "existing@example.com",
        "password": "password123",
    })
    assert res2.status_code == 400
    assert "sudah terdaftar" in res2.json()["detail"]


def test_supabase_authenticate_and_me(monkeypatch):
    client = TestClient(app)

    plain_pwd = "my_secure_pwd_123"
    plain_tok = "cs_live_sampletoken1234567890abcdef"
    enc_tok = db.encrypt_token(plain_tok)
    pwd_hash = db.hash_password(plain_pwd)

    db_store = [{
        "id": 42,
        "username": "tester42",
        "email": "tester42@example.com",
        "password": pwd_hash,
        "credential_token": enc_tok,
        "created_at": "2026-10-27T12:00:00",
    }]

    def mock_supabase_request(method, path, params=None, json=None, headers=None, **kwargs):
        req = httpx.Request(method, f"https://mockproject.supabase.co{path}")
        if method == "GET":
            if params and "username" in params:
                val = params["username"].replace("eq.", "")
                matched = [u for u in db_store if u["username"] == val]
                return httpx.Response(200, json=matched, request=req)
            if params and "email" in params:
                val = params["email"].replace("eq.", "")
                matched = [u for u in db_store if u["email"] == val]
                return httpx.Response(200, json=matched, request=req)
            if params and "credential_token" in params:
                val = params["credential_token"].replace("eq.", "")
                matched = [u for u in db_store if u["credential_token"] == val]
                return httpx.Response(200, json=matched, request=req)
            if params and "id" in params:
                val = params["id"].replace("eq.", "")
                matched = [u for u in db_store if str(u["id"]) == val]
                return httpx.Response(200, json=matched, request=req)
        return httpx.Response(200, json=[], request=req)

    monkeypatch.setattr(db, "_supabase_request", mock_supabase_request)

    # 1. Login dengan username
    res_uname = client.post("/api/auth/login", json={
        "username_or_email": "tester42",
        "password": plain_pwd,
    })
    assert res_uname.status_code == 200
    assert res_uname.json()["user"]["username"] == "tester42"
    assert res_uname.json()["user"]["credential_token"] == plain_tok

    # 2. Login dengan email
    res_email = client.post("/api/auth/login", json={
        "username_or_email": "tester42@example.com",
        "password": plain_pwd,
    })
    assert res_email.status_code == 200

    # 3. Login password salah
    res_wrong = client.post("/api/auth/login", json={
        "username_or_email": "tester42",
        "password": "wrongpassword",
    })
    assert res_wrong.status_code == 401

    # 4. Auth me via Bearer token
    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {plain_tok}"})
    assert res_me.status_code == 200
    assert res_me.json()["user"]["username"] == "tester42"


def test_supabase_token_regenerate_and_custom(monkeypatch):
    plain_pwd = "my_secure_pwd_123"
    plain_tok = "cs_live_oldtoken1234567890abcdef"
    enc_tok = db.encrypt_token(plain_tok)
    pwd_hash = db.hash_password(plain_pwd)

    user_record = {
        "id": 10,
        "username": "user10",
        "email": "user10@example.com",
        "password": pwd_hash,
        "credential_token": enc_tok,
        "created_at": "2026-10-27T12:00:00",
    }
    db_store = [user_record]

    def mock_supabase_request(method, path, params=None, json=None, headers=None, **kwargs):
        req = httpx.Request(method, f"https://mockproject.supabase.co{path}")
        if method == "GET":
            if params and "credential_token" in params:
                val = params["credential_token"].replace("eq.", "")
                matched = [u for u in db_store if u["credential_token"] == val]
                return httpx.Response(200, json=matched, request=req)
            if params and "id" in params and "neq." in params.get("id", ""):
                # Uniqueness check for custom token
                val = params["credential_token"].replace("eq.", "")
                exclude_id = params["id"].replace("neq.", "")
                matched = [u for u in db_store if u["credential_token"] == val and str(u["id"]) != exclude_id]
                return httpx.Response(200, json=matched, request=req)
            return httpx.Response(200, json=[], request=req)
        elif method == "PATCH":
            if params and "id" in params:
                uid = params["id"].replace("eq.", "")
                for u in db_store:
                    if str(u["id"]) == uid:
                        u["credential_token"] = json["credential_token"]
                        return httpx.Response(200, json=[u], request=req)
            return httpx.Response(200, json=[], request=req)
        return httpx.Response(404, request=req)

    monkeypatch.setattr(db, "_supabase_request", mock_supabase_request)

    client = TestClient(app)

    # Regenerate token
    res_regen = client.post("/api/auth/token/regenerate", headers={"Authorization": f"Bearer {plain_tok}"})
    assert res_regen.status_code == 200
    new_token = res_regen.json()["credential_token"]
    assert new_token != plain_tok
    assert new_token.startswith("cs_live_")

    # Set custom token
    custom = "custom_supa_token_9999"
    res_custom = client.patch(
        "/api/auth/token",
        json={"token": custom},
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert res_custom.status_code == 200
    assert res_custom.json()["credential_token"] == custom
    assert res_custom.json()["token_credential"] == custom
