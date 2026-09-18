"""Hosting klip di URL HTTPS publik, karena Buffer API tidak menerima upload file.

Pilihan (sesuai rekomendasi dokumentasi Buffer):
- Cloudinary: upload video bertanda tangan (API key + secret), dipecah per 20 MB.
- Cloudflare R2: bucket S3-compatible dengan akses publik (r2.dev atau domain sendiri).
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
    "cloudinary": ["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"],
    "r2": ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_URL"],
}
SECRET_FIELDS = {"CLOUDINARY_API_SECRET", "R2_SECRET_ACCESS_KEY"}
LABELS = {
    "CLOUDINARY_CLOUD_NAME": "Cloud name", "CLOUDINARY_API_KEY": "API key", "CLOUDINARY_API_SECRET": "API secret",
    "R2_ACCOUNT_ID": "Account ID", "R2_ACCESS_KEY_ID": "Access key ID", "R2_SECRET_ACCESS_KEY": "Secret access key",
    "R2_BUCKET": "Bucket", "R2_PUBLIC_URL": "URL publik bucket",
}
NAMES = {"cloudinary": "Cloudinary", "r2": "Cloudflare R2"}


def provider() -> str:
    p = os.environ.get("MEDIA_HOST", "").strip()
    return p if p in FIELDS else "cloudinary"


def missing() -> list[str]:
    return [f for f in FIELDS[provider()] if not os.environ.get(f, "").strip()]


def missing_message(lacking: list[str] | None = None) -> str:
    lacking = missing() if lacking is None else lacking
    names = ", ".join(LABELS.get(f, f) for f in lacking)
    return f"Hosting video {NAMES[provider()]} belum lengkap: {names} belum diisi. Buka ⚙ Pengaturan."


def check() -> str:
    """Cek kredensial tanpa mengunggah apa pun. Return pesan sukses, atau raise dengan alasan."""
    lacking = missing()
    if lacking:
        raise RuntimeError(missing_message(lacking))
    env = os.environ
    if provider() == "cloudinary":
        cloud, api_key, secret = (env[f].strip() for f in FIELDS["cloudinary"])
        try:
            resp = httpx.get(f"https://api.cloudinary.com/v1_1/{cloud}/ping", auth=(api_key, secret), timeout=20)
        except httpx.HTTPError as e:
            raise RuntimeError(f"Tidak bisa terhubung ke Cloudinary: {e}") from e
        if resp.status_code == 200:
            return f"Terhubung ke Cloudinary (cloud “{cloud}”)."
        try:
            msg = resp.json().get("error", {}).get("message", "")
        except ValueError:
            msg = ""
        hint = {401: "cloud name, API key, atau API secret salah"}.get(resp.status_code, "")
        raise RuntimeError(f"Cloudinary menolak (HTTP {resp.status_code}): {hint or msg or resp.text[:120]}")
    import boto3

    account, access, secret, bucket, public = (env[f].strip() for f in FIELDS["r2"])
    s3 = boto3.client("s3", endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
                      aws_access_key_id=access, aws_secret_access_key=secret, region_name="auto")
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Cloudflare R2 menolak: {e}") from e
    if not public.startswith("https://"):
        raise RuntimeError("URL publik bucket harus diawali https://")
    return f"Terhubung ke Cloudflare R2 (bucket “{bucket}”)."


def cloudinary_signature(params: dict[str, str], secret: str) -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha1((to_sign + secret).encode()).hexdigest()


def _upload_cloudinary(path: Path, key: str, on_progress: Callable[[float], None]) -> str:
    env = os.environ
    cloud, api_key, secret = (env[f].strip() for f in FIELDS["cloudinary"])
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


def _upload_r2(path: Path, key: str, on_progress: Callable[[float], None]) -> str:
    import boto3
    from boto3.s3.transfer import TransferConfig

    env = os.environ
    account, access, secret, bucket, public = (env[f].strip() for f in FIELDS["r2"])
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


def upload(path: Path, key: str, on_progress: Callable[[float], None]) -> str:
    """Unggah file dan kembalikan URL HTTPS publik yang stabil."""
    lacking = missing()
    if lacking:
        raise RuntimeError(missing_message(lacking))
    url = (_upload_cloudinary if provider() == "cloudinary" else _upload_r2)(path, key, on_progress)
    if not url.startswith("https://"):
        raise RuntimeError(f"URL video harus HTTPS agar diterima Buffer: {url}")
    # Pastikan benar-benar bisa diakses publik sebelum dikirim ke Buffer.
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        head = client.head(url)
    if head.status_code != 200:
        raise RuntimeError(f"Video sudah terunggah tapi URL-nya tidak bisa diakses publik (HTTP {head.status_code}): {url}")
    return url
