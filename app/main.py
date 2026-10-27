"""Server lokal: REST API + WebSocket realtime + antarmuka web."""
from __future__ import annotations

import asyncio
import contextvars
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
from contextlib import asynccontextmanager

from dotenv import load_dotenv, set_key
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import anthropic
import openai
from google.genai import errors as genai_errors
from pydantic import BaseModel
from starlette.background import BackgroundTask

from . import analysis, branding, buffer, db, facetrack, media, mediahost, pipeline, pricing, ratelimit, security, system, transcribe
from .jobs import hub, store

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
load_dotenv(ENV_FILE)
PUBLIC_MODE = os.environ.get("PUBLIC_MODE", "false").strip().lower() in ("1", "true", "yes", "on")
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true" if PUBLIC_MODE else "true").strip().lower() in ("1", "true", "yes", "on")
JOB_RATE_LIMIT = max(1, int(os.environ.get("JOB_RATE_LIMIT", "5")))
JOB_RATE_WINDOW_SECONDS = max(1, int(os.environ.get("JOB_RATE_WINDOW_SECONDS", "3600")))
job_rate_limiter = ratelimit.JobRateLimiter(JOB_RATE_LIMIT, JOB_RATE_WINDOW_SECONDS)
SESSION_COOKIE = security.SESSION_COOKIE
USER_TOKEN_COOKIE = security.USER_TOKEN_COOKIE
AI_CREDS_COOKIE = security.AI_CREDS_COOKIE
MEDIA_CREDS_COOKIE = security.MEDIA_CREDS_COOKIE
CURRENT_SESSION: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_session", default=None)
CURRENT_USER: contextvars.ContextVar[dict | None] = contextvars.ContextVar("current_user", default=None)

PURGE_INTERVAL_SECONDS: int = int(os.environ.get("PURGE_INTERVAL_SECONDS", "1800"))


