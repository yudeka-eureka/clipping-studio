"""Koneksi database MySQL untuk manajemen pengguna dan token kredensial."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from typing import Any
from dotenv import load_dotenv

load_dotenv()

import pymysql
import pymysql.cursors
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+$")
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{3,50}$")
TOKEN_ENCRYPTION_PREFIX = "enc_aes256$"


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
        return stored_token


def get_db_config() -> dict[str, Any]:
    return {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USER", "agy"),
        "password": os.environ.get("MYSQL_PASSWORD", "n!ggeradot"),
        "database": os.environ.get("MYSQL_DATABASE", "clipping_studio"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "connect_timeout": 5,
        "autocommit": True,
    }


def get_connection():
    config = get_db_config()
    return pymysql.connect(**config)


def init_db() -> None:
    """Inisialisasi tabel users dan model_keys di database MySQL jika belum ada, serta migrasi kolom jika perlu."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                email VARCHAR(100) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                credential_token VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) DEFAULT CHARSET=utf8mb4;
            """)
            try:
                cur.execute("ALTER TABLE users MODIFY COLUMN credential_token VARCHAR(255) NOT NULL;")
            except Exception:
                pass

            # Tabel terpisah untuk kredensial model AI, media hosting, dan buffer
            cur.execute("""
            CREATE TABLE IF NOT EXISTS model_keys (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                type VARCHAR(30) NOT NULL,
                provider VARCHAR(50) NOT NULL,
                `key` TEXT NOT NULL,
                secret_key TEXT NULL,
                r2_account_id TEXT NULL,
                r2_bucket VARCHAR(255) NULL,
                r2_bucket_url VARCHAR(255) NULL,
                cloud_name VARCHAR(120) NULL,
                model VARCHAR(100) NULL,
                is_active BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_user_type_provider (user_id, type, provider),
                INDEX idx_user_type (user_id, type),
                CONSTRAINT fk_model_keys_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) DEFAULT CHARSET=utf8mb4;
            """)
            try:
                cur.execute("ALTER TABLE model_keys ADD COLUMN cloud_name VARCHAR(120) NULL;")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE model_keys ADD COLUMN model VARCHAR(100) NULL;")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE model_keys ADD COLUMN is_active BOOLEAN DEFAULT FALSE;")
            except Exception:
                pass
        conn.close()
    except Exception as e:
        # Jangan gagalkan startup jika database sedang offline; log peringatan
        print(f"⚠️ [MySQL Init] Peringatan koneksi database: {e}")


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
    row.pop("password", None)
    row.pop("ai_credentials", None)
    row.pop("media_credentials", None)
    if "credential_token" in row and row["credential_token"]:
        row["credential_token"] = decrypt_token(row["credential_token"])
    if "created_at" in row and row["created_at"] is not None:
        if hasattr(row["created_at"], "isoformat"):
            row["created_at"] = row["created_at"].isoformat()
        else:
            row["created_at"] = str(row["created_at"])
    return row


def register_user(username: str, email: str, password: str) -> dict[str, Any]:
    """Daftarkan user baru ke MySQL dan buatkan token kredensial terenkripsi AES-256."""
    uname = (username or "").strip()
    mail = (email or "").strip().lower()
    pwd = password or ""

    if not USERNAME_REGEX.match(uname):
        raise ValueError("Username harus terdiri dari 3–50 karakter alfanumerik (huruf, angka, _, -).")
    if not EMAIL_REGEX.match(mail):
        raise ValueError("Alamat email tidak valid.")
    if len(pwd) < 6:
        raise ValueError("Kata sandi minimal 6 karakter.")

    pwd_hash = hash_password(pwd)
    plain_token = generate_credential_token()
    enc_token = encrypt_token(plain_token)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Cek apakah username sudah dipakai
            cur.execute("SELECT id FROM users WHERE username = %s LIMIT 1", (uname,))
            if cur.fetchone():
                raise ValueError(f"Username '{uname}' sudah digunakan. Silakan pilih username lain.")

            # Cek apakah email sudah dipakai
            cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (mail,))
            if cur.fetchone():
                raise ValueError(f"Alamat email '{mail}' sudah terdaftar.")

            # Insert user dengan credential_token terenkripsi AES-256
            cur.execute(
                """
                INSERT INTO users (username, email, password, credential_token)
                VALUES (%s, %s, %s, %s)
                """,
                (uname, mail, pwd_hash, enc_token),
            )
            user_id = cur.lastrowid
            cur.execute("SELECT id, username, email, credential_token, created_at FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            return _format_user(user)
    finally:
        conn.close()


def authenticate_user(username_or_email: str, password: str) -> dict[str, Any] | None:
    """Autentikasi user dengan username atau email beserta password."""
    identifier = (username_or_email or "").strip()
    if not identifier or not password:
        return None

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, username, email, password, credential_token, created_at
                FROM users
                WHERE username = %s OR email = %s
                LIMIT 1
                """,
                (identifier, identifier.lower()),
            )
            row = cur.fetchone()
            if not row:
                return None
            if not verify_password(password, row["password"]):
                return None

            return _format_user(row)
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """Ambil data user berdasarkan ID."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, email, credential_token, created_at FROM users WHERE id = %s LIMIT 1",
                (user_id,),
            )
            return _format_user(cur.fetchone())
    finally:
        conn.close()


def get_user_by_token(token: str) -> dict[str, Any] | None:
    """Ambil data user berdasarkan token kredensial (mencocokkan ciphertext AES-256)."""
    tok = (token or "").strip()
    if not tok:
        return None
    enc_tok = encrypt_token(tok)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, email, credential_token, created_at FROM users WHERE credential_token = %s LIMIT 1",
                (enc_tok,),
            )
            row = cur.fetchone()
            if not row:
                # Fallback jika record legacy tersimpan dalam plaintext
                cur.execute(
                    "SELECT id, username, email, credential_token, created_at FROM users WHERE credential_token = %s LIMIT 1",
                    (tok,),
                )
                row = cur.fetchone()
            return _format_user(row)
    finally:
        conn.close()


def regenerate_token(user_id: int) -> str:
    """Generate token kredensial baru untuk user dan enkripsi dengan AES-256 sebelum disimpan."""
    new_token = generate_credential_token()
    enc_token = encrypt_token(new_token)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET credential_token = %s WHERE id = %s",
                (enc_token, user_id),
            )
            if cur.rowcount == 0:
                raise ValueError("User tidak ditemukan.")
            return new_token
    finally:
        conn.close()


def update_custom_token(user_id: int, custom_token: str) -> str:
    """Atur token kredensial kustom sesuai keinginan user dan enkripsi dengan AES-256 sebelum disimpan."""
    tok = (custom_token or "").strip()
    if len(tok) < 8 or len(tok) > 80:
        raise ValueError("Token kredensial harus antara 8 hingga 80 karakter.")
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", tok):
        raise ValueError("Token hanya boleh berisi huruf, angka, garis bawah (_), tanda hubung (-), atau titik (.).")

    enc_token = encrypt_token(tok)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE (credential_token = %s OR credential_token = %s) AND id != %s LIMIT 1",
                (enc_token, tok, user_id),
            )
            if cur.fetchone():
                raise ValueError("Token kredensial ini sudah digunakan oleh pengguna lain. Silakan pilih token lain.")

            cur.execute(
                "UPDATE users SET credential_token = %s WHERE id = %s",
                (enc_token, user_id),
            )
            if cur.rowcount == 0:
                raise ValueError("User tidak ditemukan.")
            return tok
    finally:
        conn.close()


def normalize_provider(p: str | None) -> str:
    """Normalisasi alias nama provider AI / media ke identifier standar."""
    prov = (p or "").strip().lower()
    mapping = {
        "claude": "anthropic",
        "chatgpt": "openai",
        "gpt": "openai",
        "cloudflare": "r2",
        "cloudflare_r2": "r2",
    }
    return mapping.get(prov, prov)


def save_model_key(
    user_id: int,
    key_type: str,
    provider: str,
    *,
    key: str | None = None,
    secret_key: str | None = None,
    r2_account_id: str | None = None,
    r2_bucket: str | None = None,
    r2_bucket_url: str | None = None,
    cloud_name: str | None = None,
    model: str | None = None,
    is_active: bool | None = None,
) -> None:
    """Simpan atau perbarui entri kredensial di tabel model_keys.

    Bidang sensitif (`key`, `secret_key`, `r2_account_id`) selalu dienkripsi
    menggunakan AES-256 sebelum disimpan ke dalam database.
    """
    k_type = (key_type or "").strip().lower()
    p_name = normalize_provider(provider)
    if not k_type or not p_name:
        raise ValueError("Tipe dan provider model_key wajib diisi.")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, `key`, secret_key, r2_account_id, r2_bucket, r2_bucket_url, cloud_name, model, is_active "
                "FROM model_keys WHERE user_id = %s AND type = %s AND provider = %s LIMIT 1",
                (user_id, k_type, p_name),
            )
            existing = cur.fetchone()

            # Enkripsi bidang sensitif jika disediakan nilai baru; pertahankan jika None
            if key is not None:
                val = key.strip()
                final_key = encrypt_token(val) if val else None
            else:
                final_key = existing["key"] if existing else None

            if secret_key is not None:
                val = secret_key.strip()
                final_sec = encrypt_token(val) if val else None
            else:
                final_sec = existing["secret_key"] if existing else None

            if r2_account_id is not None:
                val = r2_account_id.strip()
                final_acc = encrypt_token(val) if val else None
            else:
                final_acc = existing["r2_account_id"] if existing else None

            final_bucket = r2_bucket.strip() if r2_bucket is not None else (existing["r2_bucket"] if existing else None)
            final_url = r2_bucket_url.strip() if r2_bucket_url is not None else (existing["r2_bucket_url"] if existing else None)
            final_cloud = cloud_name.strip() if cloud_name is not None else (existing["cloud_name"] if existing else None)
            final_model = model.strip() if model is not None else (existing["model"] if existing else None)

            if is_active is None:
                final_active = bool(existing["is_active"]) if existing else True
            else:
                final_active = bool(is_active)

            # Jika entri ini dijadikan aktif, nonaktifkan entri lain dengan user_id dan type yang sama
            if final_active:
                cur.execute(
                    "UPDATE model_keys SET is_active = FALSE WHERE user_id = %s AND type = %s AND provider != %s",
                    (user_id, k_type, p_name),
                )

            cur.execute(
                """
                INSERT INTO model_keys (
                    user_id, type, provider, `key`, secret_key,
                    r2_account_id, r2_bucket, r2_bucket_url, cloud_name, model, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    `key` = VALUES(`key`),
                    secret_key = VALUES(secret_key),
                    r2_account_id = VALUES(r2_account_id),
                    r2_bucket = VALUES(r2_bucket),
                    r2_bucket_url = VALUES(r2_bucket_url),
                    cloud_name = VALUES(cloud_name),
                    model = VALUES(model),
                    is_active = VALUES(is_active)
                """,
                (
                    user_id, k_type, p_name, final_key, final_sec,
                    final_acc, final_bucket, final_url, final_cloud, final_model, final_active,
                ),
            )
    finally:
        conn.close()


def get_model_keys_by_user(user_id: int, key_type: str | None = None) -> list[dict[str, Any]]:
    """Ambil daftar kredensial model_keys milik user dengan dekripsi otomatis nilai sensitif."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if key_type:
                cur.execute(
                    "SELECT * FROM model_keys WHERE user_id = %s AND type = %s ORDER BY id ASC",
                    (user_id, key_type.strip().lower()),
                )
            else:
                cur.execute(
                    "SELECT * FROM model_keys WHERE user_id = %s ORDER BY id ASC",
                    (user_id,),
                )
            rows = cur.fetchall() or []
            results = []
            for r in rows:
                item = dict(r)
                item["key"] = decrypt_token(item.get("key"))
                item["secret_key"] = decrypt_token(item.get("secret_key"))
                item["r2_account_id"] = decrypt_token(item.get("r2_account_id"))
                results.append(item)
            return results
    finally:
        conn.close()


def delete_model_key(user_id: int, key_type: str, provider: str | None = None) -> None:
    """Hapus entri model_key untuk pengguna tertentu."""
    k_type = (key_type or "").strip().lower()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if provider:
                p_name = normalize_provider(provider)
                cur.execute(
                    "DELETE FROM model_keys WHERE user_id = %s AND type = %s AND provider = %s",
                    (user_id, k_type, p_name),
                )
            else:
                cur.execute(
                    "DELETE FROM model_keys WHERE user_id = %s AND type = %s",
                    (user_id, k_type),
                )
    finally:
        conn.close()


def save_user_ai_credentials(user_id: int, creds: dict) -> None:
    """Simpan preferensi kredensial AI user ke tabel model_keys terpisah."""
    if not isinstance(creds, dict):
        return

    active_provider = normalize_provider(creds.get("provider") or "gemini")
    providers_map = creds.get("providers") or {}

    if not providers_map and not creds.get("provider"):
        delete_model_key(user_id, "ai")
        return

    for prov_name, prov_data in providers_map.items():
        if not isinstance(prov_data, dict):
            continue
        p = normalize_provider(prov_name)
        save_model_key(
            user_id,
            "ai",
            p,
            key=prov_data.get("key"),
            model=prov_data.get("model"),
            is_active=(p == active_provider),
        )

    if active_provider:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE model_keys SET is_active = (provider = %s) WHERE user_id = %s AND type = 'ai'",
                    (active_provider, user_id),
                )
        finally:
            conn.close()


