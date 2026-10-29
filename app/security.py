"""Validasi keamanan URL (SSRF & Domain Filtering) dan kuota unduhan video."""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import secrets
import socket
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Request, Response


class SecurityValidationError(ValueError):
    """Pengecualian saat validasi URL gagal karena alasan keamanan."""
    pass


# Domain publik terverifikasi untuk unduhan video
VERIFIED_DOMAINS: set[str] = {
    # YouTube
    "youtube.com",
    "youtu.be",
    # TikTok
    "tiktok.com",
    # Vimeo
    "vimeo.com",
    # Instagram
    "instagram.com",
    "instagr.am",
    # Facebook
    "facebook.com",
    "fb.watch",
    # X / Twitter
    "twitter.com",
    "x.com",
    # Twitch
    "twitch.tv",
    # Dailymotion
    "dailymotion.com",
    "dai.ly",
    # Reddit
    "reddit.com",
    "v.redd.it",
    # Loom
    "loom.com",
    # Streamable
    "streamable.com",
}

DEFAULT_MAX_FILESIZE_MB: int = 500
DEFAULT_MAX_DURATION_MINUTES: int = 45
DEFAULT_JOB_RETENTION_HOURS: int = 24
DEFAULT_EXECUTION_TIMEOUT_MINUTES: int = 15

ALLOWED_VIDEO_EXTENSIONS: set[str] = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
ALLOWED_VIDEO_MIMES: set[str] = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
}


def max_filesize_mb() -> int:
    try:
        val = int(os.environ.get("MAX_FILESIZE_MB", "").strip() or DEFAULT_MAX_FILESIZE_MB)
        return max(1, val)
    except (ValueError, TypeError):
        return DEFAULT_MAX_FILESIZE_MB


def max_filesize_bytes() -> int:
    return max_filesize_mb() * 1024 * 1024


def max_duration_minutes() -> int:
    try:
        val = int(os.environ.get("MAX_DURATION_MINUTES", "").strip() or DEFAULT_MAX_DURATION_MINUTES)
        return max(1, val)
    except (ValueError, TypeError):
        return DEFAULT_MAX_DURATION_MINUTES


def max_duration_seconds() -> int:
    return max_duration_minutes() * 60


def job_retention_hours() -> int:
    try:
        val = int(os.environ.get("JOB_RETENTION_HOURS", "").strip() or DEFAULT_JOB_RETENTION_HOURS)
        return max(1, val)
    except (ValueError, TypeError):
        return DEFAULT_JOB_RETENTION_HOURS


def job_retention_seconds() -> int:
    return job_retention_hours() * 3600


def execution_timeout_minutes() -> int:
    try:
        val = int(os.environ.get("EXECUTION_TIMEOUT_MINUTES", "").strip() or DEFAULT_EXECUTION_TIMEOUT_MINUTES)
        return max(1, val)
    except (ValueError, TypeError):
        return DEFAULT_EXECUTION_TIMEOUT_MINUTES


def execution_timeout_seconds() -> int:
    return execution_timeout_minutes() * 60


def detect_video_mime(header: bytes) -> str | None:
    """Deteksi tipe MIME kontainer video dari header magic bytes.

    Mendukung:
    - video/mp4 (ISO Base Media File Format: mp41, mp42, isom, iso2, avc1, dash, dll)
    - video/quicktime (Apple QuickTime MOV: qt  , moov, wide)
    - video/webm (EBML container dengan DocType webm)
    - video/x-matroska (EBML container dengan DocType matroska)

    Mengembalikan tipe MIME jika valid, atau None jika bukan kontainer video valid.
    """
    if not header or len(header) < 8:
        return None

    # 1. EBML Header (WebM / Matroska MKV): 0x1A 0x45 0xDF 0xA3
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        sample = header[:128]
        if b"matroska" in sample:
            return "video/x-matroska"
        if b"webm" in sample:
            return "video/webm"
        # Secara standar EBML didominasi webm / matroska
        return "video/webm"

    # 2. ISO Base Media File Format (MP4 / QuickTime / M4V)
    # Box header: [4 bytes box size][4 bytes box type]
    box_type = header[4:8]
    if box_type == b"ftyp":
        major_brand = header[8:12] if len(header) >= 12 else b""
        if major_brand == b"qt  ":
            return "video/quicktime"
        mp4_brands = (
            b"isom", b"iso2", b"mp41", b"mp42", b"mp4v", b"dash",
            b"avc1", b"MSNV", b"NDSC", b"NSDC", b"M4V ", b"M4A ",
            b"M4B ", b"M4P ", b"f4v ", b"kddi"
        )
        if major_brand in mp4_brands:
            return "video/mp4"

        # Periksa compatible brands jika ada
        compatible = header[16:128]
        if b"qt  " in compatible:
            return "video/quicktime"
        if any(b in compatible for b in mp4_brands):
            return "video/mp4"
        return "video/mp4"

    # QuickTime legacy atoms tanpa ftyp box di awal (moov, wide, mdat, free, skip)
    if box_type in (b"moov", b"wide", b"mdat", b"free", b"skip"):
        return "video/quicktime"

    return None


