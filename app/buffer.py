"""Koneksi ke Buffer GraphQL API (https://developers.buffer.com) untuk posting klip ke media sosial."""
from __future__ import annotations

import os
import time

import httpx

API_URL = os.environ.get("BUFFER_API_URL", "https://api.buffer.com")

# Service yang bisa menerima video lewat Buffer.
VIDEO_SERVICES = {"instagram", "tiktok", "youtube", "facebook", "linkedin", "twitter",
                  "threads", "bluesky", "mastodon", "pinterest", "googlebusiness"}

_channels_cache: tuple[float, list[dict]] | None = None


class BufferError(RuntimeError):
    pass


def api_key() -> str:
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not key:
        raise BufferError("API key Buffer belum diisi. Buat di publish.buffer.com/settings/api lalu isi di Pengaturan.")
    return key


def graphql(query: str, variables: dict | None = None) -> dict:
    try:
        resp = httpx.post(
            API_URL, json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
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


def list_channels(refresh: bool = False) -> list[dict]:
    """Semua channel dari semua organisasi. Di-cache 10 menit supaya hemat kuota (Free: 250 request/hari)."""
    global _channels_cache
    if not refresh and _channels_cache and time.time() - _channels_cache[0] < 600:
        return _channels_cache[1]
    orgs = graphql("query { account { organizations { id name } } }")["account"]["organizations"]
    channels = []
    for org in orgs:
        data = graphql(
            """query Channels($input: ChannelsInput!) {
              channels(input: $input) { id name displayName service avatar isDisconnected isLocked }
            }""",
            {"input": {"organizationId": org["id"]}},
        )
        for ch in data.get("channels") or []:
            ch["organization"] = org["name"]
            ch["supportsVideo"] = ch["service"] in VIDEO_SERVICES
            channels.append(ch)
    _channels_cache = (time.time(), channels)
    return channels


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
    result = graphql(CREATE_POST, {"input": post_input}).get("createPost") or {}
    if result.get("post") is None:
        raise BufferError(result.get("message") or f"Buffer menolak post ({result.get('__typename', 'unknown')}).")
    return result["post"]


def post_statuses(post_ids: list[str]) -> dict[str, dict]:
    """Status terbaru beberapa post sekaligus (satu request, maks 30 alias)."""
    ids = post_ids[:30]
    if not ids:
        return {}
    fields = "id status dueAt sentAt externalLink error { message }"
    params = ", ".join(f"$id{i}: PostId!" for i in range(len(ids)))
    body = "\n".join(f"  p{i}: post(input: {{ id: $id{i} }}) {{ {fields} }}" for i in range(len(ids)))
    data = graphql(f"query PostStatuses({params}) {{\n{body}\n}}", {f"id{i}": pid for i, pid in enumerate(ids)})
    return {v["id"]: v for v in data.values() if v}
