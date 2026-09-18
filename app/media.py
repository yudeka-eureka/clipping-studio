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
    fm = re.search(r"Stream #\S+.*Video:.*?(\d+(?:\.\d+)?) fps", text)
    return {
        "duration": duration,
        "fps": float(fm[1]) if fm else 30.0,
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


def output_size(iw: int, ih: int, aspect: str) -> tuple[int, int]:
    size = ASPECTS.get(aspect)
    return size if size else (iw // 2 * 2, ih // 2 * 2)


def snap_segments(segments: list[tuple[float, float]] | None, fps: float) -> list[tuple[float, float]] | None:
    """Bulatkan batas potongan ke grid frame supaya video & audio terpotong di titik yang sama."""
    if not segments:
        return None
    snapped = [(round(s * fps) / fps, round(e * fps) / fps) for s, e in segments]
    return [(s, e) for s, e in snapped if e > s]


def _between(segments: list[tuple[float, float]], shift: float = 0.0) -> str:
    # Rentang setengah terbuka [s, e) supaya jumlah frame/sampel per segmen tepat (e - s).
    return "+".join(f"gte(t,{s - shift:.4f})*lt(t,{e - shift:.4f})" for s, e in segments)


def _video_filter(aspect: str, layout: str, fps: float, ass_file: str | None,
                  face_crop: tuple[str, int, int, int, int] | None,
                  segments: list[tuple[float, float]] | None) -> str:
    size = ASPECTS.get(aspect)
    src = f"[0:v]fps={fps:g}"  # frame rate konstan supaya pemotongan jeda tetap sinkron
    if size is not None and face_crop:
        # Posisi crop berubah sepanjang waktu mengikuti wajah (perintah dari file sendcmd).
        cmd_file, cw, ch, x0, y0 = face_crop
        w, h = size
        chain = f"{src},sendcmd=f={cmd_file},crop=w={cw}:h={ch}:x={x0}:y={y0},scale={w}:{h},setsar=1[base]"
    elif size is None:
        chain = f"{src},scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1[base]"
    else:
        w, h = size
        if layout == "blur":
            # Video utuh di tengah, latar belakang versi blur dari video yang sama.
            chain = (
                f"{src},split[a][b];"
                f"[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=25:3[bg];"
                f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
            )
        else:
            r = w / h
            chain = (
                f"{src},crop=w='min(iw,ih*{r:.6f})':h='min(ih,iw/{r:.6f})',"
                f"scale={w}:{h},setsar=1[base]"
            )
    # Crop wajah memakai timeline asli, jadi jeda baru dibuang setelahnya.
    half_frame = 0.5 / fps  # bandingkan di tengah frame supaya tidak goyah karena pembulatan pts
    tail = f"select='{_between(segments, half_frame)}',setpts=N/FRAME_RATE/TB" if segments else "null"
    if ass_file:
        tail += f",subtitles=filename={ass_file}"
    return chain + f";[base]{tail}[v]"


async def render_clip(src: Path, dst: Path, start: float, end: float, aspect: str, layout: str,
                      has_audio: bool, fps: float, ass_path: Path | None, on_progress: ProgressCb,
                      face_crop: tuple[str, int, int, int, int] | None = None,
                      segments: list[tuple[float, float]] | None = None) -> None:
    duration = max(0.1, end - start)
    segments = snap_segments(segments, fps)
    out_duration = sum(e - s for s, e in segments) if segments else duration
    # cwd = folder klip, supaya nama file di filter tidak perlu di-escape.
    ass_name = ass_path.name if ass_path and SUBTITLES_SUPPORTED else None
    graph = _video_filter(aspect, layout, fps, ass_name, face_crop, segments)
    if has_audio:
        # Audio dipecah jadi potongan kecil (256 sampel) supaya titik potongnya presisi.
        audio = (f"asetnsamples=n=256:p=0,aselect='{_between(segments)}',asetpts=N/SR/TB"
                 if segments else "anull")
        graph += f";[0:a:0]{audio}[a]"
    args = [
        "-ss", f"{start:.3f}", "-i", str(src.resolve()), "-t", f"{duration:.3f}",
        "-filter_complex", graph, "-map", "[v]",
    ]
    if has_audio:
        args += ["-map", "[a]", "-c:a", "aac", "-b:a", "160k"]
    args += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", dst.name,
    ]
    await run_ffmpeg(args, out_duration, on_progress, cwd=dst.parent)


def _ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_text(text: str) -> str:
    return (text.replace("\\", "/").replace("{", "(").replace("}", ")")
            .replace("\n", " ").strip())


def write_ass(path: Path, width: int, height: int, duration: float, title: str | None,
              captions: list[dict]) -> bool:
    """Judul di atas + subtitle di bawah, dalam satu file ASS seukuran video output.

    Posisi disesuaikan dengan area aman TikTok/Reels/Shorts (tidak tertutup tombol & keterangan).
    """
    portrait = height > width
    unit = min(width, height) / 1080
    title_size, sub_size = round(64 * unit), round(72 * unit)
    title_margin_v = round(height * (0.11 if portrait else 0.05))
    sub_margin_v = round(height * (0.24 if portrait else 0.08))
    side = round(width * 0.08)
    # Warna ASS: &HAABBGGRR. Judul = teks hitam di kotak putih; subtitle = putih bergaris hitam.
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Arial,{title_size},&H00111111,&H00111111,&H00FFFFFF,&H00000000,-1,0,0,0,100,100,0,0,3,{round(14 * unit)},0,8,{side},{side},{title_margin_v},1
Style: Caption,Arial,{sub_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{round(6 * unit)},{round(2 * unit)},2,{side},{side},{sub_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    if title and title.strip():
        events.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration + 1)},Title,,0,0,0,,{_ass_text(title)}")
    for c in captions:
        text = _ass_text(c.get("text") or "")
        if text and c["end"] - c["start"] >= 0.05:
            events.append(f"Dialogue: 0,{_ass_time(c['start'])},{_ass_time(c['end'])},Caption,,0,0,0,,{text}")
    if not events:
        return False
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return True


def _srt_time(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(captions: list[dict], path: Path) -> bool:
    """Tulis SRT dari caption yang waktunya sudah relatif terhadap klip hasil."""
    entries = sorted((c["start"], c["end"], (c.get("text") or "").strip()) for c in captions)
    entries = [e for e in entries if e[1] - e[0] >= 0.05 and e[2]]
    if not entries:
        return False
    lines = []
    for i, (s, e, text) in enumerate(entries, start=1):
        lines += [str(i), f"{_srt_time(s)} --> {_srt_time(e)}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return True
