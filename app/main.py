"""Server lokal: REST API + WebSocket realtime + antarmuka web."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from pathlib import Path

from dotenv import load_dotenv, set_key
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.genai import errors as genai_errors
from pydantic import BaseModel

from . import facetrack, gemini, media, pipeline, transcribe
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
    api_key: str | None = None
    model: str | None = None
    whisper_model: str | None = None
    whisper_language: str | None = None


@app.get("/api/config")
def get_config():
    key = os.environ.get("GEMINI_API_KEY", "")
    return {
        "has_key": bool(key),
        "key_hint": f"…{key[-4:]}" if key else "",
        "model": pipeline.model_name(),
        "ffmpeg": media.FFMPEG,
        "subtitles_supported": media.SUBTITLES_SUPPORTED,
        "face_tracking": facetrack.available(),
        "whisper_model": transcribe.model_name(),
        "whisper_models": transcribe.MODELS,
        "whisper_downloaded": {m: transcribe.is_downloaded(m) for m in transcribe.MODELS},
        "whisper_language": transcribe.language(),
        "whisper_languages": transcribe.LANGUAGES,
        "aspects": list(media.ASPECTS),
    }


@app.post("/api/config")
def save_config(cfg: ConfigIn):
    ENV_FILE.touch(mode=0o600, exist_ok=True)
    if cfg.api_key is not None and cfg.api_key.strip():
        os.environ["GEMINI_API_KEY"] = cfg.api_key.strip()
        set_key(str(ENV_FILE), "GEMINI_API_KEY", cfg.api_key.strip())
    if cfg.model:
        os.environ["GEMINI_MODEL"] = cfg.model.strip()
        set_key(str(ENV_FILE), "GEMINI_MODEL", cfg.model.strip())
    for field, env, allowed in (("whisper_model", "WHISPER_MODEL", transcribe.MODELS),
                                ("whisper_language", "WHISPER_LANGUAGE", transcribe.LANGUAGES)):
        value = getattr(cfg, field)
        if value in allowed:
            os.environ[env] = value
            set_key(str(ENV_FILE), env, value)
    return get_config()


@app.get("/api/models")
async def models():
    try:
        return {"models": await asyncio.to_thread(gemini.list_models, pipeline.api_key())}
    except genai_errors.APIError as e:
        raise HTTPException(400, f"Gemini API ({e.code}): {e.message}")
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


@app.post("/api/jobs/{job_id}/rerender")
async def rerender_all(job_id: str, body: RerenderIn):
    job = get_job(job_id)
    if not job.get("meta"):
        raise HTTPException(400, "Video sumber belum siap.")
    if body.aspect not in media.ASPECTS or body.layout not in ("face", "crop", "blur"):
        raise HTTPException(400, "Opsi tidak valid.")
    if any(c["status"] in ("queued", "rendering") for c in job["clips"]):
        raise HTTPException(409, "Tunggu sampai semua klip selesai dirender.")
    job["options"].update(aspect=body.aspect, layout=body.layout, subtitles=body.subtitles)
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


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
