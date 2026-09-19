"""Pemilihan klip memakai Claude (Anthropic SDK resmi).

Claude tidak menerima video, jadi input berupa transkrip bertimestamp dari Whisper lokal
plus beberapa frame sebagai gambar. Jawaban dipaksa sesuai skema lewat structured output.
"""
from __future__ import annotations

import anthropic

from . import pricing
from .analysis import Analysis, AnalysisError, build_prompt, transcript_text


def client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def list_models(api_key: str) -> list[str]:
    return [m.id for m in client(api_key).models.list()]


def analyze(api_key: str, model: str, opts: dict, duration: float, words: list[dict],
            frames: list[tuple[float, bytes]]) -> tuple[Analysis, dict]:
    from .analysis import b64

    content: list[dict] = []
    for seconds, jpeg in frames:
        content.append({"type": "text", "text": f"Frame pada detik {seconds:.0f}:"})
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64(jpeg)}})
    content.append({"type": "text", "text": "Transkrip lengkap (angka dalam kurung = detik):\n"
                                            + transcript_text(words)})
    content.append({"type": "text", "text": build_prompt(opts, duration, has_media=False)})

    c = client(api_key)
    try:
        resp = c.messages.parse(
            model=model,
            max_tokens=16000,
            system="Kamu editor video pendek. Jawab hanya sesuai skema yang diminta.",
            messages=[{"role": "user", "content": content}],
            output_format=Analysis,
            output_config={"effort": "medium"},
        )
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude API ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError(f"Tidak bisa terhubung ke Claude: {e}") from e

    usage = pricing.usage_from_anthropic(resp, model, duration)
    if resp.stop_reason == "refusal":
        detail = getattr(resp.stop_details, "explanation", "") or ""
        raise AnalysisError(f"Claude menolak permintaan ini. {detail}".strip(), usage)
    if not isinstance(resp.parsed_output, Analysis):
        raise AnalysisError("Claude tidak mengembalikan jawaban sesuai skema.", usage)
    return resp.parsed_output, usage
