"""Pelacakan wajah untuk crop otomatis yang mengikuti pembicara.

Langkah:
1. Ambil sampel frame (5 fps) dari rentang klip lewat ffmpeg.
2. Deteksi wajah (MediaPipe BlazeFace full-range) dan hubungkan antar frame jadi "track" per orang.
3. Kalau ada beberapa orang yang tidak muat dalam satu frame crop, pilih yang sedang bicara
   berdasarkan gerakan bibir (MediaPipe FaceMesh).
4. Rapikan seperti operator kamera: tahan shot minimal ~1,2 detik, pindah orang = potongan
   langsung (cut), gerak di dalam shot dihaluskan dengan dead-zone.
5. Hasilnya diubah jadi perintah `sendcmd` untuk filter crop ffmpeg.
"""
from __future__ import annotations

import bisect
import math
import os
import subprocess
from pathlib import Path
from typing import Callable

import numpy as np

from .media import FFMPEG

os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")


def _quiet_absl() -> None:
    try:  # absl ikut terpasang bersama mediapipe
        import logging

        from absl import logging as absl_logging

        absl_logging.use_absl_handler()
        absl_logging.set_verbosity(logging.ERROR)
    except ImportError:
        pass

SAMPLE_FPS = 5
ANALYSIS_W = 960
MIN_SHOT = int(SAMPLE_FPS * 1.2)        # sampel minimal sebelum kamera boleh pindah orang
TALK_THRESHOLD = 0.012                   # aktivitas bibir minimum untuk dianggap bicara
DEAD_ZONE = 0.025                        # geseran kecil (relatif lebar video) diabaikan
LIP_UP, LIP_LO, CORNER_L, CORNER_R = 13, 14, 78, 308


def available() -> bool:
    try:
        import mediapipe as mp  # noqa: F401
        return hasattr(mp, "solutions")
    except ImportError:
        return False


def _frames(src: Path, start: float, dur: float, src_w: int, src_h: int):
    h = max(2, int(round(ANALYSIS_W * src_h / src_w / 2)) * 2)
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", str(src),
        "-t", f"{dur:.3f}", "-vf", f"fps={SAMPLE_FPS},scale={ANALYSIS_W}:{h}",
        "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = ANALYSIS_W * h * 3
    try:
        assert proc.stdout
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, ANALYSIS_W, 3)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()


def _detect_once(detector, frame: np.ndarray, x_off: float, x_scale: float) -> list[dict]:
    faces = []
    for d in detector.process(np.ascontiguousarray(frame)).detections or []:
        b = d.location_data.relative_bounding_box
        faces.append({
            "cx": min(1.0, max(0.0, x_off + (b.xmin + b.width / 2) * x_scale)),
            "cy": min(1.0, max(0.0, b.ymin + b.height / 2)),
            "w": b.width * x_scale, "h": b.height, "score": d.score[0], "mouth": None,
        })
    return faces


def _detect(detector, frame: np.ndarray) -> list[dict]:
    """Deteksi di frame penuh + dua potongan yang saling tumpang tindih.

    Model memperkecil input ke 192x192, jadi wajah kecil di video lebar sering terlewat.
    Potongan yang lebih sempit membuat wajah tampak dua kali lebih besar bagi model.
    """
    H, W, _ = frame.shape
    faces = _detect_once(detector, frame, 0.0, 1.0)
    if W / H > 1.2:
        tile = 0.58
        for x0 in (0.0, 1 - tile):
            a, b = int(x0 * W), int((x0 + tile) * W)
            faces += _detect_once(detector, frame[:, a:b], x0, tile)
    # Gabungkan deteksi ganda dari frame penuh & potongan (ambil skor tertinggi).
    kept: list[dict] = []
    for f in sorted(faces, key=lambda f: -f["score"]):
        if f["w"] < 0.012 or f["h"] < 0.012:
            continue
        if all(math.hypot(f["cx"] - k["cx"], f["cy"] - k["cy"]) > max(f["w"], k["w"]) * 0.6 for k in kept):
            kept.append(f)
    return kept


def _mouth_ratio(mesh, frame: np.ndarray, face: dict) -> float | None:
    """Rasio bukaan bibir / lebar mulut. Berubah-ubah cepat saat orang bicara."""
    import cv2

    H, W, _ = frame.shape
    side = max(face["w"] * W, face["h"] * H) * 1.7
    x0, x1 = int(max(0, face["cx"] * W - side / 2)), int(min(W, face["cx"] * W + side / 2))
    y0, y1 = int(max(0, face["cy"] * H - side / 2)), int(min(H, face["cy"] * H + side / 2))
    crop = frame[y0:y1, x0:x1]
    if crop.shape[0] < 24 or crop.shape[1] < 24:
        return None
    if crop.shape[0] < 256:
        k = 256 / crop.shape[0]
        crop = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_LINEAR)
    res = mesh.process(np.ascontiguousarray(crop))
    if not res.multi_face_landmarks:
        return None
    lm = res.multi_face_landmarks[0].landmark
    aspect = crop.shape[0] / crop.shape[1]
    dist = lambda a, b: math.hypot(lm[a].x - lm[b].x, (lm[a].y - lm[b].y) * aspect)  # noqa: E731
    width = dist(CORNER_L, CORNER_R)
    return dist(LIP_UP, LIP_LO) / width if width > 1e-6 else None


