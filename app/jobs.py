"""Penyimpanan job di disk dan siaran event realtime via WebSocket."""
from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path

from fastapi import WebSocket

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "jobs"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Hub:
    """Browser pemilik job menerima event realtime; session lain tidak."""

    def __init__(self) -> None:
        # socket → session_id
        self.sockets: dict[WebSocket, str] = {}
        # Pendengar lokal (dipakai mode command line untuk menampilkan progres).
        self.listeners: list = []

    def add(self, ws: WebSocket, session_id: str) -> None:
        self.sockets[ws] = session_id

    def remove(self, ws: WebSocket) -> None:
        self.sockets.pop(ws, None)

    async def send(self, event: dict, session_id: str | None = None) -> None:
        """Kirim event ke semua socket.

        Kalau *session_id* diisi, hanya socket milik sesi itu yang menerima.
        Kalau None (event global seperti snapshot), kirim ke semua.
        """
        for listen in list(self.listeners):
            listen(event)
        dead = []
        for ws, sid in list(self.sockets.items()):
            if session_id is not None and sid != session_id:
                continue
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.sockets.pop(ws, None)


hub = Hub()


class Store:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self._last_progress: dict[str, float] = {}
        for f in DATA_DIR.glob("*/job.json"):
            try:
                job = json.loads(f.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            # Proses yang terputus karena server dimatikan.
            if job["status"] not in ("done", "error"):
                job["status"], job["error"] = "error", "Server dihentikan saat proses berjalan."
            for c in job["clips"]:
                if c["status"] in ("queued", "rendering"):
                    c["status"], c["error"] = "error", "Render terputus. Klik Render ulang."
                pub = c.get("publish")
                if pub and pub["status"] in ("uploading", "posting"):
                    pub["status"], pub["error"] = "error", "Posting terputus karena server dimatikan."
            self.jobs[job["id"]] = job

    def dir(self, job_id: str) -> Path:
        return DATA_DIR / job_id

    def create(self, name: str, source_type: str, options: dict, owner_session_id: str = "") -> dict:
        job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        (self.dir(job_id) / "clips").mkdir(parents=True)
        job = {
            "id": job_id, "name": name, "source_type": source_type, "options": options,
            "created_at": time.time(), "status": "queued", "stage": "Menunggu antrean…",
            "progress": 0.0, "error": None, "source": None, "meta": None,
            "summary": None, "clips": [], "logs": [],
            "owner_session_id": owner_session_id,
        }
        self.jobs[job_id] = job
        return job

    def save(self, job: dict) -> None:
        path = self.dir(job["id"]) / "job.json"
        if not path.parent.exists():
            return  # job sudah dihapus
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2))
        tmp.replace(path)

    async def publish(self, job: dict) -> None:
        self.save(job)
        await hub.send({"type": "job", "job": job}, job.get("owner_session_id") or None)

    async def update(self, job: dict, **fields) -> None:
        job.update(fields)
        await self.publish(job)

    async def log(self, job: dict, line: str) -> None:
        entry = {"t": time.time(), "line": line}
        job["logs"] = (job["logs"] + [entry])[-200:]
        self.save(job)
        await hub.send({"type": "log", "job_id": job["id"], **entry},
                       job.get("owner_session_id") or None)

    async def progress(self, job: dict, value: float, stage: str | None = None, clip_id: str | None = None) -> None:
        """Progres dikirim ringan (tanpa seluruh job) dan dibatasi ~8x per detik."""
        key = f"{job['id']}:{clip_id}"
        now = time.monotonic()
        clip = self.clip(job, clip_id) if clip_id else None
        stage_changed = bool(stage) and (clip or job).get("stage") != stage
        if value < 1 and not stage_changed and now - self._last_progress.get(key, 0) < 0.12:
            return
        self._last_progress[key] = now
        if clip_id:
            if clip:
                clip["progress"] = value
                if stage:
                    clip["stage"] = stage
        else:
            job["progress"] = value
            if stage:
                job["stage"] = stage
        await hub.send({"type": "progress", "job_id": job["id"], "clip_id": clip_id,
                        "progress": value, "stage": stage},
                       job.get("owner_session_id") or None)

    @staticmethod
    def clip(job: dict, clip_id: str) -> dict | None:
        return next((c for c in job["clips"] if c["id"] == clip_id), None)

    async def delete(self, job_id: str) -> None:
        job = self.jobs.pop(job_id, None)
        session_id = (job or {}).get("owner_session_id") or None
        await asyncio.to_thread(shutil.rmtree, self.dir(job_id), True)
        await hub.send({"type": "deleted", "job_id": job_id}, session_id)


store = Store()
