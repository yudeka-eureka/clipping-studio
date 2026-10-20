import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from app import main


def _job(tmp_path, name="Podcast: episode / 1", clips=None):
    job_id = "job-test"
    job_dir = tmp_path / job_id / "clips"
    job_dir.mkdir(parents=True)
    main.store.jobs[job_id] = {"id": job_id, "name": name, "clips": clips or []}
    return job_id, job_dir


def test_download_all_contains_ready_videos_and_subtitles(tmp_path, monkeypatch):
    job_id, clips_dir = _job(
        tmp_path,
        clips=[
            {"status": "ready", "file": "clips/clip_a.mp4", "srt": "clips/clip_a.srt"},
            {"status": "rendering", "file": "clips/clip_b.mp4", "srt": "clips/clip_b.srt"},
        ],
    )
    (clips_dir / "clip_a.mp4").write_bytes(b"video-a")
    (clips_dir / "clip_a.srt").write_text("subtitle-a", encoding="utf-8")
    (clips_dir / "clip_b.mp4").write_bytes(b"video-b")
    monkeypatch.setattr(main.store, "dir", lambda _job_id: tmp_path / _job_id)

    response = main.download_all_clips(job_id)

    assert response.media_type == "application/zip"
    assert response.filename == "clips_Podcast_episode_1.zip"
    with zipfile.ZipFile(response.path) as archive:
        assert set(archive.namelist()) == {"clip_a.mp4", "clip_a.srt"}
        assert archive.read("clip_a.mp4") == b"video-a"

    Path(response.path).unlink(missing_ok=True)
    main.store.jobs.pop(job_id, None)


def test_download_all_returns_400_without_ready_clips(tmp_path, monkeypatch):
    job_id, _ = _job(tmp_path, clips=[{"status": "rendering", "file": "clips/clip.mp4"}])
    monkeypatch.setattr(main.store, "dir", lambda _job_id: tmp_path / _job_id)

    with pytest.raises(HTTPException) as error:
        main.download_all_clips(job_id)

    assert error.value.status_code == 400
    main.store.jobs.pop(job_id, None)


def test_download_all_returns_404_for_unknown_job():
    with pytest.raises(HTTPException) as error:
        main.download_all_clips("does-not-exist")

    assert error.value.status_code == 404


def test_download_all_enforces_job_ownership_isolation(tmp_path, monkeypatch):
    owner_sid = "11111111-2222-4333-8444-555555555555"
    attacker_sid = "99999999-8888-4777-8666-555555555555"

    job_id, clips_dir = _job(
        tmp_path,
        clips=[
            {"status": "ready", "file": "clips/clip_a.mp4", "srt": "clips/clip_a.srt"},
        ],
    )
    main.store.jobs[job_id]["owner_session_id"] = owner_sid
    (clips_dir / "clip_a.mp4").write_bytes(b"video-a")
    (clips_dir / "clip_a.srt").write_text("subtitle-a", encoding="utf-8")
    monkeypatch.setattr(main.store, "dir", lambda _job_id: tmp_path / _job_id)

    # 1. Creator dapat mengunduh klip miliknya
    response = main.download_all_clips(job_id, session_id=owner_sid)
    assert response.media_type == "application/zip"
    Path(response.path).unlink(missing_ok=True)

    # 2. Pengguna lain dengan session_id berbeda ditolak (403 Forbidden)
    with pytest.raises(HTTPException) as error:
        main.download_all_clips(job_id, session_id=attacker_sid)
    assert error.value.status_code == 403

    # 3. Request tanpa session_id ditolak (403 Forbidden)
    with pytest.raises(HTTPException) as error:
        main.download_all_clips(job_id, session_id="")
    assert error.value.status_code == 403

    main.store.jobs.pop(job_id, None)


def test_download_all_via_testclient_with_cookie_and_header(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    client = TestClient(main.app)

    owner_sid = "11111111-2222-4333-8444-555555555555"
    attacker_sid = "99999999-8888-4777-8666-555555555555"

    job_id, clips_dir = _job(
        tmp_path,
        clips=[
            {"status": "ready", "file": "clips/clip_a.mp4", "srt": "clips/clip_a.srt"},
        ],
    )
    main.store.jobs[job_id]["owner_session_id"] = owner_sid
    (clips_dir / "clip_a.mp4").write_bytes(b"video-a")
    (clips_dir / "clip_a.srt").write_text("subtitle-a", encoding="utf-8")
    monkeypatch.setattr(main.store, "dir", lambda _job_id: tmp_path / _job_id)

    # 1. Akses via Header X-Session-ID
    res_header = client.get(f"/api/jobs/{job_id}/download-all", headers={"X-Session-ID": owner_sid})
    assert res_header.status_code == 200
    assert res_header.headers["content-type"] == "application/zip"

    # 2. Akses via HTTP Cookie session_id (dipakai browser pada link <a> / <video>)
    client.cookies.set("session_id", owner_sid)
    res_cookie = client.get(f"/api/jobs/{job_id}/download-all")
    assert res_cookie.status_code == 200
    assert res_cookie.headers["content-type"] == "application/zip"

    # 3. Akses dengan Cookie milik session lain ditolak (403)
    client.cookies.set("session_id", attacker_sid)
    res_forbidden = client.get(f"/api/jobs/{job_id}/download-all")
    assert res_forbidden.status_code == 403

    # 4. Akses tanpa cookie/header ditolak (403)
    client.cookies.clear()
    res_unauthed = client.get(f"/api/jobs/{job_id}/download-all")
    assert res_unauthed.status_code == 403

    main.store.jobs.pop(job_id, None)
