"""Koneksi database MySQL untuk manajemen pengguna dan token kredensial."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from typing import Any

import pymysql
import pymysql.cursors

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")


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
    """Inisialisasi tabel users di database MySQL jika belum ada."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                email VARCHAR(100) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                token_credential VARCHAR(100) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
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
    row.pop("password_hash", None)
    if "created_at" in row and row["created_at"] is not None:
        if hasattr(row["created_at"], "isoformat"):
            row["created_at"] = row["created_at"].isoformat()
        else:
            row["created_at"] = str(row["created_at"])
    return row


def register_user(username: str, email: str, password: str) -> dict[str, Any]:
    """Daftarkan user baru ke MySQL dan buatkan token kredensial otomatis."""
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
    token = generate_credential_token()

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

            # Insert user
            cur.execute(
                """
                INSERT INTO users (username, email, password_hash, token_credential)
                VALUES (%s, %s, %s, %s)
                """,
                (uname, mail, pwd_hash, token),
            )
            user_id = cur.lastrowid
            cur.execute("SELECT id, username, email, token_credential, created_at FROM users WHERE id = %s", (user_id,))
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
                SELECT id, username, email, password_hash, token_credential, created_at
                FROM users
                WHERE username = %s OR email = %s
                LIMIT 1
                """,
                (identifier, identifier.lower()),
            )
            row = cur.fetchone()
            if not row:
                return None
            if not verify_password(password, row["password_hash"]):
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
                "SELECT id, username, email, token_credential, created_at FROM users WHERE id = %s LIMIT 1",
                (user_id,),
            )
            return _format_user(cur.fetchone())
    finally:
        conn.close()


def get_user_by_token(token: str) -> dict[str, Any] | None:
    """Ambil data user berdasarkan token kredensial."""
    tok = (token or "").strip()
    if not tok:
        return None
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, email, token_credential, created_at FROM users WHERE token_credential = %s LIMIT 1",
                (tok,),
            )
            return _format_user(cur.fetchone())
    finally:
        conn.close()


def regenerate_token(user_id: int) -> str:
    """Generate token kredensial baru untuk user."""
    new_token = generate_credential_token()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET token_credential = %s WHERE id = %s",
                (new_token, user_id),
            )
            if cur.rowcount == 0:
                raise ValueError("User tidak ditemukan.")
            return new_token
    finally:
        conn.close()


def update_custom_token(user_id: int, custom_token: str) -> str:
    """Atur token kredensial kustom sesuai keinginan user."""
    tok = (custom_token or "").strip()
    if len(tok) < 8 or len(tok) > 80:
        raise ValueError("Token kredensial harus antara 8 hingga 80 karakter.")
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", tok):
        raise ValueError("Token hanya boleh berisi huruf, angka, garis bawah (_), tanda hubung (-), atau titik (.).")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE token_credential = %s AND id != %s LIMIT 1", (tok, user_id))
            if cur.fetchone():
                raise ValueError("Token kredensial ini sudah digunakan oleh pengguna lain. Silakan pilih token lain.")

            cur.execute(
                "UPDATE users SET token_credential = %s WHERE id = %s",
                (tok, user_id),
            )
            if cur.rowcount == 0:
                raise ValueError("User tidak ditemukan.")
            return tok
    finally:
        conn.close()
