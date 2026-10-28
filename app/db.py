"""Manajemen database pengguna dan token kredensial via Supabase (PostgREST HTTP API).

Didesain untuk serverless / Vercel dan lingkungan terdistribusi:
- Komunikasi stateless menggunakan HTTP PostgREST
- Menggunakan SUPABASE_SECRET untuk bypass RLS pada operasi backend
- Token kredensial disimpan terenkripsi dengan AES-256-GCM
- Password di-hash menggunakan PBKDF2-HMAC-SHA256 (100.000 iterasi) dengan constant-time verification
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from typing import Any
from dotenv import load_dotenv
import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

load_dotenv()

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")
TOKEN_ENCRYPTION_PREFIX = "enc_aes256$"


# ==============================================================================
# Keamanan & Enkripsi Token / Password
# ==============================================================================

def get_token_encryption_key() -> bytes:
    """Ambil atau derivasi kunci master AES-256 (32 bytes = 256 bits)."""
    raw_key = os.getenv("SECRET_KEY") or os.getenv("TOKEN_ENCRYPTION_KEY") or "clipping-studio-master-secret-key-32b"
    key_bytes = raw_key.encode("utf-8")
    if len(key_bytes) in (16, 24, 32):
        return key_bytes
    return hashlib.sha256(key_bytes).digest()


def encrypt_token(plain_token: str) -> str:
    """Enkripsi token kredensial menggunakan AES-256-GCM.

    Menggunakan derivasi deterministik untuk nonce (via HMAC-SHA256) agar
    pencarian query token di database tetap O(1) dan terindeks unik.
    """
    if not plain_token:
        return plain_token
    if plain_token.startswith(TOKEN_ENCRYPTION_PREFIX):
        return plain_token

    key = get_token_encryption_key()
    token_bytes = plain_token.encode("utf-8")
    nonce = hmac.new(key, b"token_nonce:" + token_bytes, hashlib.sha256).digest()[:12]
    aesgcm = AESGCM(key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, token_bytes, None)
    encoded = base64.urlsafe_b64encode(nonce + ciphertext_and_tag).decode("ascii")
    return f"{TOKEN_ENCRYPTION_PREFIX}{encoded}"


def decrypt_token(stored_token: str | None) -> str:
    """Dekripsi token kredensial terenkripsi AES-256-GCM kembali ke plain text.

    Mendukung backward-compatibility jika ada record token legacy yang belum terenkripsi.
    """
    if not stored_token:
        return ""
    if not stored_token.startswith(TOKEN_ENCRYPTION_PREFIX):
        return stored_token

    try:
        encoded = stored_token[len(TOKEN_ENCRYPTION_PREFIX):]
        raw_bytes = base64.urlsafe_b64decode(encoded.encode("ascii"))
        nonce = raw_bytes[:12]
        ciphertext_and_tag = raw_bytes[12:]
        key = get_token_encryption_key()
        aesgcm = AESGCM(key)
        plain_bytes = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
        return plain_bytes.decode("utf-8")
    except Exception:
        return ""


def hash_password(password: str) -> str:
    """Hash password menggunakan PBKDF2-HMAC-SHA256 dengan salt acak 16-byte."""
    salt = secrets.token_hex(16)
    iterations = 100000
    hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${hash_bytes.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifikasi password terhadap stored hash dengan aman (constant-time)."""
    try:
        parts = stored_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_hex = parts[3]
        calculated_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return hmac.compare_digest(calculated_bytes.hex(), expected_hex)
    except Exception:
        return False


def generate_credential_token() -> str:
    """Generate secure token kredensial untuk user."""
    return f"cs_live_{secrets.token_urlsafe(28)}"