def validate_video_header(header: bytes) -> str:
    """Validasi magic bytes dan kembalikan MIME type video.

    Melempar SecurityValidationError jika header bukan video yang didukung.
    """
    mime = detect_video_mime(header)
    if not mime:
        raise SecurityValidationError(
            "Berkas bukan format video yang valid. "
            "Hanya kontainer video (MP4, WebM, MOV, MKV) yang diizinkan."
        )
    return mime


def detect_image_mime(header: bytes) -> str | None:
    """Deteksi tipe MIME gambar (PNG, JPEG, WebP) dari magic bytes."""
    if not header or len(header) < 4:
        return None
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def allowed_domains() -> set[str]:
    domains = set(VERIFIED_DOMAINS)
    custom = os.environ.get("ALLOWED_DOMAINS", "").strip()
    if custom:
        for d in custom.split(","):
            cleaned = d.strip().lower().lstrip(".")
            if cleaned:
                domains.add(cleaned)
    return domains


def is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Periksa apakah IP termasuk loopback, private, link-local, multicast, CGNAT, atau reserved."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (
        not ip.is_global or
        ip.is_loopback or
        ip.is_private or
        ip.is_link_local or
        ip.is_reserved or
        ip.is_unspecified or
        ip.is_multicast
    )


def is_domain_allowed(hostname: str, allowed: set[str]) -> bool:
    """Periksa apakah hostname cocok dengan allowlist domain atau subdomainnya."""
    if "*" in allowed:
        return True
    for d in allowed:
        d = d.strip().lower().lstrip(".")
        if not d:
            continue
        if hostname == d or hostname.endswith("." + d):
            return True
    return False


def validate_video_url(url: str) -> str:
    """Validasi URL video untuk mencegah SSRF dan penyalahgunaan unduhan."""
    url = (url or "").strip()
    if not url:
        raise SecurityValidationError("URL video tidak boleh kosong.")

    # 1. Pastikan protokol https://
    # Tolak eksplisit http://, file://, ftp://, dsb.
    if url.lower().startswith("http://"):
        raise SecurityValidationError(
            "URL harus menggunakan protokol https:// (protokol http:// ditolak demi keamanan)."
        )
    if not url.lower().startswith("https://"):
        raise SecurityValidationError(
            "URL tidak valid. Hanya protokol https:// yang diizinkan (protokol seperti file://, ftp:// ditolak)."
        )

    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise SecurityValidationError("Hanya protokol https:// yang diizinkan.")

    if not parsed.hostname:
        raise SecurityValidationError("URL tidak memiliki nama host atau domain yang valid.")

    hostname = parsed.hostname.strip().lower().rstrip(".")

    # Larang kredensial di URL (misal: https://user:pass@example.com)
    if parsed.username or parsed.password:
        raise SecurityValidationError("URL tidak boleh menyertakan kredensial pengguna.")

    # Larang port non-standar HTTPS
    if parsed.port is not None and parsed.port != 443:
        raise SecurityValidationError(
            f"Port {parsed.port} tidak diizinkan. Hanya port standar HTTPS (443) yang didukung."
        )

    # 2. Cek localhost dan IP literal secara langsung sebelum DNS
    if hostname in ("localhost", "localhost.localdomain") or hostname.endswith(".localhost"):
        raise SecurityValidationError(f"Akses ke host lokal ({hostname}) tidak diizinkan.")

    try:
        ip = ipaddress.ip_address(hostname)
        # Jika hostname adalah IP literal
        if is_ip_blocked(ip):
            raise SecurityValidationError(f"Akses ke alamat IP privat atau lokal ({hostname}) tidak diizinkan.")
        # Sekalipun IP publik literal, hanya domain terverifikasi yang didukung
        raise SecurityValidationError("Penggunaan alamat IP langsung tidak diizinkan. Gunakan domain penyedia video.")
    except ValueError as e:
        if "Akses ke" in str(e) or "Penggunaan alamat IP" in str(e):
            raise
        # Bukan IP literal, lanjutkan ke pengecekan domain

    # 3. Batasi domain ke allowlist (YouTube, TikTok, Vimeo, dsb.)
    allowed = allowed_domains()
    if not is_domain_allowed(hostname, allowed):
        raise SecurityValidationError(
            f"Domain '{hostname}' tidak diizinkan. Hanya domain penyedia video publik terverifikasi "
            f"(YouTube, TikTok, Vimeo, dll) yang didukung."
        )

    # 4. Resolusi IP domain target (DNS resolution) dan blokir jika mengarah ke IP privat
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise SecurityValidationError(f"Gagal melakukan resolusi DNS untuk domain '{hostname}'.") from e

    if not addr_info:
        raise SecurityValidationError(f"Domain '{hostname}' tidak dapat dijangkau.")

    for item in addr_info:
        ip_str = item[4][0]
        try:
            resolved_ip = ipaddress.ip_address(ip_str)
            if is_ip_blocked(resolved_ip):
                raise SecurityValidationError(
                    f"Akses ke IP privat atau localhost tidak diizinkan ({hostname} mengarah ke IP privat {ip_str})."
                )
        except ValueError as e:
            if "Akses ke IP privat" in str(e):
                raise
            raise SecurityValidationError(f"Format IP dari hasil resolusi tidak valid: {ip_str}") from e

    return url


