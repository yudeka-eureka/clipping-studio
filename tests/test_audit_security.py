"""Security audit tests: endpoint authorization, secret exposure, user isolation, and injection defense."""
import asyncio
import os
import pytest
import httpx
from fastapi.testclient import TestClient

from app.main import app, USER_TOKEN_COOKIE
from app import db, main, security
from app.jobs import hub, store


@pytest.fixture(autouse=True)
def setup_mock_db(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mockproject.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "super-secret-service-role-key-999")
    monkeypatch.setenv("SECRET_KEY", "32-bytes-master-secret-key-mock12")
    db.invalidate_user_cache()


def test_public_mode_blocks_sensitive_endpoints(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", True)
    client = TestClient(app)

    # 1. POST /api/config should be blocked with 403
    res_cfg = client.post("/api/config", json={"provider": "gemini", "api_key": "hacked"})
    assert res_cfg.status_code == 403
    assert "dinonaktifkan dalam PUBLIC_MODE" in res_cfg.json()["detail"]

    # 2. POST /api/pricing should be blocked with 403
    res_price = client.post("/api/pricing", json={"tier": "custom", "usd_idr": 16000})
    assert res_price.status_code == 403
    assert "dinonaktifkan dalam PUBLIC_MODE" in res_price.json()["detail"]

    # 3. Buffer accounts mutations should be blocked with 403
    res_badd = client.post("/api/buffer/accounts", json={"label": "hack", "api_key": "bad"})
    assert res_badd.status_code == 403

    res_bedit = client.patch("/api/buffer/accounts/acc1", json={"label": "hack"})
    assert res_bedit.status_code == 403

    res_bdel = client.delete("/api/buffer/accounts/acc1")
    assert res_bdel.status_code == 403


def test_public_mode_blocks_branding_and_buffer_publishing(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", True)
    client = TestClient(app)

    # 1. Branding mutations blocked
    res_logo_patch = client.patch("/api/branding/logos/lg1", json={"label": "hack"})
    assert res_logo_patch.status_code == 403
    assert "dinonaktifkan dalam PUBLIC_MODE" in res_logo_patch.json()["detail"]

    res_logo_del = client.delete("/api/branding/logos/lg1")
    assert res_logo_del.status_code == 403

    res_logo_def = client.post("/api/branding/default-logo", json={"logo_id": "lg1"})
    assert res_logo_def.status_code == 403

    res_bmp_patch = client.patch("/api/branding/bumpers/bmp1", json={"label": "hack"})
    assert res_bmp_patch.status_code == 403

    res_bmp_del = client.delete("/api/branding/bumpers/bmp1")
    assert res_bmp_del.status_code == 403

    res_bmp_def = client.post("/api/branding/default-bumper", json={"role": "intro", "bumper_id": "bmp1"})
    assert res_bmp_def.status_code == 403

    # 2. Buffer channels and accounts hidden
    res_channels = client.get("/api/buffer/channels")
    assert res_channels.status_code == 200
    assert res_channels.json()["channels"] == []
    assert res_channels.json()["accounts"] == []

    res_accounts = client.get("/api/buffer/accounts")
    assert res_accounts.status_code == 200
    assert res_accounts.json()["accounts"] == []

    # 3. Buffer publishing blocked with 403
    res_pub = client.post("/api/jobs/job1/clips/c1/publish", json={"text": "hello"})
    assert res_pub.status_code == 403
    assert "dinonaktifkan dalam PUBLIC_MODE" in res_pub.json()["detail"]


def test_supabase_secret_key_never_leaked():
    client = TestClient(app)

    # 1. Config endpoint
    res = client.get("/api/config")
    assert res.status_code == 200
    config_text = res.text
    assert "super-secret-service-role-key" not in config_text
    assert "SUPABASE_SECRET_KEY" not in config_text
    assert "SUPABASE_SERVICE_ROLE_KEY" not in config_text
    assert "mockproject.supabase.co" not in config_text

    # 2. AI & Media credentials endpoints
    res_ai = client.get("/api/credentials/ai")
    assert "super-secret-service-role-key" not in res_ai.text

    res_media = client.get("/api/credentials/media")
    assert "super-secret-service-role-key" not in res_media.text


def test_secret_redaction_defense_in_depth(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "super-secret-service-role-key-999")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "super-secret-cloudinary-key-888")

    job = {
        "id": "job_test_redact",
        "name": "Test Redact",
        "_ai_context": {"key": "AIzaSySecretAIKey"},
        "logs": [],
    }

    # Redact in log string
    raw_log = "Error in connection: super-secret-service-role-key-999 and AIzaSySecretAIKey and super-secret-cloudinary-key-888"
    redacted = store.redact(job, raw_log)
    assert "super-secret-service-role-key-999" not in redacted
    assert "AIzaSySecretAIKey" not in redacted
    assert "super-secret-cloudinary-key-888" not in redacted
    assert "[REDACTED]" in redacted

    # Redact in public_job
    job_with_leaks = {
        "id": "job123",
        "name": "Leaky Job",
        "owner_session_id": "sess-secret",
        "user_id": 999,
        "_ai_context": {"key": "AIzaSySecretAIKey"},
        "meta": {"info": "Contains super-secret-service-role-key-999"},
    }
    public = store.public_job(job_with_leaks)
    assert "_ai_context" not in public
    assert "owner_session_id" not in public
    assert "user_id" not in public
    assert "super-secret-service-role-key-999" not in str(public)
    assert "[REDACTED]" in public["meta"]["info"]


def test_authenticated_user_isolation(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", True)

    # Mock user 1 and user 2
    user1 = {"id": 101, "username": "user101", "credential_token": "cs_live_user101_tok"}
    user2 = {"id": 202, "username": "user202", "credential_token": "cs_live_user202_tok"}

    monkeypatch.setattr(main.store, "jobs", {
        "job_u1": {
            "id": "job_u1",
            "name": "User 1 Job",
            "created_at": 100,
            "status": "ready",
            "clips": [],
            "owner_session_id": "session-aaa",
            "user_id": 101,
        },
        "job_u2": {
            "id": "job_u2",
            "name": "User 2 Job",
            "created_at": 200,
            "status": "ready",
            "clips": [],
            "owner_session_id": "session-bbb",
            "user_id": 202,
        },
    })

    # Simulate request as user1 (even with a different session ID)
    token_sess = main.CURRENT_SESSION.set("session-ccc-new")
    token_user = main.CURRENT_USER.set(user1)
    try:
        # User 1 should see job_u1
        owned = main.owned_jobs()
        assert [j["id"] for j in owned] == ["job_u1"]
        assert main.get_job("job_u1")["id"] == "job_u1"

        # User 1 must NOT be able to access job_u2
        with pytest.raises(main.HTTPException) as err:
            main.get_job("job_u2")
        assert err.value.status_code == 404
    finally:
        main.CURRENT_SESSION.reset(token_sess)
        main.CURRENT_USER.reset(token_user)


def test_password_and_identifier_dos_and_injection_protection(monkeypatch):
    # 1. Password excessively long (> 128 chars) is rejected with 400
    with pytest.raises(ValueError, match="maksimal 128 karakter"):
        db.register_user("valid_user", "valid@example.com", "A" * 129)

    # 2. Authentication with password > 128 chars returns None without hashing
    assert db.authenticate_user("valid_user", "A" * 129) is None

    # 3. PostgREST filter injection attempt in identifier returns None safely
    assert db.authenticate_user("admin,email.eq.admin@example.com", "mypassword") is None
    assert db.authenticate_user("admin;DROP TABLE users;", "mypassword") is None
    assert db.authenticate_user("A" * 101, "mypassword") is None

    # 4. Token validation prevents injection
    assert db.get_user_by_token("token_with_illegal_char$!*") is None
    assert db.get_user_by_token("A" * 125) is None


def test_decrypt_token_corrupted_returns_empty():
    # Corrupted ciphertext should fail gracefully and return empty string, NOT leak raw ciphertext
    corrupted = f"{db.TOKEN_ENCRYPTION_PREFIX}corrupted_base64_payload_here"
    assert db.decrypt_token(corrupted) == ""
    assert db.decrypt_token(None) == ""


def test_user_cache_invalidation_workflow(monkeypatch):
    users_db = [{
        "id": 1,
        "username": "cache_user",
        "email": "cache@example.com",
        "password": db.hash_password("password123"),
        "credential_token": db.encrypt_token("cs_live_cache_token_123"),
        "created_at": "2026-10-27T12:00:00",
        "updated_at": "2026-10-27T12:00:00",
    }]

    call_count = 0

    def mock_supabase_request(method, path, params=None, json=None, headers=None, **kwargs):
        nonlocal call_count
        call_count += 1
        req = httpx.Request(method, f"https://mockproject.supabase.co{path}")
        if method == "GET":
            if params and "credential_token" in params:
                tok = params["credential_token"].replace("eq.", "")
                matched = [u for u in users_db if u["credential_token"] == tok]
                return httpx.Response(200, json=matched, request=req)
        elif method == "PATCH":
            if params and "id" in params:
                uid = params["id"].replace("eq.", "")
                for u in users_db:
                    if str(u["id"]) == uid:
                        u.update(json)
                        return httpx.Response(200, json=[u], request=req)
        return httpx.Response(200, json=[], request=req)

    monkeypatch.setattr(db, "_supabase_request", mock_supabase_request)
    db.invalidate_user_cache()

    # 1. First fetch hits Supabase
    u1 = db.get_user_by_token("cs_live_cache_token_123")
    assert u1 is not None
    assert u1["username"] == "cache_user"
    assert call_count == 1

    # 2. Second fetch served from cache (no extra Supabase request)
    u2 = db.get_user_by_token("cs_live_cache_token_123")
    assert u2 is not None
    assert u2["username"] == "cache_user"
    assert call_count == 1  # Still 1!

    # 3. Regenerating token invalidates cache
    new_tok = db.regenerate_token(1)
    assert call_count == 2
    assert "cs_live_cache_token_123" not in db._USER_CACHE

    # 4. Old token fails (negative lookup cached)
    assert db.get_user_by_token("cs_live_cache_token_123") is None
    # Subsequent negative lookup is cached
    prev_calls = call_count
    assert db.get_user_by_token("cs_live_cache_token_123") is None
    assert call_count == prev_calls


@pytest.mark.anyio
async def test_websocket_user_job_isolation_and_hub_send(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", True)

    # Fake WebSockets
    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, data):
            self.sent.append(data)

    ws_u1 = FakeWS()
    ws_u2 = FakeWS()

    hub.sockets.clear()
    hub.sockets[ws_u1] = {"session_id": "sess-u1", "user_id": 101}
    hub.sockets[ws_u2] = {"session_id": "sess-u2", "user_id": 202}

    # 1. Event targeted to user 101 must NOT reach user 202
    await hub.send({"type": "job", "job_id": "job_1"}, session_id="sess-u1", user_id=101)
    assert len(ws_u1.sent) == 1
    assert len(ws_u2.sent) == 0

    # 2. Event targeted to user 202 must NOT reach user 101
    await hub.send({"type": "job", "job_id": "job_2"}, session_id="sess-u2", user_id=202)
    assert len(ws_u1.sent) == 1
    assert len(ws_u2.sent) == 1

    # 3. Unowned event in PUBLIC_MODE must NOT be broadcast to any socket
    await hub.send({"type": "progress", "job_id": "job_orphan"}, session_id=None, user_id=None)
    assert len(ws_u1.sent) == 1
    assert len(ws_u2.sent) == 1