def get_user_ai_credentials(user_id: int) -> dict | None:
    """Ambil preferensi kredensial AI user dari tabel model_keys."""
    items = get_model_keys_by_user(user_id, "ai")
    if not items:
        # Fallback ke kolom users.ai_credentials jika ada data legacy
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT ai_credentials FROM users WHERE id = %s LIMIT 1", (user_id,))
                row = cur.fetchone()
                if row and row.get("ai_credentials"):
                    decrypted = decrypt_token(row["ai_credentials"])
                    if decrypted:
                        data = json.loads(decrypted)
                        if isinstance(data, dict):
                            save_user_ai_credentials(user_id, data)
                            return data
        except Exception:
            pass
        return None

    active_provider = "gemini"
    providers_dict = {}
    for it in items:
        p = it["provider"]
        providers_dict[p] = {
            "key": it["key"] or "",
            "model": it["model"] or "",
        }
        if it.get("is_active"):
            active_provider = p

    return {
        "provider": active_provider,
        "providers": providers_dict,
    }


def save_user_media_credentials(user_id: int, creds: dict) -> None:
    """Simpan preferensi kredensial cloud media user ke tabel model_keys terpisah."""
    if not isinstance(creds, dict):
        return

    active_host = (creds.get("host") or "default").strip().lower()

    if not creds.get("cloudinary") and not creds.get("r2") and active_host == "default":
        delete_model_key(user_id, "media")
        return

    # Simpan Cloudinary jika ada data
    c_data = creds.get("cloudinary") or {}
    if isinstance(c_data, dict) and any(c_data.values()):
        save_model_key(
            user_id,
            "media",
            "cloudinary",
            key=c_data.get("api_key") or c_data.get("CLOUDINARY_API_KEY"),
            secret_key=c_data.get("api_secret") or c_data.get("CLOUDINARY_API_SECRET"),
            cloud_name=c_data.get("cloud_name") or c_data.get("CLOUDINARY_CLOUD_NAME"),
            r2_account_id=c_data.get("cloud_name") or c_data.get("CLOUDINARY_CLOUD_NAME"),
            is_active=(active_host == "cloudinary"),
        )

    # Simpan Cloudflare R2 jika ada data
    r_data = creds.get("r2") or {}
    if isinstance(r_data, dict) and any(r_data.values()):
        save_model_key(
            user_id,
            "media",
            "r2",
            key=r_data.get("access_key_id") or r_data.get("R2_ACCESS_KEY_ID"),
            secret_key=r_data.get("secret_access_key") or r_data.get("R2_SECRET_ACCESS_KEY"),
            r2_account_id=r_data.get("account_id") or r_data.get("R2_ACCOUNT_ID"),
            r2_bucket=r_data.get("bucket") or r_data.get("R2_BUCKET"),
            r2_bucket_url=r_data.get("public_url") or r_data.get("R2_PUBLIC_URL"),
            is_active=(active_host == "r2"),
        )

    # Update status aktif host
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE model_keys SET is_active = (provider = %s) WHERE user_id = %s AND type = 'media'",
                (active_host, user_id),
            )
    finally:
        conn.close()


