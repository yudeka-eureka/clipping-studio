"""Memadatkan klip: buang jeda diam supaya durasi terpakai untuk bicara.

Sumber jeda:
- Timestamp per kata dari Whisper (paling akurat, tahan terhadap musik/latar bising), atau
- Energi audio (kalau subtitle mati / transkripsi tidak tersedia).

Hasilnya daftar segmen yang dipertahankan, dalam detik relatif terhadap awal klip.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

MIN_PAUSE = 0.5    # jeda lebih pendek dari ini dibiarkan (ritme bicara alami)
PAD = 0.12         # sisakan sedikit napas sebelum & sesudah bicara
FRAME = 0.02       # jendela analisis energi (detik)


def _voiced_from_audio(audio: np.ndarray, sr: int) -> list[tuple[float, float]]:
    n = int(sr * FRAME)
    frames = len(audio) // n
    if frames == 0:
        return []
    rms = np.sqrt(np.mean(audio[: frames * n].reshape(frames, n) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    speech_level = np.percentile(db, 90)
    threshold = max(speech_level - 24, -60.0)
    voiced = db > threshold
    spans, start = [], None
    for i, v in enumerate(voiced):
        if v and start is None:
            start = i
        elif not v and start is not None:
            spans.append((start * FRAME, i * FRAME))
            start = None
    if start is not None:
        spans.append((start * FRAME, frames * FRAME))
    return [s for s in spans if s[1] - s[0] >= 0.06]  # buang letupan sangat pendek


def keep_segments(duration: float, words: list[dict] | None = None, clip_start: float = 0.0,
                  audio: np.ndarray | None = None, sr: int = 16000) -> list[tuple[float, float]] | None:
    """Segmen yang dipertahankan, atau None kalau tidak ada jeda berarti yang bisa dibuang."""
    if words:
        spans = [(w["start"] - clip_start, w["end"] - clip_start) for w in words]
    elif audio is not None and audio.size:
        spans = _voiced_from_audio(audio, sr)
    else:
        return None
    spans = sorted((max(0.0, s), min(duration, e)) for s, e in spans if e > 0 and s < duration)
    if not spans:
        return None

    merged: list[list[float]] = []
    for s, e in spans:
        if merged and s - merged[-1][1] < MIN_PAUSE:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    segments = []
    for s, e in merged:
        s, e = max(0.0, s - PAD), min(duration, e + PAD)
        if segments and s <= segments[-1][1]:
            segments[-1] = (segments[-1][0], e)
        else:
            segments.append((s, e))

    kept = sum(e - s for s, e in segments)
    if kept < 1.0 or duration - kept < 0.3:
        return None
    return [(round(s, 3), round(e, 3)) for s, e in segments]


def remap(t: float, segments: list[tuple[float, float]]) -> float:
    """Waktu di klip asli → waktu di klip yang sudah dipadatkan."""
    out = 0.0
    for s, e in segments:
        if t < s:
            return out
        if t <= e:
            return out + (t - s)
        out += e - s
    return out


def remap_items(items: list[dict], segments: list[tuple[float, float]] | None,
                offset: float) -> list[dict]:
    """Geser item bertimestamp absolut (kata/caption) ke timeline klip hasil. Yang jatuh di jeda dibuang."""
    result = []
    for it in items:
        s, e = it["start"] - offset, it["end"] - offset
        if segments:
            s, e = remap(s, segments), remap(e, segments)
        if e - s >= 0.05:
            result.append({**it, "start": s, "end": e})
    return result


def load_clip_audio(src: Path, start: float, end: float) -> np.ndarray:
    from .transcribe import _load_audio

    return _load_audio(src, start, end)
