import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app, USER_TOKEN_COOKIE, AI_CREDS_COOKIE, MEDIA_CREDS_COOKIE
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
    assert user["credential_token"].startswith("cs_live_")
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
    assert new_token != old_token
    assert new_token.startswith("cs_live_")

    # Set custom token
    custom = f"my_custom_token_{uuid.uuid4().hex[:10]}"
    res_custom = client.patch("/api/auth/token", json={"token": custom})
    assert res_custom.status_code == 200
    assert res_custom.json()["credential_token"] == custom

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


def test_token_is_encrypted_with_aes256_in_database():
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

    # Langsung query database MySQL untuk memeriksa isi kolom mentah
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT credential_token FROM users WHERE username = %s LIMIT 1", (uname,))
            row = cur.fetchone()
            assert row is not None
            raw_db_token = row["credential_token"]

            # Token mentah di database HARUS terenkripsi AES-256 dan TIDAK sama dengan plaintext
            assert raw_db_token != plain_token
            assert raw_db_token.startswith(db.TOKEN_ENCRYPTION_PREFIX)
            assert plain_token not in raw_db_token

            # Fungsi dekripsi harus mengembalikan token asli
            decrypted = db.decrypt_token(raw_db_token)
            assert decrypted == plain_token
    finally:
        conn.close()


def test_unauthenticated_app_access_redirects_to_login():
    """Pastikan akses ke /app atau /index.html oleh guest dialihkan (redirect 303) ke /login."""
    guest_client = TestClient(app)

    # 1. Guest akses /app -> redirect 303 ke /login
    res_app = guest_client.get("/app", follow_redirects=False)
    assert res_app.status_code == 303
    assert res_app.headers["location"] == "/login"

    # 2. Guest akses /index.html -> redirect 303 ke /login
    res_index = guest_client.get("/index.html", follow_redirects=False)
    assert res_index.status_code == 303
    assert res_index.headers["location"] == "/login"

    # 3. Guest akses /login dan /register -> 200 OK (halaman form auth)
    res_login = guest_client.get("/login", follow_redirects=False)
    assert res_login.status_code == 200
    res_reg = guest_client.get("/register", follow_redirects=False)
    assert res_reg.status_code == 200

    # 4. User terautentikasi akses /app -> 200 OK
    auth_client = TestClient(app)
    uname = random_uname()
    auth_client.post("/api/auth/register", json={
        "username": uname,
        "email": f"{uname}@example.com",
        "password": "valid_password_123",
    })
    res_auth_app = auth_client.get("/app", follow_redirects=False)
    assert res_auth_app.status_code == 200

    # 5. User terautentikasi akses /login atau /register -> redirect 303 ke /app
    res_auth_login = auth_client.get("/login", follow_redirects=False)
    assert res_auth_login.status_code == 303
    assert res_auth_login.headers["location"] == "/app"

    res_auth_reg = auth_client.get("/register", follow_redirects=False)
    assert res_auth_reg.status_code == 303
    assert res_auth_reg.headers["location"] == "/app"


def test_ai_credentials_tied_to_user_account_in_database():
    """Pastikan model API key (AI credentials) terikat ke akun pengguna di tabel model_keys dan terenkripsi AES-256."""
    client = TestClient(app)
    uname = random_uname()
    reg_res = client.post("/api/auth/register", json={
        "username": uname,
        "email": f"{uname}@example.com",
        "password": "secure_password_123",
    })
    user_id = reg_res.json()["user"]["id"]

    # Simpan API key AI via BYOK
    secret_key = "AIzaSyTestUserKey_999888777"
    save_res = client.post("/api/credentials/ai", json={
        "provider": "gemini",
        "key": secret_key,
        "model": "gemini-3.8-flash",
    })
    assert save_res.status_code == 200

    # 1. Cek langsung ke database MySQL: harus tersimpan di tabel model_keys
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT `key`, model, is_active FROM model_keys WHERE user_id = %s AND type = 'ai' AND provider = 'gemini' LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
            assert row is not None
            raw_ai_key = row["key"]

            # Nilai di database HARUS terenkripsi dan tidak membocorkan plaintext key
            assert raw_ai_key.startswith(db.TOKEN_ENCRYPTION_PREFIX)
            assert secret_key not in raw_ai_key
            assert row["model"] == "gemini-3.8-flash"
            assert bool(row["is_active"]) is True
    finally:
        conn.close()

    # 2. Fungsi database db.get_user_ai_credentials harus mengembalikan data yang benar
    db_creds = db.get_user_ai_credentials(user_id)
    assert db_creds is not None
    assert db_creds["provider"] == "gemini"
    assert db_creds["providers"]["gemini"]["key"] == secret_key
    assert db_creds["providers"]["gemini"]["model"] == "gemini-3.8-flash"

    # 3. Pengguna login dari client baru (tanpa cookie lama): kredensial AI otomatis dipulihkan dari DB
    new_client = TestClient(app)
    login_res = new_client.post("/api/auth/login", json={
        "username_or_email": uname,
        "password": "secure_password_123",
    })
    assert login_res.status_code == 200

    # Endpoint GET /api/credentials/ai pada client baru dapat membaca kredensial akun
    get_res = new_client.get("/api/credentials/ai")
    assert get_res.status_code == 200
    ai_data = get_res.json()
    assert ai_data["providers"]["gemini"]["has_key"] is True
    assert ai_data["providers"]["gemini"]["model"] == "gemini-3.8-flash"


