"""Alur kerja: sumber video → proxy → Gemini → render klip."""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Callable

import yt_dlp
from google.genai import errors as genai_errors

from . import facetrack, gemini, media, transcribe
from .jobs import store

# Satu analisis penuh sekaligus; render klip boleh paralel terbatas.
pipeline_lock = asyncio.Semaphore(1)
render_lock = asyncio.Semaphore(max(1, min(3, (os.cpu_count() or 2) // 4)))


def api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("API key Gemini belum diisi. Buka Pengaturan di pojok kanan atas.")
    return key


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"


def _download(job: dict, url: str, loop: asyncio.AbstractEventLoop) -> Path:
    out_dir = store.dir(job["id"])

    def hook(d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            pct = (d.get("downloaded_bytes", 0) / total) if total else 0
            speed = d.get("_speed_str", "").strip()
            asyncio.run_coroutine_threadsafe(
                store.progress(job, pct, f"Mengunduh video… {speed}"), loop)

    opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "source.%(ext)s"),
        "ffmpeg_location": media.FFMPEG,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        job["name"] = info.get("title") or job["name"]
    files = sorted(out_dir.glob("source.*"), key=lambda p: p.stat().st_size, reverse=True)
    files = [f for f in files if f.suffix not in (".part", ".ytdl")]
    if not files:
        raise RuntimeError("Video gagal diunduh.")
    return files[0]


def _sanitize(suggestions: list[gemini.ClipSuggestion], duration: float, opts: dict) -> list[gemini.ClipSuggestion]:
    """Rapikan waktu dari AI: batasi ke durasi video dan panjang min/maks."""
    result = []
    for s in suggestions:
        start = max(0.0, min(s.start, duration - 1))
        end = max(start + 1, min(s.end, duration))
        if end - start > opts["max_len"]:
            end = start + opts["max_len"]
        if end - start < opts["min_len"]:
            end = min(duration, start + opts["min_len"])
            start = max(0.0, end - opts["min_len"])
        s.start, s.end = round(start, 2), round(end, 2)
        result.append(s)
    return result


def new_clip(job: dict, start: float, end: float, title: str, **extra) -> dict:
    clip = {
        "id": uuid.uuid4().hex[:8], "title": title, "start": start, "end": end,
        "hook": "", "reason": "", "score": None, "hashtags": [], "captions": [], "ai_captions": [],
        "status": "pending", "progress": 0.0, "error": None, "file": None, "srt": None,
        "version": 0,
    }
    clip.update(extra)
    job["clips"].append(clip)
    return clip


class ClipProgress:
    """Progres satu klip yang terdiri dari beberapa tahap berbobot (wajah, subtitle, render)."""

    def __init__(self, job: dict, clip: dict, stages: dict[str, tuple[str, float]]) -> None:
        self.job, self.clip, self.loop = job, clip, asyncio.get_running_loop()
        total = sum(w for _, w in stages.values())
        self.stages, acc = {}, 0.0
        for name, (label, w) in stages.items():
            self.stages[name] = (label, acc / total, w / total)
            acc += w

    async def set(self, name: str, p: float) -> None:
        label, base, weight = self.stages[name]
        await store.progress(self.job, base + p * weight, stage=label, clip_id=self.clip["id"])

    def threadsafe(self, name: str) -> Callable[[float], None]:
        return lambda p: asyncio.run_coroutine_threadsafe(self.set(name, p), self.loop) and None


async def _face_crop(job: dict, clip: dict, src: Path, clips_dir: Path, prog: ClipProgress) -> tuple | None:
    """Untuk tata letak "face": lacak wajah lalu siapkan crop yang bergerak mengikuti pembicara."""
    meta = job["meta"]
    cw, ch = media.crop_size(meta["width"], meta["height"], job["options"]["aspect"])
    result = await asyncio.to_thread(
        facetrack.track, src, clip["start"], clip["end"], meta["width"], meta["height"],
        cw / meta["width"], ch / meta["height"], prog.threadsafe("face"),
    )
    st = result["stats"]
    await store.log(job, f"👤 “{clip['title']}”: wajah terlihat di {st['coverage']:.0%} frame, "
                         f"{st['people']} orang, {st['cuts']} perpindahan kamera.")
    cmd = clips_dir / f"clip_{clip['id']}.cmd"
    x0, y0 = facetrack.write_sendcmd(result["keys"], clip["end"] - clip["start"],
                                     meta["width"], meta["height"], cw, ch, cmd)
    return cmd.name, cw, ch, x0, y0


def _wants_face(job: dict) -> bool:
    opts, meta = job["options"], job["meta"]
    size = media.crop_size(meta["width"], meta["height"], opts["aspect"])
    return (opts["layout"] == "face" and size is not None
            and size != (meta["width"], meta["height"]) and facetrack.available())


async def _captions(job: dict, clip: dict, src: Path, clips_dir: Path, prog: ClipProgress) -> list[dict]:
    """Subtitle dengan timestamp per kata dari Whisper lokal; kalau gagal, pakai perkiraan Gemini."""
    clip.setdefault("ai_captions", clip.get("captions") or [])
    if not job["meta"]["has_audio"]:
        return []
    if not transcribe.model_downloaded_or_loading():
        await store.log(job, f"⬇️ Mengunduh model Whisper “{transcribe.model_name()}” (sekali saja)…")
    try:
        captions = await asyncio.to_thread(
            transcribe.captions_for_clip, src, clip, clips_dir, prog.threadsafe("subs"))
        await store.log(job, f"💬 “{clip['title']}”: {len(captions)} baris subtitle diselaraskan dengan suara.")
        return captions
    except Exception as e:  # noqa: BLE001
        await store.log(job, f"⚠️ Transkripsi lokal gagal ({e}). Memakai waktu perkiraan dari Gemini.")
        return clip["ai_captions"]


async def render(job: dict, clip: dict) -> None:
    opts = job["options"]
    clip.update(status="queued", progress=0.0, error=None, stage=None)
    await store.publish(job)
    async with render_lock:
        clip["status"] = "rendering"
        await store.publish(job)
        try:
            clips_dir = store.dir(job["id"]) / "clips"
            base = f"clip_{clip['id']}"
            src = store.dir(job["id"]) / job["source"]
            out = clips_dir / f"{base}.mp4"
            srt_path = clips_dir / f"{base}.srt"
            srt_path.unlink(missing_ok=True)

            face = _wants_face(job)
            subs = bool(opts.get("subtitles"))
            stages = {}
            if face:
                stages["face"] = ("Mendeteksi wajah…", 0.3)
            if subs:
                stages["subs"] = ("Menyelaraskan subtitle…", 0.35)
            stages["render"] = ("Merender…", 0.5)
            prog = ClipProgress(job, clip, stages)

            face_crop = await _face_crop(job, clip, src, clips_dir, prog) if face else None
            if subs:
                clip["captions"] = await _captions(job, clip, src, clips_dir, prog)
            has_srt = subs and media.write_srt(clip["captions"], clip["start"], clip["end"], srt_path)
            burn = has_srt and media.SUBTITLES_SUPPORTED

            await media.render_clip(
                src, out, clip["start"], clip["end"],
                opts["aspect"], opts["layout"], job["meta"]["has_audio"],
                srt_path if burn else None, lambda p: prog.set("render", p), face_crop,
            )
            clip.update(status="ready", progress=1.0, stage=None, file=f"clips/{out.name}",
                        srt=f"clips/{srt_path.name}" if has_srt else None,
                        version=clip.get("version", 0) + 1)
            await store.log(job, f"✅ Klip siap: {clip['title']}")
        except Exception as e:  # noqa: BLE001
            clip.update(status="error", error=str(e), stage=None)
            await store.log(job, f"❌ Gagal render “{clip['title']}”: {e}")
    await store.publish(job)


async def run(job: dict, upload_path: Path | None, url: str | None) -> None:
    loop = asyncio.get_running_loop()
    opts = job["options"]
    await store.log(job, "Masuk antrean.")
    async with pipeline_lock:
        uploaded = None
        key = ""
        try:
            # 1. Sumber video
            if url:
                await store.update(job, status="downloading", stage="Mengunduh video…", progress=0)
                await store.log(job, f"Mengunduh dari {url}")
                src = await asyncio.to_thread(_download, job, url, loop)
            else:
                assert upload_path
                src = upload_path
            meta = await media.probe(src)
            job.update(source=src.name, meta=meta)
            await store.log(job, f"Video: {meta['width']}x{meta['height']}, {meta['duration']:.0f} detik"
                                 + ("" if meta["has_audio"] else " (tanpa audio)"))
            await store.publish(job)

            # Sumber sudah siap: klip manual bisa dibuat walau langkah AI gagal.
            key = api_key()
            model = model_name()

            # 2. Proxy kecil untuk analisis AI
            await store.update(job, status="preparing", stage="Menyiapkan video untuk AI…", progress=0)
            proxy = store.dir(job["id"]) / "proxy.mp4"
            await media.make_proxy(src, proxy, meta["duration"],
                                   lambda p: store.progress(job, p, "Menyiapkan video untuk AI…"))
            await store.log(job, f"Proxy siap ({proxy.stat().st_size / 1e6:.1f} MB).")

            # 3. Upload + analisis Gemini
            await store.update(job, status="analyzing", stage="Mengunggah ke Gemini…", progress=0)

            def on_state(msg: str) -> None:
                asyncio.run_coroutine_threadsafe(store.progress(job, 0, msg), loop)

            uploaded = await asyncio.to_thread(gemini.upload_video, key, proxy, on_state)
            await store.log(job, f"Video diterima Gemini. Menganalisis dengan {model}…")
            await store.update(job, stage=f"AI ({model}) sedang menonton & memilih momen…", progress=0)
            analysis = await asyncio.to_thread(gemini.analyze, key, model, uploaded, opts, meta["duration"])
            suggestions = _sanitize(analysis.clips, meta["duration"], opts)
            if not suggestions:
                raise RuntimeError("AI tidak menemukan momen yang cocok. Coba ubah instruksi atau durasi klip.")
            job["summary"] = analysis.summary
            ai_clips = [
                new_clip(job, s.start, s.end, s.title, hook=s.hook, reason=s.reason, score=s.score,
                         hashtags=s.hashtags, ai_captions=[c.model_dump() for c in s.captions])
                for s in suggestions
            ]
            await store.log(job, f"AI memilih {len(suggestions)} klip.")

            # 4. Render semua klip (klip muncul satu per satu begitu selesai)
            await store.update(job, status="rendering", stage="Merender klip…", progress=0)
            # Klip manual yang dibuat selama analisis sudah dirender sendiri.
            await asyncio.gather(*(render(job, c) for c in ai_clips))
            ready = sum(c["status"] == "ready" for c in job["clips"])
            await store.update(job, status="done", stage=f"Selesai — {ready} klip siap", progress=1)
            proxy.unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001
            msg = f"Gemini API ({e.code}): {e.message}" if isinstance(e, genai_errors.APIError) else str(e)
            await store.log(job, f"❌ {msg}")
            await store.update(job, status="error", error=msg, stage="Gagal")
        finally:
            if uploaded is not None:
                await asyncio.to_thread(gemini.delete_file, key, uploaded)
