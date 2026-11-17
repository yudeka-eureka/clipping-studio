"""Logo (watermark) dan bumper (video/gambar pembuka & penutup) untuk klip.

Logo dan bumper (video/gambar pembuka & penutup) sama-sama disimpan sebagai pustaka:
boleh beberapa, masing-masing dengan pengaturannya sendiri. Tiap proyek memilih mana yang dipakai,
dan ada default untuk proyek baru.

File ada di data/branding/ (logo di subfolder logos/), pengaturannya di data/branding.json.
Semuanya dipasang saat render, jadi klip lama perlu "Render ulang" untuk ikut berubah.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "data" / "branding"
SETTINGS_FILE = DIR.parent / "branding.json"


def logo_dir() -> Path:
    return DIR / "logos"


def bumper_dir() -> Path:
    return DIR / "bumpers"

POSITIONS = {
    "top-left": "Kiri atas", "top-right": "Kanan atas",
    "bottom-left": "Kiri bawah", "bottom-right": "Kanan bawah",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}

LOGO_DEFAULTS = {"position": "bottom-right", "size": 12, "opacity": 0.85, "margin": 5}
NO_LOGO = ""  # nilai logo_id untuk "proyek ini tanpa logo"

_LIMITS = {"size": (3, 40), "opacity": (0.1, 1.0), "margin": (0, 25), "duration": (0.5, 15.0)}


def _read() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))


def settings() -> dict:
    """{"logos": [...], "default_logo": id|None, "outro": {...}}"""
    saved = _read()
    logos = []
    for entry in saved.get("logos") or []:
        if entry.get("file") and (logo_dir() / entry["file"]).is_file():
            logos.append({**LOGO_DEFAULTS, **entry})
    # Versi lama hanya punya satu logo di data/branding/logo.*; pindahkan jadi entri pertama.
    old = saved.get("logo") or {}
    if old.get("file") and (DIR / old["file"]).is_file():
        logo_dir().mkdir(parents=True, exist_ok=True)
        dest = logo_dir() / f"utama{Path(old['file']).suffix}"
        shutil.move(str(DIR / old["file"]), dest)
        logos.insert(0, {**LOGO_DEFAULTS, **{k: v for k, v in old.items() if k in LOGO_DEFAULTS},
                         "id": "utama", "label": "Logo utama", "file": dest.name})
        data = {"logos": logos, "default_logo": "utama" if old.get("enabled", True) else None,
                "outro": saved.get("outro") or dict(OUTRO_DEFAULTS)}
        _save(data)
        saved = data

    bumpers = []
    for entry in saved.get("bumpers") or []:
        if entry.get("file") and (bumper_dir() / entry["file"]).is_file():
            bumpers.append({**BUMPER_DEFAULTS, **entry})
    defaults = {role: saved.get(f"default_{role}") for role in ROLES}

    # Versi lama hanya punya satu penutup di data/branding/outro.*; pindahkan ke pustaka.
    old_outro = saved.get("outro") or {}
    if old_outro.get("file") and (DIR / old_outro["file"]).is_file():
        bumper_dir().mkdir(parents=True, exist_ok=True)
        dest = bumper_dir() / f"penutup{Path(old_outro['file']).suffix}"
        shutil.move(str(DIR / old_outro["file"]), dest)
        bumpers.insert(0, {**BUMPER_DEFAULTS, "id": "penutup", "label": "Penutup", "file": dest.name,
                           **{k: v for k, v in old_outro.items() if k in BUMPER_DEFAULTS}})
        defaults["outro"] = "penutup" if old_outro.get("enabled", True) else None

    ids = [b["id"] for b in bumpers]
    data = {"logos": logos, "default_logo": saved.get("default_logo"), "bumpers": bumpers,
            **{f"default_{role}": (defaults[role] if defaults[role] in ids else None) for role in ROLES}}
    if data["default_logo"] not in [lg["id"] for lg in logos]:
        data["default_logo"] = logos[0]["id"] if logos and data["default_logo"] is not None else None
    if old_outro.get("file"):
        _save(data)
    return data


def _store(data: dict) -> None:
    _save({k: data[k] for k in ("logos", "default_logo", "bumpers", "default_intro", "default_outro")})


def _clamp(field: str, value):
    lo, hi = _LIMITS[field]
    return max(lo, min(hi, float(value)))


# ---------- pustaka logo ----------

def add_logo(src: Path, filename: str, label: str = "") -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in IMAGE_EXT:
        raise ValueError(f"Format {ext or '?'} tidak didukung untuk logo. Pakai: {', '.join(sorted(IMAGE_EXT))}")
    data = settings()
    logo_id = uuid.uuid4().hex[:8]
    logo_dir().mkdir(parents=True, exist_ok=True)
    dest = logo_dir() / f"{logo_id}{ext}"
    shutil.copyfile(src, dest)
    entry = {**LOGO_DEFAULTS, "id": logo_id, "label": label.strip() or Path(filename).stem, "file": dest.name}
    data["logos"].append(entry)
    if data["default_logo"] is None and len(data["logos"]) == 1:
        data["default_logo"] = logo_id
    _store(data)
    return entry


def update_logo(logo_id: str, **fields) -> dict:
    data = settings()
    entry = next((lg for lg in data["logos"] if lg["id"] == logo_id), None)
    if not entry:
        raise ValueError(f"Logo '{logo_id}' tidak ditemukan.")
    for key, value in fields.items():
        if value is None:
            continue
        if key == "label":
            entry["label"] = str(value).strip() or entry["label"]
        elif key == "position":
            if value not in POSITIONS:
                raise ValueError(f"Posisi harus salah satu dari: {', '.join(POSITIONS)}")
            entry["position"] = value
        elif key in ("size", "opacity", "margin"):
            entry[key] = _clamp(key, value)
    _store(data)
    return entry


def remove_logo(logo_id: str) -> dict:
    data = settings()
    entry = next((lg for lg in data["logos"] if lg["id"] == logo_id), None)
    if not entry:
        raise ValueError(f"Logo '{logo_id}' tidak ditemukan.")
    (logo_dir() / entry["file"]).unlink(missing_ok=True)
    data["logos"] = [lg for lg in data["logos"] if lg["id"] != logo_id]
    if data["default_logo"] == logo_id:
        data["default_logo"] = data["logos"][0]["id"] if data["logos"] else None
    _store(data)
    return data


def set_default_logo(logo_id: str | None) -> dict:
    data = settings()
    if logo_id and logo_id not in [lg["id"] for lg in data["logos"]]:
        raise ValueError(f"Logo '{logo_id}' tidak ditemukan.")
    data["default_logo"] = logo_id or None
    _store(data)
    return data


def logo_for(logo_id: str | None) -> dict | None:
    """Logo yang dipakai sebuah proyek.

    None  → pakai logo default; ""  → proyek ini sengaja tanpa logo.
    Logo yang sudah dihapus otomatis jatuh kembali ke default.
    """
    if logo_id == NO_LOGO and logo_id is not None:
        return None
    data = settings()
    wanted = logo_id or data["default_logo"]
    entry = next((lg for lg in data["logos"] if lg["id"] == wanted), None)
    if not entry and logo_id:
        entry = next((lg for lg in data["logos"] if lg["id"] == data["default_logo"]), None)
    return {**entry, "path": logo_dir() / entry["file"]} if entry else None


# ---------- pustaka bumper (video/gambar pembuka & penutup) ----------

BUMPER_DEFAULTS = {"duration": 2.5, "keep_audio": True}
ROLES = ("intro", "outro")


def add_bumper(src: Path, filename: str, label: str = "") -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in IMAGE_EXT | VIDEO_EXT:
        raise ValueError(f"Format {ext or '?'} tidak didukung. Pakai: {', '.join(sorted(IMAGE_EXT | VIDEO_EXT))}")
    data = settings()
    bumper_id = uuid.uuid4().hex[:8]
    bumper_dir().mkdir(parents=True, exist_ok=True)
    dest = bumper_dir() / f"{bumper_id}{ext}"
    shutil.copyfile(src, dest)
    entry = {**BUMPER_DEFAULTS, "id": bumper_id, "label": label.strip() or Path(filename).stem,
             "file": dest.name}
    data["bumpers"].append(entry)
    _store(data)
    return entry


def update_bumper(bumper_id: str, **fields) -> dict:
    data = settings()
    entry = next((b for b in data["bumpers"] if b["id"] == bumper_id), None)
    if not entry:
        raise ValueError(f"Bumper '{bumper_id}' tidak ditemukan.")
    for key, value in fields.items():
        if value is None:
            continue
        if key == "label":
            entry["label"] = str(value).strip() or entry["label"]
        elif key == "duration":
            entry["duration"] = _clamp("duration", value)
        elif key == "keep_audio":
            entry["keep_audio"] = bool(value)
    _store(data)
    return entry


def remove_bumper(bumper_id: str) -> dict:
    data = settings()
    entry = next((b for b in data["bumpers"] if b["id"] == bumper_id), None)
    if not entry:
        raise ValueError(f"Bumper '{bumper_id}' tidak ditemukan.")
    (bumper_dir() / entry["file"]).unlink(missing_ok=True)
    data["bumpers"] = [b for b in data["bumpers"] if b["id"] != bumper_id]
    for role in ROLES:
        if data[f"default_{role}"] == bumper_id:
            data[f"default_{role}"] = None
    _store(data)
    return data


def set_default_bumper(role: str, bumper_id: str | None) -> dict:
    if role not in ROLES:
        raise ValueError("Peran bumper harus 'intro' atau 'outro'.")
    data = settings()
    if bumper_id and bumper_id not in [b["id"] for b in data["bumpers"]]:
        raise ValueError(f"Bumper '{bumper_id}' tidak ditemukan.")
    data[f"default_{role}"] = bumper_id or None
    _store(data)
    return data


def bumper_for(role: str, bumper_id: str | None) -> dict | None:
    """Bumper yang dipakai sebuah proyek. None → default peran itu; "" → tanpa bumper."""
    if bumper_id == NO_LOGO and bumper_id is not None:
        return None
    data = settings()
    wanted = bumper_id or data[f"default_{role}"]
    entry = next((b for b in data["bumpers"] if b["id"] == wanted), None)
    if not entry and bumper_id:
        entry = next((b for b in data["bumpers"] if b["id"] == data[f"default_{role}"]), None)
    if not entry:
        return None
    file = bumper_dir() / entry["file"]
    return {**entry, "path": file, "is_video": file.suffix.lower() in VIDEO_EXT, "role": role}


# ---------- untuk antarmuka ----------

def public() -> dict:
    data = settings()
    logos = [{**lg, "url": f"/branding/logos/{lg['file']}",
              "size_bytes": (logo_dir() / lg["file"]).stat().st_size} for lg in data["logos"]]
    bumpers = [{**b, "url": f"/branding/bumpers/{b['file']}",
                "is_video": Path(b["file"]).suffix.lower() in VIDEO_EXT,
                "size_bytes": (bumper_dir() / b["file"]).stat().st_size} for b in data["bumpers"]]
    return {
        "logos": logos, "default_logo": data["default_logo"], "positions": POSITIONS,
        "bumpers": bumpers, "default_intro": data["default_intro"], "default_outro": data["default_outro"],
        "roles": {"intro": "Pembuka", "outro": "Penutup"},
    }