# ---------- Enkripsi & Keamanan Cookie (HttpOnly, Secure, SameSite) ----------

COOKIE_ENCRYPTION_PREFIX = "enc_aes256$"
USER_TOKEN_COOKIE = "clipping_user_token"
SESSION_COOKIE = "clipping_session"
AI_CREDS_COOKIE = "clipping_ai_creds"
MEDIA_CREDS_COOKIE = "clipping_media_creds"


def encrypt_cookie_data(data: Any, master_key: bytes | None = None) -> str:
    """Enkripsi payload cookie (dict, list, atau str) menggunakan AES-256-GCM dengan random nonce."""
    if data is None:
        return ""
    if master_key is None:
        from .db import get_token_encryption_key
        master_key = get_token_encryption_key()

    payload = json.dumps(data) if not isinstance(data, str) else data
    data_bytes = payload.encode("utf-8")
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(master_key)
    ciphertext = aesgcm.encrypt(nonce, data_bytes, None)
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return f"{COOKIE_ENCRYPTION_PREFIX}{encoded}"


def decrypt_cookie_data(cookie_val: str | None, master_key: bytes | None = None) -> Any:
    """Dekripsi nilai cookie terenkripsi AES-256-GCM. Mengembalikan objek asal atau None jika gagal."""
    if not cookie_val:
        return None
    val = cookie_val.strip().strip('"').strip("'")
    if not val.startswith(COOKIE_ENCRYPTION_PREFIX):
        # Fallback jika plain json atau plain string
        try:
            return json.loads(val)
        except Exception:
            return val
    try:
        if master_key is None:
            from .db import get_token_encryption_key
            master_key = get_token_encryption_key()
        encoded = val[len(COOKIE_ENCRYPTION_PREFIX):]
        raw_bytes = base64.urlsafe_b64decode(encoded.encode("ascii"))
        nonce = raw_bytes[:12]
        ciphertext = raw_bytes[12:]
        aesgcm = AESGCM(master_key)
        plain_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        text = plain_bytes.decode("utf-8")
        try:
            return json.loads(text)
        except Exception:
            return text
    except Exception:
        return None


def is_cookie_secure(request: Request | None = None) -> bool:
    """Tentukan apakah flag 'Secure' harus aktif pada cookie.

    - Jika COOKIE_SECURE disetel di environment, prioritaskan nilai tersebut.
    - Jika request melalui HTTPS (atau reverse proxy X-Forwarded-Proto: https), kembalikan True.
    - Jika request melalui plain HTTP, kembalikan False agar browser tidak membuang cookie (RFC 6265bis).
    - Default ke nilai PUBLIC_MODE jika request tidak tersedia.
    """
    explicit = os.environ.get("COOKIE_SECURE")
    if explicit is not None:
        return explicit.strip().lower() in ("1", "true", "yes", "on")
    if request:
        try:
            proto = request.headers.get("x-forwarded-proto") or request.scope.get("scheme", "http")
            if str(proto).lower() == "https":
                return True
            # Jika request melalui plain HTTP, jangan aktifkan flag Secure
            # karena browser akan membuang cookie Secure yang dikirim melalui HTTP (RFC 6265bis).
            return False
        except Exception:
            pass
    return os.environ.get("PUBLIC_MODE", "false").strip().lower() in ("1", "true", "yes", "on")


def set_secure_cookie(
    response: Response,
    key: str,
    data: Any,
    max_age: int = 60 * 60 * 24 * 30,  # 30 hari
    request: Request | None = None,
    samesite: str = "lax",
    httponly: bool = True,
) -> None:
    """Set cookie dengan enkripsi AES-256-GCM, HttpOnly, Secure, dan SameSite."""
    val = encrypt_cookie_data(data)
    response.set_cookie(
        key=key,
        value=val,
        httponly=httponly,
        secure=is_cookie_secure(request),
        samesite=samesite,
        max_age=max_age,
        path="/",
    )


def clear_secure_cookie(response: Response, key: str) -> None:
    """Hapus cookie secara aman."""
    response.delete_cookie(key=key, path="/")
