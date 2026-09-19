"""Koneksi ke Gemini API: upload video, minta AI memilih momen terbaik untuk klip.

Skema jawaban dan prompt dipakai bersama semua penyedia AI (lihat analysis.py).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from google import genai
from google.genai import types
from . import pricing
from .analysis import Analysis, AnalysisError, build_prompt


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