def _format_user(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    user = dict(row)
    # Jangan pernah kembalikan password di objek user
    user.pop("password", None)
    user.pop("password_hash", None)

    # Dukung field credential_token baru serta alias token_credential untuk backward compatibility
    tok = user.get("credential_token") or user.get("token_credential")
    if tok:
        dec = decrypt_token(tok)
        user["credential_token"] = dec
        user["token_credential"] = dec

    for ts_col in ("created_at", "updated_at"):
        if ts_col in user and user[ts_col] is not None:
            if hasattr(user[ts_col], "isoformat"):
                user[ts_col] = user[ts_col].isoformat()
            else:
                user[ts_col] = str(user[ts_col])
    return user


# Cache in-memory untuk meminimalkan beban request ke Supabase PostgREST
_USER_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}
_CACHE_TTL_POSITIVE = 30.0  # 30 detik untuk user valid
_CACHE_TTL_NEGATIVE = 5.0   # 5 detik untuk token tidak valid


def invalidate_user_cache(token: str | None = None) -> None:
    """Invalidasi cache user di memori."""
    if token:
        _USER_CACHE.pop(token, None)
    else:
        _USER_CACHE.clear()


# ==============================================================================
# Supabase HTTP PostgREST Client
# ==============================================================================

def get_supabase_config() -> dict[str, str]:
    """Ambil konfigurasi URL dan Secret Key Supabase.

    Menggunakan SUPABASE_SECRET untuk serverless backend agar melewati
    Row Level Security (RLS) secara aman dan mencegah pembatasan anon key.
    """
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_SECRET") or "").strip()

    # Peringatan jika anon key terdeteksi tanpa secret key
    anon_key = (os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not key and anon_key:
        print("⚠️ [Supabase Config] SUPABASE_ANON_KEY terdeteksi, namun backend serverless memerlukan SUPABASE_SECRET untuk melewati RLS secara aman.")

    return {"url": url, "key": key}


def _supabase_headers(config: dict[str, str] | None = None) -> dict[str, str]:
    cfg = config or get_supabase_config()
    key = cfg["key"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _supabase_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> httpx.Response:
    cfg = get_supabase_config()
    if not cfg["url"] or not cfg["key"]:
        raise ValueError(
            "SUPABASE_URL dan SUPABASE_SECRET harus disetel di .env."
        )

    req_headers = _supabase_headers(cfg)
    if headers:
        req_headers.update(headers)

    url = f"{cfg['url']}{path}"
    with httpx.Client(timeout=timeout) as client:
        return client.request(method, url, params=params, json=json, headers=req_headers)


def init_db() -> None:
    """Verifikasi koneksi ke tabel users di Supabase."""
    cfg = get_supabase_config()
    if not cfg["url"] or not cfg["key"]:
        print("⚠️ [Supabase Init] SUPABASE_URL atau key (SUPABASE_SECRET) belum disetel.")
        return
    try:
        r = _supabase_request("GET", "/rest/v1/users", params={"select": "id", "limit": 1})
        if r.is_success:
            print("✓ [Supabase Init] Tabel users siap terhubung.")
        elif r.status_code in (401, 403):
            err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if err.get("code") == "42501":
                print("⚠️ [Supabase Init] Tabel users ditemukan namun RLS aktif. Pastikan SUPABASE_SECRET disetel dengan benar.")
            else:
                print(f"⚠️ [Supabase Init] Peringatan autentikasi Supabase ({r.status_code}): {r.text}")
        else:
            print(f"⚠️ [Supabase Init] Status endpoint Supabase: {r.status_code}")
    except Exception as e:
        print(f"⚠️ [Supabase Init] Peringatan koneksi database: {e}")


def register_user(username: str, email: str, password: str) -> dict[str, Any]:
    uname = (username or "").strip()
    mail = (email or "").strip().lower()
    pwd = password or ""

    if not USERNAME_REGEX.match(uname):
        raise ValueError("Username harus terdiri dari 3–50 karakter alfanumerik (huruf, angka, _, -).")
    if not EMAIL_REGEX.match(mail) or len(mail) > 100:
        raise ValueError("Alamat email tidak valid.")
    if len(pwd) < 6:
        raise ValueError("Kata sandi minimal 6 karakter.")
    if len(pwd) > 128:
        raise ValueError("Kata sandi maksimal 128 karakter.")

    # Cek username
    r_u = _supabase_request(
        "GET",
        "/rest/v1/users",
        params={"select": "id", "username": f"eq.{uname}", "limit": 1},
    )
    if r_u.is_success and r_u.json():
        raise ValueError(f"Username '{uname}' sudah digunakan. Silakan pilih username lain.")

    # Cek email
    r_e = _supabase_request(
        "GET",
        "/rest/v1/users",
        params={"select": "id", "email": f"eq.{mail}", "limit": 1},
    )
    if r_e.is_success and r_e.json():
        raise ValueError(f"Alamat email '{mail}' sudah terdaftar.")

    pwd_hash = hash_password(pwd)
    plain_token = generate_credential_token()
    enc_token = encrypt_token(plain_token)

    payload = {
        "username": uname,
        "email": mail,
        "password": pwd_hash,
        "credential_token": enc_token,
    }
    r = _supabase_request(
        "POST",
        "/rest/v1/users",
        json=payload,
        headers={"Prefer": "return=representation"},
    )
    if r.status_code == 409:
        err_msg = r.text
        if "username" in err_msg.lower():
            raise ValueError(f"Username '{uname}' sudah digunakan. Silakan pilih username lain.")
        if "email" in err_msg.lower():
            raise ValueError(f"Alamat email '{mail}' sudah terdaftar.")
        raise ValueError(f"Data user sudah terdaftar: {err_msg}")

    if r.status_code in (401, 403):
        err_body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if err_body.get("code") == "42501" or "row-level security" in str(err_body.get("message", "")).lower():
            raise RuntimeError(
                "Akses database Supabase ditolak oleh Row Level Security (RLS) pada tabel 'users'. "
                "Pastikan SUPABASE_SECRET disetel di .env."
            )

    if not r.is_success:
        raise RuntimeError(f"Gagal mendaftarkan pengguna di Supabase ({r.status_code}): {r.text}")

    rows = r.json()
    if not rows:
        raise RuntimeError("Gagal mendaftarkan pengguna: tidak ada respon dari Supabase.")
    user = _format_user(rows[0])
    if user and plain_token:
        _USER_CACHE[plain_token] = (time.time(), user)
    return user


def authenticate_user(username_or_email: str, password: str) -> dict[str, Any] | None:
    identifier = (username_or_email or "").strip()
    pwd = password or ""
    if not identifier or not pwd:
        return None
    if len(pwd) > 128 or len(identifier) > 100:
        return None
    # Cegah PostgREST filter injection dengan membatasi karakter identifier
    if not re.match(r"^[a-zA-Z0-9_.+@-]+$", identifier):
        return None

    # Cari berdasarkan username
    r = _supabase_request(
        "GET",
        "/rest/v1/users",
        params={
            "select": "id,username,email,password,credential_token,created_at,updated_at",
            "username": f"eq.{identifier}",
            "limit": 1,
        },
    )
    rows = r.json() if r.is_success else []
    if not rows:
        # Cari berdasarkan email
        r = _supabase_request(
            "GET",
            "/rest/v1/users",
            params={
                "select": "id,username,email,password,credential_token,created_at,updated_at",
                "email": f"eq.{identifier.lower()}",
                "limit": 1,
            },
        )
        rows = r.json() if r.is_success else []

    if not rows:
        return None

    user = rows[0]
    pwd_val = user.get("password") or user.get("password_hash")
    if not pwd_val or not verify_password(pwd, pwd_val):
        return None

    formatted = _format_user(user)
    if formatted:
        tok = formatted.get("credential_token") or formatted.get("token_credential")
        if tok:
            _USER_CACHE[tok] = (time.time(), formatted)
    return formatted


def get_user_by_id(user_id: int | str) -> dict[str, Any] | None:
    uid_str = str(user_id or "").strip()
    if not uid_str or not re.match(r"^[0-9a-fA-F-]+$", uid_str):
        return None
    r = _supabase_request(
        "GET",
        "/rest/v1/users",
        params={
            "select": "id,username,email,credential_token,created_at,updated_at",
            "id": f"eq.{uid_str}",
            "limit": 1,
        },
    )
    if not r.is_success:
        return None
    rows = r.json()
    return _format_user(rows[0]) if rows else None


def get_user_by_token(token: str) -> dict[str, Any] | None:
    tok = (token or "").strip()
    if not tok or len(tok) > 120 or not re.match(r"^[a-zA-Z0-9_\-\.]+$", tok):
        return None

    now = time.time()
    cached = _USER_CACHE.get(tok)
    if cached:
        cached_time, cached_user = cached
        ttl = _CACHE_TTL_POSITIVE if cached_user is not None else _CACHE_TTL_NEGATIVE
        if now - cached_time < ttl:
            return dict(cached_user) if cached_user else None

    enc_tok = encrypt_token(tok)
    r = _supabase_request(
        "GET",
        "/rest/v1/users",
        params={
            "select": "id,username,email,credential_token,created_at,updated_at",
            "credential_token": f"eq.{enc_tok}",
            "limit": 1,
        },
    )
    rows = r.json() if r.is_success else []
    if not rows:
        # Fallback jika record legacy tersimpan dalam plaintext
        r = _supabase_request(
            "GET",
            "/rest/v1/users",
            params={
                "select": "id,username,email,credential_token,created_at,updated_at",
                "credential_token": f"eq.{tok}",
                "limit": 1,
            },
        )
        rows = r.json() if r.is_success else []

    user = _format_user(rows[0]) if rows else None
    _USER_CACHE[tok] = (now, user)
    return dict(user) if user else None


def regenerate_token(user_id: int | str) -> str:
    new_token = generate_credential_token()
    enc_token = encrypt_token(new_token)
    r = _supabase_request(
        "PATCH",
        "/rest/v1/users",
        params={"id": f"eq.{user_id}"},
        json={"credential_token": enc_token},
        headers={"Prefer": "return=representation"},
    )
    if not r.is_success or not r.json():
        raise ValueError("User tidak ditemukan.")
    invalidate_user_cache()
    return new_token


def update_custom_token(user_id: int | str, custom_token: str) -> str:
    tok = (custom_token or "").strip()
    if len(tok) < 8 or len(tok) > 80:
        raise ValueError("Token kredensial harus antara 8 hingga 80 karakter.")
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", tok):
        raise ValueError("Token hanya boleh berisi huruf, angka, garis bawah (_), tanda hubung (-), atau titik (.).")

    enc_token = encrypt_token(tok)

    # Cek apakah token sudah digunakan oleh pengguna lain
    r_enc = _supabase_request(
        "GET",
        "/rest/v1/users",
        params={
            "select": "id",
            "id": f"neq.{user_id}",
            "credential_token": f"eq.{enc_token}",
            "limit": 1,
        },
    )
    if r_enc.is_success and r_enc.json():
        raise ValueError("Token kredensial ini sudah digunakan oleh pengguna lain. Silakan pilih token lain.")

    r_plain = _supabase_request(
        "GET",
        "/rest/v1/users",
        params={
            "select": "id",
            "id": f"neq.{user_id}",
            "credential_token": f"eq.{tok}",
            "limit": 1,
        },
    )
    if r_plain.is_success and r_plain.json():
        raise ValueError("Token kredensial ini sudah digunakan oleh pengguna lain. Silakan pilih token lain.")

    r = _supabase_request(
        "PATCH",
        "/rest/v1/users",
        params={"id": f"eq.{user_id}"},
        json={"credential_token": enc_token},
        headers={"Prefer": "return=representation"},
    )
    if not r.is_success or not r.json():
        raise ValueError("User tidak ditemukan.")
    invalidate_user_cache()
    return tok


# Backward-compatible internal aliases
_supabase_init_db = init_db
_supabase_register_user = register_user
_supabase_authenticate_user = authenticate_user
_supabase_get_user_by_id = get_user_by_id
_supabase_get_user_by_token = get_user_by_token
_supabase_regenerate_token = regenerate_token
_supabase_update_custom_token = update_custom_token
