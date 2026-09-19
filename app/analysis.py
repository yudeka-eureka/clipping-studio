"""Pemilihan momen klip oleh AI, bisa lewat Gemini, Claude (Anthropic), atau ChatGPT (OpenAI).

Perbedaan penting antar penyedia:
- Gemini bisa menonton video langsung (gambar + suara) lewat Files API.
- Claude dan ChatGPT tidak menerima video. Untuk keduanya, video diubah dulu jadi
  transkrip bertimestamp (Whisper lokal) + beberapa frame sebagai gambar.

Skema jawaban sama untuk semua penyedia, jadi sisa pipeline tidak perlu tahu bedanya.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from .media import FFMPEG

MAX_FRAMES = 20
FRAME_WIDTH = 512


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


class AnalysisError(RuntimeError):
    """Jawaban AI tidak bisa dipakai, tapi token tetap terpakai (dibawa di .usage)."""

    def __init__(self, message: str, usage: dict) -> None:
        super().__init__(message)
        self.usage = usage


# Penyedia yang didukung. "video" = bisa menonton video langsung.
PROVIDERS: dict[str, dict] = {
    "gemini": {"label": "Google Gemini", "env": "GEMINI_API_KEY", "model_env": "GEMINI_MODEL",
               "default_model": "gemini-2.5-flash", "video": True},
    "anthropic": {"label": "Anthropic Claude", "env": "ANTHROPIC_API_KEY", "model_env": "ANTHROPIC_MODEL",
                  "default_model": "claude-opus-5", "video": False},
    "openai": {"label": "OpenAI ChatGPT", "env": "OPENAI_API_KEY", "model_env": "OPENAI_MODEL",
               "default_model": "gpt-5.6-terra", "video": False},
}


def provider() -> str:
    name = os.environ.get("AI_PROVIDER", "").strip().lower()
    return name if name in PROVIDERS else "gemini"


def model_name(name: str | None = None) -> str:
    spec = PROVIDERS[name or provider()]
    return os.environ.get(spec["model_env"], "").strip() or spec["default_model"]


def api_key(name: str | None = None) -> str:
    spec = PROVIDERS[name or provider()]
    key = os.environ.get(spec["env"], "").strip()
    if not key:
        raise RuntimeError(f"API key {spec['label']} belum diisi ({spec['env']}). Buka Pengaturan.")
    return key


def needs_transcript(name: str | None = None) -> bool:
    """Claude & ChatGPT butuh transkrip lokal karena tidak bisa menonton video."""
    return not PROVIDERS[name or provider()]["video"]


def build_prompt(opts: dict, duration: float, has_media: bool) -> str:
    captions = (
        "Untuk setiap klip, isi `captions` dengan transkrip ucapan per kalimat pendek "
        "(maks ~8 kata per baris) beserta waktu mulai/selesai dalam detik absolut, "
        "dalam bahasa asli pembicara."
        if opts.get("subtitles") and has_media else
        "Biarkan `captions` berupa list kosong (subtitle dibuat terpisah di komputer ini)."
    )
    extra = f"\nInstruksi tambahan dari pengguna: {opts['instructions']}" if opts.get("instructions") else ""
    sumber = ("Tonton video ini (gambar + suara) dari awal sampai akhir."
              if has_media else
              "Kamu diberi transkrip lengkap video beserta waktunya, dan beberapa frame sebagai gambaran visual.")
    return f"""Kamu adalah editor video pendek profesional untuk TikTok, Instagram Reels, dan YouTube Shorts.

{sumber} Durasi total: {duration:.1f} detik.

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


def transcript_text(words: list[dict], max_chars: int = 120_000) -> str:
    """Transkrip bertimestamp, satu baris per ~12 kata, supaya AI bisa menunjuk waktu."""
    lines, chunk = [], []
    for w in words:
        chunk.append(w)
        if len(chunk) >= 12 or w["word"][-1:] in ".?!":
            lines.append(f"[{chunk[0]['start']:.1f}] " + " ".join(x["word"] for x in chunk))
            chunk = []
    if chunk:
        lines.append(f"[{chunk[0]['start']:.1f}] " + " ".join(x["word"] for x in chunk))
    text = "\n".join(lines)
    if len(text) > max_chars:  # video sangat panjang: potong di tengah, beri penanda
        head, tail = text[: max_chars // 2], text[-max_chars // 2:]
        text = f"{head}\n[... sebagian transkrip dilewati karena terlalu panjang ...]\n{tail}"
    return text


def sample_frames(src: Path, duration: float, work_dir: Path, count: int = MAX_FRAMES) -> list[tuple[float, bytes]]:
    """Ambil beberapa frame JPEG kecil sebagai gambaran visual untuk model yang tidak bisa menonton video."""
    if duration <= 0 or count <= 0:
        return []
    interval = max(5.0, duration / count)
    out_dir = work_dir / "frames"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-vf", f"fps=1/{interval:.3f},scale={FRAME_WIDTH}:-2", "-q:v", "6",
         str(out_dir / "f_%03d.jpg")],
        check=True,
    )
    frames = []
    for i, path in enumerate(sorted(out_dir.glob("f_*.jpg"))[:count]):
        frames.append((i * interval, path.read_bytes()))
    return frames


def b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode()


def analyze(source: Path | object, opts: dict, duration: float, words: list[dict] | None = None,
            frames: list[tuple[float, bytes]] | None = None,
            on_state: Callable[[str], None] | None = None) -> tuple[Analysis, dict]:
    """Jalankan analisis dengan penyedia yang sedang dipilih."""
    name = provider()
    if name == "gemini":
        from . import gemini

        return gemini.analyze(api_key(), model_name(), source, opts, duration)
    if name == "anthropic":
        from . import provider_anthropic

        return provider_anthropic.analyze(api_key(), model_name(), opts, duration, words or [], frames or [])
    from . import provider_openai

    return provider_openai.analyze(api_key(), model_name(), opts, duration, words or [], frames or [])


def list_models(name: str | None = None) -> list[str]:
    name = name or provider()
    if name == "gemini":
        from . import gemini

        return gemini.list_models(api_key(name))
    if name == "anthropic":
        from . import provider_anthropic

        return provider_anthropic.list_models(api_key(name))
    from . import provider_openai

    return provider_openai.list_models(api_key(name))
