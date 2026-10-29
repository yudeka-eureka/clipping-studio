from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest

from app.main import (
    app,
    AI_CREDS_COOKIE,
    MEDIA_CREDS_COOKIE,
    USER_TOKEN_COOKIE,
    SESSION_COOKIE,
    _request_ai_context,
)
from app import db, security, gemini, main


@pytest.fixture(autouse=True)
def init_database():
    db.init_db()


def test_cookie_encryption_and_tamper_proofing():
    data = {"provider": "gemini", "key": "AIzaSySecretKey", "model": "gemini-3.8-flash"}
    encrypted = security.encrypt_cookie_data(data)
    assert encrypted.startswith(security.COOKIE_ENCRYPTION_PREFIX)
    assert "AIzaSySecretKey" not in encrypted

    # Successful decryption
    decrypted = security.decrypt_cookie_data(encrypted)
    assert decrypted == data

    # Tampered ciphertext fails safely and returns None
    tampered = encrypted[:-5] + "XXXXX"
    assert security.decrypt_cookie_data(tampered) is None


def test_auth_token_cookie_is_encrypted_and_httponly():
    client = TestClient(app)
    uname = f"sec_user_{security.secrets.token_hex(4)}"
    res = client.post(
        "/api/auth/register",
        json={"username": uname, "email": f"{uname}@example.com", "password": "securepassword123"},
    )
    assert res.status_code == 200

    # Pastikan cookie diset dan nilainya terenkripsi AES-256 (bukan plaintext)
    raw_cookie = res.cookies.get(USER_TOKEN_COOKIE)
    assert raw_cookie is not None
    clean_cookie = raw_cookie.strip('"').strip("'")
    assert clean_cookie.startswith(security.COOKIE_ENCRYPTION_PREFIX)
    assert not clean_cookie.startswith("cs_live_")

    # Pastikan client terautentikasi otomatis via cookie terenkripsi
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["user"]["username"] == uname

    # Pastikan logout menghapus cookie
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    me_after_logout = client.get("/api/auth/me")
    assert me_after_logout.json()["user"] is None


