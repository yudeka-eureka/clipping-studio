"""Logo (watermark) dan video/gambar penutup (outro) untuk klip.

File disimpan di data/branding/, pengaturannya di data/branding.json.
Keduanya dipasang saat render, jadi klip lama perlu "Render ulang" untuk ikut berubah.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "data" / "branding"
SETTINGS_FILE = DIR.parent / "branding.json"

POSITIONS = {
    "top-left": "Kiri atas", "top-right": "Kanan atas",
    "bottom-left": "Kiri bawah", "bottom-right": "Kanan bawah",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}

DEFAULTS = {
    "logo": {"file": None, "enabled": True, "position": "bottom-right", "size": 12, "opacity": 0.85, "margin": 5},
    "outro": {"file": None, "enabled": True, "duration": 2.5, "keep_audio": True},
}


def settings() -> dict:
    data = {k: dict(v) for k, v in DEFAULTS.items()}
    try:
        saved = json.loads(SETTINGS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        saved = {}
    for key in data:
        data[key].update({k: v for k, v in (saved.get(key) or {}).items() if k in data[key]})
    # File yang sudah dihapus dari disk dianggap tidak ada.
    for key in data:
        if data[key]["file"] and not (DIR / data[key]["file"]).is_file():
            data[key]["file"] = None
    return data


def _save(data: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))


def update(kind: str, **fields) -> dict:
    data = settings()
    if kind not in data:
        raise ValueError(f"Bagian '{kind}' tidak dikenal.")
    for k, v in fields.items():
        if v is None or k not in data[kind]:
            continue
        if k == "position" and v not in POSITIONS:
            raise ValueError(f"Posisi harus salah satu dari: {', '.join(POSITIONS)}")
        if k == "size":
            v = max(3, min(40, float(v)))
        if k == "opacity":
            v = max(0.1, min(1.0, float(v)))
        if k == "margin":
            v = max(0, min(25, float(v)))
        if k == "duration":
            v = max(0.5, min(15.0, float(v)))
        data[kind][k] = v
    _save(data)
    return data


def save_file(kind: str, src: Path, filename: str) -> dict:
    """Simpan file logo/outro yang diunggah, lalu pakai sebagai yang aktif."""
    ext = Path(filename).suffix.lower()
    allowed = IMAGE_EXT if kind == "logo" else IMAGE_EXT | VIDEO_EXT
    if ext not in allowed:
        raise ValueError(f"Format {ext or '?'} tidak didukung. Pakai: {', '.join(sorted(allowed))}")
    DIR.mkdir(parents=True, exist_ok=True)
    for old in DIR.glob(f"{kind}.*"):
        old.unlink(missing_ok=True)
    dest = DIR / f"{kind}{ext}"
    shutil.copyfile(src, dest)
    return update(kind, file=dest.name, enabled=True)


def clear(kind: str) -> dict:
    for old in DIR.glob(f"{kind}.*"):
        old.unlink(missing_ok=True)
    data = settings()
    data[kind]["file"] = None
    _save(data)
    return data


def path(kind: str) -> Path | None:
    name = settings()[kind]["file"]
    return DIR / name if name else None


def active(kind: str) -> dict | None:
    """Pengaturan yang siap dipakai render, atau None kalau tidak aktif / filenya tidak ada."""
    cfg = settings()[kind]
    file = path(kind)
    if not cfg["enabled"] or not file:
        return None
    return {**cfg, "path": file, "is_video": file.suffix.lower() in VIDEO_EXT}


def public() -> dict:
    """Pengaturan + info file untuk antarmuka."""
    data = settings()
    out = {}
    for kind, cfg in data.items():
        file = path(kind)
        out[kind] = {**cfg, "exists": bool(file),
                     "url": f"/branding/{file.name}" if file else None,
                     "is_video": bool(file and file.suffix.lower() in VIDEO_EXT),
                     "size_bytes": file.stat().st_size if file else 0}
    out["positions"] = POSITIONS
    return out