def _build_tracks(samples: list[list[dict]]) -> list[dict]:
    tracks: list[dict] = []
    for i, faces in enumerate(samples):
        taken: set[int] = set()
        for f in sorted(faces, key=lambda f: -f["w"]):
            best, best_d = None, 0.1 + f["w"]
            for tr in tracks:
                if tr["id"] in taken or i - tr["last"] > SAMPLE_FPS * 2:
                    continue
                d = math.hypot(f["cx"] - tr["cx"], f["cy"] - tr["cy"])
                if d < best_d:
                    best, best_d = tr, d
            if best is None:
                best = {"id": len(tracks), "pts": {}}
                tracks.append(best)
            best.update(cx=f["cx"], cy=f["cy"], last=i)
            best["pts"][i] = f
            taken.add(best["id"])
    # Buang deteksi palsu yang hanya muncul sekejap (kecuali tidak ada yang lain).
    solid = [t for t in tracks if len(t["pts"]) >= 3]
    return solid or tracks


def _activity(track: dict, i: int) -> float:
    vals = [track["pts"][j]["mouth"] for j in range(i - 4, i + 5)
            if j in track["pts"] and track["pts"][j]["mouth"] is not None]
    if len(vals) < 3:
        return 0.0
    return float(np.mean(np.abs(np.diff(vals))))


def _nearest(d: dict[int, tuple], i: int) -> tuple:
    keys = sorted(d)
    k = bisect.bisect_left(keys, i)
    cands = [keys[j] for j in (k - 1, k) if 0 <= j < len(keys)]
    return d[min(cands, key=lambda j: abs(j - i))]


def _runs(labels: list) -> list[list]:
    runs: list[list] = []
    for i, lab in enumerate(labels):
        if runs and runs[-1][0] == lab:
            runs[-1][2] = i + 1
        else:
            runs.append([lab, i, i + 1])
    return runs


def track(src: Path, start: float, end: float, src_w: int, src_h: int, crop_w_norm: float,
          crop_h_norm: float, on_progress: Callable[[float], None] | None = None) -> dict:
    """Return {"keys": [(cx, cy, cut)], "stats": {...}} dengan satu key per sampel (1/SAMPLE_FPS dtk)."""
    _quiet_absl()
    import mediapipe as mp

    dur = max(0.2, end - start)
    expected = max(1, int(dur * SAMPLE_FPS))
    samples: list[list[dict]] = []
    with mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as det, \
            mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1) as mesh:
        for frame in _frames(src, start, dur, src_w, src_h):
            faces = _detect(det, frame)
            spread = (max(f["cx"] + f["w"] / 2 for f in faces) - min(f["cx"] - f["w"] / 2 for f in faces)) if faces else 0
            # Bibir hanya perlu dibaca kalau ada >1 orang yang tidak muat bersama dalam crop.
            if len(faces) > 1 and spread > crop_w_norm * 0.9:
                for f in faces:
                    f["mouth"] = _mouth_ratio(mesh, frame, f)
            samples.append(faces)
            if on_progress:
                on_progress(min(1.0, len(samples) / expected))
    return plan(samples, crop_w_norm, crop_h_norm)


