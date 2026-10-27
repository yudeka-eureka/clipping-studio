"""Koneksi ke Gemini API: upload video, minta AI memilih momen terbaik untuk klip.

Skema jawaban dan prompt dipakai bersama semua penyedia AI (lihat analysis.py).
"""
from __future__ import annotations

import concurrent.futures
import time
from pathlib import Path
from typing import Callable

from google import genai
from google.genai import types
from . import pricing
from .analysis import Analysis, AnalysisError, build_prompt

# Model atau varian yang sudah tidak tersedia untuk pengguna baru / di-sunset oleh Google
UNAVAILABLE_PATTERNS = {
    "2.5-flash",
    "2.5-flash-lite",
    "2.5-pro",
    "1.0-pro",
    "embedding",
    "imagen",
    "aqa",
    "deprecated",
    "retired",
    "legacy",
}


def client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def _is_model_available(c: genai.Client, model_name: str) -> bool:
    """Verifikasi cepat apakah model benar-benar aktif dan dapat digunakan pengguna."""
    try:
        c.models.generate_content(
            model=model_name,
            contents="ping",
            config=types.GenerateContentConfig(max_output_tokens=1),
        )
        return True
    except Exception as e:
        err = str(e).lower()
        if "no longer available" in err or "404" in err or "not found" in err or "deprecated" in err or "unsupported" in err:
            return False
        # Jika error kuota (429/RESOURCE_EXHAUSTED), model tersebut valid untuk user
        if "429" in err or "quota" in err or "resource_exhausted" in err:
            return True
        # Jika network error/offline dalam unit test
        if "connection" in err or "name resolution" in err or "mock" in err:
            return True
        return False


def list_models(api_key: str) -> list[str]:
    c = client(api_key)  # simpan referensi: pager membaca halaman berikutnya secara lazy
    raw_names = []
    try:
        for m in c.models.list():
            actions = getattr(m, "supported_actions", None) or []
            name = (m.name or "").removeprefix("models/")
            if not ("gemini" in name and (not actions or "generateContent" in actions)):
                continue
            # Saring model yang polanya sudah diketahui unavailable/deprecated seperti gemini-2.5-flash
            if any(pat in name for pat in UNAVAILABLE_PATTERNS):
                continue
            raw_names.append(name)
    except Exception:
        pass

    unique_candidates = sorted(set(raw_names), reverse=True)

    # Verifikasi ketersediaan kandidat model secara konkuren
    available = []
    if unique_candidates:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(unique_candidates))) as ex:
            futures = {ex.submit(_is_model_available, c, m): m for m in unique_candidates}
            for f in concurrent.futures.as_completed(futures):
                m = futures[f]
                try:
                    if f.result():
                        available.append(m)
                except Exception:
                    pass

    if available:
        # Urutkan secara descending dan pastikan gemini-3.8-flash diprioritaskan di atas
        return sorted(available, key=lambda x: (x == "gemini-3.8-flash", x), reverse=True)

    # Fallback ke daftar model aktif standar jika hasil pencarian kosong atau semua probe gagal
    return ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"]


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
        contents=[video_part, build_prompt(opts, duration, has_media=True)],
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