def test_ai_credentials_cookie_workflow():
    client = TestClient(app)

    # 1. Simpan kredensial AI via API
    res = client.post(
        "/api/credentials/ai",
        json={"provider": "gemini", "key": "AIzaSyTest1234567890", "model": "gemini-3.8-flash"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["providers"]["gemini"]["has_key"] is True
    assert data["providers"]["gemini"]["key_hint"] == "…7890"

    # Pastikan cookie terpasang dan terenkripsi
    raw_cookie = res.cookies.get(AI_CREDS_COOKIE)
    assert raw_cookie is not None
    assert raw_cookie.strip('"').strip("'").startswith(security.COOKIE_ENCRYPTION_PREFIX)
    assert "AIzaSyTest" not in raw_cookie

    # 2. Ambil metadata via GET /api/credentials/ai -> tidak pernah membocorkan plain key
    get_res = client.get("/api/credentials/ai")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["providers"]["gemini"]["has_key"] is True
    assert "AIzaSyTest1234567890" not in str(get_data)

    # 3. Model query via cookie tanpa header X-AI-Key
    fake_client = MagicMock()
    fake_model = MagicMock()
    fake_model.name = "models/gemini-3.8-flash"
    fake_model.supported_actions = ["generateContent"]
    fake_client.models.list.return_value = [fake_model]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(gemini, "client", lambda key: fake_client)
        mp.setattr(gemini, "_is_model_available", lambda c, m: True)
        models_res = client.get("/api/models?provider=gemini")
        assert models_res.status_code == 200
        assert "gemini-3.8-flash" in models_res.json()["models"]

    # 4. Hapus kredensial AI
    del_res = client.delete("/api/credentials/ai")
    assert del_res.status_code == 200


def test_media_credentials_cookie_workflow():
    client = TestClient(app)

    # 1. Simpan kredensial Cloudinary via API
    res = client.post(
        "/api/credentials/media",
        json={
            "host": "cloudinary",
            "credentials": {
                "cloud_name": "mytestcloud",
                "api_key": "123456789",
                "api_secret": "SuperSecretSecretKey",
            },
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["configured"]["cloudinary"] is True
    assert data["fields"]["cloudinary"]["has_secret"] is True
    assert "SuperSecretSecretKey" not in str(data)

    # Pastikan cookie terenkripsi
    raw_cookie = res.cookies.get(MEDIA_CREDS_COOKIE)
    assert raw_cookie is not None
    assert raw_cookie.strip('"').strip("'").startswith(security.COOKIE_ENCRYPTION_PREFIX)
    assert "SuperSecretSecretKey" not in raw_cookie

    # 2. GET /api/credentials/media tidak membocorkan secret
    get_res = client.get("/api/credentials/media")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["fields"]["cloudinary"]["cloud_name"] == "mytestcloud"
    assert get_data["fields"]["cloudinary"]["has_secret"] is True
    assert "SuperSecretSecretKey" not in str(get_data)

    # 3. Hapus kredensial media
    del_res = client.delete("/api/credentials/media")
    assert del_res.status_code == 200


def test_cookie_secure_logic(monkeypatch):
    from fastapi import Request

    # Local development on HTTP -> secure=False
    scope_http_local = {
        "type": "http",
        "scheme": "http",
        "path": "/",
        "headers": [(b"host", b"localhost:8765")],
    }
    req_local = Request(scope_http_local)
    assert security.is_cookie_secure(req_local) is False

    # Production on HTTPS -> secure=True
    scope_https = {
        "type": "http",
        "scheme": "https",
        "path": "/",
        "headers": [(b"host", b"clip.example.com")],
    }
    req_https = Request(scope_https)
    assert security.is_cookie_secure(req_https) is True

    # Reverse proxy with X-Forwarded-Proto: https -> secure=True
    scope_proxy = {
        "type": "http",
        "scheme": "http",
        "path": "/",
        "headers": [(b"host", b"clip.example.com"), (b"x-forwarded-proto", b"https")],
    }
    req_proxy = Request(scope_proxy)
    assert security.is_cookie_secure(req_proxy) is True

    # Explicit COOKIE_SECURE env override
    monkeypatch.setenv("COOKIE_SECURE", "true")
    assert security.is_cookie_secure(req_local) is True
    monkeypatch.setenv("COOKIE_SECURE", "false")
    assert security.is_cookie_secure(req_https) is False

    # Plain HTTP from 0.0.0.0 or LAN IP should not set Secure flag
    scope_http_ip = {
        "type": "http",
        "scheme": "http",
        "path": "/",
        "headers": [(b"host", b"0.0.0.0:8765")],
    }
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.setattr(main, "PUBLIC_MODE", True)
    req_ip = Request(scope_http_ip)
    assert security.is_cookie_secure(req_ip) is False


def test_api_config_reflects_user_ai_cookie_in_public_mode(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", True)
    client = TestClient(app)

    # Initially in PUBLIC_MODE without cookie, has_key is False
    res_init = client.get("/api/config")
    assert res_init.status_code == 200
    assert res_init.json()["has_key"] is False

    # Save AI credentials via BYOK
    post_res = client.post(
        "/api/credentials/ai",
        json={"provider": "gemini", "key": "AIzaSyUserKey123", "model": "gemini-3.7-flash"},
    )
    assert post_res.status_code == 200

    # /api/config should now read the cookie and reflect has_key=True and the model
    res_after = client.get("/api/config")
    assert res_after.status_code == 200
    data = res_after.json()
    assert data["has_key"] is True
    assert data["provider"] == "gemini"
    assert data["model"] == "gemini-3.7-flash"
    assert data["providers"]["gemini"]["has_key"] is True
    assert data["providers"]["gemini"]["model"] == "gemini-3.7-flash"


def test_job_creation_reads_user_ai_model_and_key_from_cookie(tmp_path, monkeypatch):
    from unittest.mock import patch
    import io
    store = main.store

    monkeypatch.setattr(main, "PUBLIC_MODE", True)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "jobs")
    (tmp_path / "jobs").mkdir(parents=True, exist_ok=True)

    client = TestClient(app)

    # 1. User sets AI key and custom model in cookie
    client.post(
        "/api/credentials/ai",
        json={"provider": "gemini", "key": "AIzaSyUserSecretKey99", "model": "gemini-3.8-flash"},
    )

    # 2. User creates a video clipping job without passing X-AI-Key header
    with patch("app.pipeline.run", return_value=None):
        valid_video_data = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 4096
        fake_file = io.BytesIO(valid_video_data)
        res = client.post(
            "/api/jobs",
            files={"file": ("test_clip_video.mp4", fake_file, "video/mp4")},
        )
        assert res.status_code == 200
        job_id = res.json()["id"]

        # 3. Verify internal job has _ai_context with the user's key and model
        internal_job = store.jobs.get(job_id)
        assert internal_job is not None
        assert internal_job.get("_ai_context") == {
            "provider": "gemini",
            "key": "AIzaSyUserSecretKey99",
            "model": "gemini-3.8-flash",
        }