async def _retention_purge_loop(stop_event: asyncio.Event) -> None:
    """Asyncio task berkala yang memindai dan menghapus folder proyek yang melewati masa retensi."""
    while not stop_event.is_set():
        try:
            await store.purge_expired()
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=PURGE_INTERVAL_SECONDS)
            break
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inisialisasi database MySQL untuk manajemen akun pengguna
    db.init_db()
    stop_event = asyncio.Event()
    purge_task = asyncio.create_task(_retention_purge_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        purge_task.cancel()
        try:
            await purge_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Clipping Studio", lifespan=lifespan)
tasks: set[asyncio.Task] = set()


def spawn(coro) -> None:
    t = asyncio.create_task(coro)
    tasks.add(t)
    t.add_done_callback(tasks.discard)


def current_session_id() -> str | None:
    return CURRENT_SESSION.get()


def current_user() -> dict | None:
    return CURRENT_USER.get()


def resolve_user_from_request(request: Request) -> dict | None:
    """Ambil data pengguna dari header Authorization (Bearer), X-Auth-Token, atau cookie terenkripsi."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.headers.get("X-Auth-Token", "").strip() or None
    if not token:
        raw_cookie = request.cookies.get(USER_TOKEN_COOKIE)
        if raw_cookie:
            dec = security.decrypt_cookie_data(raw_cookie)
            token = dec if isinstance(dec, str) else None

    if token:
        try:
            return db.get_user_by_token(token)
        except Exception:
            return None
    return None


def valid_session_id(value: str | None) -> str | None:
    try:
        parsed = UUID(value or "")
    except (ValueError, AttributeError):
        return None
    return str(parsed) if parsed.version == 4 else None


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        if client_ip:
            return client_ip
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def get_rate_keys(request: Request) -> list[str]:
    keys = [f"ip:{get_client_ip(request)}"]
    cookie_session = valid_session_id(request.cookies.get(SESSION_COOKIE))
    if cookie_session:
        keys.append(f"sess:{cookie_session}")
    return keys


def owned_jobs(session_id: str | None = None) -> list[dict]:
    jobs = sorted(store.jobs.values(), key=lambda j: j["created_at"], reverse=True)
    if PUBLIC_MODE:
        owner = session_id or current_session_id()
        jobs = [job for job in jobs if job.get("owner_session_id") == owner]
    return jobs


def visible_jobs(session_id: str | None = None) -> list[dict]:
    return [store.public_job(job) for job in owned_jobs(session_id)]


def get_job(job_id: str) -> dict:
    job = store.jobs.get(job_id)
    if not job or (PUBLIC_MODE and job.get("owner_session_id") != current_session_id()):
        raise HTTPException(404, "Job tidak ditemukan")
    return job


# ---------- Kesehatan sistem ----------

@app.get("/api/system/health")
def get_system_health():
    disk = system.disk_info(store.dir(""))
    active_jobs = sum(job.get("status") not in ("done", "error") for job in store.jobs.values())
    active_tasks = sum(not task.done() for task in tasks)
    return {
        "status": system.disk_status(disk["free_gb"]),
        "disk": disk,
        "ffmpeg_installed": bool(media.FFMPEG),
        "active_jobs": active_jobs,
        "active_tasks": active_tasks,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ---------- Pengaturan ----------

class ConfigIn(BaseModel):
    provider: str | None = None
    api_key: str | None = None          # key untuk penyedia di field `provider` (atau yang aktif)
    model: str | None = None            # model untuk penyedia yang sama
    whisper_model: str | None = None
    whisper_language: str | None = None
    buffer_api_key: str | None = None
    media_host: str | None = None
    media: dict[str, str] | None = None  # CLOUDINARY_* / R2_*; secret kosong = tidak diubah
    max_filesize_mb: int | None = None
    max_duration_minutes: int | None = None
    job_retention_hours: int | None = None
    execution_timeout_minutes: int | None = None


def _request_ai_context(provider_name: str | None, key: str | None, model: str | None,
                        *, request: Request | None = None, required: bool = True) -> dict | None:
    secret = (key or "").strip()
    name = (provider_name or "").strip().lower()
    selected_model = (model or "").strip()

    # Ambil kredensial AI dari cookie terenkripsi jika tidak dikirim via header/argumen
    if request and not secret:
        cookie_creds = security.decrypt_cookie_data(request.cookies.get(AI_CREDS_COOKIE))
        if isinstance(cookie_creds, dict):
            cookie_provider = (cookie_creds.get("provider") or "").strip().lower()
            if not name and cookie_provider:
                name = cookie_provider
            target_prov = name or analysis.provider()
            p_data = (cookie_creds.get("providers") or {}).get(target_prov) or {}
            if p_data.get("key"):
                secret = p_data["key"].strip()
            if not selected_model and p_data.get("model"):
                selected_model = p_data["model"].strip()

    if not secret and not name:
        if PUBLIC_MODE and required:
            raise HTTPException(400, "Header X-AI-Key atau cookie kredensial AI wajib diisi dalam PUBLIC_MODE.")
        return None

    if name and name not in analysis.PROVIDERS:
        raise HTTPException(400, "Header X-AI-Provider tidak valid.")

    target = name or analysis.provider()
    if required and not secret and PUBLIC_MODE:
        raise HTTPException(400, "Header X-AI-Key atau cookie kredensial AI wajib diisi dalam PUBLIC_MODE.")

    if not secret:
        secret = os.environ.get(analysis.PROVIDERS[target]["env"], "")
        if required and not secret:
            raise HTTPException(400, f"API key untuk {analysis.PROVIDERS[target]['label']} belum diatur.")

    if not selected_model:
        selected_model = analysis.PROVIDERS[target]["default_model"]
    return {"provider": target, "key": secret, "model": selected_model}


def _hint(env: str) -> str:
    value = os.environ.get(env, "")
    return f"…{value[-4:]}" if value else ""


def _set_env(name: str, value: str) -> None:
    os.environ[name] = value
    set_key(str(ENV_FILE), name, value)


def _pricing_info() -> dict:
    cfg = pricing.settings()
    model = analysis.model_name()
    return {"tier": cfg["tier"], "usd_idr": pricing.usd_idr(), "model": model,
            "price": pricing.price_for(model), "override": cfg["overrides"].get(model),
            "source_url": pricing.SOURCE_URL}


def _providers() -> dict:
    return {
        name: {
            "label": spec["label"], "video": spec["video"],
            "has_key": False if PUBLIC_MODE else bool(os.environ.get(spec["env"], "").strip()),
            "key_hint": "" if PUBLIC_MODE else _hint(spec["env"]),
            "model": spec["default_model"] if PUBLIC_MODE else analysis.model_name(name),
            "default_model": spec["default_model"],
        }
        for name, spec in analysis.PROVIDERS.items()
    }


@app.get("/api/config")
def get_config():
    current = analysis.provider()
    key = os.environ.get(analysis.PROVIDERS[current]["env"], "")
    if PUBLIC_MODE:
        key = ""
    return {
        "provider": current,
        "public_mode": PUBLIC_MODE,
        "providers": _providers(),
        "has_key": bool(key),
        "key_hint": f"…{key[-4:]}" if key else "",
        "model": analysis.PROVIDERS[current]["default_model"] if PUBLIC_MODE else analysis.model_name(),
        "ffmpeg": media.FFMPEG,
        "subtitles_supported": media.SUBTITLES_SUPPORTED,
        "face_tracking": facetrack.available(),
        "whisper_model": transcribe.model_name(),
        "whisper_models": transcribe.MODELS,
        "whisper_downloaded": {m: transcribe.is_downloaded(m) for m in transcribe.MODELS},
        "whisper_language": transcribe.language(),
        "whisper_languages": transcribe.LANGUAGES,
        "pricing": _pricing_info(),
        "buffer_accounts": buffer.public_accounts(),
        "media_host": "default",
        "server_media_configured": mediahost.server_is_configured(),
        "server_media_provider": mediahost.server_provider(),
        "server_retention_hours": 8,
        "custom_retention_hours": 24,
        "media_missing": [],
        "media": {},
        "aspects": list(media.ASPECTS),
        "max_filesize_mb": security.max_filesize_mb(),
        "max_duration_minutes": security.max_duration_minutes(),
        "job_retention_hours": security.job_retention_hours(),
        "allowed_domains": sorted(security.allowed_domains()),
        "limits": {
            "jobs_per_window": JOB_RATE_LIMIT,
            "window_seconds": JOB_RATE_WINDOW_SECONDS,
            "max_concurrent_jobs": pipeline.MAX_CONCURRENT_JOBS,
            "max_concurrent_renders": pipeline.MAX_CONCURRENT_RENDERS,
            "execution_timeout_minutes": security.execution_timeout_minutes(),
        },
    }


@app.post("/api/config")
def save_config(cfg: ConfigIn):
    ENV_FILE.touch(mode=0o600, exist_ok=True)
    target = cfg.provider if cfg.provider in analysis.PROVIDERS else analysis.provider()
    spec = analysis.PROVIDERS[target]
    if cfg.provider in analysis.PROVIDERS and not PUBLIC_MODE:
        _set_env("AI_PROVIDER", cfg.provider)
    if cfg.api_key is not None and cfg.api_key.strip() and not PUBLIC_MODE:
        _set_env(spec["env"], cfg.api_key.strip())
    if cfg.model and not PUBLIC_MODE:
        _set_env(spec["model_env"], cfg.model.strip())
    for field, env, allowed in (("whisper_model", "WHISPER_MODEL", transcribe.MODELS),
                                ("whisper_language", "WHISPER_LANGUAGE", transcribe.LANGUAGES)):
        value = getattr(cfg, field)
        if value in allowed:
            _set_env(env, value)
    if cfg.buffer_api_key and cfg.buffer_api_key.strip():
        _set_env("BUFFER_API_KEY", cfg.buffer_api_key.strip())
    if cfg.media_host in mediahost.FIELDS:
        _set_env("MEDIA_HOST", cfg.media_host)
    allowed = {f for fields in mediahost.FIELDS.values() for f in fields}
    for name, value in (cfg.media or {}).items():
        value = (value or "").strip()
        # Isian kosong tidak menimpa nilai tersimpan (mencegah kredensial terhapus tanpa sengaja).
        if name in allowed and value:
            _set_env(name, value)
    if cfg.max_filesize_mb is not None and cfg.max_filesize_mb > 0:
        _set_env("MAX_FILESIZE_MB", str(cfg.max_filesize_mb))
    if cfg.max_duration_minutes is not None and cfg.max_duration_minutes > 0:
        _set_env("MAX_DURATION_MINUTES", str(cfg.max_duration_minutes))
    if cfg.job_retention_hours is not None and cfg.job_retention_hours > 0:
        _set_env("JOB_RETENTION_HOURS", str(cfg.job_retention_hours))
    if cfg.execution_timeout_minutes is not None and cfg.execution_timeout_minutes > 0:
        _set_env("EXECUTION_TIMEOUT_MINUTES", str(cfg.execution_timeout_minutes))
    return get_config()


@app.get("/api/models")
async def models(request: Request, provider: str | None = None, x_ai_provider: str | None = Header(None),
                 x_ai_key: str | None = Header(None), x_ai_model: str | None = Header(None)):
    context = _request_ai_context(x_ai_provider or provider, x_ai_key, x_ai_model, request=request)
    name = context["provider"] if context else provider if provider in analysis.PROVIDERS else analysis.provider()
    try:
        key = context["key"] if context else None
        return {"provider": name, "models": await asyncio.to_thread(analysis.list_models, name, key)}
    except genai_errors.APIError as e:
        raise HTTPException(400, f"Gemini API ({e.code}): {e.message}")
    except (anthropic.APIStatusError, openai.APIStatusError) as e:
        raise HTTPException(400, f"{analysis.PROVIDERS[name]['label']} menolak: {getattr(e, 'message', e)}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Tidak bisa terhubung ke Gemini API: {e}")


# ---------- Job ----------

@app.get("/api/jobs")
def list_jobs():
    return visible_jobs()


@app.post("/api/jobs")
async def create_job(
    request: Request,
    file: UploadFile | None = File(None),
    url: str = Form(""),
    options: str = Form("{}"),
    x_ai_provider: str | None = Header(None),
    x_ai_key: str | None = Header(None),
    x_ai_model: str | None = Header(None),
):
    if RATE_LIMIT_ENABLED or PUBLIC_MODE:
        rate_keys = get_rate_keys(request)
        allowed, retry_after = job_rate_limiter.allow(*rate_keys)
        if not allowed:
            raise HTTPException(
                429,
                f"Batas pembuatan proyek tercapai ({JOB_RATE_LIMIT} per jam). Coba lagi nanti.",
                headers={"Retry-After": str(retry_after)},
            )
    raw = json.loads(options or "{}")
    has_custom_media = bool(raw.get("has_custom_media", False))
    if not has_custom_media:
        cookie_media = security.decrypt_cookie_data(request.cookies.get(MEDIA_CREDS_COOKIE))
        if isinstance(cookie_media, dict) and cookie_media.get("host") in ("cloudinary", "r2"):
            has_custom_media = True
    retention_hours = 24 if has_custom_media else 8
    opts = {
        "num_clips": max(1, min(15, int(raw.get("num_clips", 3)))),
        "min_len": max(5, int(raw.get("min_len", 30))),
        "max_len": max(10, int(raw.get("max_len", 90))),
        "aspect": raw.get("aspect") if raw.get("aspect") in media.ASPECTS else "9:16",
        "layout": raw.get("layout") if raw.get("layout") in ("face", "crop", "blur") else "face",
        "subtitles": bool(raw.get("subtitles", True)),
        "remove_silence": bool(raw.get("remove_silence", True)),
        "show_title": bool(raw.get("show_title", True)),
        # Logo: None = pakai default, "" = tanpa logo, selain itu id logo dari pustaka.
        "logo_id": raw["logo_id"] if isinstance(raw.get("logo_id"), str) else None,
        # Bumper: None = pakai default, "" = tanpa bumper, selain itu id dari pustaka.
        "intro_id": raw["intro_id"] if isinstance(raw.get("intro_id"), str) else None,
        "outro_id": raw["outro_id"] if isinstance(raw.get("outro_id"), str) else None,
        # Channel tujuan posting, dipilih sebelum render: ["idAkun:idChannel", ...]
        "channels": [c for c in (raw.get("channels") or []) if isinstance(c, str)][:20],
        "instructions": str(raw.get("instructions", ""))[:1000],
        "retention_hours": retention_hours,
    }
    opts["max_len"] = max(opts["max_len"], opts["min_len"] + 5)
    url = url.strip()

    if file and file.filename:
        ext = (Path(file.filename).suffix or "").lower()
        if ext not in security.ALLOWED_VIDEO_EXTENSIONS:
            raise HTTPException(
                400,
                f"Format file '{ext or 'unknown'}' tidak didukung. "
                f"Gunakan kontainer video yang diizinkan: {', '.join(sorted(security.ALLOWED_VIDEO_EXTENSIONS))}."
            )

        tmp_dir = store.DATA_DIR / ".tmp_uploads"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"upload_{uuid4().hex}{ext}"

        max_bytes = security.max_filesize_bytes()
        total_bytes = 0
        first_chunk = True

        try:
            with tmp_path.open("wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    if first_chunk:
                        first_chunk = False
                        mime = security.detect_video_mime(chunk)
                        if not mime:
                            raise HTTPException(
                                400,
                                "Berkas bukan format video yang valid (header berkas/magic bytes tidak valid). "
                                "Hanya MP4, WebM, QuickTime (MOV), dan Matroska (MKV) yang diizinkan."
                            )
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise HTTPException(
                            400,
                            f"Ukuran berkas melebihi batas maksimum ({security.max_filesize_mb()} MB)."
                        )
                    out.write(chunk)

            if total_bytes == 0:
                raise HTTPException(400, "Berkas video kosong.")

            safe_filename = Path(file.filename).name
            ai_context = _request_ai_context(x_ai_provider, x_ai_key, x_ai_model, request=request)
            job = store.create(safe_filename, "upload", opts)
            if PUBLIC_MODE:
                job["owner_session_id"] = current_session_id()
            if ai_context:
                job["_ai_context"] = ai_context
            dest = store.dir(job["id"]) / f"source{ext}"
            shutil.move(str(tmp_path), str(dest))
            await store.publish(job)
            spawn(pipeline.run(job, dest, None))
        finally:
            tmp_path.unlink(missing_ok=True)
    elif url:
        try:
            security.validate_video_url(url)
        except security.SecurityValidationError as e:
            raise HTTPException(400, str(e))
        ai_context = _request_ai_context(x_ai_provider, x_ai_key, x_ai_model, request=request)
        job = store.create(url, "url", opts)
        if PUBLIC_MODE:
            job["owner_session_id"] = current_session_id()
        if ai_context:
            job["_ai_context"] = ai_context
        await store.publish(job)
        spawn(pipeline.run(job, None, url))
    else:
        raise HTTPException(400, "Pilih file video atau masukkan link yang valid.")
    return store.public_job(job)


class RerenderIn(BaseModel):
    aspect: str
    layout: str
    subtitles: bool
    remove_silence: bool = True
    show_title: bool = True
    logo_id: str | None = None
    intro_id: str | None = None
    outro_id: str | None = None
    channels: list[str] | None = None


@app.post("/api/jobs/{job_id}/rerender")
async def rerender_all(job_id: str, body: RerenderIn):
    job = get_job(job_id)
    if not job.get("meta"):
        raise HTTPException(400, "Video sumber belum siap.")
    if body.aspect not in media.ASPECTS or body.layout not in ("face", "crop", "blur"):
        raise HTTPException(400, "Opsi tidak valid.")
    if any(c["status"] in ("queued", "rendering") for c in job["clips"]):
        raise HTTPException(409, "Tunggu sampai semua klip selesai dirender.")
    job["options"].update(aspect=body.aspect, layout=body.layout, subtitles=body.subtitles,
                          remove_silence=body.remove_silence, show_title=body.show_title,
                          logo_id=body.logo_id, intro_id=body.intro_id, outro_id=body.outro_id)
    if body.channels is not None:
        job["options"]["channels"] = body.channels[:20]
    job["status"] = "rendering"
    job["stage"] = "Menunggu antrean..."
    for clip in job["clips"]:
        clip.update(status="queued", stage="Menunggu antrean...", progress=0.0, error=None)
    await store.publish(job)
    for clip in job["clips"]:
        spawn(pipeline.render(job, clip))
    return job


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    get_job(job_id)
    await store.delete(job_id)
    return {"ok": True}


# ---------- Klip ----------

class ClipIn(BaseModel):
    start: float
    end: float
    title: str | None = None


def _check_range(job: dict, body: ClipIn) -> None:
    if not job.get("meta"):
        raise HTTPException(400, "Video sumber belum siap.")
    if body.start < 0 or body.end > job["meta"]["duration"] + 0.5 or body.end - body.start < 1:
        raise HTTPException(400, "Rentang waktu tidak valid (minimal 1 detik, di dalam durasi video).")


@app.post("/api/jobs/{job_id}/clips")
async def add_clip(job_id: str, body: ClipIn):
    job = get_job(job_id)
    _check_range(job, body)
    clip = pipeline.new_clip(job, round(body.start, 2), round(body.end, 2),
                             body.title or f"Klip manual {len(job['clips']) + 1}",
                             status="queued", stage="Menunggu antrean...")
    await store.publish(job)
    spawn(pipeline.render(job, clip))
    return clip


@app.patch("/api/jobs/{job_id}/clips/{clip_id}")
async def update_clip(job_id: str, clip_id: str, body: ClipIn):
    job = get_job(job_id)
    clip = store.clip(job, clip_id)
    if not clip:
        raise HTTPException(404, "Klip tidak ditemukan")
    if clip["status"] in ("queued", "rendering"):
        raise HTTPException(409, "Klip sedang dirender.")
    _check_range(job, body)
    clip.update(start=round(body.start, 2), end=round(body.end, 2),
                status="queued", stage="Menunggu antrean...", progress=0.0, error=None)
    if body.title:
        clip["title"] = body.title
    await store.publish(job)
    spawn(pipeline.render(job, clip))
    return clip


@app.delete("/api/jobs/{job_id}/clips/{clip_id}")
async def delete_clip(job_id: str, clip_id: str):
    job = get_job(job_id)
    clip = store.clip(job, clip_id)
    if not clip:
        raise HTTPException(404, "Klip tidak ditemukan")
    if clip["status"] in ("queued", "rendering"):
        raise HTTPException(409, "Klip sedang dirender.")
    for key in ("file", "srt", "vtt"):
        if clip.get(key):
            (store.dir(job_id) / clip[key]).unlink(missing_ok=True)
    job["clips"].remove(clip)
    await store.publish(job)
    return {"ok": True}


# ---------- Logo & penutup (branding) ----------

class LogoIn(BaseModel):
    label: str | None = None
    position: str | None = None
    size: float | None = None
    opacity: float | None = None
    margin: float | None = None


class OutroIn(BaseModel):
    enabled: bool | None = None
    duration: float | None = None
    keep_audio: bool | None = None


class DefaultLogoIn(BaseModel):
    logo_id: str | None = None


@app.get("/api/branding")
def get_branding():
    return branding.public()


async def _save_upload(file: UploadFile, name: str, is_image_only: bool = False) -> Path:
    ext = (Path(file.filename or "").suffix or "").lower()
    if is_image_only:
        if ext not in branding.IMAGE_EXT:
            raise HTTPException(400, f"Format {ext or '?'} tidak didukung untuk logo. Pakai: {', '.join(sorted(branding.IMAGE_EXT))}")
        max_bytes = 20 * 1024 * 1024  # Maksimal 20 MB untuk logo
    else:
        if ext not in branding.IMAGE_EXT | branding.VIDEO_EXT:
            raise HTTPException(400, f"Format {ext or '?'} tidak didukung. Pakai: {', '.join(sorted(branding.IMAGE_EXT | branding.VIDEO_EXT))}")
        max_bytes = security.max_filesize_bytes() if ext in branding.VIDEO_EXT else 20 * 1024 * 1024

    tmp = branding.DIR.parent / f".upload-{name}-{uuid4().hex[:8]}{ext}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    first_chunk = True

    try:
        with tmp.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                if first_chunk:
                    first_chunk = False
                    if ext in branding.IMAGE_EXT:
                        if not security.detect_image_mime(chunk):
                            raise HTTPException(400, "Berkas bukan format gambar yang valid.")
                    elif ext in branding.VIDEO_EXT:
                        if not security.detect_video_mime(chunk):
                            raise HTTPException(400, "Berkas bukan format video yang valid.")
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(400, "Ukuran berkas melebihi batas maksimum.")
                out.write(chunk)
        if total_bytes == 0:
            raise HTTPException(400, "Berkas kosong.")
        return tmp
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


@app.post("/api/branding/logos")
async def add_logo(file: UploadFile = File(...), label: str = Form("")):
    tmp = await _save_upload(file, "logo", is_image_only=True)
    try:
        added = await asyncio.to_thread(branding.add_logo, tmp, file.filename or "", label)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        tmp.unlink(missing_ok=True)
    return {"added": added, **branding.public()}


@app.patch("/api/branding/logos/{logo_id}")
def update_logo(logo_id: str, body: LogoIn):
    try:
        branding.update_logo(logo_id, **body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return branding.public()


@app.delete("/api/branding/logos/{logo_id}")
def delete_logo(logo_id: str):
    try:
        branding.remove_logo(logo_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return branding.public()


@app.post("/api/branding/default-logo")
def default_logo(body: DefaultLogoIn):
    try:
        branding.set_default_logo(body.logo_id or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return branding.public()


class BumperIn(BaseModel):
    label: str | None = None
    duration: float | None = None
    keep_audio: bool | None = None


class DefaultBumperIn(BaseModel):
    role: str
    bumper_id: str | None = None


@app.post("/api/branding/bumpers")
async def add_bumper(file: UploadFile = File(...), label: str = Form("")):
    tmp = await _save_upload(file, "bumper", is_image_only=False)
    try:
        added = await asyncio.to_thread(branding.add_bumper, tmp, file.filename or "", label)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        tmp.unlink(missing_ok=True)
    return {"added": added, **branding.public()}


@app.patch("/api/branding/bumpers/{bumper_id}")
def update_bumper(bumper_id: str, body: BumperIn):
    try:
        branding.update_bumper(bumper_id, **body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return branding.public()


@app.delete("/api/branding/bumpers/{bumper_id}")
def delete_bumper(bumper_id: str):
    try:
        branding.remove_bumper(bumper_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return branding.public()


@app.post("/api/branding/default-bumper")
def default_bumper(body: DefaultBumperIn):
    try:
        branding.set_default_bumper(body.role, body.bumper_id or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return branding.public()


@app.get("/branding/{path:path}")
def branding_file(path: str):
    target = (branding.DIR / path).resolve()
    if branding.DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)


# ---------- Pemakaian & biaya AI ----------

class PricingIn(BaseModel):
    tier: str | None = None
    usd_idr: float | None = None
    input: float | None = None   # harga manual USD/1 juta token untuk model aktif; kosong = pakai default
    audio: float | None = None
    output: float | None = None
    clear_override: bool = False


@app.post("/api/pricing")
def save_pricing(body: PricingIn):
    overrides = dict(pricing.settings()["overrides"])
    model = analysis.model_name()
    if body.clear_override:
        overrides.pop(model, None)
    elif body.input is not None and body.output is not None:
        if body.input < 0 or body.output < 0 or (body.audio is not None and body.audio < 0):
            raise HTTPException(400, "Harga tidak boleh negatif.")
        overrides[model] = {"input": body.input, "output": body.output, "audio": body.audio}
    pricing.save_settings(body.tier, body.usd_idr, overrides)
    return _pricing_info()


@app.get("/api/estimate")
def estimate(request: Request, duration: float, num_clips: int = 3, max_len: int = 90, subtitles: bool = True,
             x_ai_provider: str | None = Header(None), x_ai_key: str | None = Header(None),
             x_ai_model: str | None = Header(None)):
    context = _request_ai_context(x_ai_provider, x_ai_key, x_ai_model, request=request, required=False)
    provider = context["provider"] if context else analysis.provider()
    model = context["model"] if context else analysis.model_name()
    est = pricing.estimate(max(0.0, duration), model, num_clips, max_len, subtitles, provider)
    return {**est, "model": model, "provider": provider,
            "provider_label": analysis.PROVIDERS[provider]["label"], "usd_idr": pricing.usd_idr()}


@app.get("/api/usage")
def usage():
    now = datetime.now()
    month_start = datetime(now.year, now.month, 1).timestamp()
    empty = lambda: {"calls": 0, "prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0,  # noqa: E731
                     "usd": 0.0, "unpriced": 0}

    def add(bucket: dict, e: dict) -> None:
        bucket["calls"] += 1
        bucket["prompt_tokens"] += e["prompt_tokens"]
        bucket["output_tokens"] += e["output_tokens"] + e.get("thoughts_tokens", 0)
        bucket["total_tokens"] += e["prompt_tokens"] + e["output_tokens"] + e.get("thoughts_tokens", 0)
        if e.get("cost_usd") is None:
            bucket["unpriced"] += 1
        else:
            bucket["usd"] += e["cost_usd"]

    total, month, per_model, per_day, projects = empty(), empty(), {}, {}, []
    for job in owned_jobs():
        entries = job.get("usage") or []
        proj = {"id": job["id"], "name": job["name"], "created_at": job["created_at"],
                "clips": len(job["clips"]), "video_seconds": (job.get("meta") or {}).get("duration"),
                "tracked": bool(entries), **empty()}
        for e in entries:
            for bucket in (total, proj, per_model.setdefault(e["model"], empty()),
                           per_day.setdefault(datetime.fromtimestamp(e["t"]).date().isoformat(), empty())):
                add(bucket, e)
            if e["t"] >= month_start:
                add(month, e)
        projects.append(proj)
    projects.sort(key=lambda p: p["created_at"], reverse=True)
    return {"total": total, "month": month, "per_model": per_model,
            "per_day": dict(sorted(per_day.items())[-30:]), "projects": projects,
            "untracked_projects": sum(1 for p in projects if not p["tracked"]),
            "pricing": _pricing_info()}


@app.post("/api/usage/recalculate")
async def recalculate_usage():
    """Hitung ulang biaya semua catatan dengan pengaturan harga saat ini (tier/harga manual)."""
    count = 0
    for job in owned_jobs():
        if job.get("usage"):
            job["usage"] = [pricing.with_cost(e) for e in job["usage"]]
            count += len(job["usage"])
            await store.publish(job)
    return {"recalculated": count, **usage()}


# ---------- Posting ke media sosial (Buffer) ----------

@app.get("/api/buffer/channels")
async def buffer_channels(refresh: bool = False, account_id: str | None = None):
    try:
        channels, errors = await asyncio.to_thread(buffer.channels_and_errors, refresh, account_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    return {"channels": channels, "errors": errors, "accounts": buffer.public_accounts()}


class AccountIn(BaseModel):
    label: str | None = None
    api_key: str | None = None


@app.get("/api/buffer/accounts")
def buffer_accounts():
    return {"accounts": buffer.public_accounts()}


@app.post("/api/buffer/accounts")
async def add_buffer_account(body: AccountIn):
    try:
        added = await asyncio.to_thread(buffer.add_account, body.label or "", body.api_key or "")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    return {"added": added, "accounts": buffer.public_accounts()}


@app.patch("/api/buffer/accounts/{account_id}")
def rename_buffer_account(account_id: str, body: AccountIn):
    try:
        buffer.rename_account(account_id, body.label or "")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    return {"accounts": buffer.public_accounts()}


@app.delete("/api/buffer/accounts/{account_id}")
def delete_buffer_account(account_id: str):
    try:
        from_env = buffer.remove_account(account_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    if from_env:
        _set_env("BUFFER_API_KEY", "")  # supaya tidak muncul lagi dari .env
    return {"accounts": buffer.public_accounts()}


class MediaHostTestIn(BaseModel):
    provider: str = "default"
    credentials: dict[str, str] = {}


@app.post("/api/mediahost/test")
async def test_mediahost(request: Request, body: MediaHostTestIn | None = None):
    try:
        p = body.provider if body else "default"
        creds = body.credentials if body else {}
        if not creds and p in ("cloudinary", "r2"):
            cookie_creds = security.decrypt_cookie_data(request.cookies.get(MEDIA_CREDS_COOKIE))
            if isinstance(cookie_creds, dict):
                creds = cookie_creds.get(p) or {}
        return {"ok": True, "message": await asyncio.to_thread(mediahost.check_context, p, creds)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


class PublishIn(BaseModel):
    channel_ids: list[str] = []
    text: str
    mode: str = "addToQueue"
    due_at: str | None = None
    media_host: str | None = None
    media_credentials: dict[str, str] | None = None


@app.post("/api/jobs/{job_id}/clips/{clip_id}/publish")
async def publish_clip(request: Request, job_id: str, clip_id: str, body: PublishIn):
    job = get_job(job_id)
    clip = store.clip(job, clip_id)
    if not clip or clip["status"] != "ready":
        raise HTTPException(400, "Klip belum siap. Tunggu render selesai.")
    if (clip.get("publish") or {}).get("status") in ("uploading", "posting"):
        raise HTTPException(409, "Klip ini sedang diposting.")
    # Kosong = pakai tujuan yang sudah dipilih sebelum render.
    channel_ids = body.channel_ids or pipeline.target_channels(job)
    if not channel_ids:
        raise HTTPException(400, "Pilih minimal satu channel.")
    if body.mode not in ("addToQueue", "shareNow", "shareNext", "customScheduled"):
        raise HTTPException(400, "Mode posting tidak valid.")
    due_at = None
    if body.mode == "customScheduled":
        try:
            when = datetime.fromisoformat((body.due_at or "").replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Waktu jadwal tidak valid.")
        if when.tzinfo is None or when <= datetime.now(timezone.utc):
            raise HTTPException(400, "Waktu jadwal harus di masa depan.")
        due_at = when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    media_provider = (body.media_host or "default").strip().lower()
    media_creds = body.media_credentials or {}
    if not media_creds and media_provider in ("cloudinary", "r2"):
        cookie_creds = security.decrypt_cookie_data(request.cookies.get(MEDIA_CREDS_COOKIE))
        if isinstance(cookie_creds, dict):
            media_creds = cookie_creds.get(media_provider) or {}
    if media_provider == "default":
        if not mediahost.server_is_configured():
            raise HTTPException(400, "Server default belum mengonfigurasi hosting video di .env. Hubungkan Cloudinary atau R2 pribadi Anda di Pengaturan.")
    elif media_provider == "cloudinary":
        cloud = (media_creds.get("cloud_name") or media_creds.get("CLOUDINARY_CLOUD_NAME") or "").strip()
        key = (media_creds.get("api_key") or media_creds.get("CLOUDINARY_API_KEY") or "").strip()
        sec = (media_creds.get("api_secret") or media_creds.get("CLOUDINARY_API_SECRET") or "").strip()
        if not (cloud and key and sec):
            raise HTTPException(400, "Kredensial Cloudinary pribadi belum lengkap. Buka Pengaturan.")
    elif media_provider == "r2":
        acc = (media_creds.get("account_id") or media_creds.get("R2_ACCOUNT_ID") or "").strip()
        key = (media_creds.get("access_key_id") or media_creds.get("R2_ACCESS_KEY_ID") or "").strip()
        sec = (media_creds.get("secret_access_key") or media_creds.get("R2_SECRET_ACCESS_KEY") or "").strip()
        bkt = (media_creds.get("bucket") or media_creds.get("R2_BUCKET") or "").strip()
        pub = (media_creds.get("public_url") or media_creds.get("R2_PUBLIC_URL") or "").strip()
        if not (acc and key and sec and bkt and pub):
            raise HTTPException(400, "Kredensial Cloudflare R2 pribadi belum lengkap. Buka Pengaturan.")

    try:
        found = await asyncio.to_thread(buffer.list_channels)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    # Channel dirujuk sebagai "idAkun:idChannel"; id polos tetap diterima kalau tidak ambigu.
    known = {c["key"]: c for c in found}
    known.update({c["id"]: c for c in found if sum(1 for x in found if x["id"] == c["id"]) == 1})
    channels = [known[i] for i in channel_ids if i in known]
    unusable = [c for c in channels if c["isDisconnected"] or c["isLocked"]]
    if len(channels) != len(channel_ids) or unusable:
        raise HTTPException(400, "Ada channel yang tidak ditemukan atau sedang terputus di Buffer.")
    spawn(pipeline.publish(job, clip, channels, body.text.strip(), body.mode, due_at,
                           media_context={"provider": media_provider, "credentials": media_creds}))
    return {"ok": True}


@app.post("/api/jobs/{job_id}/clips/{clip_id}/publish/refresh")
async def refresh_publish(job_id: str, clip_id: str):
    job = get_job(job_id)
    clip = store.clip(job, clip_id)
    pub = (clip or {}).get("publish")
    if not pub:
        raise HTTPException(404, "Klip ini belum pernah diposting.")
    # Status ditanyakan ke akun yang memposting masing-masing.
    per_account: dict[str | None, list[str]] = {}
    for r in pub["results"]:
        if r.get("ok"):
            per_account.setdefault(r.get("account_id"), []).append(r["post_id"])
    statuses: dict[str, dict] = {}
    try:
        for account_id, ids in per_account.items():
            statuses.update(await asyncio.to_thread(buffer.post_statuses, ids, account_id))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    for r in pub["results"]:
        st = statuses.get(r.get("post_id"))
        if st:
            r.update(status=st["status"], due_at=st.get("dueAt"), sent_at=st.get("sentAt"),
                     link=st.get("externalLink"), error=(st.get("error") or {}).get("message"))
    await store.publish(job)
    return pub


# ---------- File media (mendukung Range request untuk seek video) ----------

@app.get("/api/jobs/{job_id}/download-all")
def download_all_clips(job_id: str):
    job = get_job(job_id)
    base = store.dir(job["id"]).resolve()
    files: list[Path] = []

    for clip in job.get("clips", []):
        if clip.get("status") != "ready" or not clip.get("file"):
            continue
        for relative in (clip["file"], clip.get("srt")):
            if not relative:
                continue
            target = (base / relative).resolve()
            if base not in target.parents or not target.is_file():
                continue
            if target.suffix.lower() not in (".mp4", ".srt"):
                continue
            files.append(target)

    if not files:
        raise HTTPException(400, "Belum ada klip yang siap diunduh")

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", job.get("name") or job["id"]).strip("._")
    safe_name = (safe_name or job["id"])[:80]
    temp = tempfile.NamedTemporaryFile(prefix=f"clips_{safe_name}_", suffix=".zip", delete=False)
    temp_path = Path(temp.name)
    temp.close()
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, arcname=path.name)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return FileResponse(
        temp_path,
        media_type="application/zip",
        filename=f"clips_{safe_name}.zip",
        background=BackgroundTask(temp_path.unlink, missing_ok=True),
    )

@app.get("/media/{job_id}/{path:path}")
def media_file(job_id: str, path: str, download: bool = False):
    base = store.dir(get_job(job_id)["id"]).resolve()
    target = (base / path).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, filename=target.name if download else None)


# ---------- Autentikasi Pengguna & Token Kredensial ----------

class RegisterBody(BaseModel):
    username: str
    email: str
    password: str


class LoginBody(BaseModel):
    username_or_email: str
    password: str


class CustomTokenBody(BaseModel):
    token: str


@app.post("/api/auth/register")
def auth_register(req: RegisterBody, request: Request, response: Response):
    try:
        user = db.register_user(req.username, req.email, req.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Gagal mendaftarkan pengguna: {e}")

    security.set_secure_cookie(
        response,
        USER_TOKEN_COOKIE,
        user["token_credential"],
        request=request,
    )
    return {"ok": True, "user": user}


@app.post("/api/auth/login")
def auth_login(req: LoginBody, request: Request, response: Response):
    try:
        user = db.authenticate_user(req.username_or_email, req.password)
    except Exception as e:
        raise HTTPException(500, f"Gagal memproses autentikasi: {e}")

    if not user:
        raise HTTPException(401, "Username/email atau kata sandi tidak valid.")

    security.set_secure_cookie(
        response,
        USER_TOKEN_COOKIE,
        user["token_credential"],
        request=request,
    )
    return {"ok": True, "user": user}


@app.get("/api/auth/me")
def auth_me(request: Request):
    user = CURRENT_USER.get() or resolve_user_from_request(request)
    return {"ok": True, "user": user}


@app.post("/api/auth/token/regenerate")
def auth_regenerate_token(request: Request, response: Response):
    user = CURRENT_USER.get() or resolve_user_from_request(request)
    if not user:
        raise HTTPException(401, "Silakan masuk terlebih dahulu.")
    try:
        new_token = db.regenerate_token(user["id"])
    except Exception as e:
        raise HTTPException(500, f"Gagal membuat token baru: {e}")

    security.set_secure_cookie(
        response,
        USER_TOKEN_COOKIE,
        new_token,
        request=request,
    )
    return {"ok": True, "token_credential": new_token}


@app.patch("/api/auth/token")
def auth_update_custom_token(req: CustomTokenBody, request: Request, response: Response):
    user = CURRENT_USER.get() or resolve_user_from_request(request)
    if not user:
        raise HTTPException(401, "Silakan masuk terlebih dahulu.")
    try:
        updated_token = db.update_custom_token(user["id"], req.token)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Gagal memperbarui token: {e}")

    security.set_secure_cookie(
        response,
        USER_TOKEN_COOKIE,
        updated_token,
        request=request,
    )
    return {"ok": True, "token_credential": updated_token}


@app.post("/api/auth/logout")
def auth_logout(response: Response):
    security.clear_secure_cookie(response, USER_TOKEN_COOKIE)
    return {"ok": True}


# ---------- Kredensial AI & Media BYOK Terenkripsi (HttpOnly, Secure, SameSite) ----------

class AiCredentialsIn(BaseModel):
    provider: str
    key: str | None = None
    model: str | None = None


def _summarize_ai_credentials(creds: dict) -> dict:
    current_prov = creds.get("provider") or analysis.provider()
    result = {
        "ok": True,
        "provider": current_prov,
        "providers": {},
    }
    for prov_name, prov_spec in analysis.PROVIDERS.items():
        prov_data = (creds.get("providers") or {}).get(prov_name) or {}
        key = prov_data.get("key", "")
        server_env_key = os.environ.get(prov_spec["env"], "") if not PUBLIC_MODE else ""
        has_key = bool(key or server_env_key)
        hint = f"…{key[-4:]}" if key else (f"…{server_env_key[-4:]}" if server_env_key else "")
        result["providers"][prov_name] = {
            "has_key": has_key,
            "key_hint": hint,
            "model": prov_data.get("model", prov_spec["default_model"]),
            "is_custom": bool(key),
        }
    return result


@app.get("/api/credentials/ai")
def get_ai_credentials(request: Request):
    """Ambil status dan hint kredensial AI dari cookie terenkripsi tanpa membocorkan secret key."""
    creds = security.decrypt_cookie_data(request.cookies.get(AI_CREDS_COOKIE))
    if not isinstance(creds, dict):
        creds = {"provider": analysis.provider(), "providers": {}}
    return _summarize_ai_credentials(creds)


@app.post("/api/credentials/ai")
def set_ai_credentials(body: AiCredentialsIn, request: Request, response: Response):
    """Simpan kredensial AI ke dalam cookie HttpOnly terenkripsi AES-256."""
    target_prov = (body.provider or "").strip().lower()
    if target_prov not in analysis.PROVIDERS:
        raise HTTPException(400, "Penyedia AI tidak valid.")

    creds = security.decrypt_cookie_data(request.cookies.get(AI_CREDS_COOKIE))
    if not isinstance(creds, dict):
        creds = {"provider": target_prov, "providers": {}}

    creds["provider"] = target_prov
    prov_map = creds.setdefault("providers", {})
    existing_p = prov_map.setdefault(target_prov, {})

    new_key = (body.key or "").strip()
    if new_key:
        existing_p["key"] = new_key
    if body.model:
        existing_p["model"] = body.model.strip()

    security.set_secure_cookie(response, AI_CREDS_COOKIE, creds, request=request)
    return _summarize_ai_credentials(creds)


@app.delete("/api/credentials/ai")
def clear_ai_credentials(request: Request, response: Response, provider: str | None = None):
    """Hapus kredensial AI dari cookie terenkripsi."""
    if not provider:
        security.clear_secure_cookie(response, AI_CREDS_COOKIE)
        return {"ok": True}

    target = provider.strip().lower()
    creds = security.decrypt_cookie_data(request.cookies.get(AI_CREDS_COOKIE))
    if isinstance(creds, dict) and "providers" in creds:
        creds["providers"].pop(target, None)
        security.set_secure_cookie(response, AI_CREDS_COOKIE, creds, request=request)
    return {"ok": True}


class MediaCredentialsIn(BaseModel):
    host: str
    credentials: dict[str, str] = {}


def _summarize_media_credentials(creds: dict) -> dict:
    c = creds.get("cloudinary") or {}
    r = creds.get("r2") or {}
    active_host = creds.get("host", "default")

    return {
        "ok": True,
        "host": active_host,
        "configured": {
            "default": mediahost.server_is_configured(),
            "cloudinary": bool(c.get("cloud_name") and c.get("api_key") and c.get("api_secret")),
            "r2": bool(r.get("account_id") and r.get("bucket") and r.get("access_key_id") and r.get("secret_access_key")),
        },
        "fields": {
            "cloudinary": {
                "cloud_name": c.get("cloud_name", ""),
                "api_key": c.get("api_key", ""),
                "has_secret": bool(c.get("api_secret")),
            },
            "r2": {
                "account_id": r.get("account_id", ""),
                "bucket": r.get("bucket", ""),
                "access_key_id": r.get("access_key_id", ""),
                "public_url": r.get("public_url", ""),
                "has_secret": bool(r.get("secret_access_key")),
            },
        },
    }


@app.get("/api/credentials/media")
def get_media_credentials(request: Request):
    """Ambil status hosting media kustom dari cookie terenkripsi tanpa mengekspos secret."""
    creds = security.decrypt_cookie_data(request.cookies.get(MEDIA_CREDS_COOKIE))
    if not isinstance(creds, dict):
        creds = {"host": "default", "cloudinary": {}, "r2": {}}
    return _summarize_media_credentials(creds)


@app.post("/api/credentials/media")
def set_media_credentials(body: MediaCredentialsIn, request: Request, response: Response):
    """Simpan pengaturan hosting media kustom ke dalam cookie HttpOnly terenkripsi AES-256."""
    host = body.host.strip().lower()
    if host not in ("default", "cloudinary", "r2"):
        raise HTTPException(400, "Media host tidak valid.")

    creds = security.decrypt_cookie_data(request.cookies.get(MEDIA_CREDS_COOKIE))
    if not isinstance(creds, dict):
        creds = {"host": host, "cloudinary": {}, "r2": {}}

    creds["host"] = host
    if host in ("cloudinary", "r2"):
        target_dict = creds.setdefault(host, {})
        for k, v in body.credentials.items():
            val = (v or "").strip()
            # Pertahankan secret lama jika tidak diubah / dikosongkan
            if k in ("api_secret", "secret_access_key") and not val:
                continue
            target_dict[k] = val

    security.set_secure_cookie(response, MEDIA_CREDS_COOKIE, creds, request=request)
    return _summarize_media_credentials(creds)


@app.delete("/api/credentials/media")
def clear_media_credentials(response: Response):
    """Hapus cookie kredensial hosting media kustom."""
    security.clear_secure_cookie(response, MEDIA_CREDS_COOKIE)
    return {"ok": True}


# ---------- Realtime ----------

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    session_id = valid_session_id(websocket.cookies.get(SESSION_COOKIE))
    if not session_id:
        session_id = str(uuid4())
    await websocket.accept()
    hub.sockets[websocket] = session_id
    try:
        await websocket.send_json({"type": "snapshot", "jobs": visible_jobs(session_id)})
        while True:
            await websocket.receive_text()  # ping dari browser
    except WebSocketDisconnect:
        pass
    finally:
        hub.sockets.pop(websocket, None)


@app.middleware("http")
async def no_stale_ui(request: Request, call_next):
    """Antarmuka selalu divalidasi ulang, supaya versi lama tidak nyangkut di cache browser."""
    session_id = valid_session_id(request.cookies.get(SESSION_COOKIE)) or str(uuid4())
    token_sess = CURRENT_SESSION.set(session_id)
    user = resolve_user_from_request(request)
    token_user = CURRENT_USER.set(user)
    try:
        response = await call_next(request)
    finally:
        CURRENT_SESSION.reset(token_sess)
        CURRENT_USER.reset(token_user)

    if not valid_session_id(request.cookies.get(SESSION_COOKIE)):
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            httponly=True,
            secure=security.is_cookie_secure(request),
            samesite="lax",
            max_age=60 * 60 * 24 * 365,
            path="/",
        )
    if request.url.path.startswith(("/branding/", "/static/")) or request.url.path in ("/", "/app.js", "/style.css", "/index.html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
