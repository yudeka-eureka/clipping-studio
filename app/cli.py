"""Mode command line: semua fitur Clipping Studio tanpa membuka web.

Dibuat supaya bisa dipakai AI agent / skrip: setiap perintah menerima argumen biasa,
menulis hasil terstruktur ke stdout (pakai --json), dan menulis progres ke stderr.
Kode keluar 0 = berhasil, 1 = gagal (alasannya ada di pesan error / field "error").

Contoh:
    clip run podcast.mp4 --clips 3 --json
    clip cut podcast.mp4 --start 90 --end 140 --title "Bagian menarik"
    clip publish 20260917-104219-06e78f a1b2c3d4 --channel ch_xxx --mode addToQueue
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
load_dotenv(ENV_FILE)

from . import analysis, branding, buffer, facetrack, media, mediahost, pipeline, pricing, transcribe  # noqa: E402
from .jobs import hub, store  # noqa: E402

URL_RE = re.compile(r"^https?://")


# ---------- keluaran ----------

def emit(args, data: dict | list, text: str = "") -> None:
    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")
    elif text:
        print(text)


def fail(message: str, args=None) -> None:
    if args and args.json:
        json.dump({"ok": False, "error": message}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Gagal: {message}", file=sys.stderr)
    raise SystemExit(1)


def hms(t: float) -> str:
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def clip_view(job: dict, clip: dict) -> dict:
    base = store.dir(job["id"])
    return {
        "id": clip["id"], "title": clip["title"], "start": clip["start"], "end": clip["end"],
        "duration": round(clip["end"] - clip["start"], 2), "duration_out": clip.get("duration_out"),
        "status": clip["status"], "error": clip.get("error"), "score": clip.get("score"),
        "hook": clip.get("hook"), "reason": clip.get("reason"), "hashtags": clip.get("hashtags", []),
        "captions": len(clip.get("captions") or []),
        "file": str(base / clip["file"]) if clip.get("file") else None,
        "srt": str(base / clip["srt"]) if clip.get("srt") else None,
        "publish": clip.get("publish"),
    }


def job_view(job: dict, logs: bool = False) -> dict:
    usage = job.get("usage") or []
    view = {
        "id": job["id"], "name": job["name"], "status": job["status"], "stage": job["stage"],
        "error": job.get("error"), "created_at": job["created_at"], "options": job["options"],
        "source": str(store.dir(job["id"]) / job["source"]) if job.get("source") else None,
        "meta": job.get("meta"), "summary": job.get("summary"),
        "usage": {"calls": len(usage),
                  "prompt_tokens": sum(u["prompt_tokens"] for u in usage),
                  "output_tokens": sum(u["output_tokens"] + u.get("thoughts_tokens", 0) for u in usage),
                  "cost_usd": sum(u.get("cost_usd") or 0 for u in usage) if usage else None},
        "clips": [clip_view(job, c) for c in job["clips"]],
    }
    if logs:
        view["logs"] = job["logs"]
    return view


def job_text(job: dict) -> str:
    lines = [f"{job['id']}  {job['name']}", f"  status : {job['status']} — {job['stage']}"]
    if job.get("error"):
        lines.append(f"  error  : {job['error']}")
    if job.get("summary"):
        lines.append(f"  ringkas: {job['summary']}")
    for c in job["clips"]:
        out = f" → {c['duration_out']:.1f}s" if c.get("duration_out") else ""
        score = f" 🔥{c['score']}" if c.get("score") is not None else ""
        lines.append(f"  [{c['id']}] {hms(c['start'])}–{hms(c['end'])}{out}{score} {c['status']}  {c['title']}")
        if c.get("file"):
            lines.append(f"        {store.dir(job['id']) / c['file']}")
        if c.get("error"):
            lines.append(f"        error: {c['error']}")
    usage = job.get("usage") or []
    if usage:
        usd = sum(u.get("cost_usd") or 0 for u in usage)
        lines.append(f"  AI     : {sum(u['prompt_tokens'] for u in usage):,} token input, ≈ ${usd:.4f}".replace(",", "."))
    return "\n".join(lines)


def watch_progress(enabled: bool) -> None:
    """Tampilkan progres realtime ke stderr (stdout tetap bersih untuk data)."""
    if not enabled:
        return
    last = [0.0]

    def listen(ev: dict) -> None:
        now = time.monotonic()
        if ev["type"] == "log":
            print(f"  {ev['line']}", file=sys.stderr, flush=True)
        elif ev["type"] == "progress" and now - last[0] > 0.5:
            last[0] = now
            stage = ev.get("stage") or ""
            print(f"  … {stage} {ev['progress'] * 100:.0f}%", file=sys.stderr, flush=True)

    hub.listeners.append(listen)


# ---------- util ----------

def find_job(ident: str, args) -> dict:
    if ident in ("last", "terakhir"):
        jobs = sorted(store.jobs.values(), key=lambda j: j["created_at"])
        if not jobs:
            fail("Belum ada proyek.", args)
        return jobs[-1]
    if ident in store.jobs:
        return store.jobs[ident]
    matches = [j for j in store.jobs.values() if j["id"].startswith(ident) or j["name"] == ident]
    if len(matches) == 1:
        return matches[0]
    fail(f"Proyek '{ident}' tidak ditemukan." if not matches else f"'{ident}' cocok dengan {len(matches)} proyek.", args)


def find_clip(job: dict, ident: str, args) -> dict:
    clip = store.clip(job, ident) or next((c for c in job["clips"] if c["id"].startswith(ident)), None)
    if not clip:
        fail(f"Klip '{ident}' tidak ada di proyek {job['id']}.", args)
    return clip


def build_options(args) -> dict:
    return {
        "num_clips": max(1, min(15, args.clips)), "min_len": max(5, args.min_len),
        "max_len": max(args.min_len + 5, args.max_len), "aspect": args.aspect, "layout": args.layout,
        "subtitles": not args.no_subtitles, "remove_silence": not args.no_trim,
        "show_title": not args.no_title, "instructions": args.instructions or "",
    }


async def source_job(args, opts: dict) -> tuple[dict, Path | None, str | None]:
    """Buat proyek baru dari file lokal atau link."""
    src = args.source
    if URL_RE.match(src):
        return store.create(src, "url", opts), None, src
    path = Path(src).expanduser().resolve()
    if not path.is_file():
        fail(f"File tidak ditemukan: {path}", args)
    job = store.create(path.name, "upload", opts)
    dest = store.dir(job["id"]) / f"source{path.suffix.lower() or '.mp4'}"
    if args.link:
        try:
            os.link(path, dest)  # hemat disk kalau satu drive
        except OSError:
            shutil.copy2(path, dest)
    else:
        await asyncio.to_thread(shutil.copy2, path, dest)
    return job, dest, None


# ---------- perintah ----------

async def cmd_doctor(args) -> None:
    whisper_ok = {m: transcribe.is_downloaded(m) for m in transcribe.MODELS}
    info = {
        "ffmpeg": media.FFMPEG, "subtitles_supported": media.SUBTITLES_SUPPORTED,
        "face_tracking": facetrack.available(),
        "provider": analysis.provider(), "model": analysis.model_name(),
        "providers": {n: {"label": spec["label"], "video": spec["video"],
                          "key": bool(os.environ.get(spec["env"], "").strip()),
                          "model": analysis.model_name(n)}
                      for n, spec in analysis.PROVIDERS.items()},
        "whisper_model": transcribe.model_name(), "whisper_downloaded": whisper_ok,
        "whisper_language": transcribe.language(),
        "buffer_key": bool(os.environ.get("BUFFER_API_KEY", "").strip()),
        "media_host": mediahost.provider(),
        "media_host_missing": [mediahost.LABELS[f] for f in mediahost.missing()],
        "pricing_tier": pricing.settings()["tier"], "usd_idr": pricing.usd_idr(),
        "data_dir": str(store.dir("")), "jobs": len(store.jobs),
    }
    mark = lambda ok: "✓" if ok else "✗"  # noqa: E731
    text = "\n".join([
        f"{mark(True)} ffmpeg            {info['ffmpeg']}",
        f"{mark(media.SUBTITLES_SUPPORTED)} subtitle (libass)",
        f"{mark(info['face_tracking'])} deteksi wajah (mediapipe)",
        *[f"{mark(p['key'])} {p['label']:<18}{'(aktif) ' if n == info['provider'] else ''}model: {p['model']}"
          + ("" if p["video"] else "  [pakai transkrip lokal]")
          for n, p in info["providers"].items()],
        f"{mark(whisper_ok[transcribe.model_name()])} model Whisper      {transcribe.model_name()} (bahasa: {info['whisper_language']})",
        f"{mark(info['buffer_key'])} Buffer API key",
        f"{mark(not info['media_host_missing'])} hosting video      {info['media_host']}"
        + (f" (kurang: {', '.join(info['media_host_missing'])})" if info["media_host_missing"] else ""),
        f"  data               {info['data_dir']} ({info['jobs']} proyek)",
    ])
    emit(args, info, text)


async def cmd_run(args) -> None:
    opts = build_options(args)
    job, upload, url = await source_job(args, opts)
    watch_progress(not args.quiet)
    await pipeline.run(job, upload, url)
    emit(args, job_view(job), job_text(job))
    if job["status"] == "error":
        raise SystemExit(1)


async def cmd_cut(args) -> None:
    watch_progress(not args.quiet)
    if args.job:
        job = find_job(args.job, args)
        if not job.get("source"):
            fail("Proyek ini belum punya video sumber.", args)
    else:
        if not args.source:
            fail("Sebutkan file/link video, atau --job untuk memakai proyek yang sudah ada.", args)
        job, upload, url = await source_job(args, build_options(args))
        await pipeline.prepare_source(job, upload, url)
    duration = job["meta"]["duration"]
    end = args.end if args.end is not None else duration
    if not (0 <= args.start < end <= duration + 0.5):
        fail(f"Rentang tidak valid untuk video {duration:.1f} detik.", args)
    clip = pipeline.new_clip(job, round(args.start, 2), round(end, 2),
                             args.title or f"Klip manual {len(job['clips']) + 1}")
    await pipeline.render(job, clip)
    await store.update(job, status="done", stage="Selesai", progress=1)
    emit(args, clip_view(job, clip), job_text(job))
    if clip["status"] != "ready":
        raise SystemExit(1)


async def cmd_rerender(args) -> None:
    job = find_job(args.job, args)
    for field, value in (("aspect", args.aspect), ("layout", args.layout)):
        if value:
            job["options"][field] = value
    for field, flag in (("subtitles", args.no_subtitles), ("remove_silence", args.no_trim), ("show_title", args.no_title)):
        if flag:
            job["options"][field] = False
    clips = [find_clip(job, c, args) for c in args.clips] if args.clips else list(job["clips"])
    if not clips:
        fail("Proyek ini belum punya klip.", args)
    watch_progress(not args.quiet)
    for clip in clips:
        if args.start is not None:
            clip["start"] = args.start
        if args.end is not None:
            clip["end"] = args.end
        if args.title:
            clip["title"] = args.title
        await pipeline.render(job, clip)
    emit(args, job_view(job), job_text(job))
    if any(c["status"] != "ready" for c in clips):
        raise SystemExit(1)


async def cmd_jobs(args) -> None:
    jobs = sorted(store.jobs.values(), key=lambda j: j["created_at"], reverse=True)[: args.limit]
    emit(args, [job_view(j) for j in jobs],
         "\n".join(f"{j['id']}  {j['status']:<9} {len(j['clips'])} klip  {j['name'][:60]}" for j in jobs)
         or "Belum ada proyek.")


async def cmd_show(args) -> None:
    job = find_job(args.job, args)
    emit(args, job_view(job, logs=args.logs), job_text(job) +
         ("\n  log:\n" + "\n".join(f"    {l['line']}" for l in job["logs"]) if args.logs else ""))


async def cmd_rm(args) -> None:
    job = find_job(args.job, args)
    await store.delete(job["id"])
    emit(args, {"ok": True, "deleted": job["id"]}, f"Proyek {job['id']} dihapus.")


async def cmd_transcribe(args) -> None:
    if args.job:
        job = find_job(args.job, args)
        src = store.dir(job["id"]) / job["source"]
    else:
        src = Path(args.source).expanduser().resolve()
        if not src.is_file():
            fail(f"File tidak ditemukan: {src}", args)
    meta = await media.probe(src)
    end = args.end if args.end is not None else meta["duration"]
    words = await asyncio.to_thread(transcribe.transcribe_words, src, args.start, end, "")
    captions = transcribe.build_captions(words)
    if args.format == "json":
        emit(args, {"words": words, "captions": captions})
    elif args.format == "srt":
        import tempfile

        rel = [{**c, "start": c["start"] - args.start, "end": c["end"] - args.start} for c in captions]
        with tempfile.NamedTemporaryFile("r+", suffix=".srt") as tmp:
            media.write_srt(rel, Path(tmp.name))
            sys.stdout.write(Path(tmp.name).read_text())
    else:
        for c in captions:
            print(f"[{hms(c['start'])} → {hms(c['end'])}] {c['text']}")


async def cmd_estimate(args) -> None:
    src = Path(args.source).expanduser().resolve()
    duration = (await media.probe(src))["duration"] if src.is_file() else args.duration
    if not duration:
        fail("Sebutkan file video yang ada, atau --duration dalam detik (untuk link).", args)
    provider = analysis.provider()
    est = pricing.estimate(duration, analysis.model_name(), args.clips, args.max_len,
                           not args.no_subtitles, provider)
    rate = pricing.usd_idr()
    money = "gratis (tier Free)" if est["tier"] == "free" else "harga belum diatur" if est["usd"] is None else (
        f"≈ ${est['usd']:.4f}" + (f" (Rp{est['usd'] * rate:,.0f})".replace(",", ".") if rate else ""))
    emit(args, {**est, "model": analysis.model_name(), "provider": provider, "duration": duration, "usd_idr": rate},
         f"Video {duration / 60:.1f} menit → ~{est['prompt_tokens']:,} token input + ~{est['output_tokens']:,} output: {money}".replace(",", "."))


async def cmd_usage(args) -> None:
    total = {"calls": 0, "prompt_tokens": 0, "output_tokens": 0, "usd": 0.0}
    rows = []
    for job in sorted(store.jobs.values(), key=lambda j: j["created_at"], reverse=True):
        entries = job.get("usage") or []
        if not entries:
            continue
        usd = sum(e.get("cost_usd") or 0 for e in entries)
        row = {"id": job["id"], "name": job["name"], "calls": len(entries),
               "prompt_tokens": sum(e["prompt_tokens"] for e in entries),
               "output_tokens": sum(e["output_tokens"] + e.get("thoughts_tokens", 0) for e in entries),
               "usd": round(usd, 6), "model": entries[-1]["model"]}
        rows.append(row)
        for k in ("calls", "prompt_tokens", "output_tokens"):
            total[k] += row[k]
        total["usd"] += usd
    rate = pricing.usd_idr()
    text = "\n".join(f"{r['id']}  {r['prompt_tokens']:>9,} in  {r['output_tokens']:>7,} out  ${r['usd']:.4f}  {r['name'][:40]}"
                     for r in rows).replace(",", ".")
    text += f"\nTOTAL: {total['calls']} analisis, ${total['usd']:.4f}" + (f" ≈ Rp{total['usd'] * rate:,.0f}".replace(",", ".") if rate else "")
    emit(args, {"total": total, "projects": rows, "usd_idr": rate, "tier": pricing.settings()["tier"]},
         text if rows else "Belum ada pemakaian AI tercatat.")


async def cmd_channels(args) -> None:
    try:
        channels, errors = await asyncio.to_thread(buffer.channels_and_errors, args.refresh, args.account)
    except Exception as e:  # noqa: BLE001
        fail(str(e), args)
    text = "\n".join(
        f"{c['key']:<28} {c['service']:<12} {c.get('displayName') or c['name']} [{c['account']}]"
        + ("  (terputus)" if c["isDisconnected"] else "  (terkunci)" if c["isLocked"] else "")
        for c in channels) or "Belum ada channel di Buffer."
    if errors:
        text += "\n⚠️ " + "\n⚠️ ".join(errors)
    emit(args, {"channels": channels, "errors": errors}, text)


async def cmd_accounts(args) -> None:
    try:
        if args.add:
            added = await asyncio.to_thread(
                buffer.add_account, args.label or "",
                args.key or sys.stdin.readline().strip())
            if not args.json:
                print(f"Akun “{added['label']}” ditambahkan ({', '.join(added['organizations'])}).")
        elif args.remove:
            if await asyncio.to_thread(buffer.remove_account, args.remove):
                _set_env("BUFFER_API_KEY", "")
        elif args.rename:
            buffer.rename_account(args.rename, args.label or "")
    except Exception as e:  # noqa: BLE001
        fail(str(e), args)
    data = buffer.public_accounts()
    emit(args, {"accounts": data},
         "\n".join(f"{a['id']:<10} {a['label']:<24} key {a['key_hint']}" for a in data)
         or "Belum ada akun Buffer. Tambahkan dengan: clip accounts --add --label 'Nama'")


async def cmd_publish(args) -> None:
    job = find_job(args.job, args)
    clip = find_clip(job, args.clip, args)
    if clip["status"] != "ready":
        fail("Klip belum selesai dirender.", args)
    if mediahost.missing():
        fail(mediahost.missing_message(), args)
    try:
        known = {c["id"]: c for c in await asyncio.to_thread(buffer.list_channels)}
    except Exception as e:  # noqa: BLE001
        fail(str(e), args)
    channels = [known[c] for c in args.channel if c in known]
    if len(channels) != len(args.channel):
        fail(f"Channel tidak dikenal: {', '.join(c for c in args.channel if c not in known)}", args)
    blocked = [c for c in channels if c["isDisconnected"] or c["isLocked"]]
    if blocked:
        fail(f"Channel terputus/terkunci di Buffer: {', '.join(c['name'] for c in blocked)}", args)
    if args.mode == "customScheduled" and not args.at:
        fail("Mode customScheduled butuh --at (waktu ISO, misal 2026-10-01T09:00:00+07:00).", args)
    text = args.text or "\n\n".join(x for x in [clip["title"], clip.get("hook"),
                                                " ".join(f"#{t.lstrip('#')}" for t in clip.get("hashtags", []))] if x)
    watch_progress(not args.quiet)
    await pipeline.publish(job, clip, channels, text, args.mode, args.at)
    result = clip["publish"]
    emit(args, result, "\n".join(
        f"{'✓' if r['ok'] else '✗'} {r['service']:<12} {r['channel']}: {r.get('status') or r.get('error')}"
        for r in result["results"]))
    if result["status"] != "done":
        raise SystemExit(1)


async def cmd_publish_status(args) -> None:
    job = find_job(args.job, args)
    clip = find_clip(job, args.clip, args)
    pub = clip.get("publish")
    if not pub:
        fail("Klip ini belum pernah diposting.", args)
    ids = [r["post_id"] for r in pub["results"] if r.get("ok")]
    try:
        statuses = await asyncio.to_thread(buffer.post_statuses, ids)
    except Exception as e:  # noqa: BLE001
        fail(str(e), args)
    for r in pub["results"]:
        st = statuses.get(r.get("post_id"))
        if st:
            r.update(status=st["status"], due_at=st.get("dueAt"), sent_at=st.get("sentAt"),
                     link=st.get("externalLink"), error=(st.get("error") or {}).get("message"))
    await store.publish(job)
    emit(args, pub, "\n".join(f"{r['service']:<12} {r['channel']}: {r.get('status') or r.get('error')}"
                              f"{'  ' + r['link'] if r.get('link') else ''}" for r in pub["results"]))


SETTABLE = ["AI_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
            "OPENAI_API_KEY", "OPENAI_MODEL", "WHISPER_MODEL", "WHISPER_LANGUAGE", "BUFFER_API_KEY",
            "MEDIA_HOST", *mediahost.FIELDS["cloudinary"], *mediahost.FIELDS["r2"]]


def _set_env(name: str, value: str) -> None:
    os.environ[name] = value
    ENV_FILE.touch(mode=0o600, exist_ok=True)
    set_key(str(ENV_FILE), name, value)


async def cmd_config(args) -> None:
    if args.name:
        name = args.name.upper()
        if name == "AI_PROVIDER" and (args.value or "").strip() not in analysis.PROVIDERS:
            fail(f"Penyedia AI harus salah satu dari: {', '.join(analysis.PROVIDERS)}", args)
        if name not in SETTABLE:
            fail(f"Nama tidak dikenal. Pilihan: {', '.join(SETTABLE)}", args)
        # Nilai lewat stdin supaya kredensial tidak tersimpan di riwayat shell.
        value = args.value if args.value is not None else sys.stdin.readline().strip()
        if not value:
            fail("Nilai kosong.", args)
        _set_env(name, value)
    hint = lambda v: (f"…{v[-4:]}" if v else "")  # noqa: E731
    secrets = {"GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BUFFER_API_KEY", *mediahost.SECRET_FIELDS}
    data = {n: (hint(os.environ.get(n, "")) if n in secrets else os.environ.get(n, "")) for n in SETTABLE}
    emit(args, {"env_file": str(ENV_FILE), "values": data},
         "\n".join(f"{n:<26} {v or '(kosong)'}" for n, v in data.items()))


async def cmd_provider(args) -> None:
    if args.name:
        os.environ["AI_PROVIDER"] = args.name
        ENV_FILE.touch(mode=0o600, exist_ok=True)
        set_key(str(ENV_FILE), "AI_PROVIDER", args.name)
        if args.model:
            spec = analysis.PROVIDERS[args.name]
            os.environ[spec["model_env"]] = args.model
            set_key(str(ENV_FILE), spec["model_env"], args.model)
    data = {n: {"label": spec["label"], "model": analysis.model_name(n),
                "key": bool(os.environ.get(spec["env"], "").strip()), "video": spec["video"],
                "active": n == analysis.provider()}
            for n, spec in analysis.PROVIDERS.items()}
    emit(args, {"provider": analysis.provider(), "providers": data},
         "\n".join(f"{'*' if p['active'] else ' '} {n:<10} {p['label']:<18} {p['model']}"
                   + ("" if p["key"] else "  (API key belum diisi)") for n, p in data.items()))


async def cmd_branding(args) -> None:
    try:
        for kind, file in (("logo", args.logo), ("outro", args.outro)):
            if file:
                path = Path(file).expanduser().resolve()
                if not path.is_file():
                    fail(f"File tidak ditemukan: {path}", args)
                branding.save_file(kind, path, path.name)
        if args.remove_logo:
            branding.clear("logo")
        if args.remove_outro:
            branding.clear("outro")
        branding.update("logo", position=args.position, size=args.size, opacity=args.opacity,
                        margin=args.margin,
                        enabled=False if args.logo_off else (True if args.logo_on else None))
        branding.update("outro", duration=args.outro_duration,
                        keep_audio=False if args.outro_mute else None,
                        enabled=False if args.outro_off else (True if args.outro_on else None))
    except ValueError as e:
        fail(str(e), args)
    data = branding.public()
    lg, ou = data["logo"], data["outro"]
    text = (f"logo  : {lg['file'] or '(belum ada)'}"
            + (f" · {'aktif' if lg['enabled'] else 'nonaktif'} · {lg['position']} · {lg['size']}% "
               f"· opacity {lg['opacity']} · margin {lg['margin']}%" if lg["file"] else "")
            + f"\noutro : {ou['file'] or '(belum ada)'}"
            + (f" · {'aktif' if ou['enabled'] else 'nonaktif'}"
               + (f" · {ou['duration']} dtk" if not ou["is_video"] else
                  f" · video{'' if ou['keep_audio'] else ', audio dimatikan'}") if ou["file"] else ""))
    emit(args, data, text)


async def cmd_serve(args) -> None:
    import uvicorn

    print(f"Web UI: http://127.0.0.1:{args.port}", file=sys.stderr)
    config = uvicorn.Config("app.main:app", host=args.host, port=args.port, log_level="warning")
    await uvicorn.Server(config).serve()


# ---------- argumen ----------

def build_parser() -> argparse.ArgumentParser:
    # Flag umum bisa ditulis sebelum atau sesudah nama perintah: `clip --json run x` = `clip run x --json`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="tulis hasil sebagai JSON ke stdout")
    common.add_argument("--quiet", "-q", action="store_true", help="jangan tampilkan progres di stderr")
    p = argparse.ArgumentParser(prog="clip", parents=[common],
                                description="Clipping Studio tanpa web: potong video jadi klip pendek dengan AI.")
    sub = p.add_subparsers(dest="command", required=True, parser_class=lambda **kw: argparse.ArgumentParser(parents=[common], **kw))

    def clip_opts(sp, required_source=True):
        if required_source:
            sp.add_argument("source", help="file video lokal atau link (YouTube dll)")
        sp.add_argument("--clips", type=int, default=3, help="jumlah klip yang dipilih AI (default 3)")
        sp.add_argument("--min-len", dest="min_len", type=int, default=30, help="durasi klip minimal, detik")
        sp.add_argument("--max-len", dest="max_len", type=int, default=90, help="durasi klip maksimal, detik")
        sp.add_argument("--aspect", default="9:16", choices=list(media.ASPECTS))
        sp.add_argument("--layout", default="face", choices=["face", "crop", "blur"],
                        help="face = crop mengikuti pembicara (default)")
        sp.add_argument("--no-subtitles", action="store_true", help="tanpa subtitle")
        sp.add_argument("--no-trim", action="store_true", help="jangan buang jeda diam")
        sp.add_argument("--no-title", action="store_true", help="jangan tempel judul di atas video")
        sp.add_argument("--instructions", help="instruksi tambahan untuk AI")
        sp.add_argument("--link", action="store_true", help="hardlink file sumber (hemat disk) alih-alih menyalin")

    sp = sub.add_parser("doctor", help="cek ffmpeg, model, API key, dan hosting")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("run", help="proses penuh: AI pilih momen → render semua klip")
    clip_opts(sp)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("cut", help="potong satu klip pada waktu tertentu (tanpa AI)")
    sp.add_argument("source", nargs="?", help="file/link video (boleh kosong kalau pakai --job)")
    sp.add_argument("--job", help="pakai video sumber proyek yang sudah ada")
    sp.add_argument("--start", type=float, required=True, help="detik mulai")
    sp.add_argument("--end", type=float, help="detik selesai (default sampai akhir video)")
    sp.add_argument("--title", help="judul klip (tampil di atas video)")
    clip_opts(sp, required_source=False)
    sp.set_defaults(func=cmd_cut)

    sp = sub.add_parser("rerender", help="render ulang klip dengan format/waktu berbeda")
    sp.add_argument("job")
    sp.add_argument("clips", nargs="*", help="id klip (kosong = semua klip)")
    sp.add_argument("--start", type=float)
    sp.add_argument("--end", type=float)
    sp.add_argument("--title")
    sp.add_argument("--aspect", choices=list(media.ASPECTS))
    sp.add_argument("--layout", choices=["face", "crop", "blur"])
    sp.add_argument("--no-subtitles", action="store_true")
    sp.add_argument("--no-trim", action="store_true")
    sp.add_argument("--no-title", action="store_true")
    sp.set_defaults(func=cmd_rerender)

    sp = sub.add_parser("jobs", help="daftar proyek")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_jobs)

    sp = sub.add_parser("show", help="detail proyek dan klipnya")
    sp.add_argument("job", help="id proyek, awalan id, atau 'last'")
    sp.add_argument("--logs", action="store_true")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("rm", help="hapus proyek beserta filenya")
    sp.add_argument("job")
    sp.set_defaults(func=cmd_rm)

    sp = sub.add_parser("transcribe", help="transkrip lokal (Whisper) dengan waktu per kata")
    sp.add_argument("source", nargs="?")
    sp.add_argument("--job")
    sp.add_argument("--start", type=float, default=0.0)
    sp.add_argument("--end", type=float)
    sp.add_argument("--format", default="text", choices=["text", "srt", "json"])
    sp.set_defaults(func=cmd_transcribe)

    sp = sub.add_parser("estimate", help="perkiraan token & biaya AI sebelum proses")
    sp.add_argument("source", nargs="?", default="")
    sp.add_argument("--duration", type=float, help="durasi video (detik) kalau sumbernya link")
    sp.add_argument("--clips", type=int, default=3)
    sp.add_argument("--max-len", dest="max_len", type=int, default=90)
    sp.add_argument("--no-subtitles", action="store_true")
    sp.set_defaults(func=cmd_estimate)

    sp = sub.add_parser("usage", help="pemakaian token & biaya AI")
    sp.set_defaults(func=cmd_usage)

    sp = sub.add_parser("channels", help="daftar channel media sosial di semua akun Buffer")
    sp.add_argument("--refresh", action="store_true")
    sp.add_argument("--account", help="batasi ke satu akun (id dari 'clip accounts')")
    sp.set_defaults(func=cmd_channels)

    sp = sub.add_parser("accounts", help="kelola akun Buffer (boleh lebih dari satu)")
    sp.add_argument("--add", action="store_true", help="tambah akun; API key dibaca dari stdin kalau --key kosong")
    sp.add_argument("--key", help="Buffer API key (hindari: tersimpan di riwayat shell)")
    sp.add_argument("--label", help="nama akun")
    sp.add_argument("--remove", metavar="ID", help="hapus akun")
    sp.add_argument("--rename", metavar="ID", help="ganti nama akun (pakai --label)")
    sp.set_defaults(func=cmd_accounts)

    sp = sub.add_parser("publish", help="kirim klip ke media sosial lewat Buffer")
    sp.add_argument("job")
    sp.add_argument("clip")
    sp.add_argument("--channel", action="append", required=True,
                    help="channel: 'idAkun:idChannel' dari 'clip channels' (boleh diulang)")
    sp.add_argument("--mode", default="addToQueue",
                    choices=["addToQueue", "shareNext", "shareNow", "customScheduled"])
    sp.add_argument("--at", help="waktu ISO untuk --mode customScheduled")
    sp.add_argument("--text", help="caption (default: judul + hook + hashtag)")
    sp.set_defaults(func=cmd_publish)

    sp = sub.add_parser("publish-status", help="cek status post di Buffer")
    sp.add_argument("job")
    sp.add_argument("clip")
    sp.set_defaults(func=cmd_publish_status)

    sp = sub.add_parser("config", help="lihat / ubah pengaturan di .env")
    sp.add_argument("name", nargs="?", help=f"salah satu dari: {', '.join(SETTABLE)}")
    sp.add_argument("value", nargs="?", help="nilai; kosongkan untuk membacanya dari stdin")
    sp.set_defaults(func=cmd_config)

    sp = sub.add_parser("provider", help="lihat / ganti penyedia AI (gemini, anthropic, openai)")
    sp.add_argument("name", nargs="?", choices=list(analysis.PROVIDERS))
    sp.add_argument("--model", help="model untuk penyedia tersebut")
    sp.set_defaults(func=cmd_provider)

    sp = sub.add_parser("branding", help="logo (watermark) & video/gambar penutup untuk klip")
    sp.add_argument("--logo", metavar="FILE", help="pasang logo (png/jpg/webp)")
    sp.add_argument("--position", choices=list(branding.POSITIONS))
    sp.add_argument("--size", type=float, help="lebar logo, persen dari lebar video (3-40)")
    sp.add_argument("--opacity", type=float, help="transparansi logo 0.1-1.0")
    sp.add_argument("--margin", type=float, help="jarak dari tepi, persen lebar video (0-25)")
    sp.add_argument("--logo-off", action="store_true", help="matikan logo tanpa menghapus filenya")
    sp.add_argument("--logo-on", action="store_true")
    sp.add_argument("--remove-logo", action="store_true")
    sp.add_argument("--outro", metavar="FILE", help="pasang penutup (video atau gambar)")
    sp.add_argument("--outro-duration", type=float, help="durasi penutup kalau berupa gambar (detik)")
    sp.add_argument("--outro-mute", action="store_true", help="buang audio penutup")
    sp.add_argument("--outro-off", action="store_true")
    sp.add_argument("--outro-on", action="store_true")
    sp.add_argument("--remove-outro", action="store_true")
    sp.set_defaults(func=cmd_branding)

    sp = sub.add_parser("serve", help="jalankan antarmuka web")
    sp.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8765)))
    sp.add_argument("--host", default="127.0.0.1")
    sp.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        fail(f"{type(e).__name__}: {e}", args)


if __name__ == "__main__":
    main()
