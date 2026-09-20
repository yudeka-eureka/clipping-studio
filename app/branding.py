"""Logo (watermark) dan video/gambar penutup (outro) untuk klip.

Logo disimpan sebagai pustaka: boleh beberapa logo (mis. milik sendiri dan milik klien),
masing-masing dengan posisi/ukurannya sendiri. Tiap proyek memilih logo mana yang dipakai,
dan ada satu logo default untuk proyek baru.

File ada di data/branding/ (logo di subfolder logos/), pengaturannya di data/branding.json.
Semuanya dipasang saat render, jadi klip lama perlu "Render ulang" untuk ikut berubah.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "data" / "branding"
LOGO_DIR = DIR / "logos"
SETTINGS_FILE = DIR.parent / "branding.json"

POSITIONS = {
    "top-left": "Kiri atas", "top-right": "Kanan atas",
    "bottom-left": "Kiri bawah", "bottom-right": "Kanan bawah",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}

LOGO_DEFAULTS = {"position": "bottom-right", "size": 12, "opacity": 0.85, "margin": 5}
OUTRO_DEFAULTS = {"file": None, "enabled": True, "duration": 2.5, "keep_audio": True}
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
        if entry.get("file") and (LOGO_DIR / entry["file"]).is_file():
            logos.append({**LOGO_DEFAULTS, **entry})
    # Versi lama hanya punya satu logo di data/branding/logo.*; pindahkan jadi entri pertama.
    old = saved.get("logo") or {}
    if old.get("file") and (DIR / old["file"]).is_file():
        LOGO_DIR.mkdir(parents=True, exist_ok=True)
        dest = LOGO_DIR / f"utama{Path(old['file']).suffix}"
        shutil.move(str(DIR / old["file"]), dest)
        logos.insert(0, {**LOGO_DEFAULTS, **{k: v for k, v in old.items() if k in LOGO_DEFAULTS},
                         "id": "utama", "label": "Logo utama", "file": dest.name})
        data = {"logos": logos, "default_logo": "utama" if old.get("enabled", True) else None,
                "outro": saved.get("outro") or dict(OUTRO_DEFAULTS)}
        _save(data)
        saved = data

    outro = {**OUTRO_DEFAULTS, **{k: v for k, v in (saved.get("outro") or {}).items() if k in OUTRO_DEFAULTS}}
    if outro["file"] and not (DIR / outro["file"]).is_file():
        outro["file"] = None
    default = saved.get("default_logo")
    if default not in [lg["id"] for lg in logos]:
        default = logos[0]["id"] if logos and default is not None else None
    return {"logos": logos, "default_logo": default, "outro": outro}


def _store(data: dict) -> None:
    _save({"logos": data["logos"], "default_logo": data["default_logo"], "outro": data["outro"]})


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
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    dest = LOGO_DIR / f"{logo_id}{ext}"
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
    (LOGO_DIR / entry["file"]).unlink(missing_ok=True)
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
    return {**entry, "path": LOGO_DIR / entry["file"]} if entry else None


# ---------- penutup (outro) ----------

def save_outro(src: Path, filename: str) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in IMAGE_EXT | VIDEO_EXT:
        raise ValueError(f"Format {ext or '?'} tidak didukung. Pakai: {', '.join(sorted(IMAGE_EXT | VIDEO_EXT))}")
    DIR.mkdir(parents=True, exist_ok=True)
    for old in DIR.glob("outro.*"):
        old.unlink(missing_ok=True)
    dest = DIR / f"outro{ext}"
    shutil.copyfile(src, dest)
    return update_outro(file=dest.name, enabled=True)


def update_outro(**fields) -> dict:
    data = settings()
    for key, value in fields.items():
        if value is None or key not in OUTRO_DEFAULTS:
            continue
        data["outro"][key] = _clamp("duration", value) if key == "duration" else value
    _store(data)
    return data["outro"]


def clear_outro() -> dict:
    for old in DIR.glob("outro.*"):
        old.unlink(missing_ok=True)
    data = settings()
    data["outro"]["file"] = None
    _store(data)
    return data["outro"]


def active_outro() -> dict | None:
    outro = settings()["outro"]
    if not outro["enabled"] or not outro["file"]:
        return None
    file = DIR / outro["file"]
    return {**outro, "path": file, "is_video": file.suffix.lower() in VIDEO_EXT}


# ---------- untuk antarmuka ----------

def public() -> dict:
    data = settings()
    logos = [{**lg, "url": f"/branding/logos/{lg['file']}",
              "size_bytes": (LOGO_DIR / lg["file"]).stat().st_size} for lg in data["logos"]]
    outro = data["outro"]
    file = DIR / outro["file"] if outro["file"] else None
    return {
        "logos": logos, "default_logo": data["default_logo"], "positions": POSITIONS,
        "outro": {**outro, "exists": bool(file), "url": f"/branding/{file.name}" if file else None,
                  "is_video": bool(file and file.suffix.lower() in VIDEO_EXT),
                  "size_bytes": file.stat().st_size if file else 0},
    }
