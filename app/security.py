"""Validasi keamanan URL (SSRF & Domain Filtering) dan kuota unduhan video."""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit


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
