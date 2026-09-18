"""Koneksi ke Gemini API: upload video, minta AI memilih momen terbaik untuk klip."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from . import pricing


class CaptionLine(BaseModel):
    start: float = Field(description="Detik absolut dari awal video")
    end: float = Field(description="Detik absolut dari awal video")
    text: str


class ClipSuggestion(BaseModel):
    title: str = Field(description="Judul yang ditempel di atas video: menjelaskan konteks klip, maks 60 karakter")
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
- Judul akan ditempel di bagian atas video. Buat judul yang langsung menjelaskan konteks
  (siapa/apa yang dibahas) bagi penonton yang tidak menonton video aslinya, maks 60 karakter,
  tanpa emoji dan tanpa tanda kutip.
{captions}{extra}

Urutkan dari skor tertinggi."""


class AnalysisError(RuntimeError):
    """Jawaban Gemini tidak bisa dipakai, tapi token tetap terpakai (dibawa di .usage)."""

    def __init__(self, message: str, usage: dict) -> None:
        super().__init__(message)
        self.usage = usage


def analyze(api_key: str, model: str, source: types.File, opts: dict, duration: float) -> tuple[Analysis, dict]:
    video_part = types.Part.from_uri(file_uri=source.uri, mime_type=source.mime_type or "video/mp4")
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Analysis,
        temperature=0.4,
    )
    low_res = duration > 20 * 60
    if low_res:
        # Video panjang: resolusi rendah supaya muat di context window dan lebih murah.
        config.media_resolution = types.MediaResolution.MEDIA_RESOLUTION_LOW
    c = client(api_key)
    resp = c.models.generate_content(
        model=model,
        contents=[video_part, build_prompt(opts, duration)],
        config=config,
    )
    usage = pricing.usage_from_response(resp, model, duration, low_res)
    if isinstance(resp.parsed, Analysis):
        return resp.parsed, usage
    if not resp.text:
        raise AnalysisError("Gemini tidak mengembalikan jawaban (mungkin diblokir filter keamanan).", usage)
    try:
        return Analysis.model_validate_json(resp.text), usage
    except ValueError as e:
        raise AnalysisError(f"Jawaban Gemini tidak sesuai format: {e}", usage) from e
