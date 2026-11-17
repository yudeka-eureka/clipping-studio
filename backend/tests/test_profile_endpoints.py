import base64
import io
import time
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app, USER_TOKEN_COOKIE
from app import db, security, mediahost


@pytest.fixture(autouse=True)
def init_database():
    db.init_db()


def random_uname():
    return f"user_{uuid.uuid4().hex[:8]}"


# Minimal valid 1x1 PNG bytes
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Minimal valid JPEG bytes
TINY_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05"
    b"\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c"
    b" $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4"
    b"\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06"
    b"\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)


def register_test_user(password="secretpassword123"):
    client = TestClient(app)
    uname = random_uname()
    email = f"{uname}@example.com"
    res = client.post("/api/auth/register", json={
        "username": uname,
        "email": email,
        "password": password,
    })
    assert res.status_code == 200, res.text
    data = res.json()
    user = data["user"]
    token = data.get("token") or security.create_jwt_token({
        "user_id": user["id"],
        "sub": str(user["id"]),
        "username": user["username"],
        "email": user["email"],
    })
    return client, user, token, password


# =====================================================================
# 1. Tests for /app/profile/change-name
# =====================================================================

def test_change_name_success_and_7_day_restriction():
    client, user, token, _ = register_test_user()
    user_id = user["id"]
    new_uname = f"new_{uuid.uuid4().hex[:6]}"

    # 1. Perubahan pertama berhasil
    res = client.post("/app/profile/change-name", json={
        "userid": user_id,
        "token": token,
        "username": new_uname,
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["ok"] is True
    assert data["user"]["username"] == new_uname
    assert data["user"]["username_changed_at"] is not None

    # 2. Perubahan kedua dalam 7 hari harus DITOLAK
    second_uname = f"again_{uuid.uuid4().hex[:6]}"
    res_rejected = client.post("/app/profile/change-name", json={
        "userid": user_id,
        "token": token,
        "username": second_uname,
    })
    assert res_rejected.status_code == 400
    assert "7 hari" in res_rejected.json()["detail"]

    # 3. Verifikasi juga bekerja pada alias /api/profile/change-name
    # Simulasi memajukan waktu 8 hari di database untuk menguji izin perubahan berikutnya
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET username_changed_at = DATE_SUB(NOW(), INTERVAL 8 DAY) WHERE id = %s",
                (user_id,),
            )
    finally:
        conn.close()

    third_uname = f"third_{uuid.uuid4().hex[:6]}"
    res_after_8_days = client.post("/api/profile/change-name", json={
        "userid": user_id,
        "token": token,
        "username": third_uname,
    })
    assert res_after_8_days.status_code == 200
    assert res_after_8_days.json()["user"]["username"] == third_uname


def test_change_name_validation_rules():
    client, user, token, _ = register_test_user()
    user_id = user["id"]

    # Username sama dengan saat ini
    res = client.post("/app/profile/change-name", json={
        "userid": user_id,
        "token": token,
        "username": user["username"],
    })
    assert res.status_code == 400
    assert "sama dengan" in res.json()["detail"]

    # Username terlalu pendek (< 3 karakter)
    res = client.post("/app/profile/change-name", json={
        "userid": user_id,
        "token": token,
        "username": "ab",
    })
    assert res.status_code == 400
    assert "3–50 karakter" in res.json()["detail"]

    # Username mengandung karakter ilegal
    res = client.post("/app/profile/change-name", json={
        "userid": user_id,
        "token": token,
        "username": "user!@#$%",
    })
    assert res.status_code == 400

    # Username sudah dipakai pengguna lain
    _, other_user, _, _ = register_test_user()
    res_dup = client.post("/app/profile/change-name", json={
        "userid": user_id,
        "token": token,
        "username": other_user["username"],
    })
    assert res_dup.status_code == 400
    assert "sudah digunakan" in res_dup.json()["detail"]


def test_change_name_authorization_checks():
    client_a, user_a, token_a, _ = register_test_user()
    client_b, user_b, token_b, _ = register_test_user()

    # User B mencoba mengubah username milik User A menggunakan token B
    res = client_b.post("/app/profile/change-name", json={
        "userid": user_a["id"],
        "token": token_b,
        "username": f"hacked_{uuid.uuid4().hex[:4]}",
    })
    assert res.status_code == 403
    assert "Akses ditolak" in res.json()["detail"]

    # Token tidak valid
    res_invalid_tok = client_a.post("/app/profile/change-name", json={
        "userid": user_a["id"],
        "token": "invalid_jwt_token_123",
        "username": f"valid_{uuid.uuid4().hex[:4]}",
    })
    assert res_invalid_tok.status_code == 401

    # Token kedaluwarsa
    expired_token = security.create_jwt_token(
        {"user_id": user_a["id"], "username": user_a["username"]},
        expires_in_seconds=-100,
    )
    res_exp = client_a.post("/app/profile/change-name", json={
        "userid": user_a["id"],
        "token": expired_token,
        "username": f"valid_{uuid.uuid4().hex[:4]}",
    })
    assert res_exp.status_code == 401
    assert "kedaluwarsa" in res_exp.json()["detail"]

    # Header Authorization Bearer
    new_uname = f"bearer_{uuid.uuid4().hex[:6]}"
    res_bearer = client_a.post(
        "/app/profile/change-name",
        json={"userid": user_a["id"], "username": new_uname},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_bearer.status_code == 200
    assert res_bearer.json()["user"]["username"] == new_uname


# =====================================================================
# 2. Tests for /app/profile/change-pw
# =====================================================================

def test_change_password_success_and_login():
    old_pw = "mysecretpass123"
    client, user, token, _ = register_test_user(password=old_pw)
    user_id = user["id"]
    new_pw = "newawesomepass456"

    # Sukses ganti password dengan 3 field (old_password, new_password, confirm_password)
    res = client.post("/app/profile/change-pw", json={
        "userid": user_id,
        "token": token,
        "old_password": old_pw,
        "new_password": new_pw,
        "confirm_password": new_pw,
    })
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True

    # Login dengan password lama harus GAGAL
    res_old_login = client.post("/api/auth/login", json={
        "username_or_email": user["username"],
        "password": old_pw,
    })
    assert res_old_login.status_code == 401

    # Login dengan password baru harus BERHASIL
    res_new_login = client.post("/api/auth/login", json={
        "username_or_email": user["username"],
        "password": new_pw,
    })
    assert res_new_login.status_code == 200
    assert res_new_login.json()["ok"] is True


def test_change_password_field_aliases_matching_react():
    """React form di ChangePasswordDialog menggunakan field 'current', 'next', 'confirm'."""
    old_pw = "oldpassword123"
    client, user, token, _ = register_test_user(password=old_pw)
    new_pw = "brandnewpassword789"

    res = client.post("/app/profile/change-pw", json={
        "userid": user["id"],
        "token": token,
        "current": old_pw,
        "next": new_pw,
        "confirm": new_pw,
    })
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True


def test_change_password_validation_errors():
    old_pw = "secretpass123"
    client, user, token, _ = register_test_user(password=old_pw)
    user_id = user["id"]

    # Kata sandi lama salah
    res_wrong_old = client.post("/app/profile/change-pw", json={
        "userid": user_id,
        "token": token,
        "old_password": "wrongoldpassword",
        "new_password": "newpassword123",
        "confirm_password": "newpassword123",
    })
    assert res_wrong_old.status_code == 400
    assert "lama salah" in res_wrong_old.json()["detail"].lower()

    # Konfirmasi tidak cocok
    res_mismatch = client.post("/app/profile/change-pw", json={
        "userid": user_id,
        "token": token,
        "old_password": old_pw,
        "new_password": "newpassword123",
        "confirm_password": "differentpassword",
    })
    assert res_mismatch.status_code == 400
    assert "tidak cocok" in res_mismatch.json()["detail"].lower()

    # Password baru sama dengan password lama
    res_same = client.post("/app/profile/change-pw", json={
        "userid": user_id,
        "token": token,
        "old_password": old_pw,
        "new_password": old_pw,
        "confirm_password": old_pw,
    })
    assert res_same.status_code == 400
    assert "tidak boleh sama" in res_same.json()["detail"].lower()

    # Password baru terlalu pendek
    res_short = client.post("/app/profile/change-pw", json={
        "userid": user_id,
        "token": token,
        "old_password": old_pw,
        "new_password": "123",
        "confirm_password": "123",
    })
    assert res_short.status_code == 400
    assert "minimal 6" in res_short.json()["detail"].lower()


# =====================================================================
# 3. Tests for /app/profile/change-photo
# =====================================================================

def test_change_photo_multipart_upload_mocked_cloudinary(monkeypatch):
    client, user, token, _ = register_test_user()
    user_id = user["id"]
    fake_cloudinary_url = f"https://res.cloudinary.com/demo/image/upload/v1234567/profile_user_{user_id}.png"

    # Mock mediahost.upload_profile_image_to_cloudinary
    def mock_upload(content, filename="avatar.jpg", mime_type="image/jpeg", user_id="user", creds=None):
        assert len(content) == len(TINY_PNG)
        assert mime_type == "image/png"
        return fake_cloudinary_url

    monkeypatch.setattr(mediahost, "upload_profile_image_to_cloudinary", mock_upload)

    # 1. Kirim multipart/form-data
    files = {"photo": ("my_avatar.png", io.BytesIO(TINY_PNG), "image/png")}
    data = {"userid": str(user_id), "token": token}
    res = client.post("/app/profile/change-photo", data=data, files=files)

    assert res.status_code == 200, res.text
    res_json = res.json()
    assert res_json["ok"] is True
    assert res_json["photo_url"] == fake_cloudinary_url
    assert res_json["user"]["profile_photo"] == fake_cloudinary_url

    # 2. Cek apakah database benar-benar terupdate
    user_in_db = db.get_user_by_id(user_id)
    assert user_in_db["profile_photo"] == fake_cloudinary_url


def test_change_photo_json_base64_upload_mocked_cloudinary(monkeypatch):
    client, user, token, _ = register_test_user()
    user_id = user["id"]
    fake_cloudinary_url = f"https://res.cloudinary.com/demo/image/upload/v1234567/profile_user_{user_id}.jpg"

    def mock_upload(content, filename="avatar.jpg", mime_type="image/jpeg", user_id="user", creds=None):
        assert len(content) == len(TINY_JPEG)
        assert mime_type == "image/jpeg"
        return fake_cloudinary_url

    monkeypatch.setattr(mediahost, "upload_profile_image_to_cloudinary", mock_upload)

    b64_str = f"data:image/jpeg;base64,{base64.b64encode(TINY_JPEG).decode('ascii')}"
    res = client.post("/api/profile/change-photo", json={
        "userid": user_id,
        "token": token,
        "photo": b64_str,
    })
    assert res.status_code == 200, res.text
    assert res.json()["photo_url"] == fake_cloudinary_url


def test_change_photo_rejects_invalid_images():
    client, user, token, _ = register_test_user()
    user_id = user["id"]

    # File bukan gambar (plain text)
    files = {"photo": ("fake.txt", io.BytesIO(b"Hello world this is not an image"), "text/plain")}
    res = client.post("/app/profile/change-photo", data={"userid": str(user_id), "token": token}, files=files)
    assert res.status_code == 400
    assert "gambar valid" in res.json()["detail"].lower()

    # Berkas kosong
    files_empty = {"photo": ("empty.png", io.BytesIO(b""), "image/png")}
    res_empty = client.post("/app/profile/change-photo", data={"userid": str(user_id), "token": token}, files=files_empty)
    assert res_empty.status_code == 400


def test_change_photo_rejects_unauthorized_user():
    client_a, user_a, token_a, _ = register_test_user()
    client_b, user_b, token_b, _ = register_test_user()

    files = {"photo": ("avatar.png", io.BytesIO(TINY_PNG), "image/png")}
    # Token B mencoba mengubah foto User A
    res = client_b.post(
        "/app/profile/change-photo",
        data={"userid": str(user_a["id"]), "token": token_b},
        files=files,
    )
    assert res.status_code == 403


# =====================================================================
# 4. CORS verification for React frontend
# =====================================================================

def test_cors_preflight_for_react_frontend():
    client = TestClient(app)
    res = client.options(
        "/app/profile/change-name",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_endpoints_work_without_sending_userid(monkeypatch):
    """Memastikan ketiga endpoint profil berfungsi penuh tanpa mengirimkan userid."""
    old_pw = "pass123456"
    client, user, token, _ = register_test_user(password=old_pw)
    user_id = user["id"]

    # 1. /app/profile/change-name tanpa userid (hanya token di header Bearer)
    new_uname = f"nouid_{uuid.uuid4().hex[:6]}"
    res_name = client.post(
        "/app/profile/change-name",
        json={"username": new_uname},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_name.status_code == 200, res_name.text
    assert res_name.json()["user"]["username"] == new_uname

    # 2. /app/profile/change-pw tanpa userid (token di body json)
    new_pw = "newpasswithoutuid789"
    res_pw = client.post(
        "/app/profile/change-pw",
        json={
            "token": token,
            "old_password": old_pw,
            "new_password": new_pw,
            "confirm_password": new_pw,
        },
    )
    assert res_pw.status_code == 200, res_pw.text
    assert res_pw.json()["ok"] is True

    # 3. /app/profile/change-photo tanpa userid (hanya file & Bearer token)
    fake_url = f"https://res.cloudinary.com/demo/image/upload/v999/user_{user_id}.png"
    monkeypatch.setattr(mediahost, "upload_profile_image_to_cloudinary", lambda *args, **kwargs: fake_url)

    files = {"photo": ("avatar.png", io.BytesIO(TINY_PNG), "image/png")}
    res_photo = client.post(
        "/app/profile/change-photo",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert res_photo.status_code == 200, res_photo.text
    assert res_photo.json()["photo_url"] == fake_url
    assert db.get_user_by_id(user_id)["profile_photo"] == fake_url

