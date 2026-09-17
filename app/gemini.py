"""Koneksi ke Gemini API: upload video, minta AI memilih momen terbaik untuk klip."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class CaptionLine(BaseModel):
    start: float = Field(description="Detik absolut dari awal video")
    end: float = Field(description="Detik absolut dari awal video")
    text: str


class ClipSuggestion(BaseModel):
    title: str = Field(description="Judul klip yang menarik, maks 70 karakter")
    start: float = Field(description="Detik mulai, dihitung dari awal video")
    end: float = Field(description="Detik selesai, dihitung dari awal video")
    hook: str = Field(description="Kalimat pembuka/hook untuk caption media sosial")
    reason: str = Field(description="Alasan singkat kenapa bagian ini menarik")
    score: int = Field(description="Potensi viral 1-100")
    hashtags: list[str]
    captions: list[CaptionLine] = Field(default_factory=list)


class Analysis(BaseModel):
    summary: str
    clips: list[ClipSuggestion]


def client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def list_models(api_key: str) -> list[str]:
    c = client(api_key)  # simpan referensi: pager membaca halaman berikutnya secara lazy
    names = []
    for m in c.models.list():
        actions = getattr(m, "supported_actions", None) or []
        name = (m.name or "").removeprefix("models/")
        if "gemini" in name and (not actions or "generateContent" in actions):
            names.append(name)
    return sorted(set(names), reverse=True)


def upload_video(api_key: str, path: Path, on_state: Callable[[str], None]) -> types.File:
    c = client(api_key)
    on_state("Mengunggah video ke Gemini…")
    f = c.files.upload(file=path, config={"mime_type": "video/mp4"})
    started = time.time()
    while f.state and f.state.name == "PROCESSING":
        on_state(f"Gemini sedang memproses video ({int(time.time() - started)} dtk)…")
        time.sleep(3)
        f = c.files.get(name=f.name)
    if f.state and f.state.name == "FAILED":
        raise RuntimeError("Gemini gagal memproses video.")
    return f


def delete_file(api_key: str, f: types.File) -> None:
    c = client(api_key)
    try:
        c.files.delete(name=f.name)
    except Exception:
        pass


def build_prompt(opts: dict, duration: float) -> str:
    captions = (
        "Untuk setiap klip, isi `captions` dengan transkrip ucapan per kalimat pendek "
        "(maks ~8 kata per baris) beserta waktu mulai/selesai dalam detik absolut, "
        "dalam bahasa asli pembicara."
        if opts.get("subtitles") else "Biarkan `captions` berupa list kosong."
    )
    extra = f"\nInstruksi tambahan dari pengguna: {opts['instructions']}" if opts.get("instructions") else ""
    return f"""Kamu adalah editor video pendek profesional untuk TikTok, Instagram Reels, dan YouTube Shorts.

Tonton video ini (gambar + suara) dari awal sampai akhir. Durasi total: {duration:.1f} detik.

Pilih {opts['num_clips']} momen terbaik untuk dijadikan klip pendek yang berdiri sendiri:
- Durasi tiap klip antara {opts['min_len']} dan {opts['max_len']} detik.
- Mulai tepat di awal kalimat/ide dan selesai setelah kalimat tuntas (jangan terpotong di tengah kata).
- Utamakan hook kuat di 3 detik pertama, emosi, insight, humor, atau pernyataan kontroversial.
- Klip tidak boleh saling tumpang tindih.
- Semua waktu dalam DETIK (angka desimal) dihitung dari awal video, bukan format MM:SS.
- Judul, hook, alasan, dan hashtag ditulis dalam Bahasa Indonesia.
{captions}{extra}

Urutkan dari skor tertinggi."""


def analyze(api_key: str, model: str, source: types.File, opts: dict, duration: float) -> Analysis:
    video_part = types.Part.from_uri(file_uri=source.uri, mime_type=source.mime_type or "video/mp4")
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Analysis,
        temperature=0.4,
    )
    if duration > 20 * 60:
        # Video panjang: resolusi rendah supaya muat di context window dan lebih murah.
        config.media_resolution = types.MediaResolution.MEDIA_RESOLUTION_LOW
    c = client(api_key)
    resp = c.models.generate_content(
        model=model,
        contents=[video_part, build_prompt(opts, duration)],
        config=config,
    )
    if isinstance(resp.parsed, Analysis):
        return resp.parsed
    if not resp.text:
        raise RuntimeError("Gemini tidak mengembalikan jawaban (mungkin diblokir filter keamanan).")
    return Analysis.model_validate_json(resp.text)
