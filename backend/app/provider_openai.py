"""Pemilihan klip memakai ChatGPT (OpenAI SDK resmi, Responses API).

Sama seperti Claude: model tidak menerima video, jadi input berupa transkrip bertimestamp
dari Whisper lokal plus beberapa frame sebagai gambar, dengan structured output.
"""
from __future__ import annotations

import openai

from . import pricing
from .analysis import Analysis, AnalysisError, build_prompt, transcript_text


def client(api_key: str) -> openai.OpenAI:
    return openai.OpenAI(api_key=api_key)


def list_models(api_key: str) -> list[str]:
    names = [m.id for m in client(api_key).models.list()]
    return sorted((n for n in names if n.startswith("gpt") or n.startswith("o")), reverse=True)


def analyze(api_key: str, model: str, opts: dict, duration: float, words: list[dict],
            frames: list[tuple[float, bytes]]) -> tuple[Analysis, dict]:
    from .analysis import b64

    content: list[dict] = []
    for seconds, jpeg in frames:
        content.append({"type": "input_text", "text": f"Frame pada detik {seconds:.0f}:"})
        content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64(jpeg)}"})
    content.append({"type": "input_text", "text": "Transkrip lengkap (angka dalam kurung = detik):\n"
                                                  + transcript_text(words)})
    content.append({"type": "input_text", "text": build_prompt(opts, duration, has_media=False)})

    c = client(api_key)
    try:
        resp = c.responses.parse(
            model=model,
            instructions="Kamu editor video pendek. Jawab hanya sesuai skema yang diminta.",
            input=[{"role": "user", "content": content}],
            text_format=Analysis,
            max_output_tokens=16000,
        )
    except openai.APIStatusError as e:
        raise RuntimeError(f"OpenAI API ({e.status_code}): {getattr(e, 'message', e)}") from e
    except openai.APIConnectionError as e:
        raise RuntimeError(f"Tidak bisa terhubung ke OpenAI: {e}") from e

    usage = pricing.usage_from_openai(resp, model, duration)
    if not isinstance(resp.output_parsed, Analysis):
        reason = getattr(resp, "incomplete_details", None)
        raise AnalysisError(f"ChatGPT tidak mengembalikan jawaban sesuai skema{f' ({reason})' if reason else ''}.", usage)
    return resp.output_parsed, usage
