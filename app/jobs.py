"""Penyimpanan job di disk dan siaran event realtime via WebSocket."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any
from fastapi import WebSocket

from . import security

DATA_DIR = Path(os.environ.get("CLIPPING_DATA_DIR", Path(__file__).resolve().parent.parent / "data" / "jobs"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Hub:
    """Semua browser yang terbuka menerima event yang sama secara realtime."""

    def __init__(self) -> None:
        self.sockets: dict[WebSocket, dict[str, Any] | str] = {}
        # Pendengar lokal (dipakai mode command line untuk menampilkan progres).
        self.listeners: list = []

    async def send(
        self,
        event: dict,
        session_id: str | None = None,
        user_id: int | str | None = None,
    ) -> None:
        for listen in list(self.listeners):
            listen(event)
        dead = []
        is_public = os.environ.get("PUBLIC_MODE", "false").strip().lower() in ("1", "true", "yes", "on")

        for ws, info in list(self.sockets.items()):
            # Jika session_id atau user_id dispesifikasikan:
            if session_id or user_id is not None:
                s_id = info.get("session_id") if isinstance(info, dict) else info
                u_id = info.get("user_id") if isinstance(info, dict) else None
                matches_session = bool(session_id and s_id == session_id)
                matches_user = bool(user_id is not None and u_id == user_id)
                if not (matches_session or matches_user):
                    continue
            elif is_public:
                # Dalam PUBLIC_MODE, jangan broadcast event unowned ke sembarang user
                continue

            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.sockets.pop(ws, None)


hub = Hub()


class Store:
    DATA_DIR: Path = DATA_DIR

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self._last_progress: dict[str, float] = {}
        for f in DATA_DIR.glob("*/job.json"):
            try:
                job = json.loads(f.read_text(encoding="utf-8"))
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
        target = (self.DATA_DIR / job_id).resolve()
        if self.DATA_DIR.resolve() not in target.parents and target != self.DATA_DIR.resolve():
            raise ValueError(f"Job ID tidak valid: {job_id}")
        return target

    @staticmethod
    def _collect_secrets(job: dict) -> list[str]:
        secrets_list = []
        context = job.get("_ai_context") or {}
        if context.get("key"):
            secrets_list.append(context["key"])
        for env_name in (
            "SUPABASE_SECRET", "SECRET_KEY", "TOKEN_ENCRYPTION_KEY", "CLOUDINARY_API_SECRET", "R2_SECRET_ACCESS_KEY"
        ):
            val = os.getenv(env_name, "").strip()
            if val and len(val) >= 8:
                secrets_list.append(val)
        return secrets_list

    @classmethod
    def public_job(cls, job: dict) -> dict:
        """Remove transient secrets before persistence or sending to clients."""
        secrets_list = cls._collect_secrets(job)

        def scrub(value):
            if isinstance(value, str):
                res = value
                for s in secrets_list:
                    if s in res:
                        res = res.replace(s, "[REDACTED]")
                return res
            if isinstance(value, dict):
                return {
                    key: scrub(item)
                    for key, item in value.items()
                    if key not in ("_ai_context", "owner_session_id", "user_id")
                }
            if isinstance(value, list):
                return [scrub(item) for item in value]
            return value

        return scrub(job)

    @classmethod
    def redact(cls, job: dict, line: str) -> str:
        for s in cls._collect_secrets(job):
            if s in line:
                line = line.replace(s, "[REDACTED]")
        return line

    def create(self, name: str, source_type: str, options: dict) -> dict:
        job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        (self.dir(job_id) / "clips").mkdir(parents=True)
        retention_h = int(options.get("retention_hours") or 8)
        job = {
            "id": job_id, "name": name, "source_type": source_type, "options": options,
            "created_at": time.time(), "status": "queued", "stage": "Menunggu antrean...",
            "progress": 0.0, "error": None, "source": None, "meta": None,
            "summary": None, "clips": [], "logs": [],
            "retention_hours": retention_h,
        }
        self.jobs[job_id] = job
        return job

    def save(self, job: dict) -> None:
        path = self.dir(job["id"]) / "job.json"
        if not path.parent.exists():
            return  # job sudah dihapus
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.public_job(job), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    async def publish(self, job: dict) -> None:
        self.save(job)
        await hub.send(
            {"type": "job", "job": self.public_job(job)},
            session_id=job.get("owner_session_id"),
            user_id=job.get("user_id"),
        )

    async def update(self, job: dict, **fields) -> None:
        job.update(fields)
        await self.publish(job)

    async def log(self, job: dict, line: str) -> None:
        line = self.redact(job, line)
        entry = {"t": time.time(), "line": line}
        job["logs"] = (job["logs"] + [entry])[-200:]
        self.save(job)
        await hub.send(
            {"type": "log", "job_id": job["id"], **entry},
            session_id=job.get("owner_session_id"),
            user_id=job.get("user_id"),
        )

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
        await hub.send(
            {"type": "progress", "job_id": job["id"], "clip_id": clip_id,
             "progress": value, "stage": stage},
            session_id=job.get("owner_session_id"),
            user_id=job.get("user_id"),
        )

    @staticmethod
    def clip(job: dict, clip_id: str) -> dict | None:
        return next((c for c in job["clips"] if c["id"] == clip_id), None)

    async def delete(self, job_id: str) -> None:
        job = self.jobs.pop(job_id, None)
        await asyncio.to_thread(shutil.rmtree, self.dir(job_id), True)
        await hub.send(
            {"type": "deleted", "job_id": job_id},
            session_id=job.get("owner_session_id") if job else None,
            user_id=job.get("user_id") if job else None,
        )

    async def purge_expired(self, retention_seconds: float | None = None) -> list[str]:
        """Hapus seluruh folder proyek di data/jobs/<id> yang sudah melewati masa retensi."""
        now = time.time()
        default_retention = retention_seconds if retention_seconds is not None else security.job_retention_seconds()
        cutoff = now - default_retention
        purged = []

        # 1. Periksa job yang tersimpan di memori
        for job_id, job in list(self.jobs.items()):
            created_at = job.get("created_at") or 0
            if "retention_hours" in job:
                job_retention = (job.get("retention_hours") or 8) * 3600
            elif retention_seconds is not None:
                job_retention = retention_seconds
            else:
                job_retention = security.job_retention_seconds()

            # Jika job masih aktif berjalan dan belum lewat batas retensi + 1 jam, pertahankan
            if job.get("status") not in ("done", "error") and now - created_at < job_retention + 3600:
                continue
            if created_at < now - job_retention:
                await self.delete(job_id)
                purged.append(job_id)

        # 2. Periksa folder yatim piatu (orphaned) atau file upload sementara di DATA_DIR
        try:
            if self.DATA_DIR.exists():
                for entry in list(self.DATA_DIR.iterdir()):
                    if entry.name.startswith("."):
                        try:
                            if entry.is_dir():
                                for sub in list(entry.iterdir()):
                                    if sub.stat().st_mtime < now - 3600:
                                        sub.unlink(missing_ok=True)
                            elif entry.is_file():
                                if entry.stat().st_mtime < now - 3600:
                                    entry.unlink(missing_ok=True)
                        except OSError:
                            pass
                        continue

                    if entry.is_dir() and entry.name not in self.jobs:
                        try:
                            st = entry.stat()
                            if st.st_mtime < cutoff:
                                await asyncio.to_thread(shutil.rmtree, entry, True)
                                purged.append(entry.name)
                        except OSError:
                            pass
        except OSError:
            pass

        return purged


store = Store()
