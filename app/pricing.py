"""Pencatatan pemakaian token Gemini dan estimasi biayanya.

Harga default diambil dari https://ai.google.dev/gemini-api/docs/pricing (diperbarui 2026-09-16),
tier Paid "Standard", USD per 1 juta token. Harga bisa ditimpa di Pengaturan, dan disimpan di
data/pricing.json. Biaya dihitung saat pemakaian terjadi (harga pada tanggal itu) dan disimpan
bersama catatan token, jadi riwayat tidak berubah kalau harga naik, kecuali dihitung ulang manual.

Proses lain (Whisper, deteksi wajah, render ffmpeg) berjalan lokal sehingga tidak ada biaya API.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime
from pathlib import Path

PRICING_FILE = Path(__file__).resolve().parent.parent / "data" / "pricing.json"
SOURCE_URL = "https://ai.google.dev/gemini-api/docs/pricing"
LONG_PROMPT = 200_000  # model Pro punya harga lebih tinggi di atas 200 ribu token prompt

# input = teks/gambar/video, audio = input audio (None = sama dengan input), cache = context caching.
# "from" = tanggal mulai berlaku; baris terakhir yang tanggalnya <= hari pemakaian yang dipakai.
_FLASH_3X = [
    {"from": "2000-01-01", "input": 0.75, "audio": None, "output": 3.75, "cache": 0.075},
    {"from": "2027-01-01", "input": 1.50, "audio": None, "output": 7.50, "cache": 0.15},
]
DEFAULT_PRICES: dict[str, list[dict]] = {
    "gemini-3.8-flash": _FLASH_3X,
    "gemini-3.7-flash": _FLASH_3X,
    "gemini-3.6-flash": _FLASH_3X,
    "gemini-3.5-flash": [{"from": "2000-01-01", "input": 1.50, "audio": None, "output": 9.00, "cache": 0.15}],
    "gemini-3.5-flash-lite": [{"from": "2000-01-01", "input": 0.30, "audio": None, "output": 2.50, "cache": None}],
    "gemini-3.1-flash-lite": [{"from": "2000-01-01", "input": 0.25, "audio": 0.50, "output": 1.50, "cache": None}],
    "gemini-3.1-pro-preview": [{"from": "2000-01-01", "input": 2.00, "audio": None, "output": 12.00, "cache": 0.20,
                                "long": {"input": 4.00, "output": 18.00, "cache": 0.40}}],
    "gemini-2.5-pro": [{"from": "2000-01-01", "input": 1.25, "audio": None, "output": 10.00, "cache": 0.125,
                        "long": {"input": 2.50, "output": 15.00, "cache": 0.25}}],
    "gemini-2.5-flash": [{"from": "2000-01-01", "input": 0.30, "audio": 1.00, "output": 2.50, "cache": None}],
    "gemini-2.5-flash-lite": [{"from": "2000-01-01", "input": 0.10, "audio": 0.30, "output": 0.40, "cache": None}],
}

# Anthropic (https://docs.claude.com/en/docs/about-claude/pricing), USD per 1 juta token.
DEFAULT_PRICES.update({
    "claude-fable-5-1": [{"from": "2000-01-01", "input": 10.00, "audio": None, "output": 50.00, "cache": 1.00}],
    "claude-fable-5": [{"from": "2000-01-01", "input": 10.00, "audio": None, "output": 50.00, "cache": 1.00}],
    "claude-opus-5": [{"from": "2000-01-01", "input": 5.00, "audio": None, "output": 25.00, "cache": 0.50}],
    "claude-opus-4-8": [{"from": "2000-01-01", "input": 5.00, "audio": None, "output": 25.00, "cache": 0.50}],
    "claude-opus-4-7": [{"from": "2000-01-01", "input": 5.00, "audio": None, "output": 25.00, "cache": 0.50}],
    "claude-opus-4-6": [{"from": "2000-01-01", "input": 5.00, "audio": None, "output": 25.00, "cache": 0.50}],
    "claude-sonnet-5": [{"from": "2000-01-01", "input": 2.00, "audio": None, "output": 10.00, "cache": 0.20}],
    "claude-sonnet-4-6": [{"from": "2000-01-01", "input": 3.00, "audio": None, "output": 15.00, "cache": 0.30}],
    "claude-haiku-4-5": [{"from": "2000-01-01", "input": 1.00, "audio": None, "output": 5.00, "cache": 0.10}],
})

# OpenAI (https://developers.openai.com/api/docs/pricing), tier Standard, USD per 1 juta token.
DEFAULT_PRICES.update({
    "gpt-6-astra": [{"from": "2000-01-01", "input": 10.00, "audio": None, "output": 50.00, "cache": 1.00}],
    "gpt-5.6-sol": [{"from": "2000-01-01", "input": 4.00, "audio": None, "output": 20.00, "cache": 0.40}],
    "gpt-5.6-terra": [{"from": "2000-01-01", "input": 2.00, "audio": None, "output": 12.00, "cache": 0.20}],
    "gpt-5.6-luna": [{"from": "2000-01-01", "input": 0.20, "audio": None, "output": 1.20, "cache": 0.02}],
    "gpt-5.5-pro": [{"from": "2000-01-01", "input": 30.00, "audio": None, "output": 180.00, "cache": None}],
    "gpt-5.5": [{"from": "2000-01-01", "input": 5.00, "audio": None, "output": 30.00, "cache": 0.50}],
    "gpt-5.4-mini": [{"from": "2000-01-01", "input": 0.75, "audio": None, "output": 4.50, "cache": 0.075}],
    "gpt-5.4-nano": [{"from": "2000-01-01", "input": 0.20, "audio": None, "output": 1.25, "cache": 0.02}],
    "gpt-5-mini": [{"from": "2000-01-01", "input": 0.25, "audio": None, "output": 2.00, "cache": 0.025}],
    "gpt-5-nano": [{"from": "2000-01-01", "input": 0.05, "audio": None, "output": 0.40, "cache": 0.005}],
})

# Perkiraan token video Gemini per detik (gambar 1 fps + audio): resolusi default vs rendah.
TOKENS_PER_SEC = {"default": 300, "low": 100}
MAX_FRAME_TOKENS = 20 * 400  # 20 frame sampel untuk Claude/ChatGPT


def settings() -> dict:
    """{"tier": "paid"|"free", "usd_idr": float, "overrides": {model: {input, audio, output}}}"""
    data = {"tier": "paid", "usd_idr": None, "overrides": {}}
    try:
        data.update(json.loads(PRICING_FILE.read_text()))
    except (OSError, json.JSONDecodeError):
        pass
    return data


def save_settings(tier: str | None = None, usd_idr: float | None = None,
                  overrides: dict[str, dict] | None = None) -> dict:
    data = settings()
    if tier in ("paid", "free"):
        data["tier"] = tier
    if usd_idr is not None:
        data["usd_idr"] = usd_idr if usd_idr > 0 else None
    if overrides is not None:
        data["overrides"] = {m: {k: float(v) for k, v in p.items() if k in ("input", "audio", "output") and v is not None}
                             for m, p in overrides.items()}
    PRICING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRICING_FILE.write_text(json.dumps(data, indent=2))
    return data


def _base_model(model: str) -> str:
    """'gemini-3.8-flash-preview-09-2026' → cocokkan ke entri tabel terpanjang yang jadi awalan."""
    matches = [m for m in DEFAULT_PRICES if model == m or model.startswith(m + "-")]
    return max(matches, key=len) if matches else model


def price_for(model: str, when: float | None = None, prompt_tokens: int = 0) -> dict | None:
    """Harga USD/1 juta token yang berlaku untuk model pada waktu tertentu."""
    cfg = settings()
    override = cfg["overrides"].get(model)
    if override and "input" in override and "output" in override:
        return {"input": override["input"], "audio": override.get("audio") or override["input"],
                "output": override["output"], "cache": None, "source": "manual"}
    rows = DEFAULT_PRICES.get(_base_model(model))
    if not rows:
        return None
    day = (datetime.fromtimestamp(when).date() if when else date.today()).isoformat()
    row = [r for r in rows if r["from"] <= day][-1]
    long = row.get("long") if prompt_tokens > LONG_PROMPT else None
    base = {**row, **(long or {})}
    return {"input": base["input"], "audio": row["audio"] or base["input"], "output": base["output"],
            "cache": base.get("cache"), "source": "default", "effective_from": row["from"]}


def usage_from_response(resp, model: str, video_seconds: float, low_res: bool) -> dict:
    """Ambil rincian token dari usage_metadata respons Gemini."""
    um = getattr(resp, "usage_metadata", None)
    by_modality = {"TEXT": 0, "VIDEO": 0, "AUDIO": 0, "IMAGE": 0}
    for d in (getattr(um, "prompt_tokens_details", None) or []):
        name = getattr(d.modality, "name", str(d.modality))
        by_modality[name] = by_modality.get(name, 0) + (d.token_count or 0)
    get = lambda f: (getattr(um, f, None) or 0) if um else 0  # noqa: E731
    return {
        "t": time.time(), "kind": "analysis", "model": model, "provider": "gemini",
        "video_seconds": round(video_seconds, 1), "low_res": low_res,
        "prompt_tokens": get("prompt_token_count"),
        "video_tokens": by_modality.get("VIDEO", 0) + by_modality.get("IMAGE", 0),
        "audio_tokens": by_modality.get("AUDIO", 0),
        "text_tokens": by_modality.get("TEXT", 0),
        "cached_tokens": get("cached_content_token_count"),
        "output_tokens": get("candidates_token_count"),
        "thoughts_tokens": get("thoughts_token_count"),
        "total_tokens": get("total_token_count"),
    }


def usage_from_anthropic(resp, model: str, video_seconds: float) -> dict:
    """Token dari respons Claude. output_tokens sudah termasuk token thinking."""
    u = resp.usage
    cached = (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
    prompt = (u.input_tokens or 0) + cached
    return {
        "t": time.time(), "kind": "analysis", "model": model, "provider": "anthropic",
        "video_seconds": round(video_seconds, 1), "low_res": False,
        "prompt_tokens": prompt, "video_tokens": 0, "audio_tokens": 0, "text_tokens": prompt,
        "cached_tokens": u.cache_read_input_tokens or 0,
        "output_tokens": u.output_tokens or 0, "thoughts_tokens": 0,
        "total_tokens": prompt + (u.output_tokens or 0),
    }


def usage_from_openai(resp, model: str, video_seconds: float) -> dict:
    """Token dari respons ChatGPT. output_tokens sudah termasuk reasoning token."""
    u = resp.usage
    cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
    reasoning = getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", 0) or 0
    prompt, output = u.input_tokens or 0, u.output_tokens or 0
    return {
        "t": time.time(), "kind": "analysis", "model": model, "provider": "openai",
        "video_seconds": round(video_seconds, 1), "low_res": False,
        "prompt_tokens": prompt, "video_tokens": 0, "audio_tokens": 0, "text_tokens": prompt - cached,
        "cached_tokens": cached, "output_tokens": output, "thoughts_tokens": 0,
        "reasoning_tokens": reasoning,
        "total_tokens": u.total_tokens or (prompt + output),
    }


def cost(entry: dict) -> dict:
    """Biaya USD sebuah catatan pemakaian. Output termasuk token 'thinking' (ditagih sebagai output)."""
    cfg = settings()
    if cfg["tier"] == "free":
        return {"usd": 0.0, "tier": "free", "price": None}
    price = price_for(entry["model"], entry["t"], entry["prompt_tokens"])
    if not price:
        return {"usd": None, "tier": "paid", "price": None}
    cached = entry.get("cached_tokens", 0)
    audio = entry.get("audio_tokens", 0)
    other_input = max(0, entry["prompt_tokens"] - audio - cached)
    usd = (other_input * price["input"] + audio * price["audio"]
           + cached * (price["cache"] or price["input"])
           + (entry["output_tokens"] + entry.get("thoughts_tokens", 0)) * price["output"]) / 1_000_000
    return {"usd": round(usd, 6), "tier": "paid", "price": price}


def with_cost(entry: dict) -> dict:
    c = cost(entry)
    return {**entry, "cost_usd": c["usd"], "price": c["price"], "tier": c["tier"]}


def estimate(duration: float, model: str, num_clips: int, max_len: int, subtitles: bool,
             provider: str = "gemini") -> dict:
    """Perkiraan sebelum analisis. Gemini menonton video; penyedia lain membaca transkrip + frame."""
    low = duration > 20 * 60
    if provider == "gemini":
        prompt = int(duration * TOKENS_PER_SEC["low" if low else "default"]) + 600
    else:
        # ~2,5 kata/detik bicara ≈ 3,5 token/detik, plus ~20 frame @ ~400 token.
        prompt = int(duration * 3.5) + MAX_FRAME_TOKENS + 600
        low = False
    # ~250 token metadata per klip, ~4 token/detik transkrip per klip, ~1500 token thinking.
    output = num_clips * (250 + (max_len * 4 if subtitles and provider == "gemini" else 0)) + 1500
    entry = {"t": time.time(), "model": model, "prompt_tokens": prompt, "audio_tokens": 0,
             "cached_tokens": 0, "output_tokens": output, "thoughts_tokens": 0}
    c = cost(entry)
    return {"prompt_tokens": prompt, "output_tokens": output, "usd": c["usd"], "tier": c["tier"],
            "low_res": low, "price": c["price"]}


def usd_idr() -> float | None:
    rate = settings().get("usd_idr") or os.environ.get("USD_IDR")
    try:
        return float(rate) if rate else None
    except ValueError:
        return None
