"""Server lokal: REST API + WebSocket realtime + antarmuka web."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv, set_key
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import anthropic
import openai
from google.genai import errors as genai_errors
from pydantic import BaseModel

from . import analysis, branding, buffer, facetrack, media, mediahost, pipeline, pricing, transcribe
from .jobs import hub, store

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
load_dotenv(ENV_FILE)

app = FastAPI(title="Clipping Studio")
tasks: set[asyncio.Task] = set()


def spawn(coro) -> None:
    t = asyncio.create_task(coro)
    tasks.add(t)
    t.add_done_callback(tasks.discard)


def get_job(job_id: str) -> dict:
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    return job


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
            "has_key": bool(os.environ.get(spec["env"], "").strip()),
            "key_hint": _hint(spec["env"]), "model": analysis.model_name(name),
            "default_model": spec["default_model"],
        }
        for name, spec in analysis.PROVIDERS.items()
    }


@app.get("/api/config")
def get_config():
    current = analysis.provider()
    key = os.environ.get(analysis.PROVIDERS[current]["env"], "")
    return {
        "provider": current,
        "providers": _providers(),
        "has_key": bool(key),
        "key_hint": f"…{key[-4:]}" if key else "",
        "model": analysis.model_name(),
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
        "media_host": mediahost.provider(),
        "media_missing": [mediahost.LABELS[f] for f in mediahost.missing()],
        # Nilai non-rahasia dikirim apa adanya; rahasia hanya petunjuk 4 karakter terakhir.
        "media": {f: (_hint(f) if f in mediahost.SECRET_FIELDS else os.environ.get(f, ""))
                  for fields in mediahost.FIELDS.values() for f in fields},
        "aspects": list(media.ASPECTS),
    }


@app.post("/api/config")
def save_config(cfg: ConfigIn):
    ENV_FILE.touch(mode=0o600, exist_ok=True)
    target = cfg.provider if cfg.provider in analysis.PROVIDERS else analysis.provider()
    spec = analysis.PROVIDERS[target]
    if cfg.provider in analysis.PROVIDERS:
        _set_env("AI_PROVIDER", cfg.provider)
    if cfg.api_key is not None and cfg.api_key.strip():
        _set_env(spec["env"], cfg.api_key.strip())
    if cfg.model:
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
    return get_config()


@app.get("/api/models")
async def models(provider: str | None = None):
    name = provider if provider in analysis.PROVIDERS else analysis.provider()
    try:
        return {"provider": name, "models": await asyncio.to_thread(analysis.list_models, name)}
    except genai_errors.APIError as e:
        raise HTTPException(400, f"Gemini API ({e.code}): {e.message}")
    except (anthropic.APIStatusError, openai.APIStatusError) as e:
        raise HTTPException(400, f"{analysis.PROVIDERS[name]['label']} menolak: {getattr(e, 'message', e)}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Tidak bisa terhubung ke Gemini API: {e}")


# ---------- Job ----------

@app.get("/api/jobs")
def list_jobs():
    return sorted(store.jobs.values(), key=lambda j: j["created_at"], reverse=True)


@app.post("/api/jobs")
async def create_job(
    file: UploadFile | None = File(None),
    url: str = Form(""),
    options: str = Form("{}"),
):
    raw = json.loads(options or "{}")
    opts = {
        "num_clips": max(1, min(15, int(raw.get("num_clips", 3)))),
        "min_len": max(5, int(raw.get("min_len", 30))),
        "max_len": max(10, int(raw.get("max_len", 90))),
        "aspect": raw.get("aspect") if raw.get("aspect") in media.ASPECTS else "9:16",
        "layout": raw.get("layout") if raw.get("layout") in ("face", "crop", "blur") else "face",
        "subtitles": bool(raw.get("subtitles", True)),
        "remove_silence": bool(raw.get("remove_silence", True)),
        "show_title": bool(raw.get("show_title", True)),
        "instructions": str(raw.get("instructions", ""))[:1000],
    }
    opts["max_len"] = max(opts["max_len"], opts["min_len"] + 5)
    url = url.strip()

    if file and file.filename:
        job = store.create(file.filename, "upload", opts)
        ext = (Path(file.filename).suffix or ".mp4").lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,5}", ext):
            ext = ".mp4"
        dest = store.dir(job["id"]) / f"source{ext}"
        with dest.open("wb") as out:
            await asyncio.to_thread(shutil.copyfileobj, file.file, out, 4 * 1024 * 1024)
        await store.publish(job)
        spawn(pipeline.run(job, dest, None))
    elif re.match(r"^https?://", url):
        job = store.create(url, "url", opts)
        await store.publish(job)
        spawn(pipeline.run(job, None, url))
    else:
        raise HTTPException(400, "Pilih file video atau masukkan link yang valid.")
    return job


class RerenderIn(BaseModel):
    aspect: str
    layout: str
    subtitles: bool
    remove_silence: bool = True
    show_title: bool = True


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
                          remove_silence=body.remove_silence, show_title=body.show_title)
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
                             body.title or f"Klip manual {len(job['clips']) + 1}")
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
    clip.update(start=round(body.start, 2), end=round(body.end, 2))
    if body.title:
        clip["title"] = body.title
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
    for key in ("file", "srt"):
        if clip.get(key):
            (store.dir(job_id) / clip[key]).unlink(missing_ok=True)
    job["clips"].remove(clip)
    await store.publish(job)
    return {"ok": True}


# ---------- Logo & penutup (branding) ----------

class BrandingIn(BaseModel):
    enabled: bool | None = None
    position: str | None = None
    size: float | None = None
    opacity: float | None = None
    margin: float | None = None
    duration: float | None = None
    keep_audio: bool | None = None


def _check_kind(kind: str) -> None:
    if kind not in ("logo", "outro"):
        raise HTTPException(404, "Bagian tidak dikenal.")


@app.get("/api/branding")
def get_branding():
    return branding.public()


@app.post("/api/branding/{kind}")
async def upload_branding(kind: str, file: UploadFile = File(...)):
    _check_kind(kind)
    tmp = branding.DIR.parent / f".upload-{kind}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tmp.open("wb") as out:
            await asyncio.to_thread(shutil.copyfileobj, file.file, out, 4 * 1024 * 1024)
        await asyncio.to_thread(branding.save_file, kind, tmp, file.filename or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        tmp.unlink(missing_ok=True)
    return branding.public()


@app.patch("/api/branding/{kind}")
def update_branding(kind: str, body: BrandingIn):
    _check_kind(kind)
    try:
        branding.update(kind, **body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return branding.public()


@app.delete("/api/branding/{kind}")
def delete_branding(kind: str):
    _check_kind(kind)
    branding.clear(kind)
    return branding.public()


@app.get("/branding/{name}")
def branding_file(name: str):
    target = (branding.DIR / name).resolve()
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
def estimate(duration: float, num_clips: int = 3, max_len: int = 90, subtitles: bool = True):
    provider = analysis.provider()
    est = pricing.estimate(max(0.0, duration), analysis.model_name(), num_clips, max_len, subtitles, provider)
    return {**est, "model": analysis.model_name(), "provider": provider,
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
    for job in store.jobs.values():
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
    for job in store.jobs.values():
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


@app.post("/api/mediahost/test")
async def test_mediahost():
    try:
        return {"ok": True, "message": await asyncio.to_thread(mediahost.check)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


class PublishIn(BaseModel):
    channel_ids: list[str]
    text: str
    mode: str = "addToQueue"
    due_at: str | None = None


@app.post("/api/jobs/{job_id}/clips/{clip_id}/publish")
async def publish_clip(job_id: str, clip_id: str, body: PublishIn):
    job = get_job(job_id)
    clip = store.clip(job, clip_id)
    if not clip or clip["status"] != "ready":
        raise HTTPException(400, "Klip belum siap. Tunggu render selesai.")
    if (clip.get("publish") or {}).get("status") in ("uploading", "posting"):
        raise HTTPException(409, "Klip ini sedang diposting.")
    if not body.channel_ids:
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
    if mediahost.missing():
        raise HTTPException(400, mediahost.missing_message())
    try:
        found = await asyncio.to_thread(buffer.list_channels)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    # Channel dirujuk sebagai "idAkun:idChannel"; id polos tetap diterima kalau tidak ambigu.
    known = {c["key"]: c for c in found}
    known.update({c["id"]: c for c in found if sum(1 for x in found if x["id"] == c["id"]) == 1})
    channels = [known[i] for i in body.channel_ids if i in known]
    unusable = [c for c in channels if c["isDisconnected"] or c["isLocked"]]
    if len(channels) != len(body.channel_ids) or unusable:
        raise HTTPException(400, "Ada channel yang tidak ditemukan atau sedang terputus di Buffer.")
    spawn(pipeline.publish(job, clip, channels, body.text.strip(), body.mode, due_at))
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

@app.get("/media/{job_id}/{path:path}")
def media_file(job_id: str, path: str, download: bool = False):
    base = store.dir(get_job(job_id)["id"]).resolve()
    target = (base / path).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, filename=target.name if download else None)


# ---------- Realtime ----------

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    hub.sockets.add(websocket)
    try:
        await websocket.send_json({"type": "snapshot", "jobs": list_jobs()})
        while True:
            await websocket.receive_text()  # ping dari browser
    except WebSocketDisconnect:
        pass
    finally:
        hub.sockets.discard(websocket)


@app.middleware("http")
async def no_stale_ui(request, call_next):
    """Antarmuka selalu divalidasi ulang, supaya versi lama tidak nyangkut di cache browser."""
    response = await call_next(request)
    if request.url.path.startswith(("/branding/", "/static/")) or request.url.path in ("/", "/app.js", "/style.css", "/index.html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
