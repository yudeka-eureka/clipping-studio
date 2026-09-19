"""Subtitle yang pas dengan gerak mulut: transkripsi lokal (faster-whisper) dengan timestamp per kata.

Gemini menonton video versi 5 fps dan membulatkan waktu ke ~0,5 detik, jadi caption darinya
bisa meleset. Di sini audio klip ditranskripsi ulang di komputer sendiri dengan timestamp per kata,
lalu kata-kata dikelompokkan jadi baris pendek yang muncul tepat saat diucapkan. Teks dari Gemini
dipakai sebagai petunjuk ejaan (initial prompt) supaya nama & istilah lebih akurat.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from .media import FFMPEG

SAMPLE_RATE = 16000
PAD = 0.6  # detik audio tambahan di kiri-kanan supaya kata di tepi klip tidak terpotong

MODELS = {
    "small": "Cepat, akurasi cukup (~480 MB)",
    "medium": "Seimbang (~1,5 GB)",
    "large-v3-turbo": "Paling akurat, lebih lambat (~1,6 GB)",
}
LANGUAGES = {"auto": "Otomatis", "id": "Indonesia", "en": "English"}

_models: dict[str, object] = {}
_lock = threading.Lock()


def model_name() -> str:
    name = os.environ.get("WHISPER_MODEL", "").strip()
    return name if name in MODELS else "small"


def language() -> str:
    lang = os.environ.get("WHISPER_LANGUAGE", "").strip()
    return lang if lang in LANGUAGES else "auto"


def _model(name: str):
    from faster_whisper import WhisperModel

    if name not in _models:
        # Unduh sekali dari Hugging Face, lalu tersimpan di ~/.cache/huggingface.
        _models[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _models[name]


def _load_audio(src: Path, start: float, end: float) -> np.ndarray:
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", str(src),
        "-t", f"{end - start:.3f}", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def transcribe_words(src: Path, start: float, end: float, hint: str = "",
                     on_progress: Callable[[float], None] | None = None) -> list[dict]:
    """Kata-kata beserta waktu absolut (detik dari awal video sumber)."""
    a0 = max(0.0, start - PAD)
    audio = _load_audio(src, a0, end + PAD)
    if audio.size < SAMPLE_RATE * 0.3:
        return []
    with _lock:
        model = _model(model_name())
        lang = language()
        if lang == "auto":
            detected, _, _ = model.detect_language(audio, vad_filter=True)
            lang = "id" if detected == "ms" else detected  # Whisper sering tertukar Indonesia ↔ Melayu
        segments, _ = model.transcribe(
            audio, language=lang, word_timestamps=True, beam_size=5,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
            condition_on_previous_text=False,
            initial_prompt=hint[:400] or None,
        )
        total = len(audio) / SAMPLE_RATE
        words = []
        for seg in segments:
            for w in seg.words or []:
                text = w.word.strip()
                if text:
                    words.append({"start": a0 + w.start, "end": a0 + w.end, "word": text})
            if on_progress:
                on_progress(min(1.0, seg.end / total))
    # Hanya kata yang sebagian besar berada di dalam rentang klip.
    return [w for w in words if (w["start"] + w["end"]) / 2 >= start and (w["start"] + w["end"]) / 2 <= end]


def build_captions(words: list[dict], max_chars: int = 30, max_dur: float = 2.2,
                   max_gap: float = 0.5) -> list[dict]:
    """Kelompokkan kata jadi baris pendek. Baris muncul saat kata pertama diucapkan."""
    lines: list[list[dict]] = []
    for w in words:
        cur = lines[-1] if lines else None
        if cur:
            text_len = len(" ".join(x["word"] for x in cur)) + 1 + len(w["word"])
            prev = cur[-1]
            # Kata penutup kalimat boleh sedikit melebihi batas supaya tidak tertinggal sendirian.
            closes = w["word"][-1] in ".?!,"
            breaks = (
                text_len > max_chars + (8 if closes else 0)
                or w["end"] - cur[0]["start"] > max_dur + (0.7 if closes else 0)
                or w["start"] - prev["end"] > max_gap
                or prev["word"][-1] in ".?!"
                or (prev["word"][-1] in ",;:" and len(cur) >= 3)
            )
            if not breaks:
                cur.append(w)
                continue
        lines.append([w])

    captions = []
    for i, line in enumerate(lines):
        start = line[0]["start"]
        end = line[-1]["end"] + 0.15  # tahan sebentar setelah kata terakhir
        if i + 1 < len(lines):
            end = min(end, lines[i + 1][0]["start"])
        end = max(end, start + 0.35)
        captions.append({"start": round(start, 3), "end": round(end, 3),
                         "text": " ".join(x["word"] for x in line)})
    return captions


def _cache_key(start: float, end: float) -> dict:
    return {"start": round(start, 2), "end": round(end, 2), "model": model_name(), "lang": language()}


def _read_cache(path: Path, key: dict) -> list[dict] | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data["words"] if data.get("key") == key else None


def source_words(src: Path, duration: float, cache_dir: Path,
                 on_progress: Callable[[float], None] | None = None) -> list[dict]:
    """Transkrip seluruh video (dipakai Claude/ChatGPT untuk memilih klip, lalu dipakai ulang untuk subtitle)."""
    key = _cache_key(0, duration)
    cache = cache_dir / "source.words.json"
    words = _read_cache(cache, key)
    if words is None:
        words = transcribe_words(src, 0, duration, "", on_progress)
        cache.write_text(json.dumps({"key": key, "words": words}, ensure_ascii=False))
    return words


def words_for_clip(src: Path, clip: dict, cache_dir: Path,
                   on_progress: Callable[[float], None] | None = None) -> list[dict]:
    """Kata bertimestamp absolut untuk klip, di-cache per rentang waktu + model + bahasa."""
    hint = " ".join(c["text"] for c in clip.get("ai_captions") or [])
    key = _cache_key(clip["start"], clip["end"])
    cache = cache_dir / f"clip_{clip['id']}.words.json"
    words = _read_cache(cache, key)
    if words is None:
        # Kalau transkrip seluruh video sudah ada (dipakai Claude/ChatGPT), tinggal dipotong.
        for full in (cache_dir / "source.words.json", cache_dir.parent / "source.words.json"):
            data = json.loads(full.read_text()) if full.exists() else {}
            fkey = data.get("key") or {}
            if fkey.get("model") == key["model"] and fkey.get("lang") == key["lang"]:
                mid = lambda w: (w["start"] + w["end"]) / 2  # noqa: E731
                return [w for w in data["words"] if clip["start"] <= mid(w) <= clip["end"]]
    if words is None:
        words = transcribe_words(src, clip["start"], clip["end"], hint, on_progress)
        cache.write_text(json.dumps({"key": key, "words": words}, ensure_ascii=False))
    return words


def model_downloaded_or_loading() -> bool:
    return model_name() in _models or is_downloaded(model_name())


def is_downloaded(name: str) -> bool:
    try:
        from faster_whisper.utils import download_model

        download_model(name, local_files_only=True)
        return True
    except Exception:  # noqa: BLE001
        return False