def get_user_media_credentials(user_id: int) -> dict | None:
    """Ambil preferensi kredensial cloud media user dari tabel model_keys."""
    items = get_model_keys_by_user(user_id, "media")
    if not items:
        # Fallback ke users.media_credentials jika ada data legacy
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT media_credentials FROM users WHERE id = %s LIMIT 1", (user_id,))
                row = cur.fetchone()
                if row and row.get("media_credentials"):
                    decrypted = decrypt_token(row["media_credentials"])
                    if decrypted:
                        data = json.loads(decrypted)
                        if isinstance(data, dict):
                            save_user_media_credentials(user_id, data)
                            return data
        except Exception:
            pass
        return None

    active_host = "default"
    cloudinary_dict = {}
    r2_dict = {}

    for it in items:
        p = it["provider"]
        if it.get("is_active"):
            active_host = p

        if p == "cloudinary":
            cloudinary_dict = {
                "cloud_name": it["cloud_name"] or it["r2_account_id"] or "",
                "api_key": it["key"] or "",
                "api_secret": it["secret_key"] or "",
            }
        elif p == "r2":
            r2_dict = {
                "account_id": it["r2_account_id"] or "",
                "access_key_id": it["key"] or "",
                "secret_access_key": it["secret_key"] or "",
                "bucket": it["r2_bucket"] or "",
                "public_url": it["r2_bucket_url"] or "",
            }

    return {
        "host": active_host,
        "cloudinary": cloudinary_dict,
        "r2": r2_dict,
    }


def save_user_buffer_key(user_id: int, api_key: str) -> None:
    """Simpan Buffer API key user ke model_keys terenkripsi AES-256."""
    save_model_key(user_id, "buffer", "buffer", key=api_key, is_active=True)


def get_user_buffer_key(user_id: int) -> str:
    """Ambil Buffer API key user dari model_keys."""
    items = get_model_keys_by_user(user_id, "buffer")
    if items:
        return items[0].get("key") or ""
    return ""