def plan(samples: list[list[dict]], crop_w_norm: float, crop_h_norm: float) -> dict:
    """Ubah deteksi wajah per sampel jadi jalur kamera."""
    n = len(samples)
    if n == 0:
        return {"keys": [], "stats": {"coverage": 0, "people": 0, "cuts": 0}}

    tracks = _build_tracks(samples)
    by_id = {t["id"]: t for t in tracks}
    group_pos: dict[int, tuple] = {}

    # 1. Keputusan per sampel: siapa yang di-frame.
    labels: list = [None] * n
    for i in range(n):
        present = [t for t in tracks if i in t["pts"]]
        if not present:
            continue
        pts = [t["pts"][i] for t in present]
        x0, x1 = min(p["cx"] - p["w"] / 2 for p in pts), max(p["cx"] + p["w"] / 2 for p in pts)
        y0, y1 = min(p["cy"] - p["h"] / 2 for p in pts), max(p["cy"] + p["h"] / 2 for p in pts)
        if x1 - x0 <= crop_w_norm * 0.9 and y1 - y0 <= crop_h_norm * 0.9:
            labels[i] = "group"  # semua orang muat dalam satu crop
            group_pos[i] = ((x0 + x1) / 2, (y0 + y1) / 2)
            continue
        talking = max(present, key=lambda t: _activity(t, i))
        if _activity(talking, i) >= TALK_THRESHOLD:
            labels[i] = talking["id"]
        elif i == 0 or labels[i - 1] is None or labels[i - 1] == "group":
            labels[i] = max(present, key=lambda t: t["pts"][i]["w"])["id"]
        # selain itu: None → tahan orang sebelumnya

    # 2. Isi kekosongan dengan keputusan sebelumnya (atau berikutnya di awal klip).
    first = next((lab for lab in labels if lab is not None), None)
    prev = first
    for i in range(n):
        if labels[i] is None:
            labels[i] = prev
        prev = labels[i]

    # 3. Shot terlalu pendek digabung ke shot sebelumnya supaya kamera tidak loncat-loncat.
    for _ in range(3):
        runs = _runs(labels)
        for k, (lab, a, b) in enumerate(runs):
            if b - a < MIN_SHOT and len(runs) > 1:
                repl = runs[k - 1][0] if k > 0 else runs[k + 1][0]
                labels[a:b] = [repl] * (b - a)

    # 4. Posisi target per sampel.
    raw: list[tuple[float, float]] = []
    for i, lab in enumerate(labels):
        if lab is None:
            raw.append((0.5, 0.45))
        elif lab == "group":
            raw.append(_nearest(group_pos, i))
        else:
            pts = by_id[lab]["pts"]
            f = pts.get(i) or pts[min(pts, key=lambda j: abs(j - i))]
            raw.append((f["cx"], f["cy"]))

    # 5. Haluskan di dalam tiap shot: rata-rata bergerak, lalu kamera diam selama subjek hanya
    #    bergoyang kecil, dan ikut penuh begitu subjek benar-benar berpindah.
    keys: list[tuple[float, float, bool]] = []
    for lab, a, b in _runs(labels):
        cam: list[float] = []
        moving, still, prev = [False, False], [0, 0], [0.0, 0.0]
        for i in range(a, b):
            lo, hi = max(a, i - 3), min(b, i + 4)
            target = [sum(raw[j][ax] for j in range(lo, hi)) / (hi - lo) for ax in (0, 1)]
            if not cam:
                cam, prev = target[:], target[:]
            for ax in (0, 1):
                if moving[ax]:
                    cam[ax] = target[ax]
                    still[ax] = still[ax] + 1 if abs(target[ax] - prev[ax]) < 0.003 else 0
                    moving[ax] = still[ax] < 3
                elif abs(target[ax] - cam[ax]) > DEAD_ZONE:
                    moving[ax], still[ax] = True, 0
                    cam[ax] += (target[ax] - cam[ax]) * 0.5
            prev = target
            keys.append((cam[0], cam[1], i == a and i > 0))

    stats = {
        "coverage": sum(1 for s in samples if s) / n,
        "people": sum(1 for t in tracks if len(t["pts"]) >= SAMPLE_FPS),
        "cuts": sum(1 for k in keys if k[2]),
    }
    return {"keys": keys, "stats": stats}


def write_sendcmd(keys: list[tuple[float, float, bool]], duration: float, iw: int, ih: int,
                  cw: int, ch: int, path: Path, fps: int = 30) -> tuple[int, int]:
    """Tulis perintah crop per frame. Return posisi awal (x, y)."""
    def pos(cx: float, cy: float) -> tuple[int, int]:
        x = int(round(cx * iw - cw / 2))
        y = int(round(cy * ih - ch * 0.42))  # wajah sedikit di atas tengah
        return min(max(0, x), iw - cw), min(max(0, y), ih - ch)

    if not keys:
        path.write_text("")
        return pos(0.5, 0.45)
    lines, last = [], None
    n = len(keys)
    for k in range(int(duration * fps) + 1):
        t = k / fps
        s = t * SAMPLE_FPS
        i = min(n - 1, int(s))
        j = i + 1
        if j >= n or keys[j][2]:
            cx, cy = keys[i][0], keys[i][1]
        else:
            f = s - i
            cx = keys[i][0] + (keys[j][0] - keys[i][0]) * f
            cy = keys[i][1] + (keys[j][1] - keys[i][1]) * f
        p = pos(cx, cy)
        if p != last:
            lines.append(f"{t:.3f} crop x {p[0]}, crop y {p[1]};")
            last = p
    path.write_text("\n".join(lines) + "\n")
    return pos(keys[0][0], keys[0][1])
