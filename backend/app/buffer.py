"""Koneksi ke Buffer GraphQL API (https://developers.buffer.com) untuk posting klip ke media sosial.

Mendukung beberapa akun Buffer sekaligus: tiap akun punya API key sendiri dan daftar channelnya
digabung, jadi satu klip bisa dikirim ke channel milik akun yang berbeda dalam sekali jalan.
Akun disimpan di data/buffer_accounts.json (hanya bisa dibaca pemilik file).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import httpx

API_URL = os.environ.get("BUFFER_API_URL", "https://api.buffer.com")
ACCOUNTS_FILE = Path(__file__).resolve().parent.parent / "data" / "buffer_accounts.json"

# Service yang bisa menerima video lewat Buffer.
VIDEO_SERVICES = {"instagram", "tiktok", "youtube", "facebook", "linkedin", "twitter",
                  "threads", "bluesky", "mastodon", "pinterest", "googlebusiness"}

_channels_cache: dict[str, tuple[float, list[dict]]] = {}


class BufferError(RuntimeError):
    pass


# ---------- akun ----------

def accounts() -> list[dict]:
    """Daftar akun Buffer. BUFFER_API_KEY lama otomatis dipindahkan jadi akun pertama."""
    try:
        data = json.loads(ACCOUNTS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        data = []
    env_key = os.environ.get("BUFFER_API_KEY", "").strip()
    if env_key and not any(a["api_key"] == env_key for a in data):
        data.insert(0, {"id": "env", "label": "Akun utama", "api_key": env_key})
        _save(data)
    return data


def _save(data: list[dict]) -> None:
    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_FILE.touch(mode=0o600, exist_ok=True)
    ACCOUNTS_FILE.write_text(json.dumps(data, indent=2))
    os.chmod(ACCOUNTS_FILE, 0o600)


def account(account_id: str) -> dict:
    found = next((a for a in accounts() if a["id"] == account_id), None)
    if not found:
        raise BufferError(f"Akun Buffer '{account_id}' tidak ditemukan.")
    return found


def public_accounts() -> list[dict]:
    """Data akun tanpa API key, untuk dikirim ke antarmuka."""
    return [{"id": a["id"], "label": a["label"], "key_hint": f"…{a['api_key'][-4:]}"} for a in accounts()]


def add_account(label: str, api_key: str) -> dict:
    api_key = api_key.strip()
    if not api_key:
        raise BufferError("API key kosong.")
    data = accounts()
    if any(a["api_key"] == api_key for a in data):
        raise BufferError("API key ini sudah terdaftar.")
    # Pastikan key-nya benar sebelum disimpan, sekalian ambil nama organisasinya.
    orgs = graphql("query { account { organizations { id name } } }", key=api_key)["account"]["organizations"]
    entry = {"id": uuid.uuid4().hex[:8], "label": (label or "").strip() or (orgs[0]["name"] if orgs else "Akun Buffer"),
             "api_key": api_key, "added_at": time.time()}
    data.append(entry)
    _save(data)
    _channels_cache.clear()
    return {"id": entry["id"], "label": entry["label"], "organizations": [o["name"] for o in orgs]}


def remove_account(account_id: str) -> bool:
    """Hapus akun. Return True kalau akun ini berasal dari BUFFER_API_KEY di .env
    (pemanggil perlu mengosongkannya juga, kalau tidak akun akan muncul lagi)."""
    before = accounts()
    if not any(a["id"] == account_id for a in before):
        raise BufferError(f"Akun Buffer '{account_id}' tidak ditemukan.")
    _save([a for a in before if a["id"] != account_id])
    _channels_cache.pop(account_id, None)
    if account_id == "env":
        os.environ["BUFFER_API_KEY"] = ""
        return True
    return False


def rename_account(account_id: str, label: str) -> dict:
    data = accounts()
    entry = next((a for a in data if a["id"] == account_id), None)
    if not entry:
        raise BufferError(f"Akun Buffer '{account_id}' tidak ditemukan.")
    entry["label"] = label.strip() or entry["label"]
    _save(data)
    return {"id": entry["id"], "label": entry["label"]}


def api_key(account_id: str | None = None) -> str:
    if account_id:
        return account(account_id)["api_key"]
    data = accounts()
    if not data:
        raise BufferError("Belum ada akun Buffer. Tambahkan di Pengaturan "
                          "(API key dibuat di publish.buffer.com/settings/api).")
    return data[0]["api_key"]


# ---------- API ----------

def graphql(query: str, variables: dict | None = None, key: str | None = None) -> dict:
    key = key or api_key()
    try:
        resp = httpx.post(
            API_URL, json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=60,
        )
    except httpx.HTTPError as e:
        raise BufferError(f"Tidak bisa terhubung ke Buffer: {e}") from e
    if resp.status_code == 429:
        raise BufferError(f"Batas request Buffer tercapai. Coba lagi dalam {resp.headers.get('Retry-After', '?')} detik.")
    if resp.status_code == 401:
        raise BufferError("API key Buffer tidak valid.")
    try:
        body = resp.json()
    except ValueError as e:
        raise BufferError(f"Respons Buffer tidak terbaca (HTTP {resp.status_code}).") from e
    if body.get("errors"):
        err = body["errors"][0]
        code = (err.get("extensions") or {}).get("code", "")
        raise BufferError(f"Buffer: {err.get('message', 'error')}" + (f" ({code})" if code else ""))
    return body.get("data") or {}


def account_channels(acc: dict, refresh: bool = False) -> list[dict]:
    """Channel satu akun. Di-cache 10 menit supaya hemat kuota (Free: 250 request/hari)."""
    cached = _channels_cache.get(acc["id"])
    if not refresh and cached and time.time() - cached[0] < 600:
        return cached[1]
    orgs = graphql("query { account { organizations { id name } } }", key=acc["api_key"])["account"]["organizations"]
    channels = []
    for org in orgs:
        data = graphql(
            """query Channels($input: ChannelsInput!) {
              channels(input: $input) { id name displayName service avatar isDisconnected isLocked }
            }""",
            {"input": {"organizationId": org["id"]}}, key=acc["api_key"],
        )
        for ch in data.get("channels") or []:
            ch["organization"] = org["name"]
            ch["supportsVideo"] = ch["service"] in VIDEO_SERVICES
            ch["account_id"] = acc["id"]
            ch["account"] = acc["label"]
            ch["key"] = f"{acc['id']}:{ch['id']}"  # unik lintas akun
            channels.append(ch)
    _channels_cache[acc["id"]] = (time.time(), channels)
    return channels


def channels_and_errors(refresh: bool = False, account_id: str | None = None) -> tuple[list[dict], list[str]]:
    """Channel dari satu akun atau gabungan semua akun.

    Akun yang bermasalah (key dicabut, kuota habis) tidak menghentikan akun lain;
    masalahnya dikembalikan terpisah supaya bisa ditampilkan sebagai peringatan.
    """
    targets = [account(account_id)] if account_id else accounts()
    if not targets:
        raise BufferError("Belum ada akun Buffer. Tambahkan di Pengaturan "
                          "(API key dibuat di publish.buffer.com/settings/api).")
    channels, errors = [], []
    for acc in targets:
        try:
            channels += account_channels(acc, refresh)
        except BufferError as e:
            errors.append(f"{acc['label']}: {e}")
    if errors and not channels:
        raise BufferError(" | ".join(errors))
    return channels, errors


def list_channels(refresh: bool = False, account_id: str | None = None) -> list[dict]:
    return channels_and_errors(refresh, account_id)[0]


def _metadata(service: str, title: str) -> dict | None:
    """Metadata wajib per platform agar video terkirim sebagai format video pendek."""
    if service == "instagram":
        return {"instagram": {"type": "reel", "shouldShareToFeed": True}}
    if service == "facebook":
        return {"facebook": {"type": "reel"}}
    if service == "youtube":
        return {"youtube": {"title": title[:100], "categoryId": "22", "privacy": "public"}}
    return None


CREATE_POST = """mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess { post { id status dueAt externalLink } }
    ... on MutationError { message }
  }
}"""


def create_video_post(channel: dict, text: str, video_url: str, title: str, mode: str,
                      due_at: str | None = None) -> dict:
    key = api_key(channel.get("account_id"))
    if mode not in ("addToQueue", "shareNow", "shareNext", "customScheduled"):
        raise BufferError(f"Mode posting tidak dikenal: {mode}")
    post_input: dict = {
        "channelId": channel["id"],
        "text": text,
        "schedulingType": "automatic",
        "mode": mode,
        "needsApproval": False,
        "assets": [{"video": {"url": video_url, "metadata": {"thumbnailOffset": 1000}}}],
        "source": "clipping-studio",
    }
    if mode == "customScheduled":
        if not due_at:
            raise BufferError("Waktu jadwal belum diisi.")
        post_input["dueAt"] = due_at
    meta = _metadata(channel["service"], title)
    if meta:
        post_input["metadata"] = meta
    result = graphql(CREATE_POST, {"input": post_input}, key=key).get("createPost") or {}
    if result.get("post") is None:
        raise BufferError(result.get("message") or f"Buffer menolak post ({result.get('__typename', 'unknown')}).")
    return result["post"]


def post_statuses(post_ids: list[str], account_id: str | None = None) -> dict[str, dict]:
    """Status terbaru beberapa post sekaligus (satu request per akun, maks 30 alias)."""
    ids = post_ids[:30]
    if not ids:
        return {}
    fields = "id status dueAt sentAt externalLink error { message }"
    params = ", ".join(f"$id{i}: PostId!" for i in range(len(ids)))
    body = "\n".join(f"  p{i}: post(input: {{ id: $id{i} }}) {{ {fields} }}" for i in range(len(ids)))
    data = graphql(f"query PostStatuses({params}) {{\n{body}\n}}",
                   {f"id{i}": pid for i, pid in enumerate(ids)}, key=api_key(account_id))
    return {v["id"]: v for v in data.values() if v}