def test_media_cloud_credentials_tied_to_user_account_in_database():
    """Pastikan cloud key-secret (Cloudinary / R2) terikat langsung ke akun pengguna di tabel model_keys dan terenkripsi AES-256."""
    client = TestClient(app)
    uname = random_uname()
    reg_res = client.post("/api/auth/register", json={
        "username": uname,
        "email": f"{uname}@example.com",
        "password": "secure_password_123",
    })
    user_id = reg_res.json()["user"]["id"]

    # Simpan Cloudinary media credentials
    secret_api_key = "cloud_api_key_12345"
    secret_api_secret = "CloudinarySuperSecretKey_XYZ"
    save_res = client.post("/api/credentials/media", json={
        "host": "cloudinary",
        "credentials": {
            "cloud_name": "production_cloud",
            "api_key": secret_api_key,
            "api_secret": secret_api_secret,
        },
    })
    assert save_res.status_code == 200

    # 1. Cek langsung ke database MySQL: harus tersimpan di tabel model_keys
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT `key`, secret_key, r2_account_id, cloud_name FROM model_keys WHERE user_id = %s AND type = 'media' AND provider = 'cloudinary' LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
            assert row is not None

            # Nilai di database HARUS terenkripsi dan tidak membocorkan plaintext key/secret
            assert row["key"].startswith(db.TOKEN_ENCRYPTION_PREFIX)
            assert row["secret_key"].startswith(db.TOKEN_ENCRYPTION_PREFIX)
            assert secret_api_secret not in row["secret_key"]
            assert secret_api_key not in row["key"]
    finally:
        conn.close()

    # 2. Fungsi database db.get_user_media_credentials harus mengembalikan data yang benar
    db_media = db.get_user_media_credentials(user_id)
    assert db_media is not None
    assert db_media["host"] == "cloudinary"
    assert db_media["cloudinary"]["api_secret"] == secret_api_secret

    # 3. Login dari client baru: kredensial cloud otomatis disinkronkan ke sesi user
    new_client = TestClient(app)
    new_client.post("/api/auth/login", json={
        "username_or_email": uname,
        "password": "secure_password_123",
    })
    get_res = new_client.get("/api/credentials/media")
    assert get_res.status_code == 200
    media_data = get_res.json()
    assert media_data["configured"]["cloudinary"] is True
    assert media_data["fields"]["cloudinary"]["cloud_name"] == "production_cloud"
    assert media_data["fields"]["cloudinary"]["has_secret"] is True


