"""Hosting klip di URL HTTPS publik, karena Buffer API tidak menerima upload file.

Pilihan (sesuai rekomendasi dokumentasi Buffer):
- Default Server: menggunakan Cloudinary atau Cloudflare R2 yang dikonfigurasi di file .env server (Retensi 8 jam).
- Cloudinary Pribadi (BYOK): upload ke akun Cloudinary milik pengguna sendiri, disimpan di localStorage (Retensi 24 jam).
- Cloudflare R2 Pribadi (BYOK): upload ke bucket Cloudflare R2 milik pengguna sendiri, disimpan di localStorage (Retensi 24 jam).
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from pathlib import Path
from typing import Callable

import httpx

CHUNK = 20 * 1024 * 1024

FIELDS = {
    "default": ["DEFAULT_MEDIA_HOST"],
    "cloudinary": ["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"],
    "r2": ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_URL"],
}
SECRET_FIELDS = {"CLOUDINARY_API_SECRET", "R2_SECRET_ACCESS_KEY"}
LABELS = {
    "DEFAULT_MEDIA_HOST": "URL publik server default",
    "CLOUDINARY_CLOUD_NAME": "Cloud name", "CLOUDINARY_API_KEY": "API key", "CLOUDINARY_API_SECRET": "API secret",
    "R2_ACCOUNT_ID": "Account ID", "R2_ACCESS_KEY_ID": "Access key ID", "R2_SECRET_ACCESS_KEY": "Secret access key",
    "R2_BUCKET": "Bucket", "R2_PUBLIC_URL": "URL publik bucket",
}
NAMES = {
    "default": "Default Server (Cloudinary / R2 bawaan server — 8 Jam)",
    "cloudinary": "Cloudinary Pribadi (24 Jam)",
    "r2": "Cloudflare R2 Pribadi (24 Jam)",
}


def server_provider() -> str:
    p = os.environ.get("MEDIA_HOST", "").strip().lower()
    if p in ("cloudinary", "r2"):
        return p
    if os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip():
        return "cloudinary"
    if os.environ.get("R2_ACCOUNT_ID", "").strip():
        return "r2"
    if os.environ.get("DEFAULT_MEDIA_HOST", "").strip():
        return "default"
    return "cloudinary"


def server_missing() -> list[str]:
    sp = server_provider()
    if sp in ("cloudinary", "r2"):
        return [f for f in FIELDS[sp] if not os.environ.get(f, "").strip()]
    if sp == "default":
        return [f for f in FIELDS["default"] if not os.environ.get(f, "").strip()]
    return []


def server_is_configured() -> bool:
    return len(server_missing()) == 0


def provider() -> str:
    p = os.environ.get("MEDIA_HOST", "").strip().lower()
    if p in FIELDS:
        return p
    if os.environ.get("DEFAULT_MEDIA_HOST", "").strip():
        return "default"
    return "default"


def missing() -> list[str]:
    return server_missing()


def missing_message(lacking: list[str] | None = None) -> str:
    lacking = missing() if lacking is None else lacking
    names = ", ".join(LABELS.get(f, f) for f in lacking)
    return f"Hosting video {NAMES.get(server_provider(), server_provider())} belum lengkap: {names} belum diisi di .env."


def check_context(provider_name: str = "default", creds: dict | None = None) -> str:
    """Cek koneksi hosting baik untuk server default (.env) maupun custom user (localStorage)."""
    creds = creds or {}
    p = (provider_name or "default").strip().lower()
    if p == "default":
        sp = server_provider()
        lacking = server_missing()
        if lacking:
            raise RuntimeError(f"Server default belum lengkap mengonfigurasi hosting video ({NAMES.get(sp, sp)} di .env). Silakan gunakan Cloudinary atau R2 pribadi Anda.")
        env = os.environ
        if sp == "cloudinary":
            cloud = env.get("CLOUDINARY_CLOUD_NAME", "").strip()
            api_key = env.get("CLOUDINARY_API_KEY", "").strip()
            secret = env.get("CLOUDINARY_API_SECRET", "").strip()
            try:
                resp = httpx.get(f"https://api.cloudinary.com/v1_1/{cloud}/ping", auth=(api_key, secret), timeout=20)
            except httpx.HTTPError as e:
                raise RuntimeError(f"Tidak bisa terhubung ke Cloudinary server: {e}") from e
            if resp.status_code == 200:
                return "Terhubung ke Hosting Default Server (Cloudinary bawaan server). Retensi klip: 8 jam."
            hint = {401: "cloud name, API key, atau API secret server salah"}.get(resp.status_code, "")
            raise RuntimeError(f"Cloudinary server menolak (HTTP {resp.status_code}): {hint or resp.text[:120]}")
        elif sp == "r2":
            import boto3
            account = env.get("R2_ACCOUNT_ID", "").strip()
            access = env.get("R2_ACCESS_KEY_ID", "").strip()
            secret = env.get("R2_SECRET_ACCESS_KEY", "").strip()
            bucket = env.get("R2_BUCKET", "").strip()
            public = env.get("R2_PUBLIC_URL", "").strip()
            s3 = boto3.client("s3", endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
                              aws_access_key_id=access, aws_secret_access_key=secret, region_name="auto")
            try:
                s3.head_bucket(Bucket=bucket)
            except Exception as e:
                raise RuntimeError(f"Cloudflare R2 server menolak: {e}") from e
            if not public.startswith("https://"):
                raise RuntimeError("URL publik bucket server default harus diawali https://")
            return "Terhubung ke Hosting Default Server (Cloudflare R2 bawaan server). Retensi klip: 8 jam."
        elif sp == "default":
            base = env.get("DEFAULT_MEDIA_HOST", "").strip()
            if not base or not (base.startswith("https://") or base.startswith("http://")):
                raise RuntimeError("URL publik hosting default server harus diawali https:// (atau http://).")
            return "Terhubung ke Hosting Default Server. Retensi klip: 8 jam."
        else:
            raise RuntimeError("Hosting default server belum siap.")
    elif p == "cloudinary":
        cloud = (creds.get("cloud_name") or creds.get("CLOUDINARY_CLOUD_NAME") or "").strip()
        api_key = (creds.get("api_key") or creds.get("CLOUDINARY_API_KEY") or "").strip()
        secret = (creds.get("api_secret") or creds.get("CLOUDINARY_API_SECRET") or "").strip()
        if not (cloud and api_key and secret):
            raise RuntimeError("Kredensial Cloudinary pribadi belum lengkap (Cloud Name, API Key, dan API Secret wajib diisi).")
        try:
            resp = httpx.get(f"https://api.cloudinary.com/v1_1/{cloud}/ping", auth=(api_key, secret), timeout=20)
        except httpx.HTTPError as e:
            raise RuntimeError(f"Tidak bisa terhubung ke Cloudinary: {e}") from e
        if resp.status_code == 200:
            return f"Terhubung ke Cloudinary pribadi (cloud “{cloud}”). Retensi klip: 24 jam."
        hint = {401: "cloud name, API key, atau API secret salah"}.get(resp.status_code, "")
        raise RuntimeError(f"Cloudinary menolak (HTTP {resp.status_code}): {hint or resp.text[:120]}")
    elif p == "r2":
        import boto3
        account = (creds.get("account_id") or creds.get("R2_ACCOUNT_ID") or "").strip()
        access = (creds.get("access_key_id") or creds.get("R2_ACCESS_KEY_ID") or "").strip()
        secret = (creds.get("secret_access_key") or creds.get("R2_SECRET_ACCESS_KEY") or "").strip()
        bucket = (creds.get("bucket") or creds.get("R2_BUCKET") or "").strip()
        public = (creds.get("public_url") or creds.get("R2_PUBLIC_URL") or "").strip()
        if not (account and access and secret and bucket and public):
            raise RuntimeError("Kredensial Cloudflare R2 pribadi belum lengkap (Account ID, Access Key ID, Secret Access Key, Bucket, URL Publik).")
        s3 = boto3.client("s3", endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
                          aws_access_key_id=access, aws_secret_access_key=secret, region_name="auto")
        try:
            s3.head_bucket(Bucket=bucket)
        except Exception as e:
            raise RuntimeError(f"Cloudflare R2 menolak: {e}") from e
        if not public.startswith("https://"):
            raise RuntimeError("URL publik bucket harus diawali https://")
        return f"Terhubung ke Cloudflare R2 pribadi (bucket “{bucket}”). Retensi klip: 24 jam."
    else:
        raise RuntimeError(f"Penyedia hosting '{p}' tidak didukung.")


def check() -> str:
    """Cek kredensial default tanpa mengunggah apa pun."""
    return check_context("default", {})


def cloudinary_signature(params: dict[str, str], secret: str) -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha1((to_sign + secret).encode()).hexdigest()


def _upload_cloudinary(path: Path, key: str, on_progress: Callable[[float], None], creds: dict | None = None) -> str:
    creds = creds or {}
    cloud = (creds.get("cloud_name") or creds.get("CLOUDINARY_CLOUD_NAME") or os.environ.get("CLOUDINARY_CLOUD_NAME", "")).strip()
    api_key = (creds.get("api_key") or creds.get("CLOUDINARY_API_KEY") or os.environ.get("CLOUDINARY_API_KEY", "")).strip()
    secret = (creds.get("api_secret") or creds.get("CLOUDINARY_API_SECRET") or os.environ.get("CLOUDINARY_API_SECRET", "")).strip()
    if not (cloud and api_key and secret):
        raise RuntimeError("Kredensial Cloudinary belum lengkap (Cloud Name, API Key, API Secret).")

    params = {"folder": "clipping-studio", "public_id": key, "timestamp": str(int(time.time()))}
    data = {**params, "api_key": api_key, "signature": cloudinary_signature(params, secret)}
    url = f"https://api.cloudinary.com/v1_1/{cloud}/video/upload"
    size = path.stat().st_size
    upload_id = uuid.uuid4().hex
    result: dict = {}
    with path.open("rb") as f, httpx.Client(timeout=300) as client:
        offset = 0
        while offset < size:
            chunk = f.read(CHUNK)
            end = offset + len(chunk) - 1
            resp = client.post(
                url, data=data, files={"file": (path.name, chunk, "video/mp4")},
                headers={"X-Unique-Upload-Id": upload_id, "Content-Range": f"bytes {offset}-{end}/{size}"},
            )
            if resp.status_code >= 400:
                msg = resp.json().get("error", {}).get("message", resp.text) if resp.content else resp.status_code
                raise RuntimeError(f"Cloudinary menolak upload: {msg}")
            result = resp.json()
            offset = end + 1
            on_progress(offset / size)
    if not result.get("secure_url"):
        raise RuntimeError("Cloudinary tidak mengembalikan URL video.")
    return result["secure_url"]


def _upload_r2(path: Path, key: str, on_progress: Callable[[float], None], creds: dict | None = None) -> str:
    import boto3
    from boto3.s3.transfer import TransferConfig

    creds = creds or {}
    account = (creds.get("account_id") or creds.get("R2_ACCOUNT_ID") or os.environ.get("R2_ACCOUNT_ID", "")).strip()
    access = (creds.get("access_key_id") or creds.get("R2_ACCESS_KEY_ID") or os.environ.get("R2_ACCESS_KEY_ID", "")).strip()
    secret = (creds.get("secret_access_key") or creds.get("R2_SECRET_ACCESS_KEY") or os.environ.get("R2_SECRET_ACCESS_KEY", "")).strip()
    bucket = (creds.get("bucket") or creds.get("R2_BUCKET") or os.environ.get("R2_BUCKET", "")).strip()
    public = (creds.get("public_url") or creds.get("R2_PUBLIC_URL") or os.environ.get("R2_PUBLIC_URL", "")).strip()
    if not (account and access and secret and bucket and public):
        raise RuntimeError("Kredensial Cloudflare R2 belum lengkap.")

    s3 = boto3.client("s3", endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
                      aws_access_key_id=access, aws_secret_access_key=secret, region_name="auto")
    size, sent = path.stat().st_size, 0

    def cb(n: int) -> None:
        nonlocal sent
        sent += n
        on_progress(min(1.0, sent / size))

    object_key = f"clipping-studio/{key}.mp4"
    s3.upload_file(str(path), bucket, object_key, Callback=cb,
                   ExtraArgs={"ContentType": "video/mp4"},
                   Config=TransferConfig(multipart_chunksize=CHUNK))
    return f"{public.rstrip('/')}/{object_key}"


def _upload_default(path: Path, key: str, on_progress: Callable[[float], None]) -> str:
    base = os.environ.get("DEFAULT_MEDIA_HOST", "").strip()
    if not base:
        raise RuntimeError("DEFAULT_MEDIA_HOST belum diatur pada .env server.")
    on_progress(1.0)
    return f"{base.rstrip('/')}/media/{path.parent.name}/{path.name}"


def upload_context(path: Path, key: str, on_progress: Callable[[float], None],
                   provider_name: str = "default", creds: dict | None = None) -> str:
    """Unggah file menggunakan provider pilihan (default server atau custom user credentials)."""
    creds = creds or {}
    p = (provider_name or "default").strip().lower()
    if p == "default":
        sp = server_provider()
        if sp == "cloudinary":
            url = _upload_cloudinary(path, key, on_progress, {})
        elif sp == "r2":
            url = _upload_r2(path, key, on_progress, {})
        elif sp == "default":
            url = _upload_default(path, key, on_progress)
        else:
            raise RuntimeError("Server default belum mengonfigurasi hosting video (Cloudinary atau R2 di .env).")
    elif p == "cloudinary":
        url = _upload_cloudinary(path, key, on_progress, creds)
    elif p == "r2":
        url = _upload_r2(path, key, on_progress, creds)
    else:
        raise RuntimeError(f"Penyedia hosting '{p}' tidak didukung.")

    if not url.startswith("https://"):
        raise RuntimeError(f"URL video harus HTTPS agar diterima Buffer: {url}")
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        head = client.head(url)
    if head.status_code != 200:
        raise RuntimeError(f"Video sudah terunggah tapi URL-nya tidak bisa diakses publik (HTTP {head.status_code}): {url}")
    return url


def upload(path: Path, key: str, on_progress: Callable[[float], None]) -> str:
    """Unggah file dan kembalikan URL HTTPS publik yang stabil."""
    return upload_context(path, key, on_progress, "default", {})
