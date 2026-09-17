"""Helper ffmpeg: probe, proxy untuk analisis, render klip, dan SRT."""
from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Awaitable, Callable

import imageio_ffmpeg

FFMPEG = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()

ProgressCb = Callable[[float], Awaitable[None]]

# Ukuran output per rasio. None = pertahankan rasio asli.
ASPECTS: dict[str, tuple[int, int] | None] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
    "original": None,
}


class FFmpegError(RuntimeError):
    pass


def _supports_filter(name: str) -> bool:
    import subprocess

    out = subprocess.run([FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return re.search(rf"\s{name}\s", out) is not None


SUBTITLES_SUPPORTED = _supports_filter("subtitles")


async def probe(path: Path) -> dict:
    """Ambil durasi, resolusi, dan ada/tidaknya audio dari output `ffmpeg -i`."""
    proc = await asyncio.create_subprocess_exec(
        FFMPEG, "-hide_banner", "-i", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    text = err.decode(errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        raise FFmpegError("File bukan video yang valid atau tidak bisa dibaca ffmpeg.")
    duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    width = height = 0
    vm = re.search(r"Stream #\S+.*Video:.*?(\d{2,5})x(\d{2,5})", text)
    if vm:
        width, height = int(vm[1]), int(vm[2])
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "has_audio": re.search(r"Stream #\S+.*Audio:", text) is not None,
    }


async def run_ffmpeg(args: list[str], duration: float, on_progress: ProgressCb | None = None,
                     cwd: Path | None = None) -> None:
    """Jalankan ffmpeg dan laporkan progres (0-1) secara realtime dari `-progress pipe:1`."""
    proc = await asyncio.create_subprocess_exec(
        FFMPEG, "-hide_banner", "-y", "-nostats", "-progress", "pipe:1", *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd,
    )
    stderr_tail: list[str] = []

    async def read_stdout():
        assert proc.stdout
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").strip()
            if line.startswith("out_time_us=") and on_progress and duration > 0:
                try:
                    secs = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                await on_progress(max(0.0, min(1.0, secs / duration)))

    async def read_stderr():
        assert proc.stderr
        async for raw in proc.stderr:
            stderr_tail.append(raw.decode(errors="replace").rstrip())
            del stderr_tail[:-20]

    await asyncio.gather(read_stdout(), read_stderr())
    code = await proc.wait()
    if code != 0:
        raise FFmpegError("ffmpeg gagal:\n" + "\n".join(stderr_tail[-8:]))
    if on_progress:
        await on_progress(1.0)


async def make_proxy(src: Path, dst: Path, duration: float, on_progress: ProgressCb) -> None:
    """Versi kecil (360p, 5fps, audio mono) supaya upload ke Gemini cepat dan hemat token."""
    await run_ffmpeg([
        "-i", str(src),
        "-vf", "scale=-2:360,fps=5",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "32",
        "-c:a", "aac", "-ac", "1", "-b:a", "64k",
        "-movflags", "+faststart", str(dst),
    ], duration, on_progress)


def crop_size(iw: int, ih: int, aspect: str) -> tuple[int, int] | None:
    """Ukuran crop terbesar dengan rasio target di dalam video sumber (genap)."""
    size = ASPECTS.get(aspect)
    if size is None or not iw or not ih:
        return None
    r = size[0] / size[1]
    cw = min(iw, int(ih * r)) // 2 * 2
    ch = min(ih, int(iw / r)) // 2 * 2
    return cw, ch


def _video_filter(aspect: str, layout: str, subtitle_file: str | None,
                  face_crop: tuple[str, int, int, int, int] | None = None) -> str:
    size = ASPECTS.get(aspect)
    if size is not None and face_crop:
        # Posisi crop berubah sepanjang waktu mengikuti wajah (perintah dari file sendcmd).
        cmd_file, cw, ch, x0, y0 = face_crop
        w, h = size
        chain = f"[0:v]sendcmd=f={cmd_file},crop=w={cw}:h={ch}:x={x0}:y={y0},scale={w}:{h},setsar=1[base]"
    elif size is None:
        chain = "[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1[base]"
    else:
        w, h = size
        if layout == "blur":
            # Video utuh di tengah, latar belakang versi blur dari video yang sama.
            chain = (
                f"[0:v]split[a][b];"
                f"[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=25:3[bg];"
                f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
            )
        else:
            r = w / h
            chain = (
                f"[0:v]crop=w='min(iw,ih*{r:.6f})':h='min(ih,iw/{r:.6f})',"
                f"scale={w}:{h},setsar=1[base]"
            )
    if subtitle_file:
        style = ("FontName=Arial,FontSize=13,Bold=1,PrimaryColour=&H00FFFFFF,"
                 "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
                 "Alignment=2,MarginV=60")
        chain += f";[base]subtitles=filename={subtitle_file}:force_style='{style}'[v]"
    else:
        chain += ";[base]null[v]"
    return chain


async def render_clip(src: Path, dst: Path, start: float, end: float, aspect: str, layout: str,
                      has_audio: bool, subtitle_path: Path | None, on_progress: ProgressCb,
                      face_crop: tuple[str, int, int, int, int] | None = None) -> None:
    duration = max(0.1, end - start)
    # cwd = folder klip, supaya nama file SRT di filter tidak perlu di-escape.
    sub_name = subtitle_path.name if subtitle_path and SUBTITLES_SUPPORTED else None
    args = [
        "-ss", f"{start:.3f}", "-i", str(src.resolve()), "-t", f"{duration:.3f}",
        "-filter_complex", _video_filter(aspect, layout, sub_name, face_crop),
        "-map", "[v]",
    ]
    if has_audio:
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k"]
    args += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", dst.name,
    ]
    await run_ffmpeg(args, duration, on_progress, cwd=dst.parent)


def _srt_time(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(captions: list[dict], clip_start: float, clip_end: float, path: Path) -> bool:
    """Tulis SRT dengan waktu relatif terhadap awal klip. Return False jika tidak ada teks."""
    entries = []
    for c in captions:
        s, e = max(c["start"], clip_start), min(c["end"], clip_end)
        text = (c.get("text") or "").strip()
        if e - s < 0.05 or not text:
            continue
        entries.append((s - clip_start, e - clip_start, text))
    if not entries:
        return False
    lines = []
    for i, (s, e, text) in enumerate(sorted(entries), start=1):
        lines += [str(i), f"{_srt_time(s)} --> {_srt_time(e)}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return True