def test_user_can_set_multiple_ai_keys_and_both_media_hosts_in_model_keys():
    """Pastikan satu user bisa menyimpan key dari berbagai AI sekaligus dan kedua cloud media hosting di model_keys."""
    client = TestClient(app)
    uname = random_uname()
    reg_res = client.post("/api/auth/register", json={
        "username": uname,
        "email": f"{uname}@example.com",
        "password": "secure_password_123",
    })
    user_id = reg_res.json()["user"]["id"]

    # 1. User set key Gemini
    client.post("/api/credentials/ai", json={
        "provider": "gemini",
        "key": "AIzaSyGemini_Key111",
        "model": "gemini-3.7-flash",
    })

    # 2. User set key Claude (anthropic)
    client.post("/api/credentials/ai", json={
        "provider": "anthropic",
        "key": "sk-ant-Claude_Key222",
        "model": "claude-3-7-sonnet-latest",
    })

    # 3. User set key ChatGPT (openai)
    client.post("/api/credentials/ai", json={
        "provider": "openai",
        "key": "sk-OpenAI_Key333",
        "model": "gpt-4o",
    })

    # 4. User set Cloudinary
    client.post("/api/credentials/media", json={
        "host": "cloudinary",
        "credentials": {
            "cloud_name": "my_cloud",
            "api_key": "c_key_111",
            "api_secret": "c_sec_222",
        },
    })

    # 5. User set Cloudflare R2
    client.post("/api/credentials/media", json={
        "host": "r2",
        "credentials": {
            "account_id": "r2_acc_12345",
            "access_key_id": "r2_access_key_abc",
            "secret_access_key": "r2_secret_key_xyz",
            "bucket": "my-video-bucket",
            "public_url": "https://pub.example.com",
        },
    })

    # Verifikasi langsung ke database MySQL pada tabel model_keys
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            # Harus ada 3 row AI
            cur.execute("SELECT provider, `key`, secret_key, r2_account_id, is_active FROM model_keys WHERE user_id = %s AND type = 'ai'", (user_id,))
            ai_rows = {r["provider"]: r for r in cur.fetchall()}
            assert len(ai_rows) == 3
            assert "gemini" in ai_rows
            assert "anthropic" in ai_rows
            assert "openai" in ai_rows

            # Semua key sensitif AI terenkripsi
            for prov, r in ai_rows.items():
                assert r["key"].startswith(db.TOKEN_ENCRYPTION_PREFIX)
                assert "AIzaSy" not in r["key"]
                assert "sk-ant" not in r["key"]
                assert "sk-OpenAI" not in r["key"]

            # Provider aktif terakhir adalah openai
            assert bool(ai_rows["openai"]["is_active"]) is True
            assert bool(ai_rows["gemini"]["is_active"]) is False

            # Harus ada 2 row media (Cloudinary dan R2)
            cur.execute("SELECT provider, `key`, secret_key, r2_account_id, r2_bucket, r2_bucket_url, is_active FROM model_keys WHERE user_id = %s AND type = 'media'", (user_id,))
            media_rows = {r["provider"]: r for r in cur.fetchall()}
            assert len(media_rows) == 2
            assert "cloudinary" in media_rows
            assert "r2" in media_rows

            # Kredensial sensitif R2 (key, secret_key, r2_account_id) wajib terenkripsi
            r2_row = media_rows["r2"]
            assert r2_row["key"].startswith(db.TOKEN_ENCRYPTION_PREFIX)
            assert r2_row["secret_key"].startswith(db.TOKEN_ENCRYPTION_PREFIX)
            assert r2_row["r2_account_id"].startswith(db.TOKEN_ENCRYPTION_PREFIX)
            assert "r2_access_key_abc" not in r2_row["key"]
            assert "r2_secret_key_xyz" not in r2_row["secret_key"]
            assert "r2_acc_12345" not in r2_row["r2_account_id"]
            assert r2_row["r2_bucket"] == "my-video-bucket"

            # Host aktif terakhir adalah R2
            assert bool(r2_row["is_active"]) is True
            assert bool(media_rows["cloudinary"]["is_active"]) is False
    finally:
        conn.close()

    # Verifikasi pembacaan dari API: semua 3 provider AI dan kedua media host terbaca
    ai_status = client.get("/api/credentials/ai").json()
    assert ai_status["providers"]["gemini"]["has_key"] is True
    assert ai_status["providers"]["anthropic"]["has_key"] is True
    assert ai_status["providers"]["openai"]["has_key"] is True

    media_status = client.get("/api/credentials/media").json()
    assert media_status["configured"]["cloudinary"] is True
    assert media_status["configured"]["r2"] is True
    assert media_status["host"] == "r2"


def test_user_credential_isolation():
    """Pastikan isolasi kredensial: User A dan User B memiliki kunci AI & cloud terpisah dan tidak saling mengganggu."""
    # User A
    client_a = TestClient(app)
    uname_a = random_uname()
    res_a = client_a.post("/api/auth/register", json={
        "username": uname_a,
        "email": f"{uname_a}@example.com",
        "password": "password_a_123",
    })
    user_a_id = res_a.json()["user"]["id"]

    # User B
    client_b = TestClient(app)
    uname_b = random_uname()
    res_b = client_b.post("/api/auth/register", json={
        "username": uname_b,
        "email": f"{uname_b}@example.com",
        "password": "password_b_123",
    })
    user_b_id = res_b.json()["user"]["id"]

    # User A menyimpan Gemini key
    client_a.post("/api/credentials/ai", json={
        "provider": "gemini",
        "key": "AIzaSyKeyForUserA",
        "model": "gemini-3.7-flash",
    })

    # User B menyimpan Claude key
    client_b.post("/api/credentials/ai", json={
        "provider": "anthropic",
        "key": "sk-ant-KeyForUserB",
        "model": "claude-3-7-sonnet-latest",
    })

    # Verifikasi isolasi di database MySQL
    creds_a = db.get_user_ai_credentials(user_a_id)
    creds_b = db.get_user_ai_credentials(user_b_id)

    assert "gemini" in creds_a["providers"]
    assert "anthropic" not in creds_a.get("providers", {})
    assert creds_a["providers"]["gemini"]["key"] == "AIzaSyKeyForUserA"

    assert "anthropic" in creds_b["providers"]
    assert "gemini" not in creds_b.get("providers", {})
    assert creds_b["providers"]["anthropic"]["key"] == "sk-ant-KeyForUserB"

    # Verifikasi isolasi via API
    api_a = client_a.get("/api/credentials/ai").json()
    assert api_a["providers"]["gemini"]["has_key"] is True
    assert api_a["providers"]["anthropic"]["has_key"] is False

    api_b = client_b.get("/api/credentials/ai").json()
    assert api_b["providers"]["gemini"]["has_key"] is False
    assert api_b["providers"]["anthropic"]["has_key"] is True

    # User A menghapus kredensial AI miliknya -> Kredensial User B tidak boleh terpengaruh
    client_a.delete("/api/credentials/ai")
    assert db.get_user_ai_credentials(user_a_id) in (None, {})
    assert db.get_user_ai_credentials(user_b_id)["providers"]["anthropic"]["key"] == "sk-ant-KeyForUserB"

